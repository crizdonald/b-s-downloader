"""
Audio converter utilities
"""
import os
import subprocess
from typing import Optional
from utils.colors import print_error, print_warning

class AudioConverter:
    """Convert audio files and ensure MP3 format"""
    
    @staticmethod
    def check_ffmpeg() -> bool:
        """
        Check if FFmpeg is available
        
        Returns:
            True if FFmpeg is available
        """
        # Try to locate/initialize static-ffmpeg first
        try:
            import static_ffmpeg
            static_ffmpeg.add_paths(weak=True)
        except Exception:
            pass

        try:
            subprocess.run(['ffmpeg', '-version'], 
                         capture_output=True, 
                         check=True,
                         timeout=5)
            return True
        except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
            return False
    
    @staticmethod
    def convert_to_mp3(input_file: str, output_file: str, bitrate: str = '320k') -> bool:
        """
        Convert audio file to MP3
        
        Args:
            input_file: Path to input file
            output_file: Path to output MP3 file
            bitrate: Bitrate (default: 320k)
            
        Returns:
            True if conversion successful
        """
        if not AudioConverter.check_ffmpeg():
            print_warning("FFmpeg not found. yt-dlp should handle conversion, but if issues occur, install FFmpeg.")
            return False
        
        try:
            cmd = [
                'ffmpeg',
                '-i', input_file,
                '-codec:a', 'libmp3lame',
                '-b:a', bitrate,
                '-y',  # Overwrite output file
                output_file
            ]
            
            subprocess.run(cmd, 
                         capture_output=True, 
                         check=True,
                         timeout=300)
            
            # Verify output file exists
            if os.path.exists(output_file):
                return True
            return False
            
        except subprocess.CalledProcessError as e:
            print_error(f"FFmpeg conversion failed: {e.stderr.decode() if e.stderr else 'Unknown error'}")
            return False
        except Exception as e:
            print_error(f"Error during audio conversion: {str(e)}")
            return False
    
    @staticmethod
    def ensure_mp3(file_path: str, target_bitrate: str = '320k') -> Optional[str]:
        """
        Ensure file is MP3 format, convert if necessary
        
        Args:
            file_path: Path to audio file
            target_bitrate: Target bitrate
            
        Returns:
            Path to MP3 file (may be same or converted)
        """
        if not os.path.exists(file_path):
            return None
        
        # Check if already MP3
        if file_path.lower().endswith('.mp3'):
            return file_path
        
        # Convert to MP3
        output_file = os.path.splitext(file_path)[0] + '.mp3'
        if AudioConverter.convert_to_mp3(file_path, output_file, target_bitrate):
            # Remove original if different
            if output_file != file_path and os.path.exists(output_file):
                try:
                    os.remove(file_path)
                except:
                    pass
            return output_file
        
        return None

