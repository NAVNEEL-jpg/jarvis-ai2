import os
import time
import threading
import subprocess
import shutil
import requests
import datetime
import winsound
from flask import Flask, jsonify, request, redirect, session

import jarvis_state
from intent_router import handle_command
from tts import speak, stop_speaking
from supabase_client import log_command, get_today_tasks, complete_task, get_automations
from home_assistant import call_service
from system_actions import open_url, open_app

base_dir = os.path.dirname(os.path.abspath(__file__))
static_dir = os.path.join(base_dir, "dashboard", "static")

app = Flask(__name__, static_folder=static_dir, static_url_path="")
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "stark-industries-lock-key-9982")

def is_session_locked():
    if jarvis_state.state.is_locked:
        return True
    return not session.get("verified", False)

@app.after_request
def add_cors_headers(response):
    response.headers.add("Access-Control-Allow-Origin", "*")
    response.headers.add("Access-Control-Allow-Headers", "Content-Type,Authorization")
    response.headers.add("Access-Control-Allow-Methods", "GET,PUT,POST,DELETE,OPTIONS")
    return response


# Local session logs list for quick UI feedback
session_logs = []

# ── User Reference Face Templates for Secure Biometric Matching ──
REF_IMGS = [
    r"C:\Users\admin\.gemini\antigravity-ide\brain\8f783435-32d7-465f-86e3-ec67c21710b1\media__1783720097525.png",
    r"C:\Users\admin\.gemini\antigravity-ide\brain\8f783435-32d7-465f-86e3-ec67c21710b1\media__1783720106849.png",
    r"C:\Users\admin\.gemini\antigravity-ide\brain\8f783435-32d7-465f-86e3-ec67c21710b1\media__1783720116069.png",
    r"C:\Users\admin\.gemini\antigravity-ide\brain\8f783435-32d7-465f-86e3-ec67c21710b1\media__1783720130047.png",
    r"C:\Users\admin\.gemini\antigravity-ide\brain\8f783435-32d7-465f-86e3-ec67c21710b1\media__1783720140328.png"
]

_ref_face_templates = []

def _init_reference_faces():
    global _ref_face_templates
    _ref_face_templates = []
    try:
        import cv2
        cascade_path = cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
        face_cascade = cv2.CascadeClassifier(cascade_path)
        
        for path in REF_IMGS:
            if not os.path.exists(path):
                continue
            img = cv2.imread(path)
            if img is None:
                continue
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            faces = face_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=3, minSize=(60, 60))
            if len(faces) > 0:
                faces = sorted(faces, key=lambda f: f[2]*f[3], reverse=True)
                x, y, w, h = faces[0]
                face_roi = gray[y:y+h, x:x+w]
                face_resized = cv2.resize(face_roi, (100, 100))
                face_equalized = cv2.equalizeHist(face_resized)
                _ref_face_templates.append(face_equalized)
        print(f"[OK] Loaded {len(_ref_face_templates)} user reference face templates.")
    except Exception as e:
        print(f"Error loading reference face templates: {e}")

# Lazy-load templates when needed, no module-level blocking call

def speak_web_response(text):
    """Speak text in a background thread to prevent blocking Flask routes."""
    stop_speaking()
    
    def run_speak():
        jarvis_state.state.status = "speaking"
        speak(text)
        jarvis_state.state.status = "idle"
        
    threading.Thread(target=run_speak, daemon=True).start()


def prepare_and_speak_response(text, play_local=True, speech_id=None, resume_spotify=False):
    """Synthesizes the WAV file synchronously so it's ready for client download,
    then optionally plays it on the laptop speakers in the background."""
    stop_speaking()
    
    # Update speech ID in Jarvis state
    if speech_id is None:
        speech_id = int(time.time() * 1000)
    jarvis_state.state.last_speech_id = speech_id
    
    # 1. Synthesize the wav file synchronously in the main request thread
    import wave
    from tts import voice
    try:
        with wave.open("tts_output.wav", "wb") as wav_file:
            voice.synthesize_wav(text, wav_file)
    except Exception as e:
        print(f"[Dashboard Server] TTS Synthesis error: {e}")

    # Calculate audio duration
    duration = 0.0
    try:
        import soundfile as sf
        info = sf.info("tts_output.wav")
        duration = info.duration
    except Exception:
        duration = len(text) * 0.08

    def do_resume():
        try:
            import spotify_control
            sp = spotify_control.get_spotify_client()
            if sp:
                spotify_control.resume_playback(sp)
                jarvis_state.state.spotify_is_playing = True
        except Exception as e:
            print(f"[Dashboard Server] Error resuming Spotify: {e}")

    # 2. If we need to play locally on laptop, trigger that in a thread
    if play_local:
        import sounddevice as sd
        import soundfile as sf
        
        def run_play():
            try:
                jarvis_state.state.status = "speaking"
                data, samplerate = sf.read("tts_output.wav")
                sd.play(data, samplerate)
                
                from tts import _stop_event
                _stop_event.clear()
                play_duration = len(data) / samplerate
                start_time = time.time()
                while time.time() - start_time < play_duration:
                    if _stop_event.is_set():
                        sd.stop()
                        break
                    time.sleep(0.05)
            except Exception as e:
                print(f"[Dashboard Server] Local playback error: {e}")
            finally:
                jarvis_state.state.status = "idle"
                if resume_spotify:
                    do_resume()
                
        threading.Thread(target=run_play, daemon=True).start()
    else:
        # Update status to idle since synthesis is complete and no local playback is running
        jarvis_state.state.status = "idle"
        if resume_spotify:
            def run_delayed_resume():
                time.sleep(duration + 0.5)
                do_resume()
            threading.Thread(target=run_delayed_resume, daemon=True).start()

# ── Flask API Routes ────────────────────────────────────────────────────────

@app.route("/")
def index():
    return app.send_static_file("index.html")

@app.route("/api/lock_voice_prompt", methods=["POST"])
def lock_voice_prompt():
    response = "Systems are locked, Sir. Please provide the passcode, voice authentication, or run face verification."
    speech_id = int(time.time() * 1000)
    prepare_and_speak_response(response, play_local=False, speech_id=speech_id)
    return jsonify({"status": "success", "speech_id": speech_id})

@app.route("/api/status", methods=["GET"])
def get_status():
    res = jarvis_state.state.get_dict()
    res["is_locked"] = is_session_locked()
    return jsonify(res)

@app.route("/api/command", methods=["POST"])
def run_command_endpoint():
    data = request.json or {}
    text = data.get("command", "").strip()
    if not text:
        return jsonify({"error": "Empty command"}), 400

    # Session authentication check
    if is_session_locked():
        import re
        t_norm = text.lower().strip().replace(" ", "").replace("-", "")
        t_norm = re.sub(r'^(hey)?jarvis', '', t_norm)
        
        if "4598" in t_norm or "fourfivenineeight" in t_norm:
            session["verified"] = True
            jarvis_state.state.is_locked = False
            response = "Verification successful. Welcome back, Sir."
            prepare_and_speak_response(response, play_local=True)
            return jsonify({"status": "success", "response": response})
            
        elif any(phrase in text.lower() for phrase in ["authenticate", "unlock", "log in", "login"]):
            response = "Standing by. Please state the passcode, Sir."
            prepare_and_speak_response(response, play_local=True)
            return jsonify({"status": "success", "response": response})
            
        else:
            response = "Systems are locked, Sir. Please provide the passcode, voice authentication, or run face verification."
            prepare_and_speak_response(response, play_local=True)
            return jsonify({
                "status": "blocked",
                "response": response
            }), 403

    # Block mobile/web commands when laptop mic has exclusive control
    active_device = jarvis_state.state.active_mic_device
    if active_device == "laptop":
        return jsonify({
            "status": "blocked",
            "response": "Laptop mic is the active input device. Switch to Mobile or Both to use this device."
        }), 403

    jarvis_state.state.status = "processing"
    jarvis_state.state.last_command = text

    # Pause Spotify if active on command entry
    spotify_paused_by_jarvis = False
    try:
        import spotify_control
        sp = spotify_control.get_spotify_client()
        if sp:
            curr = spotify_control.get_current_track(sp)
            if curr and curr.get("is_playing"):
                spotify_control.pause_playback(sp)
                spotify_paused_by_jarvis = True
                jarvis_state.state.spotify_is_playing = False
                jarvis_state.state.spotify_playback_changed = False
    except Exception:
        pass

    # Process intent
    response = handle_command(text)
    jarvis_state.state.last_response = response

    # Log command locally and in Supabase in background thread
    def async_log():
        try:
            log_command(text, "web_command", response, source="web")
        except Exception as e:
            print(f"[Dashboard Server] Failed to log command to Supabase: {e}")
    threading.Thread(target=async_log, daemon=True).start()

    session_logs.insert(0, {
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "transcript": text,
        "response": response,
        "source": "web"
    })
    if len(session_logs) > 20:
        session_logs.pop()

    # Determine if Spotify needs to be resumed after response finishes speaking
    resume_spotify = False
    if spotify_paused_by_jarvis and not jarvis_state.state.spotify_playback_changed:
        is_pause_cmd = any(w in text.lower() for w in ["pause", "stop", "mute", "silence", "shutup", "quiet"])
        if not is_pause_cmd:
            resume_spotify = True

    # Speak the response
    play_local = (active_device == "both")
    speech_id = int(time.time() * 1000)
    prepare_and_speak_response(response, play_local=play_local, speech_id=speech_id, resume_spotify=resume_spotify)

    open_url_val = getattr(jarvis_state.state, "client_open_url", "")
    if open_url_val:
        jarvis_state.state.client_open_url = ""

    return jsonify({
        "status": "success",
        "response": response,
        "speech_id": speech_id,
        "open_url": open_url_val
    })

@app.route("/api/stop", methods=["POST"])
def stop_speech():
    stop_speaking()
    jarvis_state.state.status = "idle"
    return jsonify({"status": "stopped"})


@app.route("/api/spotify/login")
def spotify_login():
    import spotify_control
    auth_manager = spotify_control.get_sp_oauth()
    if not auth_manager:
        return "Spotify client ID/secret are not configured in your environment files, Sir.", 400
    auth_url = auth_manager.get_authorize_url()
    return redirect(auth_url)


@app.route("/callback")
def spotify_callback():
    import spotify_control
    code = request.args.get("code")
    if not code:
        return "Authorization failed. Code is missing, Sir.", 400
    
    auth_manager = spotify_control.get_sp_oauth()
    if not auth_manager:
        return "Spotify configuration error, Sir.", 500
        
    try:
        auth_manager.get_access_token(code)
    except Exception as e:
        return f"Failed to authenticate with Spotify, Sir: {str(e)}", 500
        
    return """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Spotify Uplink Established</title>
        <link href="https://fonts.googleapis.com/css2?family=Orbitron:wght@400;700;900&family=Share+Tech+Mono&display=swap" rel="stylesheet">
        <style>
            body {
                background-color: #030406;
                color: #d6e8f4;
                font-family: 'Orbitron', sans-serif;
                margin: 0;
                display: flex;
                justify-content: center;
                align-items: center;
                height: 100vh;
                background-image: 
                    linear-gradient(rgba(0, 240, 255, 0.03) 1px, transparent 1px),
                    linear-gradient(90deg, rgba(0, 240, 255, 0.03) 1px, transparent 1px);
                background-size: 30px 30px;
            }
            .success-container {
                background: rgba(6, 9, 15, 0.85);
                border: 1px solid #00f0ff;
                box-shadow: 0 0 25px rgba(0, 240, 255, 0.15);
                padding: 40px;
                border-radius: 8px;
                text-align: center;
                max-width: 500px;
                width: 90%;
            }
            .logo {
                font-size: 0.9rem;
                letter-spacing: 4px;
                color: #5e7e90;
                margin-bottom: 20px;
            }
            h1 {
                font-size: 1.5rem;
                color: #00f0ff;
                margin-bottom: 15px;
                text-shadow: 0 0 10px rgba(0, 240, 255, 0.2);
            }
            p {
                font-family: 'Share Tech Mono', monospace;
                font-size: 0.85rem;
                color: #26ff7b;
                margin-bottom: 30px;
                line-height: 1.5;
            }
            .btn {
                background: rgba(0, 162, 255, 0.05);
                border: 1px solid #00f0ff;
                color: #00f0ff;
                font-family: 'Share Tech Mono', monospace;
                font-size: 0.75rem;
                padding: 10px 20px;
                cursor: pointer;
                transition: all 0.3s;
                text-decoration: none;
                display: inline-block;
            }
            .btn:hover {
                background: rgba(0, 240, 255, 0.2);
                box-shadow: 0 0 8px rgba(0, 240, 255, 0.35);
            }
        </style>
    </head>
    <body>
        <div class="success-container">
            <div class="logo">STARK INDUSTRIES</div>
            <h1>SPOTIFY UPLINK SUCCESSFUL</h1>
            <p>[SYSTEM SECURE] J.A.R.V.I.S. MUSIC CONTROL PROTOCOL DEPLOYED AND CACHED SUCCESSFULLY.</p>
            <button class="btn" onclick="window.close()">CLOSE SECURE TERMINAL</button>
        </div>
    </body>
    </html>
    """


@app.route("/api/spotify/control", methods=["POST"])
def spotify_control_api():
    import spotify_control
    
    if jarvis_state.state.is_locked:
        return jsonify({"error": "Systems are locked"}), 403
        
    data = request.json or {}
    action = data.get("action", "").lower()
    
    sp = spotify_control.get_spotify_client()
    if not sp:
        return jsonify({"error": "Spotify not logged in"}), 401
        
    res_msg = ""
    if action == "play":
        res_msg = spotify_control.resume_playback(sp)
    elif action == "pause":
        res_msg = spotify_control.pause_playback(sp)
    elif action == "next":
        res_msg = spotify_control.next_track(sp)
    elif action == "previous":
        res_msg = spotify_control.previous_track(sp)
    else:
        return jsonify({"error": "Invalid action"}), 400
        
    open_url_val = getattr(jarvis_state.state, "client_open_url", "")
    if open_url_val:
        jarvis_state.state.client_open_url = ""

    return jsonify({"status": "success", "message": res_msg, "open_url": open_url_val})


@app.route("/api/spotify/devices", methods=["GET"])
def spotify_devices_api():
    import spotify_control
    if jarvis_state.state.is_locked:
        return jsonify({"error": "Systems are locked"}), 403
    sp = spotify_control.get_spotify_client()
    if not sp:
        return jsonify({"error": "Spotify not logged in"}), 401
    try:
        devices = sp.devices()
        return jsonify(devices.get("devices", []))
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/spotify/devices/switch", methods=["POST"])
def spotify_devices_switch_api():
    import spotify_control
    if jarvis_state.state.is_locked:
        return jsonify({"error": "Systems are locked"}), 403
    sp = spotify_control.get_spotify_client()
    if not sp:
        return jsonify({"error": "Spotify not logged in"}), 401
    data = request.json or {}
    device_id = data.get("device_id")
    if not device_id:
        return jsonify({"error": "Missing device_id"}), 400
    try:
        sp.transfer_playback(device_id=device_id, force_play=True)
        return jsonify({"status": "success"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500




# ── Active Mic Device Switcher ───────────────────────────────────────────────

@app.route("/api/active_device", methods=["GET"])
def get_active_device():
    return jsonify({"active_mic_device": jarvis_state.state.active_mic_device})


@app.route("/api/active_device", methods=["POST"])
def set_active_device():
    data = request.json or {}
    device = data.get("device", "").strip().lower()
    allowed = ("laptop", "mobile", "both")
    if device not in allowed:
        return jsonify({"error": f"Invalid device. Must be one of: {allowed}"}), 400

    old = jarvis_state.state.active_mic_device
    jarvis_state.state.active_mic_device = device
    print(f"[Device Switch] Active mic changed: {old} -> {device}")
    return jsonify({"active_mic_device": device})


@app.route("/api/speak", methods=["POST"])
def speak_endpoint():
    data = request.json or {}
    text = data.get("text", "").strip()
    if not text:
        return jsonify({"error": "Empty text"}), 400
    
    speak_web_response(text)
    return jsonify({"status": "speaking"})


@app.route("/api/tts_audio", methods=["GET"])
def get_tts_audio():
    from flask import send_file
    filepath = os.path.join(base_dir, "tts_output.wav")
    if os.path.exists(filepath):
        return send_file(filepath, mimetype="audio/wav", as_attachment=False)
    else:
        return jsonify({"error": "Audio not found"}), 404

@app.route("/api/stats", methods=["GET"])
def get_stats():
    # Gather CPU Usage using PowerShell CIM cmdlet
    cpu = 0
    try:
        out = subprocess.check_output("powershell -Command \"(Get-CimInstance Win32_Processor).LoadPercentage\"", shell=True).decode().strip()
        if out.isdigit():
            cpu = int(out)
    except Exception:
        pass

    # Gather RAM Usage using PowerShell CIM cmdlet
    ram = {"percent": 0, "used_gb": 0, "total_gb": 0}
    try:
        free_str = subprocess.check_output("powershell -Command \"(Get-CimInstance Win32_OperatingSystem).FreePhysicalMemory\"", shell=True).decode().strip()
        total_str = subprocess.check_output("powershell -Command \"(Get-CimInstance Win32_OperatingSystem).TotalVisibleMemorySize\"", shell=True).decode().strip()
        if free_str.isdigit() and total_str.isdigit():
            free = int(free_str)
            total = int(total_str)
            used = total - free
            ram = {
                "percent": round((used / total) * 100, 1),
                "used_gb": round(used / (1024 * 1024), 2),
                "total_gb": round(total / (1024 * 1024), 2)
            }
    except Exception:
        pass

    # Gather Disk Usage
    disk = {"percent": 0, "used_gb": 0, "total_gb": 0}
    try:
        drive = "d:\\" if os.path.exists("d:\\") else "c:\\"
        t, u, f = shutil.disk_usage(drive)
        disk = {
            "percent": round((u / t) * 100, 1),
            "used_gb": round(u / (1024**3), 2),
            "total_gb": round(t / (1024**3), 2)
        }
    except Exception:
        pass

    # Gather Battery Status using PowerShell CIM cmdlet
    battery = {"percent": 100, "charging": True}
    try:
        pct_str = subprocess.check_output("powershell -Command \"(Get-CimInstance Win32_Battery).EstimatedChargeRemaining\"", shell=True).decode().strip()
        status_str = subprocess.check_output("powershell -Command \"(Get-CimInstance Win32_Battery).BatteryStatus\"", shell=True).decode().strip()
        if pct_str.isdigit():
            battery["percent"] = int(pct_str)
        if status_str.isdigit():
            battery["charging"] = (int(status_str) == 2)
    except Exception:
        pass

    # Gather GPU Usage, Temp, VRAM
    gpu = {"load": 0, "temp": 35, "mem_used": 0, "mem_total": 0}
    try:
        out = subprocess.check_output("nvidia-smi --query-gpu=utilization.gpu,temperature.gpu,memory.used,memory.total --format=csv,noheader,nounits", shell=True).decode()
        parts = [p.strip() for p in out.split(",")]
        if len(parts) >= 4:
            gpu = {
                "load": int(parts[0]),
                "temp": int(parts[1]),
                "mem_used": round(int(parts[2]) / 1024, 2),
                "mem_total": round(int(parts[3]) / 1024, 2)
            }
    except Exception:
        pass

    # Estimate CPU Temp based on load
    cpu_temp = 38 + int(cpu * 0.45) + (int(time.time()) % 3)
    # Estimate Fan RPMs (simulating dynamic fan response for locked systems)
    cpu_fan_rpm = 1500 + int((cpu / 100) * 3300) + (int(time.time() * 10) % 25)
    
    if gpu["load"] > 0 or gpu["temp"] > 45:
        base_gpu_fan = 1200 if gpu["load"] > 0 else 0
        gpu_fan_rpm = base_gpu_fan + int((gpu["load"] / 100) * 3100) + (int(time.time() * 10) % 20)
    else:
        gpu_fan_rpm = 0

    return jsonify({
        "cpu": cpu,
        "ram": ram,
        "disk": disk,
        "battery": battery,
        "gpu": gpu,
        "cpu_temp": cpu_temp,
        "cpu_fan_rpm": cpu_fan_rpm,
        "gpu_fan_rpm": gpu_fan_rpm
    })

@app.route("/api/weather", methods=["GET"])
def get_weather_endpoint():
    lat = 22.5726
    lon = 88.3639
    city = "Kolkata"
    url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current=temperature_2m,relative_humidity_2m,apparent_temperature,wind_speed_10m,weather_code"
    try:
        res = requests.get(url, timeout=5).json()
        curr = res["current"]
        temp = curr["temperature_2m"]
        humidity = curr["relative_humidity_2m"]
        feels_like = curr["apparent_temperature"]
        wind = curr["wind_speed_10m"]
        code = curr["weather_code"]
        
        descriptions = {
            0: "Clear Sky",
            1: "Mainly Clear", 2: "Partly Cloudy", 3: "Overcast",
            45: "Foggy", 48: "Depositing Rime Fog",
            51: "Light Drizzle", 53: "Moderate Drizzle", 55: "Dense Drizzle",
            61: "Slight Rain", 63: "Moderate Rain", 65: "Heavy Rain",
            71: "Slight Snowfall", 73: "Moderate Snowfall", 75: "Heavy Snowfall",
            80: "Slight Rain Showers", 81: "Moderate Rain Showers", 82: "Violent Rain Showers",
            95: "Thunderstorm", 96: "Thunderstorm with Hail", 99: "Thunderstorm with Heavy Hail"
        }
        condition = descriptions.get(code, "Unknown")
        return jsonify({
            "success": True,
            "city": city,
            "temp": temp,
            "feels_like": feels_like,
            "humidity": humidity,
            "wind_speed": wind,
            "condition": condition
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@app.route("/api/tasks", methods=["GET"])
def get_tasks_endpoint():
    try:
        tasks = get_today_tasks()
        return jsonify(tasks)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/tasks/complete", methods=["POST"])
def complete_task_endpoint():
    data = request.json or {}
    task_id = data.get("id")
    if not task_id:
        return jsonify({"error": "Empty task ID"}), 400
    try:
        complete_task(task_id)
        return jsonify({"status": "success"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/automations", methods=["GET"])
def get_automations_endpoint():
    try:
        from intent_router import refresh_automations
        refresh_automations()
        automations = get_automations()
        return jsonify(automations)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/trigger_automation", methods=["POST"])
def trigger_automation_endpoint():
    data = request.json or {}
    a = data.get("automation", {})
    action_type = a.get("action_type")
    
    success = False
    if action_type == "ha_service":
        success = call_service(a.get("domain"), a.get("service"), a.get("entity_id"))
    elif action_type == "open_url":
        open_url(a.get("target"))
        success = True
    elif action_type == "open_app":
        open_app(a.get("target"))
        success = True
        
    return jsonify({"success": success})

@app.route("/api/logs", methods=["GET"])
def get_logs_endpoint():
    try:
        from supabase_client import supabase
        result = supabase.table("commands_log").select("*").order("created_at", desc=True).limit(15).execute()
        db_logs = result.data
        
        # Merge local and db logs, prioritizing db but ensuring no duplicates
        all_logs = {log.get("id") or log.get("created_at"): log for log in db_logs}
        for log in session_logs:
            key = log.get("created_at")
            if key not in all_logs:
                all_logs[key] = log
                
        sorted_logs = sorted(all_logs.values(), key=lambda x: x.get("created_at", ""), reverse=True)
        return jsonify(sorted_logs[:15])
    except Exception as e:
        print(f"[Dashboard Server] Failed to fetch logs from Supabase: {e}")
        return jsonify(session_logs)

# ── Auth & Verification Endpoints ───────────────────────────────────────────

@app.route("/api/verify_passcode", methods=["POST"])
def verify_passcode():
    data = request.json or {}
    passcode = data.get("passcode", "").strip()
    if passcode == "4598":
        session["verified"] = True
        jarvis_state.state.is_locked = False
        speak_web_response("Verification successful. Welcome back, Sir.")
        return jsonify({"verified": True})
    speak_web_response("Verification failed.")
    return jsonify({"verified": False, "error": "Invalid passcode"})

@app.route("/api/lock", methods=["POST"])
def lock_session():
    session["verified"] = False
    jarvis_state.state.is_locked = True
    speak_web_response("Systems locked, Sir. Shield active.")
    return jsonify({"status": "success", "is_locked": True})

@app.route("/api/face_verify", methods=["POST"])
def face_verify_endpoint():
    try:
        import cv2
        import numpy as np
    except ImportError:
        speak_web_response("Verification failed. Biometric libraries offline.")
        return jsonify({
            "verified": False,
            "error": "OpenCV not installed. Please use Passcode verification."
        })

    if not _ref_face_templates:
        _init_reference_faces()
    if not _ref_face_templates:
        speak_web_response("Verification failed. Reference photos missing.")
        return jsonify({
            "verified": False,
            "error": "No reference face templates loaded."
        })

    cascade_path = cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
    face_cascade = cv2.CascadeClassifier(cascade_path)

    # 1. Check if an image was uploaded from the client (mobile browser / remote web)
    uploaded_file = request.files.get("image")
    if uploaded_file:
        try:
            file_bytes = np.frombuffer(uploaded_file.read(), np.uint8)
            frame = cv2.imdecode(file_bytes, cv2.IMREAD_COLOR)
            if frame is None:
                return jsonify({"verified": False, "error": "Could not decode uploaded image."})
            
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            faces = face_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=3, minSize=(60, 60))
            
            verified = False
            best_match_score = -1.0
            
            if len(faces) > 0:
                faces = sorted(faces, key=lambda f: f[2]*f[3], reverse=True)
                x, y, w, h = faces[0]
                webcam_face = gray[y:y+h, x:x+w]
                webcam_resized = cv2.resize(webcam_face, (100, 100))
                webcam_equalized = cv2.equalizeHist(webcam_resized)
                
                for ref_face in _ref_face_templates:
                    res = cv2.matchTemplate(webcam_equalized, ref_face, cv2.TM_CCOEFF_NORMED)
                    _, max_val, _, _ = cv2.minMaxLoc(res)
                    if max_val > best_match_score:
                        best_match_score = max_val
                
                if best_match_score >= 0.22:
                    verified = True
            
            if verified:
                session["verified"] = True
                jarvis_state.state.is_locked = False
                speak_web_response("Verification successful. Welcome back, Sir.")
                return jsonify({"verified": True})
            else:
                speak_web_response("Verification failed.")
                return jsonify({
                    "verified": False,
                    "error": f"Remote face match failed (Best Score: {best_match_score:.2f})."
                })
        except Exception as e:
            return jsonify({"verified": False, "error": f"Error processing uploaded image: {e}"})

    # 2. Fallback to laptop local webcam capture
    # Use DirectShow on Windows for instant camera initialization
    cap = cv2.VideoCapture(0, cv2.CAP_DSHOW) if os.name == "nt" else cv2.VideoCapture(0)
    if not cap.isOpened():
        speak_web_response("Verification failed. Camera source offline.")
        return jsonify({
            "verified": False,
            "error": "Webcam not accessible."
        })

    verified = False
    best_match_score = -1.0
    
    for _ in range(15):
        ret, frame = cap.read()
        if not ret:
            continue
        
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        faces = face_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=4, minSize=(80, 80))
        if len(faces) > 0:
            faces = sorted(faces, key=lambda f: f[2]*f[3], reverse=True)
            x, y, w, h = faces[0]
            webcam_face = gray[y:y+h, x:x+w]
            webcam_resized = cv2.resize(webcam_face, (100, 100))
            webcam_equalized = cv2.equalizeHist(webcam_resized)
            
            for ref_face in _ref_face_templates:
                res = cv2.matchTemplate(webcam_equalized, ref_face, cv2.TM_CCOEFF_NORMED)
                _, max_val, _, _ = cv2.minMaxLoc(res)
                if max_val > best_match_score:
                    best_match_score = max_val
            
            if best_match_score >= 0.22:
                verified = True
                break
        time.sleep(0.05)
        
    cap.release()
    
    if verified:
        session["verified"] = True
        jarvis_state.state.is_locked = False
        speak_web_response("Verification successful. Welcome back, Sir.")
        return jsonify({"verified": True})
    else:
        speak_web_response("Verification failed.")
        return jsonify({
            "verified": False,
            "error": f"Face verify failed. Correlation score: {best_match_score:.2f}"
        })
@app.route("/api/transcribe_mobile", methods=["POST"])
def transcribe_mobile():
    if "audio" not in request.files:
        return jsonify({"error": "No audio file uploaded"}), 400

    audio_file = request.files["audio"]
    if audio_file.filename == "":
        return jsonify({"error": "No selected file"}), 400

    temp_filename = "mobile_command_temp.wav"
    audio_file.save(temp_filename)

    try:
        whisper_model = getattr(jarvis_state.state, "whisper_model", None)
        if whisper_model is None:
            return jsonify({
                "status": "warning",
                "response": "Core voice recognition modules are still initializing, Sir. Please standby."
            }), 503

        jarvis_state.state.status = "processing"
        
        segments, _ = whisper_model.transcribe(
            temp_filename,
            vad_filter=True,
            no_speech_threshold=0.6,
            temperature=0.0,
            initial_prompt=jarvis_state.BILINGUAL_PROMPT
        )
        text = " ".join([seg.text for seg in segments]).strip()
        
        jarvis_state.state.status = "idle"

        if not text:
            return jsonify({"status": "empty", "response": "No speech detected. Please try again."})

        # Process the transcribed text as a command
        # Block mobile/web commands when laptop mic has exclusive control
        active_device = jarvis_state.state.active_mic_device
        if active_device == "laptop":
            return jsonify({
                "status": "blocked",
                "response": "Laptop mic is the active input device. Switch to Mobile or Both to use this device."
            }), 403

        jarvis_state.state.status = "processing"
        jarvis_state.state.last_command = text

        # Pause Spotify if active on command entry
        spotify_paused_by_jarvis = False
        try:
            import spotify_control
            sp = spotify_control.get_spotify_client()
            if sp:
                curr = spotify_control.get_current_track(sp)
                if curr and curr.get("is_playing"):
                    spotify_control.pause_playback(sp)
                    spotify_paused_by_jarvis = True
                    jarvis_state.state.spotify_is_playing = False
                    jarvis_state.state.spotify_playback_changed = False
        except Exception:
            pass

        response = handle_command(text)
        jarvis_state.state.last_response = response

        # Log command
        def async_log():
            try:
                log_command(text, "mobile_voice_command", response, source="mobile")
            except Exception as e:
                print(f"[Dashboard Server] Failed to log command: {e}")
        threading.Thread(target=async_log, daemon=True).start()

        # Add to local session logs
        session_logs.insert(0, {
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "transcript": text,
            "response": response,
            "source": "mobile"
        })
        if len(session_logs) > 20:
            session_logs.pop()

        # Determine if Spotify needs to be resumed after response finishes speaking
        resume_spotify = False
        if spotify_paused_by_jarvis and not jarvis_state.state.spotify_playback_changed:
            is_pause_cmd = any(w in text.lower() for w in ["pause", "stop", "mute", "silence", "shutup", "quiet"])
            if not is_pause_cmd:
                resume_spotify = True

        # Speak the response
        play_local = (active_device == "both")
        speech_id = int(time.time() * 1000)
        prepare_and_speak_response(response, play_local=play_local, speech_id=speech_id, resume_spotify=resume_spotify)

        open_url_val = getattr(jarvis_state.state, "client_open_url", "")
        if open_url_val:
            jarvis_state.state.client_open_url = ""

        return jsonify({
            "status": "success",
            "transcript": text,
            "response": response,
            "speech_id": speech_id,
            "open_url": open_url_val
        })

    except Exception as e:
        print(f"[Dashboard Server] Transcription error: {e}")
        return jsonify({"error": str(e)}), 500
    finally:
        if os.path.exists(temp_filename):
            try:
                os.remove(temp_filename)
            except Exception:
                pass


# ── Alarms Endpoints ────────────────────────────────────────────────────────

@app.route("/api/alarms", methods=["GET"])
def get_alarms_endpoint():
    return jsonify(jarvis_state.state.alarms)

@app.route("/api/alarms/add", methods=["POST"])
def add_alarm_endpoint():
    data = request.json or {}
    time_str = data.get("time", "").strip()
    label = data.get("label", "Alarm").strip()
    if not time_str:
        return jsonify({"error": "Time is required"}), 400
        
    current_alarms = jarvis_state.state.alarms
    new_alarm = {
        "id": int(time.time()),
        "time": time_str,
        "label": label,
        "active": True
    }
    current_alarms.append(new_alarm)
    jarvis_state.state.alarms = current_alarms
    return jsonify({"status": "success", "alarm": new_alarm})

@app.route("/api/alarms/delete", methods=["POST"])
def delete_alarm_endpoint():
    data = request.json or {}
    alarm_id = data.get("id")
    if not alarm_id:
        return jsonify({"error": "Alarm ID is required"}), 400
        
    current_alarms = jarvis_state.state.alarms
    current_alarms = [a for a in current_alarms if a.get("id") != alarm_id]
    jarvis_state.state.alarms = current_alarms
    return jsonify({"status": "success"})


# ── Alarm Checker Background Thread ─────────────────────────────────────────

def alarm_checker():
    last_triggered_minute = ""
    while True:
        try:
            now = datetime.datetime.now()
            current_time_str = now.strftime("%H:%M")
            
            if current_time_str != last_triggered_minute:
                alarms = jarvis_state.state.alarms
                triggered_any = False
                
                for alarm in alarms:
                    if alarm.get("active") and alarm.get("time") == current_time_str:
                        triggered_any = True
                        label = alarm.get("label", "Alarm")
                        print(f"\n[ALARM TRIGGERED: {label}]")
                        
                        # Play system beep sound
                        def play_beep_sound():
                            for _ in range(5):
                                winsound.Beep(1200, 350)
                                time.sleep(0.15)
                        threading.Thread(target=play_beep_sound, daemon=True).start()
                        
                        speak_web_response(f"Excuse me Sir, your alarm for {current_time_str} is ringing.")
                        alarm["active"] = False
                        
                if triggered_any:
                    jarvis_state.state.alarms = alarms
                    last_triggered_minute = current_time_str
        except Exception as e:
            print(f"[Alarm Checker] Error: {e}")
        time.sleep(1)

threading.Thread(target=alarm_checker, daemon=True).start()


def spotify_status_poller():
    import spotify_control
    import jarvis_state
    
    while True:
        try:
            sp = spotify_control.get_spotify_client()
            if sp:
                track_info = spotify_control.get_current_track(sp)
                if track_info:
                    jarvis_state.state.spotify_logged_in = True
                    jarvis_state.state.spotify_track = track_info.get("track", "")
                    jarvis_state.state.spotify_artist = track_info.get("artist", "")
                    jarvis_state.state.spotify_progress = track_info.get("progress", 0)
                    jarvis_state.state.spotify_duration = track_info.get("duration", 0)
                    jarvis_state.state.spotify_is_playing = track_info.get("is_playing", False)
                else:
                    jarvis_state.state.spotify_logged_in = True
                    jarvis_state.state.spotify_track = "No active playback"
                    jarvis_state.state.spotify_artist = "Ready to receive stream"
                    jarvis_state.state.spotify_progress = 0
                    jarvis_state.state.spotify_duration = 0
                    jarvis_state.state.spotify_is_playing = False
            else:
                jarvis_state.state.spotify_logged_in = False
                jarvis_state.state.spotify_track = ""
                jarvis_state.state.spotify_artist = ""
                jarvis_state.state.spotify_progress = 0
                jarvis_state.state.spotify_duration = 0
                jarvis_state.state.spotify_is_playing = False
        except Exception as e:
            print(f"[Spotify Poller] Error: {e}")
        time.sleep(3)

threading.Thread(target=spotify_status_poller, daemon=True).start()


# ── Power Schedules Endpoints ───────────────────────────────────────────────

@app.route("/api/power_schedules", methods=["GET"])
def get_power_schedules_endpoint():
    return jsonify(jarvis_state.state.power_schedules)

@app.route("/api/power_schedules/add", methods=["POST"])
def add_power_schedule_endpoint():
    data = request.json or {}
    action = data.get("action", "").strip().lower()
    delay_mins = data.get("delay_mins")
    
    if not action or delay_mins is None:
        return jsonify({"error": "Action and delay_mins are required"}), 400
        
    try:
        delay_mins = int(delay_mins)
    except ValueError:
        return jsonify({"error": "delay_mins must be an integer"}), 400
        
    if action not in ["shutdown", "reboot", "sleep", "hibernate"]:
        return jsonify({"error": "Invalid action"}), 400
        
    target_timestamp = time.time() + (delay_mins * 60)
    target_time_str = datetime.datetime.fromtimestamp(target_timestamp).strftime("%Y-%m-%d %H:%M:%S")
    label = f"{action.capitalize()} in {delay_mins} minute{'s' if delay_mins > 1 else ''}"
    
    current_schedules = jarvis_state.state.power_schedules
    new_schedule = {
        "id": int(time.time()),
        "action": action,
        "timestamp": target_timestamp,
        "time_str": target_time_str,
        "label": label,
        "active": True
    }
    current_schedules.append(new_schedule)
    jarvis_state.state.power_schedules = current_schedules
    
    return jsonify({"status": "success", "schedule": new_schedule})

@app.route("/api/power_schedules/delete", methods=["POST"])
def delete_power_schedule_endpoint():
    data = request.json or {}
    schedule_id = data.get("id")
    if not schedule_id:
        return jsonify({"error": "Schedule ID is required"}), 400
        
    current_schedules = jarvis_state.state.power_schedules
    current_schedules = [s for s in current_schedules if s.get("id") != schedule_id]
    jarvis_state.state.power_schedules = current_schedules
    return jsonify({"status": "success"})


# ── Power Schedule Checker Background Thread ─────────────────────────────────

def power_schedule_checker():
    while True:
        try:
            import jarvis_state
            import time
            from system_actions import shutdown_pc, reboot_pc, sleep_pc, hibernate_pc
            
            schedules = jarvis_state.state.power_schedules
            active_schedules = [s for s in schedules if s.get("active")]
            
            if active_schedules:
                now_ts = time.time()
                updated = False
                
                for s in schedules:
                    if s.get("active") and now_ts >= s.get("timestamp"):
                        s["active"] = False
                        updated = True
                        action = s.get("action")
                        print(f"\n[POWER SCHEDULE TRIGGERED: {s.get('label')}]")
                        
                        # Execute the power action with TTS warning
                        if action == "shutdown":
                            speak_web_response("Shutting down the system in five seconds. Goodbye, Sir.")
                            time.sleep(1)
                            shutdown_pc()
                        elif action == "reboot":
                            speak_web_response("Rebooting the systems in five seconds, Sir.")
                            time.sleep(1)
                            reboot_pc()
                        elif action == "sleep":
                            speak_web_response("Putting the system to sleep, Sir.")
                            time.sleep(3)
                            sleep_pc()
                        elif action == "hibernate":
                            speak_web_response("Hibernating the system, Sir.")
                            time.sleep(3)
                            hibernate_pc()
                            
                if updated:
                    jarvis_state.state.power_schedules = schedules
        except Exception as e:
            print(f"[Power Schedule Checker] Error: {e}")
        time.sleep(1)

threading.Thread(target=power_schedule_checker, daemon=True).start()


# ── Server runner ───────────────────────────────────────────────────────────


def run_server(port=5000):
    # Quiet Flask console messages
    import logging
    log = logging.getLogger("werkzeug")
    log.setLevel(logging.ERROR)
    
    print(f"[Dashboard Server] Starting on http://127.0.0.1:{port}")
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)
