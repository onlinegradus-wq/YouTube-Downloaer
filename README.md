# 🤖 Telegram YouTube Downloader Bot

Ushbu bot Telegram orqali YouTube (va YouTube Shorts) videolarini hamda MP3 audiolarni sifatli va asinxron tarzda yuklab olish imkonini beradi.

---

## 🛠 O'rnatish va Ishga TushirishYo'riqnomasi

### 1-bosqich: Telegram Bot Tokenini Olish
1. Telegram'da **[@BotFather](https://t.me/BotFather)** botini oching.
2. `/newbot` buyrug'ini yuboring va ko'rsatmalarga amal qilib yangi bot yarating.
3. Bot yaratilgach, sizga berilgan **HTTP API Token** (masalan: `7123456789:ABCdefGHI...`) kodini nusxalab oling.

---

### 2-bosqich: Tokenni Saqlash
Loyiha papkasidagi `.env` faylini oching va bot tokeningizni joylashtiring:

```env
BOT_TOKEN=sizning_bot_tokeningiz_shu_yerga
```

---

### 3-bosqich: Kutubxonalarni O'rnatish
Terminal yoki Buyruqlar satrida (*Command Prompt / PowerShell*) loyiha papkasiga o'tib, quyidagi buyruqni bajaring:

```bash
pip install -r requirements.txt
```

---

### 4-bosqich: Botni Ishga Tushirish
Botni ishga tushirish uchun:

```bash
python main.py
```

---

## 💡 Botdan Foydalanish

1. Telegram'da yaratgan botingizga kiring va `/start` tugmasini bosing.
2. Istalgan **YouTube video linkini** yuboring.
3. Bot sizga videoning rasmi, sarlavhasi va davomiyligi bilan birga **🎬 Video (MP4)** hamda **🎵 Audio (MP3)** tugmalarini ko'rsatadi.
4. Kerakli tugmani bosing — bot videoni yuklab beradi.

---

## ⚠️ Muhim Eslatmalar

- **Fayl Hajmi Cheklovi:** Telegram Bot API orqali yuborilishi mumkin bo'lgan maksimal fayl hajmi **50 MB** ni tashkil etadi. 50 MB dan katta videolar uchun bot mos keluvchi xabarnoma chiqaradi.
- **Vaqtinchalik fayllar:** Yuklangan videolar foydalanuvchiga yuborilgach, disk joyini tejash uchun avtomatik ravishda o'chiriladi.
