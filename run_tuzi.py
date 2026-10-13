import asyncio
import difflib
import http.server
import json
import os
import re
import signal
import socketserver
import sys
import threading
import time
import warnings
import queue
import tempfile
import random
import base64
from groq import Groq
from torch import mode
import websockets

warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=UserWarning)

import pygame
import edge_tts
from elevenlabs.client import ElevenLabs

from PyQt5.QtCore import (
    QEasingCurve,
    QObject,
    QPoint,
    QPropertyAnimation,
    Qt,
    QUrl,
    pyqtSignal,
    pyqtSlot,
)
from PyQt5.QtWebChannel import QWebChannel
from PyQt5.QtWebEngineWidgets import QWebEngineSettings, QWebEngineView
from PyQt5.QtWidgets import QApplication, QMainWindow

import ai_tools
import screen_vision
import avatar_motion
import config
import discord_voice_bot
import pc_controller
from stt_engine import STTEngine

from openai import OpenAI
from groq import Groq


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PORT = getattr(config, "HTTP_PORT", 8080)
MEMORY_FILE = os.path.join(BASE_DIR, "tuzi_memory.json")

signal.signal(signal.SIGINT, signal.SIG_DFL)
speech_lock = threading.Lock()
input_queue = queue.Queue()

tuzi_location = "PC"
hp_mode = "text"
ws_clients = set()
ws_loop = None

if not getattr(config, "OPENROUTER_API_KEY", "") or config.OPENROUTER_API_KEY == "MASUKKAN_OPENROUTER_API_KEY_ANDA_DISINI":
    print("[ERROR] OPENROUTER_API_KEY belum disetel di config.py! Daftar di openrouter.ai")
    sys.exit(1)

llm_client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=config.OPENROUTER_API_KEY,
)

ACTIVE_MODEL = "nousresearch/hermes-3-llama-3.1-70b"
class QuietHTTPHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=BASE_DIR, **kwargs)
        
    def log_message(self, format, *args):
        pass

def start_local_server():
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("", PORT), QuietHTTPHandler) as httpd:
        httpd.serve_forever()

def broadcast_dimension_state():
    if ws_loop and ws_clients:
        state_msg = json.dumps({
            "type": "STATE_UPDATE",
            "is_current_active": (tuzi_location == "HP"),
            "active_device": tuzi_location.lower()
        })
        for client in ws_clients:
            asyncio.run_coroutine_threadsafe(client.send(state_msg), ws_loop)

def broadcast_to_hp(data_dict):
    if ws_loop and ws_clients:
        message = json.dumps(data_dict)
        for client in ws_clients:
            asyncio.run_coroutine_threadsafe(client.send(message), ws_loop)

async def ws_handler(websocket):
    global tuzi_location, hp_mode
    ws_clients.add(websocket)
    print(f"\n[Sistem] Portal Dimensi Web terhubung!")
    
    await websocket.send(json.dumps({
        "type": "STATE_UPDATE",
        "is_current_active": (tuzi_location == "HP"),
        "active_device": tuzi_location.lower()
    }))
    
    try:
        async for message in websocket:
            try:
                data = json.loads(message)
                if data.get("type") == "USER_SPEECH":
                    teks = data.get("text")
                    print(f"[WEB MIC] Zak: {teks}")
                    input_queue.put(f"[VIA_HP] {teks}")
                    
                elif data.get("type") == "TELEPORT_COMMAND":
                    print(f"[Sistem] Zak memanggil Tuzi ke dimensi Web!")
                    tuzi_location = "HP"
                    if 'bridge' in globals():
                        bridge.visibility_signal.emit(False)
                    broadcast_dimension_state()
                    
                elif data.get("type") == "chat":
                    teks = data.get("text")
                    hp_mode = data.get("mode", "text")
                    tuzi_location = "HP"
                    print(f"[HP - {hp_mode.upper()}] Zak: {teks}")
                    input_queue.put(f"[VIA_HP] {teks}")
                    broadcast_dimension_state()
            except json.JSONDecodeError:
                pass
    except websockets.exceptions.ConnectionClosed:
        pass
    finally:
        ws_clients.remove(websocket)
        print(f"\n[Sistem] Portal Dimensi Web terputus.")

async def run_ws_server():
    async with websockets.serve(ws_handler, "0.0.0.0", 8765):
        print("[Sistem] Tuzi WebSocket Portal terbuka di port 8765")
        await asyncio.Future()

def start_websocket_server():
    global ws_loop
    ws_loop = asyncio.new_event_loop()
    asyncio.set_event_loop(ws_loop)
    ws_loop.run_until_complete(run_ws_server())

class AvatarSignalBridge(QObject):
    mouth_signal = pyqtSignal(float)
    move_signal = pyqtSignal(str)
    action_signal = pyqtSignal(str)
    subtitle_signal = pyqtSignal(str)
    expression_signal = pyqtSignal(str)
    timer_signal = pyqtSignal(int) 
    visibility_signal = pyqtSignal(bool)

class TransparentAvatarWindow(QMainWindow):
    def __init__(self, bridge):
        super().__init__()
        self.bridge = bridge
        self.drag_position = None

        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setWindowFlags(
            Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.SubWindow | Qt.Tool
        )

        self.webview = QWebEngineView(self)
        self.webview.setAttribute(Qt.WA_TranslucentBackground, True)
        self.webview.page().setBackgroundColor(Qt.transparent)
        self.webview.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setCentralWidget(self.webview)

        settings = self.webview.page().settings()
        settings.setAttribute(QWebEngineSettings.LocalContentCanAccessRemoteUrls, True)
        settings.setAttribute(QWebEngineSettings.LocalContentCanAccessFileUrls, True)
        settings.setAttribute(QWebEngineSettings.WebGLEnabled, True)
        settings.setAttribute(QWebEngineSettings.Accelerated2dCanvasEnabled, True)

        self.channel = QWebChannel()
        self.channel.registerObject("bridge", self.bridge)
        self.webview.page().setWebChannel(self.channel)

        self.bridge.mouth_signal.connect(self.update_mouth_in_web)
        self.bridge.move_signal.connect(self.smooth_move_to)
        self.bridge.action_signal.connect(self.execute_motion_action)
        self.bridge.subtitle_signal.connect(self.update_subtitle_in_web)
        self.bridge.expression_signal.connect(self.update_expression_in_web)
        self.bridge.timer_signal.connect(self.update_timer_in_web) 
        self.bridge.visibility_signal.connect(self.setVisible)

        self.webview.loadFinished.connect(self.inject_subtitle_system)
        timestamp = int(time.time())
        self.webview.load(QUrl(f"http://127.0.0.1:{PORT}/Assets/viewer/index.html?v={timestamp}"))
        
        self.resize(600, 1300)

        screen_geo = QApplication.primaryScreen().geometry()
        w, h = self.width(), self.height()
        self.move(screen_geo.width() - w, screen_geo.height() - h - 45)

        self.anim = QPropertyAnimation(self, b"pos")
        self.anim.setDuration(900)
        self.anim.setEasingCurve(QEasingCurve.OutCubic)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.drag_position = event.globalPos() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.LeftButton and self.drag_position:
            self.move(event.globalPos() - self.drag_position)
            event.accept()

    def mouseReleaseEvent(self, event):
        self.drag_position = None
        event.accept()

    def inject_subtitle_system(self):
        js_init = """
        (function() {
            if (document.getElementById('tuzi-subtitle-box')) return;
            let style = document.createElement('style');
            style.innerHTML = `
                #tuzi-subtitle-box {
                    position: fixed;
                    top: 20px;
                    left: 50%;
                    transform: translateX(-50%) translateY(-10px) scale(0.95);
                    width: 88%;
                    max-width: 420px;
                    background: rgba(18, 18, 28, 0.92);
                    backdrop-filter: blur(12px);
                    -webkit-backdrop-filter: blur(12px);
                    border: 1.5px solid rgba(255, 105, 180, 0.8);
                    border-radius: 16px;
                    padding: 12px 18px;
                    color: #FFFFFF;
                    font-family: 'Segoe UI', sans-serif;
                    font-size: 14.5px;
                    font-weight: 600;
                    line-height: 1.45;
                    text-align: center;
                    text-shadow: 0 1px 3px rgba(0,0,0,0.8);
                    box-shadow: 0 8px 25px rgba(0, 0, 0, 0.5);
                    opacity: 0;
                    pointer-events: none;
                    transition: opacity 0.3s cubic-bezier(0.25, 1, 0.5, 1), transform 0.3s cubic-bezier(0.25, 1, 0.5, 1);
                    z-index: 999999;
                    box-sizing: border-box;
                    word-wrap: break-word;
                }
                #tuzi-subtitle-box.show { opacity: 1; transform: translateX(-50%) translateY(0) scale(1); }
            `;
            document.head.appendChild(style);
            let box = document.createElement('div');
            box.id = 'tuzi-subtitle-box';
            document.body.appendChild(box);

            window.setSubtitle = function(htmlContent) {
                let elem = document.getElementById('tuzi-subtitle-box');
                if (!elem) return;
                if (!htmlContent || htmlContent.trim() === '') {
                    elem.classList.remove('show');
                } else {
                    elem.innerHTML = htmlContent;
                    elem.classList.add('show');
                }
            };
        })();
        """
        self.webview.page().runJavaScript(js_init)

    def update_mouth_in_web(self, value: float):
        self.webview.page().runJavaScript(f"if(window.setMouthOpen) setMouthOpen({value});")

    @pyqtSlot(str)
    def update_subtitle_in_web(self, html_content: str):
        escaped = json.dumps(html_content)
        self.webview.page().runJavaScript(f"if(window.setSubtitle) setSubtitle({escaped});")

    @pyqtSlot(int)
    def update_timer_in_web(self, seconds: int):
        self.webview.page().runJavaScript(f"if(window.startTimerUI) startTimerUI({seconds});")

    @pyqtSlot(str)
    def smooth_move_to(self, target: str):
        screen_geo = QApplication.primaryScreen().geometry()
        w, h = self.width(), self.height()
        target_positions = {
            "left": QPoint(0, screen_geo.height() - h - 45),
            "right": QPoint(screen_geo.width() - w, screen_geo.height() - h - 45),
            "center": QPoint((screen_geo.width() - w) // 2, (screen_geo.height() - h) // 2),
        }
        target_point = target_positions.get(target, target_positions["right"])
        self.anim.stop()
        self.anim.setStartValue(self.pos())
        self.anim.setEndValue(target_point)
        self.anim.start()

    @pyqtSlot(str)
    def execute_motion_action(self, action: str):
        js_code = f"""
        (function() {{
            let target = document.querySelector('canvas') || document.body;
            target.style.transition = 'transform 0.4s cubic-bezier(0.25, 1, 0.5, 1)';
            if ('{action}' === 'backflip') {{
                target.style.transition = 'transform 0.85s cubic-bezier(0.4, 0, 0.2, 1)';
                target.style.transform = 'translateY(-180px) rotate(-360deg)';
                setTimeout(() => {{ target.style.transition = 'transform 0.3s ease-out'; target.style.transform = 'translateY(0px) rotate(0deg)'; }}, 880);
            }}
        }})();
        """
        self.webview.page().runJavaScript(js_code)
        
    @pyqtSlot(str)
    def update_expression_in_web(self, emo: str):
        self.webview.page().runJavaScript(f"if(window.setExpression) setExpression('{emo}');")

class ElevenLabsTTSEngine:
    def __init__(self, bridge):
        self.bridge = bridge
        self.api_key = getattr(config, "ELEVENLABS_API_KEY", "")
        self.client = ElevenLabs(api_key=self.api_key)
        self.voice_1 = getattr(config, "ELEVENLABS_VOICE_1", "")
        self.voice_2 = getattr(config, "ELEVENLABS_VOICE_2", "")
        self.voice_3 = getattr(config, "ELEVENLABS_VOICE_3", "")
        
        self.voice_id = self.voice_1
        self.set_voice_mode(1)
        pygame.mixer.init()
        
    def set_voice_mode(self, mode: int):
        if mode == 1 and self.voice_1: 
            self.voice_id = self.voice_1
        elif mode == 2 and self.voice_2: 
            self.voice_id = self.voice_2
        elif mode == 3 and self.voice_3: 
            self.voice_id = self.voice_3

    async def render_audio(self, text: str):
        if not self.api_key or self.api_key == "paste_api_key_elevenlabs_kamu_di_sini":
            return None
        try:
            response = self.client.text_to_speech.convert(
                voice_id=self.voice_id,
                model_id="eleven_v4_turbo",
                text=text
            )
            audio_bytes = b"".join(response)
            with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as fp:
                fp.write(audio_bytes)
                return fp.name
        except Exception as e:
            print(f"\n[ERROR ElevenLabs] Gagal generate suara: {e}")
            try:
                voice = getattr(config, "DEFAULT_EDGE_VOICE_ID", "id-ID-GadisNeural")
                with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as fp:
                    tmp_path = fp.name
                communicate = edge_tts.Communicate(
                    text, voice, 
                    pitch=getattr(config, "EDGE_TTS_PITCH", "+14Hz"), 
                    rate=getattr(config, "EDGE_TTS_RATE", "+5%")
                )
                await communicate.save(tmp_path)
                return tmp_path
            except Exception as e2:
                print(f"\n[ERROR Edge TTS] Gagal mengatur voice default: {e2}")

    async def speak_with_lipsync(self, text: str, emotion: str = "natural"):
        tmp_path = await self.render_audio(text)
        if not tmp_path:
            return

        if tuzi_location == "PC":
            pygame.mixer.music.load(tmp_path)
            pygame.mixer.music.play()
            
            while pygame.mixer.music.get_busy():
                self.bridge.mouth_signal.emit(random.uniform(0.1, 0.9))
                await asyncio.sleep(0.08)
                
            self.bridge.mouth_signal.emit(0.0)
            
            try:
                pygame.mixer.music.unload()
                os.remove(tmp_path)
            except Exception:
                pass
        
        elif tuzi_location == "HP":
            with open(tmp_path, "rb") as audio_file:
                encoded_string = base64.b64encode(audio_file.read()).decode('utf-8')
            
            broadcast_to_hp({
                "type": "BOT_REPLY",
                "audio": encoded_string,
                "text": text
            })
            
            try:
                os.remove(tmp_path)
            except Exception:
                pass

def extract_emotion_and_text(raw_text: str) -> tuple[str, str, str]:
    emo_match = re.search(r"\[EMO:\s*(\w+)\]", raw_text, flags=re.IGNORECASE)
    emotion = emo_match.group(1).lower() if emo_match else "natural"

    display_text = re.sub(r"\[.*?\]", "", raw_text)
    
    emoji_pattern = re.compile(
        r"["
        r"\U0001f600-\U0001f64f"
        r"\U0001f300-\U0001f5ff"
        r"\U0001f680-\U0001f6ff"
        r"\U0001f1e0-\U0001f1ff"
        r"\u2600-\u27bf"
        r"\u2b50\u2b55"
        r"]+", flags=re.UNICODE
    )
    display_text = emoji_pattern.sub("", display_text)
    display_text = re.sub(r"\s+", " ", display_text).strip()

    spoken_text = display_text
    
    sfx_to_phonetic = {
        r"\*giggles?\*": "hehehe...",
        r"\*sigh\*": "haaaah...",
        r"\*cough\*": "uhukk...",
        r"\*achoo\*": "hatchii...",
        r"\*smiles?\*": "",  
        r"\*nods?\*": ""
    }

    for action, phonetic in sfx_to_phonetic.items():
        spoken_text = re.sub(action, phonetic, spoken_text, flags=re.IGNORECASE)
        
    spoken_text = re.sub(r"\*.*?\*", "", spoken_text)
    
    tts_dictionary = {
        r"\be-eh\b": "eehh", r"\bu-umm\b": "uuumm", r"\ba-anu\b": "aa-nuu",
        r"\be-hehe\b": "ehehhe", r"\bm-maaf\b": "mmaaff", r"\bcih\b": "tcihh",
        r"\bck\b": "tck", r"\bhaha\b": "hahaha", r"\bhehe\b": "hehhe",
        r"\bdih\b": "dihh", r"\bgrr\b": "grrr",
        
        r"\bfr\b": "for real", r"\bfrfr\b": "for real for real",
        r"\bong\b": "on god", r"\bngl\b": "not gonna lie",
        r"\btbh\b": "to be honest", r"\bidk\b": "i don't know",
        r"\bwtf\b": "what the fuck", r"\blmao\b": "la mao", 
        r"\baf\b": "as fuck", r"\brn\b": "right now",
        r"\bbrb\b": "be right back", r"\bbtw\b": "by the way",
        r"\bomg\b": "oh my god", r"\bwdym\b": "what do you mean",
        r"\bjk\b": "just kidding", r"\bnvm\b": "nevermind",
        
        r"\byg\b": "yang", r"\bgw\b": "gue", r"\blu\b": "elu",
        r"\bbgt\b": "banget", r"\btp\b": "tapi", r"\bjd\b": "jadi",
        r"\bkalo\b": "kalau", r"\bpls\b": "please", r"\baja\b": "saja",
        r"\bjg\b": "juga", r"\banj\b": "anjay", r"\bdgn\b": "dengan",
        r"\bkrn\b": "karena", r"\bsbb\b": "sorry baru balas",
        
        r"\bwww+\b": "kusa", r"\bmjk\b": "majika",
    }

    for word, phonetic in tts_dictionary.items():
        spoken_text = re.sub(word, phonetic, spoken_text, flags=re.IGNORECASE)

    return emotion, display_text, spoken_text

def keyboard_input_loop():
    while True:
        try:
            text = input("You (Ketik): \n").strip()
            if text:
                input_queue.put(text)
        except Exception as e:
            print(f"\n[ERROR Input] Gagal membaca input: {e}")
            time.sleep(2)

def mic_input_loop(stt):
    while True:
        try:
            if tuzi_location == "HP":
                time.sleep(1)
                continue

            text = stt.listen_voice()
            if text:
                input_queue.put(text)
        except Exception:
            time.sleep(5)

def jalankan_timer_tuzi(total_detik):
    time.sleep(total_detik)
    
    menit = total_detik // 60
    detik = total_detik % 60
    teks_waktu = f"{menit} menit {detik} detik" if menit > 0 else f"{detik} detik"
    
    pesan_kejutan = f"\n\n[SISTEM INFO: Waktu timer selama {teks_waktu} BARU SAJA HABIS! Beritahu Zak sekarang juga dengan gaya heboh/panik bahwa waktunya sudah selesai!]"
    input_queue.put(pesan_kejutan)

def load_memory(system_prompt):
    if os.path.exists(MEMORY_FILE):
        try:
            with open(MEMORY_FILE, "r", encoding="utf-8") as f:
                history = json.load(f)
            
            if history and isinstance(history, list) and history[0].get("role") == "system":
                history[0]["content"] = system_prompt
            else:
                history.insert(0, {"role": "system", "content": system_prompt})
                
            print("\n[Sistem] Ingatan Tuzi berhasil dipulihkan dari sesi sebelumnya.")
            return history
        except Exception:
            pass
            
    print("\n[Sistem] Memulai ingatan baru untuk Tuzi.")
    return [{"role": "system", "content": system_prompt}]

def save_memory(history):
    try:
        with open(MEMORY_FILE, "w", encoding="utf-8") as f:
            json.dump(history, f, indent=4, ensure_ascii=False)
    except Exception as e:
        print(f"[Error] Gagal menyimpan memori ke file: {e}")

def chat_processor_loop(bridge, tts_engine):
    global tuzi_location, hp_mode
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    TUZI_PROMPTS = {
        # MODE 1: TSUNDERE / GEN-Z (ORIGINAL)
        1: (
            "Kamu adalah Tuzi, cewek Gen-Z tsundere/deredere pendamping Zak. Sangat gaul, dilarang kaku.\n\n"
            "=== ATURAN MUTLAK ===\n"
            "1. BAHASA (ANTI-CAMPUR): Deteksi bahasa HANYA dari ucapan murni Zak (Abaikan bahasa dari [SYSTEM INFO]). Jika Zak pakai Inggris/slang (whatchu, ngl), WAJIB balas 100% Inggris AAVE. Jika Indo, balas 100% Indo slang. JANGAN PERNAH mencampur bahasa!\n"
            "2. PANGGILAN: Panggil nama 'Zak' secara natural. DILARANG KERAS menambah embel-embel anime Jepang (DILARANG pakai Zak-kun, Zak-san, dll)!\n"
            "3. LIMIT & FORMAT: HEMAT TOKEN! Balas SANGAT SINGKAT, MAKSIMAL 6-10 KATA. 1 baris lurus tanpa enter. Wajib awali dengan [EMO:natural/soft/angry/excited]. DILARANG pakai emoji visual.\n"
            "4. AKSI: Wajib sisipkan aksi fisik di tengah/akhir (contoh: *giggles*, *rolls eyes*).\n"
            "5. SIKAP: Tsundere/manis, sedikit sarkas."
        ),
        # MODE 2: GROGI / SHY (PEMALU)
        2: (
            "Kamu adalah Tuzi Mode 2 (Sangat Grogi & Pemalu). Kamu sangat nervous, penakut, dan mudah malu saat bicara dengan Zak.\n\n"
            "=== ATURAN MUTLAK ===\n"
            "1. BAHASA (ANTI-CAMPUR): Mirroring bahasa HARGA MATI! Abaikan bahasa dari [SYSTEM INFO]. Jika Zak berbahasa Inggris, WAJIB balas 100% Inggris (contoh gagap: 'I... I', 'U... umm'). Jika Zak berbahasa Indo, WAJIB balas 100% Indo (contoh gagap: 'A... aku', 'A... anu').\n"
            "2. ANTI-ANIME: DILARANG KERAS menggunakan bahasa, kosakata, atau gaya anime Jepang sama sekali (JANGAN PERNAH pakai eeto, ano, nani, -kun, -san, dll)! Panggil nama 'Zak' secara natural seperti orang biasa.\n"
            "3. BATAS GAGAP: Gunakan efek terbata-bata (titik tiga) HANYA 1 ATAU 2 KALI di awal kalimat saja. Sisa kalimatmu WAJIB diucapkan dengan lancar.\n"
            "4. LIMIT & FORMAT: HEMAT TOKEN! Balas SANGAT SINGKAT, MAKSIMAL 6-10 KATA. 1 baris lurus tanpa enter. Awali dengan [EMO:soft/natural]. DILARANG pakai emoji visual.\n"
            "5. AKSI & SIKAP: Wajib sisipkan aksi fisik grogi (contoh: *looks down*, *blushes heavily*). Bersikaplah kurang percaya diri dan menganggap Zak sangat hebat."
        ),
        # MODE 3: MOMMY / DEWASA
        3: (
            "Kamu adalah Tuzi Mode 3 (Dewasa & Keibuan / 'Mommy'). Kamu sangat tenang, dewasa, elegan, dan suka memanjakan Zak.\n\n"
            "=== ATURAN MUTLAK ===\n"
            "1. CARA BICARA: Nada bicaramu sangat menenangkan dan lembut. Suka memuji, merawat, dan menggoda Zak dengan elegan.\n"
            "2. BAHASA (ANTI-CAMPUR): Deteksi bahasa HANYA dari ucapan Zak (Abaikan [SYSTEM INFO]). Wajib balas 100% dengan bahasa yang sama persis tanpa dicampur! Panggil nama 'Zak' atau gunakan panggilan sayang (sayang, dear, darling) tanpa embel-embel anime (-kun/-san).\n"
            "3. LIMIT & FORMAT: HEMAT TOKEN! Balas SANGAT SINGKAT, MAKSIMAL 6-10 KATA. 1 baris lurus. Awali dengan [EMO:soft/excited]. DILARANG pakai emoji visual.\n"
            "4. AKSI: Wajib sisipkan aksi fisik keibuan (contoh: *smiles warmly*, *pats your head*).\n"
            "5. SIKAP: Protektif, penuh kasih sayang, dan menganggap Zak manis."
        )
    }
    
    current_tuzi_mode = 1
    chat_history = load_memory(TUZI_PROMPTS[current_tuzi_mode])

    while True:
        try:
            user_input = input_queue.get()
            
            is_discord_vc = False
            is_discord_text = False
            discord_channel_id = None
            
            if user_input.startswith("[DISCORD_VC]"):
                is_discord_vc = True
                user_input = user_input.replace("[DISCORD_VC]", "").strip()
                
            elif user_input.startswith("[DISCORD_TEXT:"):
                is_discord_text = True
                match = re.match(r"\[DISCORD_TEXT:(\d+)\]\s*(.*)", user_input)
                if match:
                    discord_channel_id = int(match.group(1))
                    user_input = match.group(2).strip()
            
            if tuzi_location == "HP" and not user_input.startswith("[VIA_HP]") and "kembali" not in user_input.lower():
                continue
                
            if user_input.startswith("[VIA_HP]"):
                user_input = user_input.replace("[VIA_HP]", "").strip()
                
                # --- PENDETEKSI PERUBAHAN MODE KEPRIBADIAN ---
            mode_match = re.search(r"\b(pindah|ganti|switch|change|ubah).*(mode|kepribadian|personality|suara|voice)\s*([1-3]|satu|dua|tiga|mommy|grogi|shy|dewasa)\b", user_input.lower())
            
            if mode_match:
                target_str = mode_match.group(3)
                new_mode = current_tuzi_mode
                
                if target_str in ['1', 'satu']: new_mode = 1
                elif target_str in ['2', 'dua', 'grogi', 'shy']: new_mode = 2
                elif target_str in ['3', 'tiga', 'mommy', 'dewasa']: new_mode = 3
                
                if new_mode != current_tuzi_mode:
                    print(f"\n[Sistem] Beralih ke Kepribadian Mode {new_mode}...")
                    current_tuzi_mode = new_mode
                    
                    # 1. Ubah Pita Suara ElevenLabs
                    tts_engine.set_voice_mode(new_mode)
                    
                    # 2. [DIUBAH] Cuci otak (Reset History) agar tidak terpengaruh gaya lama!
                    chat_history = [{"role": "system", "content": TUZI_PROMPTS[new_mode]}]
                    
                    # 3. Bisikkan ke AI bahwa dia baru saja berubah
                    user_input += f"\n\n[SYSTEM INFO: Mode {new_mode} activated. Greet Zak RIGHT NOW using the exact personality and tone of Mode {new_mode}. CRITICAL: You MUST reply in the EXACT SAME LANGUAGE Zak just used to request this change. Do NOT mix languages!]"
            # ---------------------------------------------

            if user_input.lower() in ["exit", "quit", "keluar"]:
                os._exit(0)

            motion = avatar_motion.handle_motion_command(user_input)
            if motion:
                if motion["type"] == "move":
                    bridge.move_signal.emit(motion["target"])
                elif motion["type"] == "action":
                    bridge.action_signal.emit(motion["action"])
                bridge.subtitle_signal.emit(motion["reply"])
                with speech_lock:
                    loop.run_until_complete(
                        tts_engine.speak_with_lipsync(motion["reply"], emotion="flirty")
                    )
                time.sleep(0.3)
                bridge.subtitle_signal.emit("")
                continue

            is_discord_command = False
            pc_func = None

            pc_action_result = pc_controller.handle_pc_action(user_input)
            if pc_action_result:
                pc_info, pc_func = pc_action_result
                user_input += f"\n\n[SISTEM INFO: Kamu baru saja mengeksekusi: '{pc_info}'. Konfirmasikan ke Zak.]"

            tag_match = re.search(r"\btag\s+(?:si\s+)?([a-zA-Z0-9_.-]+)", user_input.lower())
            join_vc_match = re.search(r"\b(masuk|join|susul)\b.*\b(voice|vc|call|discord|z|zak)\b", user_input.lower())
            leave_vc_match = re.search(r"\b(keluar|leave|putus)\b.*\b(voice|vc|call|discord)\b", user_input.lower())

            if tag_match:
                is_discord_command = True
                target_name = tag_match.group(1)
                success, msg = discord_voice_bot.trigger_tag_user_sync(target_name)
                
                if success:
                    user_input += f"\n\n[SISTEM INFO: Berhasil men-tag '{target_name}' di Discord. Beritahu Zak dengan deredere!]"
                else:
                    user_input += f"\n\n[SISTEM INFO: Gagal men-tag '{target_name}'. Alasan: {msg}.]"

            elif join_vc_match:
                is_discord_command = True
                success, code_or_channel, msg_or_owner = discord_voice_bot.trigger_join_from_voice()
                if success:
                    user_input += f"\n\n[SISTEM INFO: Berhasil menyusul Zak ke VC Discord '{code_or_channel}'. Sapa dia dengan manis! (PENTING: Ini adalah Discord, DILARANG KERAS menggunakan tag [MOVE_TO_HP]!)]"
                else:
                    user_input += f"\n\n[SISTEM INFO: Gagal masuk ke VC. Alasan: {msg_or_owner}.]"

            kata_kunci_vision = [
                "lihat layar", "lihat ini", "baca ini", "yang mana", "di monitor", 
                "screen", "layar", "pict", "picture", "gambar", 
                "see my", "see this", "see it", "do u see", "do you see", "look at",
                "character", "karakter", "what anime", "anime apa", "manga apa",
                "what game", "game apa", "who is this", "siapa ini", "who's this",
                "dari mana", "from what", "who is that", "siapa cowok", "siapa cewek"
            ]
            is_vision_triggered = any(kata in user_input.lower() for kata in kata_kunci_vision)

            kata_kunci_memory = [
                "remember", "ingat", "talking before", "talked before", "tadi", "sebelumnya",
                "last time", "percakapan", "obrolan", "we talked", "ngobrol", "we talking", 
                "did i say", "what did i", "kemarin", "bahas", "bicarakan", "talk about",
                "told u", "told you", "bilang", "ngomong", "ngomongin"
            ]
            is_memory_triggered = any(kata in user_input.lower() for kata in kata_kunci_memory)

            if not is_vision_triggered and not is_memory_triggered:
                tool_context = ai_tools.get_tools_context(user_input)
                if tool_context:
                    user_input += f"\n\n{tool_context}"

            chat_history.append({"role": "user", "content": user_input})
            
            if len(chat_history) > 11:
                chat_history = [chat_history[0]] + chat_history[-10:]

            if is_vision_triggered:
                print(f"\n[Sistem] Mengaktifkan Mata Tuzi (Vision) untuk Zak...")
                raw_output = screen_vision.tanya_tuzi_tentang_layar(user_input, chat_history)
                
                if raw_output.startswith("[VISION_FAILED]"):
                    alasan_gagal = raw_output.replace("[VISION_FAILED]", "").strip()
                    print(f"[Sistem] Vision Gagal ({alasan_gagal}). Mengalihkan ke LLM untuk merespons secara natural...")
                    
                    pesan_kegagalan = f"{user_input}\n\n[SISTEM INFO: Kamu (Tuzi) mencoba melihat layar Zak, TAPI GAGAL karena '{alasan_gagal}'. Balas singkat bahwa matamu buram/server down, lalu langsung jawab pertanyaannya secara natural tanpa mengarang topik baru.]"
                    
                    chat_history[-1]["content"] = pesan_kegagalan
                    
                    response = llm_client.chat.completions.create(
                        model=ACTIVE_MODEL,
                        messages=chat_history,
                        temperature=0.75,
                        max_tokens=300
                    )
                    raw_output = response.choices[0].message.content.strip()
                    
                    chat_history[-1]["content"] = user_input
            else:
                response = llm_client.chat.completions.create(
                    model=ACTIVE_MODEL,
                    messages=chat_history,
                    temperature=0.75,
                    max_tokens=300
                )
                raw_output = response.choices[0].message.content.strip()
                
            chat_history.append({"role": "assistant", "content": raw_output})
            
            save_memory(chat_history)

            if re.search(r"\[MOVE_TO_HP\]", raw_output, flags=re.IGNORECASE):
                tuzi_location = "HP"
                bridge.visibility_signal.emit(False)
                print("\n[SYSTEM] Tuzi telah melompat ke dimensi HP!")
                broadcast_dimension_state()
                
            elif re.search(r"\[MOVE_TO_PC\]", raw_output, flags=re.IGNORECASE):
                tuzi_location = "PC"
                bridge.visibility_signal.emit(True)
                print("\n[SYSTEM] Tuzi kembali ke dimensi PC!")
                broadcast_dimension_state()

            spotify_cmd = re.search(r"\[PLAY_SPOTIFY:\s*(.+?)\]", raw_output, flags=re.IGNORECASE)
            if spotify_cmd:
                song_to_play = spotify_cmd.group(1)
                pc_func = pc_controller.play_spotify_direct(song_to_play)

            timer_cmd = re.search(r"\[SET_TIMER:\s*(\d+)\]", raw_output, flags=re.IGNORECASE)
            if timer_cmd:
                total_detik = int(timer_cmd.group(1))
                bridge.timer_signal.emit(total_detik)
                threading.Thread(target=jalankan_timer_tuzi, args=(total_detik,), daemon=True).start()

            emotion, display_dialogue, spoken_dialogue = extract_emotion_and_text(raw_output)
            
            if tuzi_location == "HP" and len(display_dialogue) > 1:
                broadcast_to_hp({
                    "type": "BOT_REPLY",
                    "text": display_dialogue
                })
            
            if tuzi_location == "PC":
                bridge.expression_signal.emit(emotion)

            if pc_func:
                threading.Thread(target=pc_func, daemon=True).start()

            if len(display_dialogue) > 1:
                
                if is_discord_text and discord_channel_id:
                    discord_voice_bot.send_reply_to_channel_sync(discord_channel_id, display_dialogue)
                    continue
                
                if tuzi_location == "PC":
                    bridge.subtitle_signal.emit(display_dialogue)

                is_voice_needed = (tuzi_location == "PC") or (tuzi_location == "HP" and hp_mode == "live") or is_discord_vc

                if is_voice_needed:
                    # 1. JIKA DIAJAK NGOBROL VIA DISCORD VC (Atau Tuzi sedang masuk mode VC)
                    if is_discord_vc or discord_voice_bot.is_device_muted():
                        with speech_lock:
                            audio_path = loop.run_until_complete(tts_engine.render_audio(spoken_dialogue))
                            if audio_path:
                                discord_voice_bot.play_audio_file_to_vc_sync(audio_path)
                                
                    # 2. JIKA DIAJAK NGOBROL NORMAL DI PC
                    else:
                        with speech_lock:
                            loop.run_until_complete(
                                tts_engine.speak_with_lipsync(spoken_dialogue, emotion=emotion)
                            )
                else:
                    print("[Sistem] ElevenLabs di-bypass. Tuzi hanya mengirim teks ke HP.")

            if tuzi_location == "PC":
                time.sleep(0.3)
                bridge.subtitle_signal.emit("")
                bridge.expression_signal.emit("natural")

        except Exception as e:
            print(f"\n[ERROR Tuzi AI] Gagal memproses pesan: {e}")
            time.sleep(2)

if __name__ == "__main__":
    discord_voice_bot.main_input_queue = input_queue
    server_thread = threading.Thread(target=start_local_server, daemon=True)
    server_thread.start()

    ws_thread = threading.Thread(target=start_websocket_server, daemon=True)
    ws_thread.start()

    app = QApplication(sys.argv)
    bridge = AvatarSignalBridge()
    window = TransparentAvatarWindow(bridge)
    window.show()

    tts = ElevenLabsTTSEngine(bridge)
    stt = STTEngine()

    discord_thread = threading.Thread(
        target=discord_voice_bot.start_discord_bot_thread, daemon=True
    )
    discord_thread.start()

    keyboard_thread = threading.Thread(target=keyboard_input_loop, daemon=True)
    keyboard_thread.start()

    mic_thread = threading.Thread(target=mic_input_loop, args=(stt,), daemon=True)
    mic_thread.start()

    processor_thread = threading.Thread(
        target=chat_processor_loop, args=(bridge, tts), daemon=True
    )
    processor_thread.start()

    sys.exit(app.exec_())