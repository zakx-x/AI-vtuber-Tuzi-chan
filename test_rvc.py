import os
import edge_tts
import asyncio
from rvc_python.infer import infer_file

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
model_path = os.path.join(BASE_DIR, "models_rvc", "zetaTest.pth")
index_path = os.path.join(BASE_DIR, "models_rvc", "zeta.index")
raw_wav = os.path.join(BASE_DIR, "test_raw.wav")
out_wav = os.path.join(BASE_DIR, "test_zeta.wav")

print("1. Cek Model RVC:")
print(f"   Model PTH : {model_path} -> {'DITEMUKAN' if os.path.exists(model_path) else 'TIDAK DITEMUKAN!'}")
print(f"   Index File: {index_path} -> {'DITEMUKAN' if os.path.exists(index_path) else 'TIDAK DITEMUKAN!'}")

async def test():
    print("\n2. Menghasilkan Audio Dasar (Edge-TTS)...")
    comm = edge_tts.Communicate("Halo, ini tes suara Vestia Zeta.", "id-ID-GadisNeural")
    await comm.save(raw_wav)
    print("   Audio dasar berhasil dibuat.")

    print("\n3. Mengonversi Suara via RVC...")
    try:
        infer_file(
            input_path=raw_wav,
            model_path=model_path,
            index_path=index_path if os.path.exists(index_path) else "",
            opt_path=out_wav,
            f0_up_key=0,
            f0_method="pm",
            device="cuda:0"
        )
        if os.path.exists(out_wav) and os.path.getsize(out_wav) > 1000:
            print("\n[BERHASIL] File test_zeta.wav berhasil dibuat dengan suara Zeta!")
        else:
            print("\n[GAGAL] File output kosong.")
    except Exception as e:
        print(f"\n[ERROR RVC]: {e}")

asyncio.run(test())