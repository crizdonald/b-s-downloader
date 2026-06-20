import os
import requests

class TelegramUploader:
    """Telegram Bot API helper to upload audio files to a chat, group or channel"""
    
    def __init__(self, bot_token=None, chat_id=None):
        # Default to environment variables if not passed in UI
        self.bot_token = bot_token or os.getenv('TELEGRAM_BOT_TOKEN')
        self.chat_id = chat_id or os.getenv('TELEGRAM_GROUP_ID')
        
    def send_audio(self, filepath, title=None, artist=None, cover_path=None):
        """Send an audio file to Telegram"""
        if not self.bot_token:
            raise ValueError("Telegram Bot Token is required (set TELEGRAM_BOT_TOKEN env or pass via UI)")
        if not self.chat_id:
            raise ValueError("Telegram Group/Chat ID is required (set TELEGRAM_GROUP_ID env or pass via UI)")
            
        url = f"https://api.telegram.org/bot{self.bot_token}/sendAudio"
        payload = {
            'chat_id': self.chat_id,
            'title': title or '',
            'performer': artist or ''
        }
        
        opened_files = []
        try:
            audio_file = open(filepath, 'rb')
            opened_files.append(audio_file)
            files = {
                'audio': audio_file
            }
            
            if cover_path and os.path.exists(cover_path):
                cover_file = open(cover_path, 'rb')
                files['thumbnail'] = cover_file
                opened_files.append(cover_file)
                
            # Set a long timeout (120s) for large file uploads
            resp = requests.post(url, data=payload, files=files, timeout=120)
        finally:
            for f in opened_files:
                try:
                    f.close()
                except:
                    pass
            
        if resp.status_code != 200:
            raise Exception(f"Telegram API Error: {resp.text}")
            
        return resp.json()


