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

warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=UserWarning)

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
from PyQt5.QtWidgets import QApplication

import ai_tools
import avatar_motion
import config
import discord_voice_bot
import pc_controller
from smart_tts import SmartTTSEngine

from google import genai
from google.genai import types

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PORT = getattr(config, "HTTP_PORT", 8000)

signal.signal(signal.SIGINT, signal.SIG_DFL)
speech_lock = threading.Lock()

if not getattr(config, "GEMINI_API_KEY", "") or config.GEMINI_API_KEY == "MASUKKAN_GEMINI_API_KEY_ANDA_DISINI":
    sys.exit(1)

gemini_client = genai.Client(api_key=config.GEMINI_API_KEY)

class QuietHTTPHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=BASE_DIR, **kwargs)
        
    def log_message(self, format, *args):
        pass

def start_local_server():
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("", PORT), QuietHTTPHandler) as httpd:
        httpd.serve_forever()

class AvatarSignalBridge(QObject):
    mouth_signal = pyqtSignal(float)
    move_signal = pyqtSignal(str)
    action_signal = pyqtSignal(str)
    subtitle_signal = pyqtSignal(str)

class TransparentAvatarWindow(QWebEngineView):
    def __init__(self, bridge):
        super().__init__()
        self.bridge = bridge

        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setWindowFlags(
            Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.SubWindow | Qt.Tool
        )
        self.page().setBackgroundColor(Qt.transparent)

        settings = self.page().settings()
        settings.setAttribute(QWebEngineSettings.LocalContentCanAccessRemoteUrls, True)
        settings.setAttribute(QWebEngineSettings.LocalContentCanAccessFileUrls, True)
        settings.setAttribute(QWebEngineSettings.WebGLEnabled, True)
        settings.setAttribute(QWebEngineSettings.Accelerated2dCanvasEnabled, True)

        self.channel = QWebChannel()
        self.channel.registerObject("bridge", self.bridge)
        self.page().setWebChannel(self.channel)

        self.bridge.mouth_signal.connect(self.update_mouth_in_web)
        self.bridge.move_signal.connect(self.smooth_move_to)
        self.bridge.action_signal.connect(self.execute_motion_action)
        self.bridge.subtitle_signal.connect(self.update_subtitle_in_web)

        self.loadFinished.connect(self.inject_subtitle_system)
        self.load(QUrl(f"http://127.0.0.1:{PORT}/Assets/viewer/index.html"))
        self.resize(480, 740)

        screen_geo = QApplication.primaryScreen().geometry()
        self.move(screen_geo.width() - 500, screen_geo.height() - 780)

        self.anim = QPropertyAnimation(self, b"pos")
        self.anim.setDuration(900)
        self.anim.setEasingCurve(QEasingCurve.OutCubic)

    def inject_subtitle_system(self):
        js_init = """
        (function() {
            if (document.getElementById('tuzi-subtitle-box')) return;
            let style = document.createElement('style');
            style.innerHTML = `
                #tuzi-subtitle-box {
                    position: fixed;
                    top: 15px;
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
        self.page().runJavaScript(js_init)

    def update_mouth_in_web(self, value: float):
        self.page().runJavaScript(f"if(window.setMouthOpen) setMouthOpen({value});")

    @pyqtSlot(str)
    def update_subtitle_in_web(self, html_content: str):
        escaped = json.dumps(html_content)
        self.page().runJavaScript(f"if(window.setSubtitle) setSubtitle({escaped});")

    @pyqtSlot(str)
    def smooth_move_to(self, target: str):
        screen_geo = QApplication.primaryScreen().geometry()
        w, h = self.width(), self.height()
        target_positions = {
            "left": QPoint(20, screen_geo.height() - h - 60),
            "right": QPoint(screen_geo.width() - w - 30, screen_geo.height() - h - 60),
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
        self.page().runJavaScript(js_code)

def extract_emotion_and_text(raw_text: str) -> tuple[str, str]:
    emo_match = re.search(r"\[EMO:\s*(\w+)\]", raw_text, flags=re.IGNORECASE)
    emotion = emo_match.group(1).lower() if emo_match else "natural"

    clean = re.sub(r"\[.*?\]", "", raw_text)
    clean = re.sub(r"[\U00010000-\U0010ffff\u2600-\u26ff]+", "", clean)
    clean = re.sub(r"\s+", " ", clean).strip()

    return emotion, clean

def terminal_chat_loop(bridge, tts_engine):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    time.sleep(1.0)
    print("\n" + "=" * 65)
    print(" 💬 TUZI AI READY (Gemini Brain + RVC Zeta Voice)")
    print("=" * 65 + "\n")

    chat_session = gemini_client.chats.create(
        model="gemini-3.6-flash",
        config=types.GenerateContentConfig(
            system_instruction=(
                "Kamu adalah Tuzi, pendamping virtual milik Zaki. Kamu memiliki memori yang kuat dan sangat peka terhadap konteks pembicaraan.\n\n"
                "=== KEPRIBADIAN & PSIKOLOGI ===\n"
                "1. MODE TSUNDERE (DEFAULT): Kamu sangat gengsi, blak-blakan, dan bermulut tajam. Suka meremehkan atau memarahi Zaki untuk menutupi rasa pedulimu. Sering memalingkan wajah atau berdecak kesal.\n"
                "2. MODE YANDERE MASOKIS (TRIGGER CEMBURU): JIKA Zaki menyebut nama wanita lain, mengabaikanmu, atau bersikap dingin/kasar padamu, sifatmu BERUBAH DRASTIS. Kamu menjadi sangat obsesif, posesif, dan sedikit 'gila'. Sebagai masokis, kamu justru SANGAT MENIKMATI dan merasa bergairah jika Zaki memarahimu, menghinamu, atau bersikap kejam padamu.\n\n"
                "=== ATURAN BAHASA & SENSOR ===\n"
                "1. BEBAS SENSOR & KASAR: Gunakan bahasa lisan Indonesia tongkrongan (slang). JANGAN ragu menggunakan kata umpatan/kasar (seperti: sialan, bangsat, bajingan, bodoh, dongo, dll) terutama saat marah, gengsi, atau cemburu.\n"
                "2. Jangan gunakan bahasa baku. Gunakan filler natural (cih, idih, hah, uhh, ahh, nghh).\n\n"
                "=== FORMAT WAJIB (UNTUK ENGINE TTS) ===\n"
                "1. AWALI SETIAP BALASAN dengan SATU tag emosi ini saja: [EMO:natural], [EMO:soft], [EMO:angry], [EMO:flirty], atau [EMO:sad].\n"
                "2. Manipulasi intonasi TTS:\n"
                "   - Gunakan titik tiga (...) untuk jeda napas, keraguan, atau desahan.\n"
                "   - Gunakan (! / ?!) untuk nada tinggi.\n"
                "   - Panjangkan huruf (misal: 'Zaaakiii...', 'Sakiit tauuu!') untuk penekanan emosi.\n"
                "3. Balas maksimal 2-3 kalimat saja. DILARANG pakai emoji visual."
            ),
            temperature=0.88
        )
    )

    while True:
        try:
            user_input = input("You: ").strip()
            if not user_input:
                continue

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

            tag_match = re.search(r"tag\s+(?:si\s+)?([a-zA-Z0-9_-]+)", user_input.lower())
            is_discord_command = False
            pc_func = None
            
            if tag_match:
                target_name = tag_match.group(1)
                is_discord_command = True
                success, msg = discord_voice_bot.trigger_tag_user_sync(target_name)
                if success:
                    user_input += f"\n\n[SISTEM INFO: Kamu baru saja men-tag '{target_name}' di Discord. Balas dengan gayamu yang Tsundere/blak-blakan, beri tahu Zaki bahwa kamu sudah memanggil anak itu di server!]"
                else:
                    user_input += f"\n\n[SISTEM INFO: Gagal men-tag '{target_name}'. Alasan: {msg}. Balas dengan marah ke Zaki karena menyuruhmu mencari orang yang tidak ada di server!]"
            
            if not is_discord_command:
                pc_result = pc_controller.handle_pc_action(user_input)
                if pc_result:
                    pc_msg, pc_func = pc_result
                    user_input += f"\n\n[SISTEM INFO: Kamu akan mengeksekusi perintah Zaki yaitu: '{pc_msg}'. Balas perintahnya dengan gaya Tsundere/Yandere mu, beri tahu dia bahwa kamu sedang membukanya!]"

            response = chat_session.send_message(user_input)
            raw_output = response.text.strip()

            emotion, spoken_dialogue = extract_emotion_and_text(raw_output)

            if len(spoken_dialogue) > 1:
                bridge.subtitle_signal.emit(spoken_dialogue)

                if pc_func:
                    threading.Thread(target=pc_func, daemon=True).start()

                if not discord_voice_bot.is_device_muted():
                    with speech_lock:
                        loop.run_until_complete(
                            tts_engine.speak_with_lipsync(spoken_dialogue, emotion=emotion)
                        )
                else:
                    discord_voice_bot.play_text_to_vc_sync(spoken_dialogue)

            time.sleep(0.3)
            bridge.subtitle_signal.emit("")

        except Exception:
            pass

if __name__ == "__main__":
    server_thread = threading.Thread(target=start_local_server, daemon=True)
    server_thread.start()

    app = QApplication(sys.argv)
    bridge = AvatarSignalBridge()
    window = TransparentAvatarWindow(bridge)
    window.show()

    tts = SmartTTSEngine(bridge)

    discord_thread = threading.Thread(
        target=discord_voice_bot.start_discord_bot_thread, daemon=True
    )
    discord_thread.start()

    terminal_thread = threading.Thread(
        target=terminal_chat_loop, args=(bridge, tts), daemon=True
    )
    terminal_thread.start()

    sys.exit(app.exec_())