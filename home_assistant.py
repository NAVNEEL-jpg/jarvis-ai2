import os
import requests
from dotenv import load_dotenv
load_dotenv()

HA_URL = os.environ["HA_URL"]
HA_TOKEN = os.environ["HA_TOKEN"]

def call_service(domain, service, entity_id, service_data: dict = None):
    """Call a Home Assistant service.
    
    Args:
        domain:       e.g. "light"
        service:      e.g. "turn_on", "turn_off"
        entity_id:    e.g. "light.bedroom"
        service_data: extra payload fields (rgb_color, brightness, color_temp, etc.)
    """
    url = f"{HA_URL}/api/services/{domain}/{service}"
    headers = {
        "Authorization": f"Bearer {HA_TOKEN}",
        "Content-Type": "application/json",
    }
    payload = {"entity_id": entity_id}
    if service_data:
        payload.update(service_data)

    try:
        response = requests.post(url, json=payload, headers=headers, timeout=5)
        return response.status_code == 200
    except requests.exceptions.RequestException as e:
        print(f"[HA] Request failed: {e}")
        return False


def set_light_color(entity_id, color_name: str = None, rgb: tuple = None,
                    brightness_pct: int = None):
    """Convenience wrapper — turn on a light with optional color and brightness."""
    data = {}
    if rgb:
        data["rgb_color"] = list(rgb)
    elif color_name:
        data["rgb_color"] = _color_to_rgb(color_name)
    if brightness_pct is not None:
        data["brightness_pct"] = max(0, min(100, brightness_pct))
    return call_service("light", "turn_on", entity_id, service_data=data or None)


# ── Colour name → RGB lookup ───────────────────────────────────────────────
_COLOR_MAP = {
    # ── Basic colors ──────────────────────────────────────────────────────────
    "red":          (255, 0,   0),
    "green":        (0,   255, 0),
    "blue":         (0,   0,   255),
    "white":        (255, 255, 255),
    "default":      (255, 255, 255),
    "normal":       (255, 255, 255),
    "regular":      (255, 255, 255),
    "normal white": (255, 255, 255),
    "regular white":(255, 255, 255),
    "warm white":   (255, 200, 100),
    "cool white":   (200, 220, 255),
    "yellow":       (255, 255, 0),
    "orange":       (255, 128, 0),
    "purple":       (128, 0,   128),
    "violet":       (138, 43,  226),
    "pink":         (255, 105, 180),
    "cyan":         (0,   255, 255),
    "teal":         (0,   128, 128),
    "magenta":      (255, 0,   255),
    "lime":         (0,   255, 0),
    "indigo":       (75,  0,   130),
    "lavender":     (230, 190, 255),
    "gold":         (255, 215, 0),
    "coral":        (255, 127, 80),
    "turquoise":    (64,  224, 208),
    "maroon":       (128, 0,   0),
    "navy":         (0,   0,   128),
    "sky blue":     (135, 206, 235),
    "rose":         (255, 0,   127),
    "mint":         (152, 255, 152),
    # ── Extended / scene colors ───────────────────────────────────────────────
    "hot pink":     (255, 20,  147),
    "deep blue":    (0,   0,   180),
    "light blue":   (100, 180, 255),
    "baby blue":    (137, 207, 240),
    "electric blue":(0,   120, 255),
    "royal blue":   (65,  105, 225),
    "dark blue":    (0,   0,   100),
    "aqua":         (0,   200, 200),
    "neon":         (255, 0,   200),
    "electric":     (0,   255, 255),
    "ironman":      (255, 60,  0),
    "iron man":     (255, 60,  0),
    "matrix":       (0,   255, 70),
    "ocean":        (0,   180, 255),
    "galaxy":       (100, 0,   255),
    "sunset":       (255, 80,  20),
    "fire":         (255, 50,  0),
    "lava":         (200, 30,  0),
    "ice":          (0,   230, 255),
    "aurora":       (0,   255, 180),
    "forest":       (0,   160, 40),
    "blood":        (200, 0,   0),
    "amber":        (255, 165, 0),
    "peach":        (255, 218, 185),
    "crimson":      (220, 20,  60),
    "scarlet":      (255, 36,  0),
    "emerald":      (0,   201, 87),
    "ruby":         (155, 17,  30),
    "sapphire":     (15,  82,  186),
    "jade":         (0,   168, 107),
    "bronze":       (205, 127, 50),
    "silver":       (192, 192, 192),
    "lilac":        (200, 162, 200),
    "plum":         (142, 69,  133),
}


def _color_to_rgb(name: str) -> list:
    """Return [r, g, b] for a colour name, defaulting to white."""
    return list(_COLOR_MAP.get(name.lower().strip(), (255, 255, 255)))


_active_lights_cache = None


def get_active_lights(force_refresh=False) -> list:
    """Fetch active light entity IDs from Home Assistant, fallback to empty list."""
    global _active_lights_cache
    if _active_lights_cache is not None and not force_refresh:
        return _active_lights_cache

    url = f"{HA_URL}/api/states"
    headers = {
        "Authorization": f"Bearer {HA_TOKEN}",
        "Content-Type": "application/json",
    }
    try:
        response = requests.get(url, headers=headers, timeout=2)
        if response.status_code == 200:
            _active_lights_cache = [state["entity_id"] for state in response.json() if state["entity_id"].startswith("light.")]
            return _active_lights_cache
    except Exception as e:
        print(f"[HA] Error fetching active lights: {e}")
    if _active_lights_cache is not None:
        return _active_lights_cache
    return []


def get_ha_automations() -> list:
    """Fetch all automation entity IDs from Home Assistant."""
    url = f"{HA_URL}/api/states"
    headers = {
        "Authorization": f"Bearer {HA_TOKEN}",
        "Content-Type": "application/json",
    }
    try:
        response = requests.get(url, headers=headers, timeout=2)
        if response.status_code == 200:
            return [state["entity_id"] for state in response.json() if state["entity_id"].startswith("automation.")]
    except Exception as e:
        print(f"[HA] Error fetching automations: {e}")
    return []


_active_switches_cache = None


def get_active_switches(force_refresh=False) -> list:
    """Fetch active switch/plug entity IDs from Home Assistant, fallback to empty list."""
    global _active_switches_cache
    if _active_switches_cache is not None and not force_refresh:
        return _active_switches_cache

    url = f"{HA_URL}/api/states"
    headers = {
        "Authorization": f"Bearer {HA_TOKEN}",
        "Content-Type": "application/json",
    }
    try:
        response = requests.get(url, headers=headers, timeout=2)
        if response.status_code == 200:
            _active_switches_cache = [state["entity_id"] for state in response.json() if state["entity_id"].startswith("switch.")]
            return _active_switches_cache
    except Exception as e:
        print(f"[HA] Error fetching active switches: {e}")
    if _active_switches_cache is not None:
        return _active_switches_cache
    return []