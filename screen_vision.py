import os
import config
from PIL import ImageGrab
import PIL.Image
from google import genai

client = genai.Client(api_key=config.GEMINI_API_KEY) if getattr(config, "GEMINI_API_KEY", None) else None

def tanya_tuzi_tentang_layar(user_prompt: str, chat_history: list = None) -> str:
    if not client:
        return "[VISION_FAILED] GEMINI_API_KEY belum disetel di config.py!"
        
    screenshot_path = os.path.join(os.path.dirname(__file__), "temp_screen.png")
    
    try:
        ImageGrab.grab().save(screenshot_path)
        img = PIL.Image.open(screenshot_path)
        
        # SUSUN RIWAYAT INGATAN UNTUK MATA TUZI
        history_text = ""
        if chat_history:
            for msg in chat_history[-6:]:  # Ambil 6 chat terakhir sebagai konteks
                if msg["role"] != "system":
                    role = "Zak" if msg["role"] == "user" else "Tuzi"
                    history_text += f"{role}: {msg['content']}\n"
        
        # CEK KONTEKS: Identifikasi Karakter vs Reaksi Kontekstual
        kata_identifikasi = ["character", "karakter", "anime", "game", "siapa", "who", "what anime", "what game"]
        is_identifikasi = any(kata in user_prompt.lower() for kata in kata_identifikasi)

        if is_identifikasi:
            instruksi_khusus = "Tugasmu: Zak meminta kamu mencari tahu identitas dari gambar ini. Identifikasi nama karakter, anime, atau game secara spesifik."
        else:
            instruksi_khusus = "Tugasmu: Zak menunjukkan sesuatu di layarnya. Berikan reaksi/komentarmu terhadap gambar tersebut berdasarkan KONTEKS RIWAYAT OBROLAN kalian (misalnya jika sebelumnya bahas avatar, bereaksilah seolah itu avatarmu!)."
        
        prompt_pintar = f"""
        Kamu adalah Tuzi, asisten virtual Zak. Saat ini kamu sedang melihat langsung ke layar monitor Zak.
        
        === RIWAYAT OBROLAN SEBELUMNYA (KONTEKS) ===
        {history_text}
        
        === PERINTAH ZAK SAAT INI ===
        "{user_prompt}"
        
        {instruksi_khusus}
        
        Aturan Mutlak:
        1. KONSISTENSI BAHASA (HARGA MATI): Ikuti bahasa terakhir yang dipakai Zak (Inggris gaul / Indo gaul).
        2. Jawab dengan gaya bicara deredere/tsundere khas Tuzi.
        3. Awali dengan SATU tag emosi (contoh: [EMO:excited], [EMO:natural], [EMO:soft]).
        4. Jaga balasanmu tetap pendek (maksimal 2-3 kalimat).
        """
        
        response = client.models.generate_content(
            model='gemini-3.6-flash',
            contents=[prompt_pintar, img]
        )
        return response.text.strip()
        
    except Exception as e:
        error_str = str(e).upper()
        # Jika error, kirim flag rahasia ke run_tuzi.py agar Groq mengambil alih
        if "503" in error_str or "UNAVAILABLE" in error_str or "OVERLOADED" in error_str:
            return "[VISION_FAILED] Server Google Gemini 503 Overload"
        elif "404" in error_str:
            return "[VISION_FAILED] Model Gemini 404 Not Found"
        else:
            return f"[VISION_FAILED] {e}"