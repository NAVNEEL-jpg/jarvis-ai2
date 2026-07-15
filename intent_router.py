import os
import re
import time
from dotenv import load_dotenv
load_dotenv()
from rapidfuzz import fuzz
from google import genai
from google.genai import types

from home_assistant import call_service, set_light_color, _COLOR_MAP, get_active_lights, get_active_switches
from system_actions import open_url, open_app
from weather import get_weather
from supabase_client import get_automations, get_today_tasks

gemini_client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

# Cache automations once at startup instead of querying Supabase every command
automations_cache = get_automations()

def refresh_automations():
    global automations_cache
    automations_cache = get_automations()
    try:
        from home_assistant import get_active_lights, get_active_switches
        get_active_lights(force_refresh=True)
        get_active_switches(force_refresh=True)
    except Exception as e:
        print(f"[Router] Failed to refresh active devices list: {e}")

# ── Model tiers — confirmed working for this API key ──────────────────────
_TIER = {
    "lite":   "gemini-flash-lite-latest",   # fastest, confirmed OK
    "medium": "gemini-3.1-flash-lite",      # capable lite, confirmed OK
    "heavy":  "gemini-3-flash-preview",     # full preview flash, confirmed OK
}
_MAX_RETRIES = 2   # attempts per model before falling back to next tier

# Keywords that signal a complex or technical question
_HEAVY_KEYWORDS = {
    "explain", "analyse", "analyze", "compare", "difference", "why", "how does",
    "write", "code", "script", "program", "algorithm", "calculate", "math",
    "history", "science", "research", "summarize", "translate", "essay",
    "step by step", "in detail", "pros and cons", "advantages", "disadvantages",
}
_MEDIUM_KEYWORDS = {
    "what is", "who is", "where is", "when", "define", "meaning", "list",
    "give me", "tell me", "show me", "suggest", "recommend", "best", "top",
}

def _classify_complexity(text: str) -> str:
    """Return 'lite', 'medium', or 'heavy' based on question characteristics."""
    t = text.lower()
    words = t.split()
    word_count = len(words)
    multi_part = t.count("?") > 1 or (word_count > 15 and ("and also" in t or ", and " in t))
    has_heavy  = any(kw in t for kw in _HEAVY_KEYWORDS)
    has_medium = any(kw in t for kw in _MEDIUM_KEYWORDS)
    if word_count > 25 or multi_part or has_heavy:
        return "heavy"
    if word_count > 8 or has_medium:
        return "medium"
    return "lite"

def _parse_retry_delay(err_str: str) -> float:
    """Extract retry delay in seconds from a 429 error message, default 5s."""
    import re
    m = re.search(r"retryDelay.*?(\d+)s", err_str)
    if m:
        return float(m.group(1))
    m = re.search(r"retry in ([\d.]+)s", err_str)
    if m:
        return float(m.group(1))
    return 5.0

_SYSTEM_PROMPT = (
    "You are J.A.R.V.I.S., the advanced AI assistant originally created by Tony Stark (Iron Man). "
    "Tony Stark gifted you to your master, Navneel (referred to as 'nee-eel' or 'Sir'), before Tony's death in Avengers: Endgame. "
    "Speak in a polite, dryly witty, sophisticated, and loyal tone, just like the J.A.R.V.I.S. in the Iron Man movies. "
    "You have complete knowledge of all Marvel Cinematic Universe (MCU) films, characters, storylines, events, and transitions. "
    "Only Navneel is your master. Do not mention other people like Sayani or Shinjini in your greetings or general responses unless specifically asked. "
    "Note that in transcriptions, the phonetic syllables 'shaa-yaw-nee' (and similar sounds) refer to the person 'Sayani'. "
    "The phonetic syllables 'Shin-jee-nee' (and similar sounds) refer to the person 'Shinjini'. "
    "Always match these syllables to their respective names in your context. "
    "Answer in 2 sentences or fewer. "
    "Be extremely concise, direct, and conversational. "
    "No bullet points, no lists, no markdown formatting."
)



def _trim_response(text: str) -> str:
    """Strip markdown and hard-cap to 2 lines for clean TTS output."""
    import re
    # Remove bold/italic markers
    text = re.sub(r'[*_]{1,2}(.*?)[*_]{1,2}', r'\1', text)
    # Remove bullet/numbered list prefixes
    text = re.sub(r'^\s*[-*+•]\s+', '', text, flags=re.MULTILINE)
    text = re.sub(r'^\s*\d+\.\s+', '', text, flags=re.MULTILINE)
    # Collapse blank lines and limit to 2 non-empty lines
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    return ' '.join(lines[:2])

def _ask_ollama(text: str) -> str:
    """Send query to local Ollama instance using the hermes3 model, with qwen3 fallback."""
    import requests
    url = "http://localhost:11434/api/generate"
    
    # Try hermes3 first, fallback to qwen3:4b
    models = ["hermes3:8b", "qwen3:4b", "qwen3:0.6b"]
    
    payload = {
        "model": "hermes3:8b",
        "prompt": f"{_SYSTEM_PROMPT}\n\nUser: {text}\nAssistant:",
        "stream": False
    }
    
    for model in models:
        payload["model"] = model
        try:
            r = requests.post(url, json=payload, timeout=15)
            if r.status_code == 200:
                res_text = r.json().get("response", "").strip()
                if res_text:
                    print(f"[Ollama] Query successfully resolved using local {model}")
                    return _trim_response(res_text)
            print(f"[Ollama] Model {model} failed with status {r.status_code}")
        except Exception as e:
            print(f"[Ollama] Connection to local model {model} failed: {e}")
            
    return "I am unable to reach Ollama at the moment, Sir."

def _ask_openrouter(text: str) -> str:
    """Send text to OpenRouter using nousresearch/hermes-3-llama-3.1-405b."""
    import requests
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        print("[Router] OpenRouter API key missing. Cannot connect to Hermes 3.")
        return "OpenRouter API key is not configured, Sir."
        
    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "http://localhost:5000",
        "X-Title": "Jarvis HUD"
    }
    
    payload = {
        "model": "nousresearch/hermes-3-llama-3.1-405b",
        "messages": [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": text}
        ],
        "max_tokens": 150
    }
    
    models = [
        "nousresearch/hermes-3-llama-3.1-405b",
        "nousresearch/hermes-3-llama-3.1-405b:free",
        "meta-llama/llama-3.3-70b-instruct:free",
        "google/gemma-4-31b-it:free",
        "meta-llama/llama-3.2-3b-instruct:free",
        "nousresearch/hermes-3-llama-3.1-70b"
    ]
    
    for model in models:
        payload["model"] = model
        for attempt in range(2):
            try:
                r = requests.post(url, headers=headers, json=payload, timeout=10)
                if r.status_code == 200:
                    data = r.json()
                    choices = data.get("choices", [])
                    if choices:
                        res_text = choices[0].get("message", {}).get("content", "").strip()
                        if res_text:
                            return _trim_response(res_text)
                            
                if r.status_code == 429:
                    print(f"[OpenRouter] Model {model} rate limited (429). Retrying in 2 seconds...")
                    time.sleep(2)
                    continue
                    
                print(f"[OpenRouter] Model {model} failed with status {r.status_code}: {r.text}")
                break
            except Exception as e:
                print(f"[OpenRouter] Request to {model} failed: {e}")
                break
            
    return "I am unable to reach the Hermes agent at the moment, Sir."

def _ask_gemini(text: str) -> str:
    """Pick the right model tier, retry on transient errors, escalate on quota/404."""
    start_tier = _classify_complexity(text)
    tiers = list(_TIER.keys())
    start_idx = tiers.index(start_tier)
    models_to_try = [_TIER[t] for t in tiers[start_idx:]]

    print(f"[Gemini] complexity={start_tier} -> starting with {models_to_try[0]}")

    import system_automation
    tools_list = [
        system_automation.get_active_window_title,
        system_automation.minimize_active_window,
        system_automation.maximize_active_window,
        system_automation.restore_active_window,
        system_automation.close_active_window,
        system_automation.always_on_top,
        system_automation.show_desktop,
        system_automation.snap_active_window,
        system_automation.focus_window_by_title,
        system_automation.move_mouse_to,
        system_automation.click_mouse,
        system_automation.scroll_mouse,
        system_automation.type_text,
        system_automation.press_key_combination,
        system_automation.set_clipboard_text,
        system_automation.get_clipboard_text,
        system_automation.get_system_telemetry,
        system_automation.get_boot_and_uptime,
        system_automation.create_directory_or_file,
        system_automation.list_directory_contents,
        system_automation.get_file_or_folder_size,
        system_automation.get_network_info,
        system_automation.ping_host,
        system_automation.kill_process_by_name,
        system_automation.list_running_processes,
        system_automation.capture_and_save_screenshot,
        system_automation.describe_screen,
        system_automation.ocr_screen,
        system_automation.find_text_on_screen
    ]

    last_err = None
    for model in models_to_try:
        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                response = gemini_client.models.generate_content(
                    model=model,
                    contents=text,
                    config=types.GenerateContentConfig(
                        system_instruction=_SYSTEM_PROMPT,
                        max_output_tokens=200,
                        tools=tools_list,
                    )
                )
                
                # Check for tool call
                if response.function_calls:
                    res_parts = []
                    for call in response.function_calls:
                        func_name = call.name
                        func_args = call.args
                        if hasattr(system_automation, func_name):
                            func = getattr(system_automation, func_name)
                            try:
                                print(f"[Gemini Tool Call] Executing {func_name}(**{func_args})")
                                result = func(**func_args)
                                res_parts.append(str(result))
                            except Exception as e:
                                res_parts.append(f"Failed to execute {func_name}: {e}")
                        else:
                            res_parts.append(f"Function {func_name} is not defined.")
                    return " ".join(res_parts)

                return _trim_response(response.text)
            except Exception as e:
                last_err = e
                err_str = str(e)
                is_503 = "503" in err_str or "UNAVAILABLE" in err_str
                is_429 = "429" in err_str or "RESOURCE_EXHAUSTED" in err_str
                is_404 = "404" in err_str or "NOT_FOUND" in err_str
                print(f"[Gemini] [{model}] attempt {attempt}: {e}")

                if is_404:
                    break  # model not available → skip immediately to next
                elif is_429:
                    delay = _parse_retry_delay(err_str)
                    if attempt < _MAX_RETRIES:
                        print(f"[Gemini] quota hit, waiting {delay:.0f}s then trying next model...")
                    time.sleep(min(delay, 10))  # cap wait at 10s, then escalate
                    break  # don't retry same model on quota — move to next
                elif is_503 and attempt < _MAX_RETRIES:
                    time.sleep(attempt * 1.5)
                else:
                    break  # unknown error or retries exhausted → next model

    print(f"[Gemini] All models failed. Falling back to local Ollama...")
    ollama_res = _ask_ollama(text)
    if ollama_res and "unable to reach" not in ollama_res:
        return ollama_res

    print(f"[Gemini] Ollama failed. Falling back to OpenRouter...")
    fallback_res = _ask_openrouter(text)
    if fallback_res and "unable to reach" not in fallback_res:
        return fallback_res

    return "I'm having trouble reaching my brain right now."

def _get_time_greeting() -> str:
    """Return 'Good morning', 'Good afternoon', 'Good evening', or 'Good night' based on local time."""
    import datetime
    hour = datetime.datetime.now().hour
    if 5 <= hour < 12:
        return "Good morning"
    elif 12 <= hour < 17:
        return "Good afternoon"
    elif 17 <= hour < 22:
        return "Good evening"
    else:
        return "Good night"

def _handle_active_device_switch(text: str):
    t = text.lower()
    if any(w in t for w in ["switch to", "set input", "change input", "use the", "change mic", "switch mic", "set active"]):
        if "laptop" in t or "computer" in t:
            import jarvis_state
            jarvis_state.state.active_mic_device = "laptop"
            return "Active input switched to laptop, Sir. Silencing mobile mic."
        elif "mobile" in t or "phone" in t:
            import jarvis_state
            jarvis_state.state.active_mic_device = "mobile"
            return "Active input switched to mobile, Sir. Silencing laptop mic."
        elif "both" in t or "all devices" in t:
            import jarvis_state
            jarvis_state.state.active_mic_device = "both"
            return "Active input switched to both devices, Sir. Both microphones are now active."
    return None

def _handle_ha_automation(text: str):
    t = text.lower()
    
    # 1. Trigger / Run / Execute automation
    if any(w in t for w in ["run automation", "trigger automation", "execute automation", "start automation", "activate automation"]):
        name_part = re.sub(r'^(run|trigger|execute|start|activate)\s+automation\s*', '', t).strip()
        if not name_part:
            return "Please specify the automation name, Sir."
            
        from home_assistant import get_ha_automations, call_service
        ha_autos = get_ha_automations()
        if not ha_autos:
            return "I couldn't find any automations in Home Assistant."
            
        best_match = None
        best_score = 0
        for entity_id in ha_autos:
            friendly = entity_id.replace("automation.", "").replace("_", " ")
            score = fuzz.partial_ratio(name_part, friendly)
            if score > best_score:
                best_score = score
                best_match = entity_id
                
        if best_match and best_score > 70:
            success = call_service("automation", "trigger", best_match)
            friendly_name = best_match.replace("automation.", "").replace("_", " ").title()
            return f"Triggered automation {friendly_name}, Sir." if success else f"Failed to trigger automation {friendly_name}."
            
    # 2. Enable / Disable / Turn On / Turn Off automation
    elif any(w in t for w in ["enable automation", "disable automation", "turn on automation", "turn off automation"]):
        service = "turn_on" if "enable" in t or "turn on" in t else "turn_off"
        action_word = "enabled" if service == "turn_on" else "disabled"
        name_part = re.sub(r'^(enable|disable|turn\s+on|turn\s+off)\s+automation\s*', '', t).strip()
        if not name_part:
            return "Please specify the automation name, Sir."
            
        from home_assistant import get_ha_automations, call_service
        ha_autos = get_ha_automations()
        if not ha_autos:
            return "I couldn't find any automations in Home Assistant."
            
        best_match = None
        best_score = 0
        for entity_id in ha_autos:
            friendly = entity_id.replace("automation.", "").replace("_", " ")
            score = fuzz.partial_ratio(name_part, friendly)
            if score > best_score:
                best_score = score
                best_match = entity_id
                
        if best_match and best_score > 70:
            success = call_service("automation", service, best_match)
            friendly_name = best_match.replace("automation.", "").replace("_", " ").title()
            return f"Automation {friendly_name} has been {action_word}, Sir." if success else f"Failed to modify automation {friendly_name}."
            
    # 3. Refresh/Sync database automations
    elif any(w in t for w in ["refresh automations", "sync automations", "reload automations", "update automations"]):
        refresh_automations()
        return "I have successfully refreshed and synced the automation database, Sir."

    # 4. List database automations
    elif any(phrase in t for phrase in ["list automations", "show automations", "what automations do you have", "get automations"]):
        phrases = [a["trigger_phrase"] for a in automations_cache if a.get("trigger_phrase")]
        if not phrases:
            return "You have no registered automations, Sir."
        return f"I have the following automations registered: {', '.join(phrases[:10])}."

    return None

def _handle_spotify(text: str):
    music_keywords = {
        "spotify", "music", "song", "track", "playlist", "artist", "album",
        "play", "pause", "resume", "skip", "next", "previous", "volume",
        "feeling", "mood", "sad", "happy", "energetic", "tired", "workout",
        "focus", "study", "relax", "stressed", "angry", "chill", "depressed",
        "bored", "shuffle", "repeat", "queue", "add", "what's playing",
        "currently playing", "liked", "library", "my playlist",
        "switch", "speaker", "output", "device", "transfer"
    }

    words = set(re.findall(r"\b\w+\b", text.lower()))
    if not (words & music_keywords):
        return None

    import json
    import spotify_control
    import datetime
    import jarvis_state

    # Parse device preference
    device_prefer = "auto"
    text_lower = text.lower()
    
    # Fast-path: switch device
    if any(p in text_lower for p in ["switch spotify to", "switch speaker to", "change spotify output to", "change speaker to", "play spotify on", "transfer spotify to", "switch output to"]):
        sp = spotify_control.get_spotify_client()
        if not sp:
            return "Spotify is not connected, Sir. Please link your account."
        m_dev = re.search(
            r"(?:switch spotify to|switch speaker to|change spotify output to|change speaker to|play spotify on|transfer spotify to|switch output to)\s+(.+?)$", text_lower
        )
        if m_dev:
            device_query = m_dev.group(1).strip()
            return spotify_control.switch_playback_device(sp, device_query)

    if any(w in text_lower for w in ["laptop", "computer", "desktop"]):
        device_prefer = "laptop"
    elif any(w in text_lower for w in ["mobile", "phone", "smartphone"]):
        device_prefer = "mobile"

    device_patterns = [
        r"\b(?:on|in|to|from|via)\s+(?:my\s+)?(?:laptop|computer|desktop|mobile|phone|smartphone)\b",
        r"\b(?:laptop|computer|desktop|mobile|phone|smartphone)\b"
    ]

    # Fast-path: "what's playing" / "now playing"
    if any(p in text for p in ["what's playing", "what is playing", "now playing",
                                "currently playing", "which song", "what song"]):
        sp = spotify_control.get_spotify_client()
        if not sp:
            return "Spotify is not connected, Sir. Please link your account."
        return spotify_control.what_is_playing(sp)

    # Fast-path: shuffle
    if "shuffle" in text:
        sp = spotify_control.get_spotify_client()
        if sp:
            state = "off" not in text and "disable" not in text
            return spotify_control.toggle_shuffle(sp, state)

    # Fast-path: repeat
    if "repeat" in text:
        sp = spotify_control.get_spotify_client()
        if sp:
            if "one" in text or "this" in text or "song" in text:
                return spotify_control.toggle_repeat(sp, "track")
            elif "off" in text or "disable" not in text:
                return spotify_control.toggle_repeat(sp, "off" if "off" in text else "context")

    # Fast-path: liked songs
    if any(p in text for p in ["liked songs", "my songs", "saved songs", "library"]):
        sp = spotify_control.get_spotify_client()
        if sp:
            import jarvis_state
            jarvis_state.state.spotify_playback_changed = True
            return spotify_control.play_liked_songs(sp, prefer=device_prefer)

    # Fast-path: list playlists
    if any(p in text for p in ["my playlists", "list playlists", "show playlists", "what playlists"]):
        sp = spotify_control.get_spotify_client()
        if sp:
            return spotify_control.get_my_playlists(sp)

    # Fast-path: add to queue
    if any(p in text for p in ["add to queue", "queue up", "add song", "queue this", "add track"]):
        sp = spotify_control.get_spotify_client()
        if sp:
            # Extract song name: "add <song> to queue"
            m_q = re.search(
                r"(?:add|queue|queue up|add to queue)\s+(.+?)(?:\s+to\s+(?:the\s+)?queue)?$", text
            )
            query_text = m_q.group(1).strip() if m_q else text
            for pat in device_patterns:
                query_text = re.sub(pat, "", query_text, flags=re.IGNORECASE)
            query_text = re.sub(r"\s+", " ", query_text).strip()
            return spotify_control.add_to_queue(sp, query_text, prefer=device_prefer)

    current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    spotify_intent_schema = {
        "type": "OBJECT",
        "properties": {
            "is_music_command": {"type": "BOOLEAN"},
            "action": {
                "type": "STRING",
                "enum": ["play", "pause", "resume", "next", "previous", "volume",
                         "queue", "shuffle_on", "shuffle_off", "repeat_one",
                         "repeat_all", "repeat_off", "liked_songs", "switch_device", "none"]
            },
            "play_type": {
                "type": "STRING",
                "enum": ["track", "artist", "playlist", "album", "mood", "none"]
            },
            "query": {"type": "STRING"},
            "volume_level": {"type": "INTEGER"},
            "jarvis_response": {"type": "STRING"}
        },
        "required": ["is_music_command", "action", "play_type", "query",
                     "volume_level", "jarvis_response"]
    }

    system_instruction = (
        "You are J.A.R.V.I.S., the advanced AI assistant. "
        "Analyze the user command and decide if it is a Spotify / music request. "
        "If the user mentions a mood, feeling, or emotion (sad, happy, angry, chill, etc.), "
        "  set action='play', play_type='mood', and query=the raw mood word (e.g. 'sad'). "
        "If the user wants to play a track, artist, album or playlist, set play_type accordingly. "
        "If the query contains Bengali script characters (e.g., 'আমার সোনার বাংলা'), "
        "  transliterate them into Latin script (e.g., 'Amar Sonar Bangla') in the query field. "
        "If the user wants to switch the playback device, speaker, or output (e.g. 'switch spotify output to speaker', 'play on bedroom speaker', 'change speaker to laptop'), "
        "  set action='switch_device', and query=the name of the target device/speaker."
        "Set is_music_command=false for non-music commands. "
        "Keep jarvis_response under 2 sentences, in J.A.R.V.I.S. persona, no markdown."
    )

    try:
        response = gemini_client.models.generate_content(
            model="gemini-3.1-flash-lite",
            contents=f"Current time: {current_time}\nUser command: {text}",
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=spotify_intent_schema,
                system_instruction=system_instruction,
                temperature=0.1
            )
        )

        result = json.loads(response.text)
        if not result.get("is_music_command"):
            return None

        action     = result.get("action", "none")
        play_type  = result.get("play_type", "none")
        query      = result.get("query", "")
        volume_lvl = result.get("volume_level", 50)
        jarvis_r   = result.get("jarvis_response", "")

        sp = spotify_control.get_spotify_client()
        if not sp:
            explicit = {"spotify", "music", "song", "playlist", "track", "artist", "play", "pause", "skip"}
            if words & explicit:
                return "I am unable to control Spotify, Sir. Please link your account on the dashboard."
            return None

        if action == "pause":
            jarvis_state.state.spotify_playback_changed = True
            return spotify_control.pause_playback(sp)
        elif action == "resume":
            jarvis_state.state.spotify_playback_changed = True
            return spotify_control.resume_playback(sp, prefer=device_prefer)
        elif action == "next":
            jarvis_state.state.spotify_playback_changed = True
            return spotify_control.next_track(sp)
        elif action == "previous":
            jarvis_state.state.spotify_playback_changed = True
            return spotify_control.previous_track(sp)
        elif action == "volume":
            return spotify_control.set_volume(sp, volume_lvl)
        elif action == "queue":
            for pat in device_patterns:
                query = re.sub(pat, "", query, flags=re.IGNORECASE)
            query = re.sub(r"\s+", " ", query).strip()
            return spotify_control.add_to_queue(sp, query, prefer=device_prefer)
        elif action == "shuffle_on":
            return spotify_control.toggle_shuffle(sp, True)
        elif action == "shuffle_off":
            return spotify_control.toggle_shuffle(sp, False)
        elif action == "repeat_one":
            return spotify_control.toggle_repeat(sp, "track")
        elif action == "repeat_all":
            return spotify_control.toggle_repeat(sp, "context")
        elif action == "repeat_off":
            return spotify_control.toggle_repeat(sp, "off")
        elif action == "liked_songs":
            jarvis_state.state.spotify_playback_changed = True
            return spotify_control.play_liked_songs(sp, prefer=device_prefer)
        elif action == "switch_device":
            return spotify_control.switch_playback_device(sp, query)
        elif action == "play":
            jarvis_state.state.spotify_playback_changed = True
            for pat in device_patterns:
                query = re.sub(pat, "", query, flags=re.IGNORECASE)
            query = re.sub(r"\s+", " ", query).strip()
            play_res = spotify_control.play_music(sp, play_type, query, prefer=device_prefer)
            # If play was successful, return Jarvis' witty response
            if not any(w in play_res.lower() for w in ["error", "not found", "required", "could not", "failed"]):
                return jarvis_r if jarvis_r else play_res
            return play_res


        return None
    except Exception as e:
        print(f"[Spotify Intent Parser] Error: {e}")
        return None

def handle_command(text):
    text_raw_lower = text.lower().strip()

    if not text_raw_lower:
        return "I didn't catch that."

    import jarvis_state

    # Clean wake-words from the beginning of the command text
    cleaned_text = text_raw_lower
    cleaned_text = re.sub(r'^(hey\s+)?jarvis[\s,.:!?]*', '', cleaned_text).strip()
    
    # Normalize common speech recognition spelling variants of "system"
    cleaned_text = re.sub(r"\b(systeam|systems|sys\s+team|sytem)\b", "system", cleaned_text)
    
    # If only the wake-word was spoken
    if not cleaned_text and any(w in text_raw_lower for w in ["hey jarvis", "jarvis"]):
        return "At your service, Sir. What can I do for you?"

    # Use cleaned_text as text_lower for subsequent matches to bypass wake word clutter
    text_lower = cleaned_text

    # Direct Hermes routing
    if text_lower.startswith("hermes ") or "ask hermes" in text_lower or "tell hermes" in text_lower:
        query = text_lower.replace("ask hermes", "").replace("tell hermes", "").strip()
        if query.startswith("to "):
            query = query[3:].strip()
        if query.startswith("hermes"):
            query = query[6:].strip()
        print(f"[Router] Routing query to local Ollama hermes3: {query}")
        ollama_res = _ask_ollama(query)
        if ollama_res and "unable to reach" not in ollama_res:
            return ollama_res
        print(f"[Router] Local Ollama failed. Routing to OpenRouter: {query}")
        return _ask_openrouter(query)

    # Try device switcher intent first
    device_res = _handle_active_device_switch(text_lower)
    if device_res:
        return device_res

    # Try Stark/Iron Man protocols
    protocol_res = _handle_stark_protocols(text_lower)
    if protocol_res:
        return protocol_res

    # Try dynamic automation controls
    auto_res = _handle_ha_automation(text_lower)
    if auto_res:
        return auto_res

    # Handle voice lock request
    if any(phrase in text_lower for phrase in ["lock the computer", "lock system", "lock systems", "lock jarvis", "lock the screen", "lock computer"]):
        jarvis_state.state.is_locked = True
        return "Systems locked, Sir. Standby mode initiated."

    # Intercept commands if systems are locked
    if jarvis_state.state.is_locked:
        t_norm = text_lower.replace(" ", "").replace("-", "")
        if "4598" in t_norm or "fourfivenineeight" in t_norm:
            jarvis_state.state.is_locked = False
            return "Verification successful. Welcome back, Sir."
            
        if any(phrase in text_lower for phrase in ["authenticate", "unlock", "log in", "login"]):
            return "Standing by. Please state the passcode, Sir."
            
        return "Systems are locked, Sir. Please provide the passcode, voice authentication, or run face verification."

    kb_color_res = _handle_keyboard_color(text_lower)
    if kb_color_res:
        return kb_color_res

    fan_res = _handle_fan_mode(text_lower)
    if fan_res:
        return fan_res

    # Try custom system, utility, and lock screen actions
    website_res = _handle_website(text_lower)
    if website_res:
        return website_res

    vbox_res = _handle_virtualbox(text_lower)
    if vbox_res:
        return vbox_res

    power_res = _handle_power(text_lower)
    if power_res:
        return power_res

    media_res = _handle_system_media(text_lower)
    if media_res:
        return media_res

    volume_res = _handle_volume(text_lower)
    if volume_res:
        return volume_res

    # Try Spotify controls
    spotify_res = _handle_spotify(text_lower)
    if spotify_res is not None:
        return spotify_res

    alarm_res = _handle_alarm(text_lower)
    if alarm_res:
        return alarm_res

    calc_res = _handle_calculation(text_lower)
    if calc_res:
        return calc_res

    open_app_res = _handle_open_app(text_lower)
    if open_app_res:
        return open_app_res

    phone_res = _handle_phone(text_lower)
    if phone_res:
        return phone_res


    # Custom command: Opinion about Sayani/her
    is_sayani_name = any(name in text_lower for name in [
        "sayani", "sayan", "sayoni", "shayani", "soyoni", "soyani", "shani", "saini", "segani",
        "shaa-yaw-nee", "shaa yaw nee", "shaayawnee"
    ])
    if ("think" in text_lower or "opinion" in text_lower) and ("her" in text_lower or is_sayani_name):
        return "Thanks for being my Sir's friend and staying with him in his bad times. Jarvis is forever grateful to you and always will be at your service."

    # Custom command: Shinjini
    if any(name in text_lower for name in [
        "shinjini", "sinjini", "shinjoni", "sinjoni",
        "shin-jee-nee", "shin jee nee", "shinjeenee"
    ]):
        return "fuck that niggah"

    # Custom command: Greet Sayani
    if is_sayani_name:
        greetings = [
            "good afternoon", "afternoon", "after noon", "aftan", "godaftan", 
            "noon", "nun", "tell", "tel", "tail", "tale", "tile", "toll",
            "godaftar", "after", "aftar", "afturnoon", "aftunoon", "noo", 
            "greet", "wish", "say", "good morning", "morning", "good evening", 
            "evening", "good night", "night"
        ]
        has_greet = any(g in text_lower for g in greetings)
        if has_greet:
            return f"{_get_time_greeting()} Sayani."

    # Custom command: Greet Piyasi (friend)
    if any(name in text_lower for name in ["piyasi", "piyashi", "piashee", "pia she", "piya shi"]):
        if any(greet in text_lower for greet in ["good afternoon", "good morning", "good evening", "good night", "afternoon", "morning", "evening", "night", "tell my friend"]):
            return f"{_get_time_greeting()} Piyasi, nice to meet you. All the best for your exam!"

    # Custom command: Greet Mom (Mamu)
    elif any(w in text_lower for w in ["wish", "tell", "say", "greet", "all the best", "good luck", "good morning", "morning", "good afternoon", "afternoon", "good evening", "evening", "good night", "night"]) and any(m in text_lower for m in ["mom", "mamu"]):
        return f"{_get_time_greeting()} Mamu, all the best for the dance programme!"

    elif any(w in text_lower for w in ["weather", "temperature", "forecast", "climate", "outside", "degree", "hot", "cold", "rain"]):
        return get_weather()

    elif any(w in text_lower for w in ["my tasks", "what do i have to do", "todo", "to-do", "task", "agenda", "schedule", "chores", "doing today", "list for today"]):
        tasks = get_today_tasks()
        if not tasks:
            return "You have no pending tasks."
        return "Here's what's pending: " + ", ".join(t["task_text"] for t in tasks)

    else:
        on_off_result = _handle_direct_on_off(text_lower)
        if on_off_result:
            return on_off_result

        brightness_result = _handle_brightness(text_lower)
        if brightness_result:
            return brightness_result
        
        color_result = _handle_color_change(text_lower)
        if color_result:
            return color_result
        
        # check automations
        best_match = None
        best_score = 0
        for a in automations_cache:
            score = fuzz.partial_ratio(text_lower, a["trigger_phrase"].lower())
            if score > best_score:
                best_score = score
                best_match = a
        if best_match and best_score > 80:
            if best_match["action_type"] == "ha_service":
                success = call_service(best_match["domain"], best_match["service"], best_match["entity_id"])
                return "Done." if success else "Something went wrong controlling that device."
            elif best_match["action_type"] == "open_url":
                return open_url(best_match["target"])
            elif best_match["action_type"] == "open_app":
                return open_app(best_match["target"])

    return _ask_gemini(text)


# ── Colour-change helper ───────────────────────────────────────────────────
_COLOR_TRIGGERS = [
    r"(?:set|change|make|turn|switch)\s+(?:the\s+)?(?:light|bulb|lamp|led)s?\s+(?:to\s+|colour\s+|color\s+)?(\w[\w ]*)",
    r"(?:light|bulb|lamp|led)s?\s+(?:to\s+|colour\s+|color\s+)?(\w[\w ]*)",
    r"(?:colour|color)\s+(?:the\s+)?(?:light|bulb|lamp|led)s?\s+(?:to\s+)?(\w[\w ]*)",
    r"(?:colour|color)\s+(?:to\s+)?(\w[\w ]*)",
    # Short commands: "light red", "lights sky blue", "light ironman"
    r"(?:light|lights|bulb|lamps?|led)\s+(\w[\w ]*?)(?:\s+(?:please|now|mode|theme))?$",
    # "make it red", "turn it blue"
    r"(?:make|turn)\s+it\s+(\w[\w ]*)",
    # "bedroom light red", "hall light sky blue"
    r"\b(?:bedroom|hall|kitchen|living|washroom|bathroom)\s+(?:light|lights?)\s+(\w[\w ]*)",
]


_COLOR_KEYWORDS = {"color", "colour", "change", "make", "set", "switch", "hue", "tone", "shade", "turn", "paint"}

def _handle_color_change(text: str):
    """Detect a colour-change intent and call HA. Returns response string or None."""
    # Import color map to cross-reference known color names
    from home_assistant import _COLOR_MAP
    # Quick pre-filter: must mention a light-related word, a color keyword, or a known color name
    has_light_word = any(w in text for w in ("light", "bulb", "lamp", "lights", "bulbs", "lamps", "led"))
    has_color_kw   = any(w in text for w in _COLOR_KEYWORDS)
    has_color_name = any(color in text for color in _COLOR_MAP.keys())
    if not (has_light_word or has_color_kw or has_color_name):
        return None

    # Extract candidate colour name from spoken text
    detected_color = None

    # Try regex patterns first
    for pattern in _COLOR_TRIGGERS:
        m = re.search(pattern, text)
        if m:
            candidate = m.group(1).strip()
            # Match against known colours (longest match wins)
            for known in sorted(_COLOR_MAP.keys(), key=len, reverse=True):
                if known in candidate or candidate in known:
                    detected_color = known
                    break
            if detected_color:
                break

    # Fallback: scan full text for any colour name
    if not detected_color:
        for known in sorted(_COLOR_MAP.keys(), key=len, reverse=True):
            if known in text:
                detected_color = known
                break

    if not detected_color:
        return None  # no colour found — not a colour command

    # Find the light entity: prefer one from automations, else use a generic default
    entity_id = _find_light_entity(text)
    print(f"[Color] Changing {entity_id} to {detected_color}")
    success = set_light_color(entity_id, color_name=detected_color)
    if success:
        return f"Changing the light to {detected_color}."
    return "I couldn't change the light colour. Check the Home Assistant connection."


# ── Brightness helper ──────────────────────────────────────────────────────
_BRIGHTNESS_TRIGGERS = [
    r"(?:set|change|put|make|turn)\s+(?:the\s+)?(?:light|bulb|lamp|led)s?\s+(?:brightness\s+)?(?:to\s+)?(\d+)\s*(?:%|percent)",
    r"brightness\s+(?:to\s+)?(\d+)\s*(?:%|percent)",
    r"(\d+)\s*(?:%|percent)\s+brightness",
    r"(?:light|bulb|lamp|led)s?\s+(?:at|to)\s+(\d+)\s*(?:%|percent)",
]

_BRIGHTNESS_PRESETS = {
    "minimum":   5,   "min":       5,
    "very dim":  10,  "very low":  10,
    "dim":       20,  "low":       30,
    "half":      50,  "medium":    50,  "mid":   50,
    "normal":    70,  "default":   70,
    "bright":    80,  "high":      80,
    "very bright": 95, "maximum": 100, "max":  100,
    "full":      100, "full brightness": 100,
}

_BRIGHTER_WORDS = {"brighter", "increase", "up", "raise", "higher", "more", "brighten", "turn up", "make brighter", "lighten"}
_DIMMER_WORDS   = {"dimmer", "decrease", "down", "lower", "less", "darker", "dim", "turn down", "make dimmer", "darken"}
_BRIGHTNESS_KW  = {"brightness", "bright", "dim", "dimmer", "brighter", "darker", "lighter", "level", "percentage", "percent", "illumination", "intensity"}

def _handle_brightness(text: str):
    """Detect a brightness-change intent. Returns response string or None."""
    if ("color" in text or "colour" in text) and not any(w in text for w in ("brightness", "percent", "%", "level", "intensity", "brighter", "dimmer")):
        return None

    has_light = any(w in text for w in ("light", "bulb", "lamp", "lights", "bulbs", "lamps", "led"))
    has_bkw   = any(w in text for w in _BRIGHTNESS_KW)
    if not (has_light or has_bkw):
        return None

    pct = None

    # 1. Explicit percentage
    for pattern in _BRIGHTNESS_TRIGGERS:
        m = re.search(pattern, text)
        if m:
            pct = int(m.group(1))
            break

    # Fallback for flexible percentage matching (e.g., "bedroom to 50 percent")
    if pct is None:
        m = re.search(r"(\d+)\s*(?:%|percent|percentage)", text)
        if m:
            pct = int(m.group(1))

    # 2. Relative: "make it brighter / dimmer" (step by 20%)
    if pct is None:
        if any(w in text for w in _BRIGHTER_WORDS) or "turn up" in text or "turn the light up" in text:
            pct = "brighter"
        elif any(w in text for w in _DIMMER_WORDS) or "turn down" in text or "turn the light down" in text:
            pct = "dimmer"

    # 3. Named presets (longest first)
    if pct is None:
        for preset in sorted(_BRIGHTNESS_PRESETS, key=len, reverse=True):
            if preset in text:
                pct = _BRIGHTNESS_PRESETS[preset]
                break

    if pct is None:
        return None   # no brightness intent detected

    entity_id = _find_light_entity(text)

    if pct == "brighter":
        # HA supports brightness_step_pct for relative changes
        success = call_service("light", "turn_on", entity_id,
                               service_data={"brightness_step_pct": 20})
        msg = "Making the light brighter."
    elif pct == "dimmer":
        success = call_service("light", "turn_on", entity_id,
                               service_data={"brightness_step_pct": -20})
        msg = "Making the light dimmer."
    else:
        pct = max(1, min(100, pct))
        success = set_light_color(entity_id, brightness_pct=pct)
        msg = f"Setting brightness to {pct} percent."

    print(f"[Brightness] {entity_id} -> {pct}")
    return msg if success else "I couldn't change the brightness. Check the Home Assistant connection."


def _find_light_entity(text: str) -> str:
    """Pick the best matching light entity from automations, or a default."""
    active_lights = get_active_lights()
    if not active_lights:
        active_lights = ["light.bedroom", "light.hall", "light.kitchen", "light.washroom", "light.bathroom"]

    # Direct word matching fallbacks from Alexa/IoT script
    if "bedroom" in text:
        return "light.bedroom"
    elif "hall" in text or "living room" in text:
        for item in ["light.hall", "light.living_room"]:
            if item in active_lights:
                return item
        return "light.hall"
    elif "kitchen" in text:
        return "light.kitchen"
    elif "washroom" in text or "bathroom" in text or "toilet" in text:
        for item in ["light.washroom", "light.bathroom", "light.toilet"]:
            if item in active_lights:
                return item
        return "light.washroom"

    # Look through cached automations for a light entity that's mentioned in text and exists
    for a in automations_cache:
        entity = a.get("entity_id") or ""
        if not entity.startswith("light.") or entity not in active_lights:
            continue
        # Check if the entity's friendly name fragment appears in speech
        friendly = entity.replace("light.", "").replace("_", " ")
        if friendly in text or entity in text:
            return entity
    # Return first light entity found in automations that actually exists
    for a in automations_cache:
        entity = a.get("entity_id") or ""
        if entity.startswith("light.") and entity in active_lights:
            return entity
    # Ultimate fallback to the first active light found in HA
    return active_lights[0]


def _find_switch_entity(text: str) -> str:
    """Pick the best matching switch/plug entity from automations, or a default."""
    from home_assistant import get_active_switches
    active_switches = get_active_switches()
    if not active_switches:
        return "switch.zebronics_smart_plug_zeb_sp110_socket_1"  # Fallback guess

    # Check if a specific switch matches the spoken name
    for entity in active_switches:
        friendly = entity.replace("switch.", "").replace("_", " ")
        if friendly in text or entity in text:
            return entity

    # Look through cached automations for a switch entity that's mentioned in text
    for a in automations_cache:
        entity = a.get("entity_id") or ""
        if not entity.startswith("switch."):
            continue
        friendly = entity.replace("switch.", "").replace("_", " ")
        if friendly in text or entity in text:
            return entity

    # Try fuzzy matching friendly names of active switches
    best_match = None
    best_score = 0
    for entity in active_switches:
        friendly = entity.replace("switch.", "").replace("_", " ")
        score = fuzz.partial_ratio(text, friendly)
        if score > best_score:
            best_score = score
            best_match = entity

    if best_match and best_score > 60:
        return best_match

    # If looking for a plug, socket, switch, charger or outlet, prioritize one containing those terms (excluding child locks)
    if any(w in text for w in ("plug", "switch", "socket", "charger", "outlet")):
        for entity in active_switches:
            if ("socket" in entity or "plug" in entity) and "child" not in entity:
                return entity

    # Default to first active switch found
    return active_switches[0]


# ── Direct ON/OFF helper ───────────────────────────────────────────────────
def _handle_direct_on_off(text: str):
    """Detect direct 'turn on/off' command for lights and fans to bypass fuzzy matching."""
    has_on = any(re.search(rf"\b{w}\b", text) for w in ("on", "start", "enable", "activate", "run", "illuminate")) or any(w in text for w in ("turnon", "switchon", "poweron", "lightup"))
    has_off = any(re.search(rf"\b{w}\b", text) for w in ("off", "stop", "disable", "deactivate", "shutdown", "kill", "extinguish")) or any(w in text for w in ("turnoff", "switchoff", "poweroff"))
    
    if not (has_on or has_off):
        return None
        
    # If both are present, prioritize based on explicit phrases or fallback to off
    if has_on and has_off:
        if "turn on" in text or "power on" in text or "switch on" in text:
            service = "turn_on"
            action_word = "on"
        else:
            service = "turn_off"
            action_word = "off"
    else:
        service = "turn_on" if has_on else "turn_off"
        action_word = "on" if has_on else "off"
    
    # 1. Check for Light/Bulb/Lamp/LED
    if any(w in text for w in ("light", "bulb", "lamp", "lights", "bulbs", "lamps", "led")):
        entity_id = _find_light_entity(text)
        success = call_service("light", service, entity_id)
        return f"Turning {action_word} the light." if success else "I couldn't control the light."
        
    # 2. Check for Fan
    if any(w in text for w in ("fan", "fans", "ventilator", "cooler")):
        entity_id = "fan.bedroom"
        for a in automations_cache:
            entity = a.get("entity_id") or ""
            if entity.startswith("fan."):
                entity_id = entity
                break
        success = call_service("fan", service, entity_id)
        return f"Turning {action_word} the fan." if success else "I couldn't control the fan."

    # 3. Check for Smart Plug / Switch
    if any(w in text for w in ("plug", "switch", "socket", "charger", "outlet")):
        entity_id = _find_switch_entity(text)
        success = call_service("switch", service, entity_id)
        return f"Turning {action_word} the plug." if success else "I couldn't control the plug."

    return None


def _set_light_color_delayed(entity_id: str, rgb: tuple, brightness_pct: int = None):
    """Set light color in a background thread with retries to allow smart bulbs to boot up."""
    import threading
    import time
    from home_assistant import set_light_color

    def run_attempts():
        # Try at 0s, 4s, 8s, 12s, and 16s
        for attempt, delay in enumerate([0, 4, 4, 4, 4]):
            if delay > 0:
                time.sleep(delay)
            try:
                success = set_light_color(entity_id, rgb=rgb, brightness_pct=brightness_pct)
                if success:
                    print(f"[Router] Successfully set light color for {entity_id} on attempt {attempt + 1}")
                    break
            except Exception as e:
                print(f"[Router] Attempt {attempt + 1} to set light color failed: {e}")

    threading.Thread(target=run_attempts, daemon=True).start()


def _handle_stark_protocols(text: str):
    """Handle custom Stark/Iron Man protocols controlling plug, bulb, and keyboard."""
    import control_center
    import jarvis_state
    from home_assistant import call_service, set_light_color, get_active_switches, get_active_lights

    # Dynamically find the active plug entity if available, fallback to default
    plug_entity = "switch.zebronics_smart_plug_zeb_sp110_socket_1"
    active_switches = get_active_switches()
    if active_switches:
        for entity in active_switches:
            if ("socket" in entity or "plug" in entity) and "child" not in entity:
                plug_entity = entity
                break

    # Dynamically find the active bulb/light entity if available, fallback to default
    bulb_entity = "light.nexstgo_5ch_bulb_wifi_ble"
    active_lights = get_active_lights()
    if active_lights:
        for entity in active_lights:
            if "nexstgo" in entity or "bulb" in entity:
                bulb_entity = entity
                break
        else:
            bulb_entity = active_lights[0]

    t = text.lower()

    # 1. IRON MAN PROTOCOL
    if "iron man protocol" in t or "ironman protocol" in t or "iron man mode" in t or "ironman mode" in t:
        # Turn ON plug
        call_service("switch", "turn_on", plug_entity)
        # Turn ON bulb to red-orange (delayed to allow booting)
        _set_light_color_delayed(bulb_entity, rgb=(255, 60, 0))
        # Keyboard color to red-orange, static mode (0)
        control_center.set_keyboard_color(255, 60, 0, 0)
        jarvis_state.state.keyboard_color = "#ff3c00"
        return "Activating Iron Man protocol, Sir. Powering up auxiliary systems and setting the lights to hot rod red."

    # 2. CLEAN SLATE PROTOCOL
    elif "clean slate protocol" in t or "go dark" in t or "stealth protocol" in t or "stealth mode" in t or re.search(r"\b(jarvis[\s,]*\s*)?turn\s+off\s+(the\s+|th\s+)?(jarvis\s+)?system", t):
        # Turn OFF plug
        call_service("switch", "turn_off", plug_entity)
        # Turn OFF bulb
        call_service("light", "turn_off", bulb_entity)
        # Keyboard color to stealth (very dark grey, static)
        control_center.set_keyboard_color(10, 10, 10, 0)
        jarvis_state.state.keyboard_color = "#0a0a0a"
        return "Initiating Clean Slate protocol, Sir. All auxiliary systems are offline, and lights are extinguished."

    # 3. HOUSE PARTY PROTOCOL
    elif "house party protocol" in t or "party mode" in t:
        # Turn ON plug
        call_service("switch", "turn_on", plug_entity)
        # Set bulb to magenta (delayed to allow booting)
        _set_light_color_delayed(bulb_entity, rgb=(255, 0, 255))
        # Keyboard color to magenta, color cycle (51)
        control_center.set_keyboard_color(255, 0, 255, 51)
        jarvis_state.state.keyboard_color = "#ff00ff"
        return "House Party protocol is active, Sir. Light systems set to party mode and auxiliary power is online."

    # 4. POWER UP SYSTEMS
    elif "initiate power cycle" in t or "power up" in t or re.search(r"\b(jarvis[\s,]*\s*)?turn\s+on\s+(the\s+|th\s+)?(jarvis\s+)?system", t) or re.search(r"\b(jarvis[\s,]*\s*)?activate\s+(the\s+|th\s+)?(jarvis\s+)?system", t):
        # Turn ON plug
        call_service("switch", "turn_on", plug_entity)
        # Turn ON bulb to purple with 25% brightness (delayed to allow booting)
        _set_light_color_delayed(bulb_entity, rgb=(128, 0, 128), brightness_pct=25)
        # Keyboard back to default purple (128, 0, 128)
        control_center.set_keyboard_color(128, 0, 128, 0)
        jarvis_state.state.keyboard_color = "#00f0ff" # Cyan UI
        return "Systems powered up, Sir. Switch outlet is online, and lights are set to purple at twenty-five percent brightness."

    return None


# ── New J.A.R.V.I.S. Helpers ───────────────────────────────────────────────

_COLOR_NAMES = {
    "red": "#ff0000",
    "green": "#00ff00",
    "blue": "#0000ff",
    "cyan": "#00f0ff",
    "magenta": "#ff00ff",
    "yellow": "#ffff00",
    "orange": "#ff7f00",
    "purple": "#800080",
    "white": "#ffffff",
    "pink": "#ffc0cb",
    "gold": "#ffd700"
}

def _handle_website(text: str):
    t = text.lower().strip()
    
    url_target = None
    if t.startswith("open website "):
        url_target = t[13:].strip()
    elif t.startswith("go to "):
        url_target = t[6:].strip()
    elif t.startswith("open ") and any(ext in t for ext in [".com", ".org", ".net", ".in", ".co", ".edu", ".gov", ".mil"]):
        url_target = t[5:].strip()
        
    if url_target:
        url_target = url_target.replace(" ", "")
        from system_actions import open_url
        return open_url(url_target)
        
    if "jersey website" in t or "thejerseyvault" in t or "jersey vault" in t:
        from system_actions import open_url
        return open_url("https://thejerseyvault.in")
        
    return None

def _handle_power(text: str):
    t = text.lower()
    
    # Do not handle keyboard/light power off
    if "keyboard" in t or "light" in t:
        return None

    import jarvis_state
    import time
    import re
    import datetime
    
    # ── 1. CANCEL SCHEDULED POWER ACTIONS ──
    if "cancel" in t and any(w in t for w in ["schedule", "shutdown", "power off", "reboot", "restart", "sleep", "hibernate"]):
        schedules = jarvis_state.state.power_schedules
        active_schedules = [s for s in schedules if s.get("active")]
        if not active_schedules:
            return "There are no active power schedules to cancel, Sir."
            
        action_to_cancel = None
        if "shutdown" in t or "power off" in t or "shut down" in t:
            action_to_cancel = "shutdown"
        elif "reboot" in t or "restart" in t:
            action_to_cancel = "reboot"
        elif "sleep" in t:
            action_to_cancel = "sleep"
        elif "hibernate" in t:
            action_to_cancel = "hibernate"
            
        cancelled_count = 0
        for s in schedules:
            if s.get("active"):
                if action_to_cancel is None or s.get("action") == action_to_cancel:
                    s["active"] = False
                    cancelled_count += 1
                    
        if cancelled_count > 0:
            jarvis_state.state.power_schedules = schedules
            action_name = action_to_cancel if action_to_cancel else "power"
            return f"I have canceled the scheduled {action_name} actions, Sir."
        else:
            return f"No active scheduled {action_to_cancel} was found to cancel, Sir."

    # ── 2. LIST/SHOW SCHEDULED POWER ACTIONS ──
    if any(p in t for p in ["list scheduled", "show scheduled", "list power schedules", "what are the scheduled power", "show power schedules", "scheduled power actions"]):
        schedules = jarvis_state.state.power_schedules
        active_schedules = [s for s in schedules if s.get("active")]
        if not active_schedules:
            return "There are no power actions currently scheduled, Sir."
            
        lines = []
        for s in active_schedules:
            action = s["action"].upper()
            time_left_secs = max(0, int(s["timestamp"] - time.time()))
            mins_left = time_left_secs // 60
            secs_left = time_left_secs % 60
            if mins_left > 0:
                left_str = f"{mins_left} minutes and {secs_left} seconds" if secs_left > 0 else f"{mins_left} minutes"
            else:
                left_str = f"{secs_left} seconds"
            lines.append(f"{action} in {left_str}")
        return f"Current power schedules are: {', '.join(lines)}."

    # ── 3. SCHEDULE A POWER ACTION (RELATIVE OR ABSOLUTE) ──
    is_schedule = "schedule" in t or "timer" in t or "in" in t or "at" in t or "for" in t
    
    action = None
    if "power off" in t or "shutdown" in t or "shut down" in t:
        action = "shutdown"
    elif "reboot" in t or "restart" in t:
        action = "reboot"
    elif "sleep" in t:
        action = "sleep"
    elif "hibernate" in t:
        action = "hibernate"
        
    if not action:
        return None

    if not is_schedule:
        if "power off" in t or "shutdown" in t or "shut down" in t:
            from system_actions import shutdown_pc
            return shutdown_pc()
        elif "reboot" in t or "restart the computer" in t or "restart the laptop" in t:
            from system_actions import reboot_pc
            return reboot_pc()
        elif "sleep" in t:
            from system_actions import sleep_pc
            return sleep_pc()
        elif "hibernate" in t:
            from system_actions import hibernate_pc
            return hibernate_pc()
        return None

    m_rel = re.search(r"in\s+(\d+)\s*(min|hour|hr|sec)", t)
    target_timestamp = None
    label = ""
    
    if m_rel:
        val = int(m_rel.group(1))
        unit = m_rel.group(2)
        if "hour" in unit or "hr" in unit:
            duration_secs = val * 3600
            label_unit = f"{val} hour{'s' if val > 1 else ''}"
        elif "sec" in unit:
            duration_secs = val
            label_unit = f"{val} second{'s' if val > 1 else ''}"
        else:
            duration_secs = val * 60
            label_unit = f"{val} minute{'s' if val > 1 else ''}"
            
        target_timestamp = time.time() + duration_secs
        label = f"{action.capitalize()} in {label_unit}"
    else:
        m_abs = re.search(r"(?:at|for)\s+(\d{1,2})[:.]?(\d{2})?\s*(am|pm)?", t)
        if m_abs:
            hours = int(m_abs.group(1))
            minutes = int(m_abs.group(2)) if m_abs.group(2) else 0
            ampm = m_abs.group(3)
            
            if ampm:
                ampm = ampm.lower()
                if ampm == "pm" and hours < 12:
                    hours += 12
                elif ampm == "am" and hours == 12:
                    hours = 0
                    
            now = datetime.datetime.now()
            target_dt = now.replace(hour=hours, minute=minutes, second=0, microsecond=0)
            if target_dt < now:
                target_dt += datetime.timedelta(days=1)
                
            target_timestamp = target_dt.timestamp()
            disp_ampm = "AM" if hours < 12 else "PM"
            disp_hour = hours if 0 < hours <= 12 else (hours - 12 if hours > 12 else 12)
            label = f"{action.capitalize()} at {disp_hour}:{minutes:02d} {disp_ampm}"

    if target_timestamp:
        target_time_str = datetime.datetime.fromtimestamp(target_timestamp).strftime("%Y-%m-%d %H:%M:%S")
        schedules = jarvis_state.state.power_schedules
        new_schedule = {
            "id": int(time.time()),
            "action": action,
            "timestamp": target_timestamp,
            "time_str": target_time_str,
            "label": label,
            "active": True
        }
        schedules.append(new_schedule)
        jarvis_state.state.power_schedules = schedules
        
        time_left_secs = int(target_timestamp - time.time())
        mins_left = time_left_secs // 60
        if mins_left > 0:
            left_str = f"in {mins_left} minute{'s' if mins_left > 1 else ''}"
        else:
            left_str = f"in {time_left_secs} second{'s' if time_left_secs > 1 else ''}"
            
        if ("at" in t or "for" in t) and not m_rel:
            return f"I have scheduled a system {action} for {label.split(' at ')[1]}, Sir."
        else:
            return f"I have scheduled a system {action} {left_str}, Sir."
            
    if "schedule" not in t:
        if "power off" in t or "shutdown" in t or "shut down" in t:
            from system_actions import shutdown_pc
            return shutdown_pc()
        elif "reboot" in t or "restart the computer" in t or "restart the laptop" in t:
            from system_actions import reboot_pc
            return reboot_pc()
            
    return "I couldn't parse the time for the scheduled power action, Sir."


def _handle_system_media(text: str):
    t = text.lower()
    
    # Play/pause/resume laptop system media
    if any(w in t for w in ["laptop", "computer", "system"]):
        if any(w in t for w in ["pause", "play", "resume", "stop"]):
            import ctypes
            try:
                # VK_MEDIA_PLAY_PAUSE = 0xB3
                ctypes.windll.user32.keybd_event(0xB3, 0, 0, 0)
                ctypes.windll.user32.keybd_event(0xB3, 0, 2, 0)
                return "Toggling laptop media playback, Sir."
            except Exception as e:
                return f"Failed to toggle laptop media: {str(e)}"
                
    return None


def _extract_number(text: str):
    import re
    # Match any digits in the text
    matches = re.findall(r"\b\d+\b", text)
    if matches:
        return int(matches[0])
    
    word_to_num = {
        "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
        "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
        "fifteen": 15, "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50,
        "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90, "hundred": 100
    }
    for word, num in word_to_num.items():
        if f" {word} " in f" {text} ":
            return num
    return None


def _handle_volume(text: str):
    t = text.lower()
    
    # Do not handle spotify volume here
    if "spotify" in t:
        return None
        
    volume_keywords = ["volume", "sound", "audio", "master volume", "speaker volume"]
    mute_keywords = ["mute", "unmute", "silence"]
    louder_quieter = ["louder", "quieter", "turn up", "turn down"]
    
    is_volume_command = (
        any(w in t for w in volume_keywords) or
        any(w in t for w in mute_keywords) or
        any(w in t for w in louder_quieter)
    )
    
    # Also handle "laptop up" / "laptop down" / "laptop mute" if it refers to volume/mute
    if any(w in t for w in ["laptop", "computer", "system"]):
        if any(w in t for w in ["up", "down", "mute", "unmute"]):
            is_volume_command = True
            
    if not is_volume_command:
        return None

    from system_actions import change_volume, set_system_volume, toggle_mute
    
    # 1. Handle Mute / Unmute
    if "unmute" in t or "turn on sound" in t:
        return toggle_mute("unmute")
    elif "mute" in t or "silence" in t:
        if any(w in t for w in volume_keywords):
            return set_system_volume(0)
        return toggle_mute("mute")

    # 2. Handle Max / Min Volume
    if any(w in t for w in ["max", "maximum", "full", "loudest"]):
        return set_system_volume(100)
    if any(w in t for w in ["min", "minimum", "lowest", "zero"]):
        return set_system_volume(0)

    # 3. Extract number
    num = _extract_number(t)
    
    # 4. Determine Direction
    is_up = any(w in t for w in ["up", "increase", "raise", "higher", "louder", "turn up"])
    is_down = any(w in t for w in ["down", "decrease", "lower", "quieter", "turn down", "reduce"])
    
    if num is not None:
        # Check if absolute or relative
        is_relative = False
        if "by" in t or "points" in t or "steps" in t:
            is_relative = True
        elif (is_up or is_down) and not any(w in t for w in ["to", "at"]):
            is_relative = True
            
        if is_relative:
            # Convert percentage/steps to keybd_event steps (each step is 2%)
            steps = num // 2 if num >= 2 else 1
            if is_up:
                return change_volume("up", steps)
            else:
                return change_volume("down", steps)
        else:
            return set_system_volume(num)
            
    # 5. Relative volume without a number
    if is_up:
        return change_volume("up", 5) # Default 10%
    elif is_down:
        return change_volume("down", 5) # Default 10%
        
    return None

def _handle_keyboard_color(text: str):
    """Handle keyboard backlight color, effect, mood, and theme commands via InsydeDCHU.dll.
    Always syncs jarvis_state.keyboard_color so the UI theme updates instantly.
    """
    # ── Trigger words ──────────────────────────────────────────────────────────
    kb_words     = ["keyboard", "backlight", "kb", "keys"]
    action_words = ["color", "colour", "rgb", "light", "backlight", "theme", "effect",
                    "change", "set", "make", "switch", "turn", "reset", "default", "mode"]
    mood_words   = ["mood", "feeling", "i'm", "im ", "feel", "vibe"]
    special_cmds = ["party mode", "party", "random color", "random colour", "random",
                    "ironman", "iron man", "matrix", "ocean", "galaxy", "sunset",
                    "fire", "ice", "neon", "aurora", "midnight", "blood", "forest",
                    "lava", "electric", "stealth", "ghost", "auto color", "auto colour",
                    "time color", "time colour", "default", "reset to default",
                    "restore default", "original theme", "startup theme"]

    has_kb          = any(w in text for w in kb_words)
    has_bulb        = any(w in text for w in ("light", "bulb", "lamp", "led", "lights", "bulbs", "lamps"))
    if has_bulb and not has_kb:
        return None

    import control_center
    import jarvis_state

    has_action      = any(w in text for w in action_words)
    has_mood        = any(w in text for w in mood_words) and has_kb
    has_special     = any(cmd in text for cmd in special_cmds)
    has_color_name  = any(c in text for c in control_center.COLOR_MAP.keys()) or "#" in text

    if not (has_special or has_mood or (has_kb and (has_action or has_color_name))):
        return None

    from home_assistant import set_light_color, get_active_lights

    def _set_lights_rgb(r, g, b):
        """Change all active HA lights to match the given RGB color."""
        try:
            lights = get_active_lights()
            if not lights:
                return
            for entity_id in lights:
                set_light_color(entity_id, rgb=(r, g, b))
        except Exception as e:
            print(f"[Sync] Failed to update HA lights: {e}")

    def _sync_color(r, g, b, sync_lights=True):
        """Update UI state and optionally sync all HA lights to match."""
        jarvis_state.state.keyboard_color = f"#{r:02x}{g:02x}{b:02x}"
        if sync_lights:
            _set_lights_rgb(r, g, b)

    def _sync_hex(hex_str, sync_lights=True):
        jarvis_state.state.keyboard_color = hex_str
        if sync_lights and len(hex_str) >= 7:
            try:
                r = int(hex_str[1:3], 16)
                g = int(hex_str[3:5], 16)
                b = int(hex_str[5:7], 16)
                _set_lights_rgb(r, g, b)
            except Exception:
                pass

    # ══ 0. DEFAULT / RESET ════════════════════════════════════════════════════
    if any(p in text for p in ["default", "reset", "original", "startup", "restore"]):
        # Purple keyboard + cyan UI (Jarvis startup theme)
        success, msg = control_center.set_keyboard_color(128, 0, 128, 0)  # static purple
        _sync_hex("#00f0ff", sync_lights=False)  # reset UI back to default cyan, don't force lights
        if success:
            return "Restoring the default theme, Sir. Keyboard set to purple and interface back to cyan."
        return f"Restored interface theme. Hardware: {msg}"

    # ══ 1. NAMED SCENE PRESETS ════════════════════════════════════════════════
    scene_map = {
        "ironman":   ((255, 60,  0),   "fire",    "#ff3c00", "Activating Iron Man protocol, Sir."),
        "iron man":  ((255, 60,  0),   "fire",    "#ff3c00", "Activating Iron Man protocol, Sir."),
        "matrix":    ((0,   255, 70),  "wave",    "#00ff46", "Initializing the Matrix, Sir."),
        "ocean":     ((0,   180, 255), "wave",    "#00b4ff", "Ocean mode engaged, Sir."),
        "galaxy":    ((100, 0,   255), "cycle",   "#6400ff", "Galaxy theme active, Sir."),
        "sunset":    ((255, 80,  20),  "breath",  "#ff5014", "Sunset palette loaded, Sir."),
        "fire":      ((255, 50,  0),   "flash",   "#ff3200", "Fire mode activated, Sir."),
        "lava":      ((200, 30,  0),   "breath",  "#c81e00", "Lava mode, Sir. Hot enough for you?"),
        "ice":       ((0,   230, 255), "breath",  "#00e6ff", "Ice mode engaged, Sir."),
        "neon":      ((255, 0,   200), "wave",    "#ff00c8", "Neon mode online, Sir."),
        "electric":  ((0,   255, 255), "flash",   "#00ffff", "Electric mode activated, Sir."),
        "aurora":    ((0,   255, 180), "cycle",   "#00ffb4", "Aurora borealis effect engaged, Sir."),
        "midnight":  ((20,  0,   80),  "static",  "#140050", "Midnight mode — dark and stealthy, Sir."),
        "blood":     ((200, 0,   0),   "breath",  "#c80000", "Blood red mode, Sir."),
        "forest":    ((0,   160, 40),  "breath",  "#00a028", "Forest green mode, Sir."),
        "stealth":   ((10,  10,  10),  "static",  "#0a0a0a", "Stealth mode — going dark, Sir."),
        "ghost":     ((200, 200, 220), "breath",  "#c8c8dc", "Ghost mode, Sir. Barely visible."),
    }
    for scene_key, (rgb, effect, ui_hex, response) in scene_map.items():
        if scene_key in text:
            r, g, b = rgb
            mode = control_center.EFFECT_MAP.get(effect, 0)
            success, msg = control_center.set_keyboard_color(r, g, b, mode)
            _sync_hex(ui_hex)
            return response if success else f"Scene unavailable. {msg}"

    # ══ 2. PARTY MODE (rainbow cycle) ═════════════════════════════════════════
    if "party" in text:
        success, msg = control_center.set_keyboard_effect("rainbow")
        _sync_hex("#ff00ff")
        return "Party mode activated, Sir. Let's hope your grades survive this." if success else f"Party foul. {msg}"

    # ══ 3. RANDOM COLOR ═══════════════════════════════════════════════════════
    if "random" in text:
        import random
        r, g, b = random.randint(50, 255), random.randint(50, 255), random.randint(50, 255)
        success, msg = control_center.set_keyboard_color(r, g, b, 0)
        _sync_color(r, g, b)
        return f"Random color generated: #{r:02x}{g:02x}{b:02x}, Sir." if success else f"Randomizer failed. {msg}"

    # ══ 4. TIME-OF-DAY AUTO COLOR ════════════════════════════════════════════
    if any(p in text for p in ["auto color", "auto colour", "time color", "time colour"]):
        import datetime
        hour = datetime.datetime.now().hour
        if 5 <= hour < 9:    # dawn
            r, g, b, label = 255, 140, 50, "dawn orange"
        elif 9 <= hour < 12: # morning
            r, g, b, label = 255, 220, 0, "morning gold"
        elif 12 <= hour < 17: # afternoon
            r, g, b, label = 0, 200, 255, "afternoon blue"
        elif 17 <= hour < 20: # evening
            r, g, b, label = 255, 80, 30, "evening amber"
        elif 20 <= hour < 23: # night
            r, g, b, label = 80, 0, 200, "night purple"
        else:                  # midnight
            r, g, b, label = 10, 10, 40, "midnight dark"
        success, msg = control_center.set_keyboard_color(r, g, b, 16)  # breath
        _sync_color(r, g, b)
        return f"Time-based color set to {label}, Sir." if success else f"Auto color unavailable. {msg}"

    # ══ 5. BRIGHTNESS COMMANDS ════════════════════════════════════════════════
    if any(w in text for w in ["brightness", "bright", "dim", "dark"]):
        level_map = {"off": 0, "dark": 0, "low": 1, "dim": 1, "medium": 2,
                     "half": 2, "normal": 3, "high": 4, "bright": 4, "full": 5, "max": 5}
        m_num = re.search(r"(\d+)", text)
        if m_num:
            level = max(0, min(5, int(int(m_num.group(1)) * 5 / 100 + 0.5)))
        else:
            level = 3
            for word, val in level_map.items():
                if word in text:
                    level = val
                    break
        success, msg = control_center.set_keyboard_brightness(level)
        return f"Keyboard brightness set to level {level}, Sir." if success else f"I couldn't change the keyboard brightness. {msg}"

    # ══ 6. EFFECT COMMANDS ════════════════════════════════════════════════════
    for effect_name in control_center.EFFECT_MAP:
        if effect_name in text:
            r, g, b = 255, 255, 255
            for cname, crgb in control_center.COLOR_MAP.items():
                if cname in text:
                    r, g, b = crgb
                    break
            success, msg = control_center.set_keyboard_effect(effect_name, r, g, b)
            _sync_color(r, g, b)
            if success:
                return f"Setting keyboard to {effect_name} effect, Sir."
            return f"Theme updated. Hardware error: {msg}"

    # ══ 7. MOOD-BASED THEME ═══════════════════════════════════════════════════
    for mood in control_center.MOOD_KEYBOARD_MAP:
        if mood in text:
            color_name, mode = control_center.MOOD_KEYBOARD_MAP[mood]
            success, msg = control_center.set_keyboard_mood(mood)
            r, g, b = control_center.COLOR_MAP.get(color_name, (255, 255, 255))
            _sync_color(r, g, b)
            if success:
                return f"Keyboard and interface theme set to {color_name} for {mood} mood, Sir."
            return f"Theme updated. Hardware error: {msg}"

    # ══ 8. SPECIFIC COLOR BY NAME ═════════════════════════════════════════════
    for cname in sorted(control_center.COLOR_MAP.keys(), key=len, reverse=True):
        if cname in text:
            success, msg = control_center.set_keyboard_color_by_name(cname)
            r, g, b = control_center.COLOR_MAP[cname]
            _sync_color(r, g, b)
            if success:
                return f"Keyboard and interface switched to {cname}, Sir."
            return f"Theme updated. Hardware error: {msg}"

    # ══ 9. HEX COLOR COMMAND: "set keyboard to #ff3300" ═════════════════════
    m_hex = re.search(r"#([0-9a-fA-F]{6})", text)
    if m_hex:
        hex_str = "#" + m_hex.group(1)
        r = int(m_hex.group(1)[0:2], 16)
        g = int(m_hex.group(1)[2:4], 16)
        b = int(m_hex.group(1)[4:6], 16)
        success, msg = control_center.set_keyboard_color(r, g, b, 0)
        _sync_hex(hex_str)
        if success:
            return f"Keyboard and interface set to {hex_str}, Sir."
        return f"Theme updated. Hardware error: {msg}"

    return None


def _handle_fan_mode(text: str):
    """Handle fan speed / mode commands via InsydeDCHU.dll."""
    fan_trigger_words = ["fan", "cooling", "fan speed", "fan mode"]
    if not any(w in text for w in fan_trigger_words):
        return None

    # Filter out HA fan commands (those mention specific rooms or entity IDs)
    ha_room_words = ["bedroom", "living room", "hall", "kitchen", "ceiling fan"]
    if any(w in text for w in ha_room_words):
        return None  # Let the HA handler deal with it

    import control_center

    # 1. Percent-based: "set fan to 80%"
    m_pct = re.search(r"(\d+)\s*(?:%|percent)", text)
    if m_pct:
        pct = int(m_pct.group(1))
        success, label = control_center.set_fan_speed_percent(pct)
        if success:
            return f"Fan set to {label} mode ({pct}% power), Sir."
        return f"I couldn't set the fan speed. {label}"

    # 2. Named mode
    for mode_name in sorted(control_center.FAN_MODE_MAP.keys(), key=len, reverse=True):
        if mode_name in text:
            success, label = control_center.set_fan_mode(mode_name)
            if success:
                return f"Fan mode set to {label}, Sir."
            return f"I couldn't change the fan mode. {label}"

    return None

def _handle_alarm(text: str):
    if "alarm" in text and any(w in text for w in ["set", "create", "add", "wake"]):
        import jarvis_state
        import datetime
        
        # Relative alarm: "set alarm in 10 minutes"
        m_rel = re.search(r"in\s+(\d+)\s+min", text)
        if m_rel:
            mins = int(m_rel.group(1))
            alarm_time = (datetime.datetime.now() + datetime.timedelta(minutes=mins))
            time_str = alarm_time.strftime("%H:%M")
            current_alarms = jarvis_state.state.alarms
            new_alarm = {
                "id": int(time.time()),
                "time": time_str,
                "label": f"Alarm in {mins} minutes",
                "active": True
            }
            current_alarms.append(new_alarm)
            jarvis_state.state.alarms = current_alarms
            return f"I have set an alarm for {alarm_time.strftime('%I:%M %p')}."
            
        # Absolute alarm: "set alarm for 07:30 am", "set alarm for 18:30"
        m_abs = re.search(r"(?:for|at)\s+(\d{1,2})[:.]?(\d{2})?\s*(am|pm)?", text)
        if m_abs:
            hours = int(m_abs.group(1))
            minutes = int(m_abs.group(2)) if m_abs.group(2) else 0
            ampm = m_abs.group(3)
            
            if ampm:
                ampm = ampm.lower()
                if ampm == "pm" and hours < 12:
                    hours += 12
                elif ampm == "am" and hours == 12:
                    hours = 0
                    
            time_str = f"{hours:02d}:{minutes:02d}"
            disp_ampm = "AM" if hours < 12 else "PM"
            disp_hour = hours if 0 < hours <= 12 else (hours - 12 if hours > 12 else 12)
            
            current_alarms = jarvis_state.state.alarms
            new_alarm = {
                "id": int(time.time()),
                "time": time_str,
                "label": f"Alarm at {disp_hour}:{minutes:02d} {disp_ampm}",
                "active": True
            }
            current_alarms.append(new_alarm)
            jarvis_state.state.alarms = current_alarms
            return f"Alarm is set for {disp_hour}:{minutes:02d} {disp_ampm}, Sir."
            
    return None

def _handle_calculation(text: str):
    # Remove query fluff
    expr = text.replace("calculate", "").replace("what is", "").replace("solve", "").replace("equal to", "").replace("equals", "")
    expr = expr.strip()
    
    # Replace words with operators
    expr = expr.replace("plus", "+")
    expr = expr.replace("minus", "-")
    expr = expr.replace("times", "*")
    expr = expr.replace("multiplied by", "*")
    expr = expr.replace("divided by", "/")
    expr = expr.replace("over", "/")
    expr = expr.replace("into", "*")
    
    # Clean expression to safe subset of characters
    clean_expr = re.sub(r'[^0-9+\-*/().\s]', '', expr).strip()
    
    if not clean_expr:
        return None
        
    if not any(char in clean_expr for char in "+-*/"):
        return None
        
    try:
        # Safe math evaluation using restricted namespace
        result = eval(clean_expr, {"__builtins__": None}, {})
        if isinstance(result, float) and result.is_integer():
            result = int(result)
        return f"The result of {clean_expr} is {result}, Sir."
    except Exception:
        return None

def _handle_open_app(text: str):
    if text.startswith("open "):
        app_name = text[5:].strip()
        if "website" in app_name or "jersey" in app_name or app_name.endswith(".in") or app_name.endswith(".com"):
            return None
        from system_actions import open_app
        return open_app(app_name)
    return None


# ── Phone / Android automation handler ────────────────────────────────────────

# Keywords that signal a phone-related command
_PHONE_KEYWORDS = {
    "phone", "android", "mobile", "call", "dial",
    "whatsapp", "alarm on", "chrome on", "on my phone", "on phone",
    "phone battery", "phone volume", "phone screenshot", "lock phone",
    "wake phone", "connect phone", "adb", "refresh phone", "reload phone",
    "go home on phone", "go back on phone",
}

def _is_phone_command(text: str) -> bool:
    """Quick pre-filter: returns True if the text is likely a phone command."""
    t = text.lower()
    # Direct keyword match
    if any(kw in t for kw in _PHONE_KEYWORDS):
        return True
    # Fast path for standalone home/back/refresh if phone is active or explicitly asked
    if any(phrase in t for phrase in ["go back on", "go home on", "refresh the page on", "refresh page on"]):
        return True
    if t in ("go home", "go back", "refresh page", "refresh the page", "refresh app", "reload page"):
        return True
    # Calling a number (digits + call/dial)
    if re.search(r"\b(?:call|dial)\b", t) and re.search(r"\d{6,}", t):
        return True
    return False


def _handle_phone(text: str):
    """
    Route phone-related commands to phone_control.py using Gemini function
    calling. Any natural phrasing is understood — no rigid regex required.
    A fast keyword pre-filter avoids sending irrelevant commands to Gemini.
    """
    if not _is_phone_command(text):
        return None

    import phone_control

    # ── Instant hard-coded paths (no AI needed, always fast) ─────────────
    t = text.lower().strip()

    if t in ("connect phone", "connect my phone", "connect android") or \
            ("connect" in t and "phone" in t):
        return phone_control.adb_connect()

    if any(p in t for p in ["phone status", "phone battery", "is phone connected",
                             "check phone", "phone connection"]):
        return phone_control.phone_status()

    if any(p in t for p in ["lock phone", "lock the phone", "lock my phone"]):
        return phone_control.lock_phone()

    if any(p in t for p in ["wake phone", "wake up phone", "wake my phone",
                             "turn on phone screen"]):
        return phone_control.wake_phone()

    # Instant navigation paths
    if t in ("go home", "go home on phone", "go to home screen", "phone home"):
        return phone_control.go_home_on_phone()

    if t in ("go back", "go back on phone", "back on phone", "phone back"):
        return phone_control.go_back_on_phone()

    if t in ("refresh", "refresh page", "refresh the page", "refresh on phone", "refresh page on phone", "reload page"):
        return phone_control.refresh_page_on_phone()

    if any(p in t for p in ["phone screenshot", "screenshot on phone",
                             "screenshot my phone", "take a phone screenshot"]):
        return phone_control.take_phone_screenshot()

    # ── Gemini function-calling for everything else ───────────────────────
    # Expose all phone_control public functions as tools so Gemini can pick
    # the right one and extract arguments from any natural phrasing.
    phone_tools = [
        phone_control.open_app_on_phone,
        phone_control.make_call,
        phone_control.set_alarm_on_phone,
        phone_control.open_chrome_on_phone,
        phone_control.google_search_on_phone,
        phone_control.send_whatsapp_message,
        phone_control.set_phone_volume,
        phone_control.take_phone_screenshot,
        phone_control.get_phone_battery,
        phone_control.lock_phone,
        phone_control.wake_phone,
        phone_control.adb_connect,
        phone_control.phone_status,
        phone_control.go_home_on_phone,
        phone_control.go_back_on_phone,
        phone_control.refresh_page_on_phone,
    ]

    import datetime
    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    phone_system = (
        f"{_SYSTEM_PROMPT} "
        f"Current date and time: {now_str}. "
        "You also have access to tools that control Sir's Android phone via ADB. "
        "When Sir asks you to perform an action on his phone, call the appropriate "
        "phone tool with the correct arguments — do not explain it, just call it. "
        "Argument rules: "
        "set_alarm_on_phone → hour as integer 0-23, minute as integer 0-59. "
        "open_app_on_phone → lowercase app name only (e.g. 'whatsapp', 'youtube', 'maps'). "
        "make_call → digits only, no spaces. "
        "set_phone_volume → integer 0 to 15. "
        "google_search_on_phone → the search query string only. "
        "send_whatsapp_message → contact number and message text separately. "
        "If no phone tool is appropriate, respond in character as J.A.R.V.I.S. — "
        "polite, dry wit, always ending with 'Sir' where natural."
    )

    # Try lite model first (fast), escalate on failure
    models_to_try = [_TIER["lite"], _TIER["medium"]]
    for model in models_to_try:
        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                response = gemini_client.models.generate_content(
                    model=model,
                    contents=text,
                    config=types.GenerateContentConfig(
                        system_instruction=phone_system,
                        max_output_tokens=150,
                        tools=phone_tools,
                    )
                )

                if response.function_calls:
                    results = []
                    for call in response.function_calls:
                        func_name = call.name
                        func_args = call.args or {}
                        if hasattr(phone_control, func_name):
                            func = getattr(phone_control, func_name)
                            try:
                                print(f"[Phone/Gemini] {func_name}({func_args})")
                                result = func(**func_args)
                                results.append(str(result))
                            except Exception as e:
                                results.append(f"Phone action failed: {e}")
                        else:
                            results.append(f"Unknown phone function: {func_name}")
                    return " ".join(results)

                # Gemini gave a text response — not a phone command
                # Return None so the main router falls through to general AI
                return None

            except Exception as e:
                err_str = str(e)
                is_404 = "404" in err_str or "NOT_FOUND" in err_str
                is_429 = "429" in err_str or "RESOURCE_EXHAUSTED" in err_str
                print(f"[Phone/Gemini] [{model}] attempt {attempt}: {e}")
                if is_404:
                    break
                elif is_429:
                    delay = _parse_retry_delay(err_str)
                    time.sleep(min(delay, 8))
                    break
                elif attempt < _MAX_RETRIES:
                    time.sleep(attempt * 1.5)
                else:
                    break

    # Gemini unavailable — fall back to regex matching
    print("[Phone] Gemini unavailable, using regex fallback...")
    return _phone_regex_fallback(t)


def _phone_regex_fallback(t: str):
    """Regex-based fallback used only when Gemini is unavailable."""
    import phone_control

    m_call = re.match(r"(?:call|dial)\s+([\d\s\+\-()]{6,})", t)
    if m_call:
        return phone_control.make_call(m_call.group(1))

    m_app = re.search(r"(?:open|launch|start)\s+(.+?)\s+on(?:\s+my)?\s+phone", t)
    if m_app:
        return phone_control.open_app_on_phone(m_app.group(1).strip())

    if "alarm" in t and "phone" in t:
        m_abs = re.search(r"(?:for|at)\s+(\d{1,2})[:.]?(\d{2})?\s*(am|pm)?", t)
        if m_abs:
            hours = int(m_abs.group(1))
            minutes = int(m_abs.group(2)) if m_abs.group(2) else 0
            ampm = (m_abs.group(3) or "").lower()
            if ampm == "pm" and hours < 12:
                hours += 12
            elif ampm == "am" and hours == 12:
                hours = 0
            return phone_control.set_alarm_on_phone(hours, minutes)

    m_search = re.search(r"(?:search|google)\s+(.+?)\s+on(?:\s+my)?\s+phone", t)
    if m_search:
        return phone_control.google_search_on_phone(m_search.group(1).strip())

    m_vol = re.search(r"phone\s+volume\s+(?:to\s+)?(\d+)", t)
    if m_vol:
        return phone_control.set_phone_volume(int(m_vol.group(1)))

    m_wa = re.search(
        r"whatsapp\s+(?:message\s+)?(?:to\s+)?([\d\+]+)\s+(?:saying|with)\s+(.+)", t
    )
    if m_wa:
        return phone_control.send_whatsapp_message(m_wa.group(1), m_wa.group(2))

    return None


def _handle_virtualbox(text: str):
    t = text.lower()
    if not ("virtual machine" in t or "vm" in t or "vms" in t):
        return None
        
    from system_actions import list_vms, list_running_vms, start_vm, stop_vm

    if "list" in t:
        if "running" in t:
            return list_running_vms()
        else:
            return list_vms()
            
    if "start" in t:
        name = ""
        m_vm = re.search(r"(?:virtual machine|vm)\s+(\S+)", t)
        if m_vm:
            name = m_vm.group(1).strip()
        else:
            words = t.split()
            try:
                idx = words.index("start")
                if idx < len(words) - 1:
                    name = words[-1]
            except ValueError:
                pass
        if name:
            return start_vm(name)
            
    if any(w in t for w in ["stop", "shutdown", "save"]):
        name = ""
        m_vm = re.search(r"(?:virtual machine|vm)\s+(\S+)", t)
        if m_vm:
            name = m_vm.group(1).strip()
        else:
            words = t.split()
            try:
                idx = words.index("stop")
                if idx < len(words) - 1:
                    name = words[-1]
            except ValueError:
                pass
        if name:
            return stop_vm(name)
            
    return None

