import os
from dotenv import load_dotenv

# .env faylini yuklash
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()

# Yuklangan fayllar saqlanadigan papka
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DOWNLOAD_DIR = os.path.join(BASE_DIR, "downloads")

# Yuklamalar papkasini hosil qilish
os.makedirs(DOWNLOAD_DIR, exist_ok=True)
