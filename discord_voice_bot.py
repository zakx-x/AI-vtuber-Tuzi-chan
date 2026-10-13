import asyncio
import audioop
import logging
import os
import re
import shutil
import threading
import time
import discord
from discord.ext import commands, voice_recv
from discord.ext.voice_recv import AudioSink, VoiceData
import discord.opus
import speech_recognition as sr
import config

logging.getLogger("discord.ext.voice_recv").setLevel(logging.ERROR)
logging.getLogger("discord.voice_state").setLevel(logging.WARNING)
logging.getLogger("discord.player").setLevel(logging.ERROR)

_original_opus_decode = discord.opus.Decoder.decode

def _safe_opus_decode(self, data, fec=False):
    try: return _original_opus_decode(self, data, fec=fec)
    except discord.opus.OpusError: return b"\x00" * 3840

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

# [KUNCI UTAMA] Antrean menuju otak di run_tuzi.py
main_input_queue = None

def is_device_muted() -> bool: return _is_device_muted
def set_device_mute(muted: bool):
    global _is_device_muted
    _is_device_muted = muted

def sanitize_reply_output(text: str) -> str:
    cleaned = text.strip()
    cleaned = re.sub(r"^(?:<@!?\d+>|@\w+|@\d+)\s*", "", cleaned, flags=re.IGNORECASE)
    emoji_pattern = re.compile(r"[\U00010000-\U0010ffff\u2600-\u26ff\u2700-\u27bf\u2b50\u2b55\u200d\ufe0f]+", flags=re.UNICODE)
    return emoji_pattern.sub("", cleaned).strip()

async def play_audio_to_vc_async(audio_path: str):
    voice_client = None
    for guild in bot.guilds:
        if guild.voice_client and guild.voice_client.is_connected():
            voice_client = guild.voice_client
            break
    if not voice_client or not voice_client.is_connected(): return
    if voice_client.is_playing(): voice_client.stop()
        
    playback_done = asyncio.Event()
    def after_done(error):
        if bot_event_loop and not bot_event_loop.is_closed():
            bot_event_loop.call_soon_threadsafe(playback_done.set)
        try:
            if os.path.exists(audio_path): os.remove(audio_path)
        except Exception: pass
            
    ffmpeg_options = {"options": '-vn -filter:a "volume=1.2,aresample=48000:first_pts=0" -ac 2 -ar 48000'}
    audio_source = discord.FFmpegPCMAudio(audio_path, executable=FFMPEG_PATH, **ffmpeg_options)
    voice_client.play(audio_source, after=after_done)
    await playback_done.wait()

def play_audio_file_to_vc_sync(audio_path: str):
    global bot_event_loop, is_bot_speaking
    if not bot_event_loop or not bot.is_ready(): return
    is_bot_speaking = True
    future = asyncio.run_coroutine_threadsafe(play_audio_to_vc_async(audio_path), bot_event_loop)
    try: future.result(timeout=30)
    except Exception: pass
    finally: is_bot_speaking = False

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

    def wants_opus(self) -> bool: return False

    def write(self, user, data: VoiceData):
        if user is None or getattr(user, "bot", False) or is_bot_speaking: return
        pcm = data.pcm
        if not pcm: return
        uid = user.id
        self.user_map[uid] = user
        if uid not in self.buffers: self.buffers[uid] = bytearray()
        self.buffers[uid].extend(pcm)
        self.last_seen[uid] = time.time()

    def _monitor_silence_loop(self):
        while self.running:
            time.sleep(0.08)
            now = time.time()
            users_to_process = [uid for uid, last_time in list(self.last_seen.items()) if now - last_time > 0.85]
            for uid in users_to_process:
                raw_bytes = bytes(self.buffers.pop(uid, b""))
                user = self.user_map.pop(uid, None)
                self.last_seen.pop(uid, None)
                if not raw_bytes or not user or len(raw_bytes) < 48000 * 2 * 2 * 0.4: continue
                try:
                    if audioop.rms(raw_bytes, 2) < 300: continue
                except Exception: pass
                threading.Thread(target=self._transcribe_and_dispatch, args=(user, raw_bytes), daemon=True).start()

    def _transcribe_and_dispatch(self, user, raw_pcm):
        try:
            mono_pcm = audioop.tomono(raw_pcm, 2, 0.5, 0.5)
            audio_data = sr.AudioData(mono_pcm, 48000, 2)
            text = self.recognizer.recognize_google(audio_data, language=getattr(config, "STT_LANGUAGE", "id-ID"))
            if text and text.strip() and self.on_speech_callback and self.loop:
                asyncio.run_coroutine_threadsafe(self.on_speech_callback(user, text.strip()), self.loop)
        except Exception: pass

    def cleanup(self):
        self.running = False
        self.buffers.clear()
        self.user_map.clear()
        self.last_seen.clear()
        super().cleanup()

async def process_and_speak_vc(user, user_text: str):
    if not user_text.strip(): return
    lower_text = user_text.lower()
    
    if any(k in lower_text for k in ["bicara di laptop", "unmute device"]):
        set_device_mute(False); return
    if any(k in lower_text for k in ["bicara di discord saja", "mute device"]):
        set_device_mute(True); return
    
    # [DIUBAH]: Melempar teks suara Discord langsung ke Otak run_tuzi.py
    if main_input_queue:
        main_input_queue.put(f"[DISCORD_VC] Pengguna {user.display_name} bertanya: \"{user_text}\"")

@bot.event
async def on_ready():
    global bot_event_loop
    bot_event_loop = asyncio.get_running_loop()

@bot.event
async def on_message(message: discord.Message):
    if message.author == bot.user: return
    await bot.process_commands(message)
    
    is_tagged = bot.user.mentioned_in(message) or (message.reference and message.reference.resolved and getattr(message.reference.resolved, "author", None) == bot.user)
    if is_tagged and not message.content.startswith(getattr(config, "DISCORD_COMMAND_PREFIX", "!")):
        clean_text = message.clean_content.replace(f"@{bot.user.display_name}", "").strip() or "halo"
        
        # [DIUBAH]: Melempar chat Teks Discord langsung ke Otak run_tuzi.py
        if main_input_queue:
            main_input_queue.put(f"[DISCORD_TEXT:{message.channel.id}] {message.author.display_name} chat: \"{clean_text}\"")

def send_reply_to_channel_sync(channel_id: int, text: str):
    global bot_event_loop
    if not bot_event_loop: return
    channel = bot.get_channel(channel_id)
    if channel:
        asyncio.run_coroutine_threadsafe(channel.send(sanitize_reply_output(text)), bot_event_loop)

async def async_trigger_join_vc() -> tuple[bool, str, str]:
    global bot_event_loop
    if not bot.guilds: return False, "NOT_FOUND", "Bot belum ada di server."
    target_channel, target_guild, owner_found_name = None, None, ""
    
    for guild in bot.guilds:
        for vc in guild.voice_channels:
            for member in vc.members:
                names = [member.name.lower(), (member.display_name or "").lower(), (member.global_name or "").lower()]
                if OWNER_USERNAME in names or any(OWNER_USERNAME in n for n in names) or any("zak" in n for n in names):
                    target_channel, target_guild, owner_found_name = vc, guild, member.display_name
                    break
            if target_channel: break
        if target_channel: break
            
    if not target_channel: return False, "OWNER_NOT_IN_VC", f"{OWNER_USERNAME} tidak di VC."
        
    try:
        voice_client = target_guild.voice_client
        if not voice_client or not voice_client.is_connected():
            voice_client = await target_channel.connect(cls=voice_recv.VoiceRecvClient)
        else: await voice_client.move_to(target_channel)
            
        if isinstance(voice_client, voice_recv.VoiceRecvClient) and not voice_client.is_listening():
            voice_client.listen(CustomDiscordVoiceSink(bot_event_loop, process_and_speak_vc))
                
        set_device_mute(True)
        return True, target_channel.name, owner_found_name
    except Exception as e: return False, "ERROR", str(e)

async def async_trigger_leave_vc() -> bool:
    set_device_mute(False)
    for guild in bot.guilds:
        if guild.voice_client and guild.voice_client.is_connected():
            if isinstance(guild.voice_client, voice_recv.VoiceRecvClient): guild.voice_client.stop_listening()
            await guild.voice_client.disconnect()
            return True
    return False

def trigger_join_from_voice():
    if not bot.is_ready(): return False, "BOT_OFFLINE", "Offline."
    try: return asyncio.run_coroutine_threadsafe(async_trigger_join_vc(), bot_event_loop).result(10)
    except Exception as e: return False, "ERROR", str(e)

def trigger_leave_from_voice():
    if not bot.is_ready(): return False
    try: return asyncio.run_coroutine_threadsafe(async_trigger_leave_vc(), bot_event_loop).result(10)
    except Exception: return False

def trigger_tag_user_sync(target_nickname: str) -> tuple[bool, str]:
    if not bot.guilds or not bot_event_loop: return False, "Belum terhubung."
    target_member, target_channel, master_id = None, None, None
    for guild in bot.guilds:
        for ch in guild.text_channels:
            if ch.permissions_for(guild.me).send_messages: target_channel = ch; break
        for member in guild.members:
            if member.bot: continue
            names = [member.name.lower(), (member.display_name or "").lower(), (member.global_name or "").lower()]
            if target_nickname.lower() in names or any(target_nickname.lower() in n for n in names): target_member = member
            if OWNER_USERNAME in names or any(OWNER_USERNAME in n for n in names): master_id = member.id
        if target_channel and target_member: break
            
    if not target_member: return False, f"Maaf, {target_nickname} tidak ketemu."
    master_mention = f"<@{master_id}>" if master_id else f"@{OWNER_USERNAME}"
    async def _send(): await target_channel.send(f"{target_member.mention}, kamu dipanggil sama {master_mention} nih!")
    if bot.is_ready():
        asyncio.run_coroutine_threadsafe(_send(), bot_event_loop)
        return True, f"Berhasil men-tag {target_nickname}"
    return False, "Belum siap."

def start_discord_bot_thread():
    token = getattr(config, "DISCORD_BOT_TOKEN", "").strip()
    if not token or token.startswith("MASUKKAN"): return
    def _run():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try: loop.run_until_complete(bot.start(token))
        except Exception: pass
    threading.Thread(target=_run, daemon=True).start()