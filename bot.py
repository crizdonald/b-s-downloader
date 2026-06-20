import os
import sys
import time
import tempfile
import shutil
import requests
import threading

# Reconfigure stdout/stderr to use UTF-8 to prevent Windows terminal encoding crashes
if sys.platform.startswith('win'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except AttributeError:
        pass

# Initialize static FFmpeg binaries on startup if available
try:
    import static_ffmpeg
    print("[FFMPEG] Initializing static FFmpeg binaries...", flush=True)
    static_ffmpeg.add_paths(weak=True)
except Exception as e:
    print(f"[FFMPEG] Warning: Could not initialize static-ffmpeg: {e}", flush=True)

def ensure_js_runtime(base_dir):
    import shutil
    import subprocess
    import urllib.request
    import zipfile
    import io
    
    # 1. Check if node, deno, or qjs is already available in PATH
    for runtime in ['deno', 'node', 'qjs']:
        if shutil.which(runtime):
            print(f"[JS RUNTIME] Found existing JavaScript runtime: {runtime}", flush=True)
            return True
            
    # 2. Check if deno is already downloaded in local bin directory
    local_bin = os.path.join(base_dir, 'bin')
    os.makedirs(local_bin, exist_ok=True)
    
    # Add local bin to PATH for the current process
    if local_bin not in os.environ.get('PATH', ''):
        os.environ['PATH'] = local_bin + os.pathsep + os.environ.get('PATH', '')
        
    deno_path = os.path.join(local_bin, 'deno')
    if sys.platform.startswith('win'):
        deno_path += '.exe'
        
    if os.path.exists(deno_path):
        print(f"[JS RUNTIME] Found downloaded deno at: {deno_path}", flush=True)
        return True
        
    # 3. If missing, download Deno binary dynamically
    print("[JS RUNTIME] No JavaScript runtime found. Downloading portable Deno...", flush=True)
    try:
        if sys.platform.startswith('win'):
            url = "https://github.com/denoland/deno/releases/latest/download/deno-x86_64-pc-windows-msvc.zip"
        elif sys.platform.startswith('darwin'):
            url = "https://github.com/denoland/deno/releases/latest/download/deno-x86_64-apple-darwin.zip"
        else:
            url = "https://github.com/denoland/deno/releases/latest/download/deno-x86_64-unknown-linux-gnu.zip"
            
        print(f"[JS RUNTIME] Downloading from: {url}", flush=True)
        headers = {'User-Agent': 'Mozilla/5.0'}
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=60) as response:
            zip_data = response.read()
            
        with zipfile.ZipFile(io.BytesIO(zip_data)) as z:
            z.extractall(local_bin)
            
        if not sys.platform.startswith('win') and os.path.exists(deno_path):
            os.chmod(deno_path, 0o755)
            
        print(f"[JS RUNTIME] Successfully installed Deno to: {deno_path}", flush=True)
        return True
    except Exception as err:
        print(f"[JS RUNTIME] Failed to download Deno: {err}", flush=True)
        return False

# Initialize JS runtime (bot.py calculates bot_dir/project_root later, calculate base_dir here dynamically)
try:
    _bot_dir = os.path.dirname(os.path.abspath(__file__))
    _base_dir = _bot_dir if os.path.exists(os.path.join(_bot_dir, 'core')) else os.path.dirname(_bot_dir)
    ensure_js_runtime(_base_dir)
except Exception as e:
    print(f"[JS RUNTIME] Warning: Error checking/installing JS runtime: {e}", flush=True)

# Add project root directory to path so imports work correctly
# Dynamically resolves whether bot.py is in the bot/ folder or placed in the root folder alongside core/utils
bot_dir = os.path.dirname(os.path.abspath(__file__))
if os.path.exists(os.path.join(bot_dir, 'core')) and os.path.exists(os.path.join(bot_dir, 'utils')):
    project_root = bot_dir
else:
    project_root = os.path.dirname(bot_dir)
sys.path.insert(0, project_root)

# Cloudflare Worker configuration (Optional - set these to load configurations dynamically from your Worker)
CF_WORKER_URL = "https://divqofy.divqomedia.workers.dev"
CF_WORKER_AUTH_KEY = os.getenv('CF_WORKER_AUTH_KEY', "divqofy_secret_auth_token_2026")

# Write file-level Cloudflare settings to environment if specified
if CF_WORKER_URL:
    os.environ['CF_WORKER_URL'] = CF_WORKER_URL
if CF_WORKER_AUTH_KEY:
    os.environ['CF_WORKER_AUTH_KEY'] = CF_WORKER_AUTH_KEY

def load_cf_worker_config_inlined(cf_url, cf_auth) -> bool:
    import requests
    if not cf_url:
        return False
    cf_url = cf_url.rstrip('/')
    config_endpoint = f"{cf_url}/api/config"
    print(f"[CONFIG] Attempting to retrieve config from Cloudflare Worker: {config_endpoint}", flush=True)
    headers = {}
    if cf_auth:
        headers['Authorization'] = f'Bearer {cf_auth}'
    try:
        resp = requests.get(config_endpoint, headers=headers, timeout=10)
        if resp.status_code == 200:
            config_data = resp.json()
            for key, val in config_data.items():
                if val and not str(val).startswith('your_'):
                    os.environ[key.upper()] = str(val)
            print("[CONFIG] Successfully fetched and loaded configuration from Cloudflare Worker into memory.", flush=True)
            return True
        else:
            print(f"[CONFIG] Cloudflare Worker returned status code: {resp.status_code} - {resp.text}", flush=True)
            return False
    except Exception as e:
        print(f"[CONFIG] Error requesting config from Cloudflare Worker: {e}", flush=True)
        return False

# 1. Load environment variables from local configuration files (.env and env.ini) first
bot_dir = os.path.dirname(os.path.abspath(__file__))
env_paths = [os.path.join(bot_dir, '.env'), os.path.join(project_root, '.env')]
for path in env_paths:
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as _env_file:
            for _line in _env_file:
                _line = _line.strip()
                if _line and not _line.startswith('#') and '=' in _line:
                    _key, _val = _line.split('=', 1)
                    os.environ[_key.strip()] = _val.strip().strip('"\'')
        break

# Load environment variables from env.ini if it exists (check bot folder first, then root)
ini_paths = [os.path.join(bot_dir, 'env.ini'), os.path.join(project_root, 'env.ini')]
for path in ini_paths:
    if os.path.exists(path):
        import configparser
        try:
            _config = configparser.ConfigParser()
            _config.read(path, encoding='utf-8')
            for _section in _config.sections():
                for _key, _val in _config.items(_section):
                    os.environ[_key.upper()] = _val
            for _key, _val in _config.defaults().items():
                os.environ[_key.upper()] = _val
        except Exception as _e:
            print(f"Error loading env.ini: {_e}")
        break

# 2. Try to fetch and override configurations from Cloudflare Worker if available
cf_loaded = load_cf_worker_config_inlined(CF_WORKER_URL, CF_WORKER_AUTH_KEY)


from core.spotify_parser import SpotifyParser
from core.yt_search import YouTubeSearcher
from core.yt_downloader import YouTubeDownloader
from core.insta_downloader import InstagramDownloader
from core.terabox_downloader import TeraboxDownloader
from core.metadata_writer import MetadataWriter
from utils.helpers import (
    parse_spotify_url, 
    parse_youtube_url, 
    parse_instagram_url, 
    parse_terabox_url, 
    sanitize_filename, 
    upload_to_remote_server
)
from utils.duplicate_manager import find_and_delete_duplicates, check_song_exists, scan_cache_directory

# Initialize core services
spotify_parser = SpotifyParser()
youtube_searcher = YouTubeSearcher()
metadata_writer = MetadataWriter()

def send_telegram_message(bot_token, chat_id, text, reply_to_message_id=None):
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        'chat_id': chat_id,
        'text': text,
        'parse_mode': 'Markdown'
    }
    if reply_to_message_id:
        payload['reply_to_message_id'] = reply_to_message_id
    try:
        resp = requests.post(url, json=payload, timeout=30)
        return resp.json()
    except Exception as e:
        print(f"Error sending message to Telegram: {e}")
        return None

def send_telegram_audio(bot_token, chat_id, filepath, title=None, artist=None, reply_to_message_id=None, cover_path=None):
    url = f"https://api.telegram.org/bot{bot_token}/sendAudio"
    payload = {
        'chat_id': chat_id,
        'title': title or '',
        'performer': artist or ''
    }
    if reply_to_message_id:
        payload['reply_to_message_id'] = reply_to_message_id
        
    opened_files = []
    try:
        audio_file = open(filepath, 'rb')
        opened_files.append(audio_file)
        files = {'audio': audio_file}
        
        if cover_path and os.path.exists(cover_path):
            cover_file = open(cover_path, 'rb')
            files['thumbnail'] = cover_file
            opened_files.append(cover_file)
            
        resp = requests.post(url, data=payload, files=files, timeout=120)
        if resp.status_code != 200:
            print(f"Telegram sendAudio error: {resp.text}")
            return False, resp.text
        return True, resp.json()
    except Exception as e:
        print(f"Error sending audio: {e}")
        return False, str(e)
    finally:
        for f in opened_files:
            try:
                f.close()
            except:
                pass

def send_telegram_document(bot_token, chat_id, filepath, caption=None, reply_to_message_id=None):
    url = f"https://api.telegram.org/bot{bot_token}/sendDocument"
    payload = {
        'chat_id': chat_id,
        'caption': caption or ''
    }
    if reply_to_message_id:
        payload['reply_to_message_id'] = reply_to_message_id
    try:
        with open(filepath, 'rb') as doc_file:
            files = {'document': doc_file}
            resp = requests.post(url, data=payload, files=files, timeout=120)
        if resp.status_code != 200:
            print(f"Telegram sendDocument error: {resp.text}")
            return False, resp.text
        return True, resp.json()
    except Exception as e:
        print(f"Error sending document: {e}")
        return False, str(e)

def send_telegram_video(bot_token, chat_id, filepath, caption=None, reply_to_message_id=None):
    url = f"https://api.telegram.org/bot{bot_token}/sendVideo"
    payload = {
        'chat_id': chat_id,
        'caption': caption or ''
    }
    if reply_to_message_id:
        payload['reply_to_message_id'] = reply_to_message_id
    try:
        with open(filepath, 'rb') as video_file:
            files = {'video': video_file}
            resp = requests.post(url, data=payload, files=files, timeout=120)
        if resp.status_code != 200:
            print(f"Telegram sendVideo error: {resp.text}")
            return False, resp.text
        return True, resp.json()
    except Exception as e:
        print(f"Error sending video: {e}")
        return False, str(e)

def send_telegram_photo(bot_token, chat_id, filepath, caption=None, reply_to_message_id=None):
    url = f"https://api.telegram.org/bot{bot_token}/sendPhoto"
    payload = {
        'chat_id': chat_id,
        'caption': caption or ''
    }
    if reply_to_message_id:
        payload['reply_to_message_id'] = reply_to_message_id
    try:
        with open(filepath, 'rb') as photo_file:
            files = {'photo': photo_file}
            resp = requests.post(url, data=payload, files=files, timeout=120)
        if resp.status_code != 200:
            print(f"Telegram sendPhoto error: {resp.text}")
            return False, resp.text
        return True, resp.json()
    except Exception as e:
        print(f"Error sending photo: {e}")
        return False, str(e)

def process_youtube_link(bot_token, chat_id, url, reply_to_message_id=None):
    try:
        send_telegram_message(bot_token, chat_id, "🔍 Inspecting YouTube link...", reply_to_message_id)
        downloader = YouTubeDownloader()
        info = downloader.get_video_info(url)
        if not info:
            send_telegram_message(bot_token, chat_id, "❌ Could not retrieve YouTube video info.", reply_to_message_id)
            return
            
        status_msg = send_telegram_message(bot_token, chat_id, f"📥 Downloading audio from: *{info['title']}*...", reply_to_message_id)
        status_msg_id = status_msg.get('result', {}).get('message_id') if status_msg else None
        
        temp_dir = tempfile.mkdtemp()
        try:
            temp_downloader = YouTubeDownloader(download_path=temp_dir)
            filename = sanitize_filename(f"{info['title']}.mp3")
            filepath = temp_downloader.download_audio(url, filename)
            
            if filepath:
                # Add basic metadata tags if we have them
                metadata = {
                    'title': info['title'],
                    'artist': info.get('uploader', 'YouTube'),
                }
                metadata_writer.write_metadata(filepath, metadata)
                
                # Upload to remote server if configured
                try:
                    upload_to_remote_server(filepath)
                except Exception as upload_e:
                    print(f"Error uploading YouTube audio to remote server: {upload_e}")
                    
                if status_msg_id:
                    send_telegram_message(bot_token, chat_id, "📤 Uploading audio to Telegram...", status_msg_id)
                    
                success, res = send_telegram_audio(
                    bot_token, chat_id, filepath, 
                    title=info['title'], artist=info.get('uploader', 'YouTube'),
                    reply_to_message_id=reply_to_message_id
                )
                
                if success and status_msg_id:
                    requests.post(f"https://api.telegram.org/bot{bot_token}/deleteMessage", json={
                        'chat_id': chat_id,
                        'message_id': status_msg_id
                    })
                elif not success:
                    send_telegram_message(bot_token, chat_id, f"❌ Failed to send audio to Telegram: {res}", reply_to_message_id)
            else:
                send_telegram_message(bot_token, chat_id, "❌ Failed to download YouTube audio.", reply_to_message_id)
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)
    except Exception as e:
        print(f"Error processing YouTube link: {e}")
        send_telegram_message(bot_token, chat_id, f"❌ YouTube processing failed: {str(e)}", reply_to_message_id)

def process_instagram_link(bot_token, chat_id, url, reply_to_message_id=None):
    try:
        url_type, shortcode = parse_instagram_url(url)
        if not url_type:
            send_telegram_message(bot_token, chat_id, "⚠️ Invalid Instagram URL. Please send a post, reel, or story link.", reply_to_message_id)
            return
            
        send_telegram_message(bot_token, chat_id, f"🔍 Fetching Instagram {url_type}...", reply_to_message_id)
        
        temp_dir = tempfile.mkdtemp()
        try:
            downloader = InstagramDownloader(download_path=temp_dir)
            files_to_send = []
            
            if url_type == 'reel':
                filepath = downloader.download_reel(url)
                if filepath:
                    files_to_send.append(filepath)
            elif url_type == 'story':
                filepath = downloader.download_story(url)
                if filepath:
                    files_to_send.append(filepath)
            else: # post
                filepaths = downloader.download_post(url)
                if filepaths:
                    files_to_send.extend(filepaths)
                    
            if not files_to_send:
                send_telegram_message(bot_token, chat_id, f"❌ Failed to download Instagram {url_type}.", reply_to_message_id)
                return
                
            for filepath in files_to_send:
                # Upload to remote server if configured
                try:
                    upload_to_remote_server(filepath)
                except Exception as upload_e:
                    print(f"Error uploading Instagram file to remote server: {upload_e}")
                    
                # Determine if photo or video
                ext = os.path.splitext(filepath)[1].lower()
                if ext in ('.mp4', '.m4v', '.mov'):
                    success, res = send_telegram_video(bot_token, chat_id, filepath, reply_to_message_id=reply_to_message_id)
                elif ext in ('.jpg', '.jpeg', '.png', '.webp'):
                    success, res = send_telegram_photo(bot_token, chat_id, filepath, reply_to_message_id=reply_to_message_id)
                else:
                    success, res = send_telegram_document(bot_token, chat_id, filepath, reply_to_message_id=reply_to_message_id)
                    
                if not success:
                    print(f"Failed to send Instagram file: {res}")
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)
    except Exception as e:
        print(f"Error processing Instagram link: {e}")
        send_telegram_message(bot_token, chat_id, f"❌ Instagram processing failed: {str(e)}", reply_to_message_id)

def process_terabox_link(bot_token, chat_id, url, reply_to_message_id=None):
    try:
        url_type, share_code = parse_terabox_url(url)
        if not url_type:
            send_telegram_message(bot_token, chat_id, "⚠️ Invalid Terabox URL.", reply_to_message_id)
            return
            
        send_telegram_message(bot_token, chat_id, "🔍 Fetching Terabox file info...", reply_to_message_id)
        downloader = TeraboxDownloader()
        info = downloader.get_file_info(url)
        if not info:
            send_telegram_message(bot_token, chat_id, "❌ Could not retrieve Terabox file details.", reply_to_message_id)
            return
            
        filename = info.get('title', 'terabox_file')
        size_str = info.get('size_str', 'Unknown')
        
        status_msg = send_telegram_message(bot_token, chat_id, f"📥 Downloading file: *{filename}* ({size_str})...", reply_to_message_id)
        status_msg_id = status_msg.get('result', {}).get('message_id') if status_msg else None
        
        temp_dir = tempfile.mkdtemp()
        try:
            temp_downloader = TeraboxDownloader(download_path=temp_dir)
            filepath = temp_downloader.download_file(url, output_filename=filename)
            
            if filepath and os.path.exists(filepath):
                # Upload to remote server if configured
                try:
                    upload_to_remote_server(filepath)
                except Exception as upload_e:
                    print(f"Error uploading Terabox file to remote server: {upload_e}")
                    
                if status_msg_id:
                    send_telegram_message(bot_token, chat_id, "📤 Uploading document to Telegram...", status_msg_id)
                    
                success, res = send_telegram_document(bot_token, chat_id, filepath, caption=filename, reply_to_message_id=reply_to_message_id)
                
                if success and status_msg_id:
                    requests.post(f"https://api.telegram.org/bot{bot_token}/deleteMessage", json={
                        'chat_id': chat_id,
                        'message_id': status_msg_id
                    })
                elif not success:
                    send_telegram_message(bot_token, chat_id, f"❌ Failed to send document: {res}", reply_to_message_id)
            else:
                send_telegram_message(bot_token, chat_id, "❌ Failed to download Terabox file.", reply_to_message_id)
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)
    except Exception as e:
        print(f"Error processing Terabox link: {e}")
        send_telegram_message(bot_token, chat_id, f"❌ Terabox processing failed: {str(e)}", reply_to_message_id)

def process_spotify_link(bot_token, chat_id, url, reply_to_message_id=None):
    try:
        # Determine track or playlist/album
        url_type, _ = parse_spotify_url(url)
        if not url_type:
            send_telegram_message(bot_token, chat_id, "⚠️ Invalid Spotify URL. Please send a track, playlist, or album link.", reply_to_message_id)
            return

        if url_type == 'track':
            send_telegram_message(bot_token, chat_id, "🔍 Parsing Spotify track...", reply_to_message_id)
            track_info = spotify_parser.parse_track(url)
            if not track_info:
                send_telegram_message(bot_token, chat_id, "❌ Could not parse track information from Spotify.", reply_to_message_id)
                return
            
            # Check cache first
            existing_path = check_song_exists(track_info['name'], track_info['artist'], 'downloads')
            filepath = None
            filename = sanitize_filename(f"{track_info['artist']} - {track_info['name']}.mp3")
            status_msg_id = None
            
            temp_dir = tempfile.mkdtemp()
            try:
                if existing_path and os.path.exists(existing_path):
                    print(f"[BOT CACHE HIT] Song '{track_info['name']}' found at '{existing_path}'")
                    filepath = os.path.join(temp_dir, filename)
                    shutil.copy2(existing_path, filepath)
                else:
                    status_msg = send_telegram_message(bot_token, chat_id, f"🎵 Found: *{track_info['name']}* by *{track_info['artist']}*\n🔎 Searching YouTube...", reply_to_message_id)
                    status_msg_id = status_msg.get('result', {}).get('message_id') if status_msg else None
                    
                    youtube_url = youtube_searcher.search_song(track_info['name'], track_info['artist'])
                    if not youtube_url:
                        send_telegram_message(bot_token, chat_id, "❌ Could not find matching YouTube video.", reply_to_message_id)
                        return
                    
                    if status_msg_id:
                        send_telegram_message(bot_token, chat_id, f"🎵 Found: *{track_info['name']}* by *{track_info['artist']}*\n📥 Downloading audio from YouTube...", status_msg_id)
                        
                    downloader = YouTubeDownloader(download_path=temp_dir)
                    filepath = downloader.download_audio(
                        youtube_url, filename,
                        fallback_query=f"{track_info['artist']} - {track_info['name']}"
                    )
                    
                    if filepath:
                        metadata = {
                            'title': track_info['name'],
                            'artist': track_info['artist'],
                            'album': track_info.get('album'),
                            'cover_art': track_info.get('cover_art', ''),
                        }
                        metadata_writer.write_metadata(filepath, metadata)
                
                # Now, whether from cache or downloaded, upload if filepath exists
                if filepath:
                    # Download cover art for Telegram thumbnail
                    cover_path = None
                    cover_url = track_info.get('cover_art', '')
                    if cover_url and cover_url.startswith('http'):
                        try:
                            cover_resp = requests.get(cover_url, timeout=10)
                            if cover_resp.status_code == 200:
                                cover_path = os.path.join(temp_dir, 'cover.jpg')
                                with open(cover_path, 'wb') as cf:
                                    cf.write(cover_resp.content)
                        except Exception as ce:
                            print(f"Error downloading cover art for Telegram: {ce}")
                    
                    # Upload to remote server if configured
                    try:
                        upload_to_remote_server(filepath)
                    except Exception as upload_e:
                        print(f"Error uploading track to remote server: {upload_e}")
                    
                    if status_msg_id:
                        send_telegram_message(bot_token, chat_id, "📤 Uploading audio to Telegram...", status_msg_id)
                    
                    success, res = send_telegram_audio(
                        bot_token, chat_id, filepath, 
                        title=track_info['name'], artist=track_info['artist'],
                        reply_to_message_id=reply_to_message_id,
                        cover_path=cover_path
                    )
                    
                    if success and status_msg_id:
                        # Try to delete processing message
                        requests.post(f"https://api.telegram.org/bot{bot_token}/deleteMessage", json={
                            'chat_id': chat_id,
                            'message_id': status_msg_id
                        })
                    elif not success:
                        send_telegram_message(bot_token, chat_id, f"❌ Failed to upload to Telegram: {res}", reply_to_message_id)
                else:
                    send_telegram_message(bot_token, chat_id, "❌ Failed to download/retrieve audio.", reply_to_message_id)
            finally:
                shutil.rmtree(temp_dir, ignore_errors=True)
                
        elif url_type in ('playlist', 'album'):
            type_label = "playlist" if url_type == 'playlist' else "album"
            send_telegram_message(bot_token, chat_id, f"🔍 Parsing Spotify {type_label}...", reply_to_message_id)
            playlist_data = spotify_parser.parse_playlist(url)
            if not playlist_data or not playlist_data.get('tracks'):
                send_telegram_message(bot_token, chat_id, f"❌ Could not parse {type_label} information.", reply_to_message_id)
                return
            
            playlist_name = playlist_data.get('name', f'Unknown {type_label.capitalize()}')
            tracks = playlist_data.get('tracks', [])
            
            send_telegram_message(
                bot_token, chat_id, 
                f"🎵 Found {type_label}: *{playlist_name}*\n📦 Total Tracks: {len(tracks)}\n🚀 Starting download and upload flow. Tracks will be sent one by one.",
                reply_to_message_id
            )
            
            # Build cache of existing downloads once at start
            cache_map = scan_cache_directory('downloads')
            
            downloaded_count = 0
            for i, track in enumerate(tracks, 1):
                if not track or track.get('name') == 'Unknown Song':
                    continue
                    
                status_txt = f"⏳ [{i}/{len(tracks)}] Processing: *{track['name']}* - *{track['artist']}*"
                status_msg = send_telegram_message(bot_token, chat_id, status_txt)
                status_msg_id = status_msg.get('result', {}).get('message_id') if status_msg else None
                
                # Check cache first
                from utils.duplicate_manager import normalize_string
                track_sig = normalize_string(f"{track['artist']} - {track['name']}")
                
                filepath = None
                filename = sanitize_filename(f"{track['artist']} - {track['name']}.mp3")
                
                # We only need to search YouTube if it's NOT in the cache
                youtube_url = None
                if track_sig not in cache_map or not os.path.exists(cache_map[track_sig]):
                    youtube_url = youtube_searcher.search_song(track['name'], track['artist'])
                    if not youtube_url:
                        if status_msg_id:
                            send_telegram_message(bot_token, chat_id, f"⚠️ [{i}/{len(tracks)}] YouTube video not found for *{track['name']}*", status_msg_id)
                        continue
                
                temp_dir = tempfile.mkdtemp()
                try:
                    if track_sig in cache_map and os.path.exists(cache_map[track_sig]):
                        print(f"[BOT PLAYLIST CACHE HIT] Song '{track['name']}' found at '{cache_map[track_sig]}'")
                        filepath = os.path.join(temp_dir, filename)
                        shutil.copy2(cache_map[track_sig], filepath)
                    else:
                        downloader = YouTubeDownloader(download_path=temp_dir)
                        filepath = downloader.download_audio(
                            youtube_url, filename,
                            fallback_query=f"{track['artist']} - {track['name']}"
                        )
                        
                        if filepath:
                            metadata = {
                                'title': track['name'],
                                'artist': track['artist'],
                                'album': track.get('album'),
                                'cover_art': track.get('cover_art', ''),
                            }
                            metadata_writer.write_metadata(filepath, metadata)
                        
                    if filepath:
                        # Download cover art for Telegram thumbnail
                        cover_path = None
                        cover_url = track.get('cover_art', '')
                        if cover_url and cover_url.startswith('http'):
                            try:
                                cover_resp = requests.get(cover_url, timeout=10)
                                if cover_resp.status_code == 200:
                                    cover_path = os.path.join(temp_dir, 'cover.jpg')
                                    with open(cover_path, 'wb') as cf:
                                        cf.write(cover_resp.content)
                            except Exception as ce:
                                print(f"Error downloading cover art for Telegram: {ce}")
                        
                        # Upload to remote server if configured
                        try:
                            upload_to_remote_server(filepath)
                        except Exception as upload_e:
                            print(f"Error uploading playlist track to remote server: {upload_e}")
                        
                        success, res = send_telegram_audio(
                            bot_token, chat_id, filepath, 
                            title=track['name'], artist=track['artist'],
                            cover_path=cover_path
                        )
                        
                        if success:
                            downloaded_count += 1
                            if status_msg_id:
                                requests.post(f"https://api.telegram.org/bot{bot_token}/deleteMessage", json={
                                    'chat_id': chat_id,
                                    'message_id': status_msg_id
                                })
                        else:
                            if status_msg_id:
                                send_telegram_message(bot_token, chat_id, f"❌ [{i}/{len(tracks)}] Upload failed: {res}", status_msg_id)
                    else:
                        if status_msg_id:
                            send_telegram_message(bot_token, chat_id, f"❌ [{i}/{len(tracks)}] Download failed", status_msg_id)
                finally:
                    shutil.rmtree(temp_dir, ignore_errors=True)
                
                # Anti-flood rate limiting
                time.sleep(5.0)
                
            send_telegram_message(bot_token, chat_id, f"✅ Completed! Successfully processed and uploaded {downloaded_count}/{len(tracks)} tracks from {type_label} *{playlist_name}*.")
            # Auto cleanup duplicates in background
            try:
                import threading
                threading.Thread(target=find_and_delete_duplicates, args=('downloads',), daemon=True).start()
            except Exception as de:
                print(f"Error starting background duplicate clean up: {de}")
    except Exception as e:
        print(f"Error processing Spotify link: {e}")
        send_telegram_message(bot_token, chat_id, f"❌ An unexpected error occurred: {str(e)}", reply_to_message_id)

def main():
    # Start the Flask web application in the background
    import subprocess
    try:
        app_path = os.path.join(project_root, 'app.py')
        print(f"[SERVER] Spawning Flask backend server ({app_path}) in background...", flush=True)
        subprocess.Popen([sys.executable, app_path])
    except Exception as e:
        print(f"⚠️ Warning: Failed to spawn Flask backend server: {e}", flush=True)

    bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
    allowed_group_id = os.getenv('TELEGRAM_GROUP_ID')
    
    if not bot_token or bot_token == 'your_telegram_bot_token_here':
        print("❌ Error: TELEGRAM_BOT_TOKEN not found in environment or configuration files.")
        print("Please configure your credentials in 'env.ini' or '.env' file.")
        sys.exit(1)
        
    print("=" * 60)
    print("🤖 Starting Telegram Spotify Downloader Bot...")
    print(f"   Bot Token: {'*' * 10}{bot_token[-5:] if len(bot_token) > 5 else ''}")
    if allowed_group_id:
        print(f"   Target Group/Channel ID: {allowed_group_id}")
    print("=" * 60)
    print("Bot is polling for messages. Press CTRL+C to stop.")
    
    offset = 0
    while True:
        try:
            url = f"https://api.telegram.org/bot{bot_token}/getUpdates?offset={offset}&timeout=30"
            resp = requests.get(url, timeout=35)
            if resp.status_code != 200:
                print(f"Error fetching updates from Telegram: {resp.text}")
                time.sleep(5)
                continue
                
            data = resp.json()
            if not data.get('ok'):
                print(f"Telegram API returned error: {data}")
                time.sleep(5)
                continue
                
            for update in data.get('result', []):
                offset = update['update_id'] + 1
                
                message = update.get('message')
                if not message:
                    continue
                    
                chat = message.get('chat', {})
                chat_id = str(chat.get('id', ''))
                text = message.get('text', '').strip()
                message_id = message.get('message_id')
                
                if not text:
                    continue
                
                # Check /start or /help commands
                if text.startswith('/start') or text.startswith('/help'):
                    welcome_text = (
                        "👋 *Welcome to Media Downloader Bot!*\n\n"
                        "Send me any link from the supported platforms below, and I will download and send it back to you!\n\n"
                        "🎵 *Spotify* (Track, Playlist, Album):\n"
                        "• `https://open.spotify.com/track/4PTG3Z6ehGkBF3zIqYQG5I`\n\n"
                        "📺 *YouTube* (Audio Extraction):\n"
                        "• `https://www.youtube.com/watch?v=dQw4w9WgXcQ`\n\n"
                        "📷 *Instagram* (Post, Reel, Story):\n"
                        "• `https://www.instagram.com/reel/C-xyz/`\n\n"
                        "☁️ *Terabox* (Files):\n"
                        "• `https://terabox.com/s/1xyz`"
                    )
                    send_telegram_message(bot_token, chat_id, welcome_text, reply_to_message_id=message_id)
                    continue
                
                # Check /test command to find group/chat ID
                if text.startswith('/test'):
                    chat_type = chat.get('type', 'unknown')
                    chat_title = chat.get('title', 'Private Chat')
                    response_text = (
                        "🔍 *Telegram Chat Information:*\n\n"
                        f"• *Chat Type:* `{chat_type}`\n"
                        f"• *Chat Title/Name:* `{chat_title}`\n"
                        f"• *Chat/Group ID:* `{chat_id}`\n\n"
                        "💡 Copy this ID and paste it into your `env.ini` or `.env` as `TELEGRAM_GROUP_ID` to restrict the bot or configure default uploads."
                    )
                    send_telegram_message(bot_token, chat_id, response_text, reply_to_message_id=message_id)
                    continue

                # Check allowed group if config restricts it
                if allowed_group_id and allowed_group_id != 'your_telegram_group_id_here':
                    if chat_id != str(allowed_group_id) and chat.get('type') != 'private':
                        print(f"Skipping request from unauthorized chat ID: {chat_id}")
                        continue

                # Detect and extract link
                words = text.split()
                target_link = None
                platform = None
                
                for word in words:
                    if 'open.spotify.com' in word:
                        target_link = word
                        platform = 'spotify'
                        break
                    elif 'youtube.com' in word or 'youtu.be' in word:
                        target_link = word
                        platform = 'youtube'
                        break
                    elif 'instagram.com' in word:
                        target_link = word
                        platform = 'instagram'
                        break
                    elif 'terabox.com' in word or '1024tera.com' in word or 'teraboxapp.com' in word:
                        target_link = word
                        platform = 'terabox'
                        break

                if target_link:
                    # Choose processing function based on platform
                    if platform == 'spotify':
                        target_func = process_spotify_link
                    elif platform == 'youtube':
                        target_func = process_youtube_link
                    elif platform == 'instagram':
                        target_func = process_instagram_link
                    elif platform == 'terabox':
                        target_func = process_terabox_link
                        
                    print(f"Processing {platform} link '{target_link}' from Chat: {chat_id}")
                    t = threading.Thread(
                        target=target_func, 
                        args=(bot_token, chat_id, target_link, message_id)
                    )
                    t.daemon = True
                    t.start()
                        
        except KeyboardInterrupt:
            print("\nExiting bot polling loop...")
            break
        except Exception as e:
            print(f"Error in main polling loop: {e}")
            time.sleep(5)

if __name__ == '__main__':
    main()

