import asyncio
import os
import sys
import threading
from avatar_engine import AvatarWindow
import config
from llm_client import LLMClient
from PySide6.QtWidgets import QApplication
from tts_engine import TTSEngine

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# Gunakan forward slash
MODEL_PATH = os.path.join(
    BASE_DIR, "assets", "model", "tuzi mian.model3.json"
).replace("\\", "/")


def chat_worker(tts_engine, llm_client):
  loop = asyncio.new_event_loop()
  asyncio.set_event_loop(loop)

  print("\n[AI Assistant Siap! Ketik pesan Anda di terminal]")
  print("Ketik 'exit' untuk keluar.\n")

  while True:
    try:
      user_input = input("User: ")
      if user_input.strip().lower() in ["exit", "quit", "keluar"]:
        print("Menutup sesi...")
        break

      if not user_input.strip():
        continue

      print("[AI sedang berpikir...]")
      ai_response = llm_client.get_response(user_input)
      print(f"Assistant: {ai_response}\n")

      loop.run_until_complete(tts_engine.speak_with_lipsync(ai_response))

    except Exception as e:
      print(f"[Error] {e}")


def main():
  if not os.path.exists(MODEL_PATH):
    print(f"[ERROR] File model tidak ditemukan di:\n{MODEL_PATH}")
    return

  app = QApplication(sys.argv)

  window = AvatarWindow(model_json_path=MODEL_PATH)
  window.show()

  tts = TTSEngine(avatar_canvas=window.canvas)
  llm = LLMClient()

  worker = threading.Thread(
      target=chat_worker, args=(tts, llm), daemon=True
  )
  worker.start()

  sys.exit(app.exec())


if __name__ == "__main__":
  main()