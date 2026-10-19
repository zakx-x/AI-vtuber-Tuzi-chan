import re
import threading
import speech_recognition as sr
from PyQt5.QtCore import Qt, QPoint
from PyQt5.QtWidgets import QApplication

is_active = False
ui_submode = "live"  # "live" (Voice Mic-to-Mic) atau "chat" (Text Chatbot)
target_lang = "en-US"
main_input_queue = None

# Ukuran Desktop Landscape Besar (1600x900)
TEACH_WIN_WIDTH = 1600
TEACH_WIN_HEIGHT = 900

# Ukuran Asli Mode Overlay Desktop
DEFAULT_WIN_WIDTH = 600
DEFAULT_WIN_HEIGHT = 1300

class HoldToTalkRecorder:
    def __init__(self):
        self.recognizer = sr.Recognizer()
        self.is_recording = False
        self.frames = []
        self.lang = "en-US"

    def start_recording(self, payload="en-US"):
        global target_lang, ui_submode

        # 1. Jika payload dari UI adalah pergantian sub-mode (LIVE / CHAT)
        if payload == "MODE:LIVE":
            ui_submode = "live"
            print("\n[TUZI UI] Beralih ke tab LIVE (Voice Mode).")
            return
        elif payload == "MODE:CHAT":
            ui_submode = "chat"
            print("\n[TUZI UI] Beralih ke tab CHAT (Chatbot Mode).")
            return

        # 2. Jika payload dari UI adalah pesan teks dari mode Chatbot
        if payload.startswith("CHAT:"):
            chat_text = payload[5:].strip()
            if chat_text and main_input_queue:
                ui_submode = "chat"
                print(f"\n[TEACH CHAT] Zak: {chat_text}")
                main_input_queue.put(f"[TEACH_INPUT] {chat_text}")
            return

        # 3. Jika payload normal (Hold-to-Talk Mic di mode Live)
        if self.is_recording:
            return
        ui_submode = "live"
        self.lang = payload
        target_lang = payload
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
        print("\n[Sistem] Membuka UI Tuzi Language Tutor (1600x900 - Senyap / Hemat Token)...")
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
            "1. If Zak's grammar or phrasing is unnatural, briefly correct it first. "
            "2. Reply naturally to keep the practice conversation going OR give him a short phrase to repeat. "
            "3. Keep your current Tuzi personality (Mode 1/2/3) and stay under 20 words!]"
        )

    return user_input

def apply_window_state(window, active: bool):
    """Mengubah ukuran jendela ke 1600x900 di tengah layar dan memicu tata letak PixiJS."""
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
    """Menyuntikkan UI Light Mode dengan Sidebar Burger Menu (Chat & Live) serta Discord Call Dock."""
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
                border: 3px solid #0D0D0D !important;
                border-radius: 28px !important;
                overflow: hidden !important;
                box-sizing: border-box !important;
            }

            /* Sembunyikan subtitle melayang saat berada di tab Chat */
            body.teach-mode-active.chat-tab-open #tuzi-subtitle-box {
                display: none !important;
            }

            body.teach-mode-active #tuzi-subtitle-box {
                top: 32px !important;
                left: 50% !important;
                background: rgba(255, 255, 255, 0.96) !important;
                color: #0D0D0D !important;
                border: 2px solid #0D0D0D !important;
                font-size: 16px !important;
                padding: 14px 24px !important;
                text-shadow: none !important;
                box-shadow: 0 10px 30px rgba(0, 0, 0, 0.10) !important;
                max-width: 680px !important;
                z-index: 999992 !important;
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
                justify-content: flex-end;
                align-items: center;
            }

            /* === TOMBOL BURGER POJOK KIRI ATAS === */
            #tuzi-burger-btn {
                pointer-events: auto;
                position: fixed;
                top: 24px;
                left: 24px;
                width: 44px;
                height: 44px;
                border-radius: 12px;
                background: #FFFFFF;
                color: #0D0D0D;
                border: 2px solid #0D0D0D;
                cursor: pointer;
                display: flex;
                align-items: center;
                justify-content: center;
                box-shadow: 0 4px 14px rgba(0, 0, 0, 0.10);
                transition: all 0.15s ease;
                z-index: 999995;
                outline: none;
            }
            #tuzi-burger-btn:hover {
                background: #0D0D0D;
                color: #FFFFFF;
            }

            /* === SIDEBAR MENU KIRI (PUTIH & HITAM) === */
            #tuzi-sidebar {
                pointer-events: auto;
                position: fixed;
                top: 0;
                left: 0;
                width: 280px;
                height: 100vh;
                background: #FFFFFF;
                color: #0D0D0D;
                border-right: 2px solid #E5E5E5;
                box-shadow: 10px 0 30px rgba(0, 0, 0, 0.08);
                display: flex;
                flex-direction: column;
                padding: 22px 18px;
                box-sizing: border-box;
                transform: translateX(-105%);
                transition: transform 0.25s cubic-bezier(0.25, 1, 0.5, 1);
                z-index: 999999;
            }
            #tuzi-sidebar.open {
                transform: translateX(0);
            }

            /* Header Sidebar: Logo TUZI + Collapse Icon */
            .sidebar-header {
                display: flex;
                align-items: center;
                justify-content: space-between;
                margin-bottom: 20px;
                padding: 0 4px;
            }
            .sidebar-brand {
                display: flex;
                align-items: center;
                font-size: 20px;
                font-weight: 900;
                color: #0D0D0D;
                letter-spacing: 0.8px;
            }
            .sidebar-brand svg {
                margin-right: 10px;
            }
            .sidebar-collapse-btn {
                width: 34px;
                height: 34px;
                border-radius: 8px;
                background: transparent;
                color: #0D0D0D;
                border: none;
                cursor: pointer;
                display: flex;
                align-items: center;
                justify-content: center;
                transition: background 0.15s ease;
            }
            .sidebar-collapse-btn:hover {
                background: #F0F0F0;
            }

            /* Segmented Pill Switcher: Chat | Live */
            .mode-switch-pill {
                display: flex;
                background: #F2F2F2;
                border: 1.5px solid #E0E0E0;
                border-radius: 999px;
                padding: 4px;
                margin-bottom: 24px;
            }
            .mode-tab-btn {
                flex: 1;
                height: 36px;
                border: none;
                border-radius: 999px;
                background: transparent;
                color: #555555;
                font-size: 13.5px;
                font-weight: 700;
                cursor: pointer;
                display: flex;
                align-items: center;
                justify-content: center;
                transition: all 0.2s ease;
                outline: none;
            }
            .mode-tab-btn.active {
                background: #0D0D0D;
                color: #FFFFFF;
                box-shadow: 0 2px 8px rgba(0, 0, 0, 0.18);
            }
            .live-badge {
                font-size: 9px;
                font-weight: 800;
                padding: 2px 5px;
                border-radius: 6px;
                background: rgba(255, 255, 255, 0.2);
                margin-left: 6px;
                letter-spacing: 0.5px;
            }
            .mode-tab-btn:not(.active) .live-badge {
                background: #E0E0E0;
                color: #0D0D0D;
            }

            /* Daftar Menu di Sidebar */
            .sidebar-menu-list {
                display: flex;
                flex-direction: column;
            }
            .sidebar-item {
                display: flex;
                align-items: center;
                height: 44px;
                padding: 0 12px;
                margin-bottom: 6px;
                border-radius: 12px;
                background: transparent;
                color: #0D0D0D;
                border: none;
                font-size: 14px;
                font-weight: 600;
                cursor: pointer;
                text-align: left;
                transition: background 0.15s ease;
                outline: none;
            }
            .sidebar-item svg {
                margin-right: 14px;
                color: #0D0D0D;
            }
            .sidebar-item:hover {
                background: #F4F4F4;
            }
            .sidebar-section-label {
                font-size: 12px;
                font-weight: 700;
                color: #777777;
                margin: 18px 0 8px 12px;
                text-transform: uppercase;
                letter-spacing: 0.6px;
            }

            /* === TAMPILAN CHATBOT (SAAT TAB 'CHAT' AKTIF) === */
            #tuzi-chat-view {
                pointer-events: auto;
                display: none;
                position: fixed;
                top: 0;
                left: 0;
                width: 100vw;
                height: 100vh;
                background: #FFFFFF;
                flex-direction: column;
                justify-content: space-between;
                align-items: center;
                padding: 28px 40px 30px 40px;
                box-sizing: border-box;
                z-index: 999993;
            }
            body.teach-mode-active.chat-tab-open #tuzi-chat-view {
                display: flex;
            }
            body.teach-mode-active.chat-tab-open .discord-call-wrapper {
                display: none !important;
            }

            .chat-top-bar {
                width: 100%;
                max-width: 820px;
                display: flex;
                align-items: center;
                justify-content: space-between;
                padding-bottom: 14px;
                border-bottom: 1.5px solid #EBEBEB;
            }
            .chat-top-title {
                font-size: 16px;
                font-weight: 800;
                color: #0D0D0D;
                letter-spacing: 0.5px;
            }

            #tuzi-chat-messages {
                width: 100%;
                max-width: 820px;
                flex: 1;
                overflow-y: auto;
                padding: 24px 8px;
                display: flex;
                flex-direction: column;
                box-sizing: border-box;
            }
            .chat-bubble-row {
                display: flex;
                width: 100%;
                margin-bottom: 16px;
            }
            .chat-bubble-row.user {
                justify-content: flex-end;
            }
            .chat-bubble-row.bot {
                justify-content: flex-start;
            }
            .chat-bubble {
                max-width: 72%;
                padding: 13px 18px;
                border-radius: 18px;
                font-size: 15px;
                font-weight: 500;
                line-height: 1.5;
                word-wrap: break-word;
            }
            .chat-bubble-row.user .chat-bubble {
                background: #0D0D0D;
                color: #FFFFFF;
                border-bottom-right-radius: 4px;
            }
            .chat-bubble-row.bot .chat-bubble {
                background: #F7F7F7;
                color: #0D0D0D;
                border: 1.5px solid #0D0D0D;
                border-bottom-left-radius: 4px;
            }

            /* Input Box Chatbot di Bawah */
            .chat-input-bar {
                width: 100%;
                max-width: 820px;
                display: flex;
                align-items: center;
                background: #FFFFFF;
                border: 2px solid #0D0D0D;
                border-radius: 20px;
                padding: 8px 12px 8px 20px;
                box-shadow: 0 8px 24px rgba(0, 0, 0, 0.06);
                box-sizing: border-box;
            }
            #tuzi-chat-input {
                flex: 1;
                border: none;
                outline: none;
                background: transparent;
                color: #0D0D0D;
                font-size: 15px;
                font-weight: 500;
                font-family: inherit;
            }
            #tuzi-chat-send {
                width: 42px;
                height: 42px;
                border-radius: 14px;
                background: #0D0D0D;
                color: #FFFFFF;
                border: none;
                cursor: pointer;
                display: flex;
                align-items: center;
                justify-content: center;
                margin-left: 10px;
                transition: transform 0.15s ease;
            }
            #tuzi-chat-send:hover {
                transform: scale(1.05);
            }

            /* === DISCORD CALL BOTTOM BAR (SAAT TAB 'LIVE' AKTIF) === */
            .discord-call-wrapper {
                pointer-events: auto;
                display: flex;
                align-items: center;
                justify-content: center;
                margin-bottom: 34px;
                z-index: 10;
            }
            .discord-call-wrapper > * {
                margin: 0 10px !important;
            }

            .discord-dock {
                display: flex;
                align-items: center;
                background: #111214;
                padding: 8px 10px;
                border-radius: 20px;
                box-shadow: 0 12px 32px rgba(0, 0, 0, 0.25);
                border: 1px solid rgba(255, 255, 255, 0.08);
            }

            #ptt-button {
                height: 52px;
                padding: 0 22px;
                border-radius: 14px;
                background: #3A1E20;
                color: #F23F43;
                border: none;
                cursor: pointer;
                display: flex;
                align-items: center;
                justify-content: center;
                font-size: 13px;
                font-weight: 800;
                letter-spacing: 0.6px;
                transition: all 0.15s ease;
                user-select: none;
                outline: none;
            }
            #ptt-button svg {
                margin-right: 10px;
            }
            #ptt-button:hover {
                background: #4B2528;
            }
            #ptt-button.holding {
                background: #23A55A;
                color: #FFFFFF;
                transform: scale(1.04);
                box-shadow: 0 0 20px rgba(35, 165, 90, 0.55);
            }
            #ptt-button .mic-on-icon { display: none; }
            #ptt-button.holding .mic-off-icon { display: none; }
            #ptt-button.holding .mic-on-icon { display: block; }

            .lang-btn {
                height: 52px;
                min-width: 58px;
                padding: 0 18px;
                margin: 0 4px;
                background: transparent;
                color: #B5BAC1;
                border: none;
                border-radius: 14px;
                font-size: 14px;
                font-weight: 800;
                cursor: pointer;
                transition: all 0.15s ease;
            }
            .lang-btn:hover {
                background: #2B2D31;
                color: #DBDEE1;
            }
            .lang-btn.active {
                background: #FFFFFF;
                color: #0D0D0D;
                box-shadow: 0 3px 10px rgba(0, 0, 0, 0.25);
            }

            .hangup-btn {
                width: 78px;
                height: 68px;
                background: #DA373C;
                color: #FFFFFF;
                border: none;
                border-radius: 20px;
                cursor: pointer;
                display: flex;
                align-items: center;
                justify-content: center;
                box-shadow: 0 12px 30px rgba(218, 55, 60, 0.35);
                transition: all 0.15s ease;
                outline: none;
            }
            .hangup-btn:hover {
                background: #A12828;
                transform: scale(1.04);
            }
            .hangup-btn:active {
                transform: scale(0.96);
            }
        `;
        document.head.appendChild(style);

        let overlay = document.createElement('div');
        overlay.id = 'tuzi-teach-overlay';
        overlay.innerHTML = `
            <!-- Tombol Burger di Pojok Kiri Atas -->
            <button id="tuzi-burger-btn" title="Buka Menu">
                <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round">
                    <line x1="3" y1="6" x2="21" y2="6"></line>
                    <line x1="3" y1="12" x2="21" y2="12"></line>
                    <line x1="3" y1="18" x2="21" y2="18"></line>
                </svg>
            </button>

            <!-- Sidebar Menu (Putih & Hitam ala Gemini) -->
            <div id="tuzi-sidebar">
                <div class="sidebar-header">
                    <div class="sidebar-brand">
                        <svg width="22" height="22" viewBox="0 0 24 24" fill="currentColor">
                            <path d="M12 2L14.8 9.2L22 12L14.8 14.8L12 22L9.2 14.8L2 12L9.2 9.2L12 2Z"/>
                        </svg>
                        <span>TUZI</span>
                    </div>
                    <button class="sidebar-collapse-btn" id="close-sidebar-btn" title="Tutup Menu">
                        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <rect x="3" y="3" width="18" height="18" rx="4"></rect>
                            <line x1="9" y1="3" x2="9" y2="21"></line>
                        </svg>
                    </button>
                </div>

                <!-- Saklar Segmented: Chat | Live -->
                <div class="mode-switch-pill">
                    <button class="mode-tab-btn" id="tab-btn-chat">Chat</button>
                    <button class="mode-tab-btn active" id="tab-btn-live">
                        <span>Live</span>
                        <span class="live-badge">VOICE</span>
                    </button>
                </div>

                <!-- Menu Navigasi Sidebar -->
                <div class="sidebar-menu-list">
                    <button class="sidebar-item" id="menu-new-chat">
                        <svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                            <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"></path>
                            <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"></path>
                        </svg>
                        <span>New chat</span>
                    </button>

                    <button class="sidebar-item" id="menu-search-chat">
                        <svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                            <circle cx="11" cy="11" r="8"></circle>
                            <line x1="21" y1="21" x2="16.65" y2="16.65"></line>
                        </svg>
                        <span>Search chats</span>
                    </button>

                    <div class="sidebar-section-label">Language Target</div>
                    <button class="sidebar-item sidebar-lang-shortcut" data-lang="en-US">
                        <span>🇺🇸 &nbsp;English Practice</span>
                    </button>
                    <button class="sidebar-item sidebar-lang-shortcut" data-lang="ja-JP">
                        <span>🇯🇵 &nbsp;Japanese Practice</span>
                    </button>
                    <button class="sidebar-item sidebar-lang-shortcut" data-lang="id-ID">
                        <span>🇮🇩 &nbsp;Indonesian Practice</span>
                    </button>
                </div>
            </div>

            <!-- Tampilan Chatbot (Muncul saat Tab 'Chat' dipilih) -->
            <div id="tuzi-chat-view">
                <div class="chat-top-bar">
                    <div style="width: 44px;"></div>
                    <div class="chat-top-title">● TUZI CHATBOT TUTOR</div>
                    <button class="hangup-btn" id="exit-teach-btn-chat" style="width: 52px; height: 42px; border-radius: 12px;" title="Akhiri Sesi Belajar">
                        <svg width="22" height="22" viewBox="0 0 24 24" fill="currentColor">
                            <path d="M12 9c-1.6 0-3.15.25-4.6.72v3.1c0 .39-.23.74-.56.9-.98.49-1.87 1.12-2.66 1.85-.18.18-.43.28-.7.28-.28 0-.53-.11-.71-.29L.29 13.08c-.18-.17-.29-.42-.29-.7 0-.28.11-.53.29-.71C3.34 8.78 7.46 7 12 7s8.66 1.78 11.71 4.67c.18.18.29.43.29.71 0 .28-.11.53-.29.71l-2.48 2.48c-.18.18-.43.29-.71.29-.27 0-.52-.11-.7-.28-.79-.74-1.69-1.36-2.67-1.85-.33-.16-.56-.5-.56-.9v-3.1C15.15 9.25 13.6 9 12 9z"/>
                        </svg>
                    </button>
                </div>

                <div id="tuzi-chat-messages">
                    <div class="chat-bubble-row bot">
                        <div class="chat-bubble">Halo Zak! Ketik kalimat dalam bahasa yang ingin kamu latih di bawah ini, nanti aku bantu koreksi dan balas ya.</div>
                    </div>
                </div>

                <div class="chat-input-bar">
                    <input type="text" id="tuzi-chat-input" placeholder="Ketik pesan ke Tuzi..." autocomplete="off" />
                    <button id="tuzi-chat-send" title="Kirim Pesan">
                        <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor">
                            <path d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z"/>
                        </svg>
                    </button>
                </div>
            </div>

            <!-- Discord Call Bottom Bar (Muncul saat Tab 'Live' dipilih) -->
            <div class="discord-call-wrapper">
                <!-- Dock Kiri: Mic Hold to Speak -->
                <div class="discord-dock">
                    <button id="ptt-button" title="Tahan untuk bicara">
                        <svg class="mic-off-icon" width="24" height="24" viewBox="0 0 24 24" fill="currentColor">
                            <path d="M19 11h-1.7c0 .74-.16 1.43-.43 2.05l1.23 1.23c.56-.98.9-2.09.9-3.28zm-4.02.17c0-.06.02-.11.02-.17V5c0-1.66-1.34-3-3-3S9 3.34 9 5v.18l5.98 5.99zM4.27 3L3 4.27l6.01 6.01V11c0 1.66 1.33 3 2.99 3 .22 0 .44-.03.65-.08l1.66 1.66c-.71.33-1.5.52-2.31.52-2.76 0-5.3-2.1-5.3-5.1H5c0 3.41 2.72 6.23 6 6.72V21h2v-3.28c.91-.13 1.77-.45 2.54-.9L19.73 21 21 19.73 4.27 3z"/>
                        </svg>
                        <svg class="mic-on-icon" width="24" height="24" viewBox="0 0 24 24" fill="currentColor">
                            <path d="M12 14c1.66 0 3-1.34 3-3V5c0-1.66-1.34-3-3-3S9 3.34 9 5v6c0 1.66 1.34 3 3 3zm5.91-3c-.49 0-.9.36-.98.85C16.52 14.2 14.47 16 12 16s-4.52-1.8-4.93-4.15c-.08-.49-.49-.85-.98-.85-.61 0-1.09.54-1 1.14.49 3 2.89 5.35 5.91 5.78V20c0 .55.45 1 1 1s1-.45 1-1v-2.08c3.02-.43 5.42-2.78 5.91-5.78.1-.6-.39-1.14-1-1.14z"/>
                        </svg>
                        <span id="ptt-status">HOLD TO SPEAK</span>
                    </button>
                </div>

                <!-- Dock Tengah: Pilihan Bahasa -->
                <div class="discord-dock">
                    <button class="lang-btn active" data-lang="en-US">EN</button>
                    <button class="lang-btn" data-lang="ja-JP">JA</button>
                    <button class="lang-btn" data-lang="id-ID">ID</button>
                </div>

                <!-- Tombol Kanan: Hang-up / Keluar -->
                <button class="hangup-btn" id="exit-teach-btn" title="Akhiri Sesi Belajar">
                    <svg width="32" height="32" viewBox="0 0 24 24" fill="currentColor">
                        <path d="M12 9c-1.6 0-3.15.25-4.6.72v3.1c0 .39-.23.74-.56.9-.98.49-1.87 1.12-2.66 1.85-.18.18-.43.28-.7.28-.28 0-.53-.11-.71-.29L.29 13.08c-.18-.17-.29-.42-.29-.7 0-.28.11-.53.29-.71C3.34 8.78 7.46 7 12 7s8.66 1.78 11.71 4.67c.18.18.29.43.29.71 0 .28-.11.53-.29.71l-2.48 2.48c-.18.18-.43.29-.71.29-.27 0-.52-.11-.7-.28-.79-.74-1.69-1.36-2.67-1.85-.33-.16-.56-.5-.56-.9v-3.1C15.15 9.25 13.6 9 12 9z"/>
                    </svg>
                </button>
            </div>
        `;
        document.body.appendChild(overlay);

        // --- LOGIKA SIDEBAR BURGER & SWITCH MODE (CHAT / LIVE) ---
        let sidebar = document.getElementById('tuzi-sidebar');
        let burgerBtn = document.getElementById('tuzi-burger-btn');
        let closeSidebarBtn = document.getElementById('close-sidebar-btn');
        let tabChat = document.getElementById('tab-btn-chat');
        let tabLive = document.getElementById('tab-btn-live');
        let chatMessages = document.getElementById('tuzi-chat-messages');
        let chatInput = document.getElementById('tuzi-chat-input');
        let chatSend = document.getElementById('tuzi-chat-send');

        burgerBtn.onclick = () => sidebar.classList.add('open');
        closeSidebarBtn.onclick = () => sidebar.classList.remove('open');

        function switchSubMode(mode) {
            if (mode === 'chat') {
                tabChat.classList.add('active');
                tabLive.classList.remove('active');
                document.body.classList.add('chat-tab-open');
                if (window.pyBridge) window.pyBridge.start_ptt('MODE:CHAT');
                setTimeout(() => chatInput.focus(), 100);
            } else {
                tabLive.classList.add('active');
                tabChat.classList.remove('active');
                document.body.classList.remove('chat-tab-open');
                if (window.pyBridge) window.pyBridge.start_ptt('MODE:LIVE');
            }
            sidebar.classList.remove('open');
        }

        tabChat.onclick = () => switchSubMode('chat');
        tabLive.onclick = () => switchSubMode('live');

        // Tombol New Chat di Sidebar
        document.getElementById('menu-new-chat').onclick = () => {
            chatMessages.innerHTML = `
                <div class="chat-bubble-row bot">
                    <div class="chat-bubble">Sesi chat baru dimulai! Silakan ketik kalimat yang ingin kamu latih.</div>
                </div>
            `;
            switchSubMode('chat');
        };

        // Tombol Search Chats di Sidebar
        document.getElementById('menu-search-chat').onclick = () => {
            switchSubMode('chat');
            chatInput.focus();
        };

        // Fungsi Menambahkan Balon Chat
        window.appendTeachChatBubble = function(sender, text) {
            if (!text || !text.trim()) return;
            let row = document.createElement('div');
            row.className = 'chat-bubble-row ' + sender;
            let bubble = document.createElement('div');
            bubble.className = 'chat-bubble';
            bubble.innerText = text;
            row.appendChild(bubble);
            chatMessages.appendChild(row);
            chatMessages.scrollTop = chatMessages.scrollHeight;
        };

        function sendChatMessage() {
            let text = chatInput.value.trim();
            if (!text) return;
            window.appendTeachChatBubble('user', text);
            chatInput.value = '';
            if (window.pyBridge) {
                window.pyBridge.start_ptt('CHAT:' + text);
            }
        }

        chatSend.onclick = sendChatMessage;
        chatInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') sendChatMessage();
        });

        // Tangkap balasan Tuzi dari setSubtitle agar otomatis muncul juga di balon Chatbot
        const origSetSubtitle = window.setSubtitle;
        window.setSubtitle = function(htmlContent) {
            if (origSetSubtitle) origSetSubtitle(htmlContent);
            if (
                document.body.classList.contains('teach-mode-active') &&
                htmlContent &&
                htmlContent.trim() !== '' &&
                !htmlContent.startsWith('Mode Belajar Aktif')
            ) {
                window.appendTeachChatBubble('bot', htmlContent);
            }
        };

        // --- LOGIKA PEMILIH BAHASA & HOLD TO SPEAK ---
        window.currentTeachLang = 'en-US';
        function setLanguage(lang) {
            window.currentTeachLang = lang;
            document.querySelectorAll('.lang-btn').forEach(b => {
                b.classList.toggle('active', b.getAttribute('data-lang') === lang);
            });
        }

        document.querySelectorAll('.lang-btn').forEach(btn => {
            btn.addEventListener('click', () => setLanguage(btn.getAttribute('data-lang')));
        });
        document.querySelectorAll('.sidebar-lang-shortcut').forEach(btn => {
            btn.addEventListener('click', () => {
                setLanguage(btn.getAttribute('data-lang'));
                sidebar.classList.remove('open');
            });
        });

        document.getElementById('exit-teach-btn').addEventListener('click', () => {
            if (window.pyBridge) window.pyBridge.exit_teach_ui();
        });
        document.getElementById('exit-teach-btn-chat').addEventListener('click', () => {
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
                window.camOffsetX = 0;
                window.camOffsetY = 230;
                window.camZoom = 1.45;
            } else {
                document.body.classList.remove('teach-mode-active');
                document.body.classList.remove('chat-tab-open');
                sidebar.classList.remove('open');
                window.camOffsetX = 0;
                window.camOffsetY = 0;
                window.camZoom = 1.0;
            }
            setTimeout(() => {
                if (window.updateModelLayout) window.updateModelLayout();
            }, 60);
        };
    })();
    """