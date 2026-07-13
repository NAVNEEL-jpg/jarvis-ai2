import threading
import time

class JarvisState:
    def __init__(self):
        self._status = "idle"  # idle, listening, processing, speaking
        self._last_command = ""
        self._last_response = ""
        self._keyboard_color = "#00f0ff"
        self._alarms = []
        self._power_schedules = []
        self._is_locked = True
        self._active_mic_device = "laptop"  # "laptop" | "mobile" | "both"
        self.lock = threading.Lock()
        self.start_time = time.time()
        self.whisper_model = None
        self._last_speech_id = 0
        self._spotify_logged_in = False
        self._spotify_track = ""
        self._spotify_artist = ""
        self._spotify_progress = 0
        self._spotify_duration = 0
        self._spotify_is_playing = False
        self._spotify_playback_changed = False
        self._client_open_url = ""

    @property
    def status(self):
        with self.lock:
            return self._status

    @status.setter
    def status(self, value):
        with self.lock:
            self._status = value

    @property
    def last_command(self):
        with self.lock:
            return self._last_command

    @last_command.setter
    def last_command(self, value):
        with self.lock:
            self._last_command = value

    @property
    def last_response(self):
        with self.lock:
            return self._last_response

    @last_response.setter
    def last_response(self, value):
        with self.lock:
            self._last_response = value

    @property
    def keyboard_color(self):
        with self.lock:
            return self._keyboard_color

    @keyboard_color.setter
    def keyboard_color(self, value):
        with self.lock:
            self._keyboard_color = value

    @property
    def alarms(self):
        with self.lock:
            return list(self._alarms)

    @alarms.setter
    def alarms(self, value):
        with self.lock:
            self._alarms = list(value)

    @property
    def power_schedules(self):
        with self.lock:
            return list(self._power_schedules)

    @power_schedules.setter
    def power_schedules(self, value):
        with self.lock:
            self._power_schedules = list(value)

    @property
    def is_locked(self):
        with self.lock:
            return self._is_locked

    @is_locked.setter
    def is_locked(self, value):
        with self.lock:
            self._is_locked = bool(value)

    @property
    def active_mic_device(self):
        with self.lock:
            return self._active_mic_device

    @active_mic_device.setter
    def active_mic_device(self, value):
        allowed = ("laptop", "mobile", "both")
        with self.lock:
            self._active_mic_device = value if value in allowed else "laptop"

    @property
    def last_speech_id(self):
        with self.lock:
            return self._last_speech_id

    @last_speech_id.setter
    def last_speech_id(self, value):
        with self.lock:
            self._last_speech_id = value

    @property
    def spotify_logged_in(self):
        with self.lock:
            return self._spotify_logged_in

    @spotify_logged_in.setter
    def spotify_logged_in(self, value):
        with self.lock:
            self._spotify_logged_in = bool(value)

    @property
    def spotify_track(self):
        with self.lock:
            return self._spotify_track

    @spotify_track.setter
    def spotify_track(self, value):
        with self.lock:
            self._spotify_track = value

    @property
    def spotify_artist(self):
        with self.lock:
            return self._spotify_artist

    @spotify_artist.setter
    def spotify_artist(self, value):
        with self.lock:
            self._spotify_artist = value

    @property
    def spotify_progress(self):
        with self.lock:
            return self._spotify_progress

    @spotify_progress.setter
    def spotify_progress(self, value):
        with self.lock:
            self._spotify_progress = int(value)

    @property
    def spotify_duration(self):
        with self.lock:
            return self._spotify_duration

    @spotify_duration.setter
    def spotify_duration(self, value):
        with self.lock:
            self._spotify_duration = int(value)

    @property
    def spotify_is_playing(self):
        with self.lock:
            return self._spotify_is_playing

    @spotify_is_playing.setter
    def spotify_is_playing(self, value):
        with self.lock:
            self._spotify_is_playing = bool(value)

    @property
    def spotify_playback_changed(self):
        with self.lock:
            return self._spotify_playback_changed

    @spotify_playback_changed.setter
    def spotify_playback_changed(self, value):
        with self.lock:
            self._spotify_playback_changed = bool(value)

    @property
    def client_open_url(self):
        with self.lock:
            return self._client_open_url

    @client_open_url.setter
    def client_open_url(self, value):
        with self.lock:
            self._client_open_url = str(value)

    def get_dict(self):
        with self.lock:
            return {
                "status": self._status,
                "last_command": self._last_command,
                "last_response": self._last_response,
                "keyboard_color": self._keyboard_color,
                "alarms": self._alarms,
                "power_schedules": self._power_schedules,
                "is_locked": self._is_locked,
                "active_mic_device": self._active_mic_device,
                "last_speech_id": self._last_speech_id,
                "spotify_logged_in": self._spotify_logged_in,
                "spotify_track": self._spotify_track,
                "spotify_artist": self._spotify_artist,
                "spotify_progress": self._spotify_progress,
                "spotify_duration": self._spotify_duration,
                "spotify_is_playing": self._spotify_is_playing,
                "spotify_playback_changed": self._spotify_playback_changed,
                "client_open_url": self._client_open_url,
                "uptime": round(time.time() - self.start_time)
            }


state = JarvisState()

BILINGUAL_PROMPT = (
    "Hey Jarvis, play some music. Play Bengali songs, Rabindra Sangeet, "
    "Arijit Singh, Shreya Ghoshal, Anupam Roy, Nachiketa, Hemanta Mukherjee, "
    "Kishore Kumar, Manna Dey, Fossils, Cactus, Anjan Dutt, Rupam Islam. "
    "Play songs like: Ami Tomake Bhalobashi, Amar Sonar Bangla, Ekla Cholo Re, "
    "Tomake Chaye, Tumi Jaake Bhalobasho, Prithibi Ta Gol, Bosey Bosey Keno Debo."
)
