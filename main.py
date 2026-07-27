import asyncio
import os
import sys
import re
import logging
from aiohttp import web

# Windows konsol kodirovkasini sozlash
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart, Command
from aiogram.types import (
    Message, CallbackQuery, InlineKeyboardButton, FSInputFile,
    ReplyKeyboardMarkup, KeyboardButton
)
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder

from config import BOT_TOKEN
from downloader import get_video_info, download_media, cleanup_file

# Logging sozlamalari
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# YouTube havola regex filteri
YOUTUBE_REGEX = r'(https?://)?(www\.)?(youtube\.com|youtu\.be)/(watch\?v=|shorts/)?[\w-]+'

bot = Bot(token=BOT_TOKEN if BOT_TOKEN else "DUMMY_TOKEN")
dp = Dispatcher()

# YouTube URL larini saqlash uchun vaqtinchalik xotira (video_id -> url)
url_cache = {}


def get_main_menu():
    """Asosiy doimiy pastki menyu tugmalari."""
    builder = ReplyKeyboardBuilder()
    builder.row(
        KeyboardButton(text="📥 Yo'riqnoma"),
        KeyboardButton(text="ℹ️ Bot Haqida")
    )
    builder.row(
        KeyboardButton(text="⚙️ Sozlamalar"),
        KeyboardButton(text="📞 Qo'llab-quvvatlash")
    )
    return builder.as_markup(resize_keyboard=True)


async def handle_ping(request):
    """Render uchun HTTP health check handler."""
    return web.Response(text="Bot is running! 🚀")


async def start_health_check_server():
    """Render Web Service portini ochish."""
    port = int(os.getenv("PORT", 8080))
    app = web.Application()
    app.router.add_get("/", handle_ping)
    app.router.add_get("/health", handle_ping)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    print(f"🌐 Health check web server started on port {port}")


@dp.message(CommandStart())
async def cmd_start(message: Message):
    """/start buyrug'i uchun handler."""
    text = (
        "👋 **Assalomu alaykum! YouTube Downloader botiga xush kelibsiz!**\n\n"
        "🎬 Menga istalgan **YouTube video** yoki **Shorts** havolasini yuboring.\n"
        "Sizga video sifatini (1080p, 720p, 480p, 360p) yoki MP3 audioni tanlash imkonini beraman.\n\n"
        "💡 *Masalan:* `https://www.youtube.com/watch?v=dQw4w9WgXcQ`"
    )
    await message.answer(text, reply_markup=get_main_menu(), parse_mode="Markdown")


@dp.message(F.text == "📥 Yo'riqnoma")
@dp.message(Command("help"))
async def cmd_help(message: Message):
    """Yo'riqnoma handler."""
    text = (
        "📖 **Yo'riqnoma:**\n\n"
        "1️⃣ YouTube ilovasi yoki saytidan video havolasini nusxalang (*Copy Link*).\n"
        "2️⃣ Havolani shu botga yuboring.\n"
        "3️⃣ Kerakli sifatni tanlang (1080p, 720p, 480p, 360p yoki Audio MP3).\n\n"
        "⚠️ *Eslatma:* Telegram Bot API cheklovi sababli 50 MB dan kichik fayllar yuboriladi."
    )
    await message.answer(text, reply_markup=get_main_menu(), parse_mode="Markdown")


@dp.message(F.text == "ℹ️ Bot Haqida")
async def cmd_about(message: Message):
    """Bot haqida handler."""
    text = (
        "ℹ️ **Bot Haqida Ma'lumot:**\n\n"
        "🚀 Ushbu bot YouTube videolarini hamda MP3 audiolarni sifatli va tezkor yuklab beradi.\n\n"
        "✨ **Imkoniyatlar:**\n"
        "• 🎬 Video sifatlari: 1080p (Full HD), 720p (HD), 480p, 360p\n"
        "• 🎵 Audio MP3 formatida yuklash\n"
        "• 📱 YouTube Shorts videolarini qo'llab-quvvatlash\n"
        "• ⚡️ H.264 (avc1) kodek - to'g'ridan-to'g'ri Telegram pleyerida tiniq ijro etish"
    )
    await message.answer(text, reply_markup=get_main_menu(), parse_mode="Markdown")


@dp.message(F.text == "⚙️ Sozlamalar")
async def cmd_settings(message: Message):
    """Sozlamalar handler."""
    text = (
        "⚙️ **Sozlamalar va Maslahatlar:**\n\n"
        "• **Maksimal hajm:** Telegram boti orqali 50 MB gacha bo'lgan fayllarni yuklash mumkin.\n"
        "• **Tezkor yuklash:** Agar internetingiz sekin bo'lsa, 480p yoki 360p sifatni tanlashingiz tavsiya etiladi.\n"
        "• **Avtomatik format:** Barcha videolar Telegram pleyerida mos keluvchi MP4 formatida tayyorlanadi."
    )
    await message.answer(text, reply_markup=get_main_menu(), parse_mode="Markdown")


@dp.message(F.text == "📞 Qo'llab-quvvatlash")
async def cmd_support(message: Message):
    """Qo'llab-quvvatlash handler."""
    text = (
        "📞 **Qo'llab-quvvatlash va Aloqa:**\n\n"
        "Agar bot ishlashida qandaydir taklif yoki savollaringiz bo'lsa, administrator bilan bog'lanishingiz mumkin.\n\n"
        "🤖 *YouTube Downloader Bot v2.0*"
    )
    await message.answer(text, reply_markup=get_main_menu(), parse_mode="Markdown")


@dp.message(F.text.regexp(YOUTUBE_REGEX))
async def handle_youtube_link(message: Message):
    """YouTube havolasini qabul qilish va sifatlar menyusini tezkor chiqarish."""
    url = message.text.strip()
    status_msg = await message.answer("🔍 Video ma'lumotlari olinmoqda, biroz kuting...")

    try:
        info = await asyncio.wait_for(get_video_info(url), timeout=30.0)
    except asyncio.TimeoutError:
        await status_msg.edit_text("⏱ **Vaqt cheklovi bo'yicha xatolik:** YouTube serveridan javob olish cho'zilib ketdi. Iltimos, qayta yuboring.")
        return
    except Exception as e:
        logger.error(f"Error getting video info: {e}")
        await status_msg.edit_text(f"❌ **Xatolik:** Video ma'lumotlarini olishda xatolik yuz berdi: {e}")
        return

    if not info:
        await status_msg.edit_text(
            "❌ **Xatolik:** Ushbu video YouTube'da mavjud emas (o'chirilgan, yopiq/private video) yoki havola noto'g'ri.\n"
            "Boshqa faol YouTube havolasini sinab ko'ring."
        )
        return

    video_id = info.get('id')
    title = info.get('title', 'YouTube Video')
    duration = info.get('duration', 0)
    thumbnail = info.get('thumbnail')
    channel = info.get('uploader') or info.get('channel', 'YouTube')

    if not thumbnail and video_id:
        thumbnail = f"https://img.youtube.com/vi/{video_id}/hqdefault.jpg"

    url_cache[video_id] = url

    minutes, seconds = divmod(duration, 60)
    duration_str = f"{minutes} min {seconds} sec" if duration else "Noma'lum"

    caption = (
        f"🎬 **{title}**\n\n"
        f"👤 **Kanal:** {channel}\n"
        f"⏱ **Davomiyligi:** {duration_str}\n\n"
        "👇 Yuklab olish uchun **sifatni** tanlang:"
    )

    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="🎬 1080p", callback_data=f"dl:video:1080:{video_id}"),
        InlineKeyboardButton(text="🎬 720p", callback_data=f"dl:video:720:{video_id}")
    )
    builder.row(
        InlineKeyboardButton(text="🎬 480p", callback_data=f"dl:video:480:{video_id}"),
        InlineKeyboardButton(text="🎬 360p", callback_data=f"dl:video:360:{video_id}")
    )
    builder.row(
        InlineKeyboardButton(text="🎵 Audio (MP3)", callback_data=f"dl:audio:mp3:{video_id}")
    )

    await status_msg.delete()

    if thumbnail:
        try:
            await message.answer_photo(
                photo=thumbnail,
                caption=caption,
                reply_markup=builder.as_markup(),
                parse_mode="Markdown"
            )
            return
        except Exception:
            pass

    await message.answer(caption, reply_markup=builder.as_markup(), parse_mode="Markdown")


@dp.callback_query(F.data.startswith("dl:"))
async def handle_download_callback(callback: CallbackQuery):
    """Tugma bosilganda tanlangan sifatda video/audioni yuklab yuborish."""
    parts = callback.data.split(":")
    mode = parts[1]
    quality = parts[2]
    video_id = parts[3]

    url = url_cache.get(video_id, f"https://www.youtube.com/watch?v={video_id}")

    mode_label = f"Video ({quality}p)" if mode == "video" else "Audio MP3 🎵"
    await callback.answer(f"{mode_label} yuklash boshlandi...")

    status_msg = await callback.message.answer(
        f"⏳ **{mode_label} yuklanmoqda...**\n*Biroz kuting...*",
        parse_mode="Markdown"
    )

    try:
        file_path, title, status = await asyncio.wait_for(
            download_media(url, mode=mode, quality=quality),
            timeout=180.0
        )
    except asyncio.TimeoutError:
        await status_msg.edit_text(
            f"⏱ **Vaqt cheklovi:** Faylni yuklash vaqti 3 daqiqadan oshib ketdi.\n"
            "Pastroq sifatni (masalan, 480p yoki 360p) tanlab ko'ring.",
            parse_mode="Markdown"
        )
        return
    except Exception as e:
        logger.error(f"Download exception: {e}")
        await status_msg.edit_text(f"❌ **Xatolik yuz berdi:** {e}")
        return

    if status == "TOO_LARGE":
        await status_msg.edit_text(
            f"⚠️ **Kechirasiz!** Ushbu {quality}p sifatidagi fayl hajmi Telegram Bot API cheklovi (**50 MB**) dan katta.\n"
            "Pastroq sifatni (masalan, 480p yoki 360p) tanlab ko'ring.",
            parse_mode="Markdown"
        )
        return

    if status != "SUCCESS" or not file_path:
        await status_msg.edit_text(f"❌ **Xatolik:** Faylni yuklab bo'lmadi.\n{status}", parse_mode="Markdown")
        return

    try:
        await status_msg.edit_text("📤 **Telegram'ga yuklanmoqda...**", parse_mode="Markdown")
        input_file = FSInputFile(file_path)

        if mode == "video":
            await callback.message.answer_video(
                video=input_file,
                caption=f"🎬 **{title}**\n📐 **Sifat:** {quality}p\n\n🤖 @YouTubeDownloaderBot",
                parse_mode="Markdown"
            )
        else:
            await callback.message.answer_audio(
                audio=input_file,
                caption=f"🎵 **{title}**\n\n🤖 @YouTubeDownloaderBot",
                parse_mode="Markdown"
            )

        await status_msg.delete()

    except Exception as e:
        logger.error(f"Fayl yuborishda xatolik: {e}")
        await status_msg.edit_text(f"❌ **Faylni yuborishda xatolik yuz berdi:** {e}")
    finally:
        cleanup_file(file_path)


async def main():
    if not BOT_TOKEN or BOT_TOKEN == "YOUR_TELEGRAM_BOT_TOKEN_HERE":
        print("\n" + "="*60)
        print("⚠️ DIQQAT: BOT_TOKEN o'rnatilmagan!")
        print("Iltimos, '.env' fayliga Telegram bot tokeningizni kiriting.")
        print("="*60 + "\n")
        return

    await start_health_check_server()

    print("🚀 Telegram bot ishga tushmoqda...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
