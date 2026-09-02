import speech_recognition as sr


class STTEngine:

  def __init__(self, language: str = "id-ID"):
    self.recognizer = sr.Recognizer()
    self.language = language

    # 1. Toleransi jeda hening setelah berbicara (dinaikkan ke 1.8 detik)
    # AI akan menunggu hening selama 1.8 detik sebelum menganggap kalimat selesai
    self.recognizer.pause_threshold = 1.8

    # 2. Toleransi keheningan jeda antar kata saat Anda berpikir
    self.recognizer.non_speaking_duration = 1.0

    # 3. Waktu minimum suara berbicara agar terdeteksi (mencegah desahan/klik terpotong)
    self.recognizer.phrase_threshold = 0.3

    # 4. Sensitivitas mikrofon (noise threshold dinamis)
    self.recognizer.dynamic_energy_threshold = True
    self.recognizer.energy_threshold = 300

  def listen_voice(self) -> str:
    with sr.Microphone() as source:
      # Kalibrasi noise ruangan selama 1 detik agar lebih akurat membedakan suara Anda dan hening
      self.recognizer.adjust_for_ambient_noise(source, duration=0.8)
      print("\n[Mic] 🎙️ Mendengarkan... (Silakan bicara)")

      try:
        # Rekam audio dengan batas durasi bicara hingga 30 detik
        audio = self.recognizer.listen(
            source, timeout=None, phrase_time_limit=30
        )
        print("[Mic] ⏳ Menerjemahkan suara...")

        text = self.recognizer.recognize_google(audio, language=self.language)
        return text.strip()

      except sr.UnknownValueError:
        return ""
      except sr.RequestError as e:
        print(f"[STT Error] Gagal terhubung ke layanan speech: {e}")
        return ""
      except Exception as e:
        print(f"[STT Error] {e}")
        return ""