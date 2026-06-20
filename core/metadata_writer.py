"""
Write metadata to audio files (MP3 tags, cover art)
"""
import os
import requests
from typing import Optional, Dict
from mutagen.mp3 import MP3
from mutagen.id3 import ID3, TIT2, TPE1, TALB, APIC, TDRC
from utils.colors import print_error, print_warning

class MetadataWriter:
    """Write metadata to MP3 files"""
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
    
    def download_cover_art(self, url: str) -> Optional[bytes]:
        """
        Download cover art image
        
        Args:
            url: URL to cover art image
            
        Returns:
            Image data as bytes or None
        """
        if not url:
            return None
        
        try:
            response = self.session.get(url, timeout=10, stream=True)
            response.raise_for_status()
            return response.content
        except Exception as e:
            print_warning(f"Could not download cover art: {str(e)}")
            return None
    
    def write_metadata(self, file_path: str, metadata: Dict) -> bool:
        """
        Write metadata to MP3 file
        
        Args:
            file_path: Path to MP3 file
            metadata: Dictionary with metadata:
                - title: Song title
                - artist: Artist name
                - album: Album name (optional)
                - cover_art: URL or bytes (optional)
                - year: Year (optional)
        
        Returns:
            True if successful
        """
        if not os.path.exists(file_path):
            print_error(f"File not found: {file_path}")
            return False
        
        try:
            print(f"DEBUG_META: Entering write_metadata for {os.path.basename(file_path)}")
            # Load or create ID3 tags
            try:
                audio = MP3(file_path, ID3=ID3)
            except:
                audio = MP3(file_path)
                if audio.tags is None:
                    audio.add(ID3())
            
            # Write title
            if 'title' in metadata and metadata['title']:
                audio.tags.add(TIT2(encoding=3, text=metadata['title']))
            
            # Write artist
            if 'artist' in metadata and metadata['artist']:
                audio.tags.add(TPE1(encoding=3, text=metadata['artist']))
            
            # Write album
            if 'album' in metadata and metadata['album']:
                audio.tags.add(TALB(encoding=3, text=metadata['album']))
            
            # Write year
            if 'year' in metadata and metadata['year']:
                audio.tags.add(TDRC(encoding=3, text=str(metadata['year'])))
            
            # Write cover art
            cover_art_data = None
            if 'cover_art' in metadata and metadata['cover_art']:
                print(f"DEBUG_META: Processing cover art. Type: {type(metadata['cover_art'])}")
                if isinstance(metadata['cover_art'], bytes):
                    cover_art_data = metadata['cover_art']
                elif isinstance(metadata['cover_art'], str):
                    # Download if URL
                    if metadata['cover_art'].startswith('http'):
                        print(f"DEBUG_META: Downloading cover art from {metadata['cover_art']}")
                        cover_art_data = self.download_cover_art(metadata['cover_art'])
                        print(f"DEBUG_META: Downloaded {len(cover_art_data) if cover_art_data else 0} bytes")
                    else:
                        # Assume it's a file path
                        if os.path.exists(metadata['cover_art']):
                            with open(metadata['cover_art'], 'rb') as f:
                                cover_art_data = f.read()
            
            if cover_art_data:
                # Determine MIME type
                mime_type = 'image/jpeg'
                if cover_art_data.startswith(b'\x89PNG'):
                    mime_type = 'image/png'
                
                print(f"DEBUG_META: Embedding cover art ({len(cover_art_data)} bytes, {mime_type})")
                audio.tags.add(APIC(
                    encoding=3,
                    mime=mime_type,
                    type=3,  # Cover (front)
                    desc='Cover',
                    data=cover_art_data
                ))
            else:
                print("DEBUG_META: No cover art data to write")
            
            # Save tags
            # Force ID3 v2.3 for maximum Windows compatibility
            audio.save(v2_version=3)
            print("DEBUG_META: Tags saved successfully (ID3v2.3)")
            return True
            
        except Exception as e:
            print_error(f"Error writing metadata: {str(e)}")
            return False

