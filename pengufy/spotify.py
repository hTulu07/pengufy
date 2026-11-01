"""Spotify Web API: sign-in (PKCE), library, search and playback control, run off the UI thread."""

import base64
import hashlib
import json
import os
import secrets
import threading
import time
import traceback
import urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import requests
from PyQt6 import sip
from PyQt6.QtCore import QObject, QRunnable, QSettings, QStandardPaths, QThreadPool, pyqtSignal

API = "https://api.spotify.com/v1"
ACCOUNTS = "https://accounts.spotify.com"
REDIRECT_PORT = 8899
REDIRECT_URI = f"http://127.0.0.1:{REDIRECT_PORT}/callback"
SCOPES = ("user-read-playback-state user-modify-playback-state user-read-currently-playing "
          "user-library-read user-library-modify playlist-read-private playlist-read-collaborative")
SEARCH_LIMIT = 10  # Development Mode maximum since February 2026


def settings() -> QSettings:
    return QSettings("pengufy", "pengufy")


def data_dir() -> Path:
    path = Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation))
    path.mkdir(parents=True, exist_ok=True)
    return path


def cache_dir() -> Path:
    path = Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.CacheLocation))
    path.mkdir(parents=True, exist_ok=True)
    return path


def fmt_time(ms) -> str:
    s = int(ms or 0) // 1000
    return f"{s // 3600}:{s // 60 % 60:02d}:{s % 60:02d}" if s >= 3600 else f"{s // 60}:{s % 60:02d}"


# --- background calls ------------------------------------------------------

class _Signals(QObject):
    done = pyqtSignal(object)
    failed = pyqtSignal(str)


class _Job(QRunnable):
    def __init__(self, fn, args, kwargs):
        super().__init__()
        self.fn, self.args, self.kwargs = fn, args, kwargs
        self.signals = _Signals()

    def run(self):
        try:
            result = self.fn(*self.args, **self.kwargs)
        except Exception as e:  # shown to the user, details on the terminal
            traceback.print_exc()
            self.signals.failed.emit(str(e) or type(e).__name__)
        else:
            self.signals.done.emit(result)


POOL = QThreadPool()
POOL.setMaxThreadCount(4)


def run_async(fn, *args, done=None, failed=None, owner=None, **kwargs):
    """Run fn in a worker thread; done/failed are called on the UI thread unless owner was deleted."""
    job = _Job(fn, args, kwargs)

    def alive():
        return owner is None or not sip.isdeleted(owner)

    if done:
        job.signals.done.connect(lambda r: alive() and done(r))
    if failed:
        job.signals.failed.connect(lambda e: alive() and failed(e))
    POOL.start(job)


# --- turning API objects into plain tracks ---------------------------------------

def best_image(images, size=300) -> str:
    if not images:
        return ""
    fitting = [i for i in images if (i.get("width") or 0) >= size]
    return (min(fitting, key=lambda i: i["width"]) if fitting else images[0])["url"]


def track(t: dict) -> dict | None:
    if not t or t.get("type", "track") != "track" or not t.get("uri") or t.get("is_local"):
        return None
    album = t.get("album") or {}
    return {
        "uri": t["uri"],
        "title": t.get("name", ""),
        "artists": ", ".join(a["name"] for a in t.get("artists", [])),
        "album": album.get("name", ""),
        "thumb": best_image(album.get("images"), 64),
        "cover": best_image(album.get("images"), 300),
        "duration": t.get("duration_ms", 0),
        "playable": t.get("is_playable", True),
    }


class ApiError(Exception):
    pass


# --- sign-in -----------------------------------------------------------------------

def _wait_for_code(state: str, timeout=300) -> str:
    """Serve the redirect page once and return the ?code= from it."""
    result = {}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            query = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            if not self.path.startswith("/callback"):
                self.send_error(404)
                return
            ok = query.get("state", [""])[0] == state and "code" in query
            result["code"] = query["code"][0] if ok else None
            result["error"] = query.get("error", ["state mismatch"])[0] if not ok else None
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            msg = "You're signed in. You can close this tab and go back to Pengufy." if ok else \
                f"Sign-in failed: {result['error']}"
            self.wfile.write(f"<html><body style='font-family:sans-serif;background:#0f141c;color:#d8e0ea;"
                             f"padding:40px'><h2>Pengufy</h2><p>{msg}</p></body></html>".encode())

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", REDIRECT_PORT), Handler)
    server.timeout = 1
    deadline = time.time() + timeout
    try:
        while "code" not in result and time.time() < deadline:
            server.handle_request()
    finally:
        server.server_close()
    if not result.get("code"):
        raise ApiError(result.get("error") or "Sign-in timed out")
    return result["code"]


class Spotify(QObject):
    """Holds the token; every method here blocks, so call them through run_async."""

    def __init__(self):
        super().__init__()
        self.auth_file = data_dir() / "auth.json"
        self.client_id = settings().value("client_id", "", str)
        self.token = {}
        self.lock = threading.Lock()
        self.session = requests.Session()
        self.user = {}
        if self.auth_file.exists():
            try:
                self.token = json.loads(self.auth_file.read_text())
            except ValueError:
                self.token = {}

    @property
    def signed_in(self) -> bool:
        return bool(self.client_id and self.token.get("refresh_token"))

    def set_client_id(self, client_id: str):
        self.client_id = client_id.strip()
        settings().setValue("client_id", self.client_id)

    def _save(self, token):
        token["expires_at"] = time.time() + token.get("expires_in", 3600) - 60
        if "refresh_token" not in token:
            token["refresh_token"] = self.token.get("refresh_token")
        self.token = token
        fd = os.open(self.auth_file, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as f:
            json.dump(token, f)

    def sign_in(self, open_url):
        """Open the consent page with open_url(url) and wait for the browser to come back."""
        verifier = secrets.token_urlsafe(64)
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
        state = secrets.token_urlsafe(16)
        url = f"{ACCOUNTS}/authorize?" + urllib.parse.urlencode({
            "client_id": self.client_id, "response_type": "code", "redirect_uri": REDIRECT_URI,
            "code_challenge_method": "S256", "code_challenge": challenge, "scope": SCOPES, "state": state})
        open_url(url)
        code = _wait_for_code(state)
        r = requests.post(f"{ACCOUNTS}/api/token", data={
            "grant_type": "authorization_code", "code": code, "redirect_uri": REDIRECT_URI,
            "client_id": self.client_id, "code_verifier": verifier}, timeout=20)
        if not r.ok:
            raise ApiError(r.json().get("error_description", r.text))
        self._save(r.json())
        return self.me()

    def sign_out(self):
        self.token = {}
        self.auth_file.unlink(missing_ok=True)

    def _access_token(self) -> str:
        with self.lock:
            if time.time() < self.token.get("expires_at", 0):
                return self.token["access_token"]
            if not self.token.get("refresh_token"):
                raise ApiError("Not signed in")
            r = requests.post(f"{ACCOUNTS}/api/token", data={
                "grant_type": "refresh_token", "refresh_token": self.token["refresh_token"],
                "client_id": self.client_id}, timeout=20)
            if r.status_code == 400:
                self.sign_out()
                raise ApiError("Your Spotify sign-in expired. Please sign in again.")
            r.raise_for_status()
            self._save(r.json())
            return self.token["access_token"]

    def call(self, method, path, params=None, body=None, retry=True):
        r = self.session.request(method, path if path.startswith("http") else API + path, params=params,
                                 json=body, headers={"Authorization": f"Bearer {self._access_token()}"},
                                 timeout=20)
        if r.status_code == 401 and retry:
            self.token["expires_at"] = 0
            return self.call(method, path, params, body, retry=False)
        if r.status_code == 429 and retry:
            time.sleep(min(int(r.headers.get("Retry-After", "2")), 10))
            return self.call(method, path, params, body, retry=False)
        if r.status_code >= 400:
            try:
                msg = r.json()["error"]["message"]
            except (ValueError, KeyError, TypeError):
                msg = r.text or r.reason
            raise ApiError(f"{msg} ({r.status_code})")
        try:
            return r.json() if r.content else None
        except ValueError:  # some player commands answer 200 with a non-JSON body
            return None

    # --- library and search ---------------------------------------------------------

    def me(self) -> dict:
        self.user = self.call("GET", "/me")
        return self.user

    def search(self, query: str, offset=0) -> list:
        res = self.call("GET", "/search", {"q": query, "type": "track", "limit": SEARCH_LIMIT, "offset": offset})
        return [t for t in map(track, res["tracks"]["items"]) if t]

    def playlists(self) -> list:
        out, url = [], "/me/playlists?limit=50"
        while url:
            page = self.call("GET", url)
            for p in page["items"]:
                if not p:
                    continue
                owner = (p.get("owner") or {}).get("id")
                out.append({"id": p["id"], "uri": p["uri"], "name": p["name"],
                            "owner": (p.get("owner") or {}).get("display_name") or owner or "",
                            "readable": owner == self.user.get("id") or p.get("collaborative", False),
                            "thumb": best_image(p.get("images"), 64)})
            url = page.get("next")
        return out

    def _pages(self, url, key):
        out = []
        while url:
            page = self.call("GET", url)
            out += [t for t in (track(item.get(key)) for item in page["items"]) if t]
            url = page.get("next")
        return out

    def liked(self) -> list:
        return self._pages("/me/tracks?limit=50", "track")

    def playlist_tracks(self, playlist_id) -> list:
        return self._pages(f"/playlists/{playlist_id}/items?limit=50", "item")

    def is_liked(self, uri) -> bool:
        return bool((self.call("GET", "/me/library/contains", {"uris": uri}) or [False])[0])

    def set_liked(self, uri, liked: bool):
        self.call("PUT" if liked else "DELETE", "/me/library", {"uris": uri})

    # --- playback ----------------------------------------------------------------------

    def devices(self) -> list:
        return self.call("GET", "/me/player/devices")["devices"]

    def state(self) -> dict | None:
        return self.call("GET", "/me/player", {"additional_types": "track"})

    def play(self, device_id, uris=None, index=0, context=None, offset_uri=None):
        body = {}
        if context:
            body["context_uri"] = context
            if offset_uri:
                body["offset"] = {"uri": offset_uri}
        elif uris:
            # Spotify accepts a limited list; send a window around the chosen song.
            start = max(0, index - 50)
            body["uris"] = uris[start:start + 300]
            body["offset"] = {"position": index - start}
        self.call("PUT", "/me/player/play", {"device_id": device_id} if device_id else None, body or None)

    def pause(self):
        self.call("PUT", "/me/player/pause")

    def resume(self, device_id=None):
        self.call("PUT", "/me/player/play", {"device_id": device_id} if device_id else None)

    def next(self):
        self.call("POST", "/me/player/next")

    def previous(self):
        self.call("POST", "/me/player/previous")

    def seek(self, ms):
        self.call("PUT", "/me/player/seek", {"position_ms": int(ms)})

    def volume(self, percent):
        self.call("PUT", "/me/player/volume", {"volume_percent": int(percent)})

    def shuffle(self, on: bool):
        self.call("PUT", "/me/player/shuffle", {"state": "true" if on else "false"})

    def repeat(self, mode: str):  # off / context / track
        self.call("PUT", "/me/player/repeat", {"state": mode})

    def transfer(self, device_id, play=False):
        self.call("PUT", "/me/player", body={"device_ids": [device_id], "play": play})
