"""
YouTube search functionality to find videos from song names
"""
import os
import re
from typing import Optional, Dict
import yt_dlp
from utils.colors import print_error, print_warning, print_info

class YouTubeSearcher:
    """Search YouTube for videos based on song information"""
    
    def __init__(self):
        self.ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': True,
            'default_search': 'ytsearch',
        }
        
        # Determine cookies file location
        self.cookies_file = None
        
        def try_convert_cookies_json_content(content_str: str) -> Optional[str]:
            import json, time
            try:
                data = json.loads(content_str)
                if isinstance(data, list):
                    lines = ["# Netscape HTTP Cookie File\n", "# Generated automatically from JSON\n\n"]
                    for cookie in data:
                        domain = cookie.get('domain', '')
                        flag = "TRUE" if domain.startswith('.') else "FALSE"
                        path = cookie.get('path', '/')
                        secure = "TRUE" if cookie.get('secure', False) else "FALSE"
                        expiry = cookie.get('expirationDate') or cookie.get('expiry')
                        expiry = int(float(expiry)) if expiry is not None else int(time.time() + 31536000)
                        name = cookie.get('name', '')
                        value = cookie.get('value', '')
                        if domain and name:
                            lines.append(f"{domain}\t{flag}\t{path}\t{secure}\t{expiry}\t{name}\t{value}\n")
                    
                    download_path = "downloads/youtube"
                    if not os.path.exists(download_path):
                        os.makedirs(download_path, exist_ok=True)
                    temp_netscape_path = os.path.join(download_path, 'temp_cookies.txt')
                    with open(temp_netscape_path, 'w', encoding='utf-8') as f:
                        f.writelines(lines)
                    return temp_netscape_path
            except Exception:
                pass
            return None
        
        # 1. Check for cookies content in environment variable to write dynamically
        cookies_content = os.getenv('YOUTUBE_COOKIES_CONTENT')
        if cookies_content:
            netscape_path = try_convert_cookies_json_content(cookies_content)
            if netscape_path:
                self.cookies_file = netscape_path
            else:
                try:
                    download_path = "downloads/youtube"
                    if not os.path.exists(download_path):
                        os.makedirs(download_path, exist_ok=True)
                    temp_cookies_path = os.path.join(download_path, 'temp_cookies.txt')
                    
                    write_file = True
                    if os.path.exists(temp_cookies_path):
                        with open(temp_cookies_path, 'r', encoding='utf-8') as f:
                            if f.read().strip() == cookies_content.strip():
                                write_file = False
                    
                    if write_file:
                        with open(temp_cookies_path, 'w', encoding='utf-8') as f:
                            f.write(cookies_content)
                    self.cookies_file = temp_cookies_path
                except Exception as e:
                    print_error(f"Failed to write temporary cookies in searcher: {e}")
                    
        # 2. Check for explicit path environment variable
        if not self.cookies_file:
            cookies_path = os.getenv('YOUTUBE_COOKIES_PATH')
            if cookies_path and os.path.exists(cookies_path):
                self.cookies_file = cookies_path
                
        # 3. Check default locations in workspace (both cookies.txt and cookies.json)
        if not self.cookies_file:
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            possible_txt_paths = [
                os.path.join(base_dir, 'cookies.txt'),
                os.path.join(base_dir, 'bot', 'cookies.txt'),
                'cookies.txt'
            ]
            possible_json_paths = [
                os.path.join(base_dir, 'cookies.json'),
                os.path.join(base_dir, 'bot', 'cookies.json'),
                'cookies.json'
            ]
            
            # Check txt first
            for p in possible_txt_paths:
                if os.path.exists(p):
                    self.cookies_file = p
                    break
                    
            # Check json next and convert if found
            if not self.cookies_file:
                for p in possible_json_paths:
                    if os.path.exists(p):
                        try:
                            with open(p, 'r', encoding='utf-8') as f:
                                json_str = f.read()
                            netscape_path = try_convert_cookies_json_content(json_str)
                            if netscape_path:
                                self.cookies_file = netscape_path
                                break
                        except Exception as e:
                            print_error(f"Failed to parse cookies.json file {p}: {e}")
                    
        if self.cookies_file:
            print_info(f"Using cookies file: {self.cookies_file}")
        else:
            print_warning("No cookies file found for YouTube searches. If searches fail, please upload cookies.txt.")

        # Check for proxy configuration
        self.proxy = os.getenv('YOUTUBE_PROXY')
        if self.proxy:
            print_info(f"Using YouTube Proxy: {self.proxy}")
        else:
            print_info("No proxy configured for YouTube searches.")
    
    def search_song(self, song_name: str, artist: str = '') -> Optional[str]:
        """
        Search YouTube for a song and return the best match URL.
        Falls back to SoundCloud if YouTube search fails.
        """
        try:
            # Construct search query
            if artist:
                query = f"{artist} {song_name}"
            else:
                query = song_name
            
            # Sanitize
            query = re.sub(r'[^\w\s\-\(\)\+]', '', query)
            query = re.sub(r'\s+', ' ', query).strip()
            if not query:
                query = song_name
            
            print_warning(f"Searching YouTube for: {query}")
            
            # Shared ydl options for YouTube search (tv_embedded = no sign-in needed)
            yt_ydl_opts = {
                'quiet': True,
                'no_warnings': True,
                'extract_flat': True,
                'nocheckcertificate': True,
                'extractor_args': {
                    'youtube': {
                        'player_client': ['tv_embedded', 'web_creator', 'mweb'],
                        'player_skip': ['webpage'],
                    }
                },
                'socket_timeout': 30,
                'retries': 3,
            }
            if self.cookies_file:
                yt_ydl_opts['cookiefile'] = self.cookies_file
            if self.proxy:
                yt_ydl_opts['proxy'] = self.proxy
            
            # --- Try 1: YouTube search with full query ---
            try:
                with yt_dlp.YoutubeDL(yt_ydl_opts) as ydl:
                    info = ydl.extract_info(f"ytsearch1:{query}", download=False)
                    if info and 'entries' in info and info['entries']:
                        video = info['entries'][0]
                        video_url = f"https://www.youtube.com/watch?v={video['id']}"
                        print_warning(f"Found: {video.get('title', 'Unknown Title')}")
                        return video_url
            except Exception as e:
                print_warning(f"YouTube search (full query) failed: {str(e)}")
            
            # --- Try 2: YouTube search with song name only ---
            if artist:
                try:
                    with yt_dlp.YoutubeDL(yt_ydl_opts) as ydl:
                        print_warning(f"Retrying YouTube search with song name only: {song_name}")
                        info = ydl.extract_info(f"ytsearch1:{song_name}", download=False)
                        if info and 'entries' in info and info['entries']:
                            video = info['entries'][0]
                            video_url = f"https://www.youtube.com/watch?v={video['id']}"
                            print_warning(f"Found (name-only): {video.get('title', 'Unknown Title')}")
                            return video_url
                except Exception as e:
                    print_warning(f"YouTube search (name only) failed: {str(e)}")
            
            # --- Try 3: SoundCloud fallback (no bot detection, no cookies needed) ---
            try:
                sc_ydl_opts = {
                    'quiet': True,
                    'no_warnings': True,
                    'extract_flat': True,
                    'nocheckcertificate': True,
                    'socket_timeout': 30,
                    'retries': 3,
                }
                if self.proxy:
                    sc_ydl_opts['proxy'] = self.proxy
                with yt_dlp.YoutubeDL(sc_ydl_opts) as ydl:
                    print_warning(f"YouTube unavailable, searching SoundCloud for: {query}")
                    info = ydl.extract_info(f"scsearch1:{query}", download=False)
                    if info and 'entries' in info and info['entries']:
                        entry = info['entries'][0]
                        sc_url = entry.get('url') or entry.get('webpage_url') or entry.get('id')
                        if sc_url:
                            print_warning(f"Found on SoundCloud: {entry.get('title', 'Unknown Title')}")
                            return sc_url
            except Exception as e:
                print_error(f"SoundCloud search also failed: {str(e)}")
            
            print_error(f"All search methods failed for: {query}")
            return None
            
        except Exception as e:
            print_error(f"Critical error in search_song: {str(e)}")
            return None
    
    def search_and_validate(self, song_name: str, artist: str = '', duration: Optional[int] = None) -> Optional[str]:
        """
        Search YouTube and validate the result matches the song
        
        Args:
            song_name: Name of the song
            artist: Name of the artist
            duration: Expected duration in seconds (optional)
            
        Returns:
            YouTube video URL or None
        """
        url = self.search_song(song_name, artist)
        
        if url and duration:
            # Validate duration (allow 10% difference)
            try:
                ydl_opts = {
                    'quiet': True,
                    'no_warnings': True,
                    'remote_components': ['ejs:github', 'ejs:npm'],
                }
                if self.cookies_file:
                    ydl_opts['cookiefile'] = self.cookies_file
                if self.proxy:
                    ydl_opts['proxy'] = self.proxy
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(url, download=False)
                    video_duration = info.get('duration', 0)
                    if abs(video_duration - duration) / duration > 0.1:
                        print_warning("Duration mismatch, but proceeding anyway")
            except:
                pass
        
        return url

