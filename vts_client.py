import asyncio
import pyvts
import config


class VTSController:

  def __init__(self):
    self.vts = pyvts.vts(
        plugin_info={
            "plugin_name": "AIVTuberAssistant",
            "developer": "Dev",
            "authentication_token_path": config.VTS_TOKEN_PATH,
        },
        port=config.VTS_PORT,
    )
    self.is_connected = False

  async def connect(self):
    """Menghubungkan dan melakukan otentikasi dengan VTube Studio."""
    try:
      await self.vts.connect()
      await self.vts.request_authenticate_token()
      await self.vts.request_authenticate()
      self.is_connected = True
      print("[VTS] Berhasil terhubung ke VTube Studio.")
    except Exception as e:
      print(f"[VTS Error] Gagal terhubung ke VTube Studio: {e}")
      self.is_connected = False

  async def set_mouth_open(self, value: float):
    """Menggerakkan mulut avatar (nilai 0.0 sampai 1.0)."""
    if not self.is_connected:
      return

    # Batasi nilai rentang 0.0 - 1.0
    val = max(0.0, min(1.0, float(value)))

    parameter_data = {
        "mode": "set",
        "parameterValues": [{"id": "MouthOpen", "value": val}],
    }
    try:
      await self.vts.websocket.send(
          pyvts.vts_request.custom_request(
              "InjectParameterDataRequest", parameter_data
          )
      )
    except Exception:
      pass

  async def close(self):
    if self.is_connected:
      await self.vts.close()