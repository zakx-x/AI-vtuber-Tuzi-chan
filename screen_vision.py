import base64
from io import BytesIO
from PIL import ImageGrab
from groq import Groq
import config

client = Groq(api_key=config.GROQ_API_KEY)

def tangkap_layar_sebagai_base64():
    """Memotret layar monitor utama dan mengompresnya."""
    screenshot = ImageGrab.grab()
    screenshot.thumbnail((1024, 1024))
    
    buffered = BytesIO()
    screenshot.save(buffered, format="JPEG", quality=80)
    return base64.b64encode(buffered.getvalue()).decode("utf-8")

def tanya_tuzi_tentang_layar(prompt_user):
    """Mengirim gambar layar beserta pertanyaan Zak ke Groq Vision."""
    try:
        base64_image = tangkap_layar_sebagai_base64()
        
        system_prompt = (
            "Kamu adalah Tuzi. Jawab pertanyaan Zak berdasarkan gambar layar ini.\n"
            "=== ATURAN MUTLAK ===\n"
            "1. SANGAT SINGKAT: Jawab HANYA dengan 1-2 kalimat pendek untuk menghemat token.\n"
            "2. TANPA EMOJI: DILARANG KERAS menggunakan emoji visual apa pun dalam balasanmu.\n"
            "3. TAG AWALAN: AWALI setiap balasan dengan SATU tag ini saja: [EMO:excited], [EMO:soft], atau [EMO:natural].\n"
            "4. ISOLASI BAHASA: WAJIB membalas menggunakan bahasa yang sama 100% dengan input Zak (Inggris balas Inggris, Indo balas Indo)."
        )
        
        response = client.chat.completions.create(
            model="qwen/qwen3.8-27b",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": f"{system_prompt}\n\nPertanyaan Zak: {prompt_user}"},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{base64_image}"
                            }
                        }
                    ]
                }
            ],
            temperature=0.6,
            max_tokens=150
        )
        return response.choices[0].message.content
        
    except Exception as e:
        return f"[EMO:sad] [SFX:sigh] I'm sorry Zak, my eyes are a bit blurry right now... Error: {e}"