import os
import glob
from PIL import Image

# Tentukan lokasi folder model berdasarkan struktur foldermu
base_dir = os.path.dirname(os.path.abspath(__file__))
model_folder = os.path.join(
    base_dir, 
    "Assets", 
    "model", 
    "tuziv2", 
    "core"
)

def resize_all_textures(folder_path, max_size=2048):
    if not os.path.exists(folder_path):
        print(f"Folder tidak ditemukan: {folder_path}")
        return

    # Cari SEMUA file .png di dalam folder tersebut
    png_files = glob.glob(os.path.join(folder_path, "*.png"))
    
    if not png_files:
        print("Tidak ada file PNG di dalam folder tersebut.")
        return

    for path in png_files:
        try:
            img = Image.open(path)
            print(f"Memproses {os.path.basename(path)} | Resolusi asli: {img.size}")

            if img.size[0] > max_size or img.size[1] > max_size:
                print(f"  -> Mengecilkan menjadi maksimal {max_size}x{max_size}...")
                img.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
                img.save(path, optimize=True)
                print(f"  -> Berhasil! Resolusi baru: {img.size}")
            else:
                print(f"  -> Aman! Sudah di bawah {max_size}px.")
        except Exception as e:
            print(f"  -> Gagal memproses {os.path.basename(path)}: {e}")

if __name__ == "__main__":
    resize_all_textures(model_folder)