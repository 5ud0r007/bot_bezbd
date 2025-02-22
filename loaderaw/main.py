from telegram.ext import Application, CommandHandler, MessageHandler, filters
from config import BOT_TOKEN
import handlers

def main():
    application = Application.builder().token(BOT_TOKEN).build()

    # Регистрируем обработчики
    application.add_handler(CommandHandler("start", handlers.start))
    application.add_handler(MessageHandler(filters.Text("Оставить тикет"), handlers.create_ticket))
    application.add_handler(MessageHandler(filters.Text("Закрыть тикет"), handlers.close_user_ticket))
    application.add_handler(MessageHandler(filters.Regex(r"^Активные тикеты"), handlers.show_tickets))  # Обработка кнопки "Активные тикеты"
    application.add_handler(MessageHandler(filters.Regex(r"^Тикет \d+ от @\w+"), handlers.handle_ticket_selection))  # Обработка кнопок с ID тикетов
    application.add_handler(MessageHandler(filters.Text("Назад"), handlers.handle_back))  # Обработка кнопки "Назад"
    application.add_handler(MessageHandler(filters.Regex(r"^Ответить на тикет \(\d+\)$"), handlers.reply_to_ticket))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handlers.handle_text_message))

    application.run_polling()

if __name__ == '__main__':
    main()