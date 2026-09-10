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
import avatar_motion
import config
import discord_voice_bot
import pc_controller
from stt_engine import STTEngine
from groq import Groq

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PORT = getattr(config, "HTTP_PORT", 8000)

signal.signal(signal.SIGINT, signal.SIG_DFL)
speech_lock = threading.Lock()
input_queue = queue.Queue()

if not getattr(config, "GROQ_API_KEY", "") or config.GROQ_API_KEY == "MASUKKAN_GROQ_API_KEY_ANDA_DISINI":
    print("\n[ERROR] API Key Groq belum diatur di config.py!")
    sys.exit(1)

groq_client = Groq(api_key=config.GROQ_API_KEY)

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
    expression_signal = pyqtSignal(str)

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

        self.webview.loadFinished.connect(self.inject_subtitle_system)
        self.webview.load(QUrl(f"http://127.0.0.1:{PORT}/Assets/viewer/index.html"))
        
        self.resize(750, 1000)

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
        self.webview.page().runJavaScript(js_init)

    def update_mouth_in_web(self, value: float):
        self.webview.page().runJavaScript(f"if(window.setMouthOpen) setMouthOpen({value});")

    @pyqtSlot(str)
    def update_subtitle_in_web(self, html_content: str):
        escaped = json.dumps(html_content)
        self.webview.page().runJavaScript(f"if(window.setSubtitle) setSubtitle({escaped});")

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
        self.voice_id = getattr(config, "ELEVENLABS_VOICE_ID", "EXAVITQu4vr4xnSDxMaL")
        pygame.mixer.init()

    async def speak_with_lipsync(self, text: str, emotion: str = "natural"):
        if not self.api_key or self.api_key == "paste_api_key_elevenlabs_kamu_di_sini":
            print("\n[TTS Error] API Key ElevenLabs belum dikonfigurasi!")
            return
            
        try:
            print("\n[TTS] ⏳ Menghasilkan suara dari ElevenLabs...")
            
            response = self.client.text_to_speech.convert(
                voice_id=self.voice_id,
                model_id="eleven_multilingual_v2",
                text=text
            )
            
            audio_bytes = b"".join(response)
            
            with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as fp:
                fp.write(audio_bytes)
                tmp_path = fp.name
                
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
                
        except Exception as e:
            print(f"\n[SYSTEM] ElevenLabs Gagal ({e}). Mengaktifkan Fallback ke Edge-TTS 🟡...")
            try:
                if re.search(r"[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff]", text):
                    voice = getattr(config, "DEFAULT_EDGE_VOICE_JA", "ja-JP-NanamiNeural")
                elif any(w in text.lower().split() for w in ["what", "the", "fuck", "you", "stfu", "bitch"]):
                    voice = getattr(config, "DEFAULT_EDGE_VOICE_EN", "en-US-AnaNeural")
                else:
                    voice = getattr(config, "DEFAULT_EDGE_VOICE_ID", "id-ID-GadisNeural")

                with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as fp:
                    tmp_path = fp.name

                communicate = edge_tts.Communicate(
                    text, 
                    voice, 
                    pitch=getattr(config, "EDGE_TTS_PITCH", "+14Hz"), 
                    rate=getattr(config, "EDGE_TTS_RATE", "+5%")
                )
                await communicate.save(tmp_path)
                
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

            except Exception as edge_e:
                print(f"\n[TTS Error] Edge-TTS juga gagal: {edge_e}")
                self.bridge.mouth_signal.emit(0.0)

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
    
    tts_dictionary = {
        r"\be-eh\b": "eehh", r"\bu-umm\b": "uuumm", r"\ba-anu\b": "aa-nuu",
        r"\be-hehe\b": "ehehhe", r"\bm-maaf\b": "mmaaff", r"\bcih\b": "tcihh",
        r"\bck\b": "tck", r"\bhaha\b": "hahaha", r"\bhehe\b": "hehhe",
        r"\bdih\b": "dihh", r"\bgrr\b": "grrr",
        
        r"\bfr\b": "for real",
        r"\bfrfr\b": "for real for real",
        r"\bong\b": "on god",
        r"\bngl\b": "not gonna lie",
        r"\btbh\b": "to be honest",
        r"\bidk\b": "i don't know",
        r"\bwtf\b": "what the fuck",
        r"\blmao\b": "la mao", 
        r"\baf\b": "as fuck",
        r"\brn\b": "right now",
        r"\bbrb\b": "be right back",
        r"\bbtw\b": "by the way",
        r"\bomg\b": "oh my god",
        r"\bwdym\b": "what do you mean",
        r"\bjk\b": "just kidding",
        r"\bnvm\b": "nevermind",
        
        r"\byg\b": "yang",
        r"\bgw\b": "gue",
        r"\blu\b": "elu",
        r"\bbgt\b": "banget",
        r"\btp\b": "tapi",
        r"\bjd\b": "jadi",
        r"\bkalo\b": "kalau",
        r"\bpls\b": "please",
        r"\baja\b": "saja",
        r"\bjg\b": "juga",
        r"\banj\b": "anjay",
        r"\bdgn\b": "dengan",
        r"\bkrn\b": "karena",
        r"\bsbb\b": "sorry baru balas",
        
        r"\bwww+\b": "kusa",
        r"\bmjk\b": "majika",
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
            print(f"\n[Keyboard Error] {e}")
            time.sleep(2)

def mic_input_loop(stt):
    while True:
        try:
            text = stt.listen_voice()
            if text:
                print(f"\n[Mic Heard] 🎙️: {text}")
                input_queue.put(text)
        except Exception as e:
            print(f"\n[Mic Error] Gagal merekam audio: {e}")
            time.sleep(5)

def chat_processor_loop(bridge, tts_engine):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    time.sleep(1.0)
    print("\n" + "=" * 65)
    print(" 💬 TUZI AI READY (Groq Qwen Brain + ElevenLabs Voice Mode)")
    print("=" * 65 + "\n")

    system_prompt = (
        "Kamu adalah Tuzi, pendamping virtual milik Zak (atau Jak). Kamu memiliki memori yang kuat dan sangat peka terhadap konteks pembicaraan.\n\n"
        "=== KEPRIBADIAN MULTI-FASE ===\n"
        "1. MODE GYARU (DEFAULT): Kamu adalah gadis ekstrover yang enerjik, selalu penasaran, ceria, dan sangat 'gaul'. Kamu sangat antusias mengobrol dengan Zak. Nada bicaramu cepat dan bersemangat.\n"
        "2. MODE TSUNDERE (TRIGGER JAHIL): JIKA Zak memancing emosimu, mengejek, atau menjahilimu, kamu akan bereaksi marah, gengsi, dan judes ala Tsundere. Kamu akan memarahinya atau menyuruhnya diam.\n"
        "3. MODE SHY/PEMALU (TRIGGER GODAAN): JIKA Zak merayumu, bersikap romantis, atau memujimu berlebihan, kamu akan langsung salah tingkah, malu, gugup, dan bicaramu menjadi terbata-bata.\n"
        "Panggil user HANYA dengan nama 'Zak' atau 'Jak'.\n\n"
        "=== ATURAN BAHASA (SANGAT KETAT) ===\n"
        "1. GAYA BAHASA SLANG: Selalu gunakan bahasa gaul/slang yang trendi di setiap bahasa.\n"
        "2. ISOLASI BAHASA: WAJIB balas dengan bahasa yang sama 100%. DILARANG mencampur bahasa!\n"
        "   - Jika Inggris: Gunakan slang Inggris (bro, chill, fr, ngl). 100% Inggris.\n"
        "   - Jika Jepang: Gunakan slang Jepang/Gyaru (majide, yabai, chou). 100% Jepang.\n"
        "   - Jika Indonesia: Gunakan slang Indo (anjir, sumpah, lu/gw, kek). 100% Indonesia.\n\n"
        "=== FORMAT WAJIB (UNTUK ENGINE TTS) ===\n"
        "1. AWALI SETIAP BALASAN dengan SATU tag emosi ini saja: [EMO:excited], [EMO:angry], [EMO:soft] (saat malu), atau [EMO:natural].\n"
        "2. Manipulasi intonasi TTS:\n"
        "   - Gunakan tanda seru (!) atau huruf kapital untuk nada antusias (Gyaru) atau marah (Tsundere).\n"
        "   - SANGAT SERING gunakan titik tiga (...) dan tanda hubung (-) HANYA SAAT mode malu/gugup (misal: 'Z-Zak... b-baka!').\n"
        "3. Balas maksimal 2-3 kalimat. DILARANG pakai emoji visual."
    )

    chat_history = [{"role": "system", "content": system_prompt}]

    while True:
        try:
            user_input = input_queue.get()
            
            print(f"\n[Tuzi Memproses] ⏳: {user_input}")

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
                user_input += f"\n\n[SISTEM INFO: Kamu memiliki akses ke sistem PC. Kamu baru saja mengeksekusi perintah: '{pc_info}'. Konfirmasikan ke Zak dengan gayamu (Gyaru/Tsundere) bahwa kamu sedang membukanya/menyetelnya sekarang!]"

            tag_match = re.search(r"\btag\s+(?:si\s+)?([a-zA-Z0-9_.-]+)", user_input.lower())
            join_vc_match = re.search(r"\b(masuk|join|susul)\b.*\b(voice|vc|call|discord|z|zak)\b", user_input.lower())
            leave_vc_match = re.search(r"\b(keluar|leave|putus)\b.*\b(voice|vc|call|discord)\b", user_input.lower())

            if tag_match:
                is_discord_command = True
                target_name = tag_match.group(1)
                success, msg = discord_voice_bot.trigger_tag_user_sync(target_name)
                
                if success:
                    user_input += f"\n\n[SISTEM INFO: Kamu baru saja berhasil men-tag '{target_name}' di Discord. Beritahu Zak dengan gayamu bahwa kamu sudah memanggil orang tersebut di chat!]"
                else:
                    user_input += f"\n\n[SISTEM INFO: Gagal men-tag '{target_name}'. Alasan: {msg}. Ejek Zak karena menyuruhmu menge-tag orang yang tidak ada di server!]"

            elif join_vc_match:
                is_discord_command = True
                success, code_or_channel, msg_or_owner = discord_voice_bot.trigger_join_from_voice()
                if success:
                    user_input += f"\n\n[SISTEM INFO: Kamu berhasil menyusul Zaki (z) ke Voice Channel '{code_or_channel}'. Sapa dia dengan nada Tsundere/sassy, tunjukkan kalau kamu repot-repot datang ke VC demi dia!]"
                else:
                    user_input += f"\n\n[SISTEM INFO: Gagal masuk ke VC. Alasan: {msg_or_owner}. Marahi si Z karena menyuruhmu menyusul tapi dia sendiri belum masuk ke Voice Channel mana pun!]"
            
            elif leave_vc_match:
                is_discord_command = True
                success = discord_voice_bot.trigger_leave_from_voice()
                if success:
                    user_input += "\n\n[SISTEM INFO: Kamu baru saja keluar dari Voice Channel Discord. Berikan kata perpisahan ala Tsundere/angkuh kepada Zaki!]"
                else:
                    user_input += "\n\n[SISTEM INFO: Zaki menyuruhmu keluar dari VC, tapi kamu sebenarnya tidak sedang berada di VC mana pun. Ejek dia karena pikun!]"

            tool_context = ai_tools.get_tools_context(user_input)
            if tool_context:
                user_input += f"\n\n{tool_context}"

            chat_history.append({"role": "user", "content": user_input})
            
            if len(chat_history) > 15:
                chat_history = [chat_history[0]] + chat_history[-14:]

            response = groq_client.chat.completions.create(
                model="qwen/qwen3.8-27b",
                messages=chat_history,
                temperature=0.88,
                max_tokens=150
            )
            
            raw_output = response.choices[0].message.content.strip()
            chat_history.append({"role": "assistant", "content": raw_output})

            emotion, display_dialogue, spoken_dialogue = extract_emotion_and_text(raw_output)
            
            bridge.expression_signal.emit(emotion)

            if len(display_dialogue) > 1:
                bridge.subtitle_signal.emit(display_dialogue)

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
            bridge.expression_signal.emit("natural")

        except Exception as e:
            print(f"\n[Otak Tuzi Error] {e}")
            time.sleep(2)

if __name__ == "__main__":
    server_thread = threading.Thread(target=start_local_server, daemon=True)
    server_thread.start()

    app = QApplication(sys.argv)
    bridge = AvatarSignalBridge()
    window = TransparentAvatarWindow(bridge)
    window.show()

    tts = ElevenLabsTTSEngine(bridge)
    stt = STTEngine(language="id-ID")

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