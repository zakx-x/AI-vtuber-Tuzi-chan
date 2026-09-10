import os
import time
import asyncio
import requests
import edge_tts
import torch

APPLIO_PYTHON = r"E:\Applio-main\env\python.exe"

print("=" * 60)
print("🔍 BENCHMARK KECEPATAN SETIAP KOMPONEN TUZI")
print("=" * 60)

print("\n[1/3] Memeriksa PyTorch & GPU...")
check_gpu_cmd = f'"{APPLIO_PYTHON}" -c "import torch; print(\'CUDA Available:\', torch.cuda.is_available()); print(\'Device Name:\', torch.cuda.get_device_name(0) if torch.cuda.is_available() else \'HANYA CPU\')"'
os.system(check_gpu_cmd)

async def test_edge():
    t0 = time.time()
    comm = edge_tts.Communicate("Halo Zaki, ini tes kecepatan Edge TTS.", "id-ID-GadisNeural", pitch="+14Hz", rate="+5%")
    await comm.save("bench_raw.wav")
    print(f"[2/3] Edge-TTS (Cloud) Selesai dalam : {time.time() - t0:.2f} detik")

asyncio.run(test_edge())

t0 = time.time()
payload = {
    "input_path": os.path.abspath("bench_raw.wav"),
    "output_path": os.path.abspath("bench_zeta.wav"),
    "pitch": 4,
    "f0_method": "rmvpe",
    "index_rate": 1.0,
    "protect": 0.15
}
try:
    res = requests.post("http://127.0.0.1:5050/infer", json=payload, timeout=30)
    if res.status_code == 200:
        print(f"[3/3] Fast Zeta Server (Lokal)       : {time.time() - t0:.2f} detik")
    else:
        print(f"[3/3] Fast Server Error ({res.status_code}): {res.text}")
except Exception as e:
    print(f"[3/3] Fast Server Gagal Dihubungi : {e}")

print("=" * 60)