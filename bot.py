import discord
from discord.ext import commands
import yt_dlp
import asyncio
from async_timeout import timeout
import re
import traceback
import sys
import os
import glob
import time
import shutil
import subprocess
import requests
from urllib.parse import urlparse
from bs4 import BeautifulSoup
import math
import io
import gtts
from gtts import gTTS
import tempfile
import logging
import hashlib
import functools
from dotenv import load_dotenv
import threading
import aiohttp

load_dotenv()

logging.basicConfig(
level=logging.INFO,
format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
handlers=[
    logging.StreamHandler(sys.stdout)
]
)
logger = logging.getLogger('VCBot')

intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True
bot = commands.Bot(command_prefix='r!', intents=intents, help_command=None)

DOWNLOAD_DIR = "./downloads"
if not os.path.exists(DOWNLOAD_DIR):
    os.makedirs(DOWNLOAD_DIR)
logger.info(f"ダウンロードディレクトリを作成しました: {DOWNLOAD_DIR}")

TTS_DIR = "./tts"
if not os.path.exists(TTS_DIR):
    os.makedirs(TTS_DIR)
logger.info(f"TTSディレクトリを作成しました: {TTS_DIR}")

ATTACHMENT_DIR = "./attachments"
if not os.path.exists(ATTACHMENT_DIR):
    os.makedirs(ATTACHMENT_DIR)
logger.info(f"添付ファイルディレクトリを作成しました: {ATTACHMENT_DIR}")

kick_enabled = True
kick_list = [
    411916947773587456,
    412347257233604609,
    412347553141751808,
    412347780841865216,
    184405253028970496,
    614109280508968980,
]

EMOJI = {
    'success': '✅',
    'retry': '🔁',
    'error': '❌',
    'youtube': '📺',
    'spotify': '🎵',
    'soundcloud': '🌤️',
    'niconico': '🎬',
    'twitch': '🟣',
    'pornhub': '🔞',
    'file': '📁',
    'search': '🔍',
    'queue': '📝',
    'loop': '🔁',
    'pause': '⏸️',
    'play': '▶️',
    'stop': '⏹️',
    'skip': '⏭️',
    'mic': '🎤',
    'forward': '⏩',
    'backward': '⏪',
}

reading_channels = {}

def check_ffmpeg():
    try:
        result = subprocess.run(['ffmpeg', '-version'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10)
        logger.info(f"FFmpeg確認: {result.stdout.decode('utf-8', errors='ignore').splitlines()[0] if result.stdout else 'No output'}")
        return True
    except (subprocess.TimeoutExpired, subprocess.SubprocessError, FileNotFoundError, Exception) as e:
        logger.error(f"FFmpeg確認エラー: {e}")
        return False

def generate_safe_filename(url, title=None, video_id=None):
    if title and video_id:
        safe_title = re.sub(r'[^\w\s-]', '', title)
        safe_title = re.sub(r'[\s-]+', '-', safe_title).strip('-')
        safe_title = safe_title[:40]
        return f"{safe_title}-{video_id}"
    else:
        hash_object = hashlib.md5(url.encode())
        return hash_object.hexdigest()[:16]

ytdl_format_options = {
    'format': 'bestaudio/best',
    'outtmpl': f'{DOWNLOAD_DIR}/%(title).30s-%(id)s.%(ext)s',
    'restrictfilenames': True,
    'noplaylist': False,
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'logtostderr': False,
    'quiet': False,
    'no_warnings': False,
    'default_search': 'auto',
    'source_address': '0.0.0.0',
    'postprocessors': [{
        'key': 'FFmpegExtractAudio',
        'preferredcodec': 'mp3',
        'preferredquality': '192',
    }],
    'keepvideo': False,
    'overwrites': True,
    'verbose': True,
    'socket_timeout': 30,
    'cookiefile': 'cookies.txt',
    'external_downloader_args': ['-loglevel', 'panic'],
}

if os.getenv('YOUTUBE_USERNAME') and os.getenv('YOUTUBE_PASSWORD'):
    ytdl_format_options['username'] = os.getenv('YOUTUBE_USERNAME')
    ytdl_format_options['password'] = os.getenv('YOUTUBE_PASSWORD')

ffmpeg_options = {
    'options': '-vn -loglevel warning',
    'before_options': '-nostdin -hide_banner',
}

async def extract_niconico_info(url):
    try:
        video_id = None
        if 'nicovideo.jp' in url or 'nico.ms' in url:
            if 'nico.ms' in url:
                video_id = url.split('/')[-1]
            else:
                match = re.search(r'(sm|nm|so)(\d+)', url)
                if match:
                    video_id = match.group(0)
            
            if video_id:
                try:
                    headers = {
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
                    }
                    full_url = f"https://www.nicovideo.jp/watch/{video_id}"
                    response = requests.get(full_url, headers=headers, timeout=10)
                    
                    if response.status_code == 200:
                        soup = BeautifulSoup(response.text, 'html.parser')
                        
                        title_element = soup.find('meta', {'property': 'og:title'})
                        if title_element and title_element.get('content'):
                            title = title_element.get('content')
                            logger.info(f"ニコニコ動画情報抽出成功: {title}")
                            return title
                except (requests.RequestException, requests.Timeout, requests.ConnectionError) as e:
                    logger.error(f"ニコニコ動画情報抽出ネットワークエラー: {e}")
        
        return url
    except Exception as e:
        logger.error(f"ニコニコ動画情報抽出エラー: {e}")
        return url

async def extract_spotify_info(url):
    try:
        parsed_url = urlparse(url)
        path_parts = parsed_url.path.split('/')
        
        if 'playlist' in path_parts:
            playlist_index = path_parts.index('playlist')
            if playlist_index + 1 < len(path_parts):
                playlist_id = path_parts[playlist_index + 1]
                
                try:
                    response = requests.get(url, timeout=10)
                    if response.status_code == 200:
                        html_content = response.text
                        
                        playlist_name_match = re.search(r'<title>(.*?) - playlist by (.*?) \|', html_content)
                        if playlist_name_match:
                            playlist_name = playlist_name_match.group(1)
                            creator = playlist_name_match.group(2)
                            logger.info(f"Spotifyプレイリスト情報抽出成功: {playlist_name} by {creator}")
                            return f"spotify playlist {playlist_name} by {creator}"
                        
                        og_title_match = re.search(r'<meta property="og:title" content="(.*?)"', html_content)
                        if og_title_match:
                            logger.info(f"Spotifyプレイリスト情報抽出成功: {og_title_match.group(1)}")
                            return f"spotify playlist {og_title_match.group(1)}"
                except (requests.RequestException, requests.Timeout, requests.ConnectionError) as e:
                    logger.error(f"Spotifyプレイリスト情報抽出ネットワークエラー: {e}")
                
                return f"spotify playlist {playlist_id}"
        
        elif 'track' in path_parts:
            track_index = path_parts.index('track')
            if track_index + 1 < len(path_parts):
                track_id = path_parts[track_index + 1]
                
                try:
                    response = requests.get(url, timeout=10)
                    if response.status_code == 200:
                        html_content = response.text
                        
                        title_match = re.search(r'<title>(.*?) - song by (.*?) \|', html_content)
                        if title_match:
                            title = title_match.group(1)
                            artist = title_match.group(2)
                            logger.info(f"Spotify曲情報抽出成功: {title} by {artist}")
                            return f"{title} {artist}"
                        
                        og_title_match = re.search(r'<meta property="og:title" content="(.*?)"', html_content)
                        if og_title_match:
                            logger.info(f"Spotify曲情報抽出成功: {og_title_match.group(1)}")
                            return og_title_match.group(1)
                except (requests.RequestException, requests.Timeout, requests.ConnectionError) as e:
                    logger.error(f"Spotify情報抽出ネットワークエラー: {e}")
        
        elif 'album' in path_parts:
            album_index = path_parts.index('album')
            if album_index + 1 < len(path_parts):
                album_id = path_parts[album_index + 1]
                
                try:
                    response = requests.get(url, timeout=10)
                    if response.status_code == 200:
                        html_content = response.text
                        
                        album_match = re.search(r'<title>(.*?) - album by (.*?) \|', html_content)
                        if album_match:
                            album = album_match.group(1)
                            artist = album_match.group(2)
                            logger.info(f"Spotifyアルバム情報抽出成功: {album} by {artist}")
                            return f"{album} {artist}"
                        
                        og_title_match = re.search(r'<meta property="og:title" content="(.*?)"', html_content)
                        if og_title_match:
                            logger.info(f"Spotifyアルバム情報抽出成功: {og_title_match.group(1)}")
                            return f"spotify album {og_title_match.group(1)}"
                except (requests.RequestException, requests.Timeout, requests.ConnectionError) as e:
                    logger.error(f"Spotifyアルバム情報抽出ネットワークエラー: {e}")
                
                return f"spotify album {album_id}"
        
        return url
    except Exception as e:
        logger.error(f"Spotify情報抽出エラー: {e}")
        return url

async def extract_soundcloud_info(url):
    try:
        try:
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                soup = BeautifulSoup(response.text, 'html.parser')
                
                title_element = soup.find('meta', property='og:title')
                if title_element and title_element.get('content'):
                    logger.info(f"SoundCloud情報抽出成功: {title_element.get('content')}")
                    return title_element.get('content')
                
                description_element = soup.find('meta', property='og:description')
                if description_element and description_element.get('content'):
                    logger.info(f"SoundCloud情報抽出成功: {description_element.get('content')}")
                    return description_element.get('content')
        except (requests.RequestException, requests.Timeout, requests.ConnectionError) as e:
            logger.error(f"SoundCloud情報抽出ネットワークエラー: {e}")
        
        return url
    except Exception as e:
        logger.error(f"SoundCloud情報抽出エラー: {e}")
        return url

async def extract_twitch_info(url):
    try:
        parsed_url = urlparse(url)
        path_parts = parsed_url.path.split('/')
        
        if len(path_parts) > 1 and path_parts[1]:
            channel_name = path_parts[1]
            
            try:
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                    'Accept-Language': 'ja-JP,ja;q=0.9,en-US;q=0.8,en;q=0.7'
                }
                response = requests.get(url, headers=headers, timeout=10)
                
                if response.status_code == 200:
                    soup = BeautifulSoup(response.text, 'html.parser')
                    
                    title_element = soup.find('meta', property='og:title')
                    if title_element and title_element.get('content'):
                        title = title_element.get('content')
                        logger.info(f"Twitch情報抽出成功: {title}")
                        return f"twitch {title}"
                    
                    return f"twitch {channel_name} stream"
            except (requests.RequestException, requests.Timeout, requests.ConnectionError) as e:
                logger.error(f"Twitch情報抽出ネットワークエラー: {e}")
        
        return f"twitch stream {url}"
    except Exception as e:
        logger.error(f"Twitch情報抽出エラー: {e}")
        return url

async def extract_pornhub_info(url):
    try:
        logger.info(f"PornHub動画を直接ダウンロードします: {url}")
        return url
    except Exception as e:
        logger.error(f"PornHub情報抽出エラー: {e}")
        return url

def cleanup_old_files(max_age_hours=24):
    current_time = time.time()
    try:
        for file_path in glob.glob(f"{DOWNLOAD_DIR}/*"):
            try:
                file_age = current_time - os.path.getmtime(file_path)
                if file_age > max_age_hours * 3600:
                    try:
                        os.remove(file_path)
                        logger.info(f"古いファイルを削除しました: {file_path}")
                    except (PermissionError, OSError) as e:
                        logger.error(f"ファイル削除エラー: {e}")
            except (OSError, Exception) as e:
                logger.error(f"ファイル処理エラー: {e}")
        
        for file_path in glob.glob(f"{TTS_DIR}/*"):
            try:
                file_age = current_time - os.path.getmtime(file_path)
                if file_age > 1 * 3600:
                    try:
                        os.remove(file_path)
                        logger.info(f"古いTTSファイルを削除しました: {file_path}")
                    except (PermissionError, OSError) as e:
                        logger.error(f"TTSファイル削除エラー: {e}")
            except (OSError, Exception) as e:
                logger.error(f"TTSファイル処理エラー: {e}")
                
        for file_path in glob.glob(f"{ATTACHMENT_DIR}/*"):
            try:
                file_age = current_time - os.path.getmtime(file_path)
                if file_age > max_age_hours * 3600:
                    try:
                        os.remove(file_path)
                        logger.info(f"古い添付ファイルを削除しました: {file_path}")
                    except (PermissionError, OSError) as e:
                        logger.error(f"添付ファイル削除エラー: {e}")
            except (OSError, Exception) as e:
                logger.error(f"添付ファイル処理エラー: {e}")
    except Exception as e:
        logger.error(f"クリーンアップ処理エラー: {e}")

class ProgressHandler:
    def __init__(self, message):
        self.message = message
        self.last_update_time = 0
        self.start_time = time.time()
        self.download_complete = False

    async def update_progress(self, d):
        try:
            if d['status'] == 'downloading':
                downloaded = d.get('downloaded_bytes', 0)
                total = d.get('total_bytes', 0) or d.get('total_bytes_estimate', 0)
                speed = d.get('speed', 0) or 0
                eta = d.get('eta', 0) or 0
                filename = os.path.basename(d.get('filename', '不明なファイル'))
                
                current_time = time.time()
                if current_time - self.last_update_time >= 1.0:
                    self.last_update_time = current_time
                    
                    if total > 0 and downloaded > 0:
                        progress = min(downloaded / total * 100, 100)
                    else:
                        progress = 0
                    
                    bar_length = 20
                    filled_length = int(bar_length * progress / 100)
                    bar = '█' * filled_length + '░' * (bar_length - filled_length)
                    
                    speed_str = f"{speed / 1024 / 1024:.2f} MB/s" if speed else "不明"
                    eta_str = f"{eta}秒" if eta else "不明"
                    
                    logger.info(f"ダウンロード進捗: {filename} - {progress:.1f}% - {speed_str} - 残り {eta_str}")
                    
                    embed = discord.Embed(
                        title=f"{EMOJI['retry']} ダウンロード中...",
                        description=f"ファイル: `{filename}`\n進捗: [{bar}] {progress:.1f}%\n速度: {speed_str}\n残り時間: {eta_str}",
                        color=discord.Color.gold()
                    )
                    
                    elapsed = current_time - self.start_time
                    embed.set_footer(text=f"経過時間: {int(elapsed)}秒")
                    
                    try:
                        asyncio.create_task(self.message.edit(embed=embed))
                    except (discord.HTTPException, discord.Forbidden, discord.NotFound) as e:
                        logger.error(f"進捗更新エラー: {e}")
            
            elif d['status'] == 'finished' and not self.download_complete:
                self.download_complete = True
                logger.info(f"ダウンロード完了: {d.get('filename', '不明なファイル')}")
                
                embed = discord.Embed(
                    title=f"{EMOJI['success']} ダウンロード完了",
                    description=f"ファイル: `{os.path.basename(d.get('filename', '不明なファイル'))}`\n進捗: [{'█' * 20}] 100%\nファイルの処理中...",
                    color=discord.Color.green()
                )
                
                elapsed = time.time() - self.start_time
                embed.set_footer(text=f"経過時間: {int(elapsed)}秒")
                
                try:
                    asyncio.create_task(self.message.edit(embed=embed))
                except (discord.HTTPException, discord.Forbidden, discord.NotFound) as e:
                    logger.error(f"完了メッセージ更新エラー: {e}")
                    
            elif d['status'] == 'error':
                logger.error(f"ダウンロードエラー: {d.get('error', '不明なエラー')}")
                embed = discord.Embed(
                    title=f"{EMOJI['error']} ダウンロードエラー",
                    description=f"エラー: {d.get('error', '不明なエラー')}",
                    color=discord.Color.red()
                )
                try:
                    asyncio.create_task(self.message.edit(embed=embed))
                except (discord.HTTPException, discord.Forbidden, discord.NotFound) as e:
                    logger.error(f"エラーメッセージ更新エラー: {e}")
        except Exception as e:
            logger.error(f"進捗ハンドラーエラー: {e}")
            traceback.print_exc()

class DRMProtectedError(Exception):
    pass

class VoiceConnectionError(Exception):
    pass

class NetworkError(Exception):
    pass

class YTDLSource(discord.PCMVolumeTransformer):
    def __init__(self, source, *, data, volume=0.5):
        super().__init__(source, volume)
        self.data = data
        self.title = data.get('title')
        self.url = data.get('url')
        self.thumbnail = data.get('thumbnail')
        self.duration = data.get('duration')
        self.uploader = data.get('uploader')
        self.uploader_url = data.get('uploader_url')
        self.view_count = data.get('view_count')
        self.like_count = data.get('like_count')
        self.webpage_url = data.get('webpage_url') or data.get('url')
        self.filename = data.get('__filename', '')
        self.requester = data.get('requester')
        self.source_type = data.get('source_type', 'youtube')
        self.original_query = data.get('original_query', '')
        self.id = data.get('id', '') or hash(self.title + str(time.time()))
        self.current_position = 0
        self._cleanup_done = False
        logger.info(f"音源作成: {self.title} - {self.filename}")

    @classmethod
    async def from_url(cls, url, *, stream=False, message=None, requester=None, playlist=False):
        if not check_ffmpeg():
            logger.error("FFmpegが見つかりません")
            embed = discord.Embed(
                title=f"{EMOJI['error']} エラー",
                description="FFmpegがインストールされていないか、パスが通っていません。",
                color=discord.Color.red()
            )
            await message.edit(embed=embed)
            raise RuntimeError("FFmpegが見つかりません")
        
        original_query = url
        is_url = bool(re.match(r'https?://', url))
        is_spotify = is_url and 'spotify.com' in url.lower()
        is_soundcloud = is_url and 'soundcloud.com' in url.lower()
        is_youtube = is_url and ('youtube.com' in url.lower() or 'youtu.be' in url.lower())
        is_niconico = is_url and ('nicovideo.jp' in url.lower() or 'nico.ms' in url.lower())
        is_twitch = is_url and 'twitch.tv' in url.lower()
        is_pornhub = is_url and ('pornhub.com' in url.lower() or 'pornhub.org' in url.lower())
        
        source_type = 'youtube'
        source_emoji = EMOJI['youtube']
        
        is_playlist = False
        if is_spotify and ('playlist' in url.lower() or 'album' in url.lower()):
            is_playlist = True
        elif is_youtube and 'list=' in url.lower():
            is_playlist = True
        elif is_soundcloud and '/sets/' in url.lower():
            is_playlist = True
        
        process_playlist = playlist and is_playlist
        
        logger.info(f"URL処理: {url} - タイプ: {source_type} - プレイリスト: {is_playlist}")
        
        if is_spotify:
            source_type = 'spotify'
            source_emoji = EMOJI['spotify']
            search_query = await extract_spotify_info(url)
            url = f"ytsearch:{search_query}"
            logger.info(f"Spotify検索クエリ: {search_query}")
        elif is_soundcloud:
            source_type = 'soundcloud'
            source_emoji = EMOJI['soundcloud']
            if not url.startswith("https://soundcloud.com"):
                search_query = await extract_soundcloud_info(url)
                url = f"ytsearch:{search_query}"
                logger.info(f"SoundCloud検索クエリ: {search_query}")
        elif is_niconico:
            source_type = 'niconico'
            source_emoji = EMOJI['niconico']
            search_query = await extract_niconico_info(url)
            logger.info(f"ニコニコ動画検索クエリ: {search_query}")
            
            ytdl_opts = dict(ytdl_format_options)
            if os.getenv('NICONICO_USERNAME') and os.getenv('NICONICO_PASSWORD'):
                ytdl_opts['username'] = os.getenv('NICONICO_USERNAME')
                ytdl_opts['password'] = os.getenv('NICONICO_PASSWORD')
        elif is_twitch:
            source_type = 'twitch'
            source_emoji = EMOJI['twitch']
            search_query = await extract_twitch_info(url)
            url = f"ytsearch:{search_query}"
            logger.info(f"Twitch検索クエリ: {search_query}")
        elif is_pornhub:
            source_type = 'pornhub'
            source_emoji = EMOJI['pornhub']
            url = await extract_pornhub_info(url)
            logger.info(f"PornHub URL: {url}")
            
            ytdl_opts = dict(ytdl_format_options)
            ytdl_opts['noplaylist'] = True
        elif is_youtube:
            source_type = 'youtube'
            source_emoji = EMOJI['youtube']
            ytdl_opts = dict(ytdl_format_options)
            
            if process_playlist:
                ytdl_opts['noplaylist'] = False
                ytdl_opts['extract_flat'] = 'in_playlist'
                ytdl_opts['playlistend'] = 30
            else:
                ytdl_opts['noplaylist'] = True
        elif not is_url:
            source_type = 'search'
            source_emoji = EMOJI['search']
            url = f"ytsearch:{url}"
            ytdl_opts = dict(ytdl_format_options)
            logger.info(f"検索クエリ: {url}")
        else:
            ytdl_opts = dict(ytdl_format_options)
        
        embed = discord.Embed(
            title=f"{source_emoji} 音楽を準備中...",
            description="音楽情報を取得しています...",
            color=discord.Color.blue()
        )
        await message.edit(embed=embed)
        
        try:
            progress_handler = ProgressHandler(message)
            
            if 'ytdl_opts' not in locals():
                ytdl_opts = dict(ytdl_format_options)
            
            ytdl_opts['outtmpl'] = f'{DOWNLOAD_DIR}/%(title).30s-%(id)s.%(ext)s'
            ytdl_opts['restrictfilenames'] = True
            
            progress_queue = asyncio.Queue()
            
            def progress_hook(d):
                try:
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        loop.create_task(progress_queue.put(d))
                    else:
                        logger.error("イベントループが実行されていません")
                except Exception as e:
                    logger.error(f"進捗フック処理エラー: {e}")
            
            async def progress_monitor():
                try:
                    while True:
                        try:
                            d = await asyncio.wait_for(progress_queue.get(), timeout=1.0)
                            await progress_handler.update_progress(d)
                            progress_queue.task_done()
                        except asyncio.TimeoutError:
                            continue
                        except asyncio.CancelledError:
                            break
                        except Exception as e:
                            logger.error(f"進捗モニター処理エラー: {e}")
                except Exception as e:
                    logger.error(f"進捗モニタータスクエラー: {e}")
            
            monitor_task = asyncio.create_task(progress_monitor())
            
            ytdl_opts['progress_hooks'] = [progress_hook]
            
            if process_playlist:
                ytdl_opts['noplaylist'] = False
                if is_youtube:
                    ytdl_opts['extract_flat'] = 'in_playlist'
                    ytdl_opts['playlistend'] = 30
            else:
                ytdl_opts['noplaylist'] = True
            
            temp_ytdl = yt_dlp.YoutubeDL(ytdl_opts)
            
            try:
                logger.info(f"情報抽出開始: {url}")
                data = await asyncio.to_thread(temp_ytdl.extract_info, url, download=not process_playlist)
                logger.info(f"情報抽出完了: {url}")
            except yt_dlp.utils.DownloadError as e:
                logger.error(f"ダウンロード中にエラーが発生: {e}")
                embed = discord.Embed(
                    title=f"{EMOJI['error']} ダウンロードエラー",
                    description=f"ダウンロード中にエラーが発生しました: {str(e)}",
                    color=discord.Color.red()
                )
                await message.edit(embed=embed)
                monitor_task.cancel()
                raise e
            except Exception as e:
                logger.error(f"予期せぬダウンロードエラー: {e}")
                embed = discord.Embed(
                    title=f"{EMOJI['error']} エラー",
                    description=f"予期せぬエラーが発生しました: {str(e)}",
                    color=discord.Color.red()
                )
                await message.edit(embed=embed)
                monitor_task.cancel()
                raise e
            
            if process_playlist and data and 'entries' in data:
                playlist_items = []
                playlist_title = data.get('title', 'プレイリスト')
                
                embed = discord.Embed(
                    title=f"{source_emoji} プレイリスト読み込み中",
                    description=f"プレイリスト「{playlist_title}」から曲を読み込んでいます...",
                    color=discord.Color.blue()
                )
                await message.edit(embed=embed)
                
                entries = list(data['entries'])
                total_entries = len(entries)
                logger.info(f"プレイリスト項目数: {total_entries}")
                
                for i, entry in enumerate(entries[:30]):
                    try:
                        video_url = None
                        if entry.get('url'):
                            video_url = entry.get('url')
                        elif entry.get('id'):
                            if is_youtube:
                                video_url = f"https://www.youtube.com/watch?v={entry['id']}"
                            elif is_spotify:
                                video_url = f"ytsearch:{entry.get('title', '')} audio"
                            elif is_soundcloud:
                                video_url = entry.get('webpage_url', '')
                        elif entry.get('webpage_url'):
                            video_url = entry.get('webpage_url')
                        
                        if not video_url:
                            logger.warning(f"プレイリスト項目 {i+1}/{total_entries} のURLが見つかりません")
                            continue
                        
                        logger.info(f"プレイリスト項目 {i+1}/{total_entries} 処理中: {video_url}")
                        
                        single_opts = dict(ytdl_format_options)
                        single_opts['noplaylist'] = True
                        single_opts['outtmpl'] = f'{DOWNLOAD_DIR}/pl{i+1}-%(title).20s-%(id)s.%(ext)s'
                        single_opts['restrictfilenames'] = True
                        
                        single_opts['progress_hooks'] = [progress_hook]
                        
                        single_ytdl = yt_dlp.YoutubeDL(single_opts)
                        
                        embed = discord.Embed(
                            title=f"{source_emoji} プレイリスト読み込み中",
                            description=f"プレイリスト「{playlist_title}」から曲を読み込んでいます...\n進捗: {i+1}/{min(30, total_entries)}",
                            color=discord.Color.blue()
                        )
                        await message.edit(embed=embed)
                        
                        single_data = await asyncio.to_thread(single_ytdl.extract_info, video_url, download=True)
                        
                        if single_data:
                            single_data['source_type'] = source_type
                            single_data['original_query'] = original_query
                            single_data['requester'] = requester
                            
                            filename = single_ytdl.prepare_filename(single_data)
                            if not os.path.exists(filename):
                                base, ext = os.path.splitext(filename)
                                mp3_filename = f"{base}.mp3"
                                if os.path.exists(mp3_filename):
                                    filename = mp3_filename
                                    logger.info(f"MP3ファイルが見つかりました: {filename}")
                            
                            single_data['__filename'] = filename
                            
                            if os.path.exists(filename) and os.path.getsize(filename) > 0:
                                logger.info(f"プレイリスト項目 {i+1} ファイル確認: {filename} ({os.path.getsize(filename)} バイト)")
                                source = discord.FFmpegPCMAudio(filename, **ffmpeg_options)
                                playlist_items.append(cls(source, data=single_data))
                            else:
                                logger.warning(f"プレイリスト項目 {i+1} のファイルが見つからないか空です: {filename}")
                    except Exception as e:
                        logger.error(f"プレイリストアイテム {i+1} 処理エラー: {e}")
                        continue
                
                monitor_task.cancel()
                
                if playlist_items:
                    logger.info(f"プレイリスト読み込み完了: {len(playlist_items)}曲")
                    embed = discord.Embed(
                        title=f"{source_emoji} プレイリスト読み込み完了",
                        description=f"プレイリスト「{playlist_title}」から{len(playlist_items)}曲を読み込みました。",
                        color=discord.Color.green()
                    )
                    await message.edit(embed=embed)
                    return playlist_items
                else:
                    logger.error("プレイリストから曲を読み込めませんでした")
                    embed = discord.Embed(
                        title=f"{EMOJI['error']} プレイリストエラー",
                        description="プレイリストから曲を読み込めませんでした。",
                        color=discord.Color.red()
                    )
                    await message.edit(embed=embed)
                    raise DRMProtectedError("プレイリストから曲を読み込めませんでした。")
            
            if data is None:
                logger.error("動画データが取得できませんでした")
                embed = discord.Embed(
                    title=f"{EMOJI['error']} エラー",
                    description="動画を取得できませんでした。",
                    color=discord.Color.red()
                )
                await message.edit(embed=embed)
                monitor_task.cancel()
                raise DRMProtectedError("動画を取得できませんでした。")
                
            if 'entries' in data:
                if not data['entries']:
                    logger.error("検索結果が見つかりませんでした")
                    embed = discord.Embed(
                        title=f"{EMOJI['error']} エラー",
                        description="検索結果が見つかりませんでした。",
                        color=discord.Color.red()
                    )
                    await message.edit(embed=embed)
                    monitor_task.cancel()
                    raise DRMProtectedError("動画を取得できませんでした。")
                data = data['entries'][0]
                logger.info(f"検索結果から最初の項目を選択: {data.get('title')}")
            
            data['source_type'] = source_type
            data['original_query'] = original_query
            
            if not stream:
                try:
                    logger.info(f"ダウンロード開始: {data.get('title')}")
                    await asyncio.to_thread(temp_ytdl.download, [data['webpage_url'] if 'webpage_url' in data else url])
                    logger.info(f"ダウンロード完了: {data.get('title')}")
                except Exception as e:
                    logger.error(f"明示的ダウンロードエラー: {e}")
            
            filename = temp_ytdl.prepare_filename(data)
            logger.info(f"準備されたファイル名: {filename}")
            
            if not os.path.exists(filename):
                base, ext = os.path.splitext(filename)
                mp3_filename = f"{base}.mp3"
                if os.path.exists(mp3_filename):
                    filename = mp3_filename
                    logger.info(f"MP3ファイルが見つかりました: {filename}")
                else:
                    logger.warning(f"ファイルが見つかりません: {filename}")
                    logger.info(f"ダウンロードディレクトリの内容:")
                    files_found = False
                    try:
                        for file in os.listdir(DOWNLOAD_DIR):
                            files_found = True
                            logger.info(f" - {file}")
                    except (PermissionError, OSError) as e:
                        logger.error(f"ディレクトリ読み取りエラー: {e}")
                    
                    if not files_found:
                        logger.warning("ダウンロードディレクトリは空です")
                    
                    video_id = data.get('id')
                    if video_id:
                        try:
                            for file in os.listdir(DOWNLOAD_DIR):
                                if video_id in file:
                                    filename = os.path.join(DOWNLOAD_DIR, file)
                                    logger.info(f"IDに基づいてファイルを見つけました: {filename}")
                                    break
                        except (PermissionError, OSError) as e:
                            logger.error(f"ディレクトリ読み取りエラー: {e}")
            
            if not os.path.exists(filename) or os.path.getsize(filename) == 0:
                logger.warning(f"ファイルが見つからないか空のため、再ダウンロードを試みます: {filename}")
                embed = discord.Embed(
                    title=f"{EMOJI['retry']} 再ダウンロード中...",
                    description="ファイルが見つからないため、再ダウンロードを試みています...",
                    color=discord.Color.gold()
                )
                await message.edit(embed=embed)
                
                try:
                    safe_filename = generate_safe_filename(url, data.get('title'), data.get('id'))
                    ytdl_opts['outtmpl'] = f'{DOWNLOAD_DIR}/{safe_filename}.%(ext)s'
                    ytdl_opts['force_generic_extractor'] = False
                    ytdl_opts['cachedir'] = False
                    ytdl_opts['nooverwrites'] = False
                    ytdl_opts['overwrites'] = True
                    progress_handler.download_complete = False
                    temp_ytdl = yt_dlp.YoutubeDL(ytdl_opts)
                    
                    logger.info(f"再ダウンロード開始: {url}")
                    data = await asyncio.to_thread(temp_ytdl.extract_info, url, download=True)
                    logger.info(f"再ダウンロード完了: {url}")
                    
                    if data is None:
                        logger.error("再ダウンロード中に動画を取得できませんでした")
                        embed = discord.Embed(
                            title=f"{EMOJI['error']} エラー",
                            description="再ダウンロード中に動画を取得できませんでした。",
                            color=discord.Color.red()
                        )
                        await message.edit(embed=embed)
                        monitor_task.cancel()
                        raise DRMProtectedError("動画を取得できませんでした。")
                        
                    if 'entries' in data:
                        if not data['entries']:
                            logger.error("再ダウンロード中に検索結果が見つかりませんでした")
                            embed = discord.Embed(
                                title=f"{EMOJI['error']} エラー",
                                description="再ダウンロード中に検索結果が見つかりませんでした。",
                                color=discord.Color.red()
                            )
                            await message.edit(embed=embed)
                            monitor_task.cancel()
                            raise DRMProtectedError("動画を取得できませんでした。")
                        data = data['entries'][0]
                    
                    data['source_type'] = source_type
                    data['original_query'] = original_query
                    
                    filename = temp_ytdl.prepare_filename(data)
                    logger.info(f"再ダウンロード後のファイル名: {filename}")
                    
                    if not os.path.exists(filename):
                        base, ext = os.path.splitext(filename)
                        mp3_filename = f"{base}.mp3"
                        if os.path.exists(mp3_filename):
                            filename = mp3_filename
                            logger.info(f"MP3ファイルが見つかりました: {filename}")
                    
                    if not os.path.exists(filename) or os.path.getsize(filename) == 0:
                        logger.warning(f"再ダウンロード後もファイルが見つからないか空です: {filename}")
                        audio_url = data.get('url')
                        if audio_url:
                            safe_output_name = generate_safe_filename(audio_url, data.get('title'), data.get('id'))
                            output_file = os.path.join(DOWNLOAD_DIR, f"{safe_output_name}.mp3")
                            try:
                                logger.info(f"FFmpegで直接ダウンロード試行: {audio_url} -> {output_file}")
                                subprocess.run([
                                    'ffmpeg', '-y', '-i', audio_url, 
                                    '-vn', '-ar', '44100', '-ac', '2', '-ab', '192k', '-f', 'mp3',
                                    output_file
                                ], check=True, timeout=300)
                                
                                if os.path.exists(output_file) and os.path.getsize(output_file) > 0:
                                    filename = output_file
                                    logger.info(f"手動ダウンロード成功: {filename} ({os.path.getsize(output_file)} バイト)")
                                else:
                                    logger.error(f"手動ダウンロードに失敗しました: {output_file}")
                                    embed = discord.Embed(
                                        title=f"{EMOJI['error']} ファイルエラー",
                                        description="手動ダウンロードに失敗しました。ファイルが作成されませんでした。",
                                        color=discord.Color.red()
                                    )
                                    await message.edit(embed=embed)
                                    monitor_task.cancel()
                                    raise FileNotFoundError("手動ダウンロードに失敗しました")
                            except (subprocess.SubprocessError, subprocess.TimeoutExpired) as e:
                                logger.error(f"FFmpegによる変換中にエラーが発生しました: {e}")
                                embed = discord.Embed(
                                    title=f"{EMOJI['error']} FFmpegエラー",
                                    description="FFmpegによる変換中にエラーが発生しました。",
                                    color=discord.Color.red()
                                )
                                await message.edit(embed=embed)
                                monitor_task.cancel()
                                raise e
                except Exception as e:
                    logger.error(f"再ダウンロード中にエラーが発生しました: {e}")
                    embed = discord.Embed(
                        title=f"{EMOJI['error']} エラー",
                        description=f"再ダウンロード中にエラーが発生しました: {str(e)}",
                        color=discord.Color.red()
                    )
                    await message.edit(embed=embed)
                    monitor_task.cancel()
                    raise e
            
            monitor_task.cancel()
            
            data['__filename'] = filename
            data['requester'] = requester
            
            try:
                ffmpeg_opts = {
                    'options': '-vn -loglevel warning',
                    'before_options': '-nostdin -hide_banner',
                }
                source = discord.FFmpegPCMAudio(filename, **ffmpeg_options)
                transformed_source = discord.PCMVolumeTransformer(source, volume=0.5)
                return cls(transformed_source, data=data)
            except Exception as e:
                logger.error(f"音声ソース作成エラー: {e}")
                raise e
        
        except yt_dlp.utils.DownloadError as e:
            error_message = str(e).lower()
            logger.error(f"ダウンロードエラー: {error_message}")
            if any(keyword in error_message for keyword in ['drm', 'protected', 'premium', 'copyright', 'unavailable']):
                embed = discord.Embed(
                    title=f"{EMOJI['error']} DRMエラー",
                    description="この動画はDRM保護されているか、プレミアムアカウントが必要です。",
                    color=discord.Color.red()
                )
                await message.edit(embed=embed)
                raise DRMProtectedError("この動画はDRM保護されているか、プレミアムアカウントが必要です。")
            
            if any(keyword in error_message for keyword in ['network', 'connection', 'timeout', 'timed out']):
                embed = discord.Embed(
                    title=f"{EMOJI['error']} ネットワークエラー",
                    description="ネットワーク接続中にエラーが発生しました。インターネット接続を確認してください。",
                    color=discord.Color.red()
                )
                await message.edit(embed=embed)
                raise NetworkError("ネットワーク接続エラー")
                
            embed = discord.Embed(
                title=f"{EMOJI['error']} ダウンロードエラー",
                description=f"ダウンロード中にエラーが発生しました: {str(e)}",
                color=discord.Color.red()
            )
            await message.edit(embed=embed)
            raise e
        except FileNotFoundError as e:
            logger.error(f"ファイルが見つかりません: {str(e)}")
            embed = discord.Embed(
                title=f"{EMOJI['error']} ファイルエラー",
                description=f"ダウンロードしたファイルが見つかりませんでした。もう一度お試しください。",
                color=discord.Color.red()
            )
            await message.edit(embed=embed)
            raise e
        except Exception as e:
            logger.error(f"予期せぬエラー: {str(e)}")
            traceback.print_exc()
            embed = discord.Embed(
                title=f"{EMOJI['error']} 予期せぬエラー",
                description=f"予期せぬエラーが発生しました: {str(e)}",
                color=discord.Color.red()
            )
            await message.edit(embed=embed)
            raise e

    @classmethod
    async def from_attachment(cls, attachment, *, message=None, requester=None):
        if not check_ffmpeg():
            logger.error("FFmpegが見つかりません")
            embed = discord.Embed(
                title=f"{EMOJI['error']} エラー",
                description="FFmpegがインストールされていないか、パスが通っていません。",
                color=discord.Color.red()
            )
            await message.edit(embed=embed)
            raise RuntimeError("FFmpegが見つかりません")
        
        embed = discord.Embed(
            title=f"{EMOJI['file']} 添付ファイルを処理中...",
            description=f"ファイル: `{attachment.filename}`\nサイズ: {attachment.size / 1024 / 1024:.2f} MB",
            color=discord.Color.blue()
        )
        await message.edit(embed=embed)
        
        try:
            # ファイル名の安全化
            timestamp = int(time.time())
            safe_filename = re.sub(r'[^\w\s.-]', '', attachment.filename)
            safe_filename = re.sub(r'[\s]+', '_', safe_filename).strip('_')
            
            if not safe_filename:
                safe_filename = f"attachment_{timestamp}"
            
            # 拡張子の確認
            file_ext = os.path.splitext(attachment.filename)[1].lower()
            
            # 保存先のパス
            original_path = os.path.join(ATTACHMENT_DIR, f"{safe_filename}")
            
            # ファイルをダウンロード
            async with aiohttp.ClientSession() as session:
                async with session.get(attachment.url) as resp:
                    if resp.status != 200:
                        logger.error(f"添付ファイルのダウンロードに失敗しました: {resp.status}")
                        embed = discord.Embed(
                            title=f"{EMOJI['error']} ダウンロードエラー",
                            description=f"添付ファイルのダウンロードに失敗しました。ステータスコード: {resp.status}",
                            color=discord.Color.red()
                        )
                        await message.edit(embed=embed)
                        raise NetworkError("添付ファイルのダウンロードに失敗しました")
                    
                    content = await resp.read()
                    
                    with open(original_path, 'wb') as f:
                        f.write(content)
            
            logger.info(f"添付ファイルをダウンロードしました: {original_path} ({len(content)} バイト)")
            
            # 音声ファイルに変換
            output_path = os.path.join(ATTACHMENT_DIR, f"{os.path.splitext(safe_filename)[0]}_{timestamp}.mp3")
            
            embed = discord.Embed(
                title=f"{EMOJI['retry']} ファイルを変換中...",
                description=f"ファイル: `{attachment.filename}`\n音声形式に変換しています...",
                color=discord.Color.gold()
            )
            await message.edit(embed=embed)
            
            try:
                # FFmpegで変換
                subprocess.run([
                    'ffmpeg', '-y', '-i', original_path, 
                    '-vn', '-ar', '44100', '-ac', '2', '-ab', '192k', '-f', 'mp3',
                    output_path
                ], check=True, timeout=300)
                
                if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                    logger.info(f"ファイル変換成功: {output_path} ({os.path.getsize(output_path)} バイト)")
                    
                    # データ作成
                    data = {
                        'title': os.path.splitext(attachment.filename)[0],
                        'url': attachment.url,
                        'webpage_url': attachment.url,
                        'duration': None,  # 不明
                        'uploader': requester.display_name if requester else None,
                        'uploader_url': None,
                        'view_count': None,
                        'like_count': None,
                        '__filename': output_path,
                        'requester': requester,
                        'source_type': 'file',
                        'original_query': attachment.url,
                        'id': f"file_{timestamp}"
                    }
                    
                    embed = discord.Embed(
                        title=f"{EMOJI['success']} ファイル変換完了",
                        description=f"ファイル: `{attachment.filename}`\n音声形式への変換が完了しました。",
                        color=discord.Color.green()
                    )
                    await message.edit(embed=embed)
                    
                    # 音声ソース作成
                    source = discord.FFmpegPCMAudio(output_path, **ffmpeg_options)
                    transformed_source = discord.PCMVolumeTransformer(source, volume=0.5)
                    return cls(transformed_source, data=data)
                else:
                    logger.error(f"ファイル変換に失敗しました: {output_path}")
                    embed = discord.Embed(
                        title=f"{EMOJI['error']} 変換エラー",
                        description="ファイルの変換に失敗しました。ファイル形式を確認してください。",
                        color=discord.Color.red()
                    )
                    await message.edit(embed=embed)
                    raise FileNotFoundError("ファイル変換に失敗しました")
            except (subprocess.SubprocessError, subprocess.TimeoutExpired) as e:
                logger.error(f"FFmpegによる変換中にエラーが発生しました: {e}")
                embed = discord.Embed(
                    title=f"{EMOJI['error']} 変換エラー",
                    description=f"ファイルの変換中にエラーが発生しました: {str(e)}",
                    color=discord.Color.red()
                )
                await message.edit(embed=embed)
                raise e
            
        except Exception as e:
            logger.error(f"添付ファイル処理エラー: {str(e)}")
            traceback.print_exc()
            embed = discord.Embed(
                title=f"{EMOJI['error']} エラー",
                description=f"添付ファイルの処理中にエラーが発生しました: {str(e)}",
                color=discord.Color.red()
            )
            await message.edit(embed=embed)
            raise e

    @classmethod
    async def recreate(cls, source, message=None):
        try:
            logger.info(f"音源再作成: {source.title}")
            return await cls.from_url(source.original_query or source.webpage_url, message=message, requester=source.requester)
        except Exception as e:
            logger.error(f"再作成エラー: {e}")
            if message:
                embed = discord.Embed(
                    title=f"{EMOJI['error']} 再作成エラー",
                    description=f"曲の再作成中にエラーが発生しました: {str(e)}",
                    color=discord.Color.red()
                )
                await message.edit(embed=embed)
            raise e

    def cleanup(self):
        try:
            if self._cleanup_done:
                return
            
            super().cleanup()
            self._cleanup_done = True
            logger.info(f"音源クリーンアップ: {self.title}")
        except Exception as e:
            logger.error(f"クリーンアップエラー: {e}")

    def create_embed(self):
        source_emoji = EMOJI['queue']
        if self.source_type == 'spotify':
            source_emoji = EMOJI['spotify']
        elif self.source_type == 'soundcloud':
            source_emoji = EMOJI['soundcloud']
        elif self.source_type == 'youtube':
            source_emoji = EMOJI['youtube']
        elif self.source_type == 'niconico':
            source_emoji = EMOJI['niconico']
        elif self.source_type == 'twitch':
            source_emoji = EMOJI['twitch']
        elif self.source_type == 'pornhub':
            source_emoji = EMOJI['pornhub']
        elif self.source_type == 'search':
            source_emoji = EMOJI['search']
        elif self.source_type == 'file':
            source_emoji = EMOJI['file']
        
        embed = discord.Embed(
            title=f"{source_emoji} 再生中",
            description=f"[{self.title}]({self.webpage_url})",
            color=discord.Color.green()
        )
        
        if self.thumbnail:
            embed.set_thumbnail(url=self.thumbnail)
        
        if self.uploader:
            embed.add_field(name="アップロード者", value=f"[{self.uploader}]({self.uploader_url})" if self.uploader_url else self.uploader, inline=True)
        
        if self.duration:
            minutes, seconds = divmod(self.duration, 60)
            hours, minutes = divmod(minutes, 60)
            if hours > 0:
                duration = f"{hours}時間{minutes}分{seconds}秒"
            else:
                duration = f"{minutes}分{seconds}秒"
            embed.add_field(name="再生時間", value=duration, inline=True)
        
        if self.view_count:
            embed.add_field(name="再生回数", value=f"{self.view_count:,}", inline=True)
            
        if self.like_count:
            embed.add_field(name="高評価数", value=f"{self.like_count:,}", inline=True)
            
        if self.requester:
            embed.add_field(name="リクエスト", value=self.requester.mention, inline=True)
        
        return embed

class TTSSource(discord.PCMVolumeTransformer):
    def __init__(self, source, *, filename, text, author=None, volume=0.5):
        super().__init__(source, volume)
        self.filename = filename
        self.text = text
        self.author = author
        self._cleanup_done = False
        logger.info(f"TTS音源作成: {text[:30]}... - {filename}")

    @classmethod
    async def from_text(cls, text, author=None):
        if len(text) > 200:
            text = text[:197] + "..."
        
        if author:
            display_text = f"{author}さん: {text}"
        else:
            display_text = text
        
        timestamp = int(time.time())
        filename = os.path.join(TTS_DIR, f"tts_{timestamp}_{hash(text) % 10000}.mp3")
        
        try:
            def _create_tts():
                try:
                    logger.info(f"TTS生成開始: {display_text[:30]}...")
                    tts = gTTS(text=display_text, lang='ja', slow=False)
                    tts.save(filename)
                    logger.info(f"TTS生成完了: {filename}")
                    return filename
                except (gtts.tts.gTTSError, IOError, OSError) as e:
                    logger.error(f"TTS生成エラー: {e}")
                    raise e
            
            try:
                await asyncio.to_thread(_create_tts)
                
                if not os.path.exists(filename) or os.path.getsize(filename) == 0:
                    logger.error("TTSファイルが正常に生成されませんでした")
                    raise FileNotFoundError("TTSファイルが正常に生成されませんでした")
                
                try:
                    tts_ffmpeg_options = {
                        'options': '-vn -loglevel warning',
                        'before_options': '-nostdin -hide_banner',
                    }
                    source = discord.FFmpegPCMAudio(filename, **tts_ffmpeg_options)
                    return cls(source, filename=filename, text=text, author=author)
                except Exception as e:
                    logger.error(f"音声ソース作成エラー: {e}")
                    raise e
            except Exception as e:
                logger.error(f"TTS生成実行エラー: {e}")
                raise e
            
        except Exception as e:
            logger.error(f"TTS生成エラー: {str(e)}")
            traceback.print_exc()
            raise e

    def cleanup(self):
        try:
            if self._cleanup_done:
                return
            
            super().cleanup()
            self._cleanup_done = True
            
            if self.filename and os.path.exists(self.filename):
                try:
                    os.remove(self.filename)
                    logger.info(f"TTS再生終了後にファイルを削除しました: {self.filename}")
                except (PermissionError, OSError) as e:
                    logger.error(f"TTSファイル削除エラー: {e}")
        except Exception as e:
            logger.error(f"TTSクリーンアップエラー: {e}")

class MusicPlayer:
    def __init__(self, ctx):
        self.bot = ctx.bot
        self.guild = ctx.guild
        self.channel = ctx.channel
        self.cog = ctx.cog

        self.queue = asyncio.Queue()
        self.next = asyncio.Event()

        self.np = None
        self.volume = 0.5
        self.current = None
        self.loop = False
        self._queue = []
        self.queue_empty_notified = True
        self.error_count = 0
        self.max_errors = 3
        self.track_ids = set()
        self.playing = False

        logger.info(f"MusicPlayerインスタンス作成: サーバー {ctx.guild.name} ({ctx.guild.id})")
        self.player_task = asyncio.create_task(self.player_loop())

    async def player_loop(self):
        await self.bot.wait_until_ready()

        while not self.bot.is_closed():
            self.next.clear()

            try:
                if not self.queue.empty():
                    self.queue_empty_notified = False
                
                if self.queue.empty() and not self.current and not self.queue_empty_notified and self._queue:
                    try:
                        logger.info(f"キュー終了: サーバー {self.guild.name} ({self.guild.id})")
                        embed = discord.Embed(
                            title=f"{EMOJI['queue']} キュー終了",
                            description="すべての曲の再生が終了しました。新しい曲を追加するには `r!play` コマンドを使用してください。",
                            color=discord.Color.blue()
                        )
                        await self.channel.send(embed=embed)
                        self.queue_empty_notified = True
                        self._queue = []
                        self.track_ids.clear()
                    except (discord.HTTPException, discord.Forbidden) as e:
                        logger.error(f"キュー終了メッセージ送信エラー: {e}")

                try:
                    async with timeout(86400):
                        source = await self.queue.get()
                        logger.info(f"キューから取得: {source.title}")
                except asyncio.TimeoutError:
                    continue
                except asyncio.CancelledError:
                    logger.warning("プレイヤーループがキャンセルされました")
                    break
                except Exception as e:
                    logger.error(f"キュー取得エラー: {e}")
                    continue
                
                if not isinstance(source, YTDLSource):
                    logger.warning(f"無効なソースタイプ: {type(source)}")
                    continue
                
                self.current = source
                self.error_count = 0
                
                try:
                    if self.guild.voice_client is None:
                        try:
                            logger.warning("ボイスクライアントが見つかりません")
                            embed = discord.Embed(
                                title=f"{EMOJI['error']} エラー",
                                description="ボイスクライアントが見つかりません。もう一度コマンドを実行してください。",
                                color=discord.Color.red()
                            )
                            await self.channel.send(embed=embed)
                        except (discord.HTTPException, discord.Forbidden) as e:
                            logger.error(f"ボイスクライアントエラーメッセージ送信エラー: {e}")
                        self.next.set()
                        continue
                    
                    def after_callback(e):
                        if e:
                            logger.error(f"再生エラー: {e}")
                            self.error_count += 1
                            if self.error_count >= self.max_errors:
                                asyncio.run_coroutine_threadsafe(
                                    self.send_error_message(f"連続して再生エラーが発生しました: {e}"), 
                                    self.bot.loop
                                )
                        else:
                            logger.info(f"再生終了: {self.current.title if self.current else 'Unknown'}")
                        self.playing = False
                        asyncio.run_coroutine_threadsafe(self.next.set(), self.bot.loop)
                    
                    try:
                        if not os.path.exists(source.filename):
                            logger.error(f"再生前にファイルが見つかりません: {source.filename}")
                            raise FileNotFoundError(f"再生前にファイルが見つかりません: {source.filename}")
                        
                        file_size = os.path.getsize(source.filename)
                        if file_size == 0:
                            logger.error(f"再生前にファイルサイズが0です: {source.filename}")
                            raise FileNotFoundError(f"再生前にファイルサイズが0です: {source.filename}")
                        
                        logger.info(f"再生開始: {source.title}, ファイル: {source.filename}, サイズ: {file_size} バイト")
                        
                        self.playing = True
                        
                        self.guild.voice_client.play(source, after=after_callback)
                        source.volume = self.volume
                        
                        await asyncio.sleep(0.5)
                    except Exception as e:
                        logger.error(f"音声再生開始エラー: {e}")
                        traceback.print_exc()
                        try:
                            embed = discord.Embed(
                                title=f"{EMOJI['error']} 再生エラー",
                                description=f"音声の再生開始中にエラーが発生しました: {str(e)}",
                                color=discord.Color.red()
                            )
                            await self.channel.send(embed=embed)
                        except (discord.HTTPException, discord.Forbidden) as e:
                            logger.error(f"再生エラーメッセージ送信エラー: {e}")
                        self.next.set()
                        continue
                    
                    try:
                        self.np = await self.channel.send(embed=source.create_embed())
                        logger.info(f"再生中メッセージを送信: {source.title}")
                    except (discord.HTTPException, discord.Forbidden) as e:
                        logger.error(f"再生中メッセージ送信エラー: {e}")
                        self.np = None
                    
                    try:
                        await self.next.wait()
                    except asyncio.CancelledError:
                        logger.warning("次の曲待機がキャンセルされました")
                        break
                    
                    if self.loop and self.current:
                        try:
                            logger.info(f"ループ再生: {self.current.title}")
                            looped_source = await YTDLSource.recreate(self.current, message=self.np)
                            await self.queue.put(looped_source)
                            self._queue.append(looped_source)
                        except Exception as e:
                            logger.error(f"ループ再生エラー: {e}")
                            try:
                                embed = discord.Embed(
                                    title=f"{EMOJI['error']} エラー",
                                    description=f"ループ再生中にエラーが発生しました: {str(e)}",
                                    color=discord.Color.red()
                                )
                                await self.channel.send(embed=embed)
                            except (discord.HTTPException, discord.Forbidden) as e:
                                logger.error(f"ループエラーメッセージ送信エラー: {e}")
                    
                    try:
                        if self.np:
                            await self.np.delete()
                    except (discord.HTTPException, discord.NotFound):
                        pass
                    
                    self.np = None
                    
                    if self.current:
                        try:
                            self.current.cleanup()
                        except Exception as e:
                            logger.error(f"ソースクリーンアップエラー: {e}")
                    
                    if hasattr(source, 'id') and source.id in self.track_ids:
                        self.track_ids.remove(source.id)
                    
                    if self._queue and self.current in self._queue:
                        self._queue.remove(self.current)
                    
                    self.current = None
                    
                except VoiceConnectionError as e:
                    logger.error(f"ボイス接続エラー: {e}")
                    try:
                        embed = discord.Embed(
                            title=f"{EMOJI['error']} 接続エラー",
                            description=f"ボイスチャンネルへの接続中にエラーが発生しました: {str(e)}",
                            color=discord.Color.red()
                        )
                        await self.channel.send(embed=embed)
                    except (discord.HTTPException, discord.Forbidden) as e:
                        logger.error(f"接続エラーメッセージ送信エラー: {e}")
                    self.next.set()
                    
                except Exception as e:
                    logger.error(f"再生中にエラーが発生しました: {str(e)}")
                    traceback.print_exc()
                    try:
                        embed = discord.Embed(
                            title=f"{EMOJI['error']} エラー",
                            description=f"再生中にエラーが発生しました: {str(e)}",
                            color=discord.Color.red()
                        )
                        await self.channel.send(embed=embed)
                    except (discord.HTTPException, discord.Forbidden) as e:
                        logger.error(f"再生エラーメッセージ送信エラー: {e}")
                    self.next.set()
            except Exception as e:
                logger.error(f"player_loopでエラーが発生しました: {str(e)}")
                traceback.print_exc()
                await asyncio.sleep(5)
                continue

    async def add_song(self, source):
        await self.queue.put(source)
        self._queue.append(source)
        if hasattr(source, 'id'):
            self.track_ids.add(source.id)
        logger.info(f"キューに追加: {source.title}")

    async def send_error_message(self, error_text):
        try:
            embed = discord.Embed(
                title=f"{EMOJI['error']} 連続エラー",
                description=error_text,
                color=discord.Color.red()
            )
            await self.channel.send(embed=embed)
            self.error_count = 0
        except (discord.HTTPException, discord.Forbidden) as e:
            logger.error(f"エラーメッセージ送信エラー: {e}")

    def play_next_song(self, error=None):
        if error:
            logger.error(f"再生エラー: {error}")
        
        self.next.set()
            
    def cleanup(self):
        try:
            self.queue.clear()
        except AttributeError:
            pass
        if self.guild.voice_client:
            self.guild.voice_client.stop()

class Music(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.players = {}
        self.cleanup_task = None
    
    async def cog_load(self):
        self.cleanup_task = asyncio.create_task(self.periodic_cleanup())
        
    async def periodic_cleanup(self):
        while not self.bot.is_closed():
            try:
                cleanup_old_files(max_age_hours=24)
            except Exception as e:
                logger.error(f"定期クリーンアップエラー: {e}")
            await asyncio.sleep(3600)

    async def cleanup(self, guild):
        try:
            if guild.voice_client:
                await guild.voice_client.disconnect()
        except (AttributeError, discord.HTTPException) as e:
            logger.error(f"ボイス切断エラー: {e}")
            
        try:
            if guild.id in self.players:
                del self.players[guild.id]
        except KeyError:
            pass
            
    def get_player(self, ctx):
        try:
            player = self.players[ctx.guild.id]
        except KeyError:
            player = MusicPlayer(ctx)
            self.players[ctx.guild.id] = player
            
        return player
        
    @commands.command(name='join', aliases=['j'])
    async def join(self, ctx):
        try:
            if ctx.voice_client is not None:
                embed = discord.Embed(
                    title=f"{EMOJI['error']} エラー",
                    description="すでにボイスチャンネルに参加しています。",
                    color=discord.Color.red()
                )
                return await ctx.send(embed=embed)
                
            if ctx.author.voice:
                try:
                    await ctx.author.voice.channel.connect()
                    embed = discord.Embed(
                        title=f"{EMOJI['success']} ボイスチャンネル参加",
                        description=f"{ctx.author.voice.channel.name}に参加しました。",
                        color=discord.Color.blue()
                    )
                    await ctx.send(embed=embed)
                except (discord.ClientException, discord.HTTPException) as e:
                    embed = discord.Embed(
                        title=f"{EMOJI['error']} 接続エラー",
                        description=f"ボイスチャンネルへの接続中にエラーが発生しました: {str(e)}",
                        color=discord.Color.red()
                    )
                    await ctx.send(embed=embed)
            else:
                embed = discord.Embed(
                    title=f"{EMOJI['error']} エラー",
                    description="あなたはボイスチャンネルに参加していません。",
                    color=discord.Color.red()
                )
                await ctx.send(embed=embed)
        except Exception as e:
            logger.error(f"joinコマンドエラー: {e}")
            embed = discord.Embed(
                title=f"{EMOJI['error']} エラー",
                description=f"予期せぬエラーが発生しました: {str(e)}",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)

    @commands.command(name='play', aliases=['p'])
    async def play(self, ctx, *, query=None):
        try:
            # 添付ファイルの確認
            if ctx.message.attachments and len(ctx.message.attachments) > 0:
                attachment = ctx.message.attachments[0]
                
                if ctx.voice_client is None:
                    if ctx.author.voice:
                        try:
                            await ctx.author.voice.channel.connect()
                            embed = discord.Embed(
                                title=f"{EMOJI['success']} ボイスチャンネル参加",
                                description=f"{ctx.author.voice.channel.name}に参加しました。",
                                color=discord.Color.blue()
                            )
                            await ctx.send(embed=embed)
                        except (discord.ClientException, discord.HTTPException) as e:
                            embed = discord.Embed(
                                title=f"{EMOJI['error']} 接続エラー",
                                description=f"ボイスチャンネルへの接続中にエラーが発生しました: {str(e)}",
                                color=discord.Color.red()
                            )
                            await ctx.send(embed=embed)
                            return
                    else:
                        embed = discord.Embed(
                            title=f"{EMOJI['error']} エラー",
                            description="あなたはボイスチャンネルに参加していません。",
                            color=discord.Color.red()
                        )
                        return await ctx.send(embed=embed)
                
                loading_embed = discord.Embed(
                    title=f"{EMOJI['file']} 添付ファイルを処理中...",
                    description=f"添付ファイルを処理しています...",
                    color=discord.Color.gold()
                )
                message = await ctx.send(embed=loading_embed)
                
                try:
                    player = self.get_player(ctx)
                    source = await YTDLSource.from_attachment(attachment, message=message, requester=ctx.author)
                    
                    await player.add_song(source)
                    
                    queue_embed = discord.Embed(
                        title=f"{EMOJI['file']} キューに追加",
                        description=f"添付ファイル `{attachment.filename}` をキューに追加しました。",
                        color=discord.Color.blue()
                    )
                    
                    queue_embed.add_field(name="ファイルサイズ", value=f"{attachment.size / 1024 / 1024:.2f} MB", inline=True)
                    queue_embed.add_field(name="リクエスト", value=ctx.author.mention, inline=True)
                    
                    queue_position = len(player._queue)
                    if queue_position > 1:
                        queue_embed.add_field(name="キュー位置", value=f"{queue_position}番目", inline=True)
                        
                    await message.edit(embed=queue_embed)
                    return
                    
                except Exception as e:
                    logger.error(f"添付ファイル処理エラー: {e}")
                    traceback.print_exc()
                    error_embed = discord.Embed(
                        title=f"{EMOJI['error']} エラー",
                        description=f"添付ファイルの処理中にエラーが発生しました: {str(e)}",
                        color=discord.Color.red()
                    )
                    await message.edit(embed=error_embed)
                    return
            
            # 通常のURL/検索クエリ処理
            if query is None:
                embed = discord.Embed(
                    title=f"{EMOJI['error']} エラー",
                    description="再生する曲のURLまたは検索キーワードを指定してください。",
                    color=discord.Color.red()
                )
                return await ctx.send(embed=embed)
                
            if ctx.voice_client is None:
                if ctx.author.voice:
                    try:
                        await ctx.author.voice.channel.connect()
                        embed = discord.Embed(
                            title=f"{EMOJI['success']} ボイスチャンネル参加",
                            description=f"{ctx.author.voice.channel.name}に参加しました。",
                            color=discord.Color.blue()
                        )
                        await ctx.send(embed=embed)
                    except (discord.ClientException, discord.HTTPException) as e:
                        embed = discord.Embed(
                            title=f"{EMOJI['error']} 接続エラー",
                            description=f"ボイスチャンネルへの接続中にエラーが発生しました: {str(e)}",
                            color=discord.Color.red()
                        )
                        await ctx.send(embed=embed)
                        return
                else:
                    embed = discord.Embed(
                        title=f"{EMOJI['error']} エラー",
                        description="あなたはボイスチャンネルに参加していません。",
                        color=discord.Color.red()
                    )
                    return await ctx.send(embed=embed)
            
            loading_embed = discord.Embed(
                title=f"{EMOJI['queue']} 音楽を準備中...",
                description=f"音楽情報を取得しています...",
                color=discord.Color.gold()
            )
            message = await ctx.send(embed=loading_embed)
            
            try:
                player = self.get_player(ctx)
                
                is_playlist = False
                if 'spotify.com' in query.lower() and ('playlist' in query.lower() or 'album' in query.lower()):
                    is_playlist = True
                elif 'youtube.com' in query.lower() and 'list=' in query.lower():
                    is_playlist = True
                elif 'soundcloud.com' in query.lower() and '/sets/' in query.lower():
                    is_playlist = True
                
                if is_playlist:
                    sources = await YTDLSource.from_url(query, stream=False, message=message, requester=ctx.author, playlist=True)
                    
                    if isinstance(sources, list) and sources:
                        first_source = sources[0]
                        await player.add_song(first_source)
                        
                        for source in sources[1:]:
                            await player.add_song(source)
                        
                        source_emoji = EMOJI['queue']
                        if first_source.source_type == 'spotify':
                            source_emoji = EMOJI['spotify']
                        elif first_source.source_type == 'soundcloud':
                            source_emoji = EMOJI['soundcloud']
                        elif first_source.source_type == 'youtube':
                            source_emoji = EMOJI['youtube']
                        
                        playlist_embed = discord.Embed(
                            title=f"{source_emoji} プレイリストを追加",
                            description=f"プレイリストから{len(sources)}曲をキューに追加しました。",
                            color=discord.Color.blue()
                        )
                        
                        if first_source.thumbnail:
                            playlist_embed.set_thumbnail(url=first_source.thumbnail)
                        
                        playlist_embed.add_field(name="最初の曲", value=f"[{first_source.title}]({first_source.webpage_url})", inline=False)
                        playlist_embed.add_field(name="リクエスト", value=ctx.author.mention, inline=True)
                        
                        await message.edit(embed=playlist_embed)
                    else:
                        embed = discord.Embed(
                            title=f"{EMOJI['error']} プレイリストエラー",
                            description="プレイリストから曲を読み込めませんでした。",
                            color=discord.Color.red()
                        )
                        await message.edit(embed=embed)
                else:
                    source = await YTDLSource.from_url(query, stream=False, message=message, requester=ctx.author)
                
                    await player.add_song(source)
                    
                    source_emoji = EMOJI['queue']
                    if source.source_type == 'spotify':
                        source_emoji = EMOJI['spotify']
                    elif source.source_type == 'soundcloud':
                        source_emoji = EMOJI['soundcloud']
                    elif source.source_type == 'youtube':
                        source_emoji = EMOJI['youtube']
                    elif source.source_type == 'niconico':
                        source_emoji = EMOJI['niconico']
                    elif source.source_type == 'twitch':
                        source_emoji = EMOJI['twitch']
                    elif source.source_type == 'pornhub':
                        source_emoji = EMOJI['pornhub']
                    elif source.source_type == 'search':
                        source_emoji = EMOJI['search']
                    
                    queue_embed = discord.Embed(
                        title=f"{source_emoji} キューに追加",
                        description=f"[{source.title}]({source.webpage_url})をキューに追加しました。",
                        color=discord.Color.blue()
                    )
                    
                    if source.thumbnail:
                        queue_embed.set_thumbnail(url=source.thumbnail)
                    
                    if source.uploader:
                        queue_embed.add_field(name="アップロード者", value=f"[{source.uploader}]({source.uploader_url})", inline=True)
                    
                    if source.duration:
                        minutes, seconds = divmod(source.duration, 60)
                        hours, minutes = divmod(minutes, 60)
                        if hours > 0:
                            duration = f"{hours}時間{minutes}分{seconds}秒"
                        else:
                            duration = f"{minutes}分{seconds}秒"
                        queue_embed.add_field(name="再生時間", value=duration, inline=True)
                        
                    queue_embed.add_field(name="リクエスト", value=ctx.author.mention, inline=True)
                    
                    queue_position = len(player._queue)
                    if queue_position > 1:
                        queue_embed.add_field(name="キュー位置", value=f"{queue_position}番目", inline=True)
                        
                    await message.edit(embed=queue_embed)
                
            except DRMProtectedError as e:
                error_embed = discord.Embed(
                    title=f"{EMOJI['error']} DRMエラー",
                    description=str(e),
                    color=discord.Color.red()
                )
                await message.edit(embed=error_embed)
                
            except NetworkError as e:
                error_embed = discord.Embed(
                    title=f"{EMOJI['error']} ネットワークエラー",
                    description=f"ネットワーク接続中にエラーが発生しました: {str(e)}",
                    color=discord.Color.red()
                )
                await message.edit(embed=error_embed)
                
            except FileNotFoundError as e:
                error_embed = discord.Embed(
                    title=f"{EMOJI['error']} ファイルエラー",
                    description=f"ダウンロードしたファイルが見つかりませんでした。もう一度お試しください。",
                    color=discord.Color.red()
                )
                await message.edit(embed=error_embed)
                
            except Exception as e:
                logger.error(f"r!playコマンドでエラー発生: {str(e)}")
                traceback.print_exc(file=sys.stdout)
                
                error_embed = discord.Embed(
                    title=f"{EMOJI['error']} エラー",
                    description=f"エラーが発生しました: {str(e)}",
                    color=discord.Color.red()
                )
                await message.edit(embed=error_embed)
        except Exception as e:
            logger.error(f"playコマンド実行エラー: {e}")
            traceback.print_exc()
            try:
                embed = discord.Embed(
                    title=f"{EMOJI['error']} 予期せぬエラー",
                    description=f"予期せぬエラーが発生しました: {str(e)}",
                    color=discord.Color.red()
                )
                await ctx.send(embed=embed)
            except:
                pass

    @commands.command(name='queue', aliases=['q'])
    async def queue(self, ctx, page: int = 1):
        try:
            player = self.get_player(ctx)
        
            if player.current is None and not player._queue:
                embed = discord.Embed(
                    title=f"{EMOJI['queue']} キュー",
                    description="現在キューに曲はありません。",
                    color=discord.Color.blue()
                )
                return await ctx.send(embed=embed)
        
            queue_list_without_current = [track for track in player._queue if player.current is None or track.id != player.current.id]
        
            items_per_page = 10
            queue_length = len(queue_list_without_current)
            pages = max(1, math.ceil(queue_length / items_per_page))
        
            if page < 1 or page > pages:
                page = 1
        
            start = (page - 1) * items_per_page
            end = min(start + items_per_page, queue_length)
        
            queue_list = ""
        
            if player.current:
                current_duration = ""
                if player.current.duration:
                    minutes, seconds = divmod(player.current.duration, 60)
                    hours, minutes = divmod(minutes, 60)
                    if hours > 0:
                        current_duration = f" ({hours}時間{minutes}分{seconds}秒)"
                    else:
                        current_duration = f" ({minutes}分{seconds}秒)"
            
                source_emoji = EMOJI['queue']
                if player.current.source_type == 'spotify':
                    source_emoji = EMOJI['spotify']
                elif player.current.source_type == 'soundcloud':
                    source_emoji = EMOJI['soundcloud']
                elif player.current.source_type == 'youtube':
                    source_emoji = EMOJI['youtube']
                elif player.current.source_type == 'niconico':
                    source_emoji = EMOJI['niconico']
                elif player.current.source_type == 'twitch':
                    source_emoji = EMOJI['twitch']
                elif player.current.source_type == 'pornhub':
                    source_emoji = EMOJI['pornhub']
                elif player.current.source_type == 'search':
                    source_emoji = EMOJI['search']
                elif player.current.source_type == 'file':
                    source_emoji = EMOJI['file']
                
                requester = f"リクエスト: {player.current.requester.mention}" if player.current.requester else ""
                queue_list += f"**{source_emoji} 現在再生中:**\n[{player.current.title}]({player.current.webpage_url}){current_duration}\n{requester}\n\n"
        
            if queue_list_without_current:
                queue_list += "**次の曲:**\n"
                for i, track in enumerate(queue_list_without_current[start:end], start=start + 1):
                    duration = ""
                    if track.duration:
                        minutes, seconds = divmod(track.duration, 60)
                        hours, minutes = divmod(minutes, 60)
                        if hours > 0:
                            duration = f" ({hours}時間{minutes}分{seconds}秒)"
                        else:
                            duration = f" ({minutes}分{seconds}秒)"
                
                    source_emoji = EMOJI['queue']
                    if track.source_type == 'spotify':
                        source_emoji = EMOJI['spotify']
                    elif track.source_type == 'soundcloud':
                        source_emoji = EMOJI['soundcloud']
                    elif track.source_type == 'youtube':
                        source_emoji = EMOJI['youtube']
                    elif track.source_type == 'niconico':
                        source_emoji = EMOJI['niconico']
                    elif track.source_type == 'twitch':
                        source_emoji = EMOJI['twitch']
                    elif track.source_type == 'pornhub':
                        source_emoji = EMOJI['pornhub']
                    elif track.source_type == 'search':
                        source_emoji = EMOJI['search']
                    elif track.source_type == 'file':
                        source_emoji = EMOJI['file']
                
                    requester = f"リクエスト: {track.requester.mention}" if track.requester else ""
                    queue_list += f"**{i}.** {source_emoji} [{track.title}]({track.webpage_url}){duration}\n{requester}\n"
        
            embed = discord.Embed(
                title=f"{EMOJI['queue']} 再生キュー",
                description=queue_list,
                color=discord.Color.blue()
            )
        
            if pages > 1:
                embed.set_footer(text=f"ページ {page}/{pages} | r!queue <ページ番号> でページを切り替えられます")
        
            await ctx.send(embed=embed)
        except Exception as e:
            logger.error(f"queueコマンドエラー: {e}")
            traceback.print_exc()
            embed = discord.Embed(
                title=f"{EMOJI['error']} エラー",
                description=f"キュー表示中にエラーが発生しました: {str(e)}",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)
                
    @commands.command(name='stop', aliases=['s'])
    async def stop(self, ctx):
        try:
            if ctx.voice_client is None:
                embed = discord.Embed(
                    title=f"{EMOJI['error']} エラー",
                    description="ボイスチャンネルに参加していません。",
                    color=discord.Color.red()
                )
                return await ctx.send(embed=embed)
                
            try:
                await self.cleanup(ctx.guild)
                embed = discord.Embed(
                    title=f"{EMOJI['stop']} 停止",
                    description="再生を停止し、ボイスチャンネルから切断しました。",
                    color=discord.Color.blue()
                )
                await ctx.send(embed=embed)
            except Exception as e:
                embed = discord.Embed(
                    title=f"{EMOJI['error']} 停止エラー",
                    description=f"停止処理中にエラーが発生しました: {str(e)}",
                    color=discord.Color.red()
                )
                await ctx.send(embed=embed)
        except Exception as e:
            logger.error(f"stopコマンドエラー: {e}")
            embed = discord.Embed(
                title=f"{EMOJI['error']} エラー",
                description=f"予期せぬエラーが発生しました: {str(e)}",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)
        
    @commands.command(name='pause', aliases=['ps'])
    async def pause(self, ctx):
        try:
            if ctx.voice_client is None:
                embed = discord.Embed(
                    title=f"{EMOJI['error']} エラー",
                    description="ボイスチャンネルに参加していません。",
                    color=discord.Color.red()
                )
                return await ctx.send(embed=embed)
                
            if ctx.voice_client.is_playing():
                try:
                    ctx.voice_client.pause()
                    embed = discord.Embed(
                        title=f"{EMOJI['pause']} 一時停止",
                        description="再生を一時停止しました。",
                        color=discord.Color.blue()
                    )
                    await ctx.send(embed=embed)
                except Exception as e:
                    embed = discord.Embed(
                        title=f"{EMOJI['error']} 一時停止エラー",
                        description=f"一時停止処理中にエラーが発生しました: {str(e)}",
                        color=discord.Color.red()
                    )
                    await ctx.send(embed=embed)
            else:
                embed = discord.Embed(
                    title=f"{EMOJI['error']} エラー",
                    description="現在音楽は再生されていません。",
                    color=discord.Color.red()
                )
                await ctx.send(embed=embed)
        except Exception as e:
            logger.error(f"pauseコマンドエラー: {e}")
            embed = discord.Embed(
                title=f"{EMOJI['error']} エラー",
                description=f"予期せぬエラーが発生しました: {str(e)}",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)
            
    @commands.command(name='start', aliases=['st'])
    async def start(self, ctx):
        try:
            if ctx.voice_client is None:
                embed = discord.Embed(
                    title=f"{EMOJI['error']} エラー",
                    description="ボイスチャンネルに参加していません。",
                    color=discord.Color.red()
                )
                return await ctx.send(embed=embed)
                
            if ctx.voice_client.is_paused():
                try:
                    ctx.voice_client.resume()
                    embed = discord.Embed(
                        title=f"{EMOJI['play']} 再開",
                        description="再生を再開しました。",
                        color=discord.Color.blue()
                    )
                    await ctx.send(embed=embed)
                except Exception as e:
                    embed = discord.Embed(
                        title=f"{EMOJI['error']} 再開エラー",
                        description=f"再開処理中にエラーが発生しました: {str(e)}",
                        color=discord.Color.red()
                    )
                    await ctx.send(embed=embed)
            else:
                embed = discord.Embed(
                    title=f"{EMOJI['error']} エラー",
                    description="音楽は一時停止されていません。",
                    color=discord.Color.red()
                )
                await ctx.send(embed=embed)
        except Exception as e:
            logger.error(f"startコマンドエラー: {e}")
            embed = discord.Embed(
                title=f"{EMOJI['error']} エラー",
                description=f"予期せぬエラーが発生しました: {str(e)}",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)
            
    @commands.command(name='skip', aliases=['sk'])
    async def skip(self, ctx):
        try:
            if ctx.voice_client is None:
                embed = discord.Embed(
                    title=f"{EMOJI['error']} エラー",
                    description="ボイスチャンネルに参加していません。",
                    color=discord.Color.red()
                )
                return await ctx.send(embed=embed)
                
            if not ctx.voice_client.is_playing() and not ctx.voice_client.is_paused():
                embed = discord.Embed(
                    title=f"{EMOJI['error']} エラー",
                    description="現在音楽は再生されていません。",
                    color=discord.Color.red()
                )
                return await ctx.send(embed=embed)
                
            try:
                ctx.voice_client.stop()
                logger.info("スキップコマンドにより再生を停止しました")
            
                embed = discord.Embed(
                    title=f"{EMOJI['skip']} スキップ",
                    description="現在の曲をスキップしました。",
                    color=discord.Color.blue()
                )
                await ctx.send(embed=embed)
            except Exception as e:
                logger.error(f"スキップ処理エラー: {e}")
                embed = discord.Embed(
                    title=f"{EMOJI['error']} スキップエラー",
                    description=f"スキップ処理中にエラーが発生しました: {str(e)}",
                    color=discord.Color.red()
                )
                await ctx.send(embed=embed)
        except Exception as e:
            logger.error(f"skipコマンドエラー: {e}")
            traceback.print_exc()
            embed = discord.Embed(
                title=f"{EMOJI['error']} エラー",
                description=f"予期せぬエラーが発生しました: {str(e)}",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)

    @commands.command(name='skip5', aliases=['sk5', 'forward5', 'fw5'])
    async def skip_5(self, ctx):
        await self.seek_relative(ctx, 5)

    @commands.command(name='skip10', aliases=['sk10', 'forward10', 'fw10'])
    async def skip_10(self, ctx):
        await self.seek_relative(ctx, 10)

    @commands.command(name='skip30', aliases=['sk30', 'forward30', 'fw30'])
    async def skip_30(self, ctx):
        await self.seek_relative(ctx, 30)

    @commands.command(name='back5', aliases=['b5', 'rewind5', 'rw5'])
    async def back_5(self, ctx):
        await self.seek_relative(ctx, -5)

    @commands.command(name='back10', aliases=['b10', 'rewind10', 'rw10'])
    async def back_10(self, ctx):
        await self.seek_relative(ctx, -10)

    @commands.command(name='back30', aliases=['b30', 'rewind30', 'rw30'])
    async def back_30(self, ctx):
        await self.seek_relative(ctx, -30)

    async def seek_relative(self, ctx, seconds):
        try:
            if ctx.voice_client is None:
                embed = discord.Embed(
                    title=f"{EMOJI['error']} エラー",
                    description="ボイスチャンネルに参加していません。",
                    color=discord.Color.red()
                )
                return await ctx.send(embed=embed)
                
            if not ctx.voice_client.is_playing() and not ctx.voice_client.is_paused():
                embed = discord.Embed(
                    title=f"{EMOJI['error']} エラー",
                    description="現在音楽は再生されていません。",
                    color=discord.Color.red()
                )
                return await ctx.send(embed=embed)
            
            player = self.get_player(ctx)
            if not player.current:
                embed = discord.Embed(
                    title=f"{EMOJI['error']} エラー",
                    description="現在再生中の曲がありません。",
                    color=discord.Color.red()
                )
                return await ctx.send(embed=embed)
            
            if not hasattr(player.current, 'current_position'):
                player.current.current_position = 0
            
            new_position = player.current.current_position + seconds
            if new_position < 0:
                new_position = 0
            
            if player.current.duration and new_position > player.current.duration:
                new_position = player.current.duration
            
            current_source = player.current
            
            ctx.voice_client.stop()
            
            loading_embed = discord.Embed(
                title=f"{EMOJI['forward' if seconds > 0 else 'backward']} {'スキップ' if seconds > 0 else '巻き戻し'}中...",
                description=f"{'前方' if seconds > 0 else '後方'}に{abs(seconds)}秒{'スキップ' if seconds > 0 else '巻き戻し'}しています...",
                color=discord.Color.gold()
            )
            message = await ctx.send(embed=loading_embed)
            
            try:
                new_source = await YTDLSource.recreate(current_source, message=message)
                new_source.current_position = new_position
                
                player._queue.insert(0, new_source)
                await player.queue.put(new_source)
                
                minutes, seconds = divmod(new_position, 60)
                hours, minutes = divmod(minutes, 60)
                
                if hours > 0:
                    position_str = f"{hours}時間{minutes}分{seconds}秒"
                else:
                    position_str = f"{minutes}分{seconds}秒"
                
                embed = discord.Embed(
                    title=f"{EMOJI['forward' if seconds > 0 else 'backward']} {'スキップ' if seconds > 0 else '巻き戻し'}完了",
                    description=f"再生位置を{position_str}に移動しました。",
                    color=discord.Color.green()
                )
                await message.edit(embed=embed)
                
            except Exception as e:
                logger.error(f"シーク処理エラー: {e}")
                traceback.print_exc()
                
                embed = discord.Embed(
                    title=f"{EMOJI['error']} シークエラー",
                    description=f"再生位置の変更中にエラーが発生しました: {str(e)}",
                    color=discord.Color.red()
                )
                await message.edit(embed=embed)
                
                try:
                    original_source = await YTDLSource.recreate(current_source, message=message)
                    await player.queue.put(original_source)
                except Exception:
                    pass
                
        except Exception as e:
            logger.error(f"seekコマンドエラー: {e}")
            traceback.print_exc()
            embed = discord.Embed(
                title=f"{EMOJI['error']} エラー",
                description=f"予期せぬエラーが発生しました: {str(e)}",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)
        
    @commands.command(name='loop', aliases=['l'])
    async def loop(self, ctx):
        try:
            if ctx.voice_client is None:
                embed = discord.Embed(
                    title=f"{EMOJI['error']} エラー",
                    description="ボイスチャンネルに参加していません。",
                    color=discord.Color.red()
                )
                return await ctx.send(embed=embed)
                
            player = self.get_player(ctx)
            player.loop = not player.loop
            
            status = "有効" if player.loop else "無効"
            embed = discord.Embed(
                title=f"{EMOJI['loop']} ループ設定",
                description=f"ループ再生を{status}にしました。",
                color=discord.Color.blue()
            )
            await ctx.send(embed=embed)
        except Exception as e:
            logger.error(f"loopコマンドエラー: {e}")
            embed = discord.Embed(
                title=f"{EMOJI['error']} エラー",
                description=f"ループ設定中にエラーが発生しました: {str(e)}",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)
        
    @commands.command(name='resume', aliases=['r'])
    async def resume(self, ctx):
        try:
            if ctx.voice_client is None:
                embed = discord.Embed(
                    title=f"{EMOJI['error']} エラー",
                    description="ボイスチャンネルに参加していません。",
                    color=discord.Color.red()
                )
                return await ctx.send(embed=embed)
                
            if ctx.voice_client.is_paused():
                try:
                    ctx.voice_client.resume()
                    embed = discord.Embed(
                        title=f"{EMOJI['play']} 再開",
                        description="再生を再開しました。",
                        color=discord.Color.blue()
                    )
                    await ctx.send(embed=embed)
                except Exception as e:
                    embed = discord.Embed(
                        title=f"{EMOJI['error']} 再開エラー",
                        description=f"再開処理中にエラーが発生しました: {str(e)}",
                        color=discord.Color.red()
                    )
                    await ctx.send(embed=embed)
            else:
                embed = discord.Embed(
                    title=f"{EMOJI['error']} エラー",
                    description="音楽は一時停止されていません。",
                    color=discord.Color.red()
                )
                await ctx.send(embed=embed)
        except Exception as e:
            logger.error(f"resumeコマンドエラー: {e}")
            embed = discord.Embed(
                title=f"{EMOJI['error']} エラー",
                description=f"予期せぬエラーが発生しました: {str(e)}",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)
            
    @commands.command(name='cleanup', aliases=['cu'])
    async def cleanup_command(self, ctx):
        try:
            if ctx.author.id != 1276774559613325473:
                embed = discord.Embed(
                    title=f"{EMOJI['error']} 権限エラー",
                    description="このコマンドを実行する権限がありません。",
                    color=discord.Color.red()
                )
                return await ctx.send(embed=embed)
                
            try:
                for file_path in glob.glob(f"{DOWNLOAD_DIR}/*"):
                    try:
                        os.remove(file_path)
                    except (PermissionError, OSError) as e:
                        logger.error(f"ファイル削除エラー: {e}")
                
                for file_path in glob.glob(f"{TTS_DIR}/*"):
                    try:
                        os.remove(file_path)
                    except (PermissionError, OSError) as e:
                        logger.error(f"TTSファイル削除エラー: {e}")
                        
                for file_path in glob.glob(f"{ATTACHMENT_DIR}/*"):
                    try:
                        os.remove(file_path)
                    except (PermissionError, OSError) as e:
                        logger.error(f"添付ファイル削除エラー: {e}")
                
                embed = discord.Embed(
                    title=f"{EMOJI['success']} クリーンアップ完了",
                    description="ダウンロードディレクトリとTTSディレクトリを空にしました。",
                    color=discord.Color.green()
                )
                await ctx.send(embed=embed)
            except Exception as e:
                embed = discord.Embed(
                    title=f"{EMOJI['error']} エラー",
                    description=f"クリーンアップ中にエラーが発生しました: {str(e)}",
                    color=discord.Color.red()
                )
                await ctx.send(embed=embed)
        except Exception as e:
            logger.error(f"cleanupコマンドエラー: {e}")
            embed = discord.Embed(
                title=f"{EMOJI['error']} エラー",
                description=f"予期せぬエラーが発生しました: {str(e)}",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)
            
    @commands.command(name='ffmpeg', aliases=['ff'])
    async def ffmpeg_check(self, ctx):
        try:
            result = check_ffmpeg()
            if result:
                embed = discord.Embed(
                    title=f"{EMOJI['success']} FFmpeg確認",
                    description="FFmpegは正常にインストールされています。",
                    color=discord.Color.green()
                )
            else:
                embed = discord.Embed(
                    title=f"{EMOJI['error']} FFmpeg確認",
                    description="FFmpegがインストールされていないか、パスが通っていません。",
                    color=discord.Color.red()
                )
            await ctx.send(embed=embed)
        except Exception as e:
            logger.error(f"ffmpegコマンドエラー: {e}")
            embed = discord.Embed(
                title=f"{EMOJI['error']} エラー",
                description=f"FFmpeg確認中にエラーが発生しました: {str(e)}",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)
            
    @commands.command(name='reconnect', aliases=['rc'])
    async def reconnect_command(self, ctx):
        try:
            if ctx.voice_client is not None:
                voice_channel = ctx.voice_client.channel
                
                try:
                    await ctx.voice_client.disconnect()
                except (discord.HTTPException, discord.ClientException) as e:
                    logger.error(f"切断エラー: {e}")
                
                try:
                    await voice_channel.connect()
                    embed = discord.Embed(
                        title=f"{EMOJI['success']} 再接続完了",
                        description=f"{voice_channel.name}に再接続しました。",
                        color=discord.Color.green()
                    )
                    await ctx.send(embed=embed)
                except (discord.HTTPException, discord.ClientException) as e:
                    embed = discord.Embed(
                        title=f"{EMOJI['error']} 再接続エラー",
                        description=f"再接続中にエラーが発生しました: {str(e)}",
                        color=discord.Color.red()
                    )
                    await ctx.send(embed=embed)
            else:
                if ctx.author.voice:
                    try:
                        await ctx.author.voice.channel.connect()
                        embed = discord.Embed(
                            title=f"{EMOJI['success']} ボイスチャンネル参加",
                            description=f"{ctx.author.voice.channel.name}に参加しました。",
                            color=discord.Color.blue()
                        )
                        await ctx.send(embed=embed)
                    except (discord.HTTPException, discord.ClientException) as e:
                        embed = discord.Embed(
                            title=f"{EMOJI['error']} 接続エラー",
                            description=f"接続中にエラーが発生しました: {str(e)}",
                            color=discord.Color.red()
                        )
                        await ctx.send(embed=embed)
                else:
                    embed = discord.Embed(
                        title=f"{EMOJI['error']} エラー",
                        description="あなたはボイスチャンネルに参加していません。",
                        color=discord.Color.red()
                    )
                    await ctx.send(embed=embed)
        except Exception as e:
            logger.error(f"reconnectコマンドエラー: {e}")
            embed = discord.Embed(
                title=f"{EMOJI['error']} エラー",
                description=f"予期せぬエラーが発生しました: {str(e)}",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)

    @commands.command(name='togglekick', aliases=['tk'])
    async def toggle_kick(self, ctx):
        try:
            global kick_enabled
            kick_enabled = not kick_enabled
            status = "有効" if kick_enabled else "無効"
            
            status_emoji = EMOJI['success'] if kick_enabled else EMOJI['error']
            embed = discord.Embed(
                title=f"{status_emoji} キック機能設定",
                description=f"自動キック機能を{status}にしました。",
                color=discord.Color.blue()
            )
            await ctx.send(embed=embed)
        except Exception as e:
            logger.error(f"togglekickコマンドエラー: {e}")
            embed = discord.Embed(
                title=f"{EMOJI['error']} エラー",
                description=f"キック機能設定中にエラーが発生しました: {str(e)}",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)

    @commands.command(name='read')
    async def read_command(self, ctx):
        try:
            if ctx.voice_client is None:
                if ctx.author.voice:
                    try:
                        await ctx.author.voice.channel.connect()
                        embed = discord.Embed(
                            title=f"{EMOJI['success']} ボイスチャンネル参加",
                            description=f"{ctx.author.voice.channel.name}に参加しました。",
                            color=discord.Color.blue()
                        )
                        await ctx.send(embed=embed)
                    except (discord.HTTPException, discord.ClientException) as e:
                        embed = discord.Embed(
                            title=f"{EMOJI['error']} 接続エラー",
                            description=f"接続中にエラーが発生しました: {str(e)}",
                            color=discord.Color.red()
                        )
                        await ctx.send(embed=embed)
                        return
                else:
                    embed = discord.Embed(
                        title=f"{EMOJI['error']} エラー",
                        description="あなたはボイスチャンネルに参加していません。",
                        color=discord.Color.red()
                    )
                    return await ctx.send(embed=embed)
            
            if ctx.guild.id in reading_channels:
                reading_channels[ctx.guild.id]['active'] = True
                embed = discord.Embed(
                    title=f"{EMOJI['success']} 読み上げ再開",
                    description="読み上げを再開しました。",
                    color=discord.Color.green()
                )
                await ctx.send(embed=embed)
                return
            
            reading_channels[ctx.guild.id] = {
                'channel': ctx.channel.id,
                'active': True,
                'requester': ctx.author.id
            }
            
            embed = discord.Embed(
                title=f"{EMOJI['mic']} 読み上げ開始",
                description=f"このチャンネルのメッセージを読み上げます。\n停止するには `!read_stop` または `r!rs` コマンドを使用してください。",
                color=discord.Color.green()
            )
            await ctx.send(embed=embed)
        except Exception as e:
            logger.error(f"readコマンドエラー: {e}")
            embed = discord.Embed(
                title=f"{EMOJI['error']} エラー",
                description=f"読み上げ開始中にエラーが発生しました: {str(e)}",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)

    @commands.command(name='stfu', aliases=['shutup', 'rs'])
    async def stop_read_command(self, ctx):
        try:
            if ctx.guild.id in reading_channels and reading_channels[ctx.guild.id]['active']:
                reading_channels[ctx.guild.id]['active'] = False
                del reading_channels[ctx.guild.id]
                
                embed = discord.Embed(
                    title=f"{EMOJI['success']} 読み上げ停止",
                    description="読み上げを停止しました。",
                    color=discord.Color.blue()
                )
                await ctx.send(embed=embed)
            else:
                embed = discord.Embed(
                    title=f"{EMOJI['error']} エラー",
                    description="現在読み上げは行われていません。",
                    color=discord.Color.red()
                )
                await ctx.send(embed=embed)
        except Exception as e:
            logger.error(f"stop_readコマンドエラー: {e}")
            embed = discord.Embed(
                title=f"{EMOJI['error']} エラー",
                description=f"読み上げ停止中にエラーが発生しました: {str(e)}",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)
            
    @commands.command(name='commands', aliases=['cmd', 'help'])
    async def commands_list(self, ctx):
        try:
            embed = discord.Embed(
                title="コマンド一覧",
                description="以下のコマンドが使用できます。すべてのコマンドは `r!` プレフィックスで始まります。",
                color=discord.Color.blue()
            )
            
            music_commands = [
                f"{EMOJI['play']} `play (p) <URL/検索キーワード>` - 音楽を再生します。YouTubeやSpotify、SoundCloudなどに対応。",
                f"{EMOJI['queue']} `queue (q) [ページ番号]` - 再生キューを表示します。",
                f"{EMOJI['pause']} `pause (ps)` - 再生を一時停止します。",
                f"{EMOJI['play']} `start (st)` - 一時停止した再生を再開します。",
                f"{EMOJI['play']} `resume (r)` - 一時停止した再生を再開します。",
                f"{EMOJI['skip']} `skip (sk)` - 現在の曲をスキップします。",
                f"{EMOJI['forward']} `skip5 (sk5)` - 5秒前方にスキップします。",
                f"{EMOJI['forward']} `skip10 (sk10)` - 10秒前方にスキップします。",
                f"{EMOJI['forward']} `skip30 (sk30)` - 30秒前方にスキップします。",
                f"{EMOJI['backward']} `back5 (b5)` - 5秒後方に巻き戻します。",
                f"{EMOJI['backward']} `back10 (b10)` - 10秒後方に巻き戻します。",
                f"{EMOJI['backward']} `back30 (b30)` - 30秒後方に巻き戻します。",
                f"{EMOJI['loop']} `loop (l)` - ループ再生を切り替えます。",
                f"{EMOJI['stop']} `stop (s)` - 再生を停止し、ボイスチャンネルから切断します。"
            ]
            
            utility_commands = [
                f"{EMOJI['mic']} `read` - テキストチャンネルのメッセージを読み上げます。",
                f"{EMOJI['mic']} `stfu (rs)` - 読み上げを停止します。",
                f"{EMOJI['success']} `join (j)` - ボイスチャンネルに参加します。",
                f"{EMOJI['retry']} `reconnect (rc)` - ボイスチャンネルに再接続します。",
                f"{EMOJI['success']} `ffmpeg (ff)` - FFmpegの状態を確認します。",
                f"{EMOJI['success']} `commands (cmd, help)` - このコマンド一覧を表示します。"
            ]
            
            embed.add_field(name="音楽コマンド", value="\n".join(music_commands), inline=False)
            embed.add_field(name="ユーティリティコマンド", value="\n".join(utility_commands), inline=False)
            
            embed.set_footer(text="括弧内はコマンドの省略形です。")
            
            await ctx.send(embed=embed)
        except Exception as e:
            logger.error(f"commandsコマンドエラー: {e}")
            embed = discord.Embed(
                title=f"{EMOJI['error']} エラー",
                description=f"コマンド一覧表示中にエラーが発生しました: {str(e)}",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot:
            return
            
        if message.guild and message.guild.id in reading_channels and reading_channels[message.guild.id]['active']:
            if message.channel.id == reading_channels[message.guild.id]['channel']:
                if message.content.startswith('r!') or message.content.startswith('!'):
                    return
                    
                if message.guild.voice_client is None or not message.guild.voice_client.is_connected():
                    reading_channels[message.guild.id]['active'] = False
                    del reading_channels[message.guild.id]
                    return
                    
                if message.guild.voice_client.is_playing():
                    return
                    
                try:
                    text = message.content
                    if len(text) == 0 and len(message.attachments) > 0:
                        text = "添付ファイル"
                        
                    if len(text) > 0:
                        source = await TTSSource.from_text(text, message.author.display_name)
                        message.guild.voice_client.play(source)
                except Exception as e:
                    logger.error(f"読み上げエラー: {e}")

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        if member.id == self.bot.user.id:
            if before.channel and not after.channel:
                logger.info(f"ボイスチャンネルから切断されました: {before.channel.name}")
                if member.guild.id in self.players:
                    try:
                        await self.cleanup(member.guild)
                    except Exception as e:
                        logger.error(f"切断後のクリーンアップエラー: {e}")
                
                if member.guild.id in reading_channels:
                    reading_channels[member.guild.id]['active'] = False
                    del reading_channels[member.guild.id]
            return
            
        if not kick_enabled:
            return
            
        if member.id in kick_list and after.channel and member.guild.me in after.channel.members:
            try:
                await member.move_to(None)
                logger.info(f"キックリストのユーザーをキックしました: {member.name}")
            except (discord.HTTPException, discord.Forbidden) as e:
                logger.error(f"キックエラー: {e}")

async def setup(bot):
    await bot.add_cog(Music(bot))

@bot.event
async def on_ready():
    logger.info(f"ログイン成功: {bot.user.name} ({bot.user.id})")
    try:
        await setup(bot)
        logger.info("Musicコグを読み込みました")
    except Exception as e:
        logger.error(f"Musicコグ読み込みエラー: {e}")
        traceback.print_exc()

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        return
        
    if isinstance(error, commands.MissingRequiredArgument):
        embed = discord.Embed(
            title=f"{EMOJI['error']} コマンドエラー",
            description=f"必要な引数が不足しています: {error.param.name}",
            color=discord.Color.red()
        )
        await ctx.send(embed=embed)
        return
        
    if isinstance(error, commands.BadArgument):
        embed = discord.Embed(
            title=f"{EMOJI['error']} コマンドエラー",
            description=f"引数の型が正しくありません: {str(error)}",
            color=discord.Color.red()
        )
        await ctx.send(embed=embed)
        return
        
    logger.error(f"コマンド実行エラー: {error}")
    traceback.print_exc()
    
    try:
        embed = discord.Embed(
            title=f"{EMOJI['error']} エラー",
            description=f"コマンド実行中にエラーが発生しました: {str(error)}",
            color=discord.Color.red()
        )
        await ctx.send(embed=embed)
    except:
        pass

if __name__ == "__main__":
    try:
        token = os.getenv("DISCORD_TOKEN")
        if not token:
            logger.error("環境変数 DISCORD_TOKEN が設定されていません")
            sys.exit(1)
            
        bot.run(token)
    except Exception as e:
        logger.error(f"起動エラー: {e}")
        traceback.print_exc()
