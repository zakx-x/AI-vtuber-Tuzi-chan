import asyncio
import io
import json
import os
import random
import re
import socket
from PIL import Image
import requests
import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

import config
from local_llm_client import LocalLLMClient

app = FastAPI()
llm = LocalLLMClient()

# ==============================================================================
# AUTO TEXTURE DOWNSCALER (4096px -> 1024px untuk Tablet / Mobile GPU)
# ==============================================================================
def optimize_live2d_for_mobile():
    base_dir = "Assets/model"
    source_model_json = os.path.join(base_dir, "tuzi_mian.model3.json")
    mobile_model_json = os.path.join(base_dir, "tuzi_mian_mobile.model3.json")
    
    if not os.path.exists(source_model_json):
        return

    try:
        with open(source_model_json, "r", encoding="utf-8") as f:
            data = json.load(f)

        textures = data.get("FileReferences", {}).get("Textures", [])
        mobile_textures = []

        mobile_tex_dir = os.path.join(base_dir, "tuzi_mian.1024")
        os.makedirs(mobile_tex_dir, exist_ok=True)

        for tex_path in textures:
            full_tex_path = os.path.join(base_dir, tex_path)
            tex_filename = os.path.basename(tex_path)
            mobile_tex_rel_path = f"tuzi_mian.1024/{tex_filename}"
            mobile_tex_full_path = os.path.join(base_dir, mobile_tex_rel_path)

            # Resize hanya jika belum ada atau file 4096px berubah
            if os.path.exists(full_tex_path):
                if not os.path.exists(mobile_tex_full_path):
                    with Image.open(full_tex_path) as img:
                        # Resize ke 1024x1024 untuk membebaskan VRAM GPU Tablet
                        img_resized = img.resize((1024, 1024), Image.Resampling.LANCZOS)
                        img_resized.save(mobile_tex_full_path, "PNG", optimize=True)
                    print(f"[Live2D Optimizer] 🖼️ Downscaled {tex_filename} (4096 -> 1024px)")
                
                mobile_textures.append(mobile_tex_rel_path)
            else:
                mobile_textures.append(tex_path)

        data["FileReferences"]["Textures"] = mobile_textures
        with open(mobile_model_json, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            
    except Exception as e:
        print(f"[Live2D Optimizer Error] {e}")

# Jalankan optimasi otomatis saat server start
optimize_live2d_for_mobile()

app.mount("/Assets", StaticFiles(directory="Assets"), name="Assets")

VOICEVOX_URL = getattr(config, "VOICEVOX_URL", "http://127.0.0.1:50021")
SPEAKER_ID = getattr(config, "DEFAULT_SPEAKER_ID", 2)

ACTIVE_DEVICE = "pc"
connected_clients: dict[str, WebSocket] = {}

def get_local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('10.255.255.255', 1))
        IP = s.getsockname()[0]
    except Exception:
        IP = '127.0.0.1'
    finally:
        s.close()
    return IP

LOCAL_IP = get_local_ip()

# ==============================================================================
# SINTESIS SUARA VOICEVOX
# ==============================================================================
KATAKANA_DICT = {
    "hai": "ハイ", "halo": "ハロー", "hello": "ハロー", "yo": "ヨー",
    "bro": "ブロー", "stfu": "シャラップ", "fuck": "ファック",
    "lu": "ル", "gua": "グア", "apa": "アパ", "bisa": "ビサ", "diem": "ディエム"
}

def text_to_phonetic(text: str) -> str:
    words = re.findall(r"[a-zA-Z0-9']+|[^\w\s]", text)
    res = [KATAKANA_DICT.get(w.lower(), w) for w in words]
    return " ".join(res)

def generate_voicevox_base64(text: str) -> str:
    clean = re.sub(r"<@!?\d+>", "", text).strip()
    if not clean:
        return ""
    phonetic = text_to_phonetic(clean)
    try:
        q = requests.post(f"{VOICEVOX_URL}/audio_query", params={"text": phonetic, "speaker": SPEAKER_ID}, timeout=10)
        if q.status_code != 200:
            return ""
        q_data = q.json()
        q_data["speedScale"] = 1.08
        q_data["pitchScale"] = 0.05
        
        s = requests.post(f"{VOICEVOX_URL}/synthesis", params={"speaker": SPEAKER_ID}, json=q_data, timeout=15)
        if s.status_code == 200:
            import base64
            return base64.b64encode(s.content).decode("utf-8")
    except Exception as e:
        print(f"[Voicevox Error] {e}")
    return ""

# ==============================================================================
# WEBSOCKET STATE & TELEPORTATION
# ==============================================================================
@app.get("/")
async def get_index():
    with open("templates/dimension_view.html", "r", encoding="utf-8") as f:
        html_content = f.read()
    return HTMLResponse(content=html_content)

async def broadcast_state():
    for device_id, ws in list(connected_clients.items()):
        is_active = (device_id == ACTIVE_DEVICE)
        try:
            await ws.send_json({
                "type": "STATE_UPDATE",
                "active_device": ACTIVE_DEVICE,
                "is_current_active": is_active
            })
        except Exception:
            pass

@app.websocket("/ws/{device_id}")
async def websocket_endpoint(websocket: WebSocket, device_id: str):
    global ACTIVE_DEVICE
    device_id = device_id.lower().strip()
    await websocket.accept()
    connected_clients[device_id] = websocket
    print(f"\n[Device Connected] 📱 '{device_id.upper()}' terhubung.")
    
    if ACTIVE_DEVICE not in connected_clients:
        ACTIVE_DEVICE = device_id
        print(f"[Auto-Switch] 🌀 Dimensi dialihkan ke '{device_id.upper()}'.")

    await broadcast_state()

    try:
        while True:
            data = await websocket.receive_json()
            msg_type = data.get("type")

            if msg_type == "TELEPORT_COMMAND":
                target = data.get("target", "tablet").lower()
                ACTIVE_DEVICE = target
                print(f"\n[Teleport Event] 🌀 Tuzi berpindah ke: '{ACTIVE_DEVICE.upper()}'")
                await broadcast_state()
                continue

            if msg_type == "USER_SPEECH":
                if device_id != ACTIVE_DEVICE:
                    continue

                user_text = data.get("text", "").strip()
                print(f"[{device_id.upper()} Heard] 🎙️: \"{user_text}\"")

                lower_u = user_text.lower()
                if any(k in lower_u for k in ["pindah ke tablet", "teleport ke tablet", "ke tablet"]):
                    ACTIVE_DEVICE = "tablet"
                    await broadcast_state()
                    reply = "Aku teleport ke tablet sekarang ya!"
                    b64_audio = generate_voicevox_base64(reply)
                    if "tablet" in connected_clients:
                        await connected_clients["tablet"].send_json({
                            "type": "BOT_REPLY",
                            "text": reply,
                            "audio": b64_audio
                        })
                    continue

                if any(k in lower_u for k in ["pindah ke pc", "pindah ke laptop", "balik ke pc"]):
                    ACTIVE_DEVICE = "pc"
                    await broadcast_state()
                    reply = "Aku balik ke laptop sekarang!"
                    b64_audio = generate_voicevox_base64(reply)
                    if "pc" in connected_clients:
                        await connected_clients["pc"].send_json({
                            "type": "BOT_REPLY",
                            "text": reply,
                            "audio": b64_audio
                        })
                    continue

                prompt = f"""[ROLEPLAY: DISCORD WAIFU TUZI]
Kamu adalah Tuzi, waifu kelinci yang sedang diajak mengobrol di {device_id}.
Pengguna berkata: "{user_text}"
Balas langsung secara natural layaknya manusia berbicara tanpa emoji."""
                
                reply_text = ""
                for token in llm.stream_response(prompt):
                    reply_text += token
                reply_text = re.sub(r"\[.*?\]", "", reply_text).strip()
                print(f"[Tuzi Reply to {device_id.upper()}] 🤖: \"{reply_text}\"")

                b64_audio = generate_voicevox_base64(reply_text)

                await websocket.send_json({
                    "type": "BOT_REPLY",
                    "text": reply_text,
                    "audio": b64_audio
                })

    except WebSocketDisconnect:
        connected_clients.pop(device_id, None)
        print(f"[Device Disconnected] ❌ '{device_id.upper()}' terputus.")
        if ACTIVE_DEVICE == device_id and connected_clients:
            ACTIVE_DEVICE = list(connected_clients.keys())[0]
        await broadcast_state()

def run_server():
    print("="*60)
    print(f"🚀 Tuzi Live2D Dimension Hub Aktif!")
    print(f"👉 Di Laptop/PC buka:  http://localhost:8000?device=pc")
    print(f"👉 Di Tablet buka:     http://{LOCAL_IP}:8000?device=tablet")
    print("="*60)
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="warning")

if __name__ == "__main__":
    run_server()