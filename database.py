import sqlite3
import os
from typing import Optional
from datetime import datetime
from config import BASE_DIR


DB_PATH = os.path.join(BASE_DIR, "bot_database.db")


def get_connection():
    """SQLite ma'lumotlar bazasi ulanishi."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Jadvallarni yaratish va dastlabki sozlash."""
    with get_connection() as conn:
        cursor = conn.cursor()
        # Foydalanuvchilar jadvali
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                full_name TEXT,
                joined_at TEXT
            )
        """)
        # Sozlamalar (Masalan: Majburiy obuna kanali)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)
        conn.commit()


def add_user(user_id: int, username: str = None, full_name: str = None):
    """Yangi foydalanuvchini bazaga qo'shish."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT OR IGNORE INTO users (user_id, username, full_name, joined_at) VALUES (?, ?, ?, ?)",
            (user_id, username, full_name, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        )
        conn.commit()


def get_users_count() -> int:
    """Foydalanuvchilar umumiy sonini olish."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM users")
        return cursor.fetchone()[0]


def get_all_user_ids() -> list[int]:
    """Ommaviy xabar yuborish uchun barcha foydalanuvchilar ID larini olish."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT user_id FROM users")
        return [row[0] for row in cursor.fetchall()]


def set_setting(key: str, value: str):
    """Sozlamani saqlash."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
            (key, value)
        )
        conn.commit()


def get_setting(key: str, default: str = None) -> Optional[str]:
    """Sozlamani o'qish."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))
        row = cursor.fetchone()
        return row[0] if row else default


# Bazani avtomatik ishga tushirish
init_db()
