import os
import config
from PIL import ImageGrab
import PIL.Image
from google import genai

client = genai.Client(api_key=config.GEMINI_API_KEY) if getattr(config, "GEMINI_API_KEY", None) else None

def tanya_tuzi_tentang_layar(user_prompt: str) -> str:
    if not client:
        return "[EMO:sad] Tuzi tidak bisa melihat karena GEMINI_API_KEY belum disetel di config.py!"
        
    screenshot_path = os.path.join(os.path.dirname(__file__), "temp_screen.png")
    
    try:
        ImageGrab.grab().save(screenshot_path)
        img = PIL.Image.open(screenshot_path)
        
        prompt_pintar = f"""
        Kamu adalah Tuzi, asisten virtual Zak. Saat ini kamu sedang melihat langsung ke layar monitor Zak.
        
        Zak baru saja bertanya kepadamu tentang apa yang ada di layar ini: "{user_prompt}"
        
        Tugasmu:
        1. Jawab pertanyaan Zak dengan sangat spesifik. Jika dia bertanya nama karakter, anime, atau game, gunakan pengetahuan luasmu untuk mengidentifikasinya!
        2. Jawab dengan gaya bicara deredere/tsundere khas Tuzi. Gunakan bahasa gaul (slang) jika Zak memakai bahasa Inggris.
        3. Awali dengan SATU tag emosi (contoh: [EMO:excited], [EMO:natural], [EMO:soft]).
        4. Jaga balasanmu tetap pendek (maksimal 2-3 kalimat).
        """
        
        response = client.models.generate_content(
            model='gemini-3.8-flash',
            contents=[prompt_pintar, img]
        )
        return response.text.strip()
        
    except Exception as e:
        error_str = str(e).upper()
        if "503" in error_str or "UNAVAILABLE" in error_str or "OVERLOADED" in error_str:
            return "[EMO:sad] *sigh* Server Google Gemini lagi down atau kepenuhan nih, Zak. Aku nggak bisa buka mata sekarang, coba tanya lagi beberapa menit lagi ya!"
        elif "404" in error_str:
            return "[EMO:angry] Zak! Model Gemini yang kita pakai sudah dihapus sama Google. Kita harus update nama model di scriptnya!"
        else:
            return f"[EMO:angry] Duh, mataku kelilipan error nih, Zak! Gagal lihat layar: {e}"