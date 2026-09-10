import asyncio
import os
import config
import edge_tts
import numpy as np
import sounddevice as sd
import soundfile as sf


class TTSEngine:

  def __init__(self, avatar_canvas):
    self.canvas = avatar_canvas
    self.temp_audio_file = "temp_voice.mp3"

  async def speak_with_lipsync(self, text: str):
    if not text or not text.strip():
      return

    communicate = edge_tts.Communicate(text, config.VOICE_NAME)
    await communicate.save(self.temp_audio_file)

    try:
      data, samplerate = sf.read(self.temp_audio_file, dtype="float32")

      if len(data.shape) > 1:
        samples = data.mean(axis=1)
      else:
        samples = data

      if len(samples) == 0:
        return

      sd.play(samples, samplerate=samplerate)

      frame_duration = 1 / 30
      chunk_size = int(samplerate * frame_duration)

      for i in range(0, len(samples), chunk_size):
        chunk = samples[i : i + chunk_size]
        if len(chunk) > 0:
          rms = np.sqrt(np.mean(chunk**2))
          mouth_val = np.clip(rms * 4.0, 0.0, 1.0)
          self.canvas.set_mouth(mouth_val)

        await asyncio.sleep(frame_duration)

      self.canvas.set_mouth(0.0)

    except Exception as e:
      print(f"[TTS Error] {e}")
    finally:
      if os.path.exists(self.temp_audio_file):
        try:
          os.remove(self.temp_audio_file)
        except PermissionError:
          pass