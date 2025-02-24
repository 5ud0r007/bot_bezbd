from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import sqlite3
import re
from openai import OpenAI
from config import BOT_TOKEN, ADMIN_USER_ID, DB_NAME, OPENAI_API_KEY, OPENAI_PROMPT

client = OpenAI(api_key=OPENAI_API_KEY, base_url="https://api.aitunnel.ru/v1/")

def get_chatgpt_response(prompt):
    try:
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": OPENAI_PROMPT},
                {"role": "user", "content": prompt}
            ]
        )
        return response.choices[0].message.content
    except Exception as e:
        print(f"Ошибка при запросе к ChatGPT: {e}")
        return None

def should_create_ticket(response):
    return "вызываю администратора для решения вашего вопроса" in response.lower()

def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS tickets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            username TEXT,
            message TEXT NOT NULL,
            status TEXT DEFAULT 'open',
            updated BOOLEAN DEFAULT FALSE
        )
    ''')
    cursor.execute("PRAGMA table_info(tickets)")
    columns = [column[1] for column in cursor.fetchall()]
    if 'updated' not in columns:
        cursor.execute('ALTER TABLE tickets ADD COLUMN updated BOOLEAN DEFAULT FALSE')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS ticket_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticket_id INTEGER NOT NULL,
            sender_id INTEGER NOT NULL,
            message TEXT NOT NULL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (ticket_id) REFERENCES tickets (id)
        )
    ''')
    conn.commit()
    conn.close()

def add_ticket(user_id: int, username: str, message: str):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('INSERT INTO tickets (user_id, username, message) VALUES (?, ?, ?)', (user_id, username, message))
    ticket_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return ticket_id

def add_ticket_message(ticket_id: int, sender_id: int, message: str):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('INSERT INTO ticket_messages (ticket_id, sender_id, message) VALUES (?, ?, ?)', (ticket_id, sender_id, message))
    if sender_id != ADMIN_USER_ID:
        cursor.execute('UPDATE tickets SET updated = TRUE WHERE id = ?', (ticket_id,))
    conn.commit()
    conn.close()

def get_active_tickets():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('SELECT id, user_id, username, message, updated FROM tickets WHERE status = "open"')
    tickets = cursor.fetchall()
    conn.close()
    return tickets

def get_updated_tickets_count():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) FROM tickets WHERE status = "open" AND updated = TRUE')
    count = cursor.fetchone()[0]
    conn.close()
    return count

def get_ticket_messages(ticket_id: int):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('SELECT sender_id, message, timestamp FROM ticket_messages WHERE ticket_id = ? ORDER BY timestamp', (ticket_id,))
    messages = cursor.fetchall()
    conn.close()
    return messages

def close_ticket(ticket_id: int):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('UPDATE tickets SET status = "closed" WHERE id = ?', (ticket_id,))
    conn.commit()
    conn.close()

init_db()

user_keyboard = ReplyKeyboardMarkup([["Оставить тикет 📩"]], resize_keyboard=True)

def get_admin_keyboard(last_ticket_id=None):
    updated_count = get_updated_tickets_count()
    buttons = []
    if last_ticket_id:
        buttons.append([f"Ответить на тикет ({last_ticket_id}) 📩"])
    if updated_count > 0:
        buttons.append([f"Активные тикеты 📋 (+{updated_count})"])
    else:
        buttons.append(["Активные тикеты 📋"])
    return ReplyKeyboardMarkup(buttons, resize_keyboard=True)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if user_id == ADMIN_USER_ID:
        await update.message.reply_text("Привет, администратор! 👋 Используй кнопки ниже для управления тикетами. 🛠️", reply_markup=get_admin_keyboard())
    else:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute('SELECT id FROM tickets WHERE user_id = ? AND status = "open"', (user_id,))
        active_ticket = cursor.fetchone()
        conn.close()
        if active_ticket:
            await update.message.reply_text("Привет! 👋 У тебя есть активный тикет. Закрой его или напиши сообщение. 📝", reply_markup=ReplyKeyboardMarkup([["Закрыть тикет 🚪"]], resize_keyboard=True))
        else:
            await update.message.reply_text("Привет! 👋 Используй кнопку ниже, чтобы создать новый тикет. 📩", reply_markup=user_keyboard)

async def create_ticket(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if user_id == ADMIN_USER_ID:
        await update.message.reply_text("Ты администратор. Используй кнопку 'Активные тикеты 📋'.")
        return
    username = update.message.from_user.username or update.message.from_user.first_name
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('SELECT id FROM tickets WHERE user_id = ? AND status = "open"', (user_id,))
    active_ticket = cursor.fetchone()
    conn.close()
    if active_ticket:
        await update.message.reply_text("У тебя уже есть активный тикет. Закрой его, чтобы создать новый. 🚪")
    else:
        await update.message.reply_text("Опиши свой запрос: 📝")
        context.user_data["awaiting_ticket_description"] = True

async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    message = update.message.text
    if user_id != ADMIN_USER_ID:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute('SELECT id FROM tickets WHERE user_id = ? AND status = "open"', (user_id,))
        active_ticket = cursor.fetchone()
        conn.close()

        if active_ticket:
            await update.message.reply_text("Используй кнопки для управления тикетами. 🎛️", reply_markup=ReplyKeyboardMarkup([["Закрыть тикет 🚪"]], resize_keyboard=True))
            return

        if context.user_data.get("awaiting_ticket_description"):
            username = update.message.from_user.username or update.message.from_user.first_name
            chatgpt_response = get_chatgpt_response(message)
            if chatgpt_response:
                await update.message.reply_text(f"🤖: {chatgpt_response}")
                if should_create_ticket(chatgpt_response):
                    ticket_id = add_ticket(user_id, username, message)
                    add_ticket_message(ticket_id, user_id, message)
                    add_ticket_message(ticket_id, ADMIN_USER_ID, chatgpt_response)
                    await update.message.reply_text("Тикет передан админу, скоро с вами свяжутся. 📩", reply_markup=ReplyKeyboardMarkup([["Закрыть тикет 🚪"]], resize_keyboard=True))
                    await context.bot.send_message(chat_id=ADMIN_USER_ID, text=f"Создан новый тикет (ID {ticket_id}) от пользователя {username}.\n\nСообщение: {message}", reply_markup=get_admin_keyboard(last_ticket_id=ticket_id))
                else:
                    await update.message.reply_text("Если вы не получили ответ на свой вопрос, попробуйте создать тикет заново.", reply_markup=ReplyKeyboardMarkup([["Оставить тикет 📩"]], resize_keyboard=True))
            context.user_data["awaiting_ticket_description"] = False
        else:
            await update.message.reply_text("Используй кнопки для управления тикетами. 🎛️", reply_markup=user_keyboard)
        return

    if re.match(r"^Назад\s*🔙$", message):
        await update.message.reply_text("Возвращаемся в главное меню. 🏠", reply_markup=get_admin_keyboard())
        context.user_data.pop("selected_ticket_id", None)
        context.user_data.pop("awaiting_admin_response", None)
        return
    if re.match(r"^Активные тикеты\s*📋", message):
        await show_tickets(update, context)
        return
    if context.user_data.get("awaiting_admin_response"):
        ticket_id = context.user_data["selected_ticket_id"]
        add_ticket_message(ticket_id, ADMIN_USER_ID, message)
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute('UPDATE tickets SET updated = FALSE WHERE id = ?', (ticket_id,))
        conn.commit()
        conn.close()
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute('SELECT user_id, username FROM tickets WHERE id = ?', (ticket_id,))
        ticket = cursor.fetchone()
        conn.close()
        if ticket:
            user_id_to_reply = ticket[0]
            username = ticket[1]
            try:
                await context.bot.send_message(chat_id=user_id_to_reply, text=f"Ответ администратора на твой тикет (ID {ticket_id}):\n\n{message}")
                await update.message.reply_text(f"Ответ отправлен пользователю @{username}. ✅", reply_markup=get_admin_keyboard())
            except Exception as e:
                await update.message.reply_text(f"Ошибка при отправке сообщения: {e}")
        else:
            await update.message.reply_text("Тикет не найден. ❌")
        context.user_data.pop("selected_ticket_id", None)
        context.user_data.pop("awaiting_admin_response", None)
    else:
        await update.message.reply_text("Используй кнопки для управления тикетами. 🎛️")

async def close_user_ticket(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if user_id == ADMIN_USER_ID:
        if "selected_ticket_id" in context.user_data:
            ticket_id = context.user_data["selected_ticket_id"]
            close_ticket(ticket_id)
            conn = sqlite3.connect(DB_NAME)
            cursor = conn.cursor()
            cursor.execute('SELECT user_id, username FROM tickets WHERE id = ?', (ticket_id,))
            ticket = cursor.fetchone()
            conn.close()
            if ticket:
                user_id_to_reply = ticket[0]
                try:
                    await context.bot.send_message(chat_id=user_id_to_reply, text=f"Твой тикет (ID {ticket_id}) был закрыт администратором. 🚪", reply_markup=ReplyKeyboardMarkup([["Оставить тикет 📩"]], resize_keyboard=True))
                except Exception as e:
                    await update.message.reply_text(f"Ошибка при отправке уведомления пользователю: {e}")
            await update.message.reply_text("Тикет успешно закрыт. 🚪", reply_markup=get_admin_keyboard())
            context.user_data.pop("selected_ticket_id", None)
            context.user_data.pop("awaiting_admin_response", None)
        else:
            await update.message.reply_text("Выбери тикет для закрытия. ❌")
    else:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute('SELECT id FROM tickets WHERE user_id = ? AND status = "open"', (user_id,))
        active_ticket = cursor.fetchone()
        conn.close()
        if active_ticket:
            ticket_id = active_ticket[0]
            close_ticket(ticket_id)
            await update.message.reply_text("Тикет закрыт. ✅", reply_markup=ReplyKeyboardMarkup([["Оставить тикет 📩"]], resize_keyboard=True))
            await context.bot.send_message(chat_id=ADMIN_USER_ID, text=f"Тикет (ID {ticket_id}) был закрыт клиентом.", reply_markup=get_admin_keyboard())
        else:
            await update.message.reply_text("У тебя нет активных тикетов. ❌", reply_markup=ReplyKeyboardMarkup([["Оставить тикет 📩"]], resize_keyboard=True))

async def reply_to_ticket(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if user_id != ADMIN_USER_ID:
        await update.message.reply_text("У тебя нет доступа к этой команде. ❌")
        return
    ticket_id = int(re.search(r"\((\d+)\)", update.message.text).group(1))
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('SELECT username, status FROM tickets WHERE id = ?', (ticket_id,))
    ticket = cursor.fetchone()
    conn.close()
    if ticket:
        username, status = ticket
        if status == "closed":
            await update.message.reply_text("Тикет закрыт. ❌")
            return
        messages = get_ticket_messages(ticket_id)
        response = f"Переписка по тикету {ticket_id} с @{username}:\n\n"
        for msg in messages:
            sender = "Админ" if msg[0] == ADMIN_USER_ID else "Пользователь"
            response += f"{sender}: {msg[1]}\n"
        await update.message.reply_text(response, reply_markup=ReplyKeyboardMarkup([["Закрыть тикет ❌", "Назад 🔙"]], resize_keyboard=True))
        context.user_data["selected_ticket_id"] = ticket_id
        context.user_data["awaiting_admin_response"] = True
    else:
        await update.message.reply_text("Тикет не найден. ❌")

async def show_tickets(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if user_id != ADMIN_USER_ID:
        await update.message.reply_text("У тебя нет доступа к этой команде. ❌")
        return
    tickets = get_active_tickets()
    if tickets:
        response = "Активные тикеты: 📋\n\n"
        for ticket in tickets:
            updated_status = " (Обновлено) 🔄" if ticket[4] else ""
            response += f"ID: {ticket[0]}\nПользователь: {ticket[2]} (ID: {ticket[1]})\nЗапрос: {ticket[3]}{updated_status}\n\n"
        response += "Выбери тикет для ответа: 📩"
        buttons = [[f"Ответить на тикет ({ticket[0]}) 📩"] for ticket in tickets]
        buttons.append(["Назад 🔙"])
        await update.message.reply_text(response, reply_markup=ReplyKeyboardMarkup(buttons, resize_keyboard=True))
    else:
        await update.message.reply_text("Активных тикетов нет. ❌")

def main():
    application = Application.builder().token(BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.Regex(r"^Оставить тикет\s*📩$"), create_ticket))
    application.add_handler(MessageHandler(filters.Regex(r"^Закрыть тикет\s*🚪$"), close_user_ticket))
    application.add_handler(MessageHandler(filters.Regex(r"^Активные тикеты\s*📋"), show_tickets))
    application.add_handler(MessageHandler(filters.Regex(r"^Ответить на тикет \(\d+\)\s*📩$"), reply_to_ticket))
    application.add_handler(MessageHandler(filters.Regex(r"^Закрыть тикет\s*❌$"), close_user_ticket))
    application.add_handler(MessageHandler(filters.Regex(r"^Назад\s*🔙$"), handle_text_message))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message))
    application.run_polling()

if __name__ == '__main__':
    main()

``` Ты бегаешь за девочкой, с которой я был вместе
Ты слушаешь с друзьями мои песни
И если я был бы ещё чуточку известнее
Весь мир перевернул, приставив к горлу лезвие
Лесби — твой выход, ведь ты не найдёшь тут никого похуже
```
