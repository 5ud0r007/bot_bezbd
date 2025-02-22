import sqlite3
from config import DB_NAME, ADMIN_USER_ID

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
        # Добавляем столбец updated, если он отсутствует
        cursor.execute('''
            ALTER TABLE tickets ADD COLUMN updated BOOLEAN DEFAULT FALSE
        ''')

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
    print("База данных успешно инициализирована.")

def add_ticket(user_id: int, username: str, message: str):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO tickets (user_id, username, message) VALUES (?, ?, ?)
    ''', (user_id, username, message))
    ticket_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return ticket_id

def add_ticket_message(ticket_id: int, sender_id: int, message: str):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO ticket_messages (ticket_id, sender_id, message) VALUES (?, ?, ?)
    ''', (ticket_id, sender_id, message))

    if sender_id != ADMIN_USER_ID:
        cursor.execute('''
            UPDATE tickets SET updated = TRUE WHERE id = ?
        ''', (ticket_id,))
    conn.commit()
    conn.close()

def get_active_tickets():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT id, user_id, username, message, updated FROM tickets WHERE status = 'open'
    ''')
    tickets = cursor.fetchall()
    conn.close()
    return tickets

def get_updated_tickets_count():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT COUNT(*) FROM tickets WHERE status = 'open' AND updated = TRUE
    ''')
    count = cursor.fetchone()[0]
    conn.close()
    return count

def get_ticket_messages(ticket_id: int):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT sender_id, message, timestamp FROM ticket_messages WHERE ticket_id = ? ORDER BY timestamp
    ''', (ticket_id,))
    messages = cursor.fetchall()
    conn.close()
    return messages

def close_ticket(ticket_id: int):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE tickets SET status = 'closed' WHERE id = ?
    ''', (ticket_id,))
    conn.commit()
    conn.close()

# Проверка, есть ли ответ администратора в тикете
def has_admin_replied(ticket_id: int) -> bool:
    """
    Проверяет, есть ли ответ администратора в переписке по тикету.
    """
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT sender_id FROM ticket_messages WHERE ticket_id = ? AND sender_id = ?
    ''', (ticket_id, ADMIN_USER_ID))
    admin_replied = cursor.fetchone() is not None
    conn.close()
    return admin_replied

def get_active_tickets_with_updates():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT id, user_id, username, message, updated FROM tickets WHERE status = 'open'
    ''')
    tickets = cursor.fetchall()
    conn.close()

    updated_tickets = []
    for ticket in tickets:
        ticket_id = ticket[0]
        has_reply = has_admin_replied(ticket_id)
        updated_tickets.append(ticket + (not has_reply,))  # Добавляем флаг "Обновлено"

    return updated_tickets