"""The Disk tab of Performance: how fast a folder's disk reads and writes.

A figure here comes with what makes it believable: the disk and the file
system it was measured on, the engine, whether anything went through the
page cache, the best and the worst lap next to the one in the middle, the
temperature, and the method in a line. What can't be measured, or has to be
read with care, is said as a note: what happened, why, and what to do.
"""

from __future__ import annotations

import dataclasses
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
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ... import disktest, render, thermal
from ...disktest import GIB, MIB
from ...i18n import _
from ...settings import Preferences
from .. import theme
from ..theme import Palette, ui_font
from ..widgets import (
    Card,
    Fact,
    FoldingRow,
    Notice,
    ProgressLine,
    RateBar,
    ReadableRoot,
    ResponsiveRow,
    ScrollPage,
    Table,
    clear_layout,
    paint_level,
    unbroken,
    value_font,
)

# The bars share one scale, logarithmic and fixed, as CrystalDiskMark's and
# KDiskMark's do: from 0.1 MB/s to 100 000. Fixed, so that two screenshots
# of two machines compare by eye; and with its axis drawn, which theirs
# lack, so that a bar's length can be read.
SCALE_FROM = -1
SCALE_DECADES = 6
SCALE = (10 ** SCALE_FROM * 1e6, SCALE_DECADES)
# Each column in its own tone of the accent.
TONES = {"read": 1.0, "write": 0.6}
MB = 1e6
FILE_SIZES = (64 * MIB, 256 * MIB, GIB, 4 * GIB, 8 * GIB, 16 * GIB, 32 * GIB)
LAPS = tuple(range(1, 10))
# What a result that didn't measure is said with, and whether its note
# offers another folder or a smaller file.
ERRORS = {
    "in_memory": "folder", "network": "folder", "not_a_disk": "folder",
    "read_only": "folder", "no_write": "folder", "no_folder": "folder",
    "no_direct": "folder", "no_space": "smaller", "io": None, "no_module": None,
    "internal": None, "failed": None, "not_started": None,
    "too_big_for_fat": "fits", "too_big": "smaller", "cache_fallback": "folder",
    "disconnected": None, "no_room": "folder",
}
ACTIONS = {"folder": "disktest.action.folder", "smaller": "disktest.action.smaller",
           "fits": "disktest.action.fits"}
# From how long writing the file is said before starting, with the way to a
# smaller one.
SLOW_FILL_SECONDS = 30
# The notes that put a figure in doubt; the rest of those that aren't
# errors are facts to read the figures with.
DOUBTFUL = frozenset({"copy_on_write", "through_the_cache", "disk_moved_less", "disk_was_busy",
                      "varied"})
# What a result is read with, shown in its own card. What comes from the
# folder is said above, before a test starts.
RESULT_NOTES = frozenset({"copy_on_write", "through_the_cache", "disk_moved_less",
                          "disk_was_busy", "queue_of_threads"})
# Each note's title and body.
NOTES = {
    "in_memory": ("disktest.note.in_memory", "disktest.note.in_memory.body"),
    "network": ("disktest.note.network", "disktest.note.network.body"),
    "not_a_disk": ("disktest.note.not_a_disk", "disktest.note.not_a_disk.body"),
    "read_only": ("disktest.note.read_only", "disktest.note.read_only.body"),
    "no_write": ("disktest.note.no_write", "disktest.note.no_write.body"),
    "no_folder": ("disktest.note.no_folder", "disktest.note.no_folder.body"),
    "no_direct": ("disktest.note.no_direct", "disktest.note.no_direct.body"),
    "no_space": ("disktest.note.no_space", "disktest.note.no_space.body"),
    "no_room": ("disktest.note.no_room", "disktest.note.no_room.body"),
    "too_big": ("disktest.note.too_big", "disktest.note.too_big.body"),
    "too_big_for_fat": ("disktest.note.too_big_for_fat", "disktest.note.too_big_for_fat.body"),
    "cache_fallback": ("disktest.note.cache_fallback", "disktest.note.cache_fallback.body"),
    "slow_fill": ("disktest.note.slow_fill", "disktest.note.slow_fill.body"),
    "slow_fill_link": ("disktest.note.slow_fill_link", "disktest.note.slow_fill_link.body"),
    "io": ("disktest.note.io", "disktest.note.io.body"),
    "no_module": ("disktest.note.no_module", "disktest.note.no_module.body"),
    "internal": ("disktest.note.internal", "disktest.note.internal.body"),
    "failed": ("disktest.note.failed", "disktest.note.failed.body"),
    "not_started": ("disktest.note.not_started", "disktest.note.not_started.body"),
    "disconnected": ("disktest.note.disconnected", "disktest.note.disconnected.body"),
    "gone_disk": ("disktest.note.gone_disk", "disktest.note.gone_disk.body"),
    "gone_mount": ("disktest.note.gone_mount", "disktest.note.gone_mount.body"),
    "rotational": ("disktest.note.rotational", "disktest.note.rotational.body"),
    "placement": ("disktest.note.placement", "disktest.note.placement.body"),
    "placement_unknown.filesystem": ("disktest.note.placement_unknown",
                                     "disktest.unplaced.filesystem"),
    "placement_unknown.crypt": ("disktest.note.placement_unknown",
                                "disktest.unplaced.crypt"),
    "placement_unknown.lvm": ("disktest.note.placement_unknown",
                              "disktest.unplaced.lvm"),
    "placement_unknown.raid": ("disktest.note.placement_unknown",
                               "disktest.unplaced.raid"),
    "placement_unknown.mapped": ("disktest.note.placement_unknown",
                                 "disktest.unplaced.mapped"),
    "placement_unknown.loop": ("disktest.note.placement_unknown",
                               "disktest.unplaced.loop"),
    "placement_unknown.several_disks": ("disktest.note.placement_unknown",
                                        "disktest.unplaced.several_disks"),
    "placement_unknown.unsaid": ("disktest.note.placement_unknown",
                                 "disktest.unplaced.unsaid"),
    "removable": ("disktest.note.removable", "disktest.note.removable.body"),
    "encrypted": ("disktest.note.encrypted", "disktest.note.encrypted.body"),
    "several_disks": ("disktest.note.several_disks", "disktest.note.several_disks.body"),
    "fuse_driver": ("disktest.note.fuse_driver", "disktest.note.fuse_driver.body"),
    "fuse": ("disktest.note.fuse", "disktest.note.fuse.body"),
    "zfs": ("disktest.note.zfs", "disktest.note.zfs.body"),
    "overlay": ("disktest.note.overlay", "disktest.note.overlay.body"),
    "loop": ("disktest.note.loop", "disktest.note.loop.body"),
    "copy_on_write": ("disktest.note.copy_on_write", "disktest.note.copy_on_write.body"),
    "through_the_cache": ("disktest.note.through_the_cache",
                          "disktest.note.through_the_cache.body"),
    "disk_moved_less": ("disktest.note.disk_moved_less", "disktest.note.disk_moved_less.body"),
    "disk_was_busy": ("disktest.note.disk_was_busy", "disktest.note.disk_was_busy.body"),
    "queue_of_threads": ("disktest.note.queue_of_threads",
                         "disktest.note.queue_of_threads.body"),
    "varied": ("disktest.note.varied", "disktest.note.varied.body"),
}
DIRECTIONS = {"read": "disktest.dir.read", "write": "disktest.dir.write"}
COLUMNS = {"read": "disktest.col.read", "write": "disktest.col.write"}
ENGINES = {"uring": "disktest.engine.uring", "threads": "disktest.engine.threads"}
PROFILE_NAMES = {"standard": "disktest.profile.standard", "real": "disktest.profile.real"}
PROFILE_TIPS = {"standard": "disktest.profile.standard.tip", "real": "disktest.profile.real.tip"}
FACT_NAMES = {"single": "disktest.fact.single", "link": "disktest.fact.link",
              "heat": "disktest.fact.heat"}
SEQUENTIAL, SINGLE = "SEQ1M Q8T1", "RND4K Q1T1"


def when(timestamp: float) -> str:
    return time.strftime("%d/%m/%Y %H:%M", time.localtime(timestamp))


def megabytes(bytes_per_second: Optional[float]) -> str:
    """A rate as the table writes it, in MB/s without the unit: «6 592»,
    «63.3»."""
    return render.rate_figure(bytes_per_second, MB)


def microseconds(nanoseconds: Optional[float]) -> str:
    """«64.5 µs», whole on its line."""
    return unbroken(render.microseconds(nanoseconds))


def test_words(test: disktest.Test) -> str:
    """What a test is, in words: «Sequential», «Random 4K, one at a time»."""
    if test.pattern == "sequential":
        kind = _("disktest.kind.sequential")
        if test.block != MIB:
            kind = f"{kind} {block_name(test.block)}"
    else:
        kind = _("disktest.kind.random").format(block=block_name(test.block))
    if test.threads > 1:
        return _("disktest.kind.threads").format(kind=kind, n=test.threads)
    if test.depth == 1:
        return _("disktest.kind.single").format(kind=kind)
    return kind


def block_name(block: int) -> str:
    return next((f"{block // unit}{letter}" for unit, letter in ((MIB, "M"), (1024, "K"))
                 if block % unit == 0), f"{block} B")


def test_tip(test: disktest.Test) -> str:
    """What the letters of a test's code stand for."""
    return _("disktest.tip.test").format(
        code=test.name, block=render.size(test.block), depth=test.depth, threads=test.threads)


class Axis(QWidget):
    """What the bars above it are measured against: a mark at each power of
    ten, with its figure where there is room."""

    # Between two figures, at least this much.
    GAP = 8

    def __init__(self, palette: Palette, parent=None, first: float = 10 ** SCALE_FROM,
                 decades: int = SCALE_DECADES):
        """`first`: the figure at the left end, in the unit the bars are
        read in; a mark every power of ten from there."""
        super().__init__(parent)
        self._p = palette
        self._first, self._decades = first, decades
        self.setFont(ui_font(theme.METRICS.small_pt - 1))
        self.setFixedHeight(self.fontMetrics().height() + 6)
        self.setMinimumWidth(0)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)

    def labels(self, width: float) -> list[tuple[QRectF, str]]:
        """Where each figure goes at `width`: always the same ones (1, 100,
        10 000: one power of ten in two), or none if they don't all fit.
        Fitting as many as there was room for gave each screenshot its own."""
        metrics = self.fontMetrics()
        first = next(decade for decade in range(self._decades + 1)
                     if self._first * 10 ** decade >= 1)
        placed: list[tuple[QRectF, str]] = []
        for decade in range(first, self._decades + 1, 2):
            text = render.thousands(round(self._first * 10 ** decade))
            text_width = metrics.horizontalAdvance(text)
            x = width * decade / self._decades
            box = QRectF(x - text_width / 2, 4, text_width, metrics.height())
            if box.left() < 0 or box.right() > width or (
                    placed and box.left() < placed[-1][0].right() + self.GAP):
                return []
            placed.append((box, text))
        return placed

    def paintEvent(self, _event) -> None:  # noqa: N802
        if self.width() < RateBar.NARROWEST:
            return
        painter = QPainter(self)
        painter.setPen(self._p.q("muted"))
        for decade in range(self._decades + 1):
            x = min(self.width() * decade / self._decades, self.width() - 1)
            painter.drawLine(int(x), 0, int(x), 3)
        for box, text in self.labels(self.width()):
            painter.drawText(box, Qt.AlignmentFlag.AlignCenter, text)
        painter.end()


class TestRows(QWidget):
    """The tests of a result, a row each: what it is in words, with its code
    small under them, and what it reads and writes, each as a bar on the
    scale they all share and a figure."""

    BAR = 20

    def __init__(self, palette: Palette, parent=None):
        super().__init__(parent)
        self._p = palette
        self._tests: tuple = ()
        self._writes: Optional[bool] = None
        self._cells: dict[tuple[str, str], tuple[RateBar, QLabel]] = {}
        self.names: list[QWidget] = []
        self._grid = QGridLayout(self)
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid.setHorizontalSpacing(14)
        self._grid.setVerticalSpacing(10)
        self._grid.setColumnStretch(1, 1)
        self._grid.setColumnStretch(3, 1)

    def _name(self, test: disktest.Test) -> QWidget:
        """A test in words on one line, with its code small under them and
        what the code's letters mean on hovering."""
        block = QWidget()
        inside = QVBoxLayout(block)
        inside.setContentsMargins(0, 0, 0, 0)
        inside.setSpacing(0)
        words = QLabel(test_words(test))
        words.setFont(ui_font(theme.METRICS.base_pt + 1))
        code = QLabel(test.name)
        code.setObjectName("Muted")
        code.setFont(ui_font(theme.METRICS.small_pt - 1))
        inside.addWidget(words)
        inside.addWidget(code)
        block.setToolTip(test_tip(test))
        return block

    @staticmethod
    def _figure() -> QLabel:
        figure = QLabel(render.DASH)
        font = value_font()
        font.setPointSizeF(font.pointSizeF() + 3)
        font.setWeight(font.Weight.DemiBold)
        figure.setFont(font)
        figure.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        figure.setMinimumWidth(figure.fontMetrics().horizontalAdvance("00 000*"))
        return figure

    @staticmethod
    def _head(direction: str) -> QLabel:
        head = QLabel(_(COLUMNS[direction]))
        head.setObjectName("ColumnTitle")
        return head

    def _build(self, tests: tuple, writes: bool) -> None:
        directions = ("read", "write") if writes else ("read",)
        for index, direction in enumerate(directions):
            self._grid.addWidget(self._head(direction), 0, 1 + 2 * index, 1, 2)
        self.names = []
        for row, test in enumerate(tests, start=1):
            name = self._name(test)
            self.names.append(name)
            self._grid.addWidget(name, row, 0)
            for index, direction in enumerate(directions):
                bar = RateBar(self._p, SCALE, tone=TONES[direction], height=self.BAR)
                figure = self._figure()
                self._grid.addWidget(bar, row, 1 + 2 * index)
                self._grid.addWidget(figure, row, 2 + 2 * index)
                self._cells[test.name, direction] = (bar, figure)
        # Every row as tall as the tallest: a name never takes two lines,
        # and the figures line up whatever the test.
        tallest = max((name.sizeHint().height() for name in self.names), default=0)
        for row in range(1, len(tests) + 1):
            self._grid.setRowMinimumHeight(row, tallest)
        for index, _direction in enumerate(directions):
            self._grid.addWidget(Axis(self._p), len(tests) + 1, 1 + 2 * index)
        unit = QLabel(_("disktest.unit"))
        unit.setObjectName("Muted")
        unit.setFont(ui_font(theme.METRICS.small_pt))
        self._grid.addWidget(unit, len(tests) + 1, 0)

    def set_rows(self, tests: tuple, writes: bool) -> None:
        """The tests to show, each with nothing measured yet."""
        if (tests, writes) != (self._tests, self._writes):
            clear_layout(self._grid)
            self._cells = {}
            self._build(tests, writes)
            self._tests, self._writes = tests, writes
        for bar, figure in self._cells.values():
            bar.set_rate(None)
            figure.setText(render.DASH)
            figure.setToolTip("")
            self._tint(figure, False)

    @staticmethod
    def _tint(figure: QLabel, live: bool) -> None:
        if figure.objectName() != ("Muted" if live else ""):
            figure.setObjectName("Muted" if live else "")
            figure.style().unpolish(figure)
            figure.style().polish(figure)

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
        self._tint(figure, live)


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
        # What is mounted where, as last seen, and the places it gave: they
        # are looked for again only when it changes.
        self._mounts: tuple = ()
        self._offered: list[tuple[str, str, str]] = []
        # The disk under each folder offered, as it was: to say which went.
        self._owners: dict[str, tuple[str, Optional[str]]] = {}
        # A folder that was chosen and went away, while its note is shown.
        self._gone: Optional[str] = None
        self._chosen: Optional[str] = None
        self._chosen_place: Optional[disktest.Place] = None
        self._blocked = False
        self._placed = False
        # The size the note of a file that doesn't fit offers instead.
        self._offer: Optional[int] = None
        self.result: Optional[disktest.Result] = None
        self._history: list = []

        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        root = ReadableRoot()
        self.setWidget(root)
        layout = root.column
        layout.addWidget(self._build_header())
        # What the folder chosen means for a test, before it starts, and
        # what went wrong with the last one. What a result has to be read
        # with goes inside its own card.
        self._notices = QVBoxLayout()
        self._notices.setSpacing(6)
        layout.addLayout(self._notices)
        self._failure: Optional[Notice] = None
        self.result_card = self._build_result()
        layout.addWidget(self.result_card)
        self.history_card = self._build_history()
        layout.addWidget(self.history_card)
        layout.addStretch(1)

        self._run.finished.connect(self._on_finished)
        self._run.progressed.connect(self._on_progress)
        self._history = disktest.load_history()
        self._paint_history()
        self._describe()
        self._show_for_place()
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
            self.profile_box.addItem(_(PROFILE_NAMES[profile]), profile)
            self.profile_box.setItemData(self.profile_box.count() - 1,
                                         _(PROFILE_TIPS[profile]), Qt.ItemDataRole.ToolTipRole)
        self.profile_box.activated.connect(self._describe)
        self.size_box = QComboBox()
        for size in FILE_SIZES:
            self.size_box.addItem(render.file_size(size), size)
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
        self.about.setObjectName("Muted")
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
        # A disk with nothing measured says so, instead of showing another's.
        self.empty = QLabel(_("disktest.empty"))
        self.empty.setObjectName("Muted")
        self.empty.setWordWrap(True)
        card.body.addWidget(self.empty)

        self.disk_name = QLabel("")
        self.disk_name.setFont(ui_font(theme.METRICS.base_pt + 3))
        self.disk_name.setWordWrap(True)
        self.conditions = QLabel("")
        self.conditions.setObjectName("Muted")
        self.conditions.setWordWrap(True)
        card.body.addWidget(self.disk_name)
        card.body.addWidget(self.conditions)

        self.rows = TestRows(self._p)
        card.body.addWidget(self.rows)

        self.facts = {name: Fact(_(FACT_NAMES[name])) for name in ("single", "link", "heat")}
        # The single request on a row of its own: its reading and its
        # writing each want a whole line.
        card.body.addWidget(self.facts["single"])
        self.fact_row = ResponsiveRow(min_item_width=170)
        for name in ("link", "heat"):
            self.fact_row.add(self.facts[name])
        card.body.addWidget(self.fact_row)

        self._result_notes = QVBoxLayout()
        self._result_notes.setSpacing(6)
        card.body.addLayout(self._result_notes)

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
        self.method = QLabel("")
        self.method.setObjectName("Muted")
        self.method.setWordWrap(True)
        self.detail = QWidget()
        inside = QVBoxLayout(self.detail)
        inside.setContentsMargins(0, 0, 0, 0)
        inside.addWidget(self.laps_table)
        inside.addWidget(self.laps_note)
        inside.addWidget(self.method)
        self.detail.hide()
        card.body.addWidget(self.detail)
        return card

    def _build_history(self) -> Card:
        card = Card(_("memtest.card.history"))
        # A table per disk, engine and profile: a test made of threads, or
        # another profile's, isn't the same test, and sat in the same column.
        self._history_groups = QVBoxLayout()
        self._history_groups.setSpacing(14)
        card.body.addLayout(self._history_groups)
        self.history_tables: list[tuple[QLabel, Table]] = []
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

    def _model_of(self, disks) -> Optional[str]:
        """The model of the one disk a plan is on, as this window knows it."""
        return getattr(self._disks.get(disks[0]), "model", None) if len(disks) == 1 else None

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
                self._choose_folder(chosen)
            self._fill_places()
        if self._gone is not None:
            self._drop_failure()
        self._describe()
        self._show_for_place()

    @property
    def history(self) -> tuple:
        return tuple(self._history)

    def choose_disk(self, disk: str) -> None:
        """The first place offered on that disk, if any."""
        for index in range(self.place_box.count()):
            folder = self.place_box.itemData(index)
            place = disktest.where(folder) if folder else None
            if place is not None and disk in place.disks:
                self.place_box.setCurrentIndex(index)
                self._describe()
                self._show_for_place()
                return

    def choose(self, folder: str) -> None:
        """Measure in `folder`, as if it had been picked in the dialog."""
        self._choose_folder(folder)
        self._fill_places()
        self._describe()
        self._show_for_place()

    def _show_for_place(self) -> None:
        """The last result of the disks the folder chosen is on, or that
        they have none yet: never another disk's."""
        if self.running:
            return
        plan = self.plan()
        disks = plan.disks if plan is not None else ()
        model = self._model_of(disks)
        latest = next((r for r in self._history if r.is_of(disks, model)), None)
        if latest is not None:
            self.show_result(latest)
        else:
            self._show_empty(bool(disks))

    def _choose_folder(self, folder: str) -> None:
        self._chosen = folder
        self._chosen_place = disktest.where(folder)

    def _offered_places(self) -> list[tuple[str, str, str]]:
        """(folder, disk, partition) for each file system a test can be run
        on that can be written to. In the home's, a folder of ours and not
        its root, and first: it is the disk most people mean."""
        home = disktest.where(pathlib.Path.home())
        found: list[tuple[str, str, str]] = []
        for disk in self._disks.values():
            for partition in disk.partitions:
                if not partition.mountpoint:
                    continue
                at_home = home is not None and os.path.basename(home.source) == partition.name
                folder = (str(pathlib.Path.home() / ".cache" / "silux") if at_home
                          else partition.mountpoint)
                check = pathlib.Path.home() if at_home else pathlib.Path(folder)
                if os.access(check, os.W_OK):
                    found.insert(0 if at_home else len(found), (folder, disk.name, partition.name))
        return found

    def _place_label(self, folder: str, disk_name: str, partition_name: str) -> str:
        disk = self._disks[disk_name]
        partition = next(p for p in disk.partitions if p.name == partition_name)
        parts = [render.home_path(folder), disk.model or disk.name, partition.filesystem or ""]
        if partition.free_bytes is not None:
            parts.append(_("disktest.where.free").format(
                size=render.decimal_size(partition.free_bytes)))
        return " · ".join(part for part in parts if part)

    def _chosen_still_there(self) -> bool:
        """Whether the folder chosen in the dialog is still on what it was."""
        place = self._chosen_place
        if self._chosen is None or place is None:
            return True
        now = disktest.where(self._chosen)
        return (now is not None and now.mountpoint == place.mountpoint
                and all(disk in self._disks for disk in place.disks))

    def _fill_places(self) -> None:
        """Each file system a test can be run on, with its disk and what is
        free, and the folder the user chose, if any. Where they are is asked
        again only when what is mounted changes; what is free is rewritten
        in the rows there are."""
        mounts = tuple((disk.name, disk.model,
                        tuple((p.name, p.mountpoint, p.filesystem) for p in disk.partitions))
                       for disk in self._disks.values())
        if mounts != self._mounts:
            self._mounts = mounts
            self._offered = self._offered_places()
            if not self._chosen_still_there():
                self._chosen = self._chosen_place = None
        rows = [(self._place_label(*place), place[0]) for place in self._offered]
        if self._chosen and self._chosen not in [folder for _label, folder in rows]:
            rows.insert(0, (render.home_path(self._chosen), self._chosen))
        rows.append((_("disktest.option.choose"), ""))
        if tuple(rows) == self._places:
            return
        folders = [folder for _label, folder in rows]
        if folders == [folder for _label, folder in self._places]:
            for index, (label, _folder) in enumerate(rows):
                if self.place_box.itemText(index) != label:
                    self.place_box.setItemText(index, label)
            self._places = tuple(rows)
            return
        before = self._folder()
        if before and before not in folders and not self.running:
            self._say_gone(before)
        elif self._gone is not None and self._gone in folders:
            self._drop_failure()
        owners = {folder: (disk, self._disks[disk].model) for folder, disk, _p in self._offered}
        if self._chosen and self._chosen_place is not None and len(self._chosen_place.disks) == 1:
            disk = self._chosen_place.disks[0]
            owners[self._chosen] = (disk, getattr(self._disks.get(disk), "model", None))
        self._owners = owners
        self._places = tuple(rows)
        self.place_box.clear()
        for label, folder in rows:
            self.place_box.addItem(label, folder)
        wanted = self._chosen or before
        index = next((i for i, folder in enumerate(folders) if folder == wanted), 0)
        self.place_box.setCurrentIndex(index)

    def _say_gone(self, folder: str) -> None:
        """The folder chosen isn't offered any more: its disk went, or its
        file system was unmounted. A run under way says it itself."""
        owner = self._owners.get(folder)
        if owner is None:
            return
        disk, model = owner
        self._drop_failure()
        self._failure = self._note("gone_mount" if disk in self._disks else "gone_disk",
                                   disk=model or disk)
        self._notices.insertWidget(0, self._failure)
        self._gone = folder

    def _describe(self, *_args) -> None:
        """Say what a test would write and how long it would take, and what
        the folder chosen means for it, before it is started."""
        # The last run's failure stays until another run or another choice.
        for index in reversed(range(self._notices.count())):
            widget = self._notices.itemAt(index).widget()
            if widget is not None and widget is not self._failure:
                self._notices.takeAt(index)
                widget.setParent(None)
                widget.deleteLater()
        plan = self.plan()
        if plan is None:
            self.about.setText(_("disktest.about.nowhere"))
            self.run_button.setEnabled(False)
            return
        place = disktest.where(plan.folder)
        disk = self._disk_of(place)
        refused = place.refusal if place is not None else None
        self.about.setVisible(not refused)
        free = self._free_of(plan)
        limit = None if refused else disktest.largest_that_fits(plan, free)
        too_big = limit is not None and plan.bytes_ > limit
        if refused:
            self._notices.addWidget(self._note(refused, "folder"))
        else:
            if too_big:
                self._notices.addWidget(self._too_big(plan, limit, free))
            for warning in self._warnings(place, disk):
                self._notices.addWidget(self._note(warning))
            slow = self._slow_fill(plan, disk)
            if slow is not None:
                self._notices.addWidget(slow)
        model = self._model_of(plan.disks)
        last = next((r for r in self._history if r.is_of(plan.disks, model)
                     and r.bytes_ == plan.bytes_ and r.laps == plan.laps
                     and r.profile == plan.profile
                     and any(m.direction == "write" for m in r.measures)), None)
        values = dict(size=render.file_size(plan.bytes_), folder=render.home_path(plan.folder),
                      writing=render.duration(disktest.writing_seconds(plan)),
                      total=render.duration(disktest.seconds_estimate(plan)))
        if not plan.write:
            text = _("disktest.about.read").format(**values)
        elif last is not None:
            text = _("disktest.about.last").format(
                written=render.decimal_size(last.written_bytes), **values)
        else:
            text = _("disktest.about.write").format(**values)
        self.about.setText(text)
        self.run_button.setEnabled(not refused and not too_big and not self.running
                                   and not self._blocked)

    def _free_of(self, plan: disktest.Plan) -> Optional[int]:
        """What is free where the folder is mounted, as the last sample read it."""
        return next((partition.free_bytes for disk in self._disks.values()
                     for partition in disk.partitions
                     if plan.mountpoint and partition.mountpoint == plan.mountpoint), None)

    def _too_big(self, plan: disktest.Plan, limit: int, free: Optional[int]) -> Notice:
        """Why the file chosen doesn't fit in the folder, with the largest
        size offered that does, or that none does."""
        largest = disktest.largest_file(plan.filesystem)
        sizes = [self.size_box.itemData(i) for i in range(self.size_box.count())]
        self._offer = max((size for size in sizes + [largest] if size and size <= limit),
                          default=None)
        if self._offer is None:
            smallest = min(sizes)
            return self._note("no_room", "folder", free=render.decimal_size(free),
                              size=render.file_size(smallest),
                              needed=render.decimal_size(smallest + disktest.FREE_MARGIN))
        offer = render.file_size(self._offer)
        if limit == largest:
            return self._note("too_big_for_fat", "fits", largest=offer, size=offer)
        return self._note("no_space", "fits", size=offer, free=render.decimal_size(free),
                          needed=render.decimal_size(plan.bytes_ + disktest.FREE_MARGIN))

    def _slow_fill(self, plan: disktest.Plan, disk) -> Optional[Notice]:
        """How long writing the file takes, where it is long enough to say:
        at what this disk wrote last time, or at least what its link takes."""
        model = disk.model if disk is not None else None
        link = render.link_bytes_per_second(disk) if disk is not None else None
        estimate = disktest.fill_estimate(plan, self._history, model, link)
        if estimate is None or estimate[0] < SLOW_FILL_SECONDS:
            return None
        seconds, source = estimate
        rate = plan.bytes_ / seconds
        if source == "last":
            return self._note("slow_fill", "smaller", fill=render.duration(seconds),
                              rate=render.disk_rate(rate))
        return self._note("slow_fill_link", "smaller", fill=render.duration(seconds),
                          rate=render.disk_rate(rate), link=render.disk_link(disk))

    def _warnings(self, place, disk) -> list[str]:
        found = list(place.warnings) if place is not None else []
        if disk is not None and disk.kind == "HDD":
            found.append("rotational")
        if disk is not None and (disk.kind == "Flash" or disk.transport in ("usb", "mmc")):
            found.append("removable")
        return found

    def _note(self, key: str, action: Optional[str] = None, **values) -> Notice:
        """What a key of the test means: what happened, why, and what can be
        done about it, with its button when there is something to do. An
        error, a doubt about the figures and a plain fact each have their
        colour, as everywhere else."""
        title, body = NOTES[key]
        tone = "bad" if key in ERRORS else "warn" if key in DOUBTFUL else "idle"
        note = Notice(_(title).format(**values), _(body).format(**values), tone=tone,
                      action=_(ACTIONS[action]).format(**values) if action else None)
        if action == "folder":
            note.action_clicked.connect(
                lambda: self._on_place(self.place_box.count() - 1))
        elif action == "smaller":
            note.action_clicked.connect(self._smaller_file)
        elif action == "fits":
            note.action_clicked.connect(self._largest_that_fits)
        return note

    def _largest_that_fits(self) -> None:
        """The size the note offered, the largest that fits, among the
        sizes if it isn't one of them."""
        largest = self._offer
        if largest is None:
            return
        index = self.size_box.findData(largest)
        if index < 0:
            index = next((i for i in range(self.size_box.count())
                          if self.size_box.itemData(i) > largest), self.size_box.count())
            self.size_box.insertItem(index, render.file_size(largest), largest)
        self.size_box.setCurrentIndex(index)
        self._drop_failure()
        self._describe()

    def _smaller_file(self) -> None:
        if self.size_box.currentIndex() > 0:
            self.size_box.setCurrentIndex(self.size_box.currentIndex() - 1)
            self._drop_failure()
            self._describe()

    def _drop_failure(self) -> None:
        if self._failure is not None:
            self._failure.setParent(None)
            self._failure.deleteLater()
            self._failure = None
        self._gone = None

    # -- running -------------------------------------------------------------

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
        try:
            os.makedirs(plan.folder, exist_ok=True)
        except OSError:
            # The test itself says what is wrong with the folder.
            pass
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
        self._drop_failure()
        plan = self._run.plan
        if plan is not None:
            # The table of the run under way, filling in as it goes.
            self._only_rows()
            self.disk_name.setText(self._run.model or " + ".join(plan.disks))
            self.conditions.setText(_("disktest.conditions.running"))
            self.rows.set_rows(plan.tests, plan.write)
            for (name, direction), rate in self._run.laps.items():
                self.rows.set_cell(name, direction, rate, live=True)
        if self._run.last:
            self._on_progress(self._run.last)

    def _only_rows(self) -> None:
        """The result card with its table and nothing a finished result
        adds to it."""
        clear_layout(self._result_notes)
        for widget in (self.empty, self.facts["single"], self.fact_row,
                       self.detail_button, self.detail):
            widget.hide()
        for widget in (self.disk_name, self.conditions, self.rows):
            widget.show()
        self.result_card.show()

    def _show_empty(self, measurable: bool) -> None:
        """No result to show: the disk has none yet, or the folder isn't on
        a disk that can be measured, and then there is nothing to say."""
        self.result = None
        clear_layout(self._result_notes)
        for widget in (self.disk_name, self.conditions, self.rows, self.facts["single"],
                       self.fact_row, self.detail_button, self.detail):
            widget.hide()
        self.empty.show()
        self.result_card.setVisible(measurable)

    def _cancel(self) -> None:
        self._run.cancel()
        self.cancel_button.setEnabled(False)
        self.progress.set_state(_("bench.state.cancelling"))

    def _on_progress(self, message: dict) -> None:
        if self._run.cancelling:
            return
        plan = self._run.plan
        if plan is None:
            return
        directions = ("read", "write") if plan.write else ("read",)
        order = [(test, direction) for test in plan.tests for direction in directions]
        total = 1 + len(order)
        done = float(message.get("done") or 0.0)
        phase = message.get("phase")
        if phase == "fill":
            left = message.get("left_seconds")
            what = (_("disktest.step.fill") if left is None else
                    _("disktest.step.fill.left").format(left=render.duration(left)))
            self.progress.set_state(_("disktest.step").format(what=what, n=1, of=total),
                                    done / total, percent=False)
            return
        name, direction = message.get("test"), message.get("direction", "read")
        # The test that runs may be another than asked (a queue of threads
        # without io_uring): its place is the asked one's.
        index = next((i for i, (test, way) in enumerate(order) if way == direction
                      and name in (test.name, test.as_run_by("threads").name)), None)
        if index is None:
            return
        words = test_words(order[index][0])
        what = _("disktest.step.test").format(test=words[:1].lower() + words[1:],
                                              direction=_(DIRECTIONS[direction]))
        self.progress.set_state(_("disktest.step").format(what=what, n=index + 2, of=total),
                                (1 + done * (total - 1)) / total, percent=False)
        if phase == "lapped":
            self.rows.set_cell(message["test"], message["direction"],
                               message["bytes_per_second"], live=True)

    def _on_finished(self, result: disktest.Result, history) -> None:
        self.cancel_button.hide()
        self.progress.hide()
        self.running_changed.emit(False)
        if history is not None:
            self._history = history
        self._paint_history()
        self._drop_failure()
        if result.reason and result.reason != "cancelled":
            key = result.reason if result.reason in ERRORS else "failed"
            figures = dict(result.figures)
            largest = render.file_size(figures.get("largest"))
            self._failure = self._note(
                key, ERRORS[key], needed=render.decimal_size(figures.get("needed")),
                free=render.decimal_size(figures.get("free")),
                size=largest if key == "too_big_for_fat" else render.file_size(result.bytes_),
                largest=largest)
            self._notices.insertWidget(0, self._failure)
        self._describe()
        self._show_for_place()

    # -- painting ------------------------------------------------------------

    def show_result(self, result: disktest.Result) -> None:
        self.result = result
        clear_layout(self._result_notes)
        self.empty.hide()
        disk = self._disks.get(result.disks[0]) if len(result.disks) == 1 else None
        same_disk = disk is not None and (result.model is None or disk.model == result.model)
        link = render.disk_link(disk) if same_disk else render.DASH
        filesystem = result.filesystem or ""
        if result.no_cow:
            filesystem = _("disktest.conditions.nocow").format(filesystem=filesystem)
        self.disk_name.setText(result.label or result.model or " + ".join(result.disks))
        parts = [result.model if result.label else "", link if link != render.DASH else "",
                 filesystem, _(ENGINES[result.engine]) if result.engine in ENGINES else "",
                 when(result.timestamp)]
        self.conditions.setText(" · ".join(part for part in parts if part))
        self.disk_name.show()
        self.conditions.show()

        tests = tuple(dict.fromkeys(m.test for m in result.measures))
        writes = any(m.direction == "write" for m in result.measures)
        self.rows.set_rows(tests, writes)
        self.rows.show()
        for measure in result.measures:
            middle = measure.median
            note = _("disktest.varied.tip").format(
                worst=megabytes(measure.worst.bytes_per_second),
                best=megabytes(measure.best.bytes_per_second)) if measure.noisy else ""
            self.rows.set_cell(measure.name, measure.direction,
                               middle.bytes_per_second if middle else None, note=note)

        fastest = {direction: max((m.median.bytes_per_second for m in result.measures
                                   if m.direction == direction and m.pattern == "sequential"
                                   and m.median is not None), default=None)
                   for direction in ("read", "write")}
        # A disk of platters is held back by them, not by its cable: no share.
        most = (render.link_bytes_per_second(disk)
                if same_disk and disk.kind != "HDD" else None)
        best = max((rate for rate in fastest.values() if rate), default=None)
        share = best / most * 100 if best and most else None

        single = {direction: result.measure(SINGLE, direction) for direction in ("read", "write")}
        single = {direction: m.median for direction, m in single.items()
                  if m is not None and m.median is not None}
        read = single.get("read")
        self.facts["single"].setVisible(read is not None)
        if read is not None:
            # A line for reading and one for writing: in one, the card was
            # crammed and «µs» parted from its figure.
            self.facts["single"].show_fact(microseconds(read.latency_mean_ns), "\n".join(
                _("disktest.single.line").format(
                    direction=_(DIRECTIONS[direction]).capitalize(),
                    iops=render.thousands(round(lap.requests_per_second)),
                    mean=microseconds(lap.latency_mean_ns), p99=microseconds(lap.latency_p99_ns))
                for direction, lap in single.items()))
        self.facts["link"].setVisible(share is not None)
        if share is not None:
            note = render.disk_link_note(disk)
            self.facts["link"].show_fact(render.whole_percent(share), " ".join(
                part for part in (_("disktest.fact.link.detail").format(
                    link=link, most=megabytes(most)), note) if part))
        fahrenheit = self._prefs.fahrenheit
        hot = result.temperature_peak_c
        heat = self.facts["heat"]
        heat.setVisible(hot is not None)
        if hot is not None:
            heat.show_fact(render.temperature(hot, fahrenheit), _("disktest.fact.heat.detail").format(
                start=unbroken(render.temperature(result.temperature_start_c, fahrenheit)),
                end=unbroken(render.temperature(result.temperature_end_c, fahrenheit))))
            # As everywhere else, from the limits the disk itself declares;
            # another disk's, or none, leave it uncoloured.
            paint_level(heat.value, thermal.level(hot, disk.temp_high_c, disk.temp_critical_c)
                        if same_disk else thermal.OK)
        self.fact_row.setVisible(any(self.facts[name].isVisibleTo(self.fact_row)
                                     for name in ("link", "heat")))

        # What this result has to be read with, in its own card.
        for warning in result.warnings:
            if warning in RESULT_NOTES:
                self._result_notes.addWidget(self._note(warning))
        # On platters, where the file lay says how much of the figure is
        # the disk and how much the spot; elsewhere it says nothing.
        if same_disk and disk.kind == "HDD":
            if result.placement is not None:
                first, last = render.disk_span(*result.placement)
                self._result_notes.addWidget(self._note("placement", first=first, last=last))
            else:
                why = disktest.unplaceable(result.filesystem, result.layers, result.disks)
                self._result_notes.addWidget(self._note(
                    f"placement_unknown.{why or 'unsaid'}", filesystem=result.filesystem or ""))
        varied = [m for m in result.measures if m.noisy]
        if varied:
            self._result_notes.addWidget(self._note("varied", tests=", ".join(
                f"{m.name} ({_(DIRECTIONS[m.direction])})" for m in varied)))

        rows = []
        for measure in result.measures:
            first = next((lap for lap in measure.laps if lap.number == 0), None)
            rows.append([
                measure.name, _(DIRECTIONS[measure.direction]),
                megabytes(first.bytes_per_second) if first else render.DASH,
                "  ".join(megabytes(lap.bytes_per_second) for lap in measure.counted),
                megabytes(measure.best.bytes_per_second) if measure.best else render.DASH,
                megabytes(measure.worst.bytes_per_second) if measure.worst else render.DASH,
                render.DASH if measure.spread is None else f"{measure.spread * 100:.1f} %"])
        self.laps_table.set_rows(rows)
        self.method.setText(self._method(result))
        self.detail_button.show()
        self.detail.setVisible(self.detail_button.isChecked())
        self.result_card.show()

    def _method(self, result: disktest.Result) -> str:
        cached = [m.cached_bytes for m in result.measures]
        checked = ("disktest.method.direct" if cached and all(c == 0 for c in cached)
                   else "disktest.method.unchecked")
        parts = [_("disktest.method.file").format(size=render.size(result.bytes_))]
        if result.no_cow:
            parts.append(_("disktest.method.nocow"))
        parts += [
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
        clear_layout(self._history_groups)
        self.history_tables = []
        groups: dict[tuple, list[disktest.Result]] = {}
        for result in self._history:
            groups.setdefault((result.model or " + ".join(result.disks), result.engine,
                               result.profile), []).append(result)
        fahrenheit = self._prefs.fahrenheit
        for (disk, engine, profile), results in groups.items():
            sequential = disktest.headline_test(profile)
            found = {name: next((m for r in results for m in r.measures
                                 if name in (m.name, m.stands_for)), None)
                     for name in (sequential, SINGLE)}
            ran = {name: m.name if m else name for name, m in found.items()}
            known = {t.name: t for tests in disktest.PROFILES.values() for t in tests}
            tests = {name: m.test if m else known[name] for name, m in found.items()}
            writes = any(m.direction == "write" for r in results for m in r.measures)
            columns = [(sequential, "read")] + ([(sequential, "write")] if writes else []) \
                + [(SINGLE, "read")]
            # Each test in words, as the table above names it, with its code
            # on hovering: «Sequential, read».
            table = Table([_("memtest.col.date")]
                          + [_("disktest.col.history").format(
                              test=test_words(tests[name]), direction=_(DIRECTIONS[direction]))
                             for name, direction in columns]
                          + [_("disktest.col.hottest")],
                          numeric=(False,) + (True,) * (len(columns) + 1))
            for column, (name, direction) in enumerate(columns, start=1):
                table.set_header_tooltip(column, f"{ran[name]} · {_(DIRECTIONS[direction])}")
            rows = []
            for result in results:
                cells = [result.label or when(result.timestamp)]
                for name, direction in columns:
                    measure = result.measure(name, direction)
                    middle = measure.median if measure is not None else None
                    cells.append(megabytes(middle.bytes_per_second) if middle else render.DASH)
                cells.append(render.temperature(result.temperature_peak_c, fahrenheit))
                rows.append(cells)
            table.set_rows(rows)
            heading = QLabel(" · ".join(part for part in (
                disk, _(ENGINES[engine]) if engine in ENGINES else "",
                _(PROFILE_NAMES[profile]) if profile in PROFILE_NAMES else profile) if part))
            heading.setObjectName("FieldName")
            heading.setWordWrap(True)
            self._history_groups.addWidget(heading)
            self._history_groups.addWidget(table)
            self.history_tables.append((heading, table))
        self.history_card.setVisible(bool(self._history))

    # -- the window's protocol -----------------------------------------------

    def apply(self, snapshot) -> None:
        """Nothing here follows the sampling but which disks there are and
        what is mounted where."""
        def seen(disks) -> list:
            return [(d.name, d.model, d.link, tuple(d.partitions)) for d in disks.values()]

        disks = {disk.name: disk for disk in snapshot.disks}
        changed = seen(disks) != seen(self._disks)
        self._disks = disks
        self._fill_places()
        if changed or not self._placed:
            self._placed = True
            self._describe()
            self._show_for_place()

    def stop(self) -> None:
        self._run.cancel()
