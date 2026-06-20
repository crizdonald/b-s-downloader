import os
import re
import shutil
from typing import Dict, List, Tuple
from mutagen.mp3 import MP3

def normalize_string(s: str) -> str:
    """Lowercase and strip spaces and special characters for signature comparison"""
    if not s:
        return ""
    s = s.lower()
    # Remove common duplicate suffixes
    s = re.sub(r'\s*\(\d+\)$', '', s)
    s = re.sub(r'\s*-\s*copy$', '', s)
    s = re.sub(r'\s*copy$', '', s)
    # Remove all non-alphanumeric characters
    s = re.sub(r'[^a-z0-9]', '', s)
    return s

def get_song_signature(file_path: str) -> str:
    """Get unique song signature based on ID3 tags or standardized filename"""
    artist = ""
    title = ""
    filename = os.path.basename(file_path)
    
    # Try parsing ID3 tags for MP3s
    if file_path.lower().endswith('.mp3'):
        try:
            audio = MP3(file_path)
            if audio.tags:
                if 'TPE1' in audio.tags:
                    artist = str(audio.tags['TPE1'].text[0])
                if 'TIT2' in audio.tags:
                    title = str(audio.tags['TIT2'].text[0])
        except Exception:
            pass
            
    if artist and title:
        return normalize_string(f"{artist} - {title}")
    else:
        # Fallback to normalized filename
        name_without_ext = os.path.splitext(filename)[0]
        return normalize_string(name_without_ext)

def find_and_delete_duplicates(directory: str) -> Tuple[List[str], float]:
    """
    Recursively scans the directory for duplicates.
    Keeps the largest file (highest quality/completed file) and deletes others.
    Returns:
        A tuple of (list of deleted file paths, total space cleared in MB)
    """
    if not os.path.exists(directory):
        return [], 0.0

    groups: Dict[str, List[Tuple[str, int, float]]] = {}
    
    # Scan directory
    for root, _, files in os.walk(directory):
        for file in files:
            # Process common audio files
            if file.lower().endswith(('.mp3', '.m4a', '.mp4', '.wav')):
                file_path = os.path.join(root, file)
                try:
                    size = os.path.getsize(file_path)
                    mtime = os.path.getmtime(file_path)
                    sig = get_song_signature(file_path)
                    if sig:
                        if sig not in groups:
                            groups[sig] = []
                        groups[sig].append((file_path, size, mtime))
                except Exception as e:
                    print(f"[DUPLICATE FINDER] Error reading file {file_path}: {e}")

    deleted_files = []
    total_space_cleared = 0.0

    for sig, file_list in groups.items():
        if len(file_list) > 1:
            # Sort: Keep the largest file.
            # If sizes match, keep the one with the cleaner/shorter path.
            # If path lengths match, keep the oldest created file.
            file_list.sort(key=lambda x: (-x[1], len(x[0]), x[2]))
            
            keep_file = file_list[0][0]
            redundant_files = file_list[1:]
            
            print(f"[DUPLICATE FINDER] Duplicate group '{sig}': keeping '{keep_file}'")
            for file_path, size, _ in redundant_files:
                try:
                    os.remove(file_path)
                    deleted_files.append(file_path)
                    total_space_cleared += size
                    print(f"  Deleted: '{file_path}' ({size / (1024 * 1024):.2f} MB)")
                except Exception as e:
                    print(f"  Failed to delete '{file_path}': {e}")

    space_cleared_mb = total_space_cleared / (1024 * 1024)
    return deleted_files, space_cleared_mb

def check_song_exists(title: str, artist: str, directory: str) -> str:
    """
    Scans the directory to check if the song already exists.
    Returns the path to the existing file or empty string if not found.
    """
    if not os.path.exists(directory):
        return ""
        
    query_sig = normalize_string(f"{artist} - {title}")
    if not query_sig:
        return ""
        
    for root, _, files in os.walk(directory):
        for file in files:
            if file.lower().endswith(('.mp3', '.m4a', '.mp4', '.wav')):
                file_path = os.path.join(root, file)
                sig = get_song_signature(file_path)
                if sig == query_sig:
                    return file_path
    return ""

def scan_cache_directory(directory: str) -> Dict[str, str]:
    """Scans directory and returns a map of standardized signatures to paths"""
    cache = {}
    if not os.path.exists(directory):
        return cache
        
    for root, _, files in os.walk(directory):
        for file in files:
            if file.lower().endswith(('.mp3', '.m4a', '.mp4', '.wav')):
                file_path = os.path.join(root, file)
                sig = get_song_signature(file_path)
                if sig:
                    cache[sig] = file_path
    return cache
