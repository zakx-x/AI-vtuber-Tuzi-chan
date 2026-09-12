import re
import os
import time
import urllib.parse
import pyautogui
import pywhatkit
import webbrowser

def extract_search_target(text: str) -> str:
    cleaned = re.sub(r"^(tuzi|halo tuzi|hi tuzi|eh tuzi|tolong|coba|can you|can u|please|hey)\s+", "", text, flags=re.IGNORECASE).strip()
    match = re.search(r"(?:cari|cariin|carikan|putar|putarkan|setel|setelkan|mainkan|tonton|search|search for|play|find|look up)\s+(?:lagu|video|tentang|berita|for)?\s*(.*)", cleaned, flags=re.IGNORECASE)
    target = match.group(1).strip() if match else cleaned

    filler_patterns = [
        r"\bbisakah\b", r"\bbisa\b", r"\bdong\b", r"\byah\b", r"\bya\b", r"\bnih\b", r"\baja\b", r"\bsih\b",
        r"\byoutube\b", r"\byt\b", r"\bspotify\b", r"\btiktok\b", r"\binstagram\b", r"\big\b",
        r"\bbuka\b", r"\bbukain\b", r"\bbukakan\b", r"\bopen\b", r"\bstart\b",
        r"\bdi\b", r"\bke\b", r"\bdan\b", r"\band\b", r"\btuzi\b", r"\bmau\b", r"\bingin\b", r"\blihat\b",
        r"\bcan u\b", r"\bcan you\b", r"\bon\b", r"\bthe\b"
    ]
    
    pattern = "|".join(filler_patterns)
    final_target = re.sub(pattern, "", target, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", final_target).strip()

def open_social_media(query: str, platform: str):
    target = extract_search_target(query)
    if platform == "tiktok":
        if not target or len(target) < 2:
            return "Membuka halaman utama TikTok", lambda: webbrowser.open("https://www.tiktok.com")
        encoded = urllib.parse.quote(target)
        return f"Membuka TikTok dan mencari '{target}'", lambda: webbrowser.open(f"https://www.tiktok.com/search?q={encoded}")
    elif platform == "instagram":
        if not target or len(target) < 2:
            return "Membuka halaman utama Instagram", lambda: webbrowser.open("https://www.instagram.com")
        encoded = urllib.parse.quote(target)
        return f"Membuka Instagram dan mencari hashtag '{target}'", lambda: webbrowser.open(f"https://www.instagram.com/explore/tags/{encoded.replace(' ', '')}/")

def launch_app(app_name: str):
    app_map = {
        "notepad": "notepad.exe", "catatan": "notepad.exe", "kalkulator": "calc.exe", "calc": "calc.exe",
        "cmd": "cmd.exe", "terminal": "wt.exe", "explorer": "explorer.exe", "discord": "discord",
        "chrome": "chrome", "vscode": "code", "vs code": "code",
    }
    target = app_map.get(app_name.lower().strip(), app_name)
    def action():
        try:
            os.system(f"start {target}")
        except Exception:
            pass
    return f"Membuka {app_name}", action

def handle_pc_action(user_input: str):
    text = user_input.lower().strip()
    
    platform = None
    if 'spotify' in text:
        platform = 'spotify'
    elif 'youtube' in text or 'yt' in text:
        platform = 'youtube'
        
    if platform:
        match = re.search(r'\b(play|putar|search|cari)\s+(.+)', text)
        if match:
            raw_query = match.group(2).strip()
            query = re.sub(r'\b(on spotify|di spotify|on youtube|di youtube|on yt|di yt)\b', '', raw_query).strip()
            query = re.split(r'\b(and play|dan putar|play the|putar lagu|song|lagu)\b', query)[0].strip()

            if query:
                if query.lower() in ["the", "it", "this", "that", "lagunya", "lagu itu", "nya"]:
                    query = ""

            if query:
                is_english = "play" in text or "search" in text or "can u" in text
                
                if platform == 'spotify':
                    pc_info = f"Opening Spotify and playing: {query}" if is_english else f"Membuka Spotify dan memutar lagu: {query}"
                    def play_spotify_action():
                        try:
                            safe_query = urllib.parse.quote(query)
                            print(f"\n[Sistem PC] 1. Meminta Windows membuka Spotify: {query}")
                            os.system(f'start spotify:search:{safe_query}')
                            
                            print("[Sistem PC] 2. Menunggu 4.5 detik agar Spotify terbuka...")
                            time.sleep(3) 
                            
                            print("[Sistem PC] 3. Mengambil alih mouse dan bergerak ke (1419, 173)...")
                            pyautogui.moveTo(1419, 173) 
                            
                            time.sleep(0.5)
                            
                            print("[Sistem PC] 4. Melakukan klik pada tombol Play!")
                            pyautogui.click(clicks=1, interval=0.1)
                            print("[Sistem PC] 5. Selesai memutar lagu!")
                        except Exception as e:
                            print(f"\n[ERROR FATAL PYAUTOGUI] Mouse terhalang karena: {e}")
                    return pc_info, play_spotify_action

                elif platform == 'youtube':
                    pc_info = f"Opening YouTube and playing: {query}" if is_english else f"Membuka YouTube dan memutar: {query}"
                    def play_youtube_action():
                        pywhatkit.playonyt(query)
                    return pc_info, play_youtube_action

    if "tiktok" in text:
        return open_social_media(text, "tiktok")
    if "instagram" in text or "ig" in text.split():
        return open_social_media(text, "instagram")
    if text.startswith("buka ") or text.startswith("open ") or text.startswith("launch "):
        app = re.sub(r"^(buka|open|launch)\s+", "", text).strip()
        return launch_app(app)
        
    return None

def play_spotify_direct(query: str):
    def action():
        try:
            safe_query = urllib.parse.quote(query)
            print(f"\n[Sistem PC] (Perintah AI) Meminta Windows membuka Spotify: {query}")
            os.system(f'start spotify:search:{safe_query}')
            
            time.sleep(3) 
            pyautogui.moveTo(1419, 173) 
            time.sleep(0.5)
            
            print(f"[Sistem PC] Melakukan klik pada tombol Play!")
            pyautogui.click(clicks=1, interval=0.1)
        except Exception as e:
            print(f"\n[ERROR FATAL PYAUTOGUI] Mouse terhalang karena: {e}")
    return action