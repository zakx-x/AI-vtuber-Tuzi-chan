import asyncio
import copy
import dataclasses
import enum
import os
import re
import sys
import types
import torch

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# 1. Cari path file hubert_base.pt lokal (185 MB)
CANDIDATE_PATHS = [
    os.path.join(BASE_DIR, "hubert_base.pt"),
    os.path.join(BASE_DIR, "Assets", "hubert", "hubert_base.pt"),
    os.path.join(BASE_DIR, "assets", "hubert", "hubert_base.pt"),
    os.path.join(
        BASE_DIR, "venv", "Lib", "site-packages", "rvc_python", "hubert_base.pt"
    ),
    os.path.join(
        BASE_DIR,
        "venv",
        "Lib",
        "site-packages",
        "rvc_python",
        "assets",
        "hubert",
        "hubert_base.pt",
    ),
]

HUBERT_PATH = None
for p in CANDIDATE_PATHS:
  if os.path.exists(p) and os.path.getsize(p) > 1000000:
    HUBERT_PATH = os.path.abspath(p)
    break

if not HUBERT_PATH:
  raise FileNotFoundError(
      f"File hubert_base.pt (~185MB) tidak ditemukan di direktori {BASE_DIR}!"
  )

# ==============================================================================
# 2. RUNTIME PATCH DATACLASS PYTHON 3.11 (Fairseq Fix)
# ==============================================================================
_orig_get_field = dataclasses._get_field


def _make_safe_factory(v):
  t = type(v)
  if isinstance(v, list):
    return lambda: list(v)
  if isinstance(v, dict):
    return lambda: dict(v)
  if isinstance(v, set):
    return lambda: set(v)
  try:
    _ = t()
    return lambda: t()
  except Exception:
    return lambda: v


def _patched_get_field(cls, a_name, a_type, default_kw_only):
  try:
    return _orig_get_field(cls, a_name, a_type, default_kw_only)
  except ValueError as e:
    if "mutable default" in str(e):
      val = getattr(cls, a_name)
      setattr(
          cls,
          a_name,
          dataclasses.field(default_factory=_make_safe_factory(val)),
      )
      return _orig_get_field(cls, a_name, a_type, default_kw_only)
    raise


dataclasses._get_field = _patched_get_field

# ==============================================================================
# 3. RUNTIME SHIM OMEGACONF (HuBERT Safe Defaults)
# ==============================================================================
try:
  import omegaconf
  import omegaconf.errors

  if not hasattr(omegaconf, "SCMode"):

    class SCMode(enum.Enum):
      NONE = 0
      DICT = 1
      LIST = 2
      INSTANTIATE = 3
      DEFAULT = 4

    omegaconf.SCMode = SCMode

  if not hasattr(omegaconf.errors, "InterpolationResolutionError"):

    class InterpolationResolutionError(Exception):
      pass

    omegaconf.errors.InterpolationResolutionError = InterpolationResolutionError

  _HUBERT_DEFAULTS = {
      "required_seq_len_multiple": 2,
      "pos_conv_depth": 1,
      "conv_pos": 128,
      "conv_pos_groups": 16,
      "depthwise_conv_kernel_size": 31,
      "checkpoint_activations": False,
      "attn_type": "",
      "pos_enc_type": "abs",
      "fp16": False,
      "print_alignment": None,
      "layer_type": "transformer",
      "encoder_layer_type": "transformer",
  }

  _orig_dictconfig_getattr = omegaconf.DictConfig.__getattr__

  def _lenient_getattr(self, key):
    try:
      val = _orig_dictconfig_getattr(self, key)
      if val is not None:
        return val
    except Exception:
      pass

    if key in _HUBERT_DEFAULTS:
      return _HUBERT_DEFAULTS[key]

    raise AttributeError(f"DictConfig tidak memiliki atribut '{key}'")

  omegaconf.DictConfig.__getattr__ = _lenient_getattr
except Exception:
  pass

mock_init = types.ModuleType("fairseq.dataclass.initialize")
mock_init.hydra_init = lambda *args, **kwargs: None
mock_init.add_defaults = lambda *args, **kwargs: None
sys.modules["fairseq.dataclass.initialize"] = mock_init

# ==============================================================================
# 4. PATCH FAIRSEQ CHECKPOINT LOADER & MODEL BUILDER
# ==============================================================================
import fairseq.checkpoint_utils
import fairseq.dataclass.utils
import fairseq.models

fairseq.checkpoint_utils._upgrade_state_dict = lambda state: state


def safe_merge_with_parent(dc, cfg, from_checkpoint=False):
  default_dict = dict(_HUBERT_DEFAULTS)
  if callable(dc):
    try:
      inst = dc()
      if dataclasses.is_dataclass(inst):
        for f in dataclasses.fields(inst):
          val = getattr(inst, f.name, None)
          if val is not None:
            default_dict[f.name] = val
    except Exception:
      pass
  if cfg is not None:
    if isinstance(cfg, omegaconf.DictConfig):
      default_dict.update(omegaconf.OmegaConf.to_container(cfg, resolve=False))
    elif isinstance(cfg, dict):
      default_dict.update(cfg)
  merged = omegaconf.OmegaConf.create(default_dict)
  omegaconf.OmegaConf.set_struct(merged, False)
  return merged


fairseq.dataclass.utils.merge_with_parent = safe_merge_with_parent
fairseq.models.merge_with_parent = safe_merge_with_parent

# ==============================================================================
# 5. PRE-LOAD HUBERT & INJEKSI LANGSUNG KE SEMUA SUBMODUL RVC
# ==============================================================================
import rvc_python.download_model as rvc_dl
import rvc_python.infer as rvc_infer
import rvc_python.modules.vc.modules as rvc_vc_modules
import rvc_python.modules.vc.utils as rvc_vc_utils

# Matikan total fungsi auto-download agar tidak pernah freeze
rvc_dl.download_hubert = lambda *args, **kwargs: None
rvc_dl.download_rmvpe = lambda *args, **kwargs: None
rvc_dl.download_all = lambda *args, **kwargs: None

print(f"\n[HuBERT Loader] Memuat model HuBERT dari: {HUBERT_PATH}")
models, _, _ = fairseq.checkpoint_utils.load_model_ensemble_and_task(
    [HUBERT_PATH], suffix=""
)
hubert_model = models[0]
device = "cuda:0" if torch.cuda.is_available() else "cpu"
hubert_model = hubert_model.to(device).float()
hubert_model.eval()
print("[HuBERT Loader] Model HuBERT 185 MB berhasil dimuat ke VRAM GPU!\n")

# Injeksi model HuBERT yang aktif ke SEMUA namespace internal rvc-python
dummy_loader = lambda *args, **kwargs: hubert_model

for mod in [rvc_vc_utils, rvc_vc_modules, rvc_infer]:
  setattr(mod, "hubert_model", hubert_model)
  setattr(mod, "load_hubert", dummy_loader)
  if hasattr(mod, "download_hubert"):
    setattr(mod, "download_hubert", lambda *args, **kwargs: None)

# ==============================================================================
# 6. LOAD RVC INFERENCE & RESTORE STANDARD DATACLASS
# ==============================================================================
from rvc_python.infer import RVCInference

dataclasses._get_field = _orig_get_field

import config
import edge_tts
import numpy as np
import sounddevice as sd
import soundfile as sf

RVC_MODEL_PATH = os.path.join(
    BASE_DIR, "Assets", "voices", "rvc", "copanorickey_325e_24700s.pth"
)
RVC_INDEX_PATH = os.path.join(
    BASE_DIR, "Assets", "voices", "rvc", "copanorickey.index"
)


def clean_text_for_speech(text: str) -> str:
  text = re.sub(r"\*.*?\*", "", text)
  text = re.sub(r"[:;=8][\-o\*\']?[\)\]\(\[dDpP/\:\}\{@\|\\]", "", text)
  text = re.sub(r"\^\^|\^_\^", "", text)
  emoji_pattern = re.compile(
      "["
      "\U0001f600-\U0001f64f"
      "\U0001f300-\U0001f5ff"
      "\U0001f680-\U0001f6ff"
      "\U0001f1e0-\U0001f1ff"
      "\u2600-\u26ff"
      "\u2700-\u27bf"
      "\U0001f900-\U0001f9ff"
      "\U0001fa70-\U0001faff"
      "]+",
      flags=re.UNICODE,
  )
  text = emoji_pattern.sub(r"", text)
  return re.sub(r"\s+", " ", text).strip()


class RVCTTSEngine:

  def __init__(self, bridge):
    self.bridge = bridge
    self.temp_base_audio = "temp_base.wav"
    self.temp_rvc_audio = "temp_rvc.wav"

    print(
        "[RVC Engine] Mengaktifkan model Copano Rickey di GPU (GTX 1650 Ti)..."
    )
    self.rvc = RVCInference(device="cuda:0")

    # Kunci referensi model di instance VC
    self.rvc.hubert_model = hubert_model
    if hasattr(self.rvc, "vc"):
      self.rvc.vc.hubert_model = hubert_model

    self.rvc.load_model(RVC_MODEL_PATH)
    if os.path.exists(RVC_INDEX_PATH):
      self.rvc.set_index(RVC_INDEX_PATH)
    print("\n[RVC Engine] Berhasil! Model suara Copano Rickey siap digunakan.\n")

  async def speak_with_lipsync(self, text: str):
    speech_text = clean_text_for_speech(text)
    if not speech_text:
      return

    # 1. Generate audio dasar via Edge-TTS
    communicate = edge_tts.Communicate(speech_text, config.VOICE_NAME)
    await communicate.save(self.temp_base_audio)

    # 2. Konversi timbre suara ke Copano Rickey via RVC
    try:
      self.rvc.infer_file(
          input_path=self.temp_base_audio,
          output_path=self.temp_rvc_audio,
          f0_up_key=0,  # Ubah ke 12 jika ingin pitch lebih tinggi/feminin
          f0_method="pm",  # Algoritma paling cepat dan ringan untuk GTX 1650 Ti
          index_rate=0.75,
      )

      # 3. Putar audio dan sinkronkan gerakan mulut avatar Live2D
      data, samplerate = sf.read(self.temp_rvc_audio, dtype="float32")
      samples = data.mean(axis=1) if len(data.shape) > 1 else data

      if len(samples) == 0:
        return

      sd.play(samples, samplerate=samplerate)

      frame_duration = 1 / 30
      chunk_size = int(samplerate * frame_duration)

      for i in range(0, len(samples), chunk_size):
        chunk = samples[i : i + chunk_size]
        if len(chunk) > 0:
          rms = np.sqrt(np.mean(chunk**2))
          mouth_val = float(np.clip(rms * 4.2, 0.0, 1.0))
          self.bridge.mouth_signal.emit(mouth_val)

        await asyncio.sleep(frame_duration)

      self.bridge.mouth_signal.emit(0.0)

    except Exception as e:
      print(f"[RVC Error] {e}")
    finally:
      for temp_file in [self.temp_base_audio, self.temp_rvc_audio]:
        if os.path.exists(temp_file):
          try:
            os.remove(temp_file)
          except PermissionError:
            pass