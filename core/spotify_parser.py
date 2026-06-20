"""
Spotify link parser - extracts track/playlist information without using official API
"""
import re
import json
import sys
import os
import re
import requests
from bs4 import BeautifulSoup
from typing import List, Dict, Optional

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.helpers import parse_spotify_url
from utils.colors import print_error, print_warning, print_info

class SpotifyParser:
    """Parse Spotify links and extract track information"""
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'authority': 'open.spotify.com',
            'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
            'accept-language': 'en-US,en;q=0.9',
            'cache-control': 'max-age=0',
            'sec-ch-ua': '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"Windows"',
            'sec-fetch-dest': 'document',
            'sec-fetch-mode': 'navigate',
            'sec-fetch-site': 'none',
            'sec-fetch-user': '?1',
            'upgrade-insecure-requests': '1',
            'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        })
    
    def parse_track(self, spotify_url: str) -> Optional[Dict]:
        """
        Parse a single Spotify track URL
        
        Args:
            spotify_url: Spotify track URL (can be regular or embed)
            
        Returns:
            Dictionary with track info or None
        """
        try:
            url_type, track_id = parse_spotify_url(spotify_url)
            if url_type != 'track':
                return None
            
            # Initialize defaults
            song_name = 'Unknown Song'
            artist_name = 'Unknown Artist'
            album_name = None  # Don't default to 'Unknown Album', let downsteam decide or preserve
            cover_art = ''
            
            # Method 1: Try embed URL first (most reliable for structured data)
            embed_url = f"https://open.spotify.com/embed/track/{track_id}"
            try:
                embed_response = self.session.get(embed_url, timeout=10)
                if embed_response.status_code == 200:
                    embed_soup = BeautifulSoup(embed_response.text, 'html.parser')
                    
                    # Look for JSON data in script tags (Spotify.Entity)
                    scripts = embed_soup.find_all('script')
                    for script in scripts:
                        if script.string:
                            script_text = script.string
                            
                            # Try Spotify.Entity format
                            if 'Spotify.Entity' in script_text:
                                try:
                                    json_match = re.search(r'Spotify\.Entity\s*=\s*({.+?});', script_text, re.DOTALL)
                                    if json_match:
                                        data = json.loads(json_match.group(1))
                                        song_name = data.get('name', song_name)
                                        artists = data.get('artists', [])
                                        if artists:
                                            artist_name = ', '.join([a.get('name', '') for a in artists if a.get('name')])
                                        album_data = data.get('album', {})
                                        if album_data:
                                            album_name = album_data.get('name', album_name)
                                            album_images = album_data.get('images', [])
                                            if album_images:
                                                cover_art = album_images[0].get('url', cover_art)
                                        # If we got good data, return early
                                        if song_name != 'Unknown Song':
                                            return {
                                                'name': song_name,
                                                'artist': artist_name,
                                                'album': album_name,
                                                'cover_art': cover_art,
                                                'url': spotify_url,
                                                'id': track_id
                                            }
                                except Exception as e:
                                    pass
                            
                            # Try alternative JSON formats in embed
                            # Look for window.__INITIAL_STATE__ or similar
                            json_patterns = [
                                r'window\.__INITIAL_STATE__\s*=\s*({.+?});',
                                r'Spotify\.Track\s*=\s*({.+?});',
                                r'"track":\s*({.+?})',
                            ]
                            for pattern in json_patterns:
                                try:
                                    match = re.search(pattern, script_text, re.DOTALL)
                                    if match:
                                        data = json.loads(match.group(1))
                                        # Try to extract track info from various structures
                                        if isinstance(data, dict):
                                            if 'name' in data:
                                                song_name = data.get('name', song_name)
                                            if 'artists' in data:
                                                artists = data.get('artists', [])
                                                if isinstance(artists, list) and artists:
                                                    artist_name = ', '.join([a.get('name', '') for a in artists if isinstance(a, dict) and a.get('name')])
                                            if 'album' in data:
                                                album_data = data.get('album', {})
                                                if isinstance(album_data, dict):
                                                    album_name = album_data.get('name', album_name)
                                                    if 'images' in album_data:
                                                        images = album_data.get('images', [])
                                                        if images and isinstance(images[0], dict):
                                                            cover_art = images[0].get('url', cover_art)
                                except:
                                    pass
            except Exception as e:
                print_warning(f"Embed method failed: {str(e)}")
            
            # Method 2: Fallback to regular Spotify page
            if song_name == 'Unknown Song':
                try:
                    response = self.session.get(spotify_url, timeout=10)
                    response.raise_for_status()
                    soup = BeautifulSoup(response.text, 'html.parser')
                    
                    # Extract from page title
                    title = soup.find('title')
                    if title:
                        title_text = title.get_text()
                        if ' - ' in title_text:
                            parts = title_text.split(' - ')
                            song_name = parts[0].strip()
                            artist_name = parts[1].split('|')[0].strip() if len(parts) > 1 else artist_name
                        else:
                            song_name = title_text.split('|')[0].strip()
                    
                    # Extract from meta tags
                    meta_tags = soup.find_all('meta', property=True)
                    for meta in meta_tags:
                        prop = meta.get('property', '') or meta.get('name', '')
                        content = meta.get('content', '')
                        
                        if 'og:title' in prop or 'twitter:title' in prop:
                            if ' - ' in content:
                                parts = content.split(' - ')
                                # Prioritize song name before the dash
                                potential_name = parts[0].strip()
                                if 'Spotify' not in potential_name:
                                    song_name = potential_name
                                if len(parts) > 1 and artist_name == 'Unknown Artist':
                                    artist_name = parts[1].split('|')[0].strip()
                            else:
                                potential_name = content.split('|')[0].strip()
                                if 'Spotify' not in potential_name:
                                    song_name = potential_name
                        
                        if ('og:description' in prop or 'twitter:description' in prop) and artist_name == 'Unknown Artist':
                            # Description often starts with "Song · Artist · Year" or "Artist · Song · Year"
                            if ' · ' in content:
                                parts = content.split(' · ')
                                if len(parts) > 1:
                                    # This is often the artist
                                    artist_name = parts[0].strip() if 'Song' in content else parts[1].strip()
                        
                        if 'music:musician' in prop:
                            artist_name = content.strip()
                            
                        if 'og:image' in prop and not cover_art:
                            cover_art = content

                    # Method 3: Try JSON-LD
                    if song_name == 'Unknown Song':
                        ld_json = soup.find('script', type='application/ld+json')
                        if ld_json:
                            try:
                                ld_data = json.loads(ld_json.string)
                                if isinstance(ld_data, dict):
                                    song_name = ld_data.get('name', song_name)
                                    if 'byArtist' in ld_data:
                                        artists = ld_data.get('byArtist', [])
                                        if isinstance(artists, list) and artists:
                                            artist_name = ', '.join([a.get('name', '') for a in artists if isinstance(a, dict) and a.get('name')])
                                    if 'album' in ld_data and isinstance(ld_data['album'], dict):
                                        album_name = ld_data['album'].get('name', album_name)
                                        if 'image' in ld_data['album']:
                                            cover_art = ld_data['album'].get('image', cover_art)
                            except:
                                pass
                except Exception as e:
                    print_warning(f"Regular page method failed: {str(e)}")
            
            # Fallback: Try Embed URL if song/artist is missing, generic, or if cover art is missing
            if song_name == 'Unknown Song' or 'Spotify' in song_name or artist_name == 'Unknown Artist' or not cover_art:
                print_warning("Main track page extraction failed. Attempting Embed fallback...")
                try:
                    embed_url = f"https://open.spotify.com/embed/track/{track_id}"
                    embed_response = self.session.get(embed_url, timeout=10)
                    if embed_response.status_code == 200:
                        embed_soup = BeautifulSoup(embed_response.text, 'html.parser')
                        for script in embed_soup.find_all('script'):
                            if script.string and '__NEXT_DATA__' == script.attrs.get('id', ''):
                                try:
                                    data = json.loads(script.string)
                                    entity = data['props']['pageProps']['state']['data']['entity']
                                    
                                    # Extract Metadata from Embed Entity (Track)
                                    if 'title' in entity:
                                        song_name = entity.get('title')
                                    elif 'name' in entity:
                                         song_name = entity.get('name')
                                    
                                    # Heuristic: Extract Album from Title if present (e.g. "Song (From 'Album')")
                                    if song_name:
                                        album_match = re.search(r'\(From (.+?)\)', song_name)
                                        if album_match:
                                            # Strip quotes if present
                                            album_name = album_match.group(1).strip('"\'')
                                    
                                    # Artist
                                    if 'artists' in entity and isinstance(entity['artists'], list):
                                        artist_names = [a.get('name') for a in entity['artists'] if a.get('name')]
                                        if artist_names:
                                            artist_name = ', '.join(artist_names)
                                    elif 'subtitle' in entity:
                                        # Playlist items often use subtitle
                                        artist_name = entity.get('subtitle', 'Unknown Artist')
                                        artist_name = artist_name.replace('&amp;', '&').replace(' ', ' ')
                                    
                                    # Cover Art
                                    if 'visualIdentity' in entity and 'image' in entity['visualIdentity']:
                                         # Track Entity structure
                                         imgs = entity['visualIdentity'].get('image', [])
                                         if imgs and isinstance(imgs, list):
                                             cover_art = imgs[0].get('url', '')
                                    elif 'images' in entity and entity['images']:
                                        cover_art = entity['images'][0].get('url', '')
                                    elif 'coverArt' in entity:
                                         cover_art = entity['coverArt'].get('url', '')

                                    print_info(f"Successfully extracted track info via Embed: {song_name} - {artist_name}")
                                    break
                                except Exception as json_e:
                                    print_warning(f"Embed JSON parse error: {json_e}")
                except Exception as e:
                     print_error(f"Embed fallback failed: {e}")

            # Safety Net: oEmbed (Last Resort)
            if song_name == 'Unknown Song' or 'Spotify' in song_name or not cover_art:
                print_warning("All parsing methods failed. Attempting oEmbed safety net...")
                try:
                    oembed_url = f"https://open.spotify.com/oembed?url={spotify_url}"
                    resp = self.session.get(oembed_url, timeout=5)
                    if resp.status_code == 200:
                        data = resp.json()
                        title = data.get('title')
                        thumb = data.get('thumbnail_url')
                        
                        if title:
                            song_name = title
                            
                            # Heuristic: Extract Album from Title if present
                            album_match = re.search(r'\(From (.+?)\)', song_name)
                            if album_match:
                                album_name = album_match.group(1).strip('"\'')

                            # oEmbed titles sometimes are "Song - Artist", or just "Song"
                            # We can't be sure, so leave artist as Unknown if not set, or try to split
                            if ' - ' in title and artist_name == 'Unknown Artist':
                                parts = title.split(' - ')
                                if len(parts) >= 2:
                                     # Heuristic: usually "Artist - Song" or "Song - Artist". Spotify usually does "Song - Artist" in HTML title but oEmbed?
                                     # Actually oEmbed title is usually just the Song Title for tracks.
                                     pass
                        
                        if thumb and not cover_art:
                            cover_art = thumb
                            
                        print_info(f"Recovered via oEmbed: {song_name}")
                except Exception as e:
                    print_error(f"oEmbed failed: {e}")
            return {
                'name': song_name,
                'artist': artist_name,
                'album': album_name,
                'cover_art': cover_art,
                'url': spotify_url,
                'id': track_id
            }
            
        except Exception as e:
            print_error(f"Error parsing Spotify track: {str(e)}")
            return None
    
    def parse_playlist(self, spotify_url: str) -> Optional[Dict]:
        """
        Parse a Spotify playlist or album URL
        """
        try:
            url_type, playlist_id = parse_spotify_url(spotify_url)
            if url_type not in ('playlist', 'album'):
                return None
            
            print_info(f"Parsing Spotify {url_type}: {spotify_url}")
            
            # Fetch the playlist page
            try:
                response = self.session.get(spotify_url, timeout=10)
                if response.status_code == 429:
                    print_error("Spotify Rate Limit hit (429). Please wait a few minutes before trying again.")
                    return None
                response.raise_for_status()
            except requests.exceptions.HTTPError as e:
                if e.response.status_code == 429:
                    print_error("Spotify Rate Limit hit (429). Please wait a few minutes before trying again.")
                    return None
                raise e
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Extract playlist/album name
            playlist_name = 'Unknown Album' if url_type == 'album' else 'Unknown Playlist'
            title_tag = soup.find('title')
            if title_tag:
                playlist_name = title_tag.get_text().split('|')[0].strip()
            
            meta_title = soup.find('meta', property='og:title')
            if meta_title:
                playlist_name = meta_title.get('content', playlist_name)

            tracks = []
            seen_ids = set()

            # Strategy: Extract tracks from JSON state in the page
            scripts = soup.find_all('script')
            for script in scripts:
                if script.string:
                    script_text = script.string
                    
                    # Look for window.__INITIAL_STATE__ or similar
                    json_match = re.search(r'window\.__INITIAL_STATE__\s*=\s*({.+?});', script_text, re.DOTALL)
                    data = None # Initialize data for this script block

                    try:
                        # Standard Embed JSON structure (resource/Spotify.Entity)
                        if 'resource' in script_text or 'Spotify.Entity' in script_text:
                            # Try to find the main JSON object
                            json_match_embed = re.search(r'=\s*({.+?});', script_text, re.DOTALL)
                            if json_match_embed:
                                data = json.loads(json_match_embed.group(1))
                                
                                # Extract Name
                                if 'name' in data:
                                    playlist_name = data.get('name', playlist_name)
                                elif 'resource' in data and 'name' in data['resource']:
                                    playlist_name = data['resource'].get('name', playlist_name)
                                    
                                # Extract Tracks
                                if not tracks:
                                    embed_tracks = []
                                    if 'resource' in data and 'tracks' in data['resource']:
                                        items = data['resource']['tracks'].get('items', [])
                                        for item in items:
                                            track = item.get('track', item)
                                            if track:
                                                t_name = track.get('name')
                                                t_id = track.get('id')
                                                if not t_id and 'uri' in track:
                                                    t_id = str(track['uri']).split(':')[-1]
                                                
                                                if t_name and t_id and t_id not in seen_ids:
                                                    artists = track.get('artists', [])
                                                    artist_name = 'Unknown Artist'
                                                    if artists:
                                                        artist_name = ', '.join([a.get('name', '') for a in artists])
                                                    
                                                    album = track.get('album', {})
                                                    album_name = album.get('name', 'Unknown Album')
                                                    cover_art = ''
                                                    if 'images' in album and album['images']:
                                                        cover_art = album['images'][0].get('url', '')
                                                    
                                                    seen_ids.add(t_id)
                                                    embed_tracks.append({
                                                        'name': t_name,
                                                        'artist': artist_name,
                                                        'album': album_name,
                                                        'cover_art': cover_art,
                                                        'id': t_id,
                                                        'url': f"https://open.spotify.com/track/{t_id}"
                                                    })
                                    if embed_tracks:
                                        tracks.extend(embed_tracks)

                        # Next.js Embed Structure (__NEXT_DATA__)
                        elif '__NEXT_DATA__' == script.attrs.get('id', ''):
                            data = json.loads(script_text)
                            # Path: props.pageProps.state.data.entity
                            try:
                                entity = data['props']['pageProps']['state']['data']['entity']
                                if 'name' in entity:
                                    playlist_name = entity.get('name', playlist_name)
                                
                                if not tracks and 'trackList' in entity:
                                    embed_tracks = []
                                    for track in entity['trackList']:
                                        t_name = track.get('title')
                                        t_uri = track.get('uri', '')
                                        t_id = t_uri.split(':')[-1] if t_uri else None
                                        
                                        if t_name and t_id and t_id not in seen_ids:
                                            artist_name = track.get('subtitle', 'Unknown Artist')
                                            # Fix HTML entities in artist names (e.g. &amp;) via plain replacement or lib
                                            artist_name = artist_name.replace('&amp;', '&').replace(' ', ' ') # Replace nbsp
                                            
                                            # Note: Embed V2 often lacks album/cover per track in this list
                                            # We use placeholders.
                                            album_name = 'Unknown Album' 
                                            cover_art = ''
                                            
                                            seen_ids.add(t_id)
                                            embed_tracks.append({
                                                'name': t_name,
                                                'artist': artist_name,
                                                'album': album_name,
                                                'cover_art': cover_art,
                                                'id': t_id,
                                                'url': f"https://open.spotify.com/track/{t_id}"
                                            })
                                    if embed_tracks:
                                        tracks.extend(embed_tracks)
                            except KeyError:
                                pass
                        elif json_match:
                            data = json.loads(json_match.group(1))
                        elif '{"uri":"spotify:playlist:' in script_text or '{"uri":"spotify:album:' in script_text: # Sometimes it's just a JSON block in a script
                            data = json.loads(script_text)
                    except:
                        data = None # Reset data if parsing fails for any of the above
                    
                    if data: # Only proceed if data was successfully parsed by any method
                        local_seen = set()
                        found_tracks = []
                        
                        def find_tracks_recursive(obj):
                            if isinstance(obj, dict):
                                # Is this a track object?
                                is_track = obj.get('type') == 'track' or 'spotify:track:' in str(obj.get('uri', ''))
                                if is_track and 'name' in obj:
                                    tid = obj.get('id')
                                    if not tid and 'uri' in obj:
                                        tid = str(obj['uri']).split(':')[-1]
                                    
                                    if tid and tid not in local_seen:
                                        local_seen.add(tid)
                                        
                                        name = obj.get('name')
                                        artist = 'Unknown Artist'
                                        artists = obj.get('artists', [])
                                        if artists and isinstance(artists, list):
                                            artist = ', '.join([a.get('name', '') for a in artists if isinstance(a, dict) and a.get('name')])
                                        
                                        album_name = 'Unknown Album'
                                        cover_art = ''
                                        album = obj.get('album', {})
                                        if isinstance(album, dict):
                                            album_name = album.get('name', 'Unknown Album')
                                            images = album.get('images', [])
                                            if images and isinstance(images, list):
                                                cover_art = images[0].get('url', '')
                                        
                                        if name and name != 'Unknown Song':
                                            found_tracks.append({
                                                'name': name,
                                                'artist': artist,
                                                'album': album_name,
                                                'cover_art': cover_art,
                                                'id': tid,
                                                'url': f"https://open.spotify.com/track/{tid}"
                                            })
                                
                                for key, value in obj.items():
                                    if value and (isinstance(value, dict) or isinstance(value, list)):
                                        find_tracks_recursive(value)
                            elif isinstance(obj, list):
                                for item in obj:
                                    if item and (isinstance(item, dict) or isinstance(item, list)):
                                        find_tracks_recursive(item)

                        find_tracks_recursive(data)
                        if found_tracks:
                            for t in found_tracks:
                                if t['id'] not in seen_ids:
                                    seen_ids.add(t['id'])
                                    tracks.append(t)

            # Fallback: if no tracks found in JSON, search for track IDs and try to get MINIMAL info
            # Fallback: If no tracks found from main page (e.g. redirected), try Embed URL
            if not tracks:
                print_warning("Main page parsing failed. Attempting fallback to Embed URL...")
                try:
                    embed_url = f"https://open.spotify.com/embed/{url_type}/{playlist_id}"
                    embed_response = self.session.get(embed_url, timeout=10)
                    if embed_response.status_code == 200:
                        embed_soup = BeautifulSoup(embed_response.text, 'html.parser')
                        for script in embed_soup.find_all('script'):
                            if script.string:
                                script_text = script.string
                                # Reuse the parsing logic for __NEXT_DATA__
                                if '__NEXT_DATA__' == script.attrs.get('id', ''):
                                    try:
                                        data = json.loads(script_text)
                                        entity = data['props']['pageProps']['state']['data']['entity']
                                        if 'name' in entity:
                                            playlist_name = entity.get('name', playlist_name)
                                        
                                        if 'trackList' in entity:
                                            embed_tracks = []
                                            for track in entity['trackList']:
                                                t_name = track.get('title')
                                                t_uri = track.get('uri', '')
                                                t_id = t_uri.split(':')[-1] if t_uri else None
                                                
                                                if t_name and t_id and t_id not in seen_ids:
                                                    artist_name = track.get('subtitle', 'Unknown Artist')
                                                    artist_name = artist_name.replace('&amp;', '&').replace(' ', ' ')
                                                    
                                                    album_name = None
                                                    # Use a high-quality placeholder or try to use playlist image if available
                                                    # Since we can't get individual track covers easily without more requests,
                                                    # we'll use a generic Spotify placeholder or the playlist cover if we could find one earlier (not usually available in this specific payload)
                                                    cover_art = 'https://open.spotify.com/cdn/images/start-page/made-for-you.jpg' # Generic Fallback 
                                                    # Or better: check if we have playlist images in data. props.pageProps.state.data.entity.images
                                                    # Try to get playlist cover art
                                                    if not cover_art or 'made-for-you' in cover_art:
                                                        if 'coverArt' in entity and 'sources' in entity['coverArt']:
                                                            sources = entity['coverArt']['sources']
                                                            if sources and isinstance(sources, list):
                                                                cover_art = sources[0].get('url', cover_art)
                                                        elif 'images' in entity and entity['images']:
                                                             cover_art = entity['images'][0].get('url', cover_art)

                                                    seen_ids.add(t_id)
                                                    embed_tracks.append({
                                                        'name': t_name,
                                                        'artist': artist_name,
                                                        'album': album_name,
                                                        'cover_art': cover_art,
                                                        'id': t_id,
                                                        'url': f"https://open.spotify.com/track/{t_id}"
                                                    })
                                            if embed_tracks:
                                                tracks.extend(embed_tracks)
                                                print_info(f"Successfully extracted {len(tracks)} tracks from Embed URL.")
                                                break
                                    except:
                                        pass
                except Exception as e:
                    print_error(f"Embed fallback failed: {e}")
                # Fallback completed

            if tracks:
                return {
                    'name': playlist_name,
                    'tracks': tracks
                }
            return None

        except Exception as e:
            print_error(f"Error parsing Spotify {url_type}: {str(e)}")
            return None
