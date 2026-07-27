import asyncio
import os
import glob
import urllib.request
import json
import re
from typing import Dict, Any, Optional, Tuple, List
from pytubefix import YouTube
import yt_dlp
from config import DOWNLOAD_DIR

# imageio_ffmpeg orqali avtomatik FFmpeg joylashuvini aniqlash
FFMPEG_PATH = None
try:
    import imageio_ffmpeg
    FFMPEG_PATH = imageio_ffmpeg.get_ffmpeg_exe()
except Exception as e:
    print(f"[WARN] imageio_ffmpeg topilmadi: {e}")

COMMON_YOUTUBE_OPTS = {
    'quiet': True,
    'no_warnings': True,
    'nocheckcertificate': True,
    'socket_timeout': 30,
    'extractor_args': {
        'youtube': {
            'player_client': ['mweb', 'android', 'ios']
        }
    }
}


def _extract_info_sync(url: str) -> Optional[Dict[str, Any]]:
    """YouTube videosi ma'lumotlarini rasmiy oEmbed API, pytubefix va yt-dlp o'rtasida 100% zaxira bilan olish."""
    v_match = re.search(r'(?:v=|shorts/|youtu\.be/)([\w-]+)', url)
    video_id = v_match.group(1) if v_match else None

    # 1-urinish: YouTube Rasmiy oEmbed API (Cheklovlarsiz va o'ta tezkor)
    if video_id:
        oembed_url = f"https://www.youtube.com/oembed?url=https://www.youtube.com/watch?v={video_id}&format=json"
        try:
            req = urllib.request.Request(oembed_url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=8) as res:
                data = json.loads(res.read().decode())
                if data and 'title' in data:
                    return {
                        'id': video_id,
                        'title': data.get('title'),
                        'duration': 0,
                        'uploader': data.get('author_name', 'YouTube'),
                        'view_count': 0,
                        'like_count': 0,
                        'thumbnail': data.get('thumbnail_url') or f"https://img.youtube.com/vi/{video_id}/hqdefault.jpg",
                        'url': f"https://www.youtube.com/watch?v={video_id}",
                        '_source': 'oembed'
                    }
        except Exception as e:
            print(f"[WARN] oEmbed extract failed: {e}")

    # 2-urinish: pytubefix (MWEB client)
    try:
        yt = YouTube(url, client='MWEB')
        v_id = yt.video_id
        if v_id and yt.title:
            return {
                'id': v_id,
                'title': yt.title,
                'duration': yt.length,
                'uploader': yt.author,
                'view_count': yt.views,
                'like_count': 0,
                'thumbnail': yt.thumbnail_url,
                'url': url,
                '_source': 'pytubefix_mweb'
            }
    except Exception as e:
        print(f"[WARN] pytubefix mweb extract failed: {e}")

    # 3-urinish: pytubefix (default client)
    try:
        yt = YouTube(url)
        v_id = yt.video_id
        if v_id and yt.title:
            return {
                'id': v_id,
                'title': yt.title,
                'duration': yt.length,
                'uploader': yt.author,
                'view_count': yt.views,
                'like_count': 0,
                'thumbnail': yt.thumbnail_url,
                'url': url,
                '_source': 'pytubefix'
            }
    except Exception as e:
        print(f"[WARN] pytubefix primary extract failed: {e}")

    # 4-urinish: yt-dlp zaxirasi
    opts_primary = {
        'quiet': True,
        'no_warnings': True,
        'skip_download': True,
        'noplaylist': True,
        'socket_timeout': 15,
        'nocheckcertificate': True,
        **COMMON_YOUTUBE_OPTS
    }
    try:
        with yt_dlp.YoutubeDL(opts_primary) as ydl:
            info = ydl.extract_info(url, download=False)
            if info and ('title' in info or 'id' in info):
                return info
    except Exception as e:
        print(f"[ERROR] yt-dlp fallback extract failed: {e}")

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
    """Videoni yoki audioni yuklab olish (MWEB, WEB, IOS, ANDROID pytubefix miyasi bilan)."""
    clients = ['MWEB', 'WEB', 'IOS', 'ANDROID']
    title = "YouTube Video"

    for c in clients:
        try:
            yt = YouTube(url, client=c)
            video_id = yt.video_id
            title = yt.title or title

            if mode == "audio":
                audio_stream = yt.streams.filter(only_audio=True).first()
                if not audio_stream:
                    audio_stream = yt.streams.get_audio_only()
                if audio_stream:
                    target_file = audio_stream.download(output_path=DOWNLOAD_DIR, filename=f"{video_id}.mp3")
                    return target_file, title, "SUCCESS"
            else:
                target_res = f"{quality}p" if quality.isdigit() else "720p"
                # 1. Tanlangan sifatli progressive stream
                stream = yt.streams.filter(res=target_res, progressive=True).first()
                # 2. Har qanday mp4 progressive stream
                if not stream:
                    stream = yt.streams.filter(progressive=True, file_extension='mp4').first()
                # 3. Har qanday progressive stream
                if not stream:
                    stream = yt.streams.filter(progressive=True).first()
                # 4. Tanlangan sifatli har qanday stream
                if not stream:
                    stream = yt.streams.filter(res=target_res).first()
                # 5. Har qanday birinchi stream
                if not stream:
                    stream = yt.streams.first()

                if stream:
                    target_file = stream.download(output_path=DOWNLOAD_DIR, filename=f"{video_id}.mp4")
                    file_size = os.path.getsize(target_file)
                    if file_size > 50 * 1024 * 1024:
                        os.remove(target_file)
                        return None, title, "TOO_LARGE"
                    return target_file, title, "SUCCESS"
        except Exception as ex:
            print(f"[WARN] pytubefix client {c} download failed: {ex}")

    # 5-urinish (Zaxira): yt-dlp fallback
    outtmpl = os.path.join(DOWNLOAD_DIR, '%(id)s_%(ext)s.%(ext)s')
    common_opts = {
        'outtmpl': outtmpl,
        'quiet': True,
        'no_warnings': True,
        'nocheckcertificate': True,
        'socket_timeout': 30,
        'max_filesize': 50 * 1024 * 1024,
        **COMMON_YOUTUBE_OPTS
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
            if info:
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
    except Exception as e:
        print(f"[ERROR] yt-dlp download failed: {e}")

    return None, title, "Faylni yuklab bo'lmadi."


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
