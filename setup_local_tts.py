import os
import urllib.request

models_dir = r"E:\TuziSideProjectAI\models_local_tts"
os.makedirs(models_dir, exist_ok=True)

files = {
    "id_model.onnx": (
        "https://huggingface.co/rhasspy/piper-voices/resolve/main/id/id_ID/indotts/medium/id_ID-indotts-medium.onnx"
    ),
    "id_model.onnx.json": (
        "https://huggingface.co/rhasspy/piper-voices/resolve/main/id/id_ID/indotts/medium/id_ID-indotts-medium.onnx.json"
    ),
}

print("Mengunduh model Local TTS (Piper Indonesian)...")
for filename, url in files.items():
  dest = os.path.join(models_dir, filename)
  if not os.path.exists(dest):
    print(f"Mengunduh {filename}...")
    urllib.request.urlretrieve(url, dest)
    print(f"Selesai: {filename}")
  else:
    print(f"File sudah ada: {filename}")

print("\nModel Local TTS siap digunakan secara 100% offline!")