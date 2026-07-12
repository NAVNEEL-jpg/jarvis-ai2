"""
control_center.py — Jarvis hardware control via InsydeDCHU.dll (Clevo Control Center 3.0)

The DLL exports five functions:
  GetDCHU_Data_Integer(command: int) -> int
  GetDCHU_Data_Buffer(command: int, buffer: bytes) -> bytes
  SetDCHU_Data(command: int, buffer: bytes, length: int) -> int
  ReadAppSettings(key: str) -> str
  WriteAppSettings(key: str, value: str) -> int

Because this DLL talks to the AcpiBridge kernel driver, it MUST be called from
a process with Administrator rights. Jarvis should be launched as admin, or this
module will catch the OSError and return a user-friendly message.

Known command IDs (reverse-engineered via opendchu / clevo-thermald):
  Keyboard backlight brightness: set=39, get=61  (value 0-5)
  Fan mode: 121  (payload[0] = mode index)
  RGB keyboard color: SetDCHU_Data with command=0 and a 12-byte buffer
    Buffer layout for single-zone:  [R, G, B, mode, 0, 0, 0, 0, 0, 0, 0, 0]
    mode byte:  0=static, 16=breath, 51=cycle, 128=dance, 144=tempo,
                160=flash, 176=wave, 240=allRGB

Fan mode values (payload[0]):
  0 = Auto (firmware default)
  1 = Max speed
  2 = Silent / Quiet
  3 = Game (balanced boost)
  4 = Battery saving (low speed)
"""

import ctypes
import os
import struct
import subprocess
import sys

# ── DLL path ─────────────────────────────────────────────────────────────────
_DLL_PRIMARY   = r"C:\Program Files (x86)\ControlCenter\InsydeDCHU.dll"
_DLL_SECONDARY = r"C:\Windows\System32\DriverStore\FileRepository\acpibridge1.inf_amd64_6172acb3e289f51f\InsydeDCHU.dll"

_dll = None  # cached DLL instance
_dll_failed = False  # if True, stop trying to reload

# ── Colour map: name → (R, G, B) ─────────────────────────────────────────────
COLOR_MAP = {
    "red":      (255, 0,   0),
    "green":    (0,   255, 0),
    "blue":     (0,   0,   255),
    "cyan":     (0,   240, 255),
    "magenta":  (255, 0,   255),
    "yellow":   (255, 255, 0),
    "orange":   (255, 127, 0),
    "purple":   (128, 0,   128),
    "violet":   (143, 0,   255),
    "white":    (255, 255, 255),
    "pink":     (255, 105, 180),
    "gold":     (255, 215, 0),
    "teal":     (0,   200, 180),
    "indigo":   (75,  0,   130),
    "lime":     (0,   255, 50),
    "off":      (0,   0,   0),
}

# ── Fan mode map: name → mode byte ───────────────────────────────────────────
FAN_MODE_MAP = {
    "auto":       0,
    "automatic":  0,
    "normal":     0,
    "max":        1,
    "maximum":    1,
    "turbo":      1,
    "full":       1,
    "silent":     2,
    "quiet":      2,
    "low":        2,
    "game":       3,
    "gaming":     3,
    "balanced":   3,
    "performance":3,
    "battery":    4,
    "power save": 4,
    "eco":        4,
    "save":       4,
}

# Friendly display names for each mode index
FAN_MODE_LABELS = {0: "Auto", 1: "Max", 2: "Silent", 3: "Game", 4: "Battery"}


def _load_dll():
    """Try to load the DLL. Returns the ctypes CDLL or None on failure."""
    global _dll, _dll_failed
    if _dll is not None:
        return _dll
    if _dll_failed:
        return None

    for path in [_DLL_PRIMARY, _DLL_SECONDARY]:
        if not os.path.exists(path):
            continue
        try:
            # Add the DLL directory so any dependent DLLs are found
            dll_dir = os.path.dirname(path)
            try:
                os.add_dll_directory(dll_dir)
            except AttributeError:
                pass  # Python < 3.8, not needed
            _dll = ctypes.WinDLL(path)
            print(f"[ControlCenter] Loaded DLL from {path}")

            # Wire up function prototypes
            _dll.SetDCHU_Data.argtypes      = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int]
            _dll.SetDCHU_Data.restype       = ctypes.c_int
            _dll.GetDCHU_Data_Integer.argtypes = [ctypes.c_int]
            _dll.GetDCHU_Data_Integer.restype  = ctypes.c_int
            _dll.GetDCHU_Data_Buffer.argtypes  = [ctypes.c_int, ctypes.c_char_p]
            _dll.GetDCHU_Data_Buffer.restype   = ctypes.c_int
            return _dll
        except OSError as e:
            print(f"[ControlCenter] Could not load {path}: {e}")

    print("[ControlCenter] DLL not found or access denied. Hardware control unavailable.")
    _dll_failed = True
    return None


def _is_admin() -> bool:
    """Return True if the current process has Administrator rights."""
    try:
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        return False


def _run_elevated_helper(args: list) -> tuple[bool, str]:
    """
    Run a tiny helper script as Admin using runas if we're not already elevated.
    Returns (success, message).
    """
    if not _is_admin():
        return False, "Jarvis is not running as Administrator. Please restart with admin rights to control hardware."

    dll = _load_dll()
    if dll is None:
        return False, "Hardware control DLL not available."
    return True, "ok"


# ── Keyboard colour ───────────────────────────────────────────────────────────

def set_keyboard_color(r: int, g: int, b: int, mode: int = 0) -> tuple[bool, str]:
    """
    Set keyboard RGB backlight.
    mode: 0=static, 16=breath, 51=cycle, 160=flash, 176=wave, 240=allRGB
    Returns (success, message).
    """
    ok, msg = _run_elevated_helper([])
    if not ok:
        return False, msg

    dll = _load_dll()
    try:
        # 12-byte buffer: [R, G, B, mode, padding × 8]
        buf = bytes([r & 0xFF, g & 0xFF, b & 0xFF, mode & 0xFF] + [0] * 8)
        result = dll.SetDCHU_Data(0, buf, len(buf))
        if result == 0:
            return True, "ok"
        return False, f"DLL returned error code {result}"
    except Exception as e:
        return False, f"DLL call failed: {e}"


def set_keyboard_color_by_name(name: str, mode: int = 0) -> tuple[bool, str]:
    """Set keyboard colour by name string. Returns (success, message)."""
    name = name.lower().strip()
    if name not in COLOR_MAP:
        return False, f"Unknown colour '{name}'. Try: {', '.join(list(COLOR_MAP)[:8])}..."
    r, g, b = COLOR_MAP[name]
    return set_keyboard_color(r, g, b, mode)


def get_keyboard_brightness() -> int:
    """Return current brightness level (0-5), or -1 on error."""
    dll = _load_dll()
    if dll is None:
        return -1
    try:
        val = dll.GetDCHU_Data_Integer(61)
        return val & 0xFF  # low byte = brightness
    except Exception:
        return -1


def set_keyboard_brightness(level: int) -> tuple[bool, str]:
    """
    Set keyboard backlight brightness.
    level: 0 (off) to 5 (max)
    """
    ok, msg = _run_elevated_helper([])
    if not ok:
        return False, msg

    dll = _load_dll()
    level = max(0, min(5, int(level)))
    try:
        buf = bytes([level, 0, 0, 0])
        result = dll.SetDCHU_Data(39, buf, len(buf))
        return (True, "ok") if result == 0 else (False, f"Error code {result}")
    except Exception as e:
        return False, f"DLL call failed: {e}"


# ── Fan control ───────────────────────────────────────────────────────────────

def set_fan_mode(mode_name: str) -> tuple[bool, str]:
    """
    Set fan mode by name. Returns (success, message).
    """
    ok, msg = _run_elevated_helper([])
    if not ok:
        return False, msg

    dll = _load_dll()
    name = mode_name.lower().strip()
    if name not in FAN_MODE_MAP:
        return False, f"Unknown fan mode '{mode_name}'. Options: {', '.join(set(FAN_MODE_MAP))}"

    mode_byte = FAN_MODE_MAP[name]
    label = FAN_MODE_LABELS.get(mode_byte, name)
    try:
        buf = bytes([mode_byte, 0, 0, 0])
        result = dll.SetDCHU_Data(121, buf, len(buf))
        return (True, label) if result == 0 else (False, f"Error code {result}")
    except Exception as e:
        return False, f"DLL call failed: {e}"


def set_fan_speed_percent(percent: int) -> tuple[bool, str]:
    """
    Set fan to a specific duty-cycle percentage (0-100).
    This maps to discrete modes:
      0-20 → Silent, 21-50 → Auto, 51-80 → Game, 81-100 → Max
    Returns (success, message).
    """
    percent = max(0, min(100, int(percent)))
    if percent <= 20:
        mode_name = "silent"
    elif percent <= 50:
        mode_name = "auto"
    elif percent <= 80:
        mode_name = "game"
    else:
        mode_name = "max"
    success, result = set_fan_mode(mode_name)
    if success:
        return True, FAN_MODE_LABELS.get(FAN_MODE_MAP[mode_name], mode_name)
    return False, result


# ── Convenience: keyboard effects ────────────────────────────────────────────

EFFECT_MAP = {
    "static":  0,
    "breath":  16,
    "cycle":   51,
    "dance":   128,
    "tempo":   144,
    "flash":   160,
    "wave":    176,
    "rainbow": 240,
    "allrgb":  240,
}

def set_keyboard_effect(effect: str, r: int = 255, g: int = 255, b: int = 255) -> tuple[bool, str]:
    """Set a keyboard lighting effect by name."""
    mode = EFFECT_MAP.get(effect.lower(), 0)
    return set_keyboard_color(r, g, b, mode)


# ── Mood-based keyboard themes ────────────────────────────────────────────────

MOOD_KEYBOARD_MAP = {
    "happy":      ("yellow",  0),   # static yellow
    "sad":        ("blue",   16),   # breathing blue
    "angry":      ("red",   160),   # flashing red
    "calm":       ("cyan",   16),   # breathing cyan
    "focused":    ("white",   0),   # static white
    "excited":    ("purple", 240),  # allRGB rainbow
    "romantic":   ("pink",   16),   # breathing pink
    "tired":      ("indigo",  0),   # dim indigo
    "energetic":  ("orange", 176),  # wave orange
    "chill":      ("teal",   16),   # breathing teal
}

def set_keyboard_mood(mood: str) -> tuple[bool, str]:
    """Set keyboard backlight to a mood-based theme."""
    mood = mood.lower().strip()
    if mood not in MOOD_KEYBOARD_MAP:
        # Default to white static for unknown moods
        color_name, mode = "white", 0
    else:
        color_name, mode = MOOD_KEYBOARD_MAP[mood]
    success, msg = set_keyboard_color_by_name(color_name, mode)
    if success:
        return True, color_name
    return False, msg
