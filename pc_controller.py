import os
import re
import urllib.parse
import webbrowser


def extract_search_target(text: str) -> str:
  """Membersihkan kata pengantar, imbuhan (-kah, -kan, -in), dan nama platform."""
  # Daftar pola kata pengantar percakapan dan variasinya
  filler_patterns = [
      r"\bbisakah\b",
      r"\bbisa\b",
      r"\bdapatkah\b",
      r"\bdapat\b",
      r"\bapakah\b",
      r"\bkamu\b",
      r"\btolonglah\b",
      r"\btolong\b",
      r"\bcobalah\b",
      r"\bcoba\b",
      r"\bdong\b",
      r"\byah\b",
      r"\bcarikan\b",
      r"\bcariin\b",
      r"\bcari\b",
      r"\bputarkan\b",
      r"\bputar\b",
      r"\bsetelkan\b",
      r"\bsetel\b",
      r"\bmainkan\b",
      r"\bbukakan\b",
      r"\bbukain\b",
      r"\bbuka\b",
      r"\bopen\b",
      r"\btonton\b",
      r"\blihat\b",
      r"\byoutube\b",
      r"\bspotify\b",
      r"\bdi\b",
      r"\bke\b",
      r"\bpada\b",
      r"\blagu\b",
      r"\bmusik\b",
      r"\bvideo\b",
      r"\btentang\b",
      r"\bdan\b",
  ]

  pattern = "|".join(filler_patterns)
  cleaned = re.sub(pattern, "", text, flags=re.IGNORECASE)
  cleaned = re.sub(r"\s+", " ", cleaned).strip()

  return cleaned


def play_spotify(song_name: str) -> str:
  target = extract_search_target(song_name)
  if not target:
    # Hanya buka Spotify tanpa pencarian spesifik
    os.system("start spotify:")
    return "Membuka aplikasi Spotify."

  encoded = urllib.parse.quote(target)
  try:
    os.system(f"start spotify:search:{encoded}")
    return f"Membuka Spotify dan memutar '{target}'."
  except Exception:
    webbrowser.open(f"https://open.spotify.com/search/{encoded}")
    return f"Membuka Spotify Web untuk mencari '{target}'."


def open_youtube(query: str) -> str:
  target = extract_search_target(query)

  # Jika user hanya berkata "buka youtube", buka halaman utama YouTube
  if not target or len(target) < 2:
    webbrowser.open("https://www.youtube.com")
    return "Membuka halaman utama YouTube."

  # Jika user menyertakan judul/topik, buka halaman pencarian
  encoded = urllib.parse.quote(target)
  webbrowser.open(f"https://www.youtube.com/results?search_query={encoded}")
  return f"Membuka YouTube dan mencari video '{target}'."


def launch_app(app_name: str) -> str:
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
  try:
    os.system(f"start {target}")
    return f"Membuka {app_name}."
  except Exception as e:
    return f"Gagal membuka {app_name}: {e}"


def handle_pc_action(text: str) -> str | None:
  lower = text.lower().strip()

  # 1. Perintah YouTube
  if "youtube" in lower:
    return open_youtube(lower)

  # 2. Perintah Spotify / Musik
  if any(k in lower for k in ["spotify", "putar lagu", "setel lagu"]):
    return play_spotify(lower)

  # 3. Perintah Buka Aplikasi Windows
  if lower.startswith("buka ") or lower.startswith("open "):
    app = re.sub(r"^(buka|open)\s+", "", lower).strip()
    return launch_app(app)

  return None