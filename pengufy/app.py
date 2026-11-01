"""Pengufy: a simple, single-page Spotify player for Linux."""

import signal
import sys
from pathlib import Path

from PyQt6.QtCore import QSize, Qt, QTimer, QUrl
from PyQt6.QtGui import QColor, QDesktopServices, QIcon, QKeySequence, QPainter, QPixmap, QShortcut
from PyQt6.QtNetwork import QLocalServer, QLocalSocket
from PyQt6.QtWidgets import (QApplication, QFrame, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem,
                             QMainWindow, QMenu, QPushButton, QSizePolicy, QStackedWidget, QVBoxLayout, QWidget)

from . import icons, theme
from .engine import Engine
from .images import images, rounded
from .playback import Playback
from .spotify import REDIRECT_URI, SEARCH_LIMIT, Spotify, fmt_time, run_async, settings
from .widgets import Cover, Seek, TrackTable, label, tool

APP_ID = "io.github.htulu07.Pengufy"
APP_NAME = "Pengufy"
VERSION = "1.0.0"
SOCKET_NAME = "pengufy-instance"
DASHBOARD = "https://developer.spotify.com/dashboard"


def app_icon() -> QIcon:
    icon = QIcon.fromTheme(APP_ID)
    if icon.isNull():
        for base in (Path(__file__).resolve().parent, Path(__file__).resolve().parent.parent / "data"):
            path = base / f"{APP_ID}.svg"
            if path.exists():
                return QIcon(str(path))
    return icon


def open_url(url):
    QDesktopServices.openUrl(QUrl(url))


def liked_tile(size, radius) -> QPixmap:
    pix = QPixmap(size * 2, size * 2)
    pix.setDevicePixelRatio(2)
    pix.fill(Qt.GlobalColor.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(theme.ACCENT_DARK))
    p.drawRoundedRect(0, 0, size, size, radius, radius)
    p.drawPixmap(size // 4, size // 4, icons.pixmap("heart", "#ffffff", size // 2))
    p.end()
    return pix


def panel() -> QFrame:
    f = QFrame()
    f.setObjectName("panel")
    return f


# --- first start ---------------------------------------------------------------------

class Setup(QWidget):
    """Two steps: sign the sound engine in, then sign this app in with the user's own Client ID."""

    def __init__(self, win):
        super().__init__()
        self.win = win
        outer = QVBoxLayout(self)
        outer.addStretch()
        box = panel()
        box.setFixedWidth(560)
        box.setMinimumHeight(560)  # room for the wrapped lines; QVBoxLayout underestimates them
        lay = QVBoxLayout(box)
        lay.setContentsMargins(40, 36, 40, 36)
        lay.setSpacing(12)
        logo = QLabel()
        logo.setFixedSize(72, 72)
        logo.setPixmap(win.icon.pixmap(QSize(72, 72), 2.0))
        lay.addWidget(logo, 0, Qt.AlignmentFlag.AlignHCenter)
        title = label("Welcome to Pengufy", "h2")
        title.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        lay.addWidget(title)
        lay.addWidget(label("Spotify Premium is required. You only do this once.", "dim"), 0,
                      Qt.AlignmentFlag.AlignHCenter)
        lay.addSpacing(12)

        lay.addWidget(label("1. Connect the player", "h3"))
        lay.addWidget(label("Pengufy plays music with its own small engine. Sign it in to Spotify in your "
                            "browser.", "dim", wrap=True))
        self.engine_btn = QPushButton("Connect player")
        self.engine_btn.setObjectName("accent")
        self.engine_btn.clicked.connect(self.connect_engine)
        lay.addWidget(self.engine_btn, 0, Qt.AlignmentFlag.AlignLeft)
        lay.addSpacing(12)

        lay.addWidget(label("2. Sign in for search and your library", "h3"))
        help_text = label(f"Create an app at <a href='{DASHBOARD}' style='color:{theme.ACCENT}'>"
                          f"developer.spotify.com/dashboard</a> with the redirect URI "
                          f"<b>{REDIRECT_URI}</b> and Web API checked, then paste its Client ID here.",
                          "dim", wrap=True)
        help_text.setOpenExternalLinks(True)
        help_text.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
        lay.addWidget(help_text)
        row = QHBoxLayout()
        self.client = QLineEdit(win.api.client_id)
        self.client.setPlaceholderText("Client ID")
        self.client.setObjectName("plain")
        self.client.returnPressed.connect(self.sign_in)
        self.sign_btn = QPushButton("Sign in")
        self.sign_btn.setObjectName("accent")
        self.sign_btn.clicked.connect(self.sign_in)
        row.addWidget(self.client, 1)
        row.addWidget(self.sign_btn)
        lay.addLayout(row)
        self.status = label("", "small", wrap=True)
        lay.addWidget(self.status)
        outer.addWidget(box, 0, Qt.AlignmentFlag.AlignHCenter)
        outer.addStretch()

        e = win.engine
        e.loginUrl.connect(open_url)
        e.loggedIn.connect(self.refresh)
        e.loginFailed.connect(lambda msg: (self.status.setText(msg), self.refresh()))
        self.refresh()

    def refresh(self):
        e = self.win.engine
        if not e.binary:
            self.engine_btn.setText("Engine missing — run install.sh again")
            self.engine_btn.setEnabled(False)
        elif e.logged_in:
            self.engine_btn.setText("✓  Player connected")
            self.engine_btn.setEnabled(False)
        else:
            self.engine_btn.setText("Connect player")
            self.engine_btn.setEnabled(True)
        if e.logged_in and self.win.api.signed_in:
            self.win.ready()

    def connect_engine(self):
        self.engine_btn.setEnabled(False)
        self.engine_btn.setText("Waiting for the browser…")
        self.win.engine.login()

    def sign_in(self):
        cid = self.client.text().strip()
        if len(cid) != 32:
            self.status.setText("That doesn't look like a Client ID (it has 32 letters and numbers).")
            return
        self.win.api.set_client_id(cid)
        self.sign_btn.setEnabled(False)
        self.status.setText("Finish signing in in your browser…")

        def done(user):
            self.sign_btn.setEnabled(True)
            self.status.setText(f"Signed in as {user.get('display_name') or user.get('id')}.")
            self.refresh()

        def failed(e):
            self.sign_btn.setEnabled(True)
            self.status.setText(f"Sign-in failed: {e}")

        run_async(self.win.api.sign_in, open_url, done=done, failed=failed, owner=self)


# --- player bar ------------------------------------------------------------------------

class PlayerBar(QWidget):
    def __init__(self, win):
        super().__init__()
        self.win = win
        pb = win.playback
        self.setObjectName("playerBar")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        self.setFixedHeight(88)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 8, 16, 8)

        left = QHBoxLayout()
        left.setSpacing(12)
        self.cover = Cover(56, 6)
        left.addWidget(self.cover)
        text = QVBoxLayout()
        text.setSpacing(2)
        text.addStretch()
        self.title = label("", "h3")
        self.artist = label("", "dim")
        for w in (self.title, self.artist):
            w.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
            text.addWidget(w)
        text.addStretch()
        left.addLayout(text, 1)
        self.like = tool("heart-outline", "Save to Liked Songs", 20, checkable=True, checked_name="heart")
        self.like.clicked.connect(self.toggle_like)
        left.addWidget(self.like)
        lw = QWidget()
        lw.setLayout(left)
        lw.setFixedWidth(320)
        lay.addWidget(lw)

        mid = QVBoxLayout()
        mid.setSpacing(4)
        buttons = QHBoxLayout()
        buttons.setSpacing(14)
        buttons.addStretch()
        self.shuffle = tool("shuffle", "Shuffle", 20, checkable=True)
        self.shuffle.clicked.connect(pb.toggle_shuffle)
        self.prev = tool("previous", "Previous", 26, color=theme.TEXT, active="#ffffff")
        self.prev.clicked.connect(pb.previous)
        self.play = tool("play", "Play", 22, name="play", color=theme.ON_ACCENT, active=theme.ON_ACCENT,
                         checked=None)
        self.play.setFixedSize(36, 36)
        self.play.clicked.connect(pb.toggle)
        self.next = tool("next", "Next", 26, color=theme.TEXT, active="#ffffff")
        self.next.clicked.connect(pb.next)
        self.repeat = tool("repeat", "Repeat", 20, checkable=True)
        self.repeat.clicked.connect(pb.cycle_repeat)
        for b in (self.shuffle, self.prev, self.play, self.next, self.repeat):
            buttons.addWidget(b)
        buttons.addStretch()
        mid.addLayout(buttons)
        seek = QHBoxLayout()
        self.pos = label("0:00", "small")
        self.pos.setFixedWidth(44)
        self.pos.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.len = label("0:00", "small")
        self.len.setFixedWidth(44)
        self.slider = Seek()
        self.slider.setRange(0, 0)
        self.slider.sliderMoved.connect(lambda v: self.pos.setText(fmt_time(v)))
        self.slider.sliderReleased.connect(lambda: pb.seek(self.slider.value()))
        seek.addWidget(self.pos)
        seek.addWidget(self.slider, 1)
        seek.addWidget(self.len)
        mid.addLayout(seek)
        mw = QWidget()
        mw.setLayout(mid)
        mw.setMaximumWidth(720)
        lay.addWidget(mw, 1)

        right = QHBoxLayout()
        right.addStretch()
        self.mute = tool("volume", "Mute", 20)
        self.mute.clicked.connect(self.toggle_mute)
        self.volume = Seek()
        self.volume.setRange(0, 100)
        self.volume.setFixedWidth(110)
        self.volume.sliderReleased.connect(lambda: pb.set_volume(self.volume.value()))
        self.volume.sliderMoved.connect(self._volume_icon)
        right.addWidget(self.mute)
        right.addWidget(self.volume)
        rw = QWidget()
        rw.setLayout(right)
        rw.setFixedWidth(320)
        lay.addWidget(rw)

        self.liked_uri = None
        pb.changed.connect(self.on_state)
        pb.positionChanged.connect(self.on_position)
        self.on_state()

    def on_state(self):
        pb = self.win.playback
        t = pb.current
        for w in (self.like, self.slider, self.play, self.prev, self.next, self.shuffle, self.repeat):
            w.setEnabled(t is not None)
        self.play.setIcon(icons.icon("pause" if pb.playing else "play", theme.ON_ACCENT, theme.ON_ACCENT, None))
        self.play.setToolTip("Pause" if pb.playing else "Play")
        self.shuffle.setChecked(pb.shuffle)
        self.repeat.setChecked(pb.repeat != "off")
        self.repeat.setIcon(icons.icon("repeat-one" if pb.repeat == "track" else "repeat"))
        self.repeat.setToolTip({"off": "Repeat", "context": "Repeat all", "track": "Repeat one"}[pb.repeat])
        if not self.volume.isSliderDown():
            self.volume.setValue(pb.volume)
            self._volume_icon(pb.volume)
        if not t:
            self.title.setText("")
            self.artist.setText("Pick a song to start")
            self.cover.load("")
            return
        self.cover.load(t["cover"])
        self.title.setText(t["title"])
        self.title.setToolTip(f"{t['title']}\n{t['album']}")
        self.artist.setText(t["artists"])
        self.slider.setRange(0, t["duration"])
        self.len.setText(fmt_time(t["duration"]))
        if t["uri"] != self.liked_uri:
            self.liked_uri = t["uri"]
            self.like.setChecked(t["uri"] in self.win.liked_uris)
            run_async(self.win.api.is_liked, t["uri"], owner=self,
                      done=lambda v, u=t["uri"]: u == self.liked_uri and self.like.setChecked(v))

    def on_position(self, ms):
        if not self.slider.isSliderDown():
            self.slider.setValue(ms)
            self.pos.setText(fmt_time(ms))

    def _volume_icon(self, v):
        self.mute.setIcon(icons.icon("mute" if v == 0 else "volume"))

    def toggle_mute(self):
        pb = self.win.playback
        if pb.volume > 0:
            self.saved_volume = pb.volume
            pb.set_volume(0)
        else:
            pb.set_volume(getattr(self, "saved_volume", 70))
        self.on_state()

    def toggle_like(self):
        t = self.win.playback.current
        if t:
            self.win.set_liked(t, self.like.isChecked())


# --- main window ---------------------------------------------------------------------------

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.settings = settings()
        self.icon = app_icon()
        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(self.icon)
        self.setMinimumSize(900, 560)
        if not self.restoreGeometry(self.settings.value("geometry", b"")):
            self.resize(1280, 820)

        self.api = Spotify()
        self.engine = Engine()
        self.playback = Playback(self.api)
        self.playback.error.connect(self.on_error)
        self.liked_uris = set()
        self.liked_tracks = None
        self.view = None        # ("liked",) / ("playlist", data) / ("search", query)
        self.search_offset = 0
        self.loading_more = False
        self.started = False

        root = QWidget()
        root.setObjectName("root")
        self.setCentralWidget(root)
        self.stack = QStackedWidget()
        QVBoxLayout(root).addWidget(self.stack)
        root.layout().setContentsMargins(0, 0, 0, 0)
        self.toast_label = QLabel(self)
        self.toast_label.setStyleSheet(f"background:{theme.TEXT}; color:{theme.ON_ACCENT}; border-radius:8px; "
                                       f"padding:8px 14px; font-weight:600;")
        self.toast_label.hide()
        self.toast_timer = QTimer(self, singleShot=True, interval=3000, timeout=self.toast_label.hide)
        # Setup switches straight to the main view when everything is already signed in.
        self.setup = Setup(self)
        self.stack.addWidget(self.setup)

    # --- building the main view (after setup) --------------------------------------------

    def ready(self):
        if self.started:
            return
        self.started = True
        main = QWidget()
        outer = QVBoxLayout(main)
        outer.setContentsMargins(8, 8, 8, 0)
        outer.setSpacing(8)
        body = QHBoxLayout()
        body.setSpacing(8)

        side = panel()
        side.setFixedWidth(280)
        sl = QVBoxLayout(side)
        sl.setContentsMargins(12, 16, 12, 12)
        head = QHBoxLayout()
        lib_icon = QLabel()
        lib_icon.setPixmap(icons.pixmap("library", theme.DIM, 22))
        head.addWidget(lib_icon)
        head.addWidget(label("Your Library", "h3"), 1)
        self.account = tool("account", "Account", 22)
        self.account.clicked.connect(self.account_menu)
        head.addWidget(self.account)
        sl.addLayout(head)
        self.library = QListWidget()
        self.library.setIconSize(QSize(40, 40))
        self.library.setVerticalScrollMode(QListWidget.ScrollMode.ScrollPerPixel)
        self.library.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.library.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.library.currentItemChanged.connect(self.open_item)
        sl.addWidget(self.library, 1)
        body.addWidget(side)

        content = panel()
        cl = QVBoxLayout(content)
        cl.setContentsMargins(20, 16, 20, 8)
        cl.setSpacing(12)
        self.search = QLineEdit()
        self.search.setPlaceholderText("What do you want to listen to?")
        self.search.addAction(QIcon(icons.pixmap("search", theme.DIM)), QLineEdit.ActionPosition.LeadingPosition)
        self.search.setObjectName("plain")
        self.search.setMaximumWidth(520)
        self.search.returnPressed.connect(self.do_search)
        cl.addWidget(self.search)
        header = QHBoxLayout()
        header.setSpacing(16)
        self.header_cover = Cover(72, 6)
        header.addWidget(self.header_cover)
        titles = QVBoxLayout()
        titles.addStretch()
        self.heading = label("", "h2")
        self.subheading = label("", "dim")
        titles.addWidget(self.heading)
        titles.addWidget(self.subheading)
        titles.addStretch()
        header.addLayout(titles, 1)
        self.play_all = tool("play", "Play", 28, name="bigPlay", color=theme.ON_ACCENT, active=theme.ON_ACCENT,
                             checked=None)
        self.play_all.setFixedSize(52, 52)
        self.play_all.clicked.connect(self.play_view)
        header.addWidget(self.play_all)
        cl.addLayout(header)
        self.table = TrackTable()
        self.table.played.connect(self.play_row)
        self.table.nearEnd.connect(self.more_results)
        self.note = label("", "dim", wrap=True)
        self.note.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cl.addWidget(self.table, 1)
        cl.addWidget(self.note, 1)
        body.addWidget(content, 1)
        outer.addLayout(body, 1)

        self.bar = PlayerBar(self)
        outer.addWidget(self.bar)
        self.stack.addWidget(main)
        self.stack.setCurrentWidget(main)
        self.playback.changed.connect(lambda: self.table.model_.set_current(
            self.playback.current["uri"] if self.playback.current else None))
        self.playback.deviceChanged.connect(lambda ok: ok or self.toast("The player didn't start. Try reopening "
                                                                       "Pengufy."))

        QShortcut(QKeySequence("Ctrl+F"), self, lambda: (self.search.setFocus(), self.search.selectAll()))
        QShortcut(QKeySequence("Ctrl+L"), self, lambda: (self.search.setFocus(), self.search.selectAll()))
        QShortcut(QKeySequence("Ctrl+Space"), self, self.playback.toggle)
        QShortcut(QKeySequence("Ctrl+Right"), self, self.playback.next)
        QShortcut(QKeySequence("Ctrl+Left"), self, self.playback.previous)

        self.engine.start()
        self.playback.find_device()
        run_async(self.api.me, done=lambda _: self.load_library(), failed=self.on_error, owner=self)

    # --- library ------------------------------------------------------------------------

    def load_library(self):
        self.library.clear()
        liked = QListWidgetItem(self._liked_icon(), "Liked Songs")
        liked.setData(Qt.ItemDataRole.UserRole, ("liked",))
        self.library.addItem(liked)
        self.library.setCurrentItem(liked)
        run_async(self.api.playlists, done=self._playlists, failed=self.on_error, owner=self)

    def _liked_icon(self) -> QIcon:
        return QIcon(liked_tile(40, 4))

    def _playlists(self, playlists):
        for pl in playlists:
            item = QListWidgetItem(f"{pl['name']}\n{pl['owner']}")
            item.setIcon(QIcon(rounded(None, 40, 40, 4)))
            item.setData(Qt.ItemDataRole.UserRole, ("playlist", pl))
            self.library.addItem(item)
            if pl["thumb"]:
                images().load(pl["thumb"], self.library,
                              lambda img, it=item: it.setIcon(QIcon(rounded(img, 40, 40, 4))))

    def open_item(self, item, _prev=None):
        if not item:
            return
        data = item.data(Qt.ItemDataRole.UserRole)
        if data[0] == "liked":
            self.show_liked()
        else:
            self.show_playlist(data[1])

    def show_tracks(self, view, title, subtitle, tracks, cover="", note=""):
        self.view = view
        self.heading.setText(title)
        self.subheading.setText(subtitle)
        self.header_cover.setVisible(view[0] != "search")
        self.header_cover.load(cover)
        if view == ("liked",):
            self.header_cover.url = None
            self.header_cover.setPixmap(liked_tile(72, 6))
        self.table.model_.set_tracks(tracks)
        self.table.model_.set_current(self.playback.current["uri"] if self.playback.current else None)
        self.table.scrollToTop()
        self.table.setVisible(bool(tracks))
        self.note.setText(note)
        self.note.setVisible(not tracks)
        self.play_all.setVisible(bool(tracks) or view[0] == "playlist")

    def show_liked(self):
        if self.liked_tracks is not None:
            self.show_tracks(("liked",), "Liked Songs", f"{len(self.liked_tracks)} songs", self.liked_tracks)
            return
        self.show_tracks(("liked",), "Liked Songs", "", [], note="Loading…")

        def done(tracks):
            self.liked_tracks = tracks
            self.liked_uris = {t["uri"] for t in tracks}
            if self.view == ("liked",):
                self.show_liked()
        run_async(self.api.liked, done=done, failed=self.on_error, owner=self)

    def show_playlist(self, pl):
        view = ("playlist", pl["id"])
        self.current_playlist = pl
        if not pl["readable"]:
            self.show_tracks(view, pl["name"], f"by {pl['owner']}", [], pl["thumb"],
                             "Spotify only lets apps like this one list songs of playlists you own.\n"
                             "Press play to listen to it anyway.")
            return
        self.show_tracks(view, pl["name"], f"by {pl['owner']}", [], pl["thumb"], "Loading…")

        def done(tracks):
            if self.view == view:
                self.show_tracks(view, pl["name"], f"by {pl['owner']} · {len(tracks)} songs", tracks, pl["thumb"],
                                 "This playlist is empty.")
        run_async(self.api.playlist_tracks, pl["id"], done=done, failed=self.on_error, owner=self)

    # --- search -------------------------------------------------------------------------

    def do_search(self):
        query = self.search.text().strip()
        if not query:
            return
        self.library.setCurrentItem(None)
        self.library.clearSelection()
        view = ("search", query)
        self.search_offset = 0
        self.show_tracks(view, f"Results for “{query}”", "", [], note="Searching…")

        def done(tracks):
            if self.view == view:
                # Dev Mode search pages are often short but not the last, so step by the page size.
                self.search_offset = SEARCH_LIMIT
                self.show_tracks(view, f"Results for “{query}”", "", tracks, note="Searching…" if not tracks
                                 else "")
                self.fill_results()
        run_async(self.api.search, query, done=done, failed=self.on_error, owner=self)

    def fill_results(self):
        """Keep loading pages until the list can scroll (scrolling then loads the rest)."""
        QTimer.singleShot(100, lambda: self.table.verticalScrollBar().maximum() == 0 and self.more_results())

    def more_results(self):
        if not self.view or self.view[0] != "search" or self.loading_more or not self.search_offset \
                or self.search_offset >= 200:  # stop after 20 pages
            return
        self.loading_more = True
        view = self.view

        def done(tracks):
            self.loading_more = False
            if self.view != view:
                return
            self.search_offset = self.search_offset + SEARCH_LIMIT if tracks else 200  # empty page: no more
            seen = {t["uri"] for t in self.table.tracks}
            new = [t for t in tracks if t["uri"] not in seen]
            if new and not self.table.tracks:
                self.show_tracks(view, self.heading.text(), "", new)
            elif new:
                self.table.model_.add_tracks(new)
            if not self.table.tracks and self.search_offset >= 200:
                self.show_tracks(view, self.heading.text(), "", [], note="Nothing found.")
            else:
                self.fill_results()
        run_async(self.api.search, view[1], self.search_offset, done=done, owner=self,
                  failed=lambda e: setattr(self, "loading_more", False))

    # --- playing ------------------------------------------------------------------------

    def play_row(self, row):
        tracks = self.table.tracks
        if not self.playback.device_id:
            self.toast("The player is still starting…")
            return
        if not tracks[row]["playable"]:
            self.toast("This song isn't available.")
            return
        if self.view[0] == "playlist":
            self.playback.play_context(self.current_playlist["uri"], tracks[row])
        else:
            self.playback.play_tracks(tracks, row)

    def play_view(self):
        if not self.playback.device_id:
            self.toast("The player is still starting…")
        elif self.view[0] == "playlist":
            self.playback.play_context(self.current_playlist["uri"],
                                       self.table.tracks[0] if self.table.tracks else None)
        elif self.table.tracks:
            self.play_row(0)

    def set_liked(self, t, liked):
        if liked:
            self.liked_uris.add(t["uri"])
            if self.liked_tracks is not None and t["uri"] not in {x["uri"] for x in self.liked_tracks}:
                self.liked_tracks.insert(0, t)
        else:
            self.liked_uris.discard(t["uri"])
            if self.liked_tracks is not None:
                self.liked_tracks = [x for x in self.liked_tracks if x["uri"] != t["uri"]]
        if self.view == ("liked",):
            self.show_liked()
        run_async(self.api.set_liked, t["uri"], liked, failed=self.on_error, owner=self)
        self.toast("Added to Liked Songs" if liked else "Removed from Liked Songs")

    # --- misc -----------------------------------------------------------------------------

    def account_menu(self):
        menu = QMenu(self)
        name = self.api.user.get("display_name") or self.api.user.get("id")
        if name:
            menu.addAction(name).setEnabled(False)
            menu.addSeparator()
        menu.addAction("Reload library", lambda: (setattr(self, "liked_tracks", None), self.load_library()))
        menu.addAction("Sign out", self.sign_out)
        menu.exec(self.account.mapToGlobal(self.account.rect().bottomLeft()))

    def sign_out(self):
        self.api.sign_out()
        self.engine.stop()
        QApplication.quit()

    def on_error(self, e):
        if "No active device" in e or "NO_ACTIVE_DEVICE" in e:
            e = "The player isn't ready yet. Try again in a moment."
        self.toast(e if len(e) < 120 else e[:117] + "…")

    def toast(self, text):
        self.toast_label.setText(text)
        self.toast_label.adjustSize()
        bar = getattr(self, "bar", None)
        self.toast_label.move((self.width() - self.toast_label.width()) // 2,
                              self.height() - (bar.height() if bar else 0) - self.toast_label.height() - 16)
        self.toast_label.show()
        self.toast_label.raise_()
        self.toast_timer.start()

    def closeEvent(self, e):
        self.settings.setValue("geometry", self.saveGeometry())
        self.engine.stop()
        super().closeEvent(e)


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("pengufy")
    app.setApplicationDisplayName(APP_NAME)
    app.setApplicationVersion(VERSION)
    app.setDesktopFileName(APP_ID)
    app.setWindowIcon(app_icon())
    app.setStyle("Fusion")
    app.setPalette(theme.palette())
    app.setStyleSheet(theme.STYLE)

    # One instance only: a second launch just brings the window up.
    probe = QLocalSocket()
    probe.connectToServer(SOCKET_NAME)
    if probe.waitForConnected(300):
        probe.write(b"show")
        probe.waitForBytesWritten(300)
        return 0
    QLocalServer.removeServer(SOCKET_NAME)
    server = QLocalServer(app)
    server.listen(SOCKET_NAME)

    window = MainWindow()
    app.aboutToQuit.connect(window.engine.stop)
    # Quit cleanly (and stop the engine) on Ctrl+C or a plain kill; Python only sees signals between Qt events.
    signal.signal(signal.SIGINT, lambda *_: app.quit())
    signal.signal(signal.SIGTERM, lambda *_: app.quit())
    heartbeat = QTimer(interval=500, timeout=lambda: None)
    heartbeat.start()
    server.newConnection.connect(lambda: (server.nextPendingConnection(), window.showNormal(),
                                          window.raise_(), window.activateWindow()))
    window.show()
    return app.exec()
