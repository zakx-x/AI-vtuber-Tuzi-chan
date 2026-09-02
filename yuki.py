from openai import OpenAI

# Gunakan Gemini/Groq via Base URL atau Ollama secara lokal
client = OpenAI(
    base_url="http://localhost:11434/v1", # Ganti jika memakai cloud API
    api_key="ollama"                      # Masukkan API Key jika menggunakan cloud
)

def generate_ai_response(user_input: str) -> str:
    response = client.chat.completions.create(
        model="qwen2.5:7b", # atau "gemini-2.0-flash" / "llama-3.1-8b-instant"
        messages=[
            {
                "role": "system",
                "content": (
                    "Kamu adalah asisten AI virtual berbasis avatar VTuber. "
                    "Jawablah dengan nada ramah, ringkas, dan ekspresif."
                )
            },
            {"role": "user", "content": user_input}
        ],
        max_tokens=150
    )
    return response.choices[0].message.content