import os
import tempfile
import speech_recognition as sr
from groq import Groq
import config

class STTEngine:
    def __init__(self, language="id-ID"):
        self.recognizer = sr.Recognizer()
        self.recognizer.dynamic_energy_threshold = False
        self.recognizer.energy_threshold = 1200
        self.recognizer.pause_threshold = 1.0
        self.groq_client = Groq(api_key=config.GROQ_API_KEY)

    def listen_voice(self):
        with sr.Microphone() as source:
            #print("\n[🎙️] Mendengarkan...")
            self.recognizer.adjust_for_ambient_noise(source, duration=0.2)
            try:
                audio = self.recognizer.listen(source, timeout=5, phrase_time_limit=10)
                print("[🎙️] Memproses ucapan...")
                
                with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                    f.write(audio.get_wav_data())
                    tmp_path = f.name
                
                with open(tmp_path, "rb") as audio_file:
                    transcription = self.groq_client.audio.transcriptions.create(
                        file=(tmp_path, audio_file.read()),
                        model="whisper-large-v3",
                        prompt="Tuzi, Zak, Jak.",
                        response_format="text"
                    )
                
                try:
                    os.remove(tmp_path)
                except Exception:
                    pass
                
                raw_text = transcription.strip()
                clean_text = raw_text.lower().replace(".", "").replace("!", "").replace("?", "").replace(",", "").strip()
                
                hallucinations = [
                    "thank you",
                    "thank you for watching",
                    "thanks for watching",
                    "please subscribe",
                    "subscribe to my channel",
                    "you",
                    "bye",
                    "transcribe accurately",
                    "hej",
                    "gawsa",
                    "gawsa gawsa",
                    "i just want to say",
                    "oboe",
                    "oboe hello zak"
                ]
                
                if clean_text in hallucinations or len(clean_text) <= 2:
                    return ""
                    
                return raw_text
                
            except sr.WaitTimeoutError:
                return ""
            except Exception as e:
                print(f"[STT Error] {e}")
                return ""