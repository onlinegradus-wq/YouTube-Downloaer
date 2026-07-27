import asyncio
import os
import glob
from typing import Dict, Any, Optional, Tuple, List
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
            'player_client': ['mweb', 'android', 'web']
        }
    }
}


def _extract_info_sync(url: str) -> Optional[Dict[str, Any]]:
    """YouTube videosi haqida ma'lumotlarni ishonchli va tezkor olish."""
    opts_primary = {
        'quiet': True,
        'no_warnings': True,
        'skip_download': True,
        'noplaylist': True,
        'socket_timeout': 15,
        'nocheckcertificate': True,
    }
    try:
        with yt_dlp.YoutubeDL(opts_primary) as ydl:
            info = ydl.extract_info(url, download=False)
            if info and ('title' in info or 'id' in info):
                return info
    except Exception as e:
        print(f"[WARN] Primary extract_info failed: {e}")

    opts_fallback = {
        'quiet': True,
        'no_warnings': True,
        'socket_timeout': 15,
        'extractor_args': {
            'youtube': {
                'player_client': ['mweb', 'android', 'web']
            }
        }
    }
    try:
        with yt_dlp.YoutubeDL(opts_fallback) as ydl:
            return ydl.extract_info(url, download=False)
    except Exception as e:
        print(f"[ERROR] Fallback extract_info failed: {e}")
        return None


async def get_video_info(url: str) -> Optional[Dict[str, Any]]:
    """YouTube videosi haqida ma'lumotlarni asinxron olish."""
    return await asyncio.to_thread(_extract_info_sync, url)


def _search_youtube_sync(query: str, limit: int = 5) -> List[Dict[str, Any]]:
    """YouTube'dan kalit so'z bo'yicha inline qidirish."""
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'extract_flat': 'in_playlist',
        'skip_download': True,
        'noplaylist': True,
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            res = ydl.extract_info(f"ytsearch{limit}:{query}", download=False)
            if res and 'entries' in res:
                return [entry for entry in res['entries'] if entry]
    except Exception as e:
        print(f"[ERROR] search_youtube: {e}")
    return []


async def search_youtube(query: str, limit: int = 5) -> List[Dict[str, Any]]:
    """YouTube inline qidiruvini asinxron bajarish."""
    return await asyncio.to_thread(_search_youtube_sync, query, limit)


def _download_subtitles_sync(url: str) -> Tuple[Optional[str], str]:
    """Video subtitrlarini (.vtt/.srt) yuklab berish."""
    outtmpl = os.path.join(DOWNLOAD_DIR, '%(id)s_sub.%(ext)s')
    ydl_opts = {
        **COMMON_YOUTUBE_OPTS,
        'outtmpl': outtmpl,
        'writesubtitles': True,
        'writeautomaticsub': True,
        'subtitleslangs': ['uz', 'en', 'ru'],
        'skip_download': True,
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            video_id = info.get('id')
            pattern = os.path.join(DOWNLOAD_DIR, f"{video_id}_sub.*")
            sub_files = glob.glob(pattern)
            if sub_files:
                return sub_files[0], info.get('title', 'Subtitle')
            return None, "Subtitr mavjud emas."
    except Exception as e:
        return None, f"Subtitr olishda xatolik: {e}"


async def download_subtitles(url: str) -> Tuple[Optional[str], str]:
    """Video subtitrlarini asinxron yuklab berish."""
    return await asyncio.to_thread(_download_subtitles_sync, url)


def _trim_video_sync(url: str, start_sec: int, end_sec: int, quality: str = "720") -> Tuple[Optional[str], str, str]:
    """Videoni ko'rsatilgan vaqt oralig'ida (start_sec -> end_sec) qirqib yuklash."""
    outtmpl = os.path.join(DOWNLOAD_DIR, '%(id)s_trim_%(ext)s.%(ext)s')
    h = quality if quality.isdigit() else "720"
    fmt = (
        f'bestvideo[height<={h}][vcodec^=avc1][filesize<=50M]+bestaudio[acodec^=mp4a]/'
        f'best[height<={h}][vcodec^=avc1][filesize<=50M]/'
        f'best[height<={h}]/b'
    )
    ydl_opts = {
        **COMMON_YOUTUBE_OPTS,
        'outtmpl': outtmpl,
        'format': fmt,
        'download_ranges': yt_dlp.utils.download_range_func(None, [(start_sec, end_sec)]),
        'force_keyframes_at_cuts': True,
    }
    if FFMPEG_PATH:
        ydl_opts['ffmpeg_location'] = FFMPEG_PATH
        ydl_opts['merge_output_format'] = 'mp4'

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            video_id = info.get('id')
            title = info.get('title', 'Trimmed Video')
            pattern = os.path.join(DOWNLOAD_DIR, f"{video_id}_trim_*")
            files = glob.glob(pattern)
            if files:
                return files[0], title, "SUCCESS"
            return None, title, "Qirqilgan fayl topilmadi."
    except Exception as e:
        return None, "", f"Qirqishda xatolik: {e}"


async def trim_video(url: str, start_sec: int, end_sec: int, quality: str = "720") -> Tuple[Optional[str], str, str]:
    """Videoni asinxron qirqib yuklash."""
    return await asyncio.to_thread(_trim_video_sync, url, start_sec, end_sec, quality)


def _download_media_sync(url: str, mode: str = "video", quality: str = "720") -> Tuple[Optional[str], str, str]:
    """Videoni yoki audioni sinxron yuklab olish."""
    outtmpl = os.path.join(DOWNLOAD_DIR, '%(id)s_%(ext)s.%(ext)s')

    common_opts = {
        'outtmpl': outtmpl,
        'quiet': True,
        'no_warnings': True,
        'nocheckcertificate': True,
        'socket_timeout': 30,
        'max_filesize': 50 * 1024 * 1024,  # Telegram bot API max 50MB
        'extractor_args': {
            'youtube': {
                'player_client': ['mweb', 'android', 'web']
            }
        }
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
