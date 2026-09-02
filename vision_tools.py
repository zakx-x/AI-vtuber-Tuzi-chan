import io
import os
from PIL import ImageGrab

try:
  from google import genai
  from google.genai import types

  GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "YOUR_GEMINI_API_KEY")
  client = genai.Client(api_key=GEMINI_API_KEY)
  HAS_VISION = True
except Exception:
  HAS_VISION = False


def capture_screen_image():
  """Mengambil screenshot layar dan memperkecil ukurannya untuk kecepatan analisis."""
  screenshot = ImageGrab.grab()
  # Resize proporsional agar hemat token dan respons instan
  screenshot.thumbnail((1280, 720))
  return screenshot


def analyze_screen(prompt: str = "Jelaskan apa yang sedang dibuka atau dilakukan user di layar saat ini.") -> str:
  """Menganalisis tampilan layar komputer menggunakan model multimodal."""
  if not HAS_VISION:
    return "Fitur penglihatan layar memerlukan API Key Gemini aktif di environment."

  try:
    img = capture_screen_image()
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=80)
    image_bytes = buf.getvalue()

    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=[
            types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg"),
            prompt + " Jawab singkat dan padat dalam 1-2 kalimat santai.",
        ],
    )
    return response.text.strip()
  except Exception as e:
    return f"Gagal membaca layar: {e}"


def is_vision_query(text: str) -> bool:
  """Mendeteksi apakah user meminta AI melihat layar desktop."""
  keywords = [
      "lihat layar",
      "lagi apa",
      "baca layar",
      "lihat desktop",
      "sedang buka apa",
      "baca teks di layar",
      "cek layar",
      "lihat ini",
      "baca kodingan",
      "lihat gambar ini",
  ]
  lower = text.lower()
  return any(k in lower for k in keywords)