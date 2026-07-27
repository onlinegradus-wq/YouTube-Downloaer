import asyncio
import os
import glob
from typing import Dict, Any, Optional, Tuple
import yt_dlp
from config import DOWNLOAD_DIR

# imageio_ffmpeg orqali avtomatik FFmpeg joylashuvini aniqlash
FFMPEG_PATH = None
try:
    import imageio_ffmpeg
    FFMPEG_PATH = imageio_ffmpeg.get_ffmpeg_exe()
except Exception as e:
    print(f"[WARN] imageio_ffmpeg topilmadi yoki yuklanmadi: {e}")

COMMON_YOUTUBE_OPTS = {
    'quiet': True,
    'no_warnings': True,
    'nocheckcertificate': True,
    'socket_timeout': 30,
    'extractor_args': {
        'youtube': {
            'player_client': ['mweb', 'android', 'web', 'ios', 'tv']
        }
    }
}


def _extract_info_sync(url: str) -> Optional[Dict[str, Any]]:
    """YouTube videosi haqida ma'lumotlarni 2 bosqichli zaxira bilan olish."""
    # 1-urinish: Standart ma'lumot yig'ish
    ydl_opts = {
        **COMMON_YOUTUBE_OPTS,
        'skip_download': True,
        'noplaylist': True,
        'socket_timeout': 15,
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            if info and ('title' in info or 'id' in info):
                return info
    except Exception as e:
        print(f"[WARN] Standard extract_info failed: {e}")

    # 2-urinish: Flat mode zaxirasi
    ydl_opts_flat = {
        **COMMON_YOUTUBE_OPTS,
        'skip_download': True,
        'extract_flat': 'in_playlist',
        'noplaylist': True,
        'socket_timeout': 15,
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts_flat) as ydl:
            return ydl.extract_info(url, download=False)
    except Exception as e:
        print(f"[ERROR] Flat extract_info failed: {e}")
        return None


async def get_video_info(url: str) -> Optional[Dict[str, Any]]:
    """YouTube videosi haqida ma'lumotlarni asinxron olish."""
    return await asyncio.to_thread(_extract_info_sync, url)


def _download_media_sync(url: str, mode: str = "video", quality: str = "720") -> Tuple[Optional[str], str, str]:
    """
    Videoni yoki audioni sinxron yuklab olish.
    quality: "1080", "720", "480", "360" yoki "mp3"
    Qaytaradi: (file_path, title, status_code_or_msg)
    """
    outtmpl = os.path.join(DOWNLOAD_DIR, '%(id)s_%(ext)s.%(ext)s')

    common_opts = {
        **COMMON_YOUTUBE_OPTS,
        'outtmpl': outtmpl,
        'max_filesize': 50 * 1024 * 1024,  # Telegram bot API max 50MB
    }

    if mode == "audio":
        ydl_opts = {
            **common_opts,
            'format': 'bestaudio/best',
        }
        if FFMPEG_PATH:
            ydl_opts['ffmpeg_location'] = FFMPEG_PATH
            ydl_opts['postprocessors'] = [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }]
    else:
        h = quality if quality.isdigit() else "720"
        # Telegram pleyerida to'g'ri ijro etilishi uchun H.264 (avc1) kodekini tanlash
        fmt = (
            f'bestvideo[height<={h}][vcodec^=avc1][filesize<=50M]+bestaudio[acodec^=mp4a]/'
            f'best[height<={h}][vcodec^=avc1][filesize<=50M]/'
            f'bestvideo[height<={h}][vcodec^=h264][filesize<=50M]+bestaudio/'
            f'best[height<={h}][ext=mp4][filesize<=50M]/'
            f'best[height<={h}]/b'
        )

        ydl_opts = {
            **common_opts,
            'format': fmt,
        }
        if FFMPEG_PATH:
            ydl_opts['ffmpeg_location'] = FFMPEG_PATH
            ydl_opts['merge_output_format'] = 'mp4'

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            if not info:
                return None, "", "Video ma'lumotlarini yuklab bo'lmadi."

            title = info.get('title', 'YouTube Media')
            video_id = info.get('id')

            pattern = os.path.join(DOWNLOAD_DIR, f"{video_id}_*")
            matching_files = glob.glob(pattern)

            if matching_files:
                target_file = matching_files[0]
                file_size = os.path.getsize(target_file)
                if file_size > 50 * 1024 * 1024:
                    os.remove(target_file)
                    return None, title, "TOO_LARGE"
                return target_file, title, "SUCCESS"

            return None, title, "Fayl topilmadi."

    except Exception as e:
        err_str = str(e)
        print(f"[ERROR] download_media: {err_str}")
        if "File is larger than max_filesize" in err_str or "max_filesize" in err_str:
            return None, "", "TOO_LARGE"
        return None, "", f"Xatolik: {err_str[:100]}"


async def download_media(url: str, mode: str = "video", quality: str = "720") -> Tuple[Optional[str], str, str]:
    """Videoni yoki audioni asinxron yuklab olish."""
    return await asyncio.to_thread(_download_media_sync, url, mode, quality)


def cleanup_file(filepath: Optional[str]):
    """Vaqtinchalik faylni o'chirish."""
    if filepath and os.path.exists(filepath):
        try:
            os.remove(filepath)
        except Exception as e:
            print(f"[ERROR] cleanup_file: {e}")
