import os
import urllib.request
import zipfile

BASE_DIR = os.path.dirname(os.path.abspath(__file__)).replace("\\", "/")
SAMPLE_DIR = f"{BASE_DIR}/Assets/sample_model"
ZIP_PATH = f"{BASE_DIR}/hiyori.zip"

# URL rilis resmi sample model Cubism
URL = "https://github.com/Live2D/CubismWebSamples/archive/refs/heads/develop.zip"

print("[1/3] Mengunduh asset sample dari repositori Live2D...")
headers = {"User-Agent": "Mozilla/5.0"}
req = urllib.request.Request(URL, headers=headers)

with (
    urllib.request.urlopen(req) as response,
    open(ZIP_PATH, "wb") as out_file,
):
  out_file.write(response.read())

print("[2/3] Mengekstrak model Hiyori...")
os.makedirs(f"{SAMPLE_DIR}/Hiyori", exist_ok=True)

with zipfile.ZipFile(ZIP_PATH, "r") as zip_ref:
  # Ekstrak hanya folder model Hiyori
  prefix = (
      "CubismWebSamples-develop/Samples/TypeScript/Demo/public/Resources/Hiyori/"
  )
  for file in zip_ref.namelist():
    if file.startswith(prefix) and not file.endswith("/"):
      rel_path = file[len(prefix) :]
      target_path = os.path.join(SAMPLE_DIR, "Hiyori", rel_path)
      os.makedirs(os.path.dirname(target_path), exist_ok=True)
      with zip_ref.open(file) as src, open(target_path, "wb") as dst:
        dst.write(src.read())

os.remove(ZIP_PATH)
print(
    "[3/3] Selesai! Model Hiyori tersimpan di: Assets/sample_model/Hiyori/"
)