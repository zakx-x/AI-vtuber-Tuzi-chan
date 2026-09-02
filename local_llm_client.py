import json
import re
import ai_tools
import pc_controller
import requests
import vision_tools

OLLAMA_BASE_URL = "http://127.0.0.1:11434"
MODEL_NAME = "qwen2.5:3b"


class LocalLLMClient:

  def __init__(self, model_name: str = MODEL_NAME):
    self.model = model_name
    self.history = []
    self.active_language = "id"

  def _detect_and_lock_language(self, text: str):
    lower = text.lower()
    if any(
        k in lower
        for k in [
            "bahasa jepang",
            "pake bahasa jepang",
            "ngomong jepang",
            "bahasa nihongo",
            "speak japanese",
        ]
    ):
      self.active_language = "ja"
      print("\n[Language Lock] 🔒 Mode Bahasa: JEPANG (日本語)")
    elif any(
        k in lower
        for k in [
            "bahasa indonesia",
            "pake bahasa indo",
            "kembali ke indonesia",
            "ngomong indo",
            "bahasa biasa",
        ]
    ):
      self.active_language = "id"
      print("\n[Language Lock] 🔒 Mode Bahasa: INDONESIA")
    elif any(
        k in lower
        for k in [
            "bahasa inggris",
            "pake bahasa inggris",
            "ngomong inggris",
            "speak english",
        ]
    ):
      self.active_language = "en"
      print("\n[Language Lock] 🔒 Mode Bahasa: INGGRIS (English)")

  def stream_response(self, user_query: str):
    self._detect_and_lock_language(user_query)

    vision_context = ""
    if vision_tools.is_vision_query(user_query):
      screen_desc = vision_tools.analyze_screen(user_query)
      vision_context = f"\n[Layar Komputer Saat Ini]: {screen_desc}\n"

    action_result = pc_controller.handle_pc_action(user_query)
    action_context = ""
    if action_result:
      action_context = f"\n[Aksi PC Berhasil]: {action_result}\n"

    current_time = ai_tools.get_current_time_info()
    web_context = ""
    if (
        not action_result
        and not vision_context
        and ai_tools.needs_web_search(user_query)
    ):
      search_data = ai_tools.search_internet(user_query, max_results=3)
      web_context = f"\n[Data Internet]:\n{search_data}\n"

    if self.active_language == "ja":
      lang_instruction = """ATURAN BAHASA JEPANG + TERJEMAHAN:
- Jawab dalam Bahasa Jepang murni (Hiragana/Katakana/Kanji).
- DILARANG menggunakan Bahasa Mandarin/Hanzi China.
- WAJIB sertakan terjemahan Bahasa Indonesia di akhir menggunakan tag [TRANS: arti bahasa indonesia].
Contoh format:
[EMO:happy] 初めまして！私はトゥジだよ、よろしくね！ [TRANS: Senang bertemu denganmu! Aku Tuzi, salam kenal ya!]"""
    elif self.active_language == "en":
      lang_instruction = """ENGLISH MODE WITH INDONESIAN TRANSLATION:
- Answer in English, and ALWAYS append Indonesian translation at the end using [TRANS: terjemahan indonesia]."""
    else:
      lang_instruction = (
          "Mode: BAHASA INDONESIA santai dan natural. (Tidak perlu tag"
          " [TRANS:])."
      )

    system_prompt = f"""Kamu adalah Tuzi, asisten virtual anime perempuan yang cerdas dan ekspresif.
Waktu saat ini: {current_time}.
{vision_context}
{action_context}
{web_context}

{lang_instruction}

ATURAN EMOSI:
- Awali jawaban dengan SATU tag: [EMO:happy], [EMO:sad], [EMO:angry], [EMO:jealous], atau [EMO:neutral].
- Jawab ringkas dan padat (1-2 kalimat)."""

    messages = [{"role": "system", "content": system_prompt}]
    for h in self.history:
      messages.append(h)
    messages.append({"role": "user", "content": user_query})

    payload = {
        "model": self.model,
        "messages": messages,
        "stream": True,
        "options": {"temperature": 0.75},
    }

    full_response_text = ""
    try:
      res = requests.post(
          f"{OLLAMA_BASE_URL}/api/chat", json=payload, stream=True, timeout=30
      )
      if res.status_code != 200:
        yield f"Error: {res.status_code}"
        return

      for line in res.iter_lines():
        if line:
          chunk = json.loads(line.decode("utf-8"))
          msg = chunk.get("message", {}).get("content", "")
          if msg:
            full_response_text += msg
            yield msg

      self.history.append({"role": "user", "content": user_query})
      self.history.append({"role": "assistant", "content": full_response_text})
      if len(self.history) > 8:
        self.history = self.history[-8:]

    except Exception as e:
      yield f"Error: {e}"