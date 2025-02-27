from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackContext
from sqlalchemy import create_engine, Column, Integer, String, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import declarative_base, sessionmaker, relationship
from sqlalchemy.sql import func
from openai import OpenAI
from config import BOT_TOKEN, ADMIN_USER_ID, DB_NAME, OPENAI_API_KEY, OPENAI_PROMPT
from datetime import datetime, timedelta
import re
import asyncio

client = OpenAI(api_key=OPENAI_API_KEY, base_url="https://api.aitunnel.ru/v1/")
BOT_USER_ID = 0

Base = declarative_base()
engine = create_engine(f'sqlite:///{DB_NAME}')
Session = sessionmaker(bind=engine)


class Complaint(Base):
    __tablename__ = 'complaints'
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, nullable=False)
    username = Column(String)
    message = Column(String, nullable=False)
    status = Column(String, default='open')
    updated = Column(Boolean, default=False)
    created_at = Column(DateTime, default=func.now())
    messages = relationship("ComplaintMessage", back_populates="complaint")


class ComplaintMessage(Base):
    __tablename__ = 'complaint_messages'
    id = Column(Integer, primary_key=True)
    complaint_id = Column(Integer, ForeignKey('complaints.id'), nullable=False)
    sender_id = Column(Integer, nullable=False)
    message = Column(String, nullable=False)
    timestamp = Column(DateTime, default=func.now())
    complaint = relationship("Complaint", back_populates="messages")


Base.metadata.create_all(engine)

tickets = {}

user_keyboard = ReplyKeyboardMarkup([["Общение с ботом 🤖"]], resize_keyboard=True)


def get_admin_keyboard(last_complaint_id=None):
    with Session() as session:
        updated_count = session.query(Complaint).filter(
            Complaint.status == 'open',
            Complaint.updated == True
        ).count()

        buttons = []
        if last_complaint_id:
            buttons.append([f"Ответить на жалобу ({last_complaint_id}) 📩"])
        if updated_count > 0:
            buttons.append([f"Активные жалобы 📋 (+{updated_count})"])
        else:
            buttons.append(["Активные жалобы 📋"])
        return ReplyKeyboardMarkup(buttons, resize_keyboard=True)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if user_id == ADMIN_USER_ID:
        await update.message.reply_text("Привет, администратор! 👋 Используй кнопки ниже для управления жалобами. 🛠️",
                                        reply_markup=get_admin_keyboard())
    else:
        if user_id in tickets:
            ticket_type = "жалобу" if tickets[user_id]["is_complaint"] else "тикет"
            await update.message.reply_text(
                f"У вас уже есть активная {ticket_type}. Продолжайте общение или закройте его.",
                reply_markup=ReplyKeyboardMarkup([["Закрыть жалобу ❌"] if tickets[user_id]["is_complaint"]
                                                  else ["Закрыть тикет 🚪"]], resize_keyboard=True)
            )
        else:
            await update.message.reply_text(
                f"Привет, {update.message.from_user.first_name}! 👋 Начните общение с ботом.",
                reply_markup=user_keyboard
            )


async def create_ticket(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if user_id == ADMIN_USER_ID:
        await update.message.reply_text("Используйте панель администратора для работы с жалобами.")
        return

    if user_id in tickets:
        await update.message.reply_text("У вас уже есть активный тикет. Закройте его перед созданием нового.")
        return

    tickets[user_id] = {
        "messages": [],
        "last_activity": datetime.now(),
        "is_complaint": False,
        "complaint_id": None
    }
    await update.message.reply_text("Опишите ваш запрос:",
                                    reply_markup=ReplyKeyboardMarkup([["Закрыть тикет 🚪"]], resize_keyboard=True))


async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    message = update.message.text

    if user_id == ADMIN_USER_ID:
        await handle_admin_message(update, context, message)
        return

    if user_id not in tickets:
        await update.message.reply_text("Начните общение с ботом, используя кнопку ниже.", reply_markup=user_keyboard)
        return

    ticket = tickets[user_id]
    ticket["last_activity"] = datetime.now()

    if ticket["is_complaint"]:
        await handle_complaint_message(update, context, message, ticket)
    else:
        await handle_bot_conversation(update, context, message, ticket)


async def handle_admin_message(update: Update, context: ContextTypes.DEFAULT_TYPE, message: str):
    if re.match(r"^Назад\s*🔙$", message):
        await update.message.reply_text("Главное меню:", reply_markup=get_admin_keyboard())
        context.user_data.clear()
        return

    if "selected_complaint_id" in context.user_data:
        await handle_admin_response(update, context, message)
        return

    if re.match(r"^Активные жалобы", message):
        await show_complaints(update, context)
    elif re.match(r"^Ответить на жалобу", message):
        await reply_to_complaint(update, context)


async def handle_admin_response(update: Update, context: ContextTypes.DEFAULT_TYPE, message: str):
    complaint_id = context.user_data["selected_complaint_id"]
    with Session() as session:
        complaint = session.query(Complaint).get(complaint_id)
        if not complaint or complaint.status == 'closed':
            await update.message.reply_text("Жалоба не найдена или закрыта", reply_markup=get_admin_keyboard())
            return


        new_message = ComplaintMessage(
            complaint_id=complaint_id,
            sender_id=ADMIN_USER_ID,
            message=message
        )
        session.add(new_message)


        complaint.updated = False
        session.commit()


        try:
            await context.bot.send_message(
                chat_id=complaint.user_id,
                text=f"Администратор: {message}"
            )
            await update.message.reply_text(
                "Сообщение отправлено. Продолжайте диалог или закройте жалобу.",
                reply_markup=ReplyKeyboardMarkup([["Назад 🔙", "Закрыть жалобу ❌"]], resize_keyboard=True)
            )
        except Exception as e:
            await update.message.reply_text(f"Ошибка отправки: {str(e)}")


async def handle_complaint_message(update: Update, context: ContextTypes.DEFAULT_TYPE, message: str, ticket: dict):
    with Session() as session:
        new_message = ComplaintMessage(
            complaint_id=ticket["complaint_id"],
            sender_id=update.message.from_user.id,
            message=message
        )
        session.add(new_message)

        complaint = session.query(Complaint).get(ticket["complaint_id"])
        if complaint:
            complaint.updated = True
            session.commit()

    await context.bot.send_message(
        chat_id=ADMIN_USER_ID,
        text=f"Новое сообщение по жалобе {ticket['complaint_id']}:\n\n{message}"
    )


async def handle_bot_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE, message: str, ticket: dict):
    ticket["messages"].append({"role": "user", "content": message})

    response = get_chatgpt_response(ticket["messages"])
    if not response:
        await update.message.reply_text("Ошибка обработки запроса")
        return

    ticket["messages"].append({"role": "assistant", "content": response})
    await update.message.reply_text(f"🤖: {response}")

    if "администратор" in response.lower():
        await escalate_to_admin(update, context, ticket)


async def escalate_to_admin(update: Update, context: ContextTypes.DEFAULT_TYPE, ticket: dict):
    with Session() as session:
        new_complaint = Complaint(
            user_id=update.message.from_user.id,
            username=update.message.from_user.username,
            message=ticket["messages"][-1]["content"]
        )
        session.add(new_complaint)
        session.commit()

        for msg in ticket["messages"]:
            session.add(ComplaintMessage(
                complaint_id=new_complaint.id,
                sender_id=BOT_USER_ID if msg["role"] == "assistant" else update.message.from_user.id,
                message=msg["content"]
            ))
        session.commit()

        ticket["is_complaint"] = True
        ticket["complaint_id"] = new_complaint.id

        await update.message.reply_text(
            "Ваш запрос передан администратору. Ожидайте ответа.",
            reply_markup=ReplyKeyboardMarkup([["Закрыть жалобу ❌"]], resize_keyboard=True)
        )

        await context.bot.send_message(
            chat_id=ADMIN_USER_ID,
            text=f"Новая жалоба #{new_complaint.id} от @{update.message.from_user.username}",
            reply_markup=get_admin_keyboard(new_complaint.id)
        )


async def close_user_ticket(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if user_id == ADMIN_USER_ID:
        await handle_admin_close(update, context)
    else:
        await handle_user_close(update, context)


async def handle_admin_close(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if "selected_complaint_id" not in context.user_data:
        await update.message.reply_text("Сначала выберите жалобу")
        return

    complaint_id = context.user_data["selected_complaint_id"]
    with Session() as session:
        complaint = session.query(Complaint).get(complaint_id)
        if complaint:
            complaint.status = 'closed'
            session.commit()

            await update.message.reply_text(f"Жалоба #{complaint_id} закрыта",
                                            reply_markup=get_admin_keyboard())
            await context.bot.send_message(
                chat_id=complaint.user_id,
                text=f"Ваша жалоба #{complaint_id} закрыта",
                reply_markup=user_keyboard
            )
        else:
            await update.message.reply_text("Жалоба не найдена")


async def handle_user_close(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if user_id not in tickets:
        await update.message.reply_text("Активных тикетов нет", reply_markup=user_keyboard)
        return

    ticket = tickets.pop(user_id)
    if ticket["is_complaint"]:
        with Session() as session:
            complaint = session.query(Complaint).get(ticket["complaint_id"])
            if complaint:
                complaint.status = 'closed'
                session.commit()
                await context.bot.send_message(
                    chat_id=ADMIN_USER_ID,
                    text=f"Жалоба #{ticket['complaint_id']} закрыта пользователем"
                )

    await update.message.reply_text("Тикет закрыт", reply_markup=user_keyboard)


async def show_complaints(update: Update, context: ContextTypes.DEFAULT_TYPE):
    with Session() as session:
        complaints = session.query(Complaint).filter(
            Complaint.status == 'open'
        ).order_by(Complaint.created_at).all()

        if not complaints:
            await update.message.reply_text("Активных жалоб нет", reply_markup=get_admin_keyboard())
            return

        response = ["Активные жалобы:"]
        buttons = []
        for complaint in complaints:
            status = "🔄 Обновлена" if complaint.updated else "⏳ В ожидании"
            response.append(
                f"#{complaint.id} от @{complaint.username} ({status})\n"
                f"Последнее сообщение: {complaint.message[:50]}..."
            )
            buttons.append([f"Ответить на жалобу ({complaint.id}) 📩"])

        buttons.append(["Назад 🔙"])
        await update.message.reply_text("\n\n".join(response),
                                        reply_markup=ReplyKeyboardMarkup(buttons, resize_keyboard=True))


async def reply_to_complaint(update: Update, context: ContextTypes.DEFAULT_TYPE):
    complaint_id = int(re.search(r"\((\d+)\)", update.message.text).group(1))
    with Session() as session:
        complaint = session.query(Complaint).get(complaint_id)
        if not complaint or complaint.status != 'open':
            await update.message.reply_text("Жалоба не найдена или закрыта")
            return

        messages = session.query(ComplaintMessage).filter(
            ComplaintMessage.complaint_id == complaint_id
        ).order_by(ComplaintMessage.timestamp).all()

        history = ["История переписки:"]
        for msg in messages:
            sender = "Админ" if msg.sender_id == ADMIN_USER_ID else "Пользователь"
            history.append(f"{sender}: {msg.message}")

        context.user_data["selected_complaint_id"] = complaint_id
        await update.message.reply_text("\n".join(history),
                                        reply_markup=ReplyKeyboardMarkup([["Назад 🔙", "Закрыть жалобу ❌"]],
                                                                         resize_keyboard=True))


def get_chatgpt_response(messages):
    try:
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "system", "content": OPENAI_PROMPT}] + messages
        )
        return response.choices[0].message.content
    except Exception as e:
        print(f"ChatGPT error: {str(e)}")
        return None


async def check_inactive_tickets(context: CallbackContext):
    now = datetime.now()
    for user_id, ticket in list(tickets.items()):
        if (now - ticket["last_activity"]) > timedelta(minutes=5):
            del tickets[user_id]
            await context.bot.send_message(user_id, "Тикет закрыт по тайм-ауту", reply_markup=user_keyboard)


def main():
    application = Application.builder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.Regex(r"^Общение с ботом"), create_ticket))
    application.add_handler(MessageHandler(filters.Regex(r"^Закрыть"), close_user_ticket))
    application.add_handler(MessageHandler(filters.Regex(r"^Активные жалобы"), show_complaints))
    application.add_handler(MessageHandler(filters.Regex(r"^Ответить на жалобу"), reply_to_complaint))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message))

    application.job_queue.run_repeating(check_inactive_tickets, interval=300)

    application.run_polling()


if __name__ == '__main__':
    main()
