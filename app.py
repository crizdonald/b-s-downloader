"""
Flask Web Application for Media Downloader
Supports Spotify, YouTube, Instagram, and Terabox downloads
"""
import os
import sys
import json
import threading
import zipfile
import tempfile
import shutil
from flask import Flask, render_template, request, jsonify, send_file
from flask_cors import CORS
import uuid

# Initialize static FFmpeg binaries on startup if available
try:
    import static_ffmpeg
    print("[FFMPEG] Initializing static FFmpeg binaries...", flush=True)
    static_ffmpeg.add_paths(weak=True)
except Exception as e:
    print(f"[FFMPEG] Warning: Could not initialize static-ffmpeg: {e}", flush=True)

# ── Startup compatibility check ──────────────────────────────────────────────
# Guard against partial deployments where app.py is newer than core/yt_downloader.py
try:
    import inspect
    from yt_downloader import YouTubeDownloader
    sig = inspect.signature(YouTubeDownloader.download_audio)
    if 'fallback_query' not in sig.parameters:
        print("[COMPAT] WARNING: core/yt_downloader.py is outdated (missing fallback_query).", flush=True)
        print("[COMPAT] Patching download_audio at runtime to accept fallback_query safely...", flush=True)
        _orig_download_audio = YouTubeDownloader.download_audio
        def _patched_download_audio(self, url, output_filename=None, progress_hook=None, fallback_query=None):
            # Run original without fallback_query (old signature), SoundCloud fallback unavailable
            return _orig_download_audio(self, url, output_filename, progress_hook)
        YouTubeDownloader.download_audio = _patched_download_audio
        print("[COMPAT] Patch applied. Upload the full bot.zip to get SoundCloud fallback working.", flush=True)
    else:
        print("[COMPAT] core/yt_downloader.py version OK (fallback_query supported).", flush=True)
except Exception as _compat_e:
    print(f"[COMPAT] Version check skipped: {_compat_e}", flush=True)
# ─────────────────────────────────────────────────────────────────────────────

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

# Initialize JS runtime
try:
    ensure_js_runtime(os.path.dirname(os.path.abspath(__file__)))
except Exception as e:
    print(f"[JS RUNTIME] Warning: Error checking/installing JS runtime: {e}", flush=True)

# Cloudflare Worker configuration (Optional - set these to load configurations dynamically from your Worker)
CF_WORKER_URL = "https://divqofy.divqomedia.workers.dev"
CF_WORKER_AUTH_KEY = os.getenv('CF_WORKER_AUTH_KEY', "divqofy_secret_auth_token_2026")

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

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
env_paths = [os.path.join('bot', '.env'), '.env']
for path in env_paths:
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as _env_file:
            for _line in _env_file:
                _line = _line.strip()
                if _line and not _line.startswith('#') and '=' in _line:
                    _key, _val = _line.split('=', 1)
                    os.environ[_key.strip()] = _val.strip().strip('"\'')
        break

# Load environment variables from env.ini file if it exists (check bot folder first, then root)
ini_paths = [os.path.join('bot', 'env.ini'), 'env.ini']
for path in ini_paths:
    if os.path.exists(path):
        import configparser
        try:
            _config = configparser.ConfigParser()
            _config.read(path, encoding='utf-8')
            for _section in _config.sections():
                for _key, _val in _config.items(_section):
                    os.environ[_key.upper()] = _val
            # Also check default section
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
try:
    from bot.telegram_uploader import TelegramUploader
except (ImportError, ModuleNotFoundError):
    try:
        from telegram_uploader import TelegramUploader
    except (ImportError, ModuleNotFoundError):
        import sys
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'bot'))
        from telegram_uploader import TelegramUploader
from utils.helpers import parse_spotify_url, parse_youtube_url, parse_instagram_url, sanitize_filename, upload_to_remote_server
from utils.duplicate_manager import find_and_delete_duplicates, check_song_exists, scan_cache_directory

app = Flask(__name__)
app.secret_key = os.urandom(24)
CORS(app)

# Download status tracking
download_status = {}

# Initialize downloaders
spotify_parser = SpotifyParser()
youtube_searcher = YouTubeSearcher()
metadata_writer = MetadataWriter()

@app.route('/')
def index():
    """Main page"""
    return render_template('index.html')

@app.route('/terabox')
def terabox_page():
    """Terabox viewer and downloader page"""
    return render_template('terabox.html')

@app.route('/api/spotify/track', methods=['POST'])
def spotify_track():
    """Download Spotify track"""
    try:
        data = request.json
        url = data.get('url')
        
        if not url:
            return jsonify({'error': 'URL is required'}), 400
        
        # Parse track
        track_info = spotify_parser.parse_track(url)
        if not track_info:
            return jsonify({'error': 'Could not parse track information'}), 400
        
        # Search YouTube
        youtube_url = youtube_searcher.search_song(track_info['name'], track_info['artist'])
        if not youtube_url:
            return jsonify({'error': 'Could not find YouTube video'}), 404
        
        # Start download in background
        task_id = str(uuid.uuid4())
        download_status[task_id] = {
            'status': 'processing',
            'message': f"Found: {track_info['name']} - {track_info['artist']}",
            'progress': 0
        }
        
        def download_task():
            temp_file = None
            try:
                # Use temporary directory
                temp_dir = tempfile.mkdtemp()
                downloader = YouTubeDownloader(download_path=temp_dir)
                filename = sanitize_filename(f"{track_info['artist']} - {track_info['name']}.mp3")
                
                def progress_hook(d):
                    if d.get('status') == 'downloading':
                        downloaded = d.get('downloaded_bytes', 0)
                        total = d.get('total_bytes', 0)
                        if total > 0:
                            progress = (downloaded / total) * 100
                            download_status[task_id]['progress'] = int(progress)
                            download_status[task_id]['message'] = f"Downloading: {int(progress)}%"
                
                filepath = downloader.download_audio(
                    youtube_url, filename, progress_hook=progress_hook,
                    fallback_query=f"{track_info['artist']} - {track_info['name']}"
                )
                
                if filepath:
                    # Write metadata
                    metadata = {
                        'title': track_info['name'],
                        'artist': track_info['artist'],
                        'album': track_info.get('album'),
                        'cover_art': track_info.get('cover_art', ''),
                    }
                    print(f"DEBUG_APP: Calling write_metadata for {filename}. Cover Art URL: '{metadata.get('cover_art')}'")
                    metadata_writer.write_metadata(filepath, metadata)
                    
                    # Copy to permanent downloads folder
                    try:
                        perm_folder = os.path.join('downloads', 'spotify')
                        os.makedirs(perm_folder, exist_ok=True)
                        perm_filepath = os.path.join(perm_folder, os.path.basename(filepath))
                        shutil.copy2(filepath, perm_filepath)
                        print(f"DEBUG_APP: Copied track to {perm_filepath}")
                        # Upload to remote server if configured
                        upload_to_remote_server(perm_filepath)
                    except Exception as copy_e:
                        print(f"DEBUG_APP: Failed to copy track to permanent folder: {copy_e}")
                    
                    # Store file in memory/temp for download
                    temp_file = filepath
                    download_status[task_id] = {
                        'status': 'completed',
                        'message': 'Download completed',
                        'progress': 100,
                        'filepath': filepath,
                        'filename': os.path.basename(filepath),
                        'temp_dir': temp_dir
                    }
                else:
                    download_status[task_id] = {
                        'status': 'error',
                        'message': 'Download failed',
                        'progress': 0
                    }
                    if temp_dir and os.path.exists(temp_dir):
                        shutil.rmtree(temp_dir, ignore_errors=True)
            except Exception as e:
                download_status[task_id] = {
                    'status': 'error',
                    'message': str(e),
                    'progress': 0
                }
                if 'temp_dir' in locals() and temp_dir and os.path.exists(temp_dir):
                    shutil.rmtree(temp_dir, ignore_errors=True)
        
        thread = threading.Thread(target=download_task)
        thread.start()
        
        return jsonify({
            'task_id': task_id,
            'track_info': track_info,
            'youtube_url': youtube_url
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/spotify/playlist', methods=['POST'])
def spotify_playlist():
    """Download Spotify playlist or album"""
    try:
        data = request.json
        url = data.get('url')
        
        if not url:
            return jsonify({'error': 'URL is required'}), 400
        
        # Determine URL type
        url_type, _ = parse_spotify_url(url)
        type_label = 'album' if url_type == 'album' else 'playlist'
        
        # Parse playlist or album
        playlist_data = spotify_parser.parse_playlist(url)
        if not playlist_data or not playlist_data.get('tracks'):
            return jsonify({'error': f'Could not parse {type_label}'}), 400
        
        playlist_name = playlist_data.get('name', f'Unknown {type_label.capitalize()}')
        tracks = playlist_data.get('tracks', [])
        
        # Start download in background
        task_id = str(uuid.uuid4())
        download_status[task_id] = {
            'status': 'processing',
            'message': f"Found {type_label}: {playlist_name} with {len(tracks)} tracks",
            'progress': 0,
            'total': len(tracks),
            'completed': 0
        }
        
        def download_task():
            temp_dir = None
            try:
                # Use temporary directory
                temp_dir = tempfile.mkdtemp()
                sanitized_playlist_name = sanitize_filename(playlist_name)
                playlist_folder = os.path.join(temp_dir, sanitized_playlist_name)
                os.makedirs(playlist_folder, exist_ok=True)
                
                downloader = YouTubeDownloader(download_path=playlist_folder)
                downloaded = 0
                failed = 0
                
                for i, track in enumerate(tracks, 1):
                    if not track or track.get('name') == 'Unknown Song':
                        print(f"Skipping track {i} due to missing metadata")
                        failed += 1
                        continue

                    print(f"[{i}/{len(tracks)}] {track['name']} - {track['artist']}")
                    download_status[task_id]['message'] = f"Downloading [{i}/{len(tracks)}]: {track['name']}"
                    download_status[task_id]['progress'] = int(((i-1) / len(tracks)) * 100)
                    
                    # Fetch high-quality metadata for individual track to get specific cover art
                    try:
                        import time
                        time.sleep(1.5) # Rate limit protection
                        # Only fetch if we suspect generic/playlist art (or always to be safe)
                        print(f"DEBUG_APP: Fetching details for {track['name']}...")
                        detailed_info = spotify_parser.parse_track(track['url'])
                        if detailed_info and detailed_info.get('cover_art'):
                            track['cover_art'] = detailed_info['cover_art']
                            track['album'] = detailed_info.get('album', track.get('album'))
                            print(f"DEBUG_APP: Refreshed metadata for {track['name']}. Cover: {track['cover_art']}")
                    except Exception as e:
                        print(f"DEBUG_APP: Failed to refresh metadata: {e}")

                    youtube_url = youtube_searcher.search_song(track['name'], track['artist'])
                    if not youtube_url:
                        failed += 1
                        continue
                    
                    filename = sanitize_filename(f"{track['artist']} - {track['name']}.mp3")
                    filepath = downloader.download_audio(
                        youtube_url, filename,
                        fallback_query=f"{track['artist']} - {track['name']}"
                    )
                    
                    if filepath:
                        metadata = {
                            'title': track['name'],
                            'artist': track['artist'],
                            'album': track.get('album', 'Unknown Album'),
                            'cover_art': track.get('cover_art', ''),
                        }
                        print(f"DEBUG_APP: Calling write_metadata for playlist track. Cover URL: '{metadata.get('cover_art')}'")
                        metadata_writer.write_metadata(filepath, metadata)
                        downloaded += 1
                    else:
                        failed += 1
                    
                    download_status[task_id]['completed'] = downloaded
                
                # Copy to permanent downloads folder
                try:
                    perm_folder = os.path.join('downloads', 'spotify', sanitized_playlist_name)
                    os.makedirs(perm_folder, exist_ok=True)
                    for file in os.listdir(playlist_folder):
                        dest_file = os.path.join(perm_folder, file)
                        shutil.copy2(os.path.join(playlist_folder, file), dest_file)
                        # Upload to remote server if configured
                        upload_to_remote_server(dest_file)
                    print(f"DEBUG_APP: Copied {type_label} tracks to {perm_folder} and uploaded to remote server")
                except Exception as copy_e:
                    print(f"DEBUG_APP: Failed to copy files to permanent folder: {copy_e}")
                
                status_msg = f'Downloaded {downloaded} tracks'
                if failed > 0:
                    status_msg += f' (Failed: {failed})'
                
                download_status[task_id] = {
                    'status': 'completed',
                    'message': status_msg,
                    'progress': 100,
                    'downloaded': downloaded,
                    'failed': failed,
                    'folder': playlist_folder,
                    'playlist_name': playlist_name,
                    'temp_dir': temp_dir
                }
            except Exception as e:
                download_status[task_id] = {
                    'status': 'error',
                    'message': str(e),
                    'progress': 0
                }
                if temp_dir and os.path.exists(temp_dir):
                    shutil.rmtree(temp_dir, ignore_errors=True)
        
        thread = threading.Thread(target=download_task)
        thread.start()
        
        return jsonify({
            'task_id': task_id,
            'playlist_name': playlist_name,
            'track_count': len(tracks),
            'tracks': tracks[:10]  # Return first 10 tracks as preview
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/spotify/metadata', methods=['POST'])
def spotify_metadata():
    """Extract and return Spotify playlist, album, or track metadata as JSON"""
    try:
        data = request.json
        url = data.get('url')
        
        if not url:
            return jsonify({'error': 'Spotify URL is required'}), 400
            
        url_type, _ = parse_spotify_url(url)
        if not url_type:
            return jsonify({'error': 'Invalid Spotify URL'}), 400
            
        if url_type == 'track':
            track_info = spotify_parser.parse_track(url)
            if not track_info:
                return jsonify({'error': 'Could not parse Spotify track metadata'}), 400
            
            result = {
                'type': 'track',
                'name': track_info['name'],
                'artist': track_info['artist'],
                'album': track_info.get('album', 'Unknown Album'),
                'cover_art': track_info.get('cover_art', ''),
                'url': track_info['url'],
                'id': track_info['id'],
                'tracks': [track_info]
            }
        elif url_type in ('playlist', 'album'):
            playlist_data = spotify_parser.parse_playlist(url)
            if not playlist_data or not playlist_data.get('tracks'):
                return jsonify({'error': f'Could not parse Spotify {url_type} metadata'}), 400
                
            result = {
                'type': url_type,
                'name': playlist_data['name'],
                'tracks': playlist_data['tracks']
            }
        else:
            return jsonify({'error': 'Unsupported Spotify link type'}), 400
            
        return jsonify(result)
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/spotify/telegram', methods=['POST'])
def spotify_telegram():
    """Download Spotify media and upload to Telegram group/channel"""
    import requests
    try:
        data = request.json
        url = data.get('url')
        bot_token = data.get('bot_token') or os.getenv('TELEGRAM_BOT_TOKEN')
        chat_id = data.get('chat_id') or os.getenv('TELEGRAM_GROUP_ID')
        type_choice = data.get('type', 'track')
        
        if not url:
            return jsonify({'error': 'Spotify URL is required'}), 400
        if not bot_token:
            return jsonify({'error': 'Telegram Bot Token is required (pass in UI or set TELEGRAM_BOT_TOKEN env)'}), 400
        if not chat_id:
            return jsonify({'error': 'Telegram Group/Chat ID is required (pass in UI or set TELEGRAM_GROUP_ID env)'}), 400
        
        # Start the background task
        task_id = str(uuid.uuid4())
        download_status[task_id] = {
            'status': 'processing',
            'message': 'Initializing Telegram upload task...',
            'progress': 0
        }
        
        # Initialize uploader helper
        uploader = TelegramUploader(bot_token, chat_id)
        
        def upload_task():
            temp_dir = None
            try:
                temp_dir = tempfile.mkdtemp()
                
                # Check url type
                url_type, _ = parse_spotify_url(url)
                
                if url_type == 'track' or type_choice == 'track':
                    # Download single track
                    track_info = spotify_parser.parse_track(url)
                    if not track_info:
                        raise Exception('Could not parse track information')
                        
                    # Check cache first
                    existing_path = check_song_exists(track_info['name'], track_info['artist'], 'downloads')
                    filepath = None
                    filename = sanitize_filename(f"{track_info['artist']} - {track_info['name']}.mp3")
                    
                    if existing_path and os.path.exists(existing_path):
                        print(f"[CACHE HIT] Song '{track_info['name']}' found at '{existing_path}'")
                        filepath = os.path.join(temp_dir, filename)
                        shutil.copy2(existing_path, filepath)
                    else:
                        download_status[task_id]['message'] = f"Searching: {track_info['name']} - {track_info['artist']}"
                        youtube_url = youtube_searcher.search_song(track_info['name'], track_info['artist'])
                        if not youtube_url:
                            raise Exception('Could not find track on YouTube')
                        
                        downloader = YouTubeDownloader(download_path=temp_dir)
                        
                        def progress_hook(d):
                            if d.get('status') == 'downloading':
                                downloaded = d.get('downloaded_bytes', 0)
                                total = d.get('total_bytes', 0)
                                if total > 0:
                                    progress = (downloaded / total) * 100
                                    download_status[task_id]['progress'] = int(progress)
                                    download_status[task_id]['message'] = f"Downloading: {int(progress)}%"
                        
                        filepath = downloader.download_audio(
                            youtube_url, filename, progress_hook=progress_hook,
                            fallback_query=f"{track_info['artist']} - {track_info['name']}"
                        )
                        if not filepath:
                            raise Exception('Download failed')
                            
                        # Tag metadata
                        metadata = {
                            'title': track_info['name'],
                            'artist': track_info['artist'],
                            'album': track_info.get('album'),
                            'cover_art': track_info.get('cover_art', ''),
                        }
                        metadata_writer.write_metadata(filepath, metadata)
                    
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
                            
                    # Upload
                    download_status[task_id]['message'] = "Uploading to Telegram..."
                    download_status[task_id]['progress'] = 95
                    uploader.send_audio(filepath, track_info['name'], track_info['artist'], cover_path=cover_path)
                    # Upload to remote server if configured
                    upload_to_remote_server(filepath)
                    
                    download_status[task_id] = {
                        'status': 'completed',
                        'message': f"Uploaded: {track_info['name']} - {track_info['artist']}",
                        'progress': 100
                    }
                else:
                    # Download playlist or album
                    playlist_data = spotify_parser.parse_playlist(url)
                    if not playlist_data or not playlist_data.get('tracks'):
                        raise Exception('Could not parse playlist/album')
                        
                    playlist_name = playlist_data.get('name', 'Unknown')
                    tracks = playlist_data.get('tracks', [])
                    total_tracks = len(tracks)
                    
                    download_status[task_id]['message'] = f"Found {total_tracks} tracks in {playlist_name}"
                    
                    downloader = YouTubeDownloader(download_path=temp_dir)
                    uploaded_count = 0
                    failed_count = 0
                    
                    # Build cache of existing downloads once at start
                    cache_map = scan_cache_directory('downloads')
                    
                    for i, track in enumerate(tracks, 1):
                        if not track or track.get('name') == 'Unknown Song':
                            failed_count += 1
                            continue
                            
                        # Update status
                        download_status[task_id]['message'] = f"[{i}/{total_tracks}] Searching: {track['name']}"
                        download_status[task_id]['progress'] = int(((i - 1) / total_tracks) * 100)
                        
                        # Check cache first
                        from utils.duplicate_manager import normalize_string
                        track_sig = normalize_string(f"{track['artist']} - {track['name']}")
                        
                        filepath = None
                        filename = sanitize_filename(f"{track['artist']} - {track['name']}.mp3")
                        
                        if track_sig in cache_map and os.path.exists(cache_map[track_sig]):
                            print(f"[PLAYLIST CACHE HIT] Song '{track['name']}' found at '{cache_map[track_sig]}'")
                            filepath = os.path.join(temp_dir, filename)
                            shutil.copy2(cache_map[track_sig], filepath)
                        else:
                            # Try to refresh detailed metadata for cover art
                            try:
                                detailed_info = spotify_parser.parse_track(track['url'])
                                if detailed_info:
                                    track['cover_art'] = detailed_info.get('cover_art', track.get('cover_art'))
                                    track['album'] = detailed_info.get('album', track.get('album'))
                            except:
                                pass
                                
                            youtube_url = youtube_searcher.search_song(track['name'], track['artist'])
                            if not youtube_url:
                                failed_count += 1
                                continue
                                
                            filepath = downloader.download_audio(
                                youtube_url, filename,
                                fallback_query=f"{track['artist']} - {track['name']}"
                            )
                            
                            if filepath:
                                metadata = {
                                    'title': track['name'],
                                    'artist': track['artist'],
                                    'album': track.get('album', 'Unknown Album'),
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
                                    
                            # Upload to Telegram
                            download_status[task_id]['message'] = f"[{i}/{total_tracks}] Uploading: {track['name']}"
                            uploader.send_audio(filepath, track['name'], track['artist'], cover_path=cover_path)
                            uploaded_count += 1
                            
                            # Upload to remote server if configured
                            upload_to_remote_server(filepath)
                            
                            # Delete temporary file immediately after successful upload
                            try:
                                os.remove(filepath)
                            except:
                                pass
                                
                            # Rate limit protection for Telegram
                            import time
                            time.sleep(5.0)
                        else:
                            failed_count += 1
                            
                    status_msg = f"Uploaded {uploaded_count} tracks to Telegram"
                    if failed_count > 0:
                        status_msg += f" (Failed: {failed_count})"
                        
                    download_status[task_id] = {
                        'status': 'completed',
                        'message': status_msg,
                        'progress': 100
                    }
                    
            except Exception as e:
                download_status[task_id] = {
                    'status': 'error',
                    'message': str(e),
                    'progress': 0
                }
            finally:
                if temp_dir and os.path.exists(temp_dir):
                    shutil.rmtree(temp_dir, ignore_errors=True)
                # Auto cleanup duplicates in background
                try:
                    threading.Thread(target=find_and_delete_duplicates, args=('downloads',), daemon=True).start()
                except Exception as de:
                    print(f"Error starting background duplicate clean up: {de}")
                    
        thread = threading.Thread(target=upload_task)
        thread.start()
        
        return jsonify({'task_id': task_id})
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/youtube/info', methods=['POST'])
def youtube_info():
    """Get YouTube video information"""
    try:
        data = request.json
        url = data.get('url')
        
        if not url:
            return jsonify({'error': 'URL is required'}), 400
        
        downloader = YouTubeDownloader()
        info = downloader.get_video_info(url)
        qualities = downloader.get_available_qualities(url)
        
        if not info:
            return jsonify({'error': 'Could not get video information'}), 400
        
        return jsonify({
            'info': info,
            'qualities': qualities
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/youtube/download', methods=['POST'])
def youtube_download():
    """Download YouTube video/audio"""
    try:
        data = request.json
        url = data.get('url')
        format_type = data.get('format', 'mp3')
        quality = data.get('quality', 'best')
        
        if not url:
            return jsonify({'error': 'URL is required'}), 400
        
        task_id = str(uuid.uuid4())
        download_status[task_id] = {
            'status': 'processing',
            'message': 'Starting download...',
            'progress': 0
        }
        
        def download_task():
            temp_dir = None
            try:
                # Use temporary directory
                temp_dir = tempfile.mkdtemp()
                downloader = YouTubeDownloader(download_path=temp_dir)
                
                def progress_hook(d):
                    if d.get('status') == 'downloading':
                        downloaded = d.get('downloaded_bytes', 0)
                        total = d.get('total_bytes', 0)
                        if total > 0:
                            progress = (downloaded / total) * 100
                            download_status[task_id]['progress'] = int(progress)
                            download_status[task_id]['message'] = f"Downloading: {int(progress)}%"
                
                if format_type == 'mp3':
                    filepath = downloader.download_audio(url, progress_hook=progress_hook)
                else:
                    filepath = downloader.download_video(url, quality=quality, progress_hook=progress_hook)
                
                if filepath:
                    # Copy to permanent downloads folder
                    try:
                        perm_folder = os.path.join('downloads', 'youtube')
                        os.makedirs(perm_folder, exist_ok=True)
                        perm_filepath = os.path.join(perm_folder, os.path.basename(filepath))
                        shutil.copy2(filepath, perm_filepath)
                        print(f"DEBUG_APP: Copied YouTube file to {perm_filepath}")
                        # Upload to remote server if configured
                        upload_to_remote_server(perm_filepath)
                    except Exception as copy_e:
                        print(f"DEBUG_APP: Failed to copy YouTube file to permanent folder: {copy_e}")

                    download_status[task_id] = {
                        'status': 'completed',
                        'message': 'Download completed',
                        'progress': 100,
                        'filepath': filepath,
                        'filename': os.path.basename(filepath),
                        'temp_dir': temp_dir
                    }
                else:
                    download_status[task_id] = {
                        'status': 'error',
                        'message': 'Download failed',
                        'progress': 0
                    }
                    if temp_dir and os.path.exists(temp_dir):
                        shutil.rmtree(temp_dir, ignore_errors=True)
            except Exception as e:
                download_status[task_id] = {
                    'status': 'error',
                    'message': str(e),
                    'progress': 0
                }
                if temp_dir and os.path.exists(temp_dir):
                    shutil.rmtree(temp_dir, ignore_errors=True)
        
        thread = threading.Thread(target=download_task)
        thread.start()
        
        return jsonify({'task_id': task_id})
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/instagram/download', methods=['POST'])
def instagram_download():
    """Download Instagram content"""
    try:
        data = request.json
        url = data.get('url')
        
        if not url:
            return jsonify({'error': 'URL is required'}), 400
        
        url_type, _ = parse_instagram_url(url)
        if not url_type:
            return jsonify({'error': 'Invalid Instagram URL'}), 400
        
        task_id = str(uuid.uuid4())
        download_status[task_id] = {
            'status': 'processing',
            'message': f'Downloading {url_type}...',
            'progress': 0
        }
        
        def download_task():
            temp_dir = None
            try:
                # Use temporary directory
                temp_dir = tempfile.mkdtemp()
                downloader = InstagramDownloader(download_path=temp_dir)
                
                if url_type == 'post':
                    results = downloader.download_post(url)
                    if results:
                        try:
                            perm_folder = os.path.join('downloads', 'instagram')
                            os.makedirs(perm_folder, exist_ok=True)
                            for f in results:
                                dest_file = os.path.join(perm_folder, os.path.basename(f))
                                shutil.copy2(f, dest_file)
                                # Upload to remote server if configured
                                upload_to_remote_server(dest_file)
                            print(f"DEBUG_APP: Copied Instagram post files to {perm_folder} and uploaded")
                        except Exception as copy_e:
                            print(f"DEBUG_APP: Failed to copy Instagram post: {copy_e}")

                        download_status[task_id] = {
                            'status': 'completed',
                            'message': f'Downloaded {len(results)} file(s)',
                            'progress': 100,
                            'files': [os.path.basename(f) for f in results],
                            'filepaths': results,
                            'temp_dir': temp_dir
                        }
                    else:
                        download_status[task_id] = {
                            'status': 'error',
                            'message': 'Download failed',
                            'progress': 0
                        }
                        if temp_dir and os.path.exists(temp_dir):
                            shutil.rmtree(temp_dir, ignore_errors=True)
                elif url_type == 'reel':
                    result = downloader.download_reel(url)
                    if result:
                        # Copy to permanent downloads folder
                        try:
                            perm_folder = os.path.join('downloads', 'instagram')
                            os.makedirs(perm_folder, exist_ok=True)
                            dest_file = os.path.join(perm_folder, os.path.basename(result))
                            shutil.copy2(result, dest_file)
                            print(f"DEBUG_APP: Copied Instagram reel file to {perm_folder}")
                            # Upload to remote server if configured
                            upload_to_remote_server(dest_file)
                        except Exception as copy_e:
                            print(f"DEBUG_APP: Failed to copy Instagram reel: {copy_e}")

                        download_status[task_id] = {
                            'status': 'completed',
                            'message': 'Download completed',
                            'progress': 100,
                            'filepath': result,
                            'filename': os.path.basename(result),
                            'temp_dir': temp_dir
                        }
                    else:
                        download_status[task_id] = {
                            'status': 'error',
                            'message': 'Download failed',
                            'progress': 0
                        }
                        if temp_dir and os.path.exists(temp_dir):
                            shutil.rmtree(temp_dir, ignore_errors=True)
                elif url_type == 'story':
                    result = downloader.download_story(url)
                    if result:
                        # Copy to permanent downloads folder
                        try:
                            perm_folder = os.path.join('downloads', 'instagram')
                            os.makedirs(perm_folder, exist_ok=True)
                            dest_file = os.path.join(perm_folder, os.path.basename(result))
                            shutil.copy2(result, dest_file)
                            print(f"DEBUG_APP: Copied Instagram story file to {perm_folder}")
                            # Upload to remote server if configured
                            upload_to_remote_server(dest_file)
                        except Exception as copy_e:
                            print(f"DEBUG_APP: Failed to copy Instagram story: {copy_e}")

                        download_status[task_id] = {
                            'status': 'completed',
                            'message': 'Download completed',
                            'progress': 100,
                            'filepath': result,
                            'filename': os.path.basename(result),
                            'temp_dir': temp_dir
                        }
                    else:
                        download_status[task_id] = {
                            'status': 'error',
                            'message': 'Download failed',
                            'progress': 0
                        }
                        if temp_dir and os.path.exists(temp_dir):
                            shutil.rmtree(temp_dir, ignore_errors=True)
            except Exception as e:
                download_status[task_id] = {
                    'status': 'error',
                    'message': str(e),
                    'progress': 0
                }
                if temp_dir and os.path.exists(temp_dir):
                    shutil.rmtree(temp_dir, ignore_errors=True)
        
        thread = threading.Thread(target=download_task)
        thread.start()
        
        return jsonify({'task_id': task_id, 'type': url_type})
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/terabox/info', methods=['POST'])
def terabox_info():
    """Get Terabox file information"""
    try:
        data = request.json
        url = data.get('url')
        
        if not url:
            return jsonify({'error': 'URL is required'}), 400
        
        downloader = TeraboxDownloader()
        file_info = downloader.get_file_info(url)
        
        if not file_info:
            return jsonify({'error': 'Could not get file information'}), 400
        
        return jsonify({'file_info': file_info})
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/terabox/download', methods=['POST'])
def terabox_download():
    """Download Terabox file"""
    try:
        data = request.json
        url = data.get('url')
        filename = data.get('filename')
        
        if not url:
            return jsonify({'error': 'URL is required'}), 400
        
        task_id = str(uuid.uuid4())
        download_status[task_id] = {
            'status': 'processing',
            'message': 'Starting download...',
            'progress': 0
        }
        
        def download_task():
            temp_dir = None
            try:
                # Use temporary directory
                temp_dir = tempfile.mkdtemp()
                downloader = TeraboxDownloader(download_path=temp_dir)
                
                def progress_hook(d):
                    if d.get('status') == 'downloading':
                        downloaded = d.get('downloaded_bytes', 0)
                        total = d.get('total_bytes', 0)
                        if total > 0:
                            progress = (downloaded / total) * 100
                            download_status[task_id]['progress'] = int(progress)
                            download_status[task_id]['message'] = f"Downloading: {int(progress)}%"
                
                filepath = downloader.download_file(url, filename, progress_hook=progress_hook)
                
                if filepath:
                    # Copy to permanent downloads folder
                    try:
                        perm_folder = os.path.join('downloads', 'terabox')
                        os.makedirs(perm_folder, exist_ok=True)
                        perm_filepath = os.path.join(perm_folder, os.path.basename(filepath))
                        shutil.copy2(filepath, perm_filepath)
                        print(f"DEBUG_APP: Copied Terabox file to {perm_filepath}")
                        # Upload to remote server if configured
                        upload_to_remote_server(perm_filepath)
                    except Exception as copy_e:
                        print(f"DEBUG_APP: Failed to copy Terabox file to permanent folder: {copy_e}")

                    download_status[task_id] = {
                        'status': 'completed',
                        'message': 'Download completed',
                        'progress': 100,
                        'filepath': filepath,
                        'filename': os.path.basename(filepath),
                        'temp_dir': temp_dir
                    }
                else:
                    download_status[task_id] = {
                        'status': 'error',
                        'message': 'Download failed',
                        'progress': 0
                    }
                    if temp_dir and os.path.exists(temp_dir):
                        shutil.rmtree(temp_dir, ignore_errors=True)
            except Exception as e:
                download_status[task_id] = {
                    'status': 'error',
                    'message': str(e),
                    'progress': 0
                }
                if temp_dir and os.path.exists(temp_dir):
                    shutil.rmtree(temp_dir, ignore_errors=True)
        
        thread = threading.Thread(target=download_task)
        thread.start()
        
        return jsonify({'task_id': task_id})
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/status/<task_id>', methods=['GET'])
def get_status(task_id):
    """Get download status"""
    status = download_status.get(task_id, {'status': 'not_found'})
    return jsonify(status)

@app.route('/api/download/<task_id>', methods=['GET'])
def download_file(task_id):
    """Download completed file and delete after sending"""
    status = download_status.get(task_id)
    if not status or status.get('status') != 'completed':
        return jsonify({'error': 'File not ready'}), 404
    
    filepath = status.get('filepath')
    if not filepath or not os.path.exists(filepath):
        return jsonify({'error': 'File not found'}), 404
    
    filename = status.get('filename', os.path.basename(filepath))
    temp_dir = status.get('temp_dir')
    
    def remove_file():
        """Remove file and temp directory after sending"""
        try:
            if filepath and os.path.exists(filepath):
                os.remove(filepath)
            if temp_dir and os.path.exists(temp_dir):
                shutil.rmtree(temp_dir, ignore_errors=True)
        except:
            pass
    
    # Send file and schedule cleanup
    response = send_file(filepath, as_attachment=True, download_name=filename)
    
    # Clean up after response is sent
    @response.call_on_close
    def cleanup():
        remove_file()
    
    return response

@app.route('/api/file/<path:filepath>', methods=['GET'])
def download_file_by_path(filepath):
    """Download file by path (for downloads list)"""
    # Security: ensure file is in downloads directory
    if not filepath.startswith('downloads/'):
        return jsonify({'error': 'Invalid file path'}), 403
    
    if not os.path.exists(filepath):
        return jsonify({'error': 'File not found'}), 404
    
    return send_file(filepath, as_attachment=True)

@app.route('/api/files', methods=['GET'])
def list_files():
    """List downloaded files in the downloads directory"""
    files = []
    downloads_dir = 'downloads'
    if os.path.exists(downloads_dir):
        for root, dirs, filenames in os.walk(downloads_dir):
            for filename in filenames:
                filepath = os.path.join(root, filename)
                # Ignore temporary or hidden system files
                if filename.startswith('.') or filename.endswith('.tmp') or filename.endswith('.zip'):
                    continue
                # Ensure it's a file
                if os.path.isfile(filepath):
                    # Get path relative to the workspace root, formatted with forward slashes
                    rel_path = os.path.relpath(filepath, '.').replace('\\', '/')
                    # Ensure path starts with downloads/
                    if rel_path.startswith('downloads/'):
                        files.append({
                            'name': filename,
                            'path': rel_path,
                            'size': os.path.getsize(filepath)
                        })
    return jsonify({'files': files})

@app.route('/api/zip/playlist/<task_id>', methods=['GET'])
def download_playlist_zip(task_id):
    """Download playlist as ZIP file from task and delete after"""
    try:
        status = download_status.get(task_id)
        if not status or status.get('status') != 'completed':
            return jsonify({'error': 'Playlist not ready'}), 404
        
        playlist_path = status.get('folder')
        if not playlist_path or not os.path.exists(playlist_path):
            return jsonify({'error': 'Playlist folder not found'}), 404
        
        # Create temporary ZIP file
        zip_filename = status.get('playlist_name', 'playlist') + '.zip'
        temp_zip = tempfile.NamedTemporaryFile(delete=False, suffix='.zip')
        temp_zip.close()
        
        # Create ZIP file
        with zipfile.ZipFile(temp_zip.name, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for root, dirs, files in os.walk(playlist_path):
                for file in files:
                    file_path = os.path.join(root, file)
                    arcname = os.path.relpath(file_path, playlist_path)
                    zipf.write(file_path, arcname)
        
        def cleanup():
            """Clean up ZIP and temp directory"""
            try:
                if os.path.exists(temp_zip.name):
                    os.remove(temp_zip.name)
                temp_dir = status.get('temp_dir')
                if temp_dir and os.path.exists(temp_dir):
                    shutil.rmtree(temp_dir, ignore_errors=True)
            except:
                pass
        
        # Send file and schedule cleanup
        response = send_file(temp_zip.name, as_attachment=True, download_name=zip_filename)
        
        @response.call_on_close
        def cleanup_on_close():
            cleanup()
        
        return response
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/zip/tracks', methods=['POST'])
def download_tracks_zip():
    """Download multiple tracks as ZIP file"""
    try:
        data = request.json
        track_paths = data.get('paths', [])
        
        if not track_paths:
            return jsonify({'error': 'No tracks specified'}), 400
        
        # Security: ensure all paths are in downloads directory
        for path in track_paths:
            if not path.startswith('downloads/'):
                return jsonify({'error': 'Invalid path'}), 403
            if not os.path.exists(path):
                return jsonify({'error': f'File not found: {path}'}), 404
        
        # Create ZIP file
        zip_filename = 'tracks.zip'
        zip_path = os.path.join('downloads', zip_filename)
        
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for file_path in track_paths:
                if os.path.exists(file_path):
                    zipf.write(file_path, os.path.basename(file_path))
        
        return send_file(zip_path, as_attachment=True, download_name=zip_filename)
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/playlists', methods=['GET'])
def list_playlists():
    """List all playlists from active tasks"""
    playlists = []
    # Only return playlists from active download tasks
    for task_id, status in download_status.items():
        if status.get('status') == 'completed' and status.get('folder'):
            playlists.append({
                'name': status.get('playlist_name', 'Unknown'),
                'task_id': task_id,
                'file_count': status.get('downloaded', 0)
            })
    
    return jsonify({'playlists': playlists})

@app.route('/api/admin/clean-duplicates', methods=['POST'])
def clean_duplicates():
    """Scan and delete duplicate files from downloads directory"""
    try:
        deleted_files, cleared_mb = find_and_delete_duplicates('downloads')
        return jsonify({
            'success': True,
            'deleted_count': len(deleted_files),
            'deleted_files': [os.path.basename(f) for f in deleted_files],
            'cleared_mb': round(cleared_mb, 2)
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

if __name__ == '__main__':
    # Create necessary directories
    for folder in ['downloads', 'templates', 'static/css', 'static/js']:
        os.makedirs(folder, exist_ok=True)
    
    port = int(os.environ.get('PORT', 7860))
    app.run(debug=False, host='0.0.0.0', port=port)


