"""The sound engine: a private spotifyd that shows up as a Spotify Connect device called "Pengufy"."""

import os
import re
import shutil
from pathlib import Path

from PyQt6.QtCore import QObject, QProcess, QTimer, pyqtSignal

from .spotify import data_dir

DEVICE_NAME = "Pengufy"


def find_spotifyd() -> str | None:
    here = Path(__file__).resolve().parent
    for path in (os.environ.get("PENGUFY_SPOTIFYD"), here.parent / "bin" / "spotifyd",
                 Path.home() / ".local/lib/pengufy/bin/spotifyd"):
        if path and os.access(path, os.X_OK):
            return str(path)
    return shutil.which("spotifyd")


class Engine(QObject):
    loginUrl = pyqtSignal(str)
    loggedIn = pyqtSignal()
    loginFailed = pyqtSignal(str)
    stateChanged = pyqtSignal(bool)  # running

    def __init__(self):
        super().__init__()
        self.binary = find_spotifyd()
        self.dir = data_dir() / "engine"
        self.dir.mkdir(mode=0o700, exist_ok=True)
        self.dir.chmod(0o700)  # holds the engine's Spotify login
        self.proc = None
        self.auth = None
        self.wanted = False
        self.restarts = 0

    @property
    def logged_in(self) -> bool:
        return (self.dir / "oauth" / "credentials.json").exists()

    @property
    def running(self) -> bool:
        return self.proc is not None and self.proc.state() == QProcess.ProcessState.Running

    # --- one-time sign-in of the engine itself -----------------------------------------

    def login(self):
        if self.auth:
            self.auth.kill()
        self.auth = QProcess(self)
        self.auth.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        self.auth.readyReadStandardOutput.connect(self._auth_output)
        self.auth.finished.connect(self._auth_finished)
        self.auth.start(self.binary, ["authenticate", "-c", str(self.dir), "--oauth-port", "8898"])

    def _auth_output(self):
        text = bytes(self.auth.readAllStandardOutput()).decode(errors="replace")
        m = re.search(r"Browse to: (\S+)", text)
        if m:
            self.loginUrl.emit(m.group(1))

    def _auth_finished(self, code, _status):
        self.auth = None
        creds = self.dir / "oauth" / "credentials.json"
        if code == 0 and creds.exists():
            creds.chmod(0o600)
            self.loggedIn.emit()
        else:
            self.loginFailed.emit("The player couldn't sign in to Spotify.")

    # --- running -------------------------------------------------------------------------

    def start(self):
        self.wanted = True
        if self.running or not self.binary or not self.logged_in:
            return
        # An engine left over from a crash would show up as a second "Pengufy" device.
        QProcess.execute("pkill", ["-f", f"^{re.escape(self.binary)} .*-c {re.escape(str(self.dir))} "])
        self.proc = QProcess(self)
        self.proc.setProcessChannelMode(QProcess.ProcessChannelMode.ForwardedErrorChannel)
        self.proc.setStandardOutputFile(QProcess.nullDevice())
        self.proc.finished.connect(self._finished)
        self.proc.start(self.binary, [
            "--no-daemon", "-c", str(self.dir), "--no-audio-cache",
            "--device-name", DEVICE_NAME, "--device-type", "computer",
            "--backend", "pulseaudio", "--bitrate", "320", "--volume-controller", "soft-volume",
            "--initial-volume", "70", "--disable-discovery", "--use-mpris"])
        self.stateChanged.emit(True)

    def _finished(self, *_):
        self.proc = None
        self.stateChanged.emit(False)
        if self.wanted and self.restarts < 5:
            self.restarts += 1
            QTimer.singleShot(2000, self.start)

    def stop(self):
        self.wanted = False
        if self.running:
            self.proc.terminate()
            if not self.proc.waitForFinished(2000):
                self.proc.kill()
