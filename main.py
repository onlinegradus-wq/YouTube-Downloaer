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
    InlineQuery, InlineQueryResultArticle, InputTextMessageContent
)
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from config import BOT_TOKEN, ADMIN_ID
from database import (
    add_user, get_users_count, get_all_user_ids,
    set_setting, get_setting
)
from downloader import (
    get_video_info, download_media, cleanup_file,
    search_youtube, download_subtitles, trim_video
)

# Logging sozlamalari
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# YouTube havola regex filteri
YOUTUBE_REGEX = r'(https?://)?(www\.)?(youtube\.com|youtu\.be)/(watch\?v=|shorts/|playlist\?list=)?[\w-]+'

bot = Bot(token=BOT_TOKEN if BOT_TOKEN else "DUMMY_TOKEN")
dp = Dispatcher()

url_cache = {}


class TrimState(StatesGroup):
    waiting_for_range = State()


class BroadcastState(StatesGroup):
    waiting_for_message = State()


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


async def check_channel_sub(user_id: int) -> bool:
    """Majburiy obuna kanalini tekshirish."""
    channel = get_setting("channel")
    if not channel:
        return True
    try:
        member = await bot.get_chat_member(chat_id=channel, user_id=user_id)
        return member.status not in ["left", "kicked"]
    except Exception as e:
        logger.error(f"Channel sub check error: {e}")
        return True


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
    """/start buyrug'i uchun handler va foydalanuvchini bazaga yozish."""
    add_user(message.from_user.id, message.from_user.username, message.from_user.full_name)

    if not await check_channel_sub(message.from_user.id):
        channel = get_setting("channel")
        builder = InlineKeyboardBuilder()
        builder.row(InlineKeyboardButton(text="📢 Kanalga Obuna Bo'ling", url=f"https://t.me/{channel.replace('@', '')}"))
        builder.row(InlineKeyboardButton(text="✅ Tekshirish", callback_data="check_sub"))
        await message.answer(
            "⚠️ **Botdan foydalanish uchun rasmiy kanalimizga obuna bo'ling!**",
            reply_markup=builder.as_markup(),
            parse_mode="Markdown"
        )
        return

    text = (
        "👋 **Assalomu alaykum! YouTube Downloader botiga xush kelibsiz!**\n\n"
        "🎬 Menga istalgan **YouTube video** yoki **Shorts** havolasini yuboring.\n"
        "Sizga video sifatini (1080p, 720p, 480p, 360p) yoki MP3 audioni tanlash imkonini beraman.\n\n"
        "💡 *Masalan:* `https://www.youtube.com/watch?v=dQw4w9WgXcQ`"
    )
    await message.answer(text, reply_markup=get_main_menu(), parse_mode="Markdown")


@dp.callback_query(F.data == "check_sub")
async def cb_check_sub(callback: CallbackQuery):
    """Obunani tekshirish tugmasi."""
    if await check_channel_sub(callback.from_user.id):
        await callback.answer("✅ Obuna tasdiqlandi!")
        await callback.message.delete()
        await callback.message.answer("🎉 Rahmat! Endi YouTube havolasini yuborishingiz mumkin.", reply_markup=get_main_menu())
    else:
        await callback.answer("❌ Siz hali kanalga obuna bo'lmadingiz!", show_alert=True)


@dp.message(Command("admin"))
async def cmd_admin(message: Message):
    """Admin panel menyusi."""
    if ADMIN_ID and message.from_user.id != ADMIN_ID:
        return

    count = get_users_count()
    channel = get_setting("channel", "O'rnatilmagan")

    text = (
        "⚙️ **ADMIN PANEL**\n\n"
        f"👥 **Jami foydalanuvchilar:** {count} ta\n"
        f"📢 **Majburiy obuna kanali:** {channel}\n\n"
        "👇 Kerakli amalnini tanlang:"
    )

    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="📢 Ommaviy Xabar Yuborish", callback_data="admin:broadcast"))
    builder.row(InlineKeyboardButton(text="➕ Kanal Sozlash", callback_data="admin:set_channel"))

    await message.answer(text, reply_markup=builder.as_markup(), parse_mode="Markdown")


@dp.callback_query(F.data == "admin:broadcast")
async def cb_admin_broadcast(callback: CallbackQuery, state: FSMContext):
    """Broadcast rejimiga o'tish."""
    if ADMIN_ID and callback.from_user.id != ADMIN_ID:
        return
    await state.set_state(BroadcastState.waiting_for_message)
    await callback.message.answer("✍️ **Barcha foydalanuvchilarga yubormoqchi bo'lgan xabaringizni yuboring:**")
    await callback.answer()


@dp.message(BroadcastState.waiting_for_message)
async def process_broadcast_message(message: Message, state: FSMContext):
    """Barcha foydalanuvchilarga xabarni tarqatish."""
    await state.clear()
    user_ids = get_all_user_ids()
    status_msg = await message.answer(f"⏳ {len(user_ids)} ta foydalanuvchiga xabar yuborilmoqda...")

    success = 0
    failed = 0
    for uid in user_ids:
        try:
            await message.copy_to(chat_id=uid)
            success += 1
            await asyncio.sleep(0.05)
        except Exception:
            failed += 1

    await status_msg.edit_text(
        f"✅ **Ommaviy xabar yuborildi!**\n\n"
        f"🟢 Muvaffaqiyatli: {success} ta\n"
        f"🔴 Muvaffaqiyatsiz: {failed} ta"
    )


@dp.callback_query(F.data == "admin:set_channel")
async def cb_admin_set_channel(callback: CallbackQuery):
    """Kanal sozlash bo'yicha yo'riqnoma."""
    await callback.message.answer(
        "📢 Kanalni majburiy obunaga sozlash uchun:\n"
        "`/setchannel @kanalingiz_username` buyrug'ini yuboring.\n\n"
        "O'chirish uchun: `/delchannel`",
        parse_mode="Markdown"
    )
    await callback.answer()


@dp.message(Command("setchannel"))
async def cmd_set_channel(message: Message):
    """Majburiy obuna kanalini o'rnatish."""
    if ADMIN_ID and message.from_user.id != ADMIN_ID:
        return
    args = message.text.split()
    if len(args) < 2:
        await message.answer("⚠️ Qullanilishi: `/setchannel @kanalingiz`", parse_mode="Markdown")
        return
    ch = args[1].strip()
    set_setting("channel", ch)
    await message.answer(f"✅ Majburiy obuna kanali **{ch}** ga o'rnatildi!")


@dp.message(Command("delchannel"))
async def cmd_del_channel(message: Message):
    """Majburiy obuna kanalini o'chirish."""
    if ADMIN_ID and message.from_user.id != ADMIN_ID:
        return
    set_setting("channel", "")
    await message.answer("✅ Majburiy obuna kanali o'chirib tashlandi!")


@dp.inline_query()
async def inline_youtube_search(inline_query: InlineQuery):
    """Telegram inline qidiruv (@botusername qidiruv_sozi)."""
    query = inline_query.query.strip()
    if not query:
        return

    results = await search_youtube(query, limit=5)
    articles = []

    for idx, item in enumerate(results):
        title = item.get('title', 'Video')
        video_id = item.get('id')
        url = item.get('url') or f"https://www.youtube.com/watch?v={video_id}"

        articles.append(
            InlineQueryResultArticle(
                id=str(idx),
                title=title,
                input_message_content=InputTextMessageContent(
                    message_text=url
                ),
                description=f"🎬 YouTube Video | ID: {video_id}",
                thumb_url=f"https://img.youtube.com/vi/{video_id}/hqdefault.jpg" if video_id else None
            )
        )

    await inline_query.answer(articles, cache_time=300)


@dp.message(F.text == "📥 Yo'riqnoma")
@dp.message(Command("help"))
async def cmd_help(message: Message):
    text = (
        "📖 **Yo'riqnoma:**\n\n"
        "1️⃣ YouTube ilovasi yoki saytidan video havolasini nusxalang (*Copy Link*).\n"
        "2️⃣ Havolani shu botga yuboring.\n"
        "3️⃣ Kerakli sifatni tanlang (1080p, 720p, 480p, 360p yoki Audio MP3).\n\n"
        "💡 **Telegram Inline Qidiruv:**\n"
        "Istalgan chatda `@botusername vaqt` deb yozsangiz, YouTube videolarini bot ichida qidirishingiz mumkin!"
    )
    await message.answer(text, reply_markup=get_main_menu(), parse_mode="Markdown")


@dp.message(F.text == "ℹ️ Bot Haqida")
async def cmd_about(message: Message):
    text = (
        "ℹ️ **Bot Haqida Ma'lumot:**\n\n"
        "🚀 Ushbu bot YouTube videolarini hamda MP3 audiolarni sifatli va tezkor yuklab beradi.\n\n"
        "✨ **Imkoniyatlar:**\n"
        "• 🎬 Video sifatlari: 1080p (Full HD), 720p (HD), 480p, 360p\n"
        "• 🎵 Audio MP3 formatida yuklash\n"
        "• ✂️ Videolarni istalgan qismini qirqib yuklash\n"
        "• 📝 Subtitrlarni (.srt/.txt) yuklab olish\n"
        "• ⚡️ H.264 (avc1) kodek - Telegram pleyerida tiniq ijro"
    )
    await message.answer(text, reply_markup=get_main_menu(), parse_mode="Markdown")


@dp.message(F.text == "⚙️ Sozlamalar")
async def cmd_settings(message: Message):
    text = (
        "⚙️ **Sozlamalar va Maslahatlar:**\n\n"
        "• **Maksimal hajm:** Telegram boti orqali 50 MB gacha bo'lgan fayllarni yuklash mumkin.\n"
        "• **Tezkor yuklash:** Agar internetingiz sekin bo'lsa, 480p yoki 360p sifatni tanlashingiz tavsiya etiladi."
    )
    await message.answer(text, reply_markup=get_main_menu(), parse_mode="Markdown")


@dp.message(F.text == "📞 Qo'llab-quvvatlash")
async def cmd_support(message: Message):
    text = "📞 **Qo'llab-quvvatlash va Aloqa:**\n\nAdministrator bilan bog'lanish uchun o'zingizning kontakt ma'lumotlaringizni yozishingiz mumkin."
    await message.answer(text, reply_markup=get_main_menu(), parse_mode="Markdown")


@dp.message(F.text.regexp(YOUTUBE_REGEX))
async def handle_youtube_link(message: Message):
    """YouTube havolasini qabul qilish va menyuni chiqarish."""
    add_user(message.from_user.id, message.from_user.username, message.from_user.full_name)

    if not await check_channel_sub(message.from_user.id):
        channel = get_setting("channel")
        builder = InlineKeyboardBuilder()
        builder.row(InlineKeyboardButton(text="📢 Kanalga Obuna Bo'ling", url=f"https://t.me/{channel.replace('@', '')}"))
        builder.row(InlineKeyboardButton(text="✅ Tekshirish", callback_data="check_sub"))
        await message.answer("⚠️ **Botdan foydalanish uchun rasmiy kanalimizga obuna bo'ling!**", reply_markup=builder.as_markup(), parse_mode="Markdown")
        return

    url = message.text.strip()
    status_msg = await message.answer("🔍 Video ma'lumotlari olinmoqda, biroz kuting...")

    try:
        info = await asyncio.wait_for(get_video_info(url), timeout=30.0)
    except asyncio.TimeoutError:
        await status_msg.edit_text("⏱ **Vaqt cheklovi bo'yicha xatolik:** YouTube serveridan javob olish cho'zilib ketdi. Qayta yuboring.")
        return
    except Exception as e:
        logger.error(f"Error getting video info: {e}")
        await status_msg.edit_text(f"❌ **Xatolik:** {e}")
        return

    if not info:
        await status_msg.edit_text("❌ **Xatolik:** Ushbu video YouTube'da mavjud emas yoki havola noto'g'ri.")
        return

    video_id = info.get('id')
    title = info.get('title', 'YouTube Video')
    duration = info.get('duration', 0)
    thumbnail = info.get('thumbnail')
    channel = info.get('uploader') or info.get('channel', 'YouTube')
    view_count = info.get('view_count', 0)
    like_count = info.get('like_count', 0)

    if not thumbnail and video_id:
        thumbnail = f"https://img.youtube.com/vi/{video_id}/hqdefault.jpg"

    url_cache[video_id] = url

    minutes, seconds = divmod(duration, 60)
    duration_str = f"{minutes} min {seconds} sec" if duration else "Noma'lum"
    views_str = f"{view_count:,}" if view_count else "Noma'lum"
    likes_str = f"{like_count:,}" if like_count else "Noma'lum"

    caption = (
        f"🎬 **{title}**\n\n"
        f"👤 **Kanal:** {channel}\n"
        f"⏱ **Davomiyligi:** {duration_str}\n"
        f"👁 **Ko'rishlar:** {views_str} | ❤️ **Layklar:** {likes_str}\n\n"
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
        InlineKeyboardButton(text="🎵 Audio (MP3)", callback_data=f"dl:audio:mp3:{video_id}"),
        InlineKeyboardButton(text="📝 Subtitr", callback_data=f"sub:{video_id}")
    )
    builder.row(
        InlineKeyboardButton(text="✂️ Videoni Qirqish", callback_data=f"trim_init:{video_id}")
    )

    await status_msg.delete()

    if thumbnail:
        try:
            await message.answer_photo(photo=thumbnail, caption=caption, reply_markup=builder.as_markup(), parse_mode="Markdown")
            return
        except Exception:
            pass

    await message.answer(caption, reply_markup=builder.as_markup(), parse_mode="Markdown")


@dp.callback_query(F.data.startswith("sub:"))
async def handle_subtitles_callback(callback: CallbackQuery):
    """Subtitrlarni yuklash handler."""
    video_id = callback.data.split(":")[1]
    url = url_cache.get(video_id, f"https://www.youtube.com/watch?v={video_id}")

    await callback.answer("📝 Subtitr yuklanmoqda...")
    status_msg = await callback.message.answer("⏳ **Subtitrlar qidirilmoqda...**", parse_mode="Markdown")

    file_path, title = await download_subtitles(url)

    if not file_path:
        await status_msg.edit_text(f"❌ **Subtitr topilmadi:** {title}")
        return

    try:
        input_file = FSInputFile(file_path)
        await callback.message.answer_document(document=input_file, caption=f"📝 **{title}** subtitri")
        await status_msg.delete()
    except Exception as e:
        await status_msg.edit_text(f"❌ **Xatolik:** {e}")
    finally:
        cleanup_file(file_path)


@dp.callback_query(F.data.startswith("trim_init:"))
async def handle_trim_init_callback(callback: CallbackQuery, state: FSMContext):
    """Video qirqish rejimini boshlash."""
    video_id = callback.data.split(":")[1]
    url = url_cache.get(video_id, f"https://www.youtube.com/watch?v={video_id}")

    await state.set_state(TrimState.waiting_for_range)
    await state.update_data(trim_url=url, trim_video_id=video_id)

    await callback.message.answer(
        "✂️ **Videoni Qirqish:**\n\n"
        "Qirqmoqchi bo'lgan vaqt oralig'ingizni soniyalarda yoki daqiqalarda yozing.\n"
        "💡 *Masalan:* `01:00-02:30` yoki `10-90`",
        parse_mode="Markdown"
    )
    await callback.answer()


@dp.message(TrimState.waiting_for_range)
async def process_trim_range(message: Message, state: FSMContext):
    """Qirqish vaqt oralig'ini qabul qilish va yuklash."""
    data = await state.get_data()
    url = data.get("trim_url")
    await state.clear()

    pattern = r'(\d+:\d+|\d+)-(\d+:\d+|\d+)'
    match = re.search(pattern, message.text.strip())

    if not match:
        await message.answer("❌ Noto'g'ri format. Masalan: `01:00-02:30` yoki `10-90` formatida yozing.")
        return

    start_str, end_str = match.groups()

    def parse_sec(s: str) -> int:
        if ':' in s:
            m, sec = s.split(':')
            return int(m) * 60 + int(sec)
        return int(s)

    start_sec = parse_sec(start_str)
    end_sec = parse_sec(end_str)

    if start_sec >= end_sec:
        await message.answer("❌ Boshlanish vaqti tugash vaqtidan kichik bo'lishi kerak.")
        return

    status_msg = await message.answer(f"⏳ **Video qirqilmoqda ({start_str} -> {end_str})...**\n*Biroz kuting...*")

    file_path, title, status = await trim_video(url, start_sec, end_sec, quality="720")

    if status != "SUCCESS" or not file_path:
        await status_msg.edit_text(f"❌ **Qirqishda xatolik:** {status}")
        return

    try:
        await status_msg.edit_text("📤 **Telegram'ga yuklanmoqda...**")
        input_file = FSInputFile(file_path)
        await message.answer_video(video=input_file, caption=f"✂️ **{title}**\n⏱ {start_str} - {end_str}")
        await status_msg.delete()
    except Exception as e:
        await status_msg.edit_text(f"❌ **Yuborishda xatolik:** {e}")
    finally:
        cleanup_file(file_path)


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
        await status_msg.edit_text("⏱ **Vaqt cheklovi:** Faylni yuklash vaqti 3 daqiqadan oshdi.", parse_mode="Markdown")
        return
    except Exception as e:
        logger.error(f"Download exception: {e}")
        await status_msg.edit_text(f"❌ **Xatolik yuz berdi:** {e}")
        return

    if status == "TOO_LARGE":
        await status_msg.edit_text("⚠️ **Fayl hajmi 50 MB dan katta.** Pastroq sifatni tanlang.", parse_mode="Markdown")
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
