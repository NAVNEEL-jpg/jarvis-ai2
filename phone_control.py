"""
phone_control.py — Android phone automation for J.A.R.V.I.S.

Primary transport: ADB (Android Debug Bridge) over Wi-Fi.
Fallback transport: HTTP to a Flask server running on Termux on the phone.

Setup (ADB Wi-Fi):
  1. On your phone: Settings → Developer Options → Wireless debugging → ON
  2. Note the IP and port shown (e.g. 192.168.1.5:5555)
  3. Run once on PC: adb connect 192.168.1.5:5555
  4. Set PHONE_ADB_TARGET=192.168.1.5:5555 in your .env file

Setup (Termux fallback — optional):
  1. Install Termux on Android → run: pip install flask && python termux_server.py
  2. Set PHONE_HTTP_URL=http://192.168.1.5:8765 in your .env file
"""

import os
import re
import subprocess
import requests
from dotenv import load_dotenv

load_dotenv()

# ── Config ────────────────────────────────────────────────────────────────────
_ADB_TARGET = os.environ.get("PHONE_ADB_TARGET", "")           # e.g. "192.168.1.5:5555"
_HTTP_URL   = os.environ.get("PHONE_HTTP_URL", "").rstrip("/") # e.g. "http://192.168.1.5:8765"

# Resolve adb binary — use PATH if available, fall back to the known WinGet install path
_ADB_FALLBACK = (
    r"C:\Users\admin\AppData\Local\Microsoft\WinGet\Packages"
    r"\Google.PlatformTools_Microsoft.Winget.Source_8wekyb3d8bbwe"
    r"\platform-tools\adb.exe"
)

def _find_adb() -> str:
    """Return the adb executable path, preferring PATH, falling back to WinGet location."""
    import shutil
    found = shutil.which("adb")
    if found:
        return found
    if os.path.isfile(_ADB_FALLBACK):
        return _ADB_FALLBACK
    return "adb"  # let it fail naturally with a clear error

_ADB_EXE = _find_adb()


# Map of spoken app names → Android package name
APP_PACKAGE_MAP = {
    "whatsapp":          "com.whatsapp",
    "youtube":           "com.google.android.youtube",
    "instagram":         "com.instagram.android",
    "chrome":            "com.android.chrome",
    "google chrome":     "com.android.chrome",
    "camera":            "com.android.camera2",
    "gallery":           "com.google.android.apps.photos",
    "photos":            "com.google.android.apps.photos",
    "maps":              "com.google.android.apps.maps",
    "google maps":       "com.google.android.apps.maps",
    "spotify":           "com.spotify.music",
    "gmail":             "com.google.android.gm",
    "settings":          "com.android.settings",
    "phone":             "com.google.android.dialer",
    "dialer":            "com.google.android.dialer",
    "contacts":          "com.google.android.contacts",
    "messages":          "com.google.android.apps.messaging",
    "facebook":          "com.facebook.katana",
    "twitter":           "com.twitter.android",
    "x":                 "com.twitter.android",
    "telegram":          "org.telegram.messenger",
    "snapchat":          "com.snapchat.android",
    "calculator":        "com.google.android.calculator",
    "clock":             "com.google.android.deskclock",
    "alarm":             "com.google.android.deskclock",
    "files":             "com.google.android.documentsui",
    "play store":        "com.android.vending",
    "netflix":           "com.netflix.mediaclient",
    "amazon":            "in.amazon.mShop.android.shopping",
    "flipkart":          "com.flipkart.android",
    "swiggy":            "in.swiggy.android",
    "zomato":            "com.application.zomato",
    "paytm":             "net.one97.paytm",
    "phonepe":           "com.phonepe.app",
    "gpay":              "com.google.android.apps.nbu.paisa.user",
    "google pay":        "com.google.android.apps.nbu.paisa.user",
    "keep":              "com.google.android.keep",
    "google keep":       "com.google.android.keep",
}


# ── ADB helpers ───────────────────────────────────────────────────────────────

def _adb_run(args: list, timeout: int = 8) -> tuple:
    """Run an adb command. Returns (success: bool, output: str)."""
    cmd = [_ADB_EXE]
    if _ADB_TARGET:
        cmd += ["-s", _ADB_TARGET]
    cmd += args
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        output = (result.stdout + result.stderr).strip()
        return result.returncode == 0, output
    except FileNotFoundError:
        return False, "ADB is not installed, Sir. Android Platform Tools must be added to your PATH."
    except subprocess.TimeoutExpired:
        return False, "The ADB command timed out, Sir."
    except Exception as e:
        return False, str(e)


def _adb_shell(shell_cmd: str, timeout: int = 8) -> tuple:
    """Run: adb shell <shell_cmd>. Returns (success, output)."""
    return _adb_run(["shell"] + shell_cmd.split(), timeout=timeout)


def is_adb_connected() -> bool:
    """Return True if the ADB target device is reachable right now."""
    ok, out = _adb_run(["devices"])
    if not ok:
        return False
    if _ADB_TARGET:
        return _ADB_TARGET in out and "device" in out
    # Any connected device
    return len([l for l in out.splitlines() if "\tdevice" in l]) > 0


def adb_connect() -> str:
    """Attempt to connect to the phone via ADB over Wi-Fi."""
    if not _ADB_TARGET:
        return "PHONE_ADB_TARGET is not set in your environment, Sir. Please add your phone's IP and port to the .env file."
    ok, out = _adb_run(["connect", _ADB_TARGET])
    if ok and ("connected" in out or "already" in out):
        return f"Your phone is online, Sir. ADB linked at {_ADB_TARGET}."
    return f"I was unable to reach your phone, Sir. ADB reported: {out}"


# ── HTTP fallback (Termux) ────────────────────────────────────────────────────

def _http_send(endpoint: str, payload: dict, timeout: int = 5) -> tuple:
    """POST a command to the Termux Flask server. Returns (success, message)."""
    if not _HTTP_URL:
        return False, "PHONE_HTTP_URL not set in .env."
    try:
        r = requests.post(f"{_HTTP_URL}{endpoint}", json=payload, timeout=timeout)
        if r.status_code == 200:
            return True, r.json().get("message", "OK")
        return False, f"HTTP {r.status_code}: {r.text}"
    except requests.ConnectionError:
        return False, "I cannot reach the Termux server on your phone, Sir. Please ensure it is running."
    except Exception as e:
        return False, str(e)


# ── Universal dispatcher ──────────────────────────────────────────────────────

def _auto_connect() -> bool:
    """Silently try adb connect if the target is configured but not currently connected."""
    if not _ADB_TARGET:
        return False
    ok, out = _adb_run(["connect", _ADB_TARGET])
    connected = ok and ("connected" in out or "already" in out)
    if connected:
        print(f"[Phone/ADB] Auto-reconnected to {_ADB_TARGET}")
    return connected


def _execute(adb_args: list, http_endpoint: str, http_payload: dict,
             success_msg: str, fail_prefix: str = "Phone action failed") -> str:
    """Try ADB first; if disconnected try auto-reconnect; then fall back to HTTP."""
    if is_adb_connected():
        ok, out = _adb_run(adb_args)
        if ok:
            print(f"[Phone/ADB] {' '.join(adb_args[:4])}")
            return success_msg
        print(f"[Phone/ADB] Failed: {out}. Trying HTTP fallback...")
    else:
        # Not connected — try silent auto-reconnect first
        print("[Phone/ADB] Not connected. Attempting auto-reconnect...")
        if _auto_connect() and is_adb_connected():
            ok, out = _adb_run(adb_args)
            if ok:
                return success_msg
        print("[Phone/ADB] Auto-reconnect failed. Trying HTTP fallback...")

    ok, out = _http_send(http_endpoint, http_payload)
    if ok:
        print(f"[Phone/HTTP] {http_endpoint}")
        return success_msg
    return f"{fail_prefix}: {out}"


# ── Public API ────────────────────────────────────────────────────────────────

def open_app_on_phone(app_name: str) -> str:
    """Open an Android app by its friendly spoken name."""
    name = app_name.lower().strip()
    package = APP_PACKAGE_MAP.get(name)

    if not package:
        for key, pkg in APP_PACKAGE_MAP.items():
            if key in name or name in key:
                package = pkg
                name = key
                break

    if not package:
        return (f"I don't have '{app_name}' in my registry, Sir. "
                f"You may add it to APP_PACKAGE_MAP in phone_control.py.")

    adb_args = [
        "shell", "monkey", "-p", package,
        "-c", "android.intent.category.LAUNCHER", "1"
    ]
    return _execute(
        adb_args=adb_args,
        http_endpoint="/open_app",
        http_payload={"package": package},
        success_msg=f"Launching {name.title()} on your phone, Sir.",
        fail_prefix=f"I was unable to launch {name.title()}, Sir"
    )


def make_call(number: str) -> str:
    """Dial a phone number from Jarvis voice command."""
    clean_number = re.sub(r"[^\d+]", "", number)
    if not clean_number:
        return "I couldn't extract a valid number from that, Sir. Please state it clearly."

    adb_args = [
        "shell", "am", "start",
        "-a", "android.intent.action.CALL",
        "-d", f"tel:{clean_number}"
    ]
    return _execute(
        adb_args=adb_args,
        http_endpoint="/call",
        http_payload={"number": clean_number},
        success_msg=f"Placing a call to {clean_number} now, Sir.",
        fail_prefix="I was unable to place the call, Sir"
    )


def set_alarm_on_phone(hour: int, minute: int = 0, message: str = "Jarvis Alarm") -> str:
    """Set an alarm on the Android phone's clock app."""
    adb_args = [
        "shell", "am", "start",
        "-a", "android.intent.action.SET_ALARM",
        "--ei", "android.intent.extra.alarm.HOUR", str(hour),
        "--ei", "android.intent.extra.alarm.MINUTES", str(minute),
        "--es", "android.intent.extra.alarm.MESSAGE", message,
        "--ez", "android.intent.extra.alarm.SKIP_UI", "true"
    ]
    ampm = "AM" if hour < 12 else "PM"
    disp_hour = hour if 0 < hour <= 12 else (hour - 12 if hour > 12 else 12)
    return _execute(
        adb_args=adb_args,
        http_endpoint="/set_alarm",
        http_payload={"hour": hour, "minute": minute, "message": message},
        success_msg=f"Alarm set for {disp_hour}:{minute:02d} {ampm} on your phone, Sir.",
        fail_prefix="I was unable to set the alarm on your phone, Sir"
    )


def open_chrome_on_phone(url: str) -> str:
    """Open a URL in Chrome on the phone."""
    if not url.startswith("http"):
        url = "https://" + url
    adb_args = [
        "shell", "am", "start",
        "-a", "android.intent.action.VIEW",
        "-d", url,
        "-n", "com.android.chrome/com.google.android.apps.chrome.Main"
    ]
    return _execute(
        adb_args=adb_args,
        http_endpoint="/open_url",
        http_payload={"url": url},
        success_msg=f"Pulling up {url} in Chrome on your phone, Sir.",
        fail_prefix="I was unable to open Chrome on your phone, Sir"
    )


def google_search_on_phone(query: str) -> str:
    """Perform a Google search in Chrome on the phone."""
    encoded = query.replace(" ", "+")
    # Override success message to mention the query, not the raw URL
    import re as _re
    adb_args = [
        "shell", "am", "start",
        "-a", "android.intent.action.VIEW",
        "-d", f"https://www.google.com/search?q={encoded}",
        "-n", "com.android.chrome/com.google.android.apps.chrome.Main"
    ]
    return _execute(
        adb_args=adb_args,
        http_endpoint="/open_url",
        http_payload={"url": f"https://www.google.com/search?q={encoded}"},
        success_msg=f"Searching for '{query}' on your phone, Sir.",
        fail_prefix="I was unable to open Chrome for that search, Sir"
    )


def set_phone_volume(level: int) -> str:
    """Set the phone's media volume (0-15 scale)."""
    level = max(0, min(15, level))
    adb_args = [
        "shell", "media", "volume",
        "--set", str(level),
        "--stream", "3"   # STREAM_MUSIC
    ]
    return _execute(
        adb_args=adb_args,
        http_endpoint="/set_volume",
        http_payload={"level": level},
        success_msg=f"Phone volume adjusted to {level}, Sir.",
        fail_prefix="I was unable to adjust the phone volume, Sir"
    )


def send_whatsapp_message(contact: str, message: str) -> str:
    """
    Open WhatsApp with a message pre-filled.
    Contact can be a phone number (with country code, e.g. +91XXXXXXXXXX).
    """
    clean_number = re.sub(r"[^\d+]", "", contact)
    if clean_number:
        url = f"https://api.whatsapp.com/send?phone={clean_number}&text={message.replace(' ', '%20')}"
    else:
        url = f"https://api.whatsapp.com/send?text={message.replace(' ', '%20')}"

    adb_args = [
        "shell", "am", "start",
        "-a", "android.intent.action.VIEW",
        "-d", url
    ]
    return _execute(
        adb_args=adb_args,
        http_endpoint="/whatsapp",
        http_payload={"contact": contact, "message": message},
        success_msg="WhatsApp is open with your message ready to send, Sir.",
        fail_prefix="I was unable to open WhatsApp, Sir"
    )


def take_phone_screenshot() -> str:
    """Take a screenshot on the phone and pull it to the Jarvis directory."""
    remote = "/sdcard/jarvis_screenshot.png"
    ok, out = _adb_run(["shell", "screencap", "-p", remote])
    if not ok:
        return f"I was unable to capture a screenshot from your phone, Sir. {out}"
    local = os.path.join(os.path.dirname(os.path.abspath(__file__)), "phone_screenshot.png")
    ok2, out2 = _adb_run(["pull", remote, local])
    if ok2:
        return "Screenshot captured and saved to the Jarvis directory, Sir."
    return f"Screenshot taken on the phone but I could not pull it to the PC, Sir. {out2}"


def get_phone_battery() -> str:
    """Get the phone's current battery level."""
    ok, out = _adb_run(["shell", "dumpsys", "battery"])
    if ok:
        m = re.search(r"level:\s*(\d+)", out)
        if m:
            level = m.group(1)
            sm = re.search(r"status:\s*(\d+)", out)
            status_map = {"2": "charging", "3": "discharging", "4": "not charging", "5": "fully charged"}
            status = status_map.get(sm.group(1) if sm else "", "status unknown")
            return f"Your phone battery is at {level}% and currently {status}, Sir."
    return "I was unable to retrieve the battery status from your phone, Sir."


def lock_phone() -> str:
    """Lock the phone screen."""
    ok, out = _adb_run(["shell", "input", "keyevent", "26"])  # KEYCODE_POWER
    return "Phone screen locked, Sir." if ok else f"I was unable to lock the phone, Sir. {out}"


def wake_phone() -> str:
    """Wake the phone screen without unlocking."""
    ok, out = _adb_run(["shell", "input", "keyevent", "224"])  # KEYCODE_WAKEUP
    return "Phone screen is awake, Sir." if ok else f"I was unable to wake the phone, Sir. {out}"


def go_home_on_phone() -> str:
    """Navigate back to the phone's home screen."""
    adb_args = ["shell", "input", "keyevent", "3"]  # KEYCODE_HOME
    return _execute(
        adb_args=adb_args,
        http_endpoint="/go_home",
        http_payload={},
        success_msg="Navigating to your home screen, Sir.",
        fail_prefix="I was unable to go to the home screen, Sir"
    )


def go_back_on_phone() -> str:
    """Go back to the previous screen or page on the phone."""
    adb_args = ["shell", "input", "keyevent", "4"]  # KEYCODE_BACK
    return _execute(
        adb_args=adb_args,
        http_endpoint="/go_back",
        http_payload={},
        success_msg="Going back, Sir.",
        fail_prefix="I was unable to go back, Sir"
    )


def refresh_page_on_phone() -> str:
    """Refresh the current browser page or app feed on the phone."""
    # We do a swipe down gesture from the middle-top to middle-bottom to refresh pages
    # Swipe from (500, 400) to (500, 1200) over 300ms
    adb_args = ["shell", "input", "swipe", "500", "400", "500", "1200", "300"]
    return _execute(
        adb_args=adb_args,
        http_endpoint="/refresh",
        http_payload={},
        success_msg="Refreshing the page, Sir.",
        fail_prefix="I was unable to refresh the page, Sir"
    )


def phone_status() -> str:
    """Return a quick summary of phone connection and battery."""
    if is_adb_connected():
        return get_phone_battery()
    if _HTTP_URL:
        ok, _ = _http_send("/ping", {})
        if ok:
            return "Your phone is online via the Termux server, Sir."
    return ("Your phone does not appear to be connected, Sir. "
            "Say 'connect phone' and I will attempt to link it.")
