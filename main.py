import asyncio
import os
import sys
import re
import logging

# Windows konsol kodirovkasini sozlash
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart, Command
from aiogram.types import (
    Message, CallbackQuery, InlineKeyboardButton, FSInputFile
)
from aiogram.utils.keyboard import InlineKeyboardBuilder

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


@dp.message(CommandStart())
async def cmd_start(message: Message):
    """/start buyrug'i uchun handler."""
    text = (
        "👋 **Assalomu alaykum! YouTube Downloader botiga xush kelibsiz!**\n\n"
        "🎬 Menga istalgan **YouTube video** yoki **Shorts** havolasini yuboring.\n"
        "Sizga video sifatini (1080p, 720p, 480p, 360p) yoki MP3 audioni tanlash imkonini beraman.\n\n"
        "💡 *Masalan:* `https://www.youtube.com/watch?v=dQw4w9WgXcQ`"
    )
    await message.answer(text, parse_mode="Markdown")


@dp.message(Command("help"))
async def cmd_help(message: Message):
    """/help buyrug'i uchun handler."""
    text = (
        "📖 **Yordam va Yo'riqnoma:**\n\n"
        "1️⃣ YouTube ilovasi yoki saytidan video havolasini nusxalang (*Copy Link*).\n"
        "2️⃣ Havolani shu botga yuboring.\n"
        "3️⃣ Kerakli sifatni tanlang (1080p, 720p, 480p, 360p yoki Audio MP3).\n\n"
        "⚠️ *Eslatma:* Telegram Bot API cheklovi sababli 50 MB dan katta fayllarni yuborib bo'lmaydi."
    )
    await message.answer(text, parse_mode="Markdown")


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
        await status_msg.edit_text(f"❌ **Xatolik:** Video ma'lumotlarini olishda xatolik: {e}")
        return

    if not info:
        await status_msg.edit_text("❌ **Xatolik:** Video ma'lumotlarini olib bo'lmadi. Havolani tekshirib qayta yuboring.")
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
        # Yuklash va qayta ishlash uchun 180 soniya (3 daqiqa) kutish vaqti
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
        print("⚠️  DIQQAT: BOT_TOKEN o'rnatilmagan!")
        print("Iltimos, '.env' fayliga Telegram bot tokeningizni kiriting.")
        print("="*60 + "\n")
        return

    print("🚀 Telegram bot ishga tushmoqda...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
