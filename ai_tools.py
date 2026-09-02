from datetime import datetime
import os
import re
import warnings

warnings.filterwarnings("ignore", category=RuntimeWarning)

# DuckDuckGo Search Compatibility
try:
  from ddgs import DDGS
except ImportError:
  try:
    from duckduckgo_search import DDGS
  except ImportError:
    DDGS = None

# Gemini API Integration
try:
  import google.generativeai as genai
except ImportError:
  genai = None

import config

if genai and getattr(config, "GEMINI_API_KEY", None):
  try:
    genai.configure(api_key=config.GEMINI_API_KEY)
  except Exception:
    pass

HARI = ["Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu", "Minggu"]
BULAN = [
    "",
    "Januari",
    "Februari",
    "Maret",
    "April",
    "Mei",
    "Juni",
    "Juli",
    "Agustus",
    "September",
    "Oktober",
    "November",
    "Desember",
]


# ==============================================================================
# 1. TIME & DATE TOOLS
# ==============================================================================
def get_current_time_info() -> str:
  """Mendapatkan waktu dan tanggal sistem saat ini secara realtime."""
  now = datetime.now()
  nama_hari = HARI[now.weekday()]
  nama_bulan = BULAN[now.month]

  return (
      f"Hari {nama_hari}, {now.day} {nama_bulan} {now.year}, Pukul"
      f" {now.strftime('%H:%M:%S')} WIB"
  )


def is_time_query(text: str) -> bool:
  """Mendeteksi apakah pertanyaan menanyakan jam/tanggal/hari."""
  time_keywords = [
      "jam berapa",
      "pukul berapa",
      "tanggal berapa",
      "hari apa",
      "bulan apa",
      "tahun berapa",
      "waktu sekarang",
      "jam sekarang",
      "tanggal sekarang",
  ]
  lower = text.lower()
  return any(k in lower for k in time_keywords)


# ==============================================================================
# 2. WEB SEARCH TOOLS (DDGS)
# ==============================================================================
def needs_web_search(text: str) -> bool:
  """Mendeteksi apakah pertanyaan membutuhkan pencarian internet."""
  if is_time_query(text):
    return False

  # Abaikan obrolan santai/sapaan pendek
  if len(text.strip().split()) <= 2 and not any(
      k in text.lower() for k in ["siapa", "apa itu", "harga", "skor"]
  ):
    return False

  keywords = [
      "siapa",
      "kapan",
      "berita",
      "cuaca",
      "harga",
      "skor",
      "jadwal",
      "terbaru",
      "terkini",
      "update",
      "film",
      "rilis",
      "presiden",
      "juara",
      "info",
      "kenapa",
      "bagaimana cara",
      "apa itu",
  ]
  lower_text = text.lower()
  return any(k in lower_text for k in keywords)


def search_internet(query: str, max_results: int = 3) -> str:
  """Mencari informasi aktual di internet melalui DDGS dengan pembersihan teks."""
  if not DDGS:
    return "Modul duckduckgo_search/ddgs belum terpasang."

  # Bersihkan query dari karakter yang mengganggu pencarian
  clean_query = re.sub(r"[^\w\s\-\?\.]", " ", query).strip()

  try:
    with DDGS() as ddgs:
      results = list(
          ddgs.text(clean_query, region="id-id", max_results=max_results)
      )
      if not results:
        # Fallback ke pencarian global jika region id-id kosong
        results = list(ddgs.text(clean_query, max_results=max_results))

      if not results:
        return "Tidak ditemukan hasil yang relevan di internet."

      summary = []
      for idx, r in enumerate(results, 1):
        title = r.get("title", "").strip()
        body = r.get("body", "").strip()
        # Potong panjang snippet agar tidak membebani context LLM
        if len(body) > 200:
          body = body[:200] + "..."
        summary.append(f"[{idx}] {title}: {body}")

      return "\n".join(summary)
  except Exception as e:
    return f"Gagal mengakses internet: {e}"


# ==============================================================================
# 3. GEMINI VISION & MULTIMODAL TOOL
# ==============================================================================
def analyze_image_with_gemini(
    image_path: str, prompt: str = "Jelaskan apa yang terlihat di gambar ini."
) -> str:
  """Menganalisis gambar menggunakan Gemini Vision API."""
  if not genai or not getattr(config, "GEMINI_API_KEY", None):
    return "Gemini API belum dikonfigurasi di config.py."

  if not os.path.exists(image_path):
    return "File gambar tidak ditemukan."

  try:
    from PIL import Image

    img = Image.open(image_path)
    model = genai.GenerativeModel("gemini-1.5-flash")
    response = model.generate_content([prompt, img])
    return response.text.strip()
  except Exception as e:
    return f"Gagal menganalisis gambar: {e}"


# ==============================================================================
# 4. SMART CONTEXT BUILDER
# ==============================================================================
def get_tools_context(user_input: str) -> str:
  """Menyusun konteks otomatis (Waktu/Internet) untuk diinjeksi ke prompt LLM."""
  context_parts = []

  # 1. Cek Pertanyaan Waktu
  if is_time_query(user_input):
    context_parts.append(f"[FAKTA WAKTU REALTIME: {get_current_time_info()}]")

  # 2. Cek Kebutuhan Pencarian Internet
  elif needs_web_search(user_input):
    search_data = search_internet(user_input, max_results=2)
    if (
        search_data
        and "Gagal" not in search_data
        and "Tidak ditemukan" not in search_data
    ):
      context_parts.append(
          f"[INFORMASI AKTUAL DARI INTERNET:\n{search_data}\n]"
      )

  return "\n".join(context_parts)