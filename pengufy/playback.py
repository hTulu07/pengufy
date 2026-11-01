"""What's playing on the Pengufy device, kept up to date by light polling of the Web API."""

import time

from PyQt6.QtCore import QObject, QTimer, pyqtSignal

from .engine import DEVICE_NAME
from .spotify import run_async, track


class Playback(QObject):
    changed = pyqtSignal()           # track, playing, shuffle, repeat, volume
    positionChanged = pyqtSignal(int)  # ms
    deviceChanged = pyqtSignal(bool)   # found
    error = pyqtSignal(str)

    def __init__(self, api):
        super().__init__()
        self.api = api
        self.device_id = None
        self.current = None
        self.playing = False
        self.shuffle = False
        self.repeat = "off"
        self.volume = 70
        self.position = 0
        self.stamp = time.monotonic()
        self.busy = False
        self.poll = QTimer(self, timeout=self.refresh)
        self.poll.start(4000)
        self.tick = QTimer(self, timeout=self._tick, interval=500)
        self.tick.start()
        self.soon = QTimer(self, singleShot=True, timeout=self.refresh)
        self.searches = 0

    # --- finding our device ------------------------------------------------------------

    def find_device(self):
        """Look for the engine's device; it takes a few seconds to register after start."""
        self.searches = 0
        self._search()

    def _search(self):
        def done(devices):
            ours = [d for d in devices if d["name"] == DEVICE_NAME]
            if ours:
                self.device_id = ours[0]["id"]
                self.deviceChanged.emit(True)
                self.refresh()
            elif self.searches < 30:
                self.searches += 1
                QTimer.singleShot(1000, self._search)
            else:
                self.deviceChanged.emit(False)
        run_async(self.api.devices, done=done, failed=lambda e: QTimer.singleShot(2000, self._search))

    # --- state ---------------------------------------------------------------------------

    def refresh(self):
        if self.busy or not self.api.signed_in:
            return
        self.busy = True
        run_async(self.api.state, done=self._apply, failed=self._failed)

    def _failed(self, e):
        self.busy = False

    def _apply(self, s):
        self.busy = False
        if not s or (s.get("device") or {}).get("id") != self.device_id:
            # Something else (or nothing) is playing: show the last song as paused.
            if s and s.get("item") and not self.current:
                self.current = track(s["item"])
            self.playing = False
        else:
            self.current = track(s.get("item")) or self.current
            self.playing = s.get("is_playing", False)
            self.shuffle = s.get("shuffle_state", False)
            self.repeat = s.get("repeat_state", "off")
            vol = s["device"].get("volume_percent")
            self.volume = self.volume if vol is None else vol
            self.position = s.get("progress_ms") or 0
            self.stamp = time.monotonic()
        self.changed.emit()
        self.positionChanged.emit(self.position)
        self.poll.setInterval(4000 if self.playing else 15000)
        if self.playing and self.current:
            # Catch the song change right when it happens instead of up to a poll later.
            left = self.current["duration"] - self.position
            if 0 < left < 4000:
                self.soon.start(left + 400)

    def _tick(self):
        if self.playing and self.current:
            now = time.monotonic()
            self.position = min(self.position + int((now - self.stamp) * 1000), self.current["duration"])
            self.stamp = now
            self.positionChanged.emit(self.position)

    def _do(self, fn, *args, refresh=600):
        def done(_):
            self.soon.start(refresh)
        run_async(fn, *args, done=done, failed=self.error.emit)

    # --- actions ---------------------------------------------------------------------------

    def play_tracks(self, tracks, index):
        uris = [t["uri"] for t in tracks]
        self._optimistic(tracks[index])
        self._do(self.api.play, self.device_id, uris, index)

    def play_context(self, context_uri, start=None):
        if start:
            self._optimistic(start)
        self._do(self.api.play, self.device_id, None, 0, context_uri, start["uri"] if start else None)

    def _optimistic(self, t):
        self.current, self.playing, self.position, self.stamp = t, True, 0, time.monotonic()
        self.changed.emit()
        self.positionChanged.emit(0)

    def toggle(self):
        if not self.current:
            return
        self.playing = not self.playing
        self.stamp = time.monotonic()
        self.changed.emit()
        if self.playing:
            def failed(_e):  # nothing loaded on our device yet: move playback here
                self._do(self.api.transfer, self.device_id, True, refresh=1200)
            run_async(self.api.resume, self.device_id, done=lambda _: self.soon.start(600), failed=failed)
        else:
            self._do(self.api.pause)

    def next(self):
        self._do(self.api.next)

    def previous(self):
        self._do(self.api.previous)

    def seek(self, ms):
        self.position, self.stamp = ms, time.monotonic()
        self._do(self.api.seek, ms, refresh=800)

    def set_volume(self, percent):
        self.volume = percent
        self._do(self.api.volume, percent, refresh=1500)

    def toggle_shuffle(self):
        self.shuffle = not self.shuffle
        self.changed.emit()
        self._do(self.api.shuffle, self.shuffle)

    def cycle_repeat(self):
        self.repeat = {"off": "context", "context": "track", "track": "off"}[self.repeat]
        self.changed.emit()
        self._do(self.api.repeat, self.repeat)
