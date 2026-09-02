import os
import re
import urllib.parse
import webbrowser

def extract_search_target(text: str) -> str:
    cleaned = re.sub(r"^(tuzi|halo tuzi|hi tuzi|eh tuzi|tolong|coba)\s+", "", text, flags=re.IGNORECASE).strip()
    
    match = re.search(r"(?:cari|cariin|carikan|putar|putarkan|setel|setelkan|mainkan|tonton)\s+(?:lagu|video|tentang|berita)?\s*(.*)", cleaned, flags=re.IGNORECASE)
    
    if match:
        target = match.group(1).strip()
    else:
        target = cleaned

    filler_patterns = [
        r"\bbisakah\b", r"\bbisa\b", r"\bdong\b", r"\byah\b", r"\bya\b", r"\bnih\b", r"\baja\b", r"\bsih\b",
        r"\byoutube\b", r"\bspotify\b", r"\btiktok\b", r"\binstagram\b", r"\big\b",
        r"\bbuka\b", r"\bbukain\b", r"\bbukakan\b", r"\bopen\b", 
        r"\bdi\b", r"\bke\b", r"\bdan\b", r"\btuzi\b", r"\bmau\b", r"\bingin\b", r"\blihat\b"
    ]
    
    pattern = "|".join(filler_patterns)
    final_target = re.sub(pattern, "", target, flags=re.IGNORECASE)
    
    return re.sub(r"\s+", " ", final_target).strip()

def play_spotify(song_name: str):
    target = extract_search_target(song_name)
    if not target:
        def action():
            try:
                os.system("start spotify:")
            except Exception:
                webbrowser.open("https://open.spotify.com")
        return "Membuka aplikasi Spotify", action

    encoded = urllib.parse.quote(target)
    def action2():
        try:
            os.system(f"start spotify:search:{encoded}")
        except Exception:
            webbrowser.open(f"https://open.spotify.com/search/{encoded}")
    return f"Membuka Spotify dan memutar '{target}'", action2

def open_youtube(query: str):
    target = extract_search_target(query)
    if not target or len(target) < 2:
        return "Membuka halaman utama YouTube", lambda: webbrowser.open("https://www.youtube.com")
    encoded = urllib.parse.quote(target)
    return f"Membuka YouTube dan mencari video '{target}'", lambda: webbrowser.open(f"https://www.youtube.com/results?search_query={encoded}")

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
        "notepad": "notepad.exe",
        "catatan": "notepad.exe",
        "kalkulator": "calc.exe",
        "calc": "calc.exe",
        "cmd": "cmd.exe",
        "terminal": "wt.exe",
        "explorer": "explorer.exe",
        "discord": "discord",
        "chrome": "chrome",
        "vscode": "code",
        "vs code": "code",
    }
    target = app_map.get(app_name.lower().strip(), app_name)
    def action():
        try:
            os.system(f"start {target}")
        except Exception:
            pass
    return f"Membuka {app_name}", action

def handle_pc_action(text: str):
    lower = text.lower().strip()
    if "youtube" in lower:
        return open_youtube(lower)
    if "tiktok" in lower:
        return open_social_media(lower, "tiktok")
    if "instagram" in lower or "ig" in lower.split():
        return open_social_media(lower, "instagram")
    if any(k in lower for k in ["spotify", "putar lagu", "setel lagu"]):
        return play_spotify(lower)
    if lower.startswith("buka ") or lower.startswith("open "):
        app = re.sub(r"^(buka|open)\s+", "", lower).strip()
        return launch_app(app)
    return None