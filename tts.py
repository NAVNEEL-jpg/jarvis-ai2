import time
import wave
import threading
import sounddevice as sd
import soundfile as sf
from piper import PiperVoice

# Load the voice ONCE when this module is imported, not per-response
voice = PiperVoice.load("en_GB-alan-medium.onnx")

_stop_event = threading.Event()

def speak(text):
    """Synthesise and play text. Call stop_speaking() to interrupt."""
    _stop_event.clear()
    with wave.open("tts_output.wav", "wb") as wav_file:
        voice.synthesize_wav(text, wav_file)

    try:
        import jarvis_state
        jarvis_state.state.last_speech_id = int(time.time() * 1000)
    except Exception:
        pass

    data, samplerate = sf.read("tts_output.wav")
    sd.play(data, samplerate)

    # Wait for playback to finish OR stop_event to be set
    duration = len(data) / samplerate
    start_time = time.time()
    while time.time() - start_time < duration:
        if _stop_event.is_set():
            sd.stop()
            break
        time.sleep(0.05)

def stop_speaking():
    """Interrupt any ongoing speech immediately."""
    _stop_event.set()
    sd.stop()