"""
YouTube downloader using yt-dlp
"""
import os
from typing import Optional, List, Dict
import yt_dlp
from utils.helpers import create_folder, sanitize_filename
from utils.colors import print_error, print_info, print_success, print_warning

class YouTubeDownloader:
    """Download videos and audio from YouTube"""
    
    def __init__(self, download_path: str = "downloads/youtube"):
        self.download_path = download_path
        create_folder(self.download_path)
        
        # Check for cookies content or path to use with yt-dlp
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
                    
                    temp_netscape_path = os.path.join(self.download_path, 'temp_cookies.txt')
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
                print_info("Dynamically converted and loaded JSON cookies from YOUTUBE_COOKIES_CONTENT.")
            else:
                try:
                    temp_cookies_path = os.path.join(self.download_path, 'temp_cookies.txt')
                    write_file = True
                    if os.path.exists(temp_cookies_path):
                        with open(temp_cookies_path, 'r', encoding='utf-8') as f:
                            if f.read().strip() == cookies_content.strip():
                                write_file = False
                    
                    if write_file:
                        with open(temp_cookies_path, 'w', encoding='utf-8') as f:
                            f.write(cookies_content)
                    self.cookies_file = temp_cookies_path
                    print_info("Dynamically loaded Netscape cookies from YOUTUBE_COOKIES_CONTENT.")
                except Exception as e:
                    print_error(f"Failed to write temporary cookies: {e}")
                
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
                                print_info(f"Dynamically converted and used JSON cookies file: {p}")
                                break
                        except Exception as e:
                            print_error(f"Failed to parse cookies.json file {p}: {e}")
                    
        if self.cookies_file:
            print_info(f"Using cookies file: {self.cookies_file}")
        else:
            print_warning("No cookies file found for YouTube downloads. If downloads fail with bot blocks, please upload cookies.txt.")
            
        # Check for proxy configuration
        self.proxy = os.getenv('YOUTUBE_PROXY')
        if self.proxy:
            print_info(f"Using YouTube Proxy: {self.proxy}")
        else:
            print_info("No proxy configured for YouTube downloads.")
    
    def get_video_info(self, url: str) -> Optional[Dict]:
        """
        Get video information without downloading
        
        Args:
            url: YouTube video URL
            
        Returns:
            Dictionary with video info or None
        """
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
                return {
                    'title': info.get('title', 'Unknown'),
                    'duration': info.get('duration', 0),
                    'uploader': info.get('uploader', 'Unknown'),
                    'thumbnail': info.get('thumbnail', ''),
                    'formats': info.get('formats', []),
                }
        except Exception as e:
            print_error(f"Error getting video info: {str(e)}")
            return None
    
    def get_available_qualities(self, url: str) -> List[Dict]:
        """
        Get list of available video qualities
        
        Args:
            url: YouTube video URL
            
        Returns:
            List of quality dictionaries
        """
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
                formats = info.get('formats', [])
                
                # Filter video formats
                video_formats = []
                seen_heights = set()
                
                for fmt in formats:
                    if fmt.get('vcodec') != 'none':  # Has video
                        height = fmt.get('height')
                        if height and height not in seen_heights:
                            seen_heights.add(height)
                            video_formats.append({
                                'format_id': fmt.get('format_id'),
                                'height': height,
                                'ext': fmt.get('ext', 'mp4'),
                                'filesize': fmt.get('filesize', 0),
                                'quality': f"{height}p",
                            })
                
                # Sort by height descending
                video_formats.sort(key=lambda x: x['height'], reverse=True)
                return video_formats
                
        except Exception as e:
            print_error(f"Error getting qualities: {str(e)}")
            return []
    
    def download_audio(self, url: str, output_filename: Optional[str] = None, 
                      progress_hook=None, fallback_query: Optional[str] = None) -> Optional[str]:
        """
        Download audio as MP3. Supports YouTube and SoundCloud URLs.
        When YouTube is bot-blocked, automatically falls back to SoundCloud
        if fallback_query (e.g. "Artist - Title") is provided.
        
        Args:
            url: YouTube or SoundCloud video/track URL
            output_filename: Optional output filename
            progress_hook: Optional progress callback
            fallback_query: Search query to use for SoundCloud fallback (e.g. "Artist Title")
            
        Returns:
            Path to downloaded file or None
        """
        if output_filename:
            base_name = os.path.splitext(output_filename)[0]
            output_path = os.path.join(self.download_path, base_name + '.%(ext)s')
        else:
            output_path = os.path.join(self.download_path, '%(title)s.%(ext)s')
        
        # Detect source platform
        is_soundcloud = 'soundcloud.com' in url or 'api.soundcloud' in url
        
        def _make_base_opts():
            return {
                'format': 'bestaudio/best',
                'outtmpl': output_path,
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '320',
                }],
                'add_metadata': False,
                'writethumbnail': False,
                'quiet': False,
                'no_warnings': False,
                'nocheckcertificate': True,
                'socket_timeout': 60,
                'retries': 5,
                'fragment_retries': 5,
            }
        
        def _run_download(ydl_opts, download_url):
            """Execute download and return mp3 path or raise."""
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(download_url, download=True)
                filename = ydl.prepare_filename(info)
                mp3_filename = os.path.splitext(filename)[0] + '.mp3'
                if os.path.exists(mp3_filename):
                    print_success(f"Downloaded: {os.path.basename(mp3_filename)}")
                    return mp3_filename
                print_error(f"File not found after download. Expected: {mp3_filename}")
                return None
        
        # ── ATTEMPT 1: Download from provided URL (YouTube or SoundCloud) ──
        try:
            opts = _make_base_opts()
            if is_soundcloud:
                print_info("Downloading from SoundCloud (no bot detection)")
            else:
                # YouTube: use best available player clients
                opts['extractor_args'] = {
                    'youtube': {
                        'player_client': ['tv_embedded', 'web_creator', 'mweb'],
                        'player_skip': ['webpage'],
                    }
                }
                opts['youtube_include_dash_manifest'] = False
                opts['youtube_include_hls_manifest'] = False
                opts['age_limit'] = 25
                opts['user_agent'] = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36'
                if self.cookies_file:
                    opts['cookiefile'] = self.cookies_file
                print_info("Downloading from YouTube (tv_embedded + web_creator clients)")
            if self.proxy:
                opts['proxy'] = self.proxy
            if progress_hook:
                opts['progress_hooks'] = [progress_hook]
            
            result = _run_download(opts, url)
            if result:
                return result
        except Exception as e:
            err_str = str(e)
            is_bot_blocked = any(kw in err_str for kw in [
                'Sign in to confirm', 'bot', 'cookies', 'authentication'
            ])
            print_error(f"Error downloading audio: {err_str}")
            
            if is_bot_blocked and fallback_query and not is_soundcloud:
                print_warning(f"YouTube bot-blocked. Falling back to SoundCloud for: {fallback_query}")
            else:
                return None
        else:
            # No exception but no file either — check fallback
            if not is_soundcloud and fallback_query:
                print_warning(f"YouTube download returned no file. Trying SoundCloud for: {fallback_query}")
            else:
                return None
        
        # ── ATTEMPT 2: SoundCloud fallback ──
        try:
            print_info(f"Searching SoundCloud for: {fallback_query}")
            sc_opts = _make_base_opts()
            if self.proxy:
                sc_opts['proxy'] = self.proxy
            if progress_hook:
                sc_opts['progress_hooks'] = [progress_hook]
            
            sc_search_url = f"scsearch1:{fallback_query}"
            result = _run_download(sc_opts, sc_search_url)
            if result:
                print_success(f"SoundCloud fallback succeeded!")
                return result
        except Exception as e:
            print_error(f"SoundCloud fallback also failed: {str(e)}")
        
        return None

    
    def download_video(self, url: str, quality: str = 'best', 
                      output_filename: Optional[str] = None,
                      progress_hook=None) -> Optional[str]:
        """
        Download video in specified quality
        
        Args:
            url: YouTube video URL
            quality: Video quality (e.g., '1080p', '720p', 'best')
            output_filename: Optional output filename
            progress_hook: Optional progress callback
            
        Returns:
            Path to downloaded file or None
        """
        try:
            if output_filename:
                output_path = os.path.join(self.download_path, output_filename)
            else:
                output_path = os.path.join(self.download_path, '%(title)s.%(ext)s')
            
            # Determine format selector based on quality
            if quality == 'best':
                format_selector = 'bestvideo+bestaudio/best'
            else:
                # Extract height from quality string (e.g., '1080p' -> 1080)
                height = quality.replace('p', '').replace('P', '')
                try:
                    height_int = int(height)
                    format_selector = f'bestvideo[height<={height_int}]+bestaudio/best[height<={height_int}]'
                except:
                    format_selector = 'bestvideo+bestaudio/best'
            
            ydl_opts = {
                'format': format_selector,
                'outtmpl': output_path,
                'merge_output_format': 'mp4',
                'quiet': False,
                'no_warnings': False,
                'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'nocheckcertificate': True,
                'extractor_args': {'youtube': {'player_client': ['web_creator', 'ios', 'android', 'mweb', 'web']}},
                'youtube_include_dash_manifest': False,
                'youtube_include_hls_manifest': False,
                'socket_timeout': 30,
                'retries': 5,
                'remote_components': ['ejs:github', 'ejs:npm'],
            }
            if self.cookies_file:
                ydl_opts['cookiefile'] = self.cookies_file
            if self.proxy:
                ydl_opts['proxy'] = self.proxy
            
            if progress_hook:
                ydl_opts['progress_hooks'] = [progress_hook]
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                filename = ydl.prepare_filename(info)
                # Ensure .mp4 extension
                if not filename.endswith('.mp4'):
                    mp4_filename = os.path.splitext(filename)[0] + '.mp4'
                    if os.path.exists(mp4_filename):
                        filename = mp4_filename
                
                if os.path.exists(filename):
                    print_success(f"Downloaded: {os.path.basename(filename)}")
                    return filename
            
            return None
            
        except Exception as e:
            msg = f"Error downloading video: {str(e)}"
            print_error(msg)
            return None

