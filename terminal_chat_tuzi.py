import os
import re
import time
import winsound
import requests

import config
from local_llm_client import LocalLLMClient
import pc_controller # <--- TAMBAHAN: Import modul kontrol PC

# ==============================================================================
# KONFIGURASI GPT-SoVITS & AUDIO
# ==============================================================================
GPTSOVITS_API_URL = getattr(config, "GPTSOVITS_API_URL", "http://127.0.0.1:9880/tts")
REF_AUDIO_PATH = getattr(config, "REF_AUDIO_PATH", "Reference Audios/sample_zeta.wav")
REF_AUDIO_TEXT = getattr(config, "REF_AUDIO_TEXT", "Halo semuanya, namaku Vestia Zeta!")
REF_AUDIO_LANG = getattr(config, "REF_AUDIO_LANG", "id")

llm = LocalLLMClient()

def remove_emojis_and_symbols(text: str) -> str:
    emoji_pattern = re.compile(
        r"[\U00010000-\U0010ffff\u2600-\u26ff\u2700-\u27bf\u2b50\u2b55\u200d\ufe0f]+",
        flags=re.UNICODE,
    )
    cleaned = emoji_pattern.sub("", text)
    cleaned = re.sub(r"\([^\w\s]{2,}[^)]*\)", "", cleaned)
    cleaned = re.sub(r"\[.*?\]", "", cleaned)
    return cleaned.strip()

def detect_language(text: str) -> str:
    if re.search(r"[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff]", text):
        return "ja"
    en_keywords = {"what", "the", "fuck", "you", "stfu", "kys", "bitch", "shut", "bro", "dude", "hey", "how"}
    words = set(re.findall(r"[a-zA-Z]+", text.lower()))
    if len(words.intersection(en_keywords)) > 0:
        return "en"
    return "id"

def generate_and_play_voice(text: str):
    clean = remove_emojis_and_symbols(text)
    if not clean:
        return

    text_lang = detect_language(clean)
    payload = {
        "text": clean,
        "text_lang": text_lang,
        "ref_audio_path": REF_AUDIO_PATH,
        "prompt_text": REF_AUDIO_TEXT,
        "prompt_lang": REF_AUDIO_LANG,
        "speed": 1.0,
        "top_k": 15,
        "top_p": 1.0,
        "temperature": 1.0,
    }

    temp_wav = f"temp_terminal_{int(time.time())}.wav"
    try:
        res = requests.post(GPTSOVITS_API_URL, json=payload, timeout=30)
        if res.status_code == 200:
            with open(temp_wav, "wb") as f:
                f.write(res.content)
            
            # Memutar audio ke speaker laptop / PC
            winsound.PlaySound(temp_wav, winsound.SND_FILENAME)
        else:
            print(f"\n[TTS Error] Status: {res.status_code}")
    except Exception as e:
        print(f"\n[TTS Connection Error] Gagal konek ke GPT-SoVITS: {e}")
    finally:
        if os.path.exists(temp_wav):
            try:
                os.remove(temp_wav)
            except Exception:
                pass

def main():
    print("=" * 60)
    print(" 🤖 TUZI TERMINAL CHAT (GPT-SoVITS Voice Mode)")
    print(" Ketik pesanmu lalu tekan ENTER. Ketik 'exit' untuk keluar.")
    print("=" * 60 + "\n")

    while True:
        try:
            user_input = input("You: ").strip()
            if not user_input:
                continue

            if user_input.lower() in ["exit", "quit", "keluar"]:
                print("\n[Tuzi] Sampai jumpa!")
                generate_and_play_voice("Sampai jumpa lagi!")
                break
                
            # ==========================================================
            # TAMBAHAN: DETEKSI & EKSEKUSI PERINTAH PC SEBELUM LLM BERPIKIR
            # ==========================================================
            pc_action = pc_controller.handle_pc_action(user_input)
            
            if pc_action:
                print(f"[Sistem] ⚙️ Mengeksekusi: {pc_action}")
                # Menyisipkan info agar LLM tahu aksinya sudah dilakukan
                user_input += f"\n\n[SISTEM INFO: Kamu baru saja mengeksekusi perintah Zaki yaitu: '{pc_action}'. Balas perintahnya dengan gayamu yang sedikit Tsundere/blak-blakan, beri tahu dia bahwa kamu sudah membukanya!]"

            # ==========================================================
            # PROMPT LLM
            # ==========================================================
            prompt = f"""[ROLEPLAY: TUZI]
Kamu adalah Tuzi, asisten AI pribadi yang santai, cerdas, ramah, dan sedikit blak-blakan.
Jawab pesan user dengan singkat, padat, dan natural saat diucapkan. DILARANG menggunakan emoji.

User: {user_input}
Tuzi:"""

            print("Tuzi: ", end="", flush=True)
            full_reply = ""
            for token in llm.stream_response(prompt):
                full_reply += token
                print(token, end="", flush=True)
            print()

            clean_reply = remove_emojis_and_symbols(full_reply)
            if clean_reply:
                generate_and_play_voice(clean_reply)

        except KeyboardInterrupt:
            print("\n\nProgram dihentikan.")
            break

if __name__ == "__main__":
    main()