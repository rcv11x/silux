"""The Disk tab of Performance: how fast a folder's disk reads and writes.

A figure here comes with what makes it believable: the disk and the file
system it was measured on, the engine, whether anything went through the
page cache, the best and the worst lap next to the one in the middle, the
temperature, and the method in a line. What can't be measured, or has to be
read with care, is said as a note: what happened, why, and what to do.
"""

from __future__ import annotations

import dataclasses
import math
import os
import pathlib
import threading
import time
from typing import Optional

from PySide6.QtCore import QObject, QRectF, Qt, Signal
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ... import disktest, render
from ...disktest import GIB, MIB
from ...i18n import _
from ...settings import Preferences
from .. import theme
from ..theme import Palette, ui_font
from ..widgets import (
    Card,
    FoldingRow,
    Notice,
    ProgressLine,
    ReadableRoot,
    ScrollPage,
    Table,
    clear_layout,
    value_font,
)

# The bars share one scale, logarithmic and fixed, as CrystalDiskMark's and
# KDiskMark's do: from 0.1 MB/s to 100 000. Fixed, so that two screenshots
# of two machines compare by eye; and with its axis drawn, which theirs
# lack, so that a bar's length can be read.
SCALE_FROM = -1
SCALE_DECADES = 6
# A bar narrower than this says nothing and isn't drawn.
NARROWEST_BAR = 40
FILE_SIZES = (64 * MIB, 256 * MIB, GIB, 4 * GIB, 8 * GIB, 16 * GIB, 32 * GIB)
LAPS = tuple(range(1, 10))
# What a result that didn't measure is said with: the note's key, and
# whether it offers another folder or a smaller file.
ERRORS = {
    "in_memory": "folder", "network": "folder", "not_a_disk": "folder",
    "read_only": "folder", "no_write": "folder", "no_folder": "folder",
    "no_direct": "folder", "no_space": "smaller", "io": None, "no_module": None,
    "internal": None, "failed": None, "not_started": None,
}
# The notes that say a figure may not be the disk's, and those that say the
# test itself broke: the rest are facts to read the figures with.
DOUBTFUL = frozenset({"copy_on_write", "through_the_cache", "disk_moved_less", "disk_was_busy",
                      "noisy"})
BROKEN = frozenset({"io", "internal", "failed", "not_started"})
WARNINGS = ("rotational", "removable", "encrypted", "several_disks", "fuse_driver", "fuse",
            "zfs", "overlay", "loop", "copy_on_write", "through_the_cache", "disk_moved_less",
            "disk_was_busy", "queue_of_threads")
SEQUENTIAL, SINGLE = "SEQ1M Q8T1", "RND4K Q1T1"


def when(timestamp: float) -> str:
    return time.strftime("%d/%m/%Y %H:%M", time.localtime(timestamp))


def megabytes(bytes_per_second: Optional[float]) -> str:
    """A rate as the table writes it, in MB/s without the unit: «6 592»,
    «63.3»."""
    if bytes_per_second is None:
        return render.DASH
    value = bytes_per_second / 1e6
    return render.thousands(round(value)) if value >= 100 else f"{value:.1f}"


def microseconds(nanoseconds: Optional[float]) -> str:
    if nanoseconds is None:
        return render.DASH
    value = nanoseconds / 1e3
    if value >= 1000:
        return f"{value / 1e3:.1f} ms"
    return f"{value:.0f} µs" if value >= 100 else f"{value:.1f} µs"


def link_bytes_per_second(link) -> Optional[float]:
    """The most a PCIe link carries: its lanes, their speed and what the
    line code leaves of it."""
    per_lane = {2.5: 2.5e9 * 8 / 10, 5.0: 5e9 * 8 / 10, 8.0: 8e9 * 128 / 130,
                16.0: 16e9 * 128 / 130, 32.0: 32e9 * 128 / 130}
    if link is None or not link.current_width:
        return None
    bits = per_lane.get(link.current_speed_gts)
    return None if bits is None else bits / 8 * link.current_width


class Bar(QWidget):
    """One bar of the table, on the scale they all share."""

    def __init__(self, palette: Palette, soft: bool = False, parent=None):
        super().__init__(parent)
        self._p = palette
        self._soft = soft
        self._fraction: Optional[float] = None
        self._live = False
        self.setFixedHeight(10)
        # It gives way first: in a narrow window the figures stay and the
        # bars go.
        self.setMinimumWidth(0)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)

    def set_rate(self, bytes_per_second: Optional[float], live: bool = False) -> None:
        fraction = None
        if bytes_per_second:
            decades = math.log10(max(bytes_per_second / 1e6, 10 ** SCALE_FROM)) - SCALE_FROM
            fraction = min(max(decades / SCALE_DECADES, 0.0), 1.0)
        if (fraction, live) != (self._fraction, self._live):
            self._fraction, self._live = fraction, live
            self.update()

    def paintEvent(self, _event) -> None:  # noqa: N802
        if self.width() < NARROWEST_BAR:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        box = QRectF(0, 1, self.width(), self.height() - 2)
        painter.setBrush(self._p.q("line_soft"))
        painter.drawRoundedRect(box, 3, 3)
        if self._fraction:
            colour = "muted" if self._live else "accent"
            painter.setBrush(self._p.q(colour, 0.6 if self._soft and not self._live else 1.0))
            painter.drawRoundedRect(QRectF(0, 1, self.width() * self._fraction,
                                           self.height() - 2), 3, 3)
        painter.end()


class Axis(QWidget):
    """What the bars above it are measured against: a mark at each power of
    ten, with its figure where there is room."""

    def __init__(self, palette: Palette, parent=None):
        super().__init__(parent)
        self._p = palette
        self.setFont(ui_font(theme.METRICS.small_pt - 1))
        self.setFixedHeight(self.fontMetrics().height() + 6)
        self.setMinimumWidth(0)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)

    def paintEvent(self, _event) -> None:  # noqa: N802
        if self.width() < NARROWEST_BAR:
            return
        painter = QPainter(self)
        painter.setPen(self._p.q("muted"))
        metrics = self.fontMetrics()
        texts = {decade: render.thousands(10 ** (decade + SCALE_FROM))
                 for decade in range(1, SCALE_DECADES + 1)}
        # Every figure where the widest fits between two marks; where it
        # doesn't, one in two, or one in three.
        widest = max(metrics.horizontalAdvance(text) for text in texts.values()) + 8
        step = next((step for step in (1, 2, 3)
                     if widest <= step * self.width() / SCALE_DECADES), SCALE_DECADES)
        for decade in range(SCALE_DECADES + 1):
            x = min(self.width() * decade / SCALE_DECADES, self.width() - 1)
            painter.drawLine(int(x), 0, int(x), 3)
            if decade in texts and (decade - 1) % step == 0:
                width = metrics.horizontalAdvance(texts[decade])
                left = min(x - width / 2, self.width() - width)
                painter.drawText(QRectF(left, 4, width, metrics.height()),
                                 Qt.AlignmentFlag.AlignCenter, texts[decade])
        painter.end()


class SpeedTable(QWidget):
    """A row for each test: its name, and a bar and a figure for what it
    reads and for what it writes."""

    def __init__(self, palette: Palette, parent=None):
        super().__init__(parent)
        self._p = palette
        self._grid = QGridLayout(self)
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid.setHorizontalSpacing(10)
        self._grid.setVerticalSpacing(7)
        self._grid.setColumnStretch(1, 1)
        self._grid.setColumnStretch(3, 1)
        self._names: tuple[str, ...] = ()
        self._writes: Optional[bool] = None
        self._cells: dict[tuple[str, str], tuple[Bar, QLabel]] = {}

    def _build(self, names: tuple[str, ...], writes: bool) -> None:
        clear_layout(self._grid)
        self._cells = {}
        small = ui_font(theme.METRICS.small_pt)
        directions = ("read", "write") if writes else ("read",)
        for index, direction in enumerate(directions):
            head = QLabel(_(f"disktest.col.{direction}"))
            head.setObjectName("Muted")
            head.setFont(small)
            self._grid.addWidget(head, 0, 1 + 2 * index, 1, 2)
        for row, name in enumerate(names, start=1):
            label = QLabel(name)
            label.setFont(value_font())
            self._grid.addWidget(label, row, 0)
            for index, direction in enumerate(directions):
                bar = Bar(self._p, soft=direction == "write")
                figure = QLabel(render.DASH)
                figure.setFont(value_font())
                figure.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                figure.setMinimumWidth(figure.fontMetrics().horizontalAdvance("00 000*"))
                self._grid.addWidget(bar, row, 1 + 2 * index)
                self._grid.addWidget(figure, row, 2 + 2 * index)
                self._cells[name, direction] = (bar, figure)
        for index, _direction in enumerate(directions):
            self._grid.addWidget(Axis(self._p), len(names) + 1, 1 + 2 * index)
        unit = QLabel(_("disktest.unit"))
        unit.setObjectName("Muted")
        unit.setFont(small)
        self._grid.addWidget(unit, len(names) + 1, 0)
        self._names, self._writes = names, writes

    def set_rows(self, names: tuple[str, ...], writes: bool) -> None:
        """The tests to show, each with nothing measured yet."""
        if (names, writes) != (self._names, self._writes):
            self._build(names, writes)
        for bar, figure in self._cells.values():
            bar.set_rate(None)
            figure.setText(render.DASH)
            figure.setObjectName("")
            figure.setToolTip("")

    def set_cell(self, name: str, direction: str, bytes_per_second: Optional[float],
                 live: bool = False, note: str = "") -> None:
        """A test's figure; `live` while it is one lap's, still under way."""
        cell = self._cells.get((name, direction))
        if cell is None:
            return
        bar, figure = cell
        bar.set_rate(bytes_per_second, live)
        figure.setText(megabytes(bytes_per_second) + ("*" if note else ""))
        figure.setToolTip(note)
        if figure.objectName() != ("Muted" if live else ""):
            figure.setObjectName("Muted" if live else "")
            figure.style().unpolish(figure)
            figure.style().polish(figure)


class DiskTestRun(QObject):
    """A disk test under way, apart from the tab that shows it: the window
    rebuilds its pages, and the test, in its child process, carries on."""

    progressed = Signal(dict)
    # The result, and the history with it when it measured something.
    finished = Signal(object, object)
    _done = Signal(object)

    def __init__(self, parent: Optional[QObject] = None):
        super().__init__(parent)
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self.plan: Optional[disktest.Plan] = None
        self.model: Optional[str] = None
        # The last step told, and each lap's figure so far, for a tab that
        # arrives half way.
        self.last: dict = {}
        self.laps: dict[tuple[str, str], int] = {}
        self._done.connect(self._on_done)

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    @property
    def cancelling(self) -> bool:
        return self.running and self._stop.is_set()

    def start(self, plan: disktest.Plan, model: Optional[str] = None) -> bool:
        if self.running:
            return False
        self._stop.clear()
        self.plan, self.model, self.last, self.laps = plan, model, {}, {}

        def step(message: dict) -> None:
            self.last = message
            if message.get("phase") == "lapped":
                self.laps[message["test"], message["direction"]] = message["bytes_per_second"]
            self.progressed.emit(message)

        def work() -> None:
            self._done.emit(disktest.run(plan, step, self._stop))

        self._thread = threading.Thread(target=work, daemon=True)
        self._thread.start()
        return True

    def cancel(self) -> None:
        self._stop.set()

    def _on_done(self, result: disktest.Result) -> None:
        self._thread = None
        result = dataclasses.replace(result, model=self.model)
        history = disktest.append_history(result) if result.measured else None
        self.finished.emit(result, history)


class DiskTestTab(ScrollPage):
    # Whether a test is under way: the other tabs wait for it.
    running_changed = Signal(bool)

    def __init__(self, palette: Palette, prefs: Preferences, parent=None,
                 run: Optional[DiskTestRun] = None):
        """`run`: the window's, which outlives this tab; without one, its own."""
        super().__init__(parent)
        self._p = palette
        self._prefs = prefs
        self._run = run if run is not None else DiskTestRun(self)
        self._disks: dict = {}
        self._places: tuple = ()
        self._chosen: Optional[str] = None
        self.result: Optional[disktest.Result] = None
        self._history: list = []

        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        root = ReadableRoot()
        self.setWidget(root)
        layout = root.column
        layout.addWidget(self._build_header())
        # What the folder chosen means for a test, before it starts; and
        # what the last one left to say.
        self._before = QVBoxLayout()
        self._before.setSpacing(6)
        layout.addLayout(self._before)
        self._notices = QVBoxLayout()
        self._notices.setSpacing(6)
        layout.addLayout(self._notices)
        self.result_card = self._build_result()
        layout.addWidget(self.result_card)
        self.history_card = self._build_history()
        layout.addWidget(self.history_card)
        layout.addStretch(1)

        self._run.finished.connect(self._on_finished)
        self._run.progressed.connect(self._on_progress)
        self._history = disktest.load_history()
        self._paint_history()
        if self._history:
            self.show_result(self._history[0])
        self._describe()
        self._shown_for_place = False
        if self._run.running:
            self._show_running()
            if self._run.cancelling:
                self._cancel()

    # -- building ------------------------------------------------------------

    def _build_header(self) -> Card:
        card = Card()
        title = QLabel(_("disktest.title"))
        title.setObjectName("Headline")
        title.setWordWrap(True)
        intro = QLabel(_("disktest.intro"))
        intro.setObjectName("Subhead")
        intro.setWordWrap(True)

        self.place_box = QComboBox()
        self.place_box.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.place_box.setMinimumContentsLength(18)
        self.place_box.activated.connect(self._on_place)
        self.profile_box = QComboBox()
        for profile in disktest.PROFILES:
            self.profile_box.addItem(_(f"disktest.profile.{profile}"), profile)
        self.profile_box.setToolTip(_("disktest.profile.tip"))
        self.profile_box.activated.connect(self._describe)
        self.size_box = QComboBox()
        for size in FILE_SIZES:
            self.size_box.addItem(render.size(size), size)
        self.size_box.setCurrentIndex(FILE_SIZES.index(disktest.FILE_BYTES))
        self.size_box.activated.connect(self._describe)
        self.laps_box = QComboBox()
        for laps in LAPS:
            self.laps_box.addItem(str(laps), laps)
        self.laps_box.setCurrentIndex(LAPS.index(disktest.LAPS))
        self.laps_box.activated.connect(self._describe)
        self.write_box = QCheckBox(_("disktest.option.write"))
        self.write_box.setChecked(True)
        self.write_box.toggled.connect(self._describe)

        where = QHBoxLayout()
        where.setSpacing(8)
        where.addWidget(self._caption("disktest.option.where"))
        where.addWidget(self.place_box, 1)
        options = FoldingRow()
        for caption, box in (("disktest.option.profile", self.profile_box),
                             ("disktest.option.size", self.size_box),
                             ("disktest.option.laps", self.laps_box)):
            pair = QWidget()
            inside = QHBoxLayout(pair)
            inside.setContentsMargins(0, 0, 8, 0)
            inside.setSpacing(6)
            inside.addWidget(self._caption(caption))
            inside.addWidget(box)
            options.add_widget(pair)
        options.add_widget(self.write_box)
        options.add_stretch(1)

        self.about = QLabel("")
        self.about.setWordWrap(True)
        self.run_button = QPushButton(_("memtest.button.run"))
        self.run_button.clicked.connect(self.start)
        self.cancel_button = QPushButton(_("bench.button.cancel"))
        self.cancel_button.setObjectName("Danger")
        self.cancel_button.clicked.connect(self._cancel)
        self.cancel_button.hide()
        self.blocked_note = QLabel("")
        self.blocked_note.setObjectName("Muted")
        self.blocked_note.hide()
        buttons = FoldingRow()
        buttons.add_widget(self.run_button)
        buttons.add_widget(self.cancel_button)
        buttons.add_widget(self.blocked_note)
        buttons.add_stretch(1)
        self.progress = ProgressLine()
        self.progress.hide()
        card.body.addWidget(title)
        card.body.addWidget(intro)
        card.body.addLayout(where)
        for widget in (options, self.about, buttons, self.progress):
            card.body.addWidget(widget)
        return card

    def _caption(self, key: str) -> QLabel:
        label = QLabel(_(key))
        label.setObjectName("Muted")
        return label

    def _build_result(self) -> Card:
        card = Card(_("memtest.card.result"))
        self.conditions = QLabel("")
        self.conditions.setObjectName("Muted")
        self.conditions.setWordWrap(True)
        card.body.addWidget(self.conditions)
        self.table = SpeedTable(self._p)
        card.body.addWidget(self.table)

        self.single_title = QLabel("")
        self.single_title.setObjectName("Muted")
        self.single = QLabel("")
        self.single.setWordWrap(True)
        self.single.setFont(value_font())
        card.body.addWidget(self.single_title)
        card.body.addWidget(self.single)

        self.share_bar = QProgressBar()
        self.share_bar.setRange(0, 100)
        self.share_bar.setTextVisible(False)
        self.share_bar.setFixedHeight(8)
        self.share = QLabel("")
        self.share.setObjectName("Muted")
        self.share.setWordWrap(True)
        card.body.addWidget(self.share_bar)
        card.body.addWidget(self.share)
        self.temperature = QLabel("")
        self.temperature.setWordWrap(True)
        card.body.addWidget(self.temperature)

        self.detail_button = QPushButton(_("disktest.detail.show"))
        self.detail_button.setObjectName("GhostButton")
        self.detail_button.setCheckable(True)
        self.detail_button.toggled.connect(self._toggle_detail)
        fold = QHBoxLayout()
        fold.addWidget(self.detail_button)
        fold.addStretch(1)
        card.body.addLayout(fold)
        self.laps_table = Table(
            [_("disktest.col.test"), "", _("disktest.col.first"), _("disktest.col.laps"),
             _("disktest.col.best"), _("disktest.col.worst"), _("disktest.col.spread")],
            numeric=(False, False, True, True, True, True, True))
        self.laps_note = QLabel(_("disktest.detail.note"))
        self.laps_note.setObjectName("Muted")
        self.laps_note.setWordWrap(True)
        self.detail = QWidget()
        inside = QVBoxLayout(self.detail)
        inside.setContentsMargins(0, 0, 0, 0)
        inside.addWidget(self.laps_table)
        inside.addWidget(self.laps_note)
        self.detail.hide()
        card.body.addWidget(self.detail)

        self.method = QLabel("")
        self.method.setObjectName("Muted")
        self.method.setWordWrap(True)
        card.body.addWidget(self.method)
        card.hide()
        return card

    def _build_history(self) -> Card:
        card = Card(_("memtest.card.history"))
        self.history = Table(
            [_("memtest.col.date"), _("disktest.col.disk"), _("disktest.col.seqread"),
             _("disktest.col.seqwrite"), _("disktest.col.single"), _("disktest.col.hottest")],
            numeric=(False, False, True, True, True, True))
        card.body.addWidget(self.history)
        card.hide()
        return card

    # -- where and what ------------------------------------------------------

    def _folder(self) -> Optional[str]:
        index = self.place_box.currentIndex()
        data = self.place_box.itemData(index) if index >= 0 else None
        return data if data else None

    def _disk_of(self, place: Optional[disktest.Place]):
        """The disk a folder sits on, as this window knows it, when it is
        just one."""
        if place is None or len(place.disks) != 1:
            return None
        return self._disks.get(place.disks[0])

    def plan(self) -> Optional[disktest.Plan]:
        folder = self._folder()
        if folder is None:
            return None
        return disktest.make_plan(
            folder, profile=self.profile_box.currentData(), bytes_=self.size_box.currentData(),
            laps=self.laps_box.currentData(), write=self.write_box.isChecked())

    def _on_place(self, index: int) -> None:
        if self.place_box.itemData(index) == "":
            chosen = QFileDialog.getExistingDirectory(self, _("disktest.option.choose"))
            if chosen:
                self._chosen = chosen
            self._fill_places()
        self._describe()
        self._show_latest_here()

    def _show_latest_here(self) -> None:
        """The last result of the disk the folder chosen is on, if it has
        one: it is the one a new test would be set against."""
        plan = self.plan()
        if plan is None or self.running or not plan.disks:
            return
        latest = next((r for r in self._history if r.disks == plan.disks), None)
        if latest is not None and latest is not self.result:
            self.show_result(latest)

    def _fill_places(self) -> None:
        """Each file system a test can be run on, with its disk and what is
        free, and the folder the user chose, if any."""
        before = self._folder()
        home = disktest.where(pathlib.Path.home())
        rows = []
        for disk in self._disks.values():
            for partition in disk.partitions:
                if not partition.mountpoint:
                    continue
                # In the home's file system, a folder of ours and not its root.
                at_home = home is not None and os.path.basename(home.source) == partition.name
                folder = (str(pathlib.Path.home() / ".cache" / "silux") if at_home
                          else partition.mountpoint)
                check = pathlib.Path.home() if at_home else pathlib.Path(folder)
                if not os.access(check, os.W_OK):
                    continue
                parts = [render.home_path(folder), disk.model or disk.name,
                         partition.filesystem or ""]
                if partition.free_bytes is not None:
                    parts.append(_("disktest.where.free").format(
                        size=render.decimal_size(partition.free_bytes)))
                rows.append((" · ".join(p for p in parts if p), folder))
        if self._chosen and self._chosen not in [folder for _label, folder in rows]:
            rows.insert(0, (render.home_path(self._chosen), self._chosen))
        rows.append((_("disktest.option.choose"), ""))
        if tuple(rows) == self._places:
            return
        self._places = tuple(rows)
        self.place_box.clear()
        for label, folder in rows:
            self.place_box.addItem(label, folder)
        wanted = self._chosen or before
        index = next((i for i, (_l, folder) in enumerate(rows) if folder == wanted), 0)
        self.place_box.setCurrentIndex(index)

    def _describe(self, *_args) -> None:
        """Say what a test would write and how long it would take, and what
        the folder chosen means for it, before it is started."""
        clear_layout(self._before)
        plan = self.plan()
        if plan is None:
            self.about.setText(_("disktest.about.nowhere"))
            self.run_button.setEnabled(False)
            return
        place = disktest.where(plan.folder)
        disk = self._disk_of(place)
        refused = place.refusal if place is not None else None
        if refused:
            self._before.addWidget(self._note(refused, "folder"))
        else:
            for warning in self._warnings(place, disk):
                self._before.addWidget(self._note(warning))
        seconds = disktest.seconds_estimate(plan)
        last = next((r for r in self._history if r.disks == plan.disks and r.bytes_ == plan.bytes_
                     and r.laps == plan.laps and any(m.direction == "write" for m in r.measures)),
                    None)
        key = "disktest.about.write" if plan.write else "disktest.about.read"
        text = _(key).format(
            size=render.size(plan.bytes_), folder=render.home_path(plan.folder),
            writing=render.duration(disktest.writing_seconds(plan)),
            total=render.duration(seconds))
        if plan.write and last is not None:
            text += " " + _("disktest.about.last").format(
                size=render.decimal_size(last.written_bytes))
        self.about.setText(text)
        self.run_button.setEnabled(not refused and not self.running and not self._blocked)

    def _warnings(self, place, disk) -> list[str]:
        found = list(place.warnings) if place is not None else []
        if disk is not None and disk.kind == "HDD":
            found.append("rotational")
        if disk is not None and (disk.kind == "Flash" or disk.transport in ("usb", "mmc")):
            found.append("removable")
        return found

    def _note(self, key: str, action: Optional[str] = None, **values) -> Notice:
        """What a key of the test means: what happened, why, and what can be
        done about it, with its button when there is something to do."""
        tone = "bad" if key in BROKEN else "warn" if key in ERRORS or key in DOUBTFUL else "idle"
        note = Notice(
            _(f"disktest.note.{key}"), _(f"disktest.note.{key}.body").format(**values),
            tone=tone,
            action=_(f"disktest.action.{action}") if action else None)
        if action == "folder":
            note.action_clicked.connect(
                lambda: self._on_place(self.place_box.count() - 1))
        elif action == "smaller":
            note.action_clicked.connect(self._smaller_file)
        return note

    def _smaller_file(self) -> None:
        if self.size_box.currentIndex() > 0:
            self.size_box.setCurrentIndex(self.size_box.currentIndex() - 1)
            self._describe()

    # -- running -------------------------------------------------------------

    _blocked = False

    @property
    def running(self) -> bool:
        return self._run.running

    def set_blocked(self, by: Optional[str]) -> None:
        """Another test is under way, called `by`, or none is."""
        self._blocked = by is not None
        self.blocked_note.setText("" if by is None else _("bench.tabs.busy").format(test=by))
        self.blocked_note.setVisible(by is not None)
        self._describe()

    def start(self) -> None:
        plan = self.plan()
        if plan is None or self.running or not self.run_button.isEnabled():
            return
        os.makedirs(plan.folder, exist_ok=True)
        disk = self._disk_of(disktest.where(plan.folder))
        if not self._run.start(plan, disk.model if disk is not None else None):
            return
        self._show_running()
        self.running_changed.emit(True)

    def _show_running(self) -> None:
        self.run_button.setEnabled(False)
        self.cancel_button.setEnabled(True)
        self.cancel_button.show()
        self.progress.begin(_("bench.state.preparing"))
        self.progress.show()
        clear_layout(self._notices)
        plan = self._run.plan
        if plan is not None:
            # The table of the run under way, filling in as it goes.
            self.conditions.setText(_("disktest.conditions.running"))
            self.table.set_rows(tuple(test.name for test in plan.tests), plan.write)
            for widget in (self.single_title, self.single, self.share_bar, self.share,
                           self.temperature, self.detail_button, self.detail, self.method):
                widget.hide()
            self.result_card.show()
            for (name, direction), rate in self._run.laps.items():
                self.table.set_cell(name, direction, rate, live=True)
        if self._run.last:
            self._on_progress(self._run.last)

    def _cancel(self) -> None:
        self._run.cancel()
        self.cancel_button.setEnabled(False)
        self.progress.set_state(_("bench.state.cancelling"))

    def _on_progress(self, message: dict) -> None:
        if self._run.cancelling:
            return
        phase = message.get("phase")
        if phase == "fill":
            self.progress.set_state(_("disktest.phase.fill"), 0.0)
            return
        what = _("disktest.phase.lap").format(
            test=message.get("test", ""), direction=_(f"disktest.dir.{message['direction']}"),
            lap=message.get("lap", 0), laps=message.get("laps", 0))
        if phase == "pause":
            what = _("disktest.phase.pause").format(
                test=message.get("test", ""), direction=_(f"disktest.dir.{message['direction']}"))
        elif message.get("lap") == 0:
            what = _("disktest.phase.first").format(
                test=message.get("test", ""), direction=_(f"disktest.dir.{message['direction']}"))
        self.progress.set_state(what, message.get("done"))
        if phase == "lapped":
            self.table.set_cell(message["test"], message["direction"],
                                message["bytes_per_second"], live=True)

    def _on_finished(self, result: disktest.Result, history) -> None:
        self.cancel_button.hide()
        self.progress.hide()
        self.running_changed.emit(False)
        if history is not None:
            self._history = history
        self._paint_history()
        self._describe()
        if result.measured:
            self.show_result(result)
        elif self._history:
            self.show_result(self._history[0])
        else:
            self.result_card.hide()
        if result.reason and result.reason != "cancelled":
            self._notices.insertWidget(0, self._failure(result))

    def _failure(self, result: disktest.Result) -> Notice:
        key = result.reason if result.reason in ERRORS else "failed"
        figures = dict(result.figures)
        values = {"needed": render.decimal_size(figures.get("needed")),
                  "free": render.decimal_size(figures.get("free"))}
        return self._note(key, ERRORS[key], **values)

    # -- painting ------------------------------------------------------------

    def show_result(self, result: disktest.Result) -> None:
        self.result = result
        clear_layout(self._notices)
        disk = self._disks.get(result.disks[0]) if len(result.disks) == 1 else None
        same_disk = disk is not None and (result.model is None or disk.model == result.model)
        link = disk.link if same_disk else None
        engine = _(f"disktest.engine.{result.engine}") if result.engine else ""
        parts = [when(result.timestamp), result.label, result.model or " + ".join(result.disks),
                 render.pcie_link(link) if link else "", result.filesystem or "", engine]
        self.conditions.setText(" · ".join(part for part in parts if part))

        names = tuple(dict.fromkeys(m.name for m in result.measures))
        writes = any(m.direction == "write" for m in result.measures)
        self.table.set_rows(names, writes)
        for measure in result.measures:
            middle = measure.median
            note = _("disktest.noisy.tip").format(
                worst=megabytes(measure.worst.bytes_per_second),
                best=megabytes(measure.best.bytes_per_second)) if measure.noisy else ""
            self.table.set_cell(measure.name, measure.direction,
                                middle.bytes_per_second if middle else None, note=note)

        lines = []
        for direction in ("read", "write"):
            measure = result.measure(SINGLE, direction)
            if measure is not None and measure.median is not None:
                lap = measure.median
                lines.append(_("disktest.single.line").format(
                    direction=_(f"disktest.dir.{direction}").capitalize(),
                    iops=render.thousands(round(lap.requests_per_second)),
                    mean=microseconds(lap.latency_mean_ns),
                    p99=microseconds(lap.latency_p99_ns)))
        self.single_title.setText(_("disktest.single.title").format(test=SINGLE))
        self.single.setText("\n".join(lines))
        for widget in (self.single_title, self.single):
            widget.setVisible(bool(lines))

        fastest = max((m.median.bytes_per_second for m in result.measures
                       if m.pattern == "sequential" and m.median is not None), default=None)
        most = link_bytes_per_second(link)
        shown = bool(fastest and most)
        if shown:
            percent = fastest / most * 100
            self.share_bar.setValue(round(min(percent, 100)))
            self.share.setText(_("disktest.share").format(
                percent=f"{percent:.0f}", link=render.pcie_link(link), most=megabytes(most)))
        for widget in (self.share_bar, self.share):
            widget.setVisible(shown)

        fahrenheit = self._prefs.fahrenheit
        temperatures = (result.temperature_start_c, result.temperature_peak_c,
                        result.temperature_end_c)
        if all(t is not None for t in temperatures):
            self.temperature.setText(_("disktest.temperature").format(
                start=render.temperature(temperatures[0], fahrenheit),
                peak=render.temperature(temperatures[1], fahrenheit),
                end=render.temperature(temperatures[2], fahrenheit)))
        self.temperature.setVisible(all(t is not None for t in temperatures))

        rows = []
        for measure in result.measures:
            first = next((lap for lap in measure.laps if lap.number == 0), None)
            rows.append([
                measure.name, _(f"disktest.dir.{measure.direction}"),
                megabytes(first.bytes_per_second) if first else render.DASH,
                "  ".join(megabytes(lap.bytes_per_second) for lap in measure.counted),
                megabytes(measure.best.bytes_per_second) if measure.best else render.DASH,
                megabytes(measure.worst.bytes_per_second) if measure.worst else render.DASH,
                render.DASH if measure.spread is None else f"{measure.spread * 100:.1f} %"])
        self.laps_table.set_rows(rows)
        self.detail_button.show()
        self.detail.setVisible(self.detail_button.isChecked())
        self.method.setText(self._method(result))
        self.method.show()
        self.result_card.show()

        for warning in result.warnings:
            if warning in WARNINGS:
                self._notices.addWidget(self._note(warning))
        noisy = [m for m in result.measures if m.noisy]
        if noisy:
            self._notices.addWidget(self._note("noisy", tests=", ".join(
                f"{m.name} ({_(f'disktest.dir.{m.direction}')})" for m in noisy)))

    def _method(self, result: disktest.Result) -> str:
        cached = [m.cached_bytes for m in result.measures]
        checked = ("disktest.method.direct" if cached and all(c == 0 for c in cached)
                   else "disktest.method.unchecked")
        parts = [
            _("disktest.method.file").format(size=render.size(result.bytes_)),
            _(checked),
            render.counted("disktest.method.laps", result.laps, seconds=f"{result.lap_seconds:g}",
                           pause=f"{result.pause_seconds:g}"),
            _("disktest.method.written").format(size=render.decimal_size(result.written_bytes)),
        ]
        return _("disktest.method") + " " + "; ".join(parts) + "."

    def _toggle_detail(self, shown: bool) -> None:
        self.detail.setVisible(shown)
        self.detail_button.setText(_("disktest.detail.hide" if shown else "disktest.detail.show"))

    def _paint_history(self) -> None:
        fahrenheit = self._prefs.fahrenheit

        def figure(result, name, direction) -> str:
            measure = result.measure(name, direction)
            middle = measure.median if measure is not None else None
            return megabytes(middle.bytes_per_second) if middle else render.DASH

        self.history.set_rows([
            [r.label or when(r.timestamp), r.model or " + ".join(r.disks),
             figure(r, SEQUENTIAL, "read"), figure(r, SEQUENTIAL, "write"),
             figure(r, SINGLE, "read"), render.temperature(r.temperature_peak_c, fahrenheit)]
            for r in self._history])
        self.history_card.setVisible(bool(self._history))

    # -- the window's protocol -----------------------------------------------

    def apply(self, snapshot) -> None:
        """Nothing here follows the sampling but which disks there are and
        what is mounted where."""
        disks = {disk.name: disk for disk in snapshot.disks}
        changed = ([(d.name, d.model, d.link, tuple(d.partitions)) for d in disks.values()]
                   != [(d.name, d.model, d.link, tuple(d.partitions))
                       for d in self._disks.values()])
        self._disks = disks
        self._fill_places()
        if not self._shown_for_place and disks:
            # The first time the disks are known: the folder offered first.
            self._shown_for_place = True
            self._show_latest_here()
        if changed:
            self._describe()
            if not self.running and self.result is not None:
                self.show_result(self.result)

    def stop(self) -> None:
        self._run.cancel()
