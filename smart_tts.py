import asyncio
import os
import re
import socket
import time
import wave  # <-- Modul baru untuk memperbaiki format audio ElevenLabs
import requests
import sounddevice as sd
import soundfile as sf
import numpy as np
import edge_tts

# --- FIX GETADDRINFO IPV6 ---
_orig_getaddrinfo = socket.getaddrinfo
def _ipv4_getaddrinfo(*args, **kwargs):
    responses = _orig_getaddrinfo(*args, **kwargs)
    ipv4_responses = [r for r in responses if r[0] == socket.AF_INET]
    return ipv4_responses if ipv4_responses else responses
socket.getaddrinfo = _ipv4_getaddrinfo
# ----------------------------

import config
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))

class SmartTTSEngine:
    def __init__(self, bridge=None, default_style="normal"):
        self.bridge = bridge
        self.fast_server_url = "http://127.0.0.1:5050/infer"
        self.eleven_key = getattr(config, "ELEVENLABS_API_KEY", "")
        self.eleven_voice = getattr(config, "ELEVENLABS_VOICE_ID", "EXAVITQu4vr4xnSDxMaL")
        self.edge_voice = getattr(config, "DEFAULT_EDGE_VOICE_ID", "id-ID-ArdiNeural")
        self.f0_method = getattr(config, "RVC_F0_METHOD", "rmvpe")

    def _clean_text_for_speech(self, text: str) -> str:
        cleaned = re.sub(r"<[^>]+>", "", text)
        cleaned = re.sub(r"\[.*?\]", "", cleaned)
        cleaned = re.sub(r"[\U00010000-\U0010ffff\u2600-\u26ff]+", "", cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        return cleaned

    async def _generate_base_elevenlabs(self, text: str, output_wav: str) -> bool:
        if not self.eleven_key or "sk_" not in self.eleven_key:
            return False

        url = f"https://api.elevenlabs.io/v1/text-to-speech/{self.eleven_voice}?output_format=pcm_44100"
        headers = {
            "xi-api-key": self.eleven_key,
            "Content-Type": "application/json"
        }
        
        payload = {
            "text": text,
            "model_id": "eleven_multilingual_v2"
        }
        
        try:
            res = await asyncio.to_thread(requests.post, url, headers=headers, json=payload, timeout=12)
            if res.status_code == 200:
                # Membungkus Raw PCM dari ElevenLabs menjadi format .WAV yang sah
                with wave.open(output_wav, 'wb') as wav_file:
                    wav_file.setnchannels(1)       # Mono
                    wav_file.setsampwidth(2)       # 16-bit
                    wav_file.setframerate(44100)   # 44.1 kHz
                    wav_file.writeframes(res.content)
                return True
            else:
                # Menampilkan alasan pasti jika ElevenLabs masih menolak
                print(f"\n[ElevenLabs Ditolak] Kode 400 | Alasan: {res.text}")
                return False
        except Exception as e:
            print(f"[ElevenLabs Error] {e}")
            return False

    async def _generate_base_edge(self, text: str, output_wav: str) -> bool:
        try:
            comm = edge_tts.Communicate(text, self.edge_voice, rate="+4%", pitch="+5Hz")
            await comm.save(output_wav)
            return os.path.exists(output_wav)
        except Exception:
            return False

    def _convert_via_zeta_model(self, abs_raw_wav: str, abs_out_wav: str, pitch_val: int) -> bool:
        try:
            payload = {
                "input_path": abs_raw_wav,
                "output_path": abs_out_wav,
                "pitch": pitch_val,
                "f0_method": self.f0_method,
                "index_rate": 0.0,
                "protect": 0.33,
            }
            res = requests.post(self.fast_server_url, json=payload, headers={"Connection": "close"}, timeout=15)
            return res.status_code == 200 and os.path.exists(abs_out_wav)
        except Exception:
            return False

    async def speak_with_lipsync(self, text: str, emotion: str = "natural", style_override: str = None):
        clean_text = self._clean_text_for_speech(text)
        if not clean_text or len(clean_text) < 2: return
        
        emo_key = emotion.lower().strip()
        profile = config.EMOTION_PROFILES.get(emo_key, config.EMOTION_PROFILES.get("natural", {}))

        temp_id = int(time.time() * 1000)
        raw_wav = os.path.join(PROJECT_DIR, f"temp_base_{temp_id}.wav")
        zeta_wav = os.path.join(PROJECT_DIR, f"temp_zeta_{temp_id}.wav")

        try:
            engine_used = "ElevenLabs"
            success_base = await self._generate_base_elevenlabs(clean_text, raw_wav)
            pitch_val = profile.get("rvc_pitch", 2) 

            if not success_base:
                engine_used = "Edge-TTS (Fallback)"
                success_base = await self._generate_base_edge(clean_text, raw_wav)
                if "Ardi" in self.edge_voice: pitch_val = 12

            if not success_base: return

            converted = await asyncio.to_thread(self._convert_via_zeta_model, raw_wav, zeta_wav, pitch_val)
            audio_to_play = zeta_wav if converted else raw_wav
            
            if converted:
                print(f" [🎙️ Zeta Voice: OK | Engine: {engine_used} | {emo_key.upper()}]", end="", flush=True)
            
            data, samplerate = sf.read(audio_to_play, dtype="float32")
            await self._play_and_lipsync(data, samplerate)

        except Exception as e:
            print(f"\n[Error] {e}")
        finally:
            for p in [raw_wav, zeta_wav]:
                if os.path.exists(p):
                    try: os.remove(p)
                    except: pass

    async def _play_and_lipsync(self, data, samplerate):
        samples = data.mean(axis=1) if len(data.shape) > 1 else data
        if len(samples) == 0: return
        sd.play(samples, samplerate=samplerate)
        frame_duration = 1 / 30
        chunk_size = int(samplerate * frame_duration)
        for i in range(0, len(samples), chunk_size):
            chunk = samples[i : i + chunk_size]
            if len(chunk) > 0:
                rms = np.sqrt(np.mean(chunk**2))
                if self.bridge: self.bridge.mouth_signal.emit(float(np.clip(rms * 4.5, 0.0, 1.0)))
            await asyncio.sleep(frame_duration)
        sd.wait()
        if self.bridge: self.bridge.mouth_signal.emit(0.0)