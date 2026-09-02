import asyncio
import io
import re
import numpy as np
import requests
import sounddevice as sd
import soundfile as sf

VOICEVOX_URL = "http://127.0.0.1:50021"

# Speaker ID Rekomendasi Karakter Anime:
# 2 = Shikikano (Lembut) | 3 = Zundamon (Ceria) | 8 = Namine Ritsu (Cool/Anime) | 14 = Meimei
DEFAULT_SPEAKER_ID = 3


def clean_text_for_speech(text: str) -> str:
  text = re.sub(r"\*.*?\*", "", text)
  text = re.sub(r"[:;=8][\-o\*\']?[\)\]\(\[dDpP/\:\}\{@\|\\]", "", text)
  text = re.sub(r"\^\^|\^_\^", "", text)
  emoji_pattern = re.compile(
      "["
      "\U0001f600-\U0001f64f"
      "\U0001f300-\U0001f5ff"
      "\U0001f680-\U0001f6ff"
      "\U0001f1e0-\U0001f1ff"
      "\u2600-\u26ff"
      "\u2700-\u27bf"
      "\U0001f900-\U0001f9ff"
      "\U0001fa70-\U0001faff"
      "]+",
      flags=re.UNICODE,
  )
  text = emoji_pattern.sub(r"", text)
  return re.sub(r"\s+", " ", text).strip()


class VoicevoxTTSEngine:

  def __init__(self, bridge, speaker_id: int = DEFAULT_SPEAKER_ID):
    self.bridge = bridge
    self.speaker_id = speaker_id
    self._check_connection()

  def _check_connection(self):
    try:
      res = requests.get(f"{VOICEVOX_URL}/version", timeout=3)
      if res.status_code == 200:
        print(f"[VOICEVOX] Terhubung ke engine lokal (Versi {res.json()})")
        print(f"[VOICEVOX] Speaker ID Aktif: {self.speaker_id}\n")
    except requests.exceptions.ConnectionError:
      print(
          "[VOICEVOX Peringatan] Engine VOICEVOX belum dibuka di"
          " http://127.0.0.1:50021"
      )

  async def speak_with_lipsync(self, text: str):
    speech_text = clean_text_for_speech(text)
    if not speech_text:
      return

    try:
      # 1. Buat query audio dari teks
      query_res = requests.post(
          f"{VOICEVOX_URL}/audio_query",
          params={"text": speech_text, "speaker": self.speaker_id},
          timeout=10,
      )
      if query_res.status_code != 200:
        return

      query_data = query_res.json()

      # 2. Sintesis audio langsung ke buffer memori (tanpa simpan ke disk)
      synth_res = requests.post(
          f"{VOICEVOX_URL}/synthesis",
          params={"speaker": self.speaker_id},
          json=query_data,
          timeout=15,
      )
      if synth_res.status_code != 200:
        return

      # 3. Baca data WAV langsung dari memory stream
      audio_data = io.BytesIO(synth_res.content)
      data, samplerate = sf.read(audio_data, dtype="float32")
      samples = data.mean(axis=1) if len(data.shape) > 1 else data

      if len(samples) == 0:
        return

      # 4. Putar audio dan sinkronkan gerakan mulut avatar
      sd.play(samples, samplerate=samplerate)

      frame_duration = 1 / 30
      chunk_size = int(samplerate * frame_duration)

      for i in range(0, len(samples), chunk_size):
        chunk = samples[i : i + chunk_size]
        if len(chunk) > 0:
          rms = np.sqrt(np.mean(chunk**2))
          mouth_val = float(np.clip(rms * 4.5, 0.0, 1.0))
          self.bridge.mouth_signal.emit(mouth_val)

        await asyncio.sleep(frame_duration)

      self.bridge.mouth_signal.emit(0.0)

    except Exception as e:
      print(f"[VOICEVOX Error] {e}")