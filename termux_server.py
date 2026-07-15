"""
termux_server.py — Jarvis phone control HTTP server for Termux (Android)

HOW TO SET UP ON YOUR PHONE:
  1. Install Termux from F-Droid (NOT Play Store)
  2. In Termux, run:
       pkg update && pkg install python
       pip install flask
  3. Copy this file to your phone (e.g. via adb push or just type it out)
  4. Run:  python termux_server.py
  5. Note your phone IP (run: ip addr show wlan0 | grep inet)
  6. Set PHONE_HTTP_URL=http://<your-ip>:8765 in Jarvis .env on your PC

Supports: open_app, call, set_alarm, open_url, set_volume, whatsapp, ping
"""

import subprocess
from flask import Flask, request, jsonify

app = Flask(__name__)


def run_am(intent_args: list) -> tuple:
    """Run: am start <intent_args> and return (success, output)."""
    try:
        result = subprocess.run(
            ["am", "start"] + intent_args,
            capture_output=True, text=True, timeout=10
        )
        return result.returncode == 0, result.stdout + result.stderr
    except Exception as e:
        return False, str(e)


@app.route("/ping", methods=["POST"])
def ping():
    return jsonify({"status": "ok", "message": "Termux server alive"})


@app.route("/open_app", methods=["POST"])
def open_app():
    data = request.get_json()
    package = data.get("package", "")
    if not package:
        return jsonify({"error": "No package provided"}), 400
    ok, out = run_am(["-n", f"{package}/.MainActivity",
                      "-c", "android.intent.category.LAUNCHER"])
    if not ok:
        # Fallback: monkey launch
        try:
            r = subprocess.run(["monkey", "-p", package, "-c",
                                 "android.intent.category.LAUNCHER", "1"],
                                capture_output=True, text=True, timeout=10)
            ok = r.returncode == 0
            out = r.stdout + r.stderr
        except Exception as e:
            out = str(e)
    return jsonify({"status": "ok" if ok else "error", "message": out})


@app.route("/call", methods=["POST"])
def call():
    data = request.get_json()
    number = data.get("number", "")
    if not number:
        return jsonify({"error": "No number provided"}), 400
    ok, out = run_am(["-a", "android.intent.action.CALL",
                      "-d", f"tel:{number}"])
    return jsonify({"status": "ok" if ok else "error", "message": out})


@app.route("/set_alarm", methods=["POST"])
def set_alarm():
    data = request.get_json()
    hour   = int(data.get("hour", 7))
    minute = int(data.get("minute", 0))
    msg    = data.get("message", "Jarvis Alarm")
    ok, out = run_am([
        "-a", "android.intent.action.SET_ALARM",
        "--ei", "android.intent.extra.alarm.HOUR", str(hour),
        "--ei", "android.intent.extra.alarm.MINUTES", str(minute),
        "--es", "android.intent.extra.alarm.MESSAGE", msg,
        "--ez", "android.intent.extra.alarm.SKIP_UI", "true"
    ])
    return jsonify({"status": "ok" if ok else "error", "message": out})


@app.route("/open_url", methods=["POST"])
def open_url():
    data = request.get_json()
    url = data.get("url", "")
    if not url:
        return jsonify({"error": "No URL provided"}), 400
    ok, out = run_am([
        "-a", "android.intent.action.VIEW",
        "-d", url,
        "-n", "com.android.chrome/com.google.android.apps.chrome.Main"
    ])
    return jsonify({"status": "ok" if ok else "error", "message": out})


@app.route("/set_volume", methods=["POST"])
def set_volume():
    data = request.get_json()
    level  = int(data.get("level", 5))
    stream = int(data.get("stream", 3))
    try:
        r = subprocess.run(
            ["media", "volume", "--set", str(level), "--stream", str(stream)],
            capture_output=True, text=True, timeout=5
        )
        return jsonify({"status": "ok", "message": r.stdout})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/whatsapp", methods=["POST"])
def whatsapp():
    data = request.get_json()
    contact = data.get("contact", "")
    message = data.get("message", "")
    number  = "".join(c for c in contact if c.isdigit() or c == "+")
    if number:
        url = f"https://api.whatsapp.com/send?phone={number}&text={message.replace(' ', '%20')}"
    else:
        url = f"https://api.whatsapp.com/send?text={message.replace(' ', '%20')}"
    ok, out = run_am(["-a", "android.intent.action.VIEW", "-d", url])
    return jsonify({"status": "ok" if ok else "error", "message": out})


@app.route("/go_home", methods=["POST"])
def go_home():
    try:
        r = subprocess.run(["input", "keyevent", "3"], capture_output=True, text=True, timeout=5)
        return jsonify({"status": "ok", "message": r.stdout})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/go_back", methods=["POST"])
def go_back():
    try:
        r = subprocess.run(["input", "keyevent", "4"], capture_output=True, text=True, timeout=5)
        return jsonify({"status": "ok", "message": r.stdout})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/refresh", methods=["POST"])
def refresh():
    try:
        r = subprocess.run(["input", "swipe", "500", "400", "500", "1200", "300"], capture_output=True, text=True, timeout=5)
        return jsonify({"status": "ok", "message": r.stdout})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


if __name__ == "__main__":
    print("Jarvis Termux server starting on port 8765...")
    print("Find your IP with: ip addr show wlan0 | grep inet")
    app.run(host="0.0.0.0", port=8765, debug=False)
