"""
Instagram downloader for reels, stories, and posts
"""
import os
import re
import requests
from typing import Optional, Dict, List
from bs4 import BeautifulSoup
from utils.helpers import create_folder, sanitize_filename, parse_instagram_url
from utils.colors import print_error, print_success, print_warning

class InstagramDownloader:
    """Download media from Instagram"""
    
    def __init__(self, download_path: str = "downloads/instagram"):
        self.download_path = download_path
        create_folder(self.download_path)
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })
    
    def download_post(self, url: str) -> Optional[List[str]]:
        """
        Download Instagram post (images/videos)
        
        Args:
            url: Instagram post URL
            
        Returns:
            List of downloaded file paths or None
        """
        try:
            url_type, shortcode = parse_instagram_url(url)
            if url_type != 'post':
                print_error("Invalid Instagram post URL")
                return None
            
            response = self.session.get(url, timeout=10)
            response.raise_for_status()
            
            # Parse HTML to find media URLs
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Look for JSON data in script tags
            scripts = soup.find_all('script', type='text/javascript')
            media_urls = []
            
            for script in scripts:
                if script.string:
                    # Look for image URLs
                    img_matches = re.findall(r'"display_url":"([^"]+)"', script.string)
                    media_urls.extend(img_matches)
                    
                    # Look for video URLs
                    video_matches = re.findall(r'"video_url":"([^"]+)"', script.string)
                    media_urls.extend(video_matches)
            
            # Alternative: Look in meta tags
            if not media_urls:
                meta_tags = soup.find_all('meta', property=True)
                for meta in meta_tags:
                    prop = meta.get('property', '')
                    content = meta.get('content', '')
                    if 'og:image' in prop or 'og:video' in prop:
                        if content and content not in media_urls:
                            media_urls.append(content)
            
            if not media_urls:
                print_error("Could not find media URLs. The post might be private or the URL format has changed.")
                return None
            
            downloaded_files = []
            for i, media_url in enumerate(media_urls):
                try:
                    # Determine file extension
                    if 'video' in media_url.lower() or '.mp4' in media_url.lower():
                        ext = '.mp4'
                        folder = os.path.join(self.download_path, 'posts')
                    else:
                        ext = '.jpg'
                        folder = os.path.join(self.download_path, 'posts')
                    
                    create_folder(folder)
                    
                    # Download media
                    media_response = self.session.get(media_url, timeout=30, stream=True)
                    media_response.raise_for_status()
                    
                    filename = f"post_{shortcode}_{i+1}{ext}"
                    filepath = os.path.join(folder, sanitize_filename(filename))
                    
                    with open(filepath, 'wb') as f:
                        for chunk in media_response.iter_content(chunk_size=8192):
                            f.write(chunk)
                    
                    downloaded_files.append(filepath)
                    print_success(f"Downloaded: {os.path.basename(filepath)}")
                    
                except Exception as e:
                    print_error(f"Error downloading media {i+1}: {str(e)}")
            
            return downloaded_files if downloaded_files else None
            
        except Exception as e:
            print_error(f"Error downloading Instagram post: {str(e)}")
            return None
    
    def download_reel(self, url: str) -> Optional[str]:
        """
        Download Instagram reel
        
        Args:
            url: Instagram reel URL
            
        Returns:
            Path to downloaded file or None
        """
        try:
            url_type, shortcode = parse_instagram_url(url)
            if url_type != 'reel':
                print_error("Invalid Instagram reel URL")
                return None
            
            response = self.session.get(url, timeout=10)
            response.raise_for_status()
            
            # Parse HTML to find video URL
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Look for video URL in script tags
            scripts = soup.find_all('script', type='text/javascript')
            video_url = None
            
            for script in scripts:
                if script.string:
                    # Look for video URL
                    matches = re.findall(r'"video_url":"([^"]+)"', script.string)
                    if matches:
                        video_url = matches[0].replace('\\u0026', '&')
                        break
            
            # Alternative: Look in meta tags
            if not video_url:
                meta_tags = soup.find_all('meta', property=True)
                for meta in meta_tags:
                    prop = meta.get('property', '')
                    content = meta.get('content', '')
                    if 'og:video' in prop:
                        video_url = content
                        break
            
            if not video_url:
                print_error("Could not find video URL. The reel might be private.")
                return None
            
            # Download video
            folder = os.path.join(self.download_path, 'reels')
            create_folder(folder)
            
            video_response = self.session.get(video_url, timeout=30, stream=True)
            video_response.raise_for_status()
            
            filename = f"reel_{shortcode}.mp4"
            filepath = os.path.join(folder, sanitize_filename(filename))
            
            with open(filepath, 'wb') as f:
                for chunk in video_response.iter_content(chunk_size=8192):
                    f.write(chunk)
            
            print_success(f"Downloaded: {os.path.basename(filepath)}")
            return filepath
            
        except Exception as e:
            print_error(f"Error downloading Instagram reel: {str(e)}")
            return None
    
    def download_story(self, url: str) -> Optional[str]:
        """
        Download Instagram story (public only)
        
        Args:
            url: Instagram story URL
            
        Returns:
            Path to downloaded file or None
        """
        try:
            url_type, shortcode = parse_instagram_url(url)
            if url_type != 'story':
                print_error("Invalid Instagram story URL")
                return None
            
            print_warning("Story downloads require authentication. This is a simplified version.")
            print_warning("For full functionality, consider using instaloader library.")
            
            # Note: Stories require authentication, so this is a basic implementation
            # For production, use instaloader or similar library
            response = self.session.get(url, timeout=10)
            
            if response.status_code == 404 or 'login' in response.url.lower():
                print_error("Story is private or requires login. Cannot download.")
                return None
            
            # Try to extract media URL (similar to post/reel)
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Look for media URL
            scripts = soup.find_all('script', type='text/javascript')
            media_url = None
            
            for script in scripts:
                if script.string:
                    # Look for video or image URL
                    video_matches = re.findall(r'"video_url":"([^"]+)"', script.string)
                    img_matches = re.findall(r'"display_url":"([^"]+)"', script.string)
                    
                    if video_matches:
                        media_url = video_matches[0].replace('\\u0026', '&')
                        ext = '.mp4'
                    elif img_matches:
                        media_url = img_matches[0]
                        ext = '.jpg'
                    
                    if media_url:
                        break
            
            if not media_url:
                print_error("Could not find story media. Stories may require authentication.")
                return None
            
            # Download media
            folder = os.path.join(self.download_path, 'stories')
            create_folder(folder)
            
            media_response = self.session.get(media_url, timeout=30, stream=True)
            media_response.raise_for_status()
            
            filename = f"story_{shortcode}{ext}"
            filepath = os.path.join(folder, sanitize_filename(filename))
            
            with open(filepath, 'wb') as f:
                for chunk in media_response.iter_content(chunk_size=8192):
                    f.write(chunk)
            
            print_success(f"Downloaded: {os.path.basename(filepath)}")
            return filepath
            
        except Exception as e:
            print_error(f"Error downloading Instagram story: {str(e)}")
            return None

