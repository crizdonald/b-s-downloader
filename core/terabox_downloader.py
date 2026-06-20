"""
Terabox downloader - Download files from Terabox links
"""
import os
import re
import requests
from typing import Optional, Dict, List
from bs4 import BeautifulSoup
from utils.helpers import create_folder, sanitize_filename
from utils.colors import print_error, print_success, print_warning

class TeraboxDownloader:
    """Download files from Terabox"""
    
    def __init__(self, download_path: str = "downloads/terabox"):
        self.download_path = download_path
        create_folder(self.download_path)
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        })
    
    def parse_terabox_url(self, url: str) -> Optional[Dict]:
        """
        Parse Terabox URL to extract file information
        
        Args:
            url: Terabox share URL
            
        Returns:
            Dictionary with file info or None
        """
        try:
            # Normalize URL
            if 'terabox.com' not in url and '1024tera.com' not in url:
                print_error("Invalid Terabox URL")
                return None
            
            # Extract share code from URL
            share_patterns = [
                r'/s/([a-zA-Z0-9_-]+)',
                r'share\.initdata=([a-zA-Z0-9_-]+)',
                r'pwd=([a-zA-Z0-9_-]+)',
            ]
            
            share_code = None
            for pattern in share_patterns:
                match = re.search(pattern, url)
                if match:
                    share_code = match.group(1)
                    break
            
            response = self.session.get(url, timeout=15, allow_redirects=True)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Try to extract file information
            file_info = {
                'name': 'Unknown File',
                'size': 0,
                'type': 'file',
                'url': url,
                'share_code': share_code,
            }
            
            # Look for file name in title
            title = soup.find('title')
            if title:
                title_text = title.get_text()
                if title_text and title_text != 'Terabox':
                    file_info['name'] = title_text.split(' - ')[0].strip()
            
            # Look for file info in meta tags
            meta_tags = soup.find_all('meta', property=True)
            for meta in meta_tags:
                prop = meta.get('property', '')
                content = meta.get('content', '')
                
                if 'og:title' in prop:
                    file_info['name'] = content
                elif 'og:type' in prop:
                    file_info['type'] = content
            
            # Look for file size
            size_patterns = [
                r'(\d+\.?\d*)\s*(GB|MB|KB|B)',
                r'size["\']?\s*[:=]\s*["\']?(\d+)',
            ]
            
            page_text = response.text
            for pattern in size_patterns:
                match = re.search(pattern, page_text, re.IGNORECASE)
                if match:
                    try:
                        size_value = float(match.group(1))
                        size_unit = match.group(2).upper() if len(match.groups()) > 1 else 'B'
                        # Convert to bytes
                        multipliers = {'B': 1, 'KB': 1024, 'MB': 1024**2, 'GB': 1024**3}
                        file_info['size'] = int(size_value * multipliers.get(size_unit, 1))
                    except:
                        pass
                    break
            
            # Look for download links in script tags
            scripts = soup.find_all('script')
            download_url = None
            
            for script in scripts:
                if script.string:
                    # Look for download URLs
                    url_patterns = [
                        r'["\'](https?://[^"\']*terabox[^"\']*download[^"\']*)["\']',
                        r'downloadUrl["\']?\s*[:=]\s*["\']([^"\']+)["\']',
                        r'fileUrl["\']?\s*[:=]\s*["\']([^"\']+)["\']',
                    ]
                    
                    for pattern in url_patterns:
                        match = re.search(pattern, script.string, re.IGNORECASE)
                        if match:
                            download_url = match.group(1)
                            break
                    
                    if download_url:
                        break
            
            if download_url:
                file_info['download_url'] = download_url
            
            return file_info
            
        except Exception as e:
            print_error(f"Error parsing Terabox URL: {str(e)}")
            return None
    
    def get_file_info(self, url: str) -> Optional[Dict]:
        """
        Get file information without downloading
        
        Args:
            url: Terabox share URL
            
        Returns:
            Dictionary with file info or None
        """
        return self.parse_terabox_url(url)
    
    def download_file(self, url: str, output_filename: Optional[str] = None,
                     progress_hook=None) -> Optional[str]:
        """
        Download file from Terabox
        
        Args:
            url: Terabox share URL
            output_filename: Optional output filename
            progress_hook: Optional progress callback
            
        Returns:
            Path to downloaded file or None
        """
        try:
            file_info = self.parse_terabox_url(url)
            if not file_info:
                print_error("Could not parse Terabox URL")
                return None
            
            # Get download URL
            download_url = file_info.get('download_url')
            if not download_url:
                # Try to construct download URL
                share_code = file_info.get('share_code')
                if share_code:
                    # Try different Terabox download URL patterns
                    base_urls = [
                        f"https://www.terabox.com/api/download?shareid={share_code}",
                        f"https://www.1024tera.com/api/download?shareid={share_code}",
                    ]
                    
                    for base_url in base_urls:
                        try:
                            test_response = self.session.head(base_url, timeout=10, allow_redirects=True)
                            if test_response.status_code == 200:
                                download_url = test_response.url
                                break
                        except:
                            continue
                
                if not download_url:
                    print_error("Could not find download URL. The file may require authentication.")
                    return None
            
            # Determine filename
            if output_filename:
                filename = sanitize_filename(output_filename)
            else:
                filename = sanitize_filename(file_info.get('name', 'terabox_file'))
            
            filepath = os.path.join(self.download_path, filename)
            
            # Download file
            print_warning(f"Downloading: {file_info.get('name', 'Unknown')}")
            
            response = self.session.get(download_url, timeout=60, stream=True, allow_redirects=True)
            response.raise_for_status()
            
            # Get file size if available
            total_size = int(response.headers.get('content-length', 0))
            if not total_size and file_info.get('size'):
                total_size = file_info['size']
            
            downloaded = 0
            with open(filepath, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        
                        if progress_hook and total_size > 0:
                            progress = (downloaded / total_size) * 100
                            progress_hook({
                                'downloaded_bytes': downloaded,
                                'total_bytes': total_size,
                                'status': 'downloading',
                                'percent': progress
                            })
            
            if os.path.exists(filepath) and os.path.getsize(filepath) > 0:
                print_success(f"Downloaded: {os.path.basename(filepath)}")
                return filepath
            else:
                print_error("Download failed: File is empty or doesn't exist")
                if os.path.exists(filepath):
                    os.remove(filepath)
                return None
            
        except requests.exceptions.RequestException as e:
            print_error(f"Network error downloading file: {str(e)}")
            return None
        except Exception as e:
            print_error(f"Error downloading Terabox file: {str(e)}")
            return None
    
    def list_files(self, url: str) -> Optional[List[Dict]]:
        """
        List files in a Terabox folder (if URL is a folder)
        
        Args:
            url: Terabox share URL
            
        Returns:
            List of file dictionaries or None
        """
        try:
            file_info = self.parse_terabox_url(url)
            if not file_info:
                return None
            
            # For folders, try to extract file list
            response = self.session.get(url, timeout=15)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            files = []
            
            # Look for file list in page
            file_elements = soup.find_all(['a', 'div'], class_=re.compile(r'file|item|entry', re.I))
            
            for element in file_elements:
                file_name = element.get_text(strip=True)
                file_link = element.get('href', '')
                
                if file_name and file_link:
                    files.append({
                        'name': file_name,
                        'url': file_link if file_link.startswith('http') else url + file_link,
                        'type': 'file'
                    })
            
            return files if files else None
            
        except Exception as e:
            print_error(f"Error listing files: {str(e)}")
            return None

