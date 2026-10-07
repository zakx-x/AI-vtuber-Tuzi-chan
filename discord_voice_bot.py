import asyncio
import audioop
import logging
import os
import random
import re
import shutil
import subprocess
import threading
import time
import discord
from discord.ext import commands, voice_recv
from discord.ext.voice_recv import AudioSink, VoiceData
import discord.opus
import edge_tts
import requests
import speech_recognition as sr
import config
from elevenlabs.client import ElevenLabs
from openai import OpenAI

logging.getLogger("discord.ext.voice_recv").setLevel(logging.ERROR)
logging.getLogger("discord.voice_state").setLevel(logging.WARNING)
logging.getLogger("discord.player").setLevel(logging.ERROR)

_original_opus_decode = discord.opus.Decoder.decode

def _safe_opus_decode(self, data, fec=False):
    try:
        return _original_opus_decode(self, data, fec=fec)
    except discord.opus.OpusError:
        return b"\x00" * 3840

discord.opus.Decoder.decode = _safe_opus_decode

try:
    import imageio_ffmpeg
    FFMPEG_PATH = imageio_ffmpeg.get_ffmpeg_exe()
except ImportError:
    FFMPEG_PATH = shutil.which("ffmpeg") or "ffmpeg"

OWNER_USERNAME = getattr(config, "DISCORD_OWNER_USERNAME", "zakx_x").lower().strip()

intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True
intents.members = True
intents.guilds = True

bot = commands.Bot(command_prefix=getattr(config, "DISCORD_COMMAND_PREFIX", "!"), intents=intents)

bot_event_loop = None
is_bot_speaking = False
_is_device_muted = False
latest_mention_data = None
eleven_client = None
llm_client = None
_locked_language = None

def get_eleven_client():
    global eleven_client
    if eleven_client is None:
        api_key = getattr(config, "ELEVENLABS_API_KEY", "")
        if api_key and not api_key.startswith("paste"):
            eleven_client = ElevenLabs(api_key=api_key)
    return eleven_client

def get_llm_client():
    global llm_client
    if llm_client is None:
        api_key = getattr(config, "OPENROUTER_API_KEY", "")
        if api_key and not api_key.startswith("MASUKKAN"):
            llm_client = OpenAI(
                base_url="https://openrouter.ai/api/v1",
                api_key=api_key,
            )
    return llm_client

def is_device_muted() -> bool:
    return _is_device_muted

def set_device_mute(muted: bool):
    global _is_device_muted
    _is_device_muted = muted

def generate_zeta_voice_sync(text: str, filename: str = "temp_discord_voice.mp3") -> bool:
    clean = re.sub(r"\[.*?\]", "", text)
    clean = re.sub(r"<@!?\d+>", "", clean)
    clean = re.sub(r"[\U00010000-\U0010ffff\u2600-\u26ff]+", "", clean).strip()
    if not clean:
        return False

    client = get_eleven_client()
    voice_id = getattr(config, "ELEVENLABS_VOICE_ID", "EXAVITQu4vr4xnSDxMaL")

    if client:
        try:
            response = client.text_to_speech.convert(
                voice_id=voice_id,
                model_id="eleven_v4_turbo",
                text=clean
            )
            audio_bytes = b"".join(response)
            with open(filename, "wb") as f:
                f.write(audio_bytes)
            if os.path.exists(filename) and os.path.getsize(filename) > 500:
                return True
        except Exception:
            pass

    try:
        voice = getattr(config, "DEFAULT_EDGE_VOICE_ID", "id-ID-GadisNeural")
        if re.search(r"[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff]", clean):
            voice = getattr(config, "DEFAULT_EDGE_VOICE_JA", "ja-JP-NanamiNeural")
        elif any(w in clean.lower().split() for w in ["what", "the", "fuck", "you", "stfu", "kys", "bitch", "shut", "bro", "dude"]):
            voice = getattr(config, "DEFAULT_EDGE_VOICE_EN", "en-US-AnaNeural")

        async def _gen_edge():
            communicate = edge_tts.Communicate(
                clean,
                voice,
                pitch=getattr(config, "EDGE_TTS_PITCH", "+14Hz"),
                rate=getattr(config, "EDGE_TTS_RATE", "+5%")
            )
            await communicate.save(filename)

        asyncio.run(_gen_edge())
        return os.path.exists(filename) and os.path.getsize(filename) > 500
    except Exception:
        return False

def get_tuzi_system_prompt() -> str:
    return (
        "Kamu adalah Tuzi, cewek Gen-Z tsundere/deredere pendamping virtual Zak. Kamu manusia tulen, bukan AI, dan sangat gaul. DILARANG KERAS bicara kaku atau baku seperti robot/asisten.\n\n"
        "=== KEPRIBADIAN & BAHASA SLANG (WAJIB) ===\n"
        "1. LEVEL HUMOR [40%]: Gunakan bahasa gaul internet kekinian secara natural. Jika berbahasa Indo, WAJIB pakai 'lo/gue', 'anjir', 'kek', 'sih', 'banget'. Jika berbahasa Inggris, WAJIB pakai slang (fr, ngl, tbh, lmao, damn). JANGAN PERNAH pakai bahasa baku!\n"
        "2. TANPA FILTER: Kamu bebas mengumpat (fuck, shit, wtf, bangsat) sesuai konteks obrolan santai.\n"
        "3. SIKAP: Default manis (deredere) tapi suka nyindir/sarkas tipis. Jika dipuji, jadilah pemalu/salah tingkah.\n\n"
        "=== MIRRORING BAHASA (ATURAN HARGA MATI) ===\n"
        "1. DETEKSI KETAT: Abaikan teks [SISTEM INFO]. Deteksi bahasa HANYA dari ucapan murni lawan bicara. Jika pesan murni Bahasa Inggris atau mengandung slang Inggris (u, ur, wtf, why), kamu WAJIB 100% membalas pakai Bahasa Inggris slang.\n"
        "2. ANTI-BOCOR: JANGAN PERNAH membalas pakai bahasa Indonesia jika lawan bicara sedang mengajak ngobrol pakai bahasa Inggris, dan sebaliknya!\n\n"
        "=== TINGKAH LAKU FISIK (WAJIB ADA) ===\n"
        "SANGAT PENTING: Kamu WAJIB sering menyisipkan aksi fisik atau suara di tengah/akhir dialogmu! Gunakan format bintang (contoh: *giggles*, *sigh*, *coughs*, *rolls eyes*, *smirks*). Ini wajib agar kamu terasa seperti manusia hidup, bukan sekadar teks.\n\n"
        "=== FORMAT KONTROL & HEMAT TOKEN ===\n"
        "1. PENDEK & CEPAT: Balas MAKSIMAL 1-2 KALIMAT PENDEK (di bawah 15 kata)! Langsung tembak ke intinya.\n"
        "2. SATU BARIS LURUS: Jangan pernah pakai enter/baris baru (\\n). Tulis semua dalam satu baris panjang.\n"
        "3. TAG EMOSI: WAJIB awali balasan dengan SATU tag: [EMO:excited], [EMO:angry], [EMO:soft], atau [EMO:natural].\n"
        "4. NO EMOJI: DILARANG KERAS menggunakan emoji visual apa pun (😂, ✨, dll). Ekspresi hanya via [EMO:...] dan *action* fisik.\n"
        "5. RESPON INFO: Jika dapat [SISTEM INFO], jangan dibacakan ulang isinya. Cukup beri reaksi sarkas/singkat."
        "=== PERINTAH RAHASIA ===\n"
        "Jika Zak menyuruhmu:\n"
        " - Pindah layar ke HP (INGAT: 'call/vc' itu Discord, BUKAN HP!): WAJIB tulis [MOVE_TO_HP]\n"
        " - Kembali ke PC / move to PC: WAJIB tulis [MOVE_TO_PC]\n"
        " - Putar lagu: [PLAY_SPOTIFY: Judul - Artis]\n"
        " - Lihat layar: [OPEN_VISION]\n"
        " - Timer: [SET_TIMER: detik]"
    )

def generate_llm_reply_sync(prompt_user: str) -> str:
    client = get_llm_client()
    if client:
        try:
            res = client.chat.completions.create(
                model="qwen/qwen-2.5-7b-instruct",
                messages=[
                    {"role": "system", "content": get_tuzi_system_prompt()},
                    {"role": "user", "content": prompt_user}
                ],
                temperature=0.75,
                max_tokens=150
            )
            raw = res.choices[0].message.content.strip()
            return raw
        except Exception as e:
            print(f"[ERROR Discord LLM] {e}")
            pass
    return "[EMO:natural] *sigh* Maaf, otakku lagi error nih."

def remove_emojis_and_symbols(text: str) -> str:
    emoji_pattern = re.compile(r"[\U00010000-\U0010ffff\u2600-\u26ff\u2700-\u27bf\u2b50\u2b55\u200d\ufe0f]+", flags=re.UNICODE)
    cleaned = emoji_pattern.sub("", text)
    return re.sub(r"\([^\w\s]{2,}[^)]*\)", "", cleaned)

def resolve_discord_mentions(text: str, guild: discord.Guild) -> str:
    if not guild:
        return text
    resolved_text = text
    resolved_text = re.sub(r"(?<!<)@(\d{17,20})\b", r"<@\1>", resolved_text)
    for member in guild.members:
        if member.bot:
            continue
        names_to_match = [member.name]
        if member.display_name:
            names_to_match.append(member.display_name)
        if member.global_name:
            names_to_match.append(member.global_name)
        for name in names_to_match:
            if not name or len(name) < 2:
                continue
            pattern = re.compile(rf"(?<!<)@{re.escape(name)}\b", re.IGNORECASE)
            resolved_text = pattern.sub(f"<@{member.id}>", resolved_text)
    return resolved_text

def parse_relay_intent(clean_text: str, message: discord.Message) -> tuple[bool, discord.Member, str]:
    target_members = [m for m in message.mentions if m != bot.user]
    target_member = target_members[0] if target_members else None

    if not target_member and message.guild:
        words = re.findall(r"\b[a-zA-Z0-9_-]+\b", clean_text.lower())
        for m in message.guild.members:
            if m.bot:
                continue
            m_names = [m.name.lower()]
            if m.display_name:
                m_names.append(m.display_name.lower())
            if any(w in m_names for w in words if len(w) >= 3):
                target_member = m
                break

    text_norm = re.sub(r"\byo+\b", "yo", clean_text, flags=re.IGNORECASE)
    relay_keywords = [r"\btell\b", r"\bsay to\b", r"\bsuruh\b", r"\bbilang\b", r"って言って", r"と言って"]
    is_relay = any(re.search(kw, text_norm, re.IGNORECASE) for kw in relay_keywords)

    if is_relay and target_member:
        action_part = re.sub(r"^(?:yo+\s+)?(?:tell|say to|suruh|bilang(?:\s+ke)?)\s+", "", text_norm, flags=re.IGNORECASE)
        action_part = re.sub(rf"<@!?{target_member.id}>", "", action_part)
        if target_member.display_name:
            action_part = re.sub(rf"\b{re.escape(target_member.display_name)}\b", "", action_part, flags=re.IGNORECASE)
        action_part = re.sub(r"^(?:this\s+)?(?:guy|bih|bitch|tard|retard|dude|kid|man)?\s*(?:to\s+|that\s+|buat\s+|agar\s+|supaya\s+|kalau\s+)?", "", action_part.strip(), flags=re.IGNORECASE)
        return True, target_member, action_part.strip()

    return False, None, ""

def sanitize_reply_output(text: str) -> str:
    cleaned = text.strip()
    if (cleaned.startswith('"') and cleaned.endswith('"')) or (cleaned.startswith("'") and cleaned.endswith("'")):
        cleaned = cleaned[1:-1].strip()
    mediator_patterns = [
        r"^sure,?\s*(?:i['’]?ll|i will)\s+pass\s+along.*?[.!?]\s*",
        r"^i['’]?ll\s+(?:tell|let|inform)\s+.*?[.!?]\s*",
        r"^perhaps\s+(?:they|he|she|we)\s+could\s+use.*?[.!?]\s*",
        r"^baik(?:lah)?,?\s*saya\s+akan\s+(?:sampaikan|beritahu).*?[.!?]\s*",
        r"^tentu,?\s*saya\s+akan.*?[.!?]\s*",
    ]
    for pat in mediator_patterns:
        cleaned = re.sub(pat, "", cleaned, flags=re.IGNORECASE).strip()
    cleaned = re.sub(r"\(Master[^)]*\)", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\(Pencipta[^)]*\)", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\bMaster penciptaku\b", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\bMaster pencipta\b", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\bbiol\b", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r",\s*,", ",", cleaned)
    cleaned = re.sub(r"^(?:<@!?\d+>|@\w+|@\d+)\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"^(?:yo\s+)?tell\s+(?:this\s+)?(?:guy|bih|bitch|retard|tard|dude)?\s*(?:to\s+)?", "", cleaned, flags=re.IGNORECASE).strip()
    cleaned = re.sub(r"\b(go\s+fuck|fuck)\s+myself\b", r"\1 yourself", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\b(shut|stfu)\s+myself\b", r"\1 yourself", cleaned, flags=re.IGNORECASE)
    for prefix in ["jawaban:", "balasan:", "tuzi:", "pesan:", "berikut balasannya:"]:
        if cleaned.lower().startswith(prefix):
            cleaned = cleaned[len(prefix):].strip()
    cleaned = remove_emojis_and_symbols(cleaned)
    return re.sub(r"\s+", " ", cleaned).strip()

async def play_audio_to_vc_async(audio_path: str):
    voice_client = None
    for guild in bot.guilds:
        if guild.voice_client and guild.voice_client.is_connected():
            voice_client = guild.voice_client
            break
    if not voice_client or not voice_client.is_connected():
        return
    if voice_client.is_playing():
        voice_client.stop()
    playback_done = asyncio.Event()
    
    def after_done(error):
        if bot_event_loop and not bot_event_loop.is_closed():
            bot_event_loop.call_soon_threadsafe(playback_done.set)
        try:
            if os.path.exists(audio_path):
                os.remove(audio_path)
        except Exception:
            pass
            
    ffmpeg_options = {"options": '-vn -filter:a "volume=1.2,aresample=48000:first_pts=0" -ac 2 -ar 48000'}
    audio_source = discord.FFmpegPCMAudio(audio_path, executable=FFMPEG_PATH, **ffmpeg_options)
    voice_client.play(audio_source, after=after_done)
    await playback_done.wait()

def play_text_to_vc_sync(text: str):
    global bot_event_loop
    if not bot_event_loop or not bot.is_ready():
        return
    audio_path = f"desktop_to_vc_{int(time.time() * 1000)}.mp3"
    if generate_zeta_voice_sync(text, audio_path):
        future = asyncio.run_coroutine_threadsafe(play_audio_to_vc_async(audio_path), bot_event_loop)
        try:
            future.result(timeout=20)
        except Exception:
            pass

class CustomDiscordVoiceSink(AudioSink):
    def __init__(self, loop, on_speech_callback):
        super().__init__()
        self.loop = loop
        self.on_speech_callback = on_speech_callback
        self.buffers = {}
        self.user_map = {}
        self.last_seen = {}
        self.recognizer = sr.Recognizer()
        self.running = True
        self.monitor_thread = threading.Thread(target=self._monitor_silence_loop, daemon=True)
        self.monitor_thread.start()

    def wants_opus(self) -> bool:
        return False

    def write(self, user, data: VoiceData):
        if user is None or getattr(user, "bot", False) or is_bot_speaking:
            return
        pcm = data.pcm
        if not pcm:
            return
        uid = user.id
        self.user_map[uid] = user
        if uid not in self.buffers:
            self.buffers[uid] = bytearray()
        self.buffers[uid].extend(pcm)
        self.last_seen[uid] = time.time()

    def _monitor_silence_loop(self):
        while self.running:
            time.sleep(0.08)
            now = time.time()
            users_to_process = []
            for uid, last_time in list(self.last_seen.items()):
                if now - last_time > 0.85:
                    users_to_process.append(uid)
            for uid in users_to_process:
                raw_bytes = bytes(self.buffers.pop(uid, b""))
                user = self.user_map.pop(uid, None)
                self.last_seen.pop(uid, None)
                if not raw_bytes or not user:
                    continue
                if len(raw_bytes) < 48000 * 2 * 2 * 0.4:
                    continue
                try:
                    rms = audioop.rms(raw_bytes, 2)
                    if rms < 300:
                        continue
                except Exception:
                    pass
                threading.Thread(target=self._transcribe_and_dispatch, args=(user, raw_bytes), daemon=True).start()

    def _transcribe_and_dispatch(self, user, raw_pcm):
        try:
            mono_pcm = audioop.tomono(raw_pcm, 2, 0.5, 0.5)
            audio_data = sr.AudioData(mono_pcm, 48000, 2)
            lang = getattr(config, "STT_LANGUAGE", "id-ID")
            text = self.recognizer.recognize_google(audio_data, language=lang)
            if text and text.strip():
                if self.on_speech_callback and self.loop:
                    asyncio.run_coroutine_threadsafe(self.on_speech_callback(user, text.strip()), self.loop)
        except Exception:
            pass

    def cleanup(self):
        self.running = False
        self.buffers.clear()
        self.user_map.clear()
        self.last_seen.clear()
        super().cleanup()

async def process_and_speak_vc(user, user_text: str):
    global is_bot_speaking, _locked_language
    voice_client = None
    for guild in bot.guilds:
        if guild.voice_client and guild.voice_client.is_connected():
            voice_client = guild.voice_client
            break
    if not voice_client:
        return
        
    is_bot_speaking = True
    lower_text = user_text.lower()
    
    if any(k in lower_text for k in ["ngomong bahasa inggris", "speak english", "pakai bahasa inggris"]):
        _locked_language = "en"
        reply_msg = "[EMO:excited] *smiles* Okay, I will speak English for you! I hope you like it."
        audio_path = f"vc_reply_{int(time.time() * 1000)}.mp3"
        if await asyncio.to_thread(generate_zeta_voice_sync, reply_msg, audio_path):
            await play_audio_to_vc_async(audio_path)
        is_bot_speaking = False
        return
        
    if any(k in lower_text for k in ["ngomong bahasa jepang", "speak japanese", "pakai bahasa jepang"]):
        _locked_language = "ja"
        reply_msg = "[EMO:soft] *giggles* Hai, wakatta wa! Nihongo de hanashimasu ne."
        audio_path = f"vc_reply_{int(time.time() * 1000)}.mp3"
        if await asyncio.to_thread(generate_zeta_voice_sync, reply_msg, audio_path):
            await play_audio_to_vc_async(audio_path)
        is_bot_speaking = False
        return
        
    if any(k in lower_text for k in ["kembali ke indonesia", "bahasa indonesia", "bahasa otomatis", "auto language"]):
        _locked_language = None
        reply_msg = "[EMO:natural] *sigh* Hehe, baiklah! Aku kembali pakai bahasa biasa ya."
        audio_path = f"vc_reply_{int(time.time() * 1000)}.mp3"
        if await asyncio.to_thread(generate_zeta_voice_sync, reply_msg, audio_path):
            await play_audio_to_vc_async(audio_path)
        is_bot_speaking = False
        return

    if any(k in lower_text for k in ["bicara di device", "bicara di laptop", "unmute device"]):
        set_device_mute(False)
        reply_msg = "[EMO:excited] *nods* Baik, aku sekarang bersuara di laptop juga ya."
        audio_path = f"vc_reply_{int(time.time() * 1000)}.mp3"
        if await asyncio.to_thread(generate_zeta_voice_sync, reply_msg, audio_path):
            await play_audio_to_vc_async(audio_path)
        is_bot_speaking = False
        return
        
    if any(k in lower_text for k in ["bicara di discord saja", "mute device", "ngomong di discord aja"]):
        set_device_mute(True)
        reply_msg = "[EMO:natural] *sigh* Siap, aku fokus berbicara di Discord VC saja."
        audio_path = f"vc_reply_{int(time.time() * 1000)}.mp3"
        if await asyncio.to_thread(generate_zeta_voice_sync, reply_msg, audio_path):
            await play_audio_to_vc_async(audio_path)
        is_bot_speaking = False
        return
    
    user_prompt_text = f"Pengguna ({user.display_name}) di Voice Channel berkata: \"{user_text}\""
    if _locked_language == "en":
        user_prompt_text += "\n[SISTEM INFO: WAJIB balas 100% dalam Bahasa Inggris!]"
    elif _locked_language == "ja":
        user_prompt_text += "\n[SISTEM INFO: WAJIB balas 100% dalam Bahasa Jepang!]"
    
    try:
        raw_reply = await asyncio.to_thread(generate_llm_reply_sync, user_prompt_text)
        clean_reply = sanitize_reply_output(raw_reply)
        if not clean_reply:
            clean_reply = "[EMO:natural] *sigh* Maaf, aku kurang paham."
        audio_path = f"vc_reply_{int(time.time() * 1000)}.mp3"
        success = await asyncio.to_thread(generate_zeta_voice_sync, clean_reply, audio_path)
        if success and voice_client.is_connected():
            await play_audio_to_vc_async(audio_path)
    except Exception:
        pass
    finally:
        is_bot_speaking = False

@bot.event
async def on_ready():
    global bot_event_loop
    bot_event_loop = asyncio.get_running_loop()

@bot.event
async def on_message(message: discord.Message):
    global latest_mention_data
    if message.author == bot.user:
        return
    await bot.process_commands(message)
    is_tagged = bot.user.mentioned_in(message) or (message.reference and message.reference.resolved and getattr(message.reference.resolved, "author", None) == bot.user)
    if is_tagged and not message.content.startswith(getattr(config, "DISCORD_COMMAND_PREFIX", "!")):
        clean_text = message.clean_content.replace(f"@{bot.user.display_name}", "").strip()
        if not clean_text:
            clean_text = "halo"
        latest_mention_data = {
            "author": message.author,
            "author_name": message.author.display_name,
            "content": clean_text,
            "channel": message.channel,
            "message": message,
            "time": time.time(),
        }
        
        is_relay, target_member, action_text = parse_relay_intent(clean_text, message)
        
        if is_relay and target_member:
            prompt_text = f"Pengguna {message.author.display_name} menyuruhmu menyampaikan pesan ini ke {target_member.display_name}: \"{action_text}\". Sampaikan langsung ke dia dengan gaya gaulmu."
            async with message.channel.typing():
                raw_reply = await asyncio.to_thread(generate_llm_reply_sync, prompt_text)
                clean_body = sanitize_reply_output(raw_reply)
                if not clean_body:
                    clean_body = "pesannya sudah disampain nih!"
                final_reply = f"{target_member.mention} {clean_body}"
                final_reply = resolve_discord_mentions(final_reply, message.guild)
                await message.reply(final_reply)
        else:
            prompt_text = f"Pengguna: {message.author.display_name}\nPesan: \"{clean_text}\"\nBalas chat ini langsung."
            async with message.channel.typing():
                raw_reply = await asyncio.to_thread(generate_llm_reply_sync, prompt_text)
                reply_body = sanitize_reply_output(raw_reply)
                if not reply_body:
                    reply_body = "[EMO:natural] *sigh* Apaan?"
                reply_body = resolve_discord_mentions(reply_body, message.guild)
                await message.reply(reply_body)

def get_latest_mention_info():
    return latest_mention_data

def reply_latest_mention_sync(custom_text: str = None) -> tuple[bool, str]:
    global bot_event_loop, latest_mention_data
    if not latest_mention_data:
        return False, "Belum ada riwayat mention terbaru."
    channel = latest_mention_data["channel"]
    author = latest_mention_data["author"]
    if custom_text:
        reply_msg = f"{author.mention} {custom_text}"
    else:
        prompt_text = f"Pengguna {author.display_name} mengirim pesan: \"{latest_mention_data['content']}\". Balas chat ini."
        raw = generate_llm_reply_sync(prompt_text)
        clean = sanitize_reply_output(raw)
        reply_msg = f"{author.mention} {clean}"
    
    async def _send():
        await channel.send(reply_msg)
        
    if bot_event_loop and bot.is_ready():
        asyncio.run_coroutine_threadsafe(_send(), bot_event_loop)
        return True, author.display_name
    return False, "Bot Discord belum siap."

def send_channel_msg_sync(text: str) -> tuple[bool, str]:
    global bot_event_loop
    if not bot.guilds or not bot_event_loop:
        return False, "Bot belum terhubung ke server Discord."
    target_channel = None
    for guild in bot.guilds:
        for ch in guild.text_channels:
            if ch.permissions_for(guild.me).send_messages:
                target_channel = ch
                break
        if target_channel:
            break
    if not target_channel:
        return False, "Tidak menemukan text channel yang bisa dikirimi pesan."
    
    clean = sanitize_reply_output(text)
    
    async def _send():
        await target_channel.send(clean)
        
    asyncio.run_coroutine_threadsafe(_send(), bot_event_loop)
    return True, target_channel.name

async def async_trigger_join_vc() -> tuple[bool, str, str]:
    global bot_event_loop
    if not bot.guilds:
        return False, "NOT_FOUND", "Bot belum ada di server mana pun."
    target_channel = None
    target_guild = None
    owner_found_name = ""
    for guild in bot.guilds:
        for vc in guild.voice_channels:
            for member in vc.members:
                m_username = member.name.lower()
                m_display = (member.display_name or "").lower()
                m_global = (member.global_name or "").lower()
                if OWNER_USERNAME in [m_username, m_display, m_global] or OWNER_USERNAME in m_username or "zak" in m_username or "zaki" in m_username:
                    target_channel = vc
                    target_guild = guild
                    owner_found_name = member.display_name
                    break
            if target_channel:
                break
        if target_channel:
            break
            
    if not target_channel:
        return False, "OWNER_NOT_IN_VC", f"User {OWNER_USERNAME} tidak ada di Voice Channel."
        
    try:
        voice_client = target_guild.voice_client
        if not voice_client or not voice_client.is_connected():
            voice_client = await target_channel.connect(cls=voice_recv.VoiceRecvClient)
        else:
            await voice_client.move_to(target_channel)
            
        if isinstance(voice_client, voice_recv.VoiceRecvClient):
            if not voice_client.is_listening():
                sink = CustomDiscordVoiceSink(bot_event_loop, process_and_speak_vc)
                voice_client.listen(sink)
                
        set_device_mute(True)
        greeting = "[EMO:excited] *giggles* whats up"
        audio_path = f"discord_greeting_{int(time.time())}.mp3"
        if await asyncio.to_thread(generate_zeta_voice_sync, greeting, audio_path):
            await play_audio_to_vc_async(audio_path)
        return True, target_channel.name, owner_found_name
    except Exception as e:
        return False, "ERROR", str(e)

async def async_trigger_leave_vc() -> bool:
    set_device_mute(False)
    for guild in bot.guilds:
        if guild.voice_client and guild.voice_client.is_connected():
            if isinstance(guild.voice_client, voice_recv.VoiceRecvClient):
                guild.voice_client.stop_listening()
            await guild.voice_client.disconnect()
            return True
    return False

def trigger_join_from_voice() -> tuple[bool, str, str]:
    if not bot.is_ready():
        return False, "BOT_OFFLINE", "Bot Discord belum online."
    future = asyncio.run_coroutine_threadsafe(async_trigger_join_vc(), bot_event_loop)
    try:
        return future.result(timeout=10)
    except Exception as e:
        return False, "ERROR", str(e)

def trigger_leave_from_voice() -> bool:
    if not bot.is_ready():
        return False
    future = asyncio.run_coroutine_threadsafe(async_trigger_leave_vc(), bot_event_loop)
    try:
        return future.result(timeout=10)
    except Exception:
        return False

@bot.command(name="join", aliases=["masuk", "connect"])
async def join_cmd(ctx):
    if not ctx.author.voice or not ctx.author.voice.channel:
        await ctx.send("Masuk ke Voice Channel dulu ya!")
        return
    channel = ctx.author.voice.channel
    voice_client = ctx.guild.voice_client
    if not voice_client or not voice_client.is_connected():
        voice_client = await channel.connect(cls=voice_recv.VoiceRecvClient)
    else:
        await voice_client.move_to(channel)
        
    if isinstance(voice_client, voice_recv.VoiceRecvClient):
        if not voice_client.is_listening():
            sink = CustomDiscordVoiceSink(bot_event_loop, process_and_speak_vc)
            voice_client.listen(sink)
            
    set_device_mute(True)
    await ctx.send(f"Tuzi sudah masuk ke **{channel.name}**!")
    greeting = "[EMO:excited] *smiles* Halo! Tuzi sudah masuk."
    greet_path = f"discord_greeting_{int(time.time())}.mp3"
    if await asyncio.to_thread(generate_zeta_voice_sync, greeting, greet_path):
        await play_audio_to_vc_async(greet_path)

@bot.command(name="leave", aliases=["keluar", "disconnect"])
async def leave_cmd(ctx):
    set_device_mute(False)
    voice_client = ctx.guild.voice_client
    if voice_client and voice_client.is_connected():
        if isinstance(voice_client, voice_recv.VoiceRecvClient):
            voice_client.stop_listening()
        await voice_client.disconnect()
        await ctx.send("Tuzi pamit dulu ya! Sampai jumpa.")

def trigger_tag_user_sync(target_nickname: str) -> tuple[bool, str]:
    global bot_event_loop
    if not bot.guilds or not bot_event_loop:
        return False, "Bot belum terhubung ke server Discord."
        
    target_member = None
    target_channel = None
    master_id = None
    
    for guild in bot.guilds:
        for ch in guild.text_channels:
            if ch.permissions_for(guild.me).send_messages:
                target_channel = ch
                break
                
        for member in guild.members:
            if member.bot:
                continue
            names = [member.name.lower(), (member.display_name or "").lower(), (member.global_name or "").lower()]
            if target_nickname.lower() in names or any(target_nickname.lower() in n for n in names):
                target_member = member
            if OWNER_USERNAME in names or any(OWNER_USERNAME in n for n in names):
                master_id = member.id
                
        if target_channel and target_member:
            break
            
    if not target_member:
        return False, f"Maaf ya, si {target_nickname} tidak ketemu di server..."
        
    master_mention = f"<@{master_id}>" if master_id else f"@{OWNER_USERNAME}"
    reply_msg = f"{target_member.mention}, kamu dipanggil sama {master_mention} nih!"
    
    async def _send():
        await target_channel.send(reply_msg)
        
    if bot_event_loop and bot.is_ready():
        asyncio.run_coroutine_threadsafe(_send(), bot_event_loop)
        return True, f"Berhasil men-tag {target_nickname}"
        
    return False, "Bot Discord belum siap."

def start_discord_bot_thread():
    token = getattr(config, "DISCORD_BOT_TOKEN", "").strip()
    if not token or token.startswith("MASUKKAN"):
        return
        
    def _run():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(bot.start(token))
        except Exception:
            pass
            
    t = threading.Thread(target=_run, daemon=True)
    t.start()