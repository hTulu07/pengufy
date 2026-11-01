"""Cover art loading with a memory and disk cache."""

from collections import OrderedDict

from PyQt6 import sip
from PyQt6.QtCore import QObject, QRectF, Qt, QUrl
from PyQt6.QtGui import QColor, QImage, QPainter, QPainterPath, QPixmap
from PyQt6.QtNetwork import QNetworkAccessManager, QNetworkDiskCache, QNetworkReply, QNetworkRequest

from . import theme
from .spotify import cache_dir


class Images(QObject):
    def __init__(self):
        super().__init__()
        self.nam = QNetworkAccessManager(self)
        disk = QNetworkDiskCache(self)
        disk.setCacheDirectory(str(cache_dir() / "images"))
        disk.setMaximumCacheSize(300 * 1024 * 1024)
        self.nam.setCache(disk)
        self.memory = OrderedDict()  # url -> QImage
        self.waiting = {}            # url -> [(owner, callback)]

    def load(self, url: str, owner: QObject, callback):
        """callback(QImage) runs once the image is there, as long as owner still exists."""
        if not url:
            return
        if url.startswith("/"):  # local file
            img = QImage(url)
            if not img.isNull():
                callback(img)
            return
        if url in self.memory:
            self.memory.move_to_end(url)
            callback(self.memory[url])
            return
        if url in self.waiting:
            self.waiting[url].append((owner, callback))
            return
        self.waiting[url] = [(owner, callback)]
        req = QNetworkRequest(QUrl(url))
        req.setAttribute(QNetworkRequest.Attribute.CacheLoadControlAttribute,
                         QNetworkRequest.CacheLoadControl.PreferCache)
        reply = self.nam.get(req)
        reply.finished.connect(lambda: self._finished(url, reply))

    def _finished(self, url, reply):
        img = QImage()
        if reply.error() == QNetworkReply.NetworkError.NoError:
            img.loadFromData(reply.readAll())
        reply.deleteLater()
        if not img.isNull():
            self.memory[url] = img
            if len(self.memory) > 600:
                self.memory.popitem(last=False)
        for owner, callback in self.waiting.pop(url, []):
            if not img.isNull() and not sip.isdeleted(owner):
                callback(img)


IMAGES: Images | None = None


def images() -> Images:
    global IMAGES
    if IMAGES is None:
        IMAGES = Images()
    return IMAGES


def rounded(img: QImage | None, w: int, h: int, radius: float, dpr: float = 2.0, circle=False) -> QPixmap:
    """Cover image cropped to fill w x h with rounded corners (or a placeholder when img is None)."""
    pix = QPixmap(int(w * dpr), int(h * dpr))
    pix.setDevicePixelRatio(dpr)
    pix.fill(Qt.GlobalColor.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    path = QPainterPath()
    if circle:
        path.addEllipse(QRectF(0, 0, w, h))
    else:
        path.addRoundedRect(QRectF(0, 0, w, h), radius, radius)
    p.setClipPath(path)
    if img is None or img.isNull():
        p.fillRect(QRectF(0, 0, w, h), QColor(theme.CARD))
    else:
        scaled = img.scaled(int(w * dpr), int(h * dpr), Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                            Qt.TransformationMode.SmoothTransformation)
        sx = (scaled.width() - w * dpr) / 2
        sy = (scaled.height() - h * dpr) / 2
        p.drawImage(QRectF(0, 0, w, h), scaled, QRectF(sx, sy, w * dpr, h * dpr))
    p.end()
    return pix
