"""
spotify_auth.py — One-time Spotify authentication helper for Jarvis.

Run this script ONCE. It starts a temporary local server on port 5000,
opens Spotify login in your browser, catches the callback automatically,
and saves the token to .spotify_cache. No manual copy-pasting needed.

Usage:
    python spotify_auth.py
"""

import os
import sys
import threading
import webbrowser
from dotenv import load_dotenv

load_dotenv()

CLIENT_ID     = os.environ.get("SPOTIFY_CLIENT_ID", "")
CLIENT_SECRET = os.environ.get("SPOTIFY_CLIENT_SECRET", "")
REDIRECT_URI  = "http://127.0.0.1:8888/callback"
CACHE_PATH    = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".spotify_cache")

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

# Shared state between Flask thread and main thread
_auth_code = None
_auth_error = None
_server_done = threading.Event()


def _check_credentials():
    if not CLIENT_ID or CLIENT_ID == "your_spotify_client_id_here":
        print("\n[ERROR] SPOTIFY_CLIENT_ID is not set in your .env file.")
        print("\nSteps to get your Spotify credentials:")
        print("  1. Go to  https://developer.spotify.com/dashboard")
        print("  2. Click 'Create app'")
        print("  3. App name: anything (e.g. 'Jarvis AI')")
        print("  4. Website:       http://localhost:5000")
        print("  5. Redirect URI:  http://localhost:5000/callback  → click Add")
        print("  6. Check 'Web API' under APIs used")
        print("  7. Save → copy Client ID and Client Secret into your .env\n")
        sys.exit(1)

    if not CLIENT_SECRET or CLIENT_SECRET == "your_spotify_client_secret_here":
        print("\n[ERROR] SPOTIFY_CLIENT_SECRET is not set in your .env file.\n")
        sys.exit(1)


def _start_callback_server():
    """Start a tiny Flask server that catches the Spotify OAuth callback."""
    global _auth_code, _auth_error

    try:
        from flask import Flask, request
    except ImportError:
        print("[ERROR] Flask is not installed. Run: pip install flask")
        sys.exit(1)

    app = Flask(__name__)

    # Suppress Flask startup logs
    import logging
    log = logging.getLogger('werkzeug')
    log.setLevel(logging.ERROR)

    @app.route("/callback")
    def callback():
        global _auth_code, _auth_error
        error = request.args.get("error")
        code  = request.args.get("code")

        if error:
            _auth_error = error
            _server_done.set()
            return f"<h2>Authentication failed: {error}</h2><p>You can close this tab.</p>"

        if code:
            _auth_code = code
            _server_done.set()
            return (
                "<h2 style='font-family:sans-serif;color:#1DB954'>✅ Jarvis authenticated!</h2>"
                "<p style='font-family:sans-serif'>Spotify is now linked. You can close this tab and return to the terminal.</p>"
                "<script>setTimeout(()=>window.close(),2000)</script>"
            )

        return "<h2>No code received.</h2>"

    # Run in a daemon thread so it exits when main thread finishes
    thread = threading.Thread(
        target=lambda: app.run(host="127.0.0.1", port=8888, debug=False, use_reloader=False),
        daemon=True
    )
    thread.start()
    return thread


def main():
    _check_credentials()

    try:
        from spotipy.oauth2 import SpotifyOAuth
        import spotipy
    except ImportError:
        print("[ERROR] spotipy is not installed. Run: pip install spotipy")
        sys.exit(1)

    print("\n[Jarvis] Starting local callback server on http://127.0.0.1:8888 ...")
    _start_callback_server()

    auth = SpotifyOAuth(
        client_id=CLIENT_ID,
        client_secret=CLIENT_SECRET,
        redirect_uri=REDIRECT_URI,
        scope=SCOPE,
        cache_path=CACHE_PATH,
        open_browser=False
    )

    auth_url = auth.get_authorize_url()
    print("[Jarvis] Opening Spotify login in your browser...")
    print(f"\n  If the browser doesn't open, visit:\n  {auth_url}\n")

    # Small delay so the server is ready before the browser hits it
    import time
    time.sleep(0.5)
    webbrowser.open(auth_url)

    print("[Jarvis] Waiting for you to approve access in the browser...")
    _server_done.wait(timeout=120)   # wait up to 2 minutes

    if _auth_error:
        print(f"\n[ERROR] Spotify returned an error: {_auth_error}")
        sys.exit(1)

    if not _auth_code:
        print("\n[ERROR] Timed out waiting for Spotify callback. Please try again.")
        sys.exit(1)

    # Exchange the code for tokens
    try:
        token_info = auth.get_access_token(_auth_code, as_dict=True, check_cache=False)
    except Exception as e:
        print(f"\n[ERROR] Failed to exchange code for token: {e}")
        sys.exit(1)

    if not token_info:
        print("\n[ERROR] Could not obtain access token.")
        sys.exit(1)

    print("\n[Jarvis] Authentication successful!")
    print(f"[Jarvis] Token cached at: {CACHE_PATH}")

    sp = spotipy.Spotify(auth=token_info['access_token'])
    try:
        user = sp.current_user()
        print(f"[Jarvis] Logged in as: {user['display_name']} ({user['email']})")
    except Exception:
        print("[Jarvis] Logged in successfully (could not fetch profile).")

    print("\nSpotify is now linked to Jarvis. You never need to run this again.")
    print("Jarvis will auto-refresh the token in the background.\n")


if __name__ == "__main__":
    main()
