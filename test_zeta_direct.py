import asyncio
import os
import subprocess
import edge_tts

APPLIO_DIR = r"E:\Applio-main"
APPLIO_PYTHON = os.path.join(APPLIO_DIR, "env", "python.exe")
APPLIO_CORE = os.path.join(APPLIO_DIR, "core.py")

model_path = os.path.join(APPLIO_DIR, "logs", "zetaTest", "zetaTest.pth")
index_path = os.path.join(APPLIO_DIR, "logs", "zetaTest", "zeta.index")

raw_input = r"E:\TuziSideProjectAI\test_raw.wav"
zeta_output = r"E:\TuziSideProjectAI\test_zeta.wav"


async def run_test():
  print("1. Membuat audio dasar dengan intonasi anime (Pitch +10Hz)...")
  # Menambahkan modulasi nada dan tempo di Edge-TTS agar tidak datar
  comm = edge_tts.Communicate(
      text=(
          "Halo Zaki! Ini suara Zeta, sekarang karakter suaraku sudah keluar"
          " penuh kan?"
      ),
      voice="id-ID-GadisNeural",
      pitch="+14Hz",  # Menaikkan nada dasar TTS
      rate="+5%",  # Sedikit mempercepat agar intonasi lebih hidup
  )
  await comm.save(raw_input)
  print("   Audio dasar berhasil dibuat.")

  print("\n2. Mengonversi audio dengan karakter Zeta 100%...")
  cmd = [
      APPLIO_PYTHON,
      APPLIO_CORE,
      "infer",
      "--f0-method",
      "rmvpe",
      "--pitch",
      "4",  # Naikkan 2 semitone (+2 hingga +4 untuk vokal anime)
      "--index-rate",
      "1",  # 0.95 = 95% memakai warna vokal asli Zeta
      "--protect",
      "0.15",  # Nilai rendah agar suara asli tidak bocor
      "--pth-path",
      model_path,
      "--index-path",
      index_path,
      "--input-path",
      raw_input,
      "--output-path",
      zeta_output,
  ]

  res = subprocess.run(cmd, capture_output=True, text=True, cwd=APPLIO_DIR)

  if os.path.exists(zeta_output) and os.path.getsize(zeta_output) > 1000:
    print(
        f"\n[SUKSES] Audio Zeta berhasil dibuat di: {zeta_output}\nPutar file"
        " ini untuk mendengarkan perbedaannya!"
    )
  else:
    print("\n[ERROR Output]:\n", res.stderr or res.stdout)


asyncio.run(run_test())