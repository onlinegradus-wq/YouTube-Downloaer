import os
from dotenv import load_dotenv

# .env faylini yuklash
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
ADMIN_ID = int(os.getenv("ADMIN_ID", "0")) if os.getenv("ADMIN_ID", "").isdigit() else 0

# Yuklangan fayllar saqlanadigan papka
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DOWNLOAD_DIR = os.path.join(BASE_DIR, "downloads")
COOKIES_PATH = os.path.join(BASE_DIR, "cookies.txt")

# Agar .env da COOKIES_TEXT bo'lsa, cookies.txt fayliga saqlash
COOKIES_TEXT = os.getenv("COOKIES_TEXT", "").strip()
if COOKIES_TEXT:
    with open(COOKIES_PATH, "w", encoding="utf-8") as f:
        f.write(COOKIES_TEXT)

os.makedirs(DOWNLOAD_DIR, exist_ok=True)
