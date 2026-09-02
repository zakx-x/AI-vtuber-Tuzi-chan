import os
import ai_tools
from google import genai
from google.genai import types

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "YOUR_GEMINI_API_KEY")


class LLMClient:

  def __init__(self):
    self.client = genai.Client(api_key=GEMINI_API_KEY)
    self.model_name = "gemini-2.5-flash"

  def build_system_prompt(self, user_query: str) -> str:
    current_time = ai_tools.get_current_time_info()

    web_context = ""
    if ai_tools.needs_web_search(user_query):
      print(f"\n[AI Tools] 🌐 Mencari info internet untuk: '{user_query}'...")
      search_data = ai_tools.search_internet(user_query, max_results=3)
      web_context = (
          f"\n\n[Informasi Terkini dari Internet]:\n{search_data}\n"
          "Gunakan informasi di atas jika relevan untuk menjawab."
      )

    prompt = (
        "Kamu adalah Tuzi, asisten virtual anime perempuan yang ramah, cerdas, dan imut.\n"
        f"- Waktu & Tanggal saat ini: {current_time}.\n"
        "- Berbicaralah dengan gaya santai dan bersahabat.\n"
        "- Jawab secara ringkas, padat, dan jelas agar enak didengar saat disuarakan TTS.\n"
        f"{web_context}"
    )
    return prompt

  def stream_response(self, user_query: str):
    system_instruction = self.build_system_prompt(user_query)

    try:
      response = self.client.models.generate_content_stream(
          model=self.model_name,
          contents=user_query,
          config=types.GenerateContentConfig(
              system_instruction=system_instruction,
              temperature=0.7,
          ),
      )
      for chunk in response:
        if chunk.text:
          yield chunk.text
    except Exception as e:
      yield f"Maaf, terjadi kendala saat memproses jawaban: {e}"