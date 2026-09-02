import asyncio
import os
import subprocess
import edge_tts

BASE_DIR = r"E:\TuziSideProjectAI"
APPLIO_DIR = r"E:\Applio-main"
APPLIO_PYTHON = os.path.join(APPLIO_DIR, "env", "python.exe")
APPLIO_CORE = os.path.join(APPLIO_DIR, "core.py")

raw_wav = os.path.join(BASE_DIR, "test_input.wav")
out_wav = os.path.join(BASE_DIR, "test_output_zeta.wav")
model_path = os.path.join(APPLIO_DIR, "logs", "zetaTest", "zetaTest.pth")
index_path = os.path.join(APPLIO_DIR, "logs", "zetaTest", "zeta.index")


async def test():
  print("1. Menghasilkan Audio Dasar (Edge-TTS)...")
  comm = edge_tts.Communicate(
      "Halo, ini adalah tes suara Vestia Zeta yang sudah berhasil terhubung!",
      "id-ID-GadisNeural",
  )
  await comm.save(raw_wav)
  print("   Audio dasar berhasil dibuat.")

  print("\n2. Mengonversi Audio ke Suara Zeta via Applio Engine...")
  cmd = [
      APPLIO_PYTHON,
      APPLIO_CORE,
      "infer",
      "--f0_method",
      "pm",
      "--f0_up_key",
      "0",
      "--index_rate",
      "0.75",
      "--model",
      model_path,
      "--index",
      index_path,
      "--input_path",
      raw_wav,
      "--output_path",
      out_wav,
  ]

  res = subprocess.run(cmd, capture_output=True, text=True, cwd=APPLIO_DIR)
  if os.path.exists(out_wav) and os.path.getsize(out_wav) > 1000:
    print("\n[BERHASIL] File 'test_output_zeta.wav' berhasil dibuat!")
    print("Suara Zeta berhasil dikonversi 100% lokal.")
  else:
    print("\n[ERROR Output]:", res.stderr or res.stdout)


asyncio.run(test())