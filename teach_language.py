import re
import threading
import speech_recognition as sr
from PyQt5.QtCore import Qt, QPoint
from PyQt5.QtWidgets import QApplication

is_active = False
target_lang = "en-US"
main_input_queue = None

# Ukuran Desktop Landscape (2x lebih kecil dari 1920x1080)
TEACH_WIN_WIDTH = 960
TEACH_WIN_HEIGHT = 540

# Ukuran Asli Mode Overlay Desktop
DEFAULT_WIN_WIDTH = 600
DEFAULT_WIN_HEIGHT = 1300

class HoldToTalkRecorder:
    def __init__(self):
        self.recognizer = sr.Recognizer()
        self.is_recording = False
        self.frames = []
        self.lang = "en-US"

    def start_recording(self, lang_code="en-US"):
        global target_lang
        if self.is_recording:
            return
        self.lang = lang_code
        target_lang = lang_code
        self.is_recording = True
        self.frames = []
        threading.Thread(target=self._record_loop, daemon=True).start()

    def _record_loop(self):
        try:
            with sr.Microphone(sample_rate=16000) as source:
                print(f"\n[TEACH MIC - {self.lang}] Mendengarkan... (Tahan tombol)")
                while self.is_recording:
                    buffer = source.stream.read(source.CHUNK)
                    self.frames.append(buffer)

            if len(self.frames) > 3:
                print("[TEACH MIC] Memproses ucapan Zak...")
                raw_data = b"".join(self.frames)
                audio_data = sr.AudioData(raw_data, 16000, 2)
                text = self.recognizer.recognize_google(audio_data, language=self.lang)
                if text and text.strip() and main_input_queue:
                    print(f"[TEACH MIC] Zak: {text}")
                    main_input_queue.put(f"[TEACH_INPUT] {text.strip()}")
        except sr.UnknownValueError:
            print("[TEACH MIC] Suara tidak terdengar jelas.")
        except Exception as e:
            print(f"[TEACH MIC Error] {e}")

    def stop_recording(self):
        self.is_recording = False

ptt_recorder = HoldToTalkRecorder()

def handle_teach_mode(user_input: str, bridge):
    """Mendeteksi perintah masuk/keluar mode belajar secara SENYAP (0 Token)."""
    global is_active

    is_teach_input = False
    if user_input.startswith("[TEACH_INPUT]"):
        is_teach_input = True
        user_input = user_input.replace("[TEACH_INPUT]", "").strip()

    teach_trigger = re.search(
        r"\b(mode\s+teach|teach\s+language|mode\s+belajar|belajar\s+bahasa|ajarin\s+bahasa|language\s+mode|duolingo)\b",
        user_input.lower()
    )
    exit_trigger = re.search(
        r"\b(exit\s+teach|keluar\s+mode\s+belajar|stop\s+belajar|normal\s+mode|tutup\s+mode\s+belajar)\b",
        user_input.lower()
    )

    if teach_trigger and not is_active:
        is_active = True
        print("\n[Sistem] Membuka UI Tuzi Language Tutor (Senyap / Hemat Token)...")
        bridge.teach_mode_signal.emit(True)
        bridge.subtitle_signal.emit("Mode Belajar Aktif — Tahan tombol mikrofon di bawah untuk bicara.")
        return None

    elif exit_trigger and is_active:
        is_active = False
        print("\n[Sistem] Menutup UI Language Tutor (Senyap / Hemat Token)...")
        bridge.subtitle_signal.emit("")
        bridge.teach_mode_signal.emit(False)
        return None

    elif is_active and is_teach_input:
        user_input += (
            f"\n\n[SYSTEM INFO - LANGUAGE TUTOR ACTIVE (Target Language: {target_lang}): "
            "1. If Zak's grammar or pronunciation phrasing is unnatural, briefly correct it first. "
            "2. Reply naturally to keep the practice conversation going OR give him a short phrase to repeat. "
            "3. Keep your current Tuzi personality (Mode 1/2/3) and stay under 20 words!]"
        )

    return user_input

def apply_window_state(window, active: bool):
    """Mengubah ukuran jendela ke 960x540 di tengah layar dan memicu tata letak PixiJS."""
    screen_geo = QApplication.primaryScreen().geometry()
    if hasattr(window, "anim"):
        window.anim.stop()

    if active:
        window.webview.setAttribute(Qt.WA_TransparentForMouseEvents, False)
        window.resize(TEACH_WIN_WIDTH, TEACH_WIN_HEIGHT)
        center_x = (screen_geo.width() - TEACH_WIN_WIDTH) // 2
        center_y = (screen_geo.height() - TEACH_WIN_HEIGHT) // 2
        window.move(QPoint(center_x, center_y))
        window.webview.page().runJavaScript("if(window.setTeachModeUI) setTeachModeUI(true);")
    else:
        window.webview.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        window.resize(DEFAULT_WIN_WIDTH, DEFAULT_WIN_HEIGHT)
        right_x = screen_geo.width() - DEFAULT_WIN_WIDTH
        right_y = screen_geo.height() - DEFAULT_WIN_HEIGHT - 45
        window.move(QPoint(right_x, right_y))
        window.webview.page().runJavaScript("if(window.setTeachModeUI) setTeachModeUI(false);")

def get_ui_injection_js() -> str:
    """Menyuntikkan UI Light Mode tanpa memodifikasi CSS <canvas> agar render WebGL tetap murni."""
    return """
    (function() {
        if (document.getElementById('tuzi-teach-overlay')) return;

        let script = document.createElement('script');
        script.src = 'qrc:///qtwebchannel/qwebchannel.js';
        script.onload = function() {
            new QWebChannel(qt.webChannelTransport, function(channel) {
                window.pyBridge = channel.objects.bridge;
            });
        };
        document.head.appendChild(script);

        let style = document.createElement('style');
        style.innerHTML = `
            body.teach-mode-active {
                background: #FFFFFF !important;
                border: 2.5px solid #0D0D0D !important;
                border-radius: 24px !important;
                overflow: hidden !important;
                box-sizing: border-box !important;
            }

            body.teach-mode-active #tuzi-subtitle-box {
                top: 68px !important;
                left: 50% !important;
                background: rgba(255, 255, 255, 0.95) !important;
                color: #0D0D0D !important;
                border: 1.5px solid #0D0D0D !important;
                text-shadow: none !important;
                box-shadow: 0 8px 24px rgba(0, 0, 0, 0.12) !important;
                max-width: 560px !important;
                z-index: 999999 !important;
            }

            #tuzi-teach-overlay {
                display: none;
                position: fixed;
                top: 0;
                left: 0;
                width: 100vw;
                height: 100vh;
                pointer-events: none;
                z-index: 999990;
                font-family: 'Segoe UI', -apple-system, sans-serif;
                box-sizing: border-box;
            }
            body.teach-mode-active #tuzi-teach-overlay {
                display: flex;
                flex-direction: column;
                justify-content: space-between;
            }

            .teach-header {
                pointer-events: auto;
                display: flex;
                justify-content: space-between;
                align-items: center;
                padding: 14px 24px;
                background: rgba(255, 255, 255, 0.92);
                border-bottom: 1px solid #E5E5E5;
                box-sizing: border-box;
                width: 100%;
            }
            .teach-left-group {
                display: flex;
                align-items: center;
                gap: 12px;
            }
            .teach-title {
                color: #0D0D0D;
                font-size: 13px;
                font-weight: 800;
                letter-spacing: 1.2px;
            }
            .cam-controls {
                display: flex;
                gap: 4px;
            }
            .cam-btn {
                background: #F4F4F4;
                color: #0D0D0D;
                border: 1px solid #D4D4D4;
                border-radius: 6px;
                width: 24px;
                height: 24px;
                font-size: 11px;
                font-weight: bold;
                cursor: pointer;
                display: flex;
                align-items: center;
                justify-content: center;
            }
            .cam-btn:hover { background: #0D0D0D; color: #FFFFFF; }

            .lang-selector {
                display: flex;
                background: #F4F4F4;
                padding: 4px;
                border-radius: 24px;
                border: 1px solid #E5E5E5;
                gap: 4px;
            }
            .lang-btn {
                background: transparent;
                color: #666666;
                border: none;
                border-radius: 18px;
                padding: 5px 14px;
                font-size: 12px;
                font-weight: 700;
                cursor: pointer;
                transition: all 0.2s ease;
            }
            .lang-btn.active {
                background: #0D0D0D;
                color: #FFFFFF;
                box-shadow: 0 2px 6px rgba(0,0,0,0.15);
            }

            .teach-close-btn {
                background: #F4F4F4;
                color: #0D0D0D;
                border: 1px solid #E5E5E5;
                border-radius: 50%;
                width: 32px;
                height: 32px;
                cursor: pointer;
                font-size: 14px;
                font-weight: bold;
                transition: all 0.2s ease;
            }
            .teach-close-btn:hover {
                background: #0D0D0D;
                color: #FFFFFF;
            }

            .teach-footer {
                pointer-events: auto;
                display: flex;
                flex-direction: column;
                align-items: center;
                justify-content: center;
                padding-bottom: 22px;
                padding-top: 20px;
                width: 100%;
                background: linear-gradient(to top, rgba(255,255,255,0.95) 60%, rgba(255,255,255,0));
            }
            #ptt-button {
                width: 72px;
                height: 72px;
                border-radius: 50%;
                background: #0D0D0D;
                color: #FFFFFF;
                border: 3px solid #FFFFFF;
                box-shadow: 0 0 0 2px #0D0D0D, 0 8px 20px rgba(0, 0, 0, 0.2);
                cursor: pointer;
                display: flex;
                align-items: center;
                justify-content: center;
                transition: all 0.15s ease;
                user-select: none;
                outline: none;
            }
            #ptt-button.holding {
                background: #FFFFFF;
                color: #0D0D0D;
                transform: scale(1.12);
                box-shadow: 0 0 0 4px #0D0D0D, 0 0 0 12px rgba(13, 13, 13, 0.15);
            }
            #ptt-status {
                color: #0D0D0D;
                font-size: 12px;
                font-weight: 800;
                margin-top: 10px;
                letter-spacing: 1px;
            }
        `;
        document.head.appendChild(style);

        let overlay = document.createElement('div');
        overlay.id = 'tuzi-teach-overlay';
        overlay.innerHTML = `
            <div class="teach-header">
                <div class="teach-left-group">
                    <div class="teach-title">● TUZI TUTOR</div>
                    <div class="cam-controls" title="Atur posisi X/Y & zoom avatar">
                        <button class="cam-btn" id="cam-left">◀</button>
                        <button class="cam-btn" id="cam-right">▶</button>
                        <button class="cam-btn" id="cam-up">▲</button>
                        <button class="cam-btn" id="cam-down">▼</button>
                        <button class="cam-btn" id="cam-zoom-in">＋</button>
                        <button class="cam-btn" id="cam-zoom-out">－</button>
                    </div>
                </div>
                <div class="lang-selector">
                    <button class="lang-btn active" data-lang="en-US">EN</button>
                    <button class="lang-btn" data-lang="ja-JP">JA</button>
                    <button class="lang-btn" data-lang="id-ID">ID</button>
                </div>
                <button class="teach-close-btn" id="exit-teach-btn">✕</button>
            </div>
            <div class="teach-footer">
                <button id="ptt-button">
                    <svg width="28" height="28" viewBox="0 0 24 24" fill="currentColor">
                        <path d="M12 14c1.66 0 3-1.34 3-3V5c0-1.66-1.34-3-3-3S9 3.34 9 5v6c0 1.66 1.34 3 3 3zm5.91-3c-.49 0-.9.36-.98.85C16.52 14.2 14.47 16 12 16s-4.52-1.8-4.93-4.15c-.08-.49-.49-.85-.98-.85-.61 0-1.09.54-1 1.14.49 3 2.89 5.35 5.91 5.78V20c0 .55.45 1 1 1s1-.45 1-1v-2.08c3.02-.43 5.42-2.78 5.91-5.78.1-.6-.39-1.14-1-1.14z"/>
                    </svg>
                </button>
                <div id="ptt-status">HOLD TO SPEAK</div>
            </div>
        `;
        document.body.appendChild(overlay);

        // Menggerakkan model langsung di dalam engine PixiJS (Bukan via CSS)
        document.getElementById('cam-left').onclick = () => { window.camOffsetX -= 25; if(window.updateModelLayout) window.updateModelLayout(); };
        document.getElementById('cam-right').onclick = () => { window.camOffsetX += 25; if(window.updateModelLayout) window.updateModelLayout(); };
        document.getElementById('cam-up').onclick = () => { window.camOffsetY -= 30; if(window.updateModelLayout) window.updateModelLayout(); };
        document.getElementById('cam-down').onclick = () => { window.camOffsetY += 30; if(window.updateModelLayout) window.updateModelLayout(); };
        document.getElementById('cam-zoom-in').onclick = () => { window.camZoom += 0.1; if(window.updateModelLayout) window.updateModelLayout(); };
        document.getElementById('cam-zoom-out').onclick = () => { window.camZoom = Math.max(0.4, window.camZoom - 0.1); if(window.updateModelLayout) window.updateModelLayout(); };

        window.currentTeachLang = 'en-US';
        document.querySelectorAll('.lang-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                document.querySelectorAll('.lang-btn').forEach(b => b.classList.remove('active'));
                btn.classList.add('active');
                window.currentTeachLang = btn.getAttribute('data-lang');
            });
        });

        document.getElementById('exit-teach-btn').addEventListener('click', () => {
            if (window.pyBridge) window.pyBridge.exit_teach_ui();
        });

        let pttBtn = document.getElementById('ptt-button');
        let pttStatus = document.getElementById('ptt-status');
        let isHolding = false;

        function startHold(e) {
            e.preventDefault();
            if (isHolding) return;
            isHolding = true;
            pttBtn.classList.add('holding');
            pttStatus.innerText = 'LISTENING...';
            if (window.pyBridge) window.pyBridge.start_ptt(window.currentTeachLang);
        }

        function stopHold(e) {
            e.preventDefault();
            if (!isHolding) return;
            isHolding = false;
            pttBtn.classList.remove('holding');
            pttStatus.innerText = 'HOLD TO SPEAK';
            if (window.pyBridge) window.pyBridge.stop_ptt();
        }

        pttBtn.addEventListener('mousedown', startHold);
        window.addEventListener('mouseup', stopHold);

        window.setTeachModeUI = function(active) {
            if (active) {
                document.body.classList.add('teach-mode-active');
            } else {
                document.body.classList.remove('teach-mode-active');
            }
            setTimeout(() => {
                if (window.updateModelLayout) window.updateModelLayout();
            }, 60);
        };
    })();
    """