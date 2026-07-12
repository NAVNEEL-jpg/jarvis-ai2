import os
import sys
import pyaudio
import numpy as np
import wave
import time

# ── Add CUDA DLL paths from nvidia packages BEFORE importing faster_whisper ──
# Search ALL site-packages dirs (system, user, and venv) for nvidia DLLs
import site as _site
_sp_dirs = list(getattr(_site, "getsitepackages", lambda: [])())
try:
    _sp_dirs.append(_site.getusersitepackages())
except AttributeError:
    pass
# Also check relative to sys.executable (covers venv when run via system python)
_sp_dirs.append(os.path.join(os.path.dirname(os.path.dirname(sys.executable)),
                             "Lib", "site-packages"))
# And the script's own directory venv
_sp_dirs.append(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             ".venv", "Lib", "site-packages"))

for _sp in dict.fromkeys(_sp_dirs):          # deduplicate, preserve order
    _nvidia_dir = os.path.join(_sp, "nvidia")
    if os.path.isdir(_nvidia_dir):
        for _pkg in os.listdir(_nvidia_dir):
            _bin = os.path.join(_nvidia_dir, _pkg, "bin")
            if os.path.isdir(_bin) and _bin not in os.environ.get("PATH", ""):
                os.environ["PATH"] = _bin + os.pathsep + os.environ.get("PATH", "")
                os.add_dll_directory(_bin)

from openwakeword.model import Model
from openwakeword.utils import download_models
from faster_whisper import WhisperModel

from intent_router import handle_command
import threading
import msvcrt
from tts import speak, stop_speaking
from supabase_client import log_command
import jarvis_state
from dashboard_server import run_server
import spotify_control



def _listen_for_stop_word(stop_flag):
    """Background thread: transcribe 1-second mic windows and stop speech on keyword."""
    import re
    chunks_per_window = int(RATE / CHUNK)  # ~1 second
    while not stop_flag.is_set():
        frames = []
        for _ in range(chunks_per_window):
            if stop_flag.is_set():
                return
            try:
                frames.append(stream.read(CHUNK, exception_on_overflow=False))
            except Exception:
                return

        # Convert to float32 for Whisper
        audio_np = (np.frombuffer(b"".join(frames), dtype=np.int16)
                    .astype(np.float32) / 32768.0)
        try:
            segs, _ = whisper_model.transcribe(
                audio_np, language="en", beam_size=1, vad_filter=False
            )
            heard = " ".join(s.text for s in segs).lower().strip()
            
            # Match exact stop words to avoid false positive triggers
            if heard:
                # Check for direct phrase matches
                has_phrase = any(phrase in heard for phrase in ("hey stop jarvis", "jarvis stop", "hey stop"))
                # Check for individual word matches
                words = set(re.findall(r"\b\w+\b", heard))
                has_word = any(w in words for w in ("stop", "quiet", "silence", "shutup"))
                
                if has_phrase or has_word:
                    print(f"\n[Voice stop triggered by: '{heard}']")
                    stop_speaking()
                    return
        except Exception:
            pass

def speak_interruptible(text):
    """Speak text; say 'hey stop' or press any key to interrupt."""
    # Flush stdin key buffer first so previous typing doesn't instantly interrupt
    while msvcrt.kbhit():
        msvcrt.getch()

    stop_flag = threading.Event()

    speech_thread = threading.Thread(target=speak, args=(text,), daemon=True)
    speech_thread.start()

    listener = threading.Thread(target=_listen_for_stop_word, args=(stop_flag,), daemon=True)
    listener.start()

    # Update Jarvis state
    jarvis_state.state.status = "speaking"
    jarvis_state.state.last_response = text

    while speech_thread.is_alive():
        if msvcrt.kbhit():
            msvcrt.getch()
            stop_speaking()
            print("\n[Speech stopped by key]")
            break
        time.sleep(0.05)

    stop_flag.set()              # tell listener to exit
    speech_thread.join(timeout=1)
    listener.join(timeout=2)
    jarvis_state.state.status = "idle"


download_models()
oww_model = Model(wakeword_models=["hey_jarvis", "jarvis"], inference_framework="onnx")

# ── Try GPU first (RTX 3050), fall back to CPU ──
try:
    whisper_model = WhisperModel("base", device="cuda", compute_type="int8_float16")
    print("[OK] Whisper loaded on GPU (CUDA)")
except Exception as e:
    print(f"[WARN] GPU unavailable ({e}), falling back to CPU")
    whisper_model = WhisperModel("base", device="cpu", compute_type="int8")

# Share Whisper model reference with dashboard server
jarvis_state.state.whisper_model = whisper_model

RATE = 16000
CHUNK = 1280

pa = pyaudio.PyAudio()
stream = pa.open(rate=RATE, channels=1, format=pyaudio.paInt16, input=True, frames_per_buffer=CHUNK)

def record_command():
    for _ in range(3):
        stream.read(CHUNK, exception_on_overflow=False)

    calibration_samples = []
    for _ in range(8):
        data = stream.read(CHUNK, exception_on_overflow=False)
        audio_np = np.frombuffer(data, dtype=np.int16)
        calibration_samples.append(np.abs(audio_np).mean())
    ambient_noise = np.mean(calibration_samples)
    silence_threshold = max(400, ambient_noise * 2.2)
    print(f"Ambient noise: {ambient_noise:.0f} -> threshold set to {silence_threshold:.0f}")

    jarvis_state.state.status = "listening"
    print("Listening for your command...")
    frames = []
    silence_chunks = 0
    max_silence_chunks = int(RATE / CHUNK * 1.5)
    max_total_chunks = int(RATE / CHUNK * 10)
    started_talking = False

    for _ in range(max_total_chunks):
        data = stream.read(CHUNK, exception_on_overflow=False)
        frames.append(data)
        audio_np = np.frombuffer(data, dtype=np.int16)
        volume = np.abs(audio_np).mean()

        if volume > silence_threshold:
            started_talking = True
            silence_chunks = 0
        elif started_talking:
            silence_chunks += 1

        if started_talking and silence_chunks > max_silence_chunks:
            break

    if not started_talking:
        print("[Silence detected]")
        return ""

    wf = wave.open("command.wav", "wb")
    wf.setnchannels(1)
    wf.setsampwidth(pa.get_sample_size(pyaudio.paInt16))
    wf.setframerate(RATE)
    wf.writeframes(b"".join(frames))
    wf.close()

    # Enable Voice Activity Detection (VAD) and a no-speech threshold to ignore ambient noise
    jarvis_state.state.status = "processing"
    segments, _ = whisper_model.transcribe(
        "command.wav", 
        vad_filter=True, 
        no_speech_threshold=0.6,
        temperature=0.0  # decrease randomness to avoid hallucinations
    )
    jarvis_state.state.status = "idle"
    return " ".join([seg.text for seg in segments]).strip()


# Start dashboard server thread
flask_thread = threading.Thread(target=run_server, args=(5000,), daemon=True)
flask_thread.start()

# Automatically open the dashboard in the default browser after a short delay
def open_browser():
    time.sleep(1.5)
    import webbrowser
    webbrowser.open("http://localhost:5000")

# Check if running in server-only mode (bypasses opening the local UI)
import sys
server_only = "--server-only" in sys.argv or "--no-ui" in sys.argv

if not server_only:
    threading.Thread(target=open_browser, daemon=True).start()
else:
    print("[OK] Server-only mode active. Local browser launch bypassed.")


# ── Global Hotkey Trigger Setup ──
import keyboard

hotkey_triggered = False

def on_hotkey_pressed():
    global hotkey_triggered
    hotkey_triggered = True

# Register system-wide hotkey Ctrl+Alt+J to trigger voice command capture
keyboard.add_hotkey("ctrl+alt+j", on_hotkey_pressed)
print("[OK] Global shortcut hotkey registered: Ctrl+Alt+J")

last_clap_time = 0
print("Jarvis is online. Say 'Hey Jarvis', 'Jarvis', or press Ctrl+Alt+J to activate...")

try:
    while True:
        # If mobile has exclusive control, pause laptop mic and skip wake-word detection
        if jarvis_state.state.active_mic_device == "mobile":
            time.sleep(0.1)
            continue

        # Standby mode: wait for wake word
        audio_data = np.frombuffer(stream.read(CHUNK, exception_on_overflow=False), dtype=np.int16)
        prediction = oww_model.predict(audio_data)

        triggered = False
        
        # Determine activation thresholds based on whether Spotify is playing music
        spotify_active = jarvis_state.state.spotify_is_playing
        clap_threshold = 28000 if spotify_active else 16000
        wakeword_threshold = 0.85 if spotify_active else 0.5

        # Double clap detection
        max_val = np.max(np.abs(audio_data))
        current_time = time.time()
        if max_val > clap_threshold:
            if current_time - last_clap_time > 0.15:
                if current_time - last_clap_time < 0.8:
                    print("\n[Double clap detected!]")
                    triggered = True
                    last_clap_time = 0
                else:
                    last_clap_time = current_time

        if hotkey_triggered:
            print("\n[Hotkey trigger detected: Ctrl+Alt+J]")
            triggered = True
            hotkey_triggered = False
        elif not triggered:
            for mdl, score in prediction.items():
                if score > wakeword_threshold:
                    print(f"Wake word detected! [{mdl}] ({score:.2f})")
                    triggered = True
                    break
        
        if triggered:
            in_conversation = True
            spotify_paused_by_jarvis = False
            jarvis_state.state.spotify_playback_changed = False
            
            # Check and pause Spotify if playing
            sp = spotify_control.get_spotify_client()
            if sp:
                try:
                    curr = spotify_control.get_current_track(sp)
                    if curr and curr.get("is_playing"):
                        print("[Spotify] Pausing music for conversation...")
                        spotify_control.pause_playback(sp)
                        spotify_paused_by_jarvis = True
                        jarvis_state.state.spotify_is_playing = False
                        time.sleep(0.5)  # Wait for sound to stop propagating
                except Exception as e:
                    print(f"[Spotify] Error pausing: {e}")
            
            while in_conversation:
                command_text = record_command()
                print(f"You said: {command_text}")

                # If silent (no command recorded), exit conversation mode
                if not command_text:
                    print("No speech detected. Returning to standby...")
                    in_conversation = False
                    jarvis_state.state.status = "idle"
                    break
                
                jarvis_state.state.last_command = command_text

                # If exit command detected, say goodbye and return to standby
                text_lower = command_text.lower().strip().rstrip(".!?")
                exact_exits = {"goodbye", "bye", "bye bye", "quit", "exit", "stop", "okay", "ok", "okay stop", "ok stop"}
                substring_exits = ("go to sleep", "exit conversation")
                
                if text_lower in exact_exits or any(exit_word in text_lower for exit_word in substring_exits):
                    response = "Goodbye. Let me know when you need me again."
                    print(f"Jarvis: {response}")
                    speak_interruptible(response)
                    in_conversation = False
                    break

                # Execute command
                jarvis_state.state.status = "processing"
                response = handle_command(command_text)
                print(f"Jarvis: {response}")
                
                open_url_val = getattr(jarvis_state.state, "client_open_url", "")
                if open_url_val:
                    import system_actions
                    system_actions.open_url(open_url_val)
                    jarvis_state.state.client_open_url = ""

                speak_interruptible(response)
                threading.Thread(target=log_command, args=(command_text, "voice_command", response, "voice"), daemon=True).start()
                
                # Check if Spotify playback was changed/started/stopped by this command
                if jarvis_state.state.spotify_playback_changed:
                    print("[Spotify] Playback command detected. Exiting conversation mode.")
                    in_conversation = False
                    break
                
                # Print a small indicator that we are listening again
                print("\n[Jarvis is listening for follow-up...]")
            
            # Resume Spotify if we paused it and no playback-altering commands occurred
            if spotify_paused_by_jarvis and not jarvis_state.state.spotify_playback_changed:
                try:
                    last_cmd = jarvis_state.state.last_command.lower()
                    is_pause_cmd = any(w in last_cmd for w in ["pause", "stop", "mute", "silence", "shutup", "quiet"])
                    if not is_pause_cmd and sp:
                        print("[Spotify] Resuming music playback...")
                        spotify_control.resume_playback(sp)
                        jarvis_state.state.spotify_is_playing = True
                except Exception as e:
                    print(f"[Spotify] Error resuming: {e}")

except KeyboardInterrupt:
    print("Stopping...")
finally:
    stream.close()
    pa.terminate()
