import os
import spotipy
from spotipy.oauth2 import SpotifyOAuth
from dotenv import load_dotenv
import jarvis_state
from rapidfuzz import fuzz

load_dotenv()

CLIENT_ID = os.environ.get("SPOTIFY_CLIENT_ID")
CLIENT_SECRET = os.environ.get("SPOTIFY_CLIENT_SECRET")
REDIRECT_URI = os.environ.get("SPOTIFY_REDIRECT_URI", "http://127.0.0.1:8888/callback")
SCOPE = (
    "user-modify-playback-state "
    "user-read-playback-state "
    "user-read-currently-playing "
    "playlist-read-private "
    "playlist-read-collaborative "
    "user-library-read "
    "user-top-read "
    "user-read-recently-played"
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_PATH = os.path.join(BASE_DIR, ".spotify_cache")

# ── Mood → playlist search query map ─────────────────────────────────────────
MOOD_PLAYLIST_MAP = {
    "happy":      "feel good happy upbeat pop",
    "sad":        "sad emotional heartbreak acoustic",
    "angry":      "angry metal hard rock intense",
    "calm":       "calm peaceful ambient relaxing",
    "focused":    "focus deep work lo-fi study",
    "study":      "study music concentration lo-fi beats",
    "excited":    "excited energetic party dance hits",
    "romantic":   "romantic love songs smooth r&b",
    "tired":      "chill mellow tired sleep playlist",
    "energetic":  "energetic workout motivation power",
    "workout":    "gym workout pump up intense beats",
    "chill":      "chill vibes relaxed mellow",
    "depressed":  "uplifting positivity recovery feel better",
    "stressed":   "stress relief meditation calm anxiety",
    "bored":      "discover new music eclectic mix",
    "morning":    "morning fresh upbeat start of day",
    "evening":    "evening chill sunset acoustic",
    "night":      "late night vibes dark ambient",
    "party":      "party hits dance floor club banger",
    "sleep":      "sleep sounds white noise peaceful",
}


def get_sp_oauth():
    if not CLIENT_ID or not CLIENT_SECRET:
        return None
    return SpotifyOAuth(
        client_id=CLIENT_ID,
        client_secret=CLIENT_SECRET,
        redirect_uri=REDIRECT_URI,
        scope=SCOPE,
        cache_path=CACHE_PATH,
        open_browser=False
    )


def get_spotify_client():
    auth_manager = get_sp_oauth()
    if not auth_manager:
        return None

    token_info = auth_manager.get_cached_token()
    if not token_info:
        return None

    if auth_manager.is_token_expired(token_info):
        try:
            token_info = auth_manager.refresh_access_token(token_info['refresh_token'])
        except Exception:
            return None

    return spotipy.Spotify(auth=token_info['access_token'])


def is_logged_in():
    return get_spotify_client() is not None


def get_active_device(sp, prefer: str = "auto"):
    """
    Return the best Spotify device ID to play on.

    prefer:
      "auto"   → use jarvis_state.active_mic_device to decide
      "mobile" → prefer a phone/smartphone device
      "laptop" → prefer a computer/desktop device
    """
    try:
        devices = sp.devices()
        if not devices or not devices.get('devices'):
            return None

        all_devices = devices['devices']
        if not all_devices:
            return None

        # Resolve "auto" using active device check, falling back to laptop
        if prefer == "auto":
            currently_active = None
            for d in all_devices:
                if d.get("is_active"):
                    currently_active = d.get("id")
            if currently_active:
                return currently_active
            prefer = "laptop"

        # Device type buckets
        mobile_types  = {"smartphone", "tablet"}
        laptop_types  = {"computer", "desktop"}

        preferred   = []
        fallback    = []
        currently_active = None

        for d in all_devices:
            dtype = (d.get("type") or "").lower()
            if d.get("is_active"):
                currently_active = d.get("id")
            if prefer == "mobile" and dtype in mobile_types:
                preferred.append(d)
            elif prefer == "laptop" and dtype in laptop_types:
                preferred.append(d)
            else:
                fallback.append(d)

        # Priority: preferred list → currently active → first available
        if preferred:
            return preferred[0].get("id")
        if currently_active:
            return currently_active
        if fallback:
            return fallback[0].get("id")
        return all_devices[0].get("id")

    except Exception:
        return None


def play_music(sp, action_type, query, prefer: str = "auto"):
    device_id = get_active_device(sp, prefer=prefer)
    if not device_id:
        jarvis_state.state.client_open_url = "https://open.spotify.com"
    try:
        # Fallback if the query is a generic "music" command
        clean_query = query.lower().strip()
        if clean_query in ["", "music", "some music", "songs", "play music"]:
            res = resume_playback(sp, prefer=prefer)
            if "could not resume" in res.lower() or "active session" in res.lower() or "ensure spotify is active" in res.lower():
                return play_liked_songs(sp, prefer=prefer)
            return res

        if not device_id:
            return "No active Spotify devices found, Sir. Please open Spotify on a device."

        if action_type == 'track':
            results = sp.search(q=query, type='track', limit=1)
            tracks = results.get('tracks', {}).get('items', [])
            if not tracks:
                return f"I could not find the song '{query}' on Spotify, Sir."
            track_uri = tracks[0]['uri']
            track_name = tracks[0]['name']
            artist_name = tracks[0]['artists'][0]['name']
            sp.start_playback(device_id=device_id, uris=[track_uri])
            return f"Playing '{track_name}' by {artist_name}."

        elif action_type == 'artist':
            results = sp.search(q=query, type='artist', limit=1)
            artists = results.get('artists', {}).get('items', [])
            if not artists:
                return f"I could not find the artist '{query}' on Spotify, Sir."
            artist_uri = artists[0]['uri']
            artist_name = artists[0]['name']
            sp.start_playback(device_id=device_id, context_uri=artist_uri)
            return f"Playing songs by {artist_name}."

        elif action_type == 'album':
            results = sp.search(q=query, type='album', limit=1)
            albums = results.get('albums', {}).get('items', [])
            if not albums:
                return f"I could not find the album '{query}' on Spotify, Sir."
            album_uri = albums[0]['uri']
            album_name = albums[0]['name']
            album_artist = albums[0]['artists'][0]['name']
            sp.start_playback(device_id=device_id, context_uri=album_uri)
            return f"Playing the album '{album_name}' by {album_artist}."

        elif action_type in ('playlist', 'mood'):
            # For mood, first check our mood map for a richer search query
            search_query = MOOD_PLAYLIST_MAP.get(query.lower(), query)
            results = sp.search(q=search_query, type='playlist', limit=5)
            playlists = results.get('playlists', {}).get('items', [])
            # Filter out None items (Spotify sometimes returns nulls)
            playlists = [p for p in playlists if p]
            if not playlists:
                return f"I could not find any playlists matching '{query}', Sir."
            playlist = playlists[0]
            playlist_uri = playlist['uri']
            playlist_name = playlist['name']
            sp.start_playback(device_id=device_id, context_uri=playlist_uri)
            return f"Queueing up '{playlist_name}'."

        return "Invalid play type."
    except spotipy.exceptions.SpotifyException as e:
        if e.http_status == 403:
            return "Spotify Premium is required to control playback, Sir."
        return f"An error occurred with Spotify, Sir: {e.msg}"
    except Exception as e:
        return f"Failed to play music: {str(e)}"


def pause_playback(sp):
    try:
        sp.pause_playback()
        return "Music paused, Sir."
    except Exception:
        return "Playback is already paused or no active session exists, Sir."


def resume_playback(sp, prefer: str = "auto"):
    device_id = get_active_device(sp, prefer)
    if not device_id:
        jarvis_state.state.client_open_url = "https://open.spotify.com"
    try:
        if device_id:
            sp.start_playback(device_id=device_id)
            return "Resuming music, Sir."
        sp.start_playback()
        return "Resuming music, Sir."
    except Exception:
        return "I could not resume playback. Ensure Spotify is active on a device, Sir."


def next_track(sp):
    try:
        sp.next_track()
        return "Skipping to the next track, Sir."
    except Exception:
        return "Failed to skip track, Sir."


def previous_track(sp):
    try:
        sp.previous_track()
        return "Playing the previous track, Sir."
    except Exception:
        return "Failed to go back, Sir."


def set_volume(sp, level):
    try:
        level = max(0, min(100, int(level)))
        sp.volume(level)
        return f"Volume set to {level} percent, Sir."
    except Exception:
        return "Failed to adjust Spotify volume, Sir."


def get_current_track(sp):
    try:
        curr = sp.current_playback()
        if not curr or not curr.get('item'):
            return None
        item = curr['item']
        return {
            "track":      item.get('name', ''),
            "artist":     item.get('artists', [{}])[0].get('name', ''),
            "album":      item.get('album', {}).get('name', ''),
            "progress":   curr.get('progress_ms', 0),
            "duration":   item.get('duration_ms', 0),
            "is_playing": curr.get('is_playing', False),
            "cover_url":  item.get('album', {}).get('images', [{}])[0].get('url', ''),
        }
    except Exception:
        return None


def what_is_playing(sp) -> str:
    """Return a spoken description of the currently playing track."""
    info = get_current_track(sp)
    if not info:
        return "Nothing is playing on Spotify right now, Sir."
    state = "Playing" if info["is_playing"] else "Paused on"
    return f"{state} '{info['track']}' by {info['artist']}, Sir."


def add_to_queue(sp, query: str, prefer: str = "auto") -> str:
    """Search for a track and add it to the play queue."""
    try:
        device_id = get_active_device(sp, prefer)
        if not device_id:
            return "No active Spotify device found, Sir."
        results = sp.search(q=query, type='track', limit=1)
        tracks = results.get('tracks', {}).get('items', [])
        if not tracks:
            return f"I could not find '{query}' on Spotify, Sir."
        track_uri = tracks[0]['uri']
        track_name = tracks[0]['name']
        artist_name = tracks[0]['artists'][0]['name']
        sp.add_to_queue(track_uri, device_id=device_id)
        return f"Added '{track_name}' by {artist_name} to the queue, Sir."
    except spotipy.exceptions.SpotifyException as e:
        if e.http_status == 403:
            return "Spotify Premium is required to manage the queue, Sir."
        return f"Spotify error: {e.msg}"
    except Exception as e:
        return f"Failed to add to queue: {str(e)}"


def toggle_shuffle(sp, state: bool) -> str:
    """Enable or disable shuffle mode."""
    try:
        sp.shuffle(state)
        return f"Shuffle {'enabled' if state else 'disabled'}, Sir."
    except Exception as e:
        return f"Failed to toggle shuffle: {str(e)}"


def toggle_repeat(sp, mode: str = "track") -> str:
    """Set repeat mode: 'track', 'context', or 'off'."""
    try:
        sp.repeat(mode)
        label = {"track": "repeat one", "context": "repeat all", "off": "repeat off"}.get(mode, mode)
        return f"{label.title()} enabled, Sir."
    except Exception as e:
        return f"Failed to set repeat: {str(e)}"


def get_my_playlists(sp, limit: int = 10) -> str:
    """Return a list of the user's playlists as a spoken string."""
    try:
        results = sp.current_user_playlists(limit=limit)
        items = results.get('items', [])
        if not items:
            return "You have no saved playlists on Spotify, Sir."
        names = [p['name'] for p in items if p]
        return "Your playlists are: " + ", ".join(names) + "."
    except Exception as e:
        return f"Could not retrieve playlists: {str(e)}"


def play_liked_songs(sp, prefer: str = "auto") -> str:
    """Play the user's liked/saved tracks."""
    device_id = get_active_device(sp, prefer)
    if not device_id:
        jarvis_state.state.client_open_url = "https://open.spotify.com"
    try:
        if not device_id:
            return "No active Spotify device found, Sir."
        results = sp.current_user_saved_tracks(limit=50)
        tracks = results.get('items', [])
        if not tracks:
            return "You have no liked songs on Spotify, Sir."
        uris = [item['track']['uri'] for item in tracks if item.get('track')]
        sp.start_playback(device_id=device_id, uris=uris)
        return "Playing your liked songs, Sir."
    except spotipy.exceptions.SpotifyException as e:
        if e.http_status == 403:
            return "Spotify Premium required, Sir."
        return f"Spotify error: {e.msg}"
    except Exception as e:
        return f"Failed to play liked songs: {str(e)}"


def switch_playback_device(sp, device_name_query: str) -> str:
    """Switch playback to a device matching the name query."""
    try:
        devices = sp.devices()
        if not devices or not devices.get('devices'):
            return "No Spotify devices found, Sir. Make sure the speaker is on."
        
        all_devices = devices['devices']
        best_match = None
        best_score = 0
        for d in all_devices:
            name = d.get("name", "").lower()
            score = fuzz.partial_ratio(device_name_query.lower(), name)
            if score > best_score:
                best_score = score
                best_match = d
                
        if best_match and best_score > 70:
            device_id = best_match.get("id")
            device_name = best_match.get("name")
            sp.transfer_playback(device_id=device_id, force_play=True)
            return f"I switched Spotify playback to {device_name}, Sir."
        
        device_names = [d.get("name", "") for d in all_devices if d.get("name")]
        return f"I could not find a device matching '{device_name_query}'. Available devices are: {', '.join(device_names)}."
    except Exception as e:
        return f"I failed to switch Spotify device: {str(e)}"

