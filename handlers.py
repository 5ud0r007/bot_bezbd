# handlers.py

from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import ContextTypes
from config import DB_NAME, ADMIN_USER_ID
import database as db

user_keyboard = ReplyKeyboardMarkup([["Оставить тикет"]], resize_keyboard=True)

def get_admin_keyboard():
    updated_count = db.get_updated_tickets_count()
    if updated_count > 0:
        return ReplyKeyboardMarkup([["Активные тикеты (+{})".format(updated_count)]], resize_keyboard=True)
    else:
        return ReplyKeyboardMarkup([["Активные тикеты"]], resize_keyboard=True)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if user_id == ADMIN_USER_ID:
        await update.message.reply_text(
            "Привет, администратор! Используйте кнопки ниже для управления тикетами.",
            reply_markup=get_admin_keyboard()
        )
    else:
        active_ticket = db.get_active_tickets()
        if active_ticket:
            await update.message.reply_text(
                "Привет! У вас есть активный тикет. Вы можете закрыть его или написать сообщение.",
                reply_markup=ReplyKeyboardMarkup([["Закрыть тикет"]], resize_keyboard=True)
            )
        else:
            await update.message.reply_text(
                "Привет! Используйте кнопку ниже, чтобы создать новый тикет.",
                reply_markup=user_keyboard
            )

async def create_ticket(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if user_id == ADMIN_USER_ID:
        await update.message.reply_text("Вы администратор. Используйте кнопку 'Активные тикеты'.")
        return

    username = update.message.from_user.username or update.message.from_user.first_name

    active_ticket = db.get_active_tickets()
    if active_ticket:
        await update.message.reply_text("У вас уже есть активный тикет. Закройте его, чтобы создать новый.")
    else:
        await update.message.reply_text("Опишите ваш запрос:")
        context.user_data["awaiting_ticket_description"] = True

async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    message = update.message.text

    if user_id != ADMIN_USER_ID:
        if context.user_data.get("awaiting_ticket_description"):
            username = update.message.from_user.username or update.message.from_user.first_name
            ticket_id = db.add_ticket(user_id, username, message)
            db.add_ticket_message(ticket_id, user_id, message)  # Сохраняем первое сообщение
            await update.message.reply_text("Ваш тикет создан. Ожидайте ответа администратора.")
            context.user_data["awaiting_ticket_description"] = False

            await update.message.reply_text(
                "Теперь у вас есть активный тикет. Вы можете закрыть его или написать сообщение.",
                reply_markup=ReplyKeyboardMarkup([["Закрыть тикет"]], resize_keyboard=True)
            )

            await context.bot.send_message(
                chat_id=ADMIN_USER_ID,
                text=f"Создан новый тикет (ID {ticket_id}) от пользователя {username}.\n\nСообщение: {message}",
                reply_markup=ReplyKeyboardMarkup([["Ответить на тикет ({})".format(ticket_id)]], resize_keyboard=True)
            )
        else:

            active_ticket = db.get_active_tickets()
            if active_ticket:
                ticket_id = active_ticket[0][0]
                db.add_ticket_message(ticket_id, user_id, message)
                await update.message.reply_text("Ваше сообщение добавлено в тикет.")

                await context.bot.send_message(
                    chat_id=ADMIN_USER_ID,
                    text=f"Тикет (ID {ticket_id}) обновлен пользователем {username}.\n\nНовое сообщение: {message}",
                    reply_markup=ReplyKeyboardMarkup([["Ответить на тикет ({})".format(ticket_id)]], resize_keyboard=True)
                )
            else:
                await update.message.reply_text("Используйте кнопки для управления тикетами.")
        return

    if context.user_data.get("awaiting_ticket_id"):
        try:
            ticket_id = int(message)
            ticket_messages = db.get_ticket_messages(ticket_id)
            if ticket_messages:
                response = "Переписка по тикету:\n\n"
                for msg in ticket_messages:
                    sender = "Админ" if msg[0] == ADMIN_USER_ID else "Пользователь"
                    response += f"{sender}: {msg[1]}\n"
                await update.message.reply_text(response)
                context.user_data["selected_ticket_id"] = ticket_id
                context.user_data["awaiting_ticket_id"] = False
                context.user_data["awaiting_admin_response"] = True
            else:
                await update.message.reply_text("Тикет с таким ID не найден.")
        except ValueError:
            await update.message.reply_text("Пожалуйста, введите корректный ID тикета (число).")

    elif context.user_data.get("awaiting_admin_response"):
        ticket_id = context.user_data["selected_ticket_id"]
        db.add_ticket_message(ticket_id, ADMIN_USER_ID, message)  # Сохраняем ответ администратора

        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute('''UPDATE tickets SET updated = FALSE WHERE id = ?''', (ticket_id,))
        conn.commit()
        conn.close()

        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute('''SELECT user_id, username FROM tickets WHERE id = ?''', (ticket_id,))
        ticket = cursor.fetchone()
        conn.close()

        if ticket:
            user_id_to_reply = ticket[0]
            username = ticket[1]
            try:
                await context.bot.send_message(
                    chat_id=user_id_to_reply,
                    text=f"Ответ администратора на ваш тикет (ID {ticket_id}):\n\n{message}"
                )
                await update.message.reply_text(f"Ваш ответ отправлен пользователю @{username}.")
            except Exception as e:
                await update.message.reply_text(f"Ошибка при отправке сообщения пользователю: {e}")
        else:
            await update.message.reply_text("Тикет не найден.")

        context.user_data.pop("selected_ticket_id", None)
        context.user_data.pop("awaiting_admin_response", None)
    else:
        await update.message.reply_text("Используйте кнопки для управления тикетами.")

async def close_user_ticket(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if user_id == ADMIN_USER_ID:
        await update.message.reply_text("Вы администратор. Используйте кнопку 'Активные тикеты'.")
        return

    active_ticket = db.get_active_tickets()
    if active_ticket:
        db.close_ticket(active_ticket[0][0])
        await update.message.reply_text("Ваш тикет закрыт.")
        await update.message.reply_text(
            "Теперь у вас нет активных тикетов. Используйте кнопку ниже, чтобы создать новый.",
            reply_markup=user_keyboard
        )
    else:
        await update.message.reply_text("У вас нет активных тикетов.")

async def reply_to_ticket(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if user_id != ADMIN_USER_ID:
        await update.message.reply_text("У вас нет доступа к этой команде.")
        return

    ticket_id = int(update.message.text.split("(")[1].split(")")[0])

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''SELECT username FROM tickets WHERE id = ?''', (ticket_id,))
    ticket = cursor.fetchone()
    conn.close()

    if ticket:
        username = ticket[0]
        await update.message.reply_text(
            f"Вы отвечаете на тикет №{ticket_id} @{username}.",
            reply_markup=ReplyKeyboardMarkup([["Активные тикеты"]], resize_keyboard=True)
        )
        # Сохраняем ID тикета в контексте
        context.user_data["selected_ticket_id"] = ticket_id
        context.user_data["awaiting_admin_response"] = True
    else:
        await update.message.reply_text("Тикет не найден.")

async def show_tickets(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if user_id != ADMIN_USER_ID:
        await update.message.reply_text("У вас нет доступа к этой команде.")
        return

    tickets = db.get_active_tickets_with_updates()
    if tickets:
        buttons = []
        for ticket in tickets:
            ticket_id, user_id, username, message, updated, is_updated = ticket

            updated_status = " (Обновлено)" if is_updated else ""
            button_text = f"Тикет {ticket_id} от @{username}{updated_status}"
            buttons.append([button_text])

        buttons.append(["Назад"])

        keyboard = ReplyKeyboardMarkup(buttons, resize_keyboard=True)

        await update.message.reply_text(
            "Выберите тикет для ответа:",
            reply_markup=keyboard
        )
    else:
        await update.message.reply_text("Активных тикетов нет.")

async def handle_ticket_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if user_id != ADMIN_USER_ID:
        await update.message.reply_text("У вас нет доступа к этой команде.")
        return

    try:
        ticket_id = int(update.message.text.split()[1])  # Пример: "Тикет 13 от @username"
    except (IndexError, ValueError):
        await update.message.reply_text("Ошибка при обработке тикета.")
        return

    ticket_messages = db.get_ticket_messages(ticket_id)
    if ticket_messages:
        response = "Переписка по тикету:\n\n"
        for msg in ticket_messages:
            sender = "Админ" if msg[0] == ADMIN_USER_ID else "Пользователь"
            response += f"{sender}: {msg[1]}\n"
        await update.message.reply_text(response)

        context.user_data["selected_ticket_id"] = ticket_id
        context.user_data["awaiting_admin_response"] = True

        await update.message.reply_text(
            "Введите ваш ответ:",
            reply_markup=ReplyKeyboardMarkup([["Назад"]], resize_keyboard=True)
        )
    else:
        await update.message.reply_text("Тикет не найден.")

async def handle_back(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if user_id != ADMIN_USER_ID:
        await update.message.reply_text("У вас нет доступа к этой команде.")
        return

    await update.message.reply_text(
        "Используйте кнопки для управления тикетами.",
        reply_markup=get_admin_keyboard()
    )