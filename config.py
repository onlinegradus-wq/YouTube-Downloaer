import os
from dotenv import load_dotenv

# .env faylini yuklash
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
ADMIN_ID = int(os.getenv("ADMIN_ID", "0")) if os.getenv("ADMIN_ID", "").isdigit() else 0

# Yuklangan fayllar saqlanadigan papka
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DOWNLOAD_DIR = os.path.join(BASE_DIR, "downloads")

# Yuklamalar papkasini hosil qilish
os.makedirs(DOWNLOAD_DIR, exist_ok=True)
