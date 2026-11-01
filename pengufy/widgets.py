"""Small reusable pieces: buttons, covers, the song list, the seek slider."""

from PyQt6.QtCore import QAbstractTableModel, QModelIndex, QRect, QRectF, QSize, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QPainter
from PyQt6.QtWidgets import (QAbstractItemView, QHeaderView, QLabel, QSlider, QStyle, QStyledItemDelegate,
                             QTableView, QToolButton)

from . import icons, theme
from .images import images, rounded
from .spotify import fmt_time


def label(text="", name=None, wrap=False) -> QLabel:
    lab = QLabel(text)
    if name:
        lab.setObjectName(name)
    lab.setWordWrap(wrap)
    return lab


def tool(icon_name, tip, size=20, checkable=False, name=None, **kw) -> QToolButton:
    b = QToolButton()
    b.setIcon(icons.icon(icon_name, **kw))
    b.setIconSize(QSize(size, size))
    b.setToolTip(tip)
    b.setCheckable(checkable)
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    if name:
        b.setObjectName(name)
    return b


class Cover(QLabel):
    """A rounded cover image that loads itself."""

    def __init__(self, size, radius=6):
        super().__init__()
        self.size_, self.radius = size, radius
        self.setFixedSize(size, size)
        self.url = None
        self.setPixmap(rounded(None, size, size, radius))

    def load(self, url):
        if url == self.url:
            return
        self.url = url
        self.setPixmap(rounded(None, self.size_, self.size_, self.radius))
        if url:
            images().load(url, self, lambda img, u=url: u == self.url and self.setPixmap(
                rounded(img, self.size_, self.size_, self.radius)))


class Seek(QSlider):
    """A slider that jumps to where you click and only reports on release."""

    def __init__(self):
        super().__init__(Qt.Orientation.Horizontal)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            value = QStyle.sliderValueFromPosition(self.minimum(), self.maximum(), int(e.position().x()),
                                                   self.width())
            self.setValue(value)
            self.setSliderDown(True)
            self.sliderMoved.emit(value)
        super().mousePressEvent(e)


# --- the song list -------------------------------------------------------------------

class TrackModel(QAbstractTableModel):
    HEADERS = ("#", "Title", "Album", "")

    def __init__(self):
        super().__init__()
        self.tracks = []
        self.pixmaps = {}
        self.current = None

    def set_tracks(self, tracks):
        self.beginResetModel()
        self.tracks = tracks
        self.endResetModel()

    def add_tracks(self, tracks):
        self.beginInsertRows(QModelIndex(), len(self.tracks), len(self.tracks) + len(tracks) - 1)
        self.tracks += tracks
        self.endInsertRows()

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.tracks)

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else 4

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return self.HEADERS[section]
        return None

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        t = self.tracks[index.row()]
        if role == Qt.ItemDataRole.ToolTipRole and index.column() in (1, 2):
            return f"{t['title']}\n{t['artists']}\n{t['album']}"
        return None

    def pixmap(self, row):
        url = self.tracks[row].get("thumb")
        if not url:
            return None
        if url not in self.pixmaps:
            self.pixmaps[url] = None
            images().load(url, self, lambda img, u=url: self._loaded(u, img))
        return self.pixmaps[url]

    def _loaded(self, url, img):
        self.pixmaps[url] = rounded(img, 40, 40, 4)
        for i, t in enumerate(self.tracks):
            if t.get("thumb") == url:
                idx = self.index(i, 1)
                self.dataChanged.emit(idx, idx)

    def set_current(self, uri):
        if uri != self.current:
            self.current = uri
            if self.tracks:
                self.dataChanged.emit(self.index(0, 0), self.index(len(self.tracks) - 1, 1))


class TrackDelegate(QStyledItemDelegate):
    def paint(self, p, option, index):
        model = index.model()
        t = model.tracks[index.row()]
        col = index.column()
        hovered = bool(option.state & QStyle.StateFlag.State_MouseOver)
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        p.save()
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = option.rect
        if selected or hovered:
            p.fillRect(r, QColor(theme.HOVER if selected else theme.CARD))
        is_current = model.current == t["uri"]
        color = QColor(theme.LINE2 if not t["playable"] else theme.ACCENT if is_current else theme.TEXT)
        fm = option.fontMetrics
        if col == 0:
            if hovered:
                p.drawPixmap(r.center().x() - 9, r.center().y() - 9, icons.pixmap("play", theme.TEXT, 18))
            elif is_current:
                p.drawPixmap(r.center().x() - 9, r.center().y() - 9, icons.pixmap("note", theme.ACCENT, 18))
            else:
                p.setPen(QColor(theme.DIM))
                p.drawText(r, Qt.AlignmentFlag.AlignCenter, str(index.row() + 1))
        elif col == 1:
            x = r.x() + 8
            pix = model.pixmap(index.row())
            cover = QRect(x, r.center().y() - 20, 40, 40)
            if pix:
                p.drawPixmap(cover, pix)
            else:
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QColor(theme.CARD))
                p.drawRoundedRect(QRectF(cover), 4, 4)
            x += 52
            width = r.right() - x - 8
            p.setPen(color)
            p.drawText(QRect(x, r.y() + 8, width, r.height() // 2 - 6),
                       Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignBottom,
                       fm.elidedText(t["title"], Qt.TextElideMode.ElideRight, width))
            p.setPen(QColor(theme.DIM))
            p.drawText(QRect(x, r.center().y() + 2, width, r.height() // 2 - 6),
                       Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop,
                       fm.elidedText(t["artists"], Qt.TextElideMode.ElideRight, width))
        elif col == 2:
            p.setPen(QColor(theme.DIM))
            p.drawText(r.adjusted(8, 0, -8, 0), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                       fm.elidedText(t["album"], Qt.TextElideMode.ElideRight, r.width() - 16))
        else:
            p.setPen(QColor(theme.DIM))
            p.drawText(r.adjusted(0, 0, -16, 0), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                       fmt_time(t["duration"]))
        p.restore()


class TrackTable(QTableView):
    ROW = 56
    played = pyqtSignal(int)
    nearEnd = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.model_ = TrackModel()
        self.setModel(self.model_)
        self.setItemDelegate(TrackDelegate(self))
        self.setMouseTracking(True)
        self.setShowGrid(False)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.verticalHeader().hide()
        self.verticalHeader().setDefaultSectionSize(self.ROW)
        h = self.horizontalHeader()
        h.setHighlightSections(False)
        h.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        h.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        h.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        h.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        h.resizeSection(0, 48)
        h.resizeSection(3, 76)
        h.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.clicked.connect(lambda idx: idx.column() == 0 and self.played.emit(idx.row()))
        self.activated.connect(lambda idx: self.played.emit(idx.row()))
        self.verticalScrollBar().valueChanged.connect(self._scrolled)

    @property
    def tracks(self):
        return self.model_.tracks

    def _scrolled(self, value):
        if value > self.verticalScrollBar().maximum() - 3 * self.ROW:
            self.nearEnd.emit()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self.horizontalHeader().resizeSection(2, max(120, int(self.width() * 0.3)))
