"""
Helper utility functions
"""
import os
import re
from pathlib import Path
from typing import Optional, Tuple
from urllib.parse import urlparse, parse_qs

def create_folder(folder_path: str) -> str:
    """
    Create folder if it doesn't exist
    
    Args:
        folder_path: Path to folder
        
    Returns:
        Created folder path
    """
    Path(folder_path).mkdir(parents=True, exist_ok=True)
    return folder_path

def sanitize_filename(filename: str) -> str:
    """
    Sanitize filename by removing invalid characters
    
    Args:
        filename: Original filename
        
    Returns:
        Sanitized filename
    """
    # Remove invalid characters for Windows/Linux/Mac and potential ffmpeg issue chars
    invalid_chars = r'[<>:"/\\|?*,]'
    filename = re.sub(invalid_chars, '_', filename)
    # Remove leading/trailing spaces and dots
    filename = filename.strip(' .')
    # Limit length
    if len(filename) > 200:
        filename = filename[:200]
    return filename

def get_file_size_mb(file_path: str) -> float:
    """
    Get file size in MB
    
    Args:
        file_path: Path to file
        
    Returns:
        File size in MB
    """
    if os.path.exists(file_path):
        return os.path.getsize(file_path) / (1024 * 1024)
    return 0.0

def parse_spotify_url(url: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Parse Spotify URL to extract type and ID
    Supports multiple formats:
    - Regular URLs: https://open.spotify.com/track/...
    - Embed URLs: https://open.spotify.com/embed/track/...
    - URI format: spotify:track:...
    
    Args:
        url: Spotify URL or URI
        
    Returns:
        Tuple of (type, id) or (None, None) if invalid
    """
    # Patterns for different URL formats
    patterns = {
        'track': [
            r'spotify\.com/track/([a-zA-Z0-9]+)',  # Regular URL
            r'spotify\.com/embed/track/([a-zA-Z0-9]+)',  # Embed URL
            r'spotify:track:([a-zA-Z0-9]+)',  # URI format
        ],
        'playlist': [
            r'spotify\.com/playlist/([a-zA-Z0-9]+)',  # Regular URL
            r'spotify\.com/embed/playlist/([a-zA-Z0-9]+)',  # Embed URL
            r'spotify:playlist:([a-zA-Z0-9]+)',  # URI format
        ],
        'album': [
            r'spotify\.com/album/([a-zA-Z0-9]+)',  # Regular URL
            r'spotify\.com/embed/album/([a-zA-Z0-9]+)',  # Embed URL
            r'spotify:album:([a-zA-Z0-9]+)',  # URI format
        ],
    }
    
    for url_type, type_patterns in patterns.items():
        for pattern in type_patterns:
            match = re.search(pattern, url)
            if match:
                return url_type, match.group(1)
    
    return None, None

def parse_youtube_url(url: str) -> Optional[str]:
    """
    Parse YouTube URL to extract video ID
    
    Args:
        url: YouTube URL
        
    Returns:
        Video ID or None if invalid
    """
    patterns = [
        r'(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/embed/)([a-zA-Z0-9_-]{11})',
        r'youtube\.com/watch\?.*v=([a-zA-Z0-9_-]{11})',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    
    return None

def parse_instagram_url(url: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Parse Instagram URL to extract type and shortcode
    
    Args:
        url: Instagram URL
        
    Returns:
        Tuple of (type, shortcode) or (None, None) if invalid
    """
    patterns = {
        'post': r'instagram\.com/p/([a-zA-Z0-9_-]+)',
        'reel': r'instagram\.com/reel/([a-zA-Z0-9_-]+)',
        'story': r'instagram\.com/stories/([a-zA-Z0-9_-]+)',
    }
    
    for url_type, pattern in patterns.items():
        match = re.search(pattern, url)
        if match:
            return url_type, match.group(1)
    
    return None, None

def format_duration(seconds: float) -> str:
    """
    Format duration in seconds to MM:SS format
    
    Args:
        seconds: Duration in seconds
        
    Returns:
        Formatted duration string
    """
    minutes = int(seconds // 60)
    secs = int(seconds % 60)
    return f"{minutes:02d}:{secs:02d}"

def format_file_size(size_bytes: int) -> str:
    """
    Format file size in human-readable format
    
    Args:
        size_bytes: Size in bytes
        
    Returns:
        Formatted size string
    """
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.2f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.2f} TB"

def parse_terabox_url(url: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Parse Terabox URL to extract type and share code
    
    Args:
        url: Terabox share URL
        
    Returns:
        Tuple of (type, share_code) or (None, None) if invalid
    """
    patterns = {
        'file': [
            r'terabox\.com/s/([a-zA-Z0-9_-]+)',
            r'1024tera\.com/s/([a-zA-Z0-9_-]+)',
        ],
        'folder': [
            r'terabox\.com/share/([a-zA-Z0-9_-]+)',
            r'1024tera\.com/share/([a-zA-Z0-9_-]+)',
        ],
    }
    
    for url_type, type_patterns in patterns.items():
        for pattern in type_patterns:
            match = re.search(pattern, url)
            if match:
                return url_type, match.group(1)
    
    return None, None

def upload_to_remote_server(filepath: str) -> bool:
    """
    Upload a file to the configured remote Python server
    
    Args:
        filepath: Path to local file to upload
        
    Returns:
        True if upload succeeded, False otherwise
    """
    import requests
    
    url = os.getenv('REMOTE_SERVER_URL')
    if not url:
        return False
        
    api_key = os.getenv('REMOTE_SERVER_API_KEY', '')
    
    if not os.path.exists(filepath):
        print(f"Error uploading to remote server: local file '{filepath}' does not exist.")
        return False
        
    print(f"[UPLOAD] Uploading '{os.path.basename(filepath)}' to remote server '{url}'...")
    
    headers = {}
    if api_key:
        headers['X-API-Key'] = api_key
        
    try:
        with open(filepath, 'rb') as f:
            files = {'file': (os.path.basename(filepath), f)}
            resp = requests.post(url, files=files, headers=headers, timeout=120)
            
        if resp.status_code == 200:
            print(f"[SUCCESS] Successfully uploaded file to remote server: {resp.json()}")
            return True
        else:
            print(f"[ERROR] Remote server returned error: {resp.status_code} - {resp.text}")
            return False
    except Exception as e:
        print(f"[ERROR] Exception uploading file to remote server: {e}")
        return False


def load_cf_worker_config() -> bool:
    """
    Attempt to load configuration variables dynamically from a Cloudflare Worker.
    Looks for environment variables:
    - CF_WORKER_URL: URL of the worker (e.g. https://xxxx.workers.dev)
    - CF_WORKER_AUTH_KEY: Authentication token
    
    If present, fetches config via GET /api/config and populates os.environ.
    Returns True if successfully retrieved, False otherwise.
    """
    import os
    import requests
    
    cf_url = os.getenv('CF_WORKER_URL')
    cf_auth = os.getenv('CF_WORKER_AUTH_KEY', 'divqofy_secret_auth_token_2026')
    
    if not cf_url:
        return False
        
    cf_url = cf_url.rstrip('/')
    config_endpoint = f"{cf_url}/api/config"
    
    print(f"[CONFIG] Attempting to retrieve config from Cloudflare Worker: {config_endpoint}")
    
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
            print("[CONFIG] Successfully fetched and loaded configuration from Cloudflare Worker into memory.")
            return True
        else:
            print(f"[CONFIG] Cloudflare Worker returned status code: {resp.status_code} - {resp.text}")
            return False
    except Exception as e:
        print(f"[CONFIG] Error requesting config from Cloudflare Worker: {e}")
        return False



