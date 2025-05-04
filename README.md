<div align="center">
  <img src="https://github.com/5ud0r007/bot_bezbd/blob/main/readme_photo/photo%201.gif" alt="Bot Demo" width="100%">
  <h1>Telegram Support Bot</h1>
  <p>A powerful Telegram bot for managing support tickets with AI integration</p>
</div>

---

## 📖 Overview

This Telegram bot streamlines customer support by allowing users to create tickets and administrators to manage them efficiently. Integrated with OpenAI's GPT-3.5 Turbo, the bot provides automated responses to common queries, escalates complex issues to admins, and ensures smooth communication.

---

## ✨ Features

- **Ticket Creation**: Users can submit tickets to report issues or ask questions.
- **Admin Management**: Admins can view, respond to, and close tickets directly in Telegram.
- **AI-Powered Responses**: Leverages OpenAI GPT-3.5 Turbo to:
  - Answer FAQs (e.g., studio hours, address).
  - Request clarification for vague queries.
  - Handle aggressive messages with polite redirection.
- **Real-Time Notifications**: Admins receive instant updates on new tickets and user replies.
- **PostgreSQL Integration**: Robust database for storing ticket and message data.

---

## 🛠️ Installation

### Prerequisites
- Python 3.8+
- PostgreSQL database
- OpenAI API key
- Telegram Bot Token (via [BotFather](https://t.me/BotFather))

### Steps
1. **Clone the Repository**:
   ```bash
   git clone https://github.com/5ud0r007/bot_bezbd.git
   cd bot_bezbd
   ```

2. **Configure Settings**:
   - Open `config.py` and add:
     - `BOT_TOKEN`: Your Telegram bot token.
     - `ADMIN_USER_ID`: Telegram ID of the admin.
     - `OPENAI_API_KEY`: Your OpenAI API key.
     - `DB_CONNECTION`: PostgreSQL connection string (e.g., `postgresql://user:password@localhost:5432/tickets`).
     - `OPENAI_PROMPT`: Customize the AI prompt if needed.

3. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

4. **Run the Bot**:
   ```bash
   python main.py
   ```

---

## 📂 Project Structure

```
bot_bezbd/
├── main.py               # Core bot logic
├── config.py             # Configuration settings
├── requirements.txt      # Project dependencies
└── readme_photo/         # Assets for README
```

---

## 🤝 Contact

Have questions or suggestions? Reach out!

- **Telegram**: [LOADERAW](https://t.me/SoulArcanum)
- **Email**: Not available

---

## 🚀 Ready to Go!

Launch your support bot and enhance your customer service with AI-driven automation!
