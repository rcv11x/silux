"""The Memory tab of Performance: latency per level, the curve and bandwidth.

A figure here comes with what makes it believable: the frequency it was
measured at and what it is in the core's cycles, whether the curve steps
where the processor says its caches end, how much of what the memory could
move is being moved, and the method, in a line.
"""

from __future__ import annotations

import math
import threading
import time
from typing import Optional

from PySide6.QtCore import QObject, QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from ... import memtest, render
from ...i18n import _
from ...settings import Preferences
from .. import tarjeta, theme
from ..theme import Palette, ui_font
from ..widgets import (
    Button,
    Card,
    Fact,
    FoldingRow,
    LockMark,
    Notice,
    PageRoot,
    ProgressLine,
    RateBar,
    ResponsiveRow,
    ScrollPage,
    ShareButtons,
    Table,
    clear_layout,
    let_go,
    unbroken,
    value_font,
)

# The grid's rows, the RAM first: it's what the test is mostly run for.
GRID_LEVELS = ("RAM", "L1", "L2", "L3")
# Each level's rows: its figures; the core's cycles and the one-thread
# figures, or «no cache» when there is no room beside the figures (and the
# one-thread figures a row lower); and the air before the next.
LEVEL_ROWS = 4
# Its bandwidth columns, each with its colour: the accent and the chart's
# two others, never the status colours, which would make a bar a warning.
GRID_COLUMNS = (("read", "memtest.op.read", "accent"), ("write", "memtest.op.write", "series_b"),
                ("copy", "memtest.op.copy", "series_c"))
# Each operation takes a bar, the word that says it skipped the cache, and
# its figure; the latency comes after them.
PER_OPERATION = 3
LATENCY_COLUMN = 1 + PER_OPERATION * len(GRID_COLUMNS)
# The air between its columns, and with no room for the bars.
GRID_GAP, NARROW_GRID_GAP = 12, 6
GB = 1e9
NBSP = "\u00a0"
# What each step of a test is called while it runs; the one with every
# thread says how many (`render.counted`).
STEPS = {"latency": "memtest.step.latency", "single": "memtest.step.single",
         "multi": "memtest.step.multi"}
REASONS = {"cancelled": "memtest.reason.cancelled", "no_memory": "memtest.reason.nomemory",
           "bad_cpu": "memtest.reason.badcpu", "clock": "memtest.reason.clock",
           "sin_memoria": "memtest.reason.nomemory", "not_started": "memtest.reason.failed"}
RATE_ROWS = (("read", False, "memtest.op.read"), ("write", False, "memtest.op.write"),
             ("copy", False, "memtest.op.copy"), ("write", True, "memtest.op.writent"),
             ("copy", True, "memtest.op.copynt"))
# A size mark under the curve every this many powers of two: 64 KiB, 1 MiB,
# 16 MiB, 256 MiB.
SIZE_MARK_EVERY = 4


def when(timestamp: float) -> str:
    return time.strftime("%d/%m/%Y %H:%M", time.localtime(timestamp))


def level_name(level: str) -> str:
    """«Memoria (RAM)», «Caché L2»."""
    return _("memtest.level.ram") if level == "RAM" else _("memtest.level.cache").format(level=level)


class CurveChart(QWidget):
    """Latency against block size, both on a logarithmic scale, with a mark
    where each cache ends."""

    def __init__(self, palette: Palette, parent=None):
        super().__init__(parent)
        self._p = palette
        self._points: tuple = ()
        self._caches: tuple = ()
        # Where each cache's name went at the last paint.
        self.label_boxes: list = []
        # Room for its axes' figures and five levels' names, at any font size.
        self.setMinimumHeight(5 * theme.METRICS.cell_h)

    def set_curve(self, points, caches) -> None:
        self._points, self._caches = tuple(points), tuple(caches)
        self.update()

    def paintEvent(self, _event) -> None:  # noqa: N802
        if len(self._points) < 2:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setFont(ui_font(theme.METRICS.small_pt))
        metrics = painter.fontMetrics()
        sizes = [math.log2(p.bytes_) for p in self._points]
        times = [math.log10(max(p.nanoseconds, 0.01)) for p in self._points]
        x0, x1 = sizes[0], sizes[-1]
        y0, y1 = math.floor(min(times)), math.ceil(max(times))
        if x1 <= x0 or y1 <= y0:
            return
        left = 10 + max(metrics.horizontalAdvance(render.nanoseconds_mark(10 ** decade))
                        for decade in range(y0, y1 + 1))
        bottom = metrics.height() + 8
        area = QRectF(left, 8, self.width() - left - 12, self.height() - bottom - 8)

        def at(size_log: float, time_log: float) -> QPointF:
            return QPointF(area.left() + (size_log - x0) / (x1 - x0) * area.width(),
                           area.bottom() - (time_log - y0) / (y1 - y0) * area.height())

        muted, line = QColor(self._p.muted), QColor(self._p.line)
        for decade in range(y0, y1 + 1):
            y = at(x0, decade).y()
            painter.setPen(QPen(line, 1))
            painter.drawLine(QPointF(area.left(), y), QPointF(area.right(), y))
            painter.setPen(muted)
            painter.drawText(QRectF(0, y - metrics.height() / 2, left - 6, metrics.height()),
                             Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                             render.nanoseconds_mark(10 ** decade))
        painter.setPen(muted)
        edges = ((Qt.AlignmentFlag.AlignLeft, self._points[0].bytes_),
                 (Qt.AlignmentFlag.AlignRight, self._points[-1].bytes_))
        taken = []
        for edge, size in edges:
            text = render.size(size)
            width = metrics.horizontalAdvance(text)
            left = area.left() if edge == Qt.AlignmentFlag.AlignLeft else area.right() - width
            taken.append((left, left + width))
            painter.drawText(QRectF(area.left(), area.bottom() + 4, area.width(),
                                    metrics.height()), edge, text)
        for size_log in range(math.ceil(x0), math.floor(x1) + 1):
            if size_log % SIZE_MARK_EVERY:
                continue
            x = at(size_log, y0).x()
            text = render.size(2 ** size_log)
            width = metrics.horizontalAdvance(text)
            left = x - width / 2
            # Not over the sizes at either end.
            if any(left < end + 8 and start - 8 < left + width for start, end in taken):
                continue
            painter.setPen(QPen(line, 1))
            painter.drawLine(QPointF(x, area.top()), QPointF(x, area.bottom()))
            painter.setPen(muted)
            painter.drawText(QPointF(left, area.bottom() + 4 + metrics.ascent()), text)
        self.label_boxes = []
        for name, size in self._caches:
            position = math.log2(size)
            if not x0 <= position <= x1:
                continue
            x = at(position, y0).x()
            painter.setPen(QPen(muted, 1, Qt.PenStyle.DashLine))
            painter.drawLine(QPointF(x, area.top()), QPointF(x, area.bottom()))
            label = f"{name} · {render.size(size)}"
            width = metrics.horizontalAdvance(label)
            # Where the curve isn't: it only rises, so above it on the left
            # and under it once it has climbed past the middle.
            nearest = min(range(len(sizes)), key=lambda i: abs(sizes[i] - position))
            high = at(position, times[nearest]).y() < area.center().y()
            top = area.bottom() - metrics.height() - 2 if high else area.top() + 1
            box = QRectF(min(x + 2, area.right() - width - 4), top, width + 4, metrics.height())
            # Over the size marks' grid, not under it.
            painter.fillRect(box, QColor(self._p.surface))
            painter.setPen(muted)
            painter.drawText(box, Qt.AlignmentFlag.AlignCenter, label)
            self.label_boxes.append(box)
        painter.setPen(QPen(QColor(self._p.accent), 2))
        painter.drawPolyline(QPolygonF([at(s, t) for s, t in zip(sizes, times)]))


class LevelGrid(QWidget):
    """A row per level: what it reads, writes and copies with every thread
    (large) and with one (under it), and its latency in nanoseconds and in
    the core's cycles. A level without a figure leaves its cells empty."""

    def __init__(self, palette: Palette, parent=None):
        super().__init__(parent)
        self._p = palette
        layout = QGridLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setHorizontalSpacing(GRID_GAP)
        layout.setVerticalSpacing(2)
        # Each operation's title: over its bar, or over its figure where
        # there are no bars (`_show_bars`).
        self.heads: list[QLabel] = []
        for index, (_operation, key, _colour) in enumerate(GRID_COLUMNS):
            first = 1 + PER_OPERATION * index
            head = self._head(key)
            layout.addWidget(head, 0, first, 1, PER_OPERATION)
            layout.setColumnStretch(first, 1)
            self.heads.append(head)
        latency = self._head("memtest.col.latency")
        latency.setAlignment(Qt.AlignmentFlag.AlignRight)
        layout.addWidget(latency, 0, LATENCY_COLUMN)
        self.names: dict[str, tuple[QLabel, QLabel]] = {}
        self.blocks: dict[str, QWidget] = {}
        # Each operation's bar, figure and line under it, and the word that
        # says the figure skipped the cache, beside it.
        self.cells: dict[tuple[str, str], tuple[RateBar, QLabel, QLabel]] = {}
        self.kinds: dict[tuple[str, str], QLabel] = {}
        # Whether there is room for the bars, and which levels have them.
        self._barred = True
        self._bars: set[str] = set()
        self.latencies: dict[str, tuple[QLabel, QLabel]] = {}
        self.rows: dict[str, list[QWidget]] = {}
        for line, level in enumerate(GRID_LEVELS):
            top = 1 + LEVEL_ROWS * line
            name, size = self._name(level)
            block = QWidget()
            inside = QVBoxLayout(block)
            inside.setContentsMargins(0, 0, 0, 0)
            inside.setSpacing(0)
            inside.addWidget(name)
            inside.addWidget(size)
            layout.addWidget(block, top, 0, 2, 1, Qt.AlignmentFlag.AlignTop)
            self.names[level] = (name, size)
            self.blocks[level] = block
            widgets: list[QWidget] = [block]
            for index, (operation, _key, colour) in enumerate(GRID_COLUMNS):
                first = 1 + PER_OPERATION * index
                bar = RateBar(palette, colour=colour, height=18)
                kind = self._small()
                kind.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                # Never on two lines: without room beside its figure it
                # goes under it (`_arrange`).
                kind.setWordWrap(False)
                figure = self._big()
                under = self._small()
                layout.addWidget(bar, top, first)
                layout.addWidget(kind, top, first + 1)
                layout.addWidget(figure, top, first + 2)
                layout.addWidget(under, top + 1, first, 1, PER_OPERATION)
                self.cells[level, operation] = (bar, figure, under)
                self.kinds[level, operation] = kind
                widgets += [bar, kind, figure, under]
            nanoseconds, cycles = self._big(), self._small()
            layout.addWidget(nanoseconds, top, LATENCY_COLUMN)
            layout.addWidget(cycles, top + 1, LATENCY_COLUMN)
            self.latencies[level] = (nanoseconds, cycles)
            widgets += [nanoseconds, cycles]
            layout.setRowMinimumHeight(top + 3, 8)
            self.rows[level] = widgets
        self.unit = QLabel("")
        self.unit.setObjectName("Muted")
        self.unit.setFont(ui_font(theme.METRICS.small_pt))
        self.unit.setWordWrap(True)
        layout.addWidget(self.unit, 1 + LEVEL_ROWS * len(GRID_LEVELS), 0, 1, LATENCY_COLUMN + 1)
        # The width the grid needs with its bars, measured while they are
        # shown: leaving them and going back are decided on the same figure.
        self._width_with_bars = 0

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._fit_bars()

    def _fit_bars(self) -> None:
        """Bars too narrow to be drawn leave the layout, and the air around
        them with them: in a narrow window the figures need it."""
        if self._barred:
            self._width_with_bars = (self.minimumSizeHint().width()
                                     + RateBar.NARROWEST * len(GRID_COLUMNS))
        room = self.width() >= self._width_with_bars
        if room != self._barred:
            self._barred = room
            self._arrange()

    def _arrange(self) -> None:
        """With the bars, each «no cache» goes beside its figure. Without
        them it goes under it, on a line of its own beside the core's cycles,
        and the one-thread figure a line lower: beside the figure there is
        only room for it on two lines."""
        layout = self.layout()
        layout.setHorizontalSpacing(GRID_GAP if self._barred else NARROW_GRID_GAP)
        under_row = 1 if self._barred else 2
        for line, level in enumerate(GRID_LEVELS):
            top = 1 + LEVEL_ROWS * line
            block = self.blocks[level]
            layout.removeWidget(block)
            layout.addWidget(block, top, 0, under_row + 1, 1, Qt.AlignmentFlag.AlignTop)
            for index, (operation, _key, _colour) in enumerate(GRID_COLUMNS):
                first = 1 + PER_OPERATION * index
                kind = self.kinds[level, operation]
                under = self.cells[level, operation][2]
                layout.removeWidget(kind)
                layout.removeWidget(under)
                if self._barred:
                    layout.addWidget(kind, top, first + 1)
                else:
                    layout.addWidget(kind, top + 1, first, 1, PER_OPERATION)
                layout.addWidget(under, top + under_row, first, 1, PER_OPERATION)
        self._show_bars()

    def _show_bars(self) -> None:
        for (level, _operation), (bar, _figure, _under) in self.cells.items():
            bar.setVisible(self._barred and level in self._bars)
        side = (Qt.AlignmentFlag.AlignLeft if self._barred and self._bars
                else Qt.AlignmentFlag.AlignRight)
        for head in self.heads:
            head.setAlignment(side | Qt.AlignmentFlag.AlignVCenter)

    @staticmethod
    def _head(key: str) -> QLabel:
        head = QLabel(_(key).upper())
        head.setObjectName("ColumnTitle")
        return head

    @staticmethod
    def _name(level: str) -> tuple[QLabel, QLabel]:
        name = QLabel(level_name(level))
        name.setFont(ui_font(theme.METRICS.base_pt + 1))
        name.setWordWrap(True)
        size = QLabel("")
        size.setObjectName("Muted")
        size.setFont(ui_font(theme.METRICS.small_pt - 1))
        size.setWordWrap(True)
        return name, size

    @staticmethod
    def _big() -> QLabel:
        label = QLabel("")
        font = value_font()
        font.setPointSizeF(font.pointSizeF() + 3)
        font.setWeight(font.Weight.DemiBold)
        label.setFont(font)
        label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        return label

    @staticmethod
    def _small() -> QLabel:
        label = QLabel("")
        label.setObjectName("Muted")
        label.setFont(ui_font(theme.METRICS.small_pt - 1))
        label.setAlignment(Qt.AlignmentFlag.AlignRight)
        # In a narrow window it takes two lines before the table outgrows
        # the page.
        label.setWordWrap(True)
        return label

    def set_result(self, result: memtest.Result) -> None:
        threads = max((r.threads for r in result.rates), default=1)
        sizes = dict(result.caches)
        # The bars against what the memory could move, as the share of the
        # maximum says: without it, none.
        most = result.theoretical_bytes_per_second
        for level in GRID_LEVELS:
            found = result.level(level)
            figures = {operation: result.fastest(operation, threads, level)
                       for operation, _key, _colour in GRID_COLUMNS}
            shown = found is not None or any(every for every, _one in figures.values())
            for widget in self.rows[level]:
                widget.setVisible(shown)
            if not shown:
                continue
            _name, size = self.names[level]
            if level == "RAM":
                size.setText(_("memtest.level.block").format(block=render.size(result.ram_block))
                             if result.ram_block else "")
            else:
                size.setText(render.size(sizes[level]) if level in sizes else "")
            for operation, _key, _colour in GRID_COLUMNS:
                bar, figure, under = self.cells[level, operation]
                kind = self.kinds[level, operation]
                every, one = figures[operation]
                for widget in (figure, under):
                    widget.setVisible(every is not None)
                if every is not None and most:
                    self._bars.add(level)
                else:
                    self._bars.discard(level)
                kind.setVisible(every is not None and every.non_temporal)
                if every is None:
                    continue
                bar.set_fraction(every.bytes_per_second / most if most else None)
                figure.setText(render.rate_figure(every.bytes_per_second, GB))
                # By the large figure, which is the one that skipped the
                # cache; the one-thread figure under it is of the same kind.
                kind.setText(_("memtest.grid.nt"))
                under.setText("" if threads == 1 or one is None else
                              f"{render.counted('memtest.threads', 1)} "
                              f"{render.rate_figure(one.bytes_per_second, GB)}".replace(" ", NBSP))
            nanoseconds, cycles = self.latencies[level]
            nanoseconds.setText(render.nanoseconds(found.nanoseconds) if found else "")
            count = render.core_cycles(found.nanoseconds, found.frequency_hz) if found else None
            cycles.setText("" if count is None else _("memtest.grid.cycles").format(n=f"{count:.1f}"))
        unit = [_("memtest.grid.unit" if threads > 1 else "memtest.grid.unit.single").format(
            threads=render.counted("memtest.threads", threads))]
        if result.rates:
            unit.append(_("memtest.grid.bars").format(total=render.bandwidth(most, 1)) if most
                        else _("memtest.grid.nobars"))
        if any(result.level(level) for level in ("L1", "L2", "L3")):
            unit.append(_("memtest.grid.caches"))
        self.unit.setText(" ".join(unit))
        # Other figures need another width: it is measured again with the bars.
        self._barred = True
        self._arrange()
        self._fit_bars()


class MemoryTestRun(QObject):
    """A memory test under way, apart from the tab that shows it.

    The window rebuilds every page when the theme, the font, the language or
    the units change. The tab goes; the test, which runs in a child process,
    carries on, and the new tab picks it up here: its progress, its result
    and the history, saved once whichever tab is showing.
    """

    progressed = Signal(str, float)
    # The result, and the history with it when it measured something.
    finished = Signal(object, object)

    def __init__(self, parent: Optional[QObject] = None):
        super().__init__(parent)
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        # The last step reported, for a tab that arrives half way, and the
        # plan it belongs to.
        self.last: tuple[str, float] = ("", 0.0)
        self.plan: Optional[memtest.Plan] = None
        self._done.connect(self._on_done)

    _done = Signal(object)

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    @property
    def cancelling(self) -> bool:
        return self.running and self._stop.is_set()

    def start(self, plan: memtest.Plan, memory: memtest.Memory) -> bool:
        if self.running:
            return False
        self._stop.clear()
        self.last = ("", 0.0)
        self.plan = plan

        def step(phase: str, done: float) -> None:
            self.last = (phase, done)
            self.progressed.emit(phase, done)

        def work() -> None:
            self._done.emit(memtest.run(plan, step, self._stop, memory))

        self._thread = threading.Thread(target=work, daemon=True)
        self._thread.start()
        return True

    def cancel(self) -> None:
        self._stop.set()

    def _on_done(self, result: memtest.Result) -> None:
        self._thread = None
        history = memtest.append_history(result) if result.measured else None
        self.finished.emit(result, history)


class MemoryTestTab(ScrollPage):
    # Whether a test is under way: the other tabs wait for it.
    running_changed = Signal(bool)
    # A test just measured, for the pages that show part of it.
    measured = Signal(object)
    # The padlock of what is read with permissions.
    elevation_requested = Signal()

    def __init__(self, palette: Palette, prefs: Preferences, parent=None,
                 run: Optional[MemoryTestRun] = None):
        """`run`: the window's, which outlives this tab; without one, its own."""
        super().__init__(parent)
        self._p = palette
        self._prefs = prefs
        self._run = run if run is not None else MemoryTestRun(self)
        self._types: tuple = ()
        self._memory = memtest.Memory()
        # Whether the channels are missing for want of permissions, and with
        # the installed helper out of date.
        self._channels_locked = False
        self._helper_outdated = False
        self._booted_at: Optional[float] = None
        self._failure: Optional[Notice] = None
        self.result: Optional[memtest.Result] = None

        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        root = PageRoot()
        self.setWidget(root)
        layout = root.column

        layout.addWidget(self._build_header())
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
        history = memtest.load_history()
        self._paint_history(history)
        if history:
            self.show_result(history[0])
        if self._run.running:
            self._show_running()
            if self._run.cancelling:
                self._cancel()
            elif self._run.last[0]:
                self._on_progress(*self._run.last)

    # -- building ------------------------------------------------------------

    def _build_header(self) -> Card:
        card = Card()
        title = QLabel(_("memtest.title"))
        title.setObjectName("Headline")
        title.setWordWrap(True)
        self.intro = QLabel(_("memtest.intro"))
        self.intro.setObjectName("Subhead")
        self.intro.setWordWrap(True)
        self.run_button = Button(_("memtest.button.run"))
        self.run_button.setObjectName("Primary")
        self.run_button.clicked.connect(self.start)
        self.cancel_button = Button(_("bench.button.cancel"))
        self.cancel_button.setObjectName("Danger")
        self.cancel_button.clicked.connect(self._cancel)
        self.cancel_button.hide()
        self.blocked_note = QLabel("")
        self.blocked_note.setObjectName("Muted")
        self.blocked_note.hide()
        # On the right, as in the Disk tab.
        buttons = FoldingRow()
        buttons.add_widget(self.blocked_note)
        buttons.add_stretch(1)
        buttons.add_widget(self.run_button)
        buttons.add_widget(self.cancel_button)
        air = card.body.spacing()
        # Apart from the button, under a line: they go with it when hidden.
        self.progress = ProgressLine(divided=True, air=theme.METRICS.card_gap + air)
        self.progress.hide()
        # What it is, and right under it, on the right, what to do.
        card.body.addWidget(title)
        card.body.addWidget(self.intro)
        for widget in (buttons, self.progress):
            card.body.addWidget(widget)
        return card

    def _build_result(self) -> Card:
        card = Card(_("memtest.card.result"))
        self.cpu_name = QLabel("")
        self.cpu_name.setFont(ui_font(theme.METRICS.base_pt + 3))
        self.cpu_name.setWordWrap(True)
        self.cpu_name.hide()
        card.body.addWidget(self.cpu_name)
        self.conditions = QLabel("")
        self.conditions.setObjectName("Muted")
        self.conditions.setWordWrap(True)
        card.body.addWidget(self.conditions)

        self.grid = LevelGrid(self._p)
        card.body.addWidget(self.grid)

        self.facts = {name: Fact(_(key)) for name, key in (
            ("share", "memtest.fact.share"), ("curve", "memtest.fact.curve"),
            ("pages", "memtest.fact.pages"))}
        self.facts_row = ResponsiveRow(min_item_width=170)
        for fact in self.facts.values():
            self.facts_row.add(fact)
        card.body.addWidget(self.facts_row)
        # The share's detail, with the padlock and the way to give
        # permissions when that is what it waits for (rule 5).
        share = self.facts["share"]
        self.share_value = share.value
        self.share = share.detail
        self.share.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        self.share_lock = LockMark(self._p.info, theme.METRICS.small_pt + 3)
        self.share_lock.hacer_pulsable()
        self.share_lock.clicked.connect(self.elevation_requested)
        self.share_button = Button("")
        self.share_button.setObjectName("LinkAction")
        self.share_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.share_button.clicked.connect(self.elevation_requested)
        share_row = QHBoxLayout()
        share_row.setSpacing(6)
        # The padlock in the middle of the text's first line, however tall
        # the letter is (`_paint_share`).
        self._lock_column = QVBoxLayout()
        self._lock_column.setContentsMargins(0, 0, 0, 0)
        self._lock_column.addWidget(self.share_lock)
        self._lock_column.addStretch(1)
        share_row.addLayout(self._lock_column)
        share.body.removeWidget(self.share)
        share_row.addWidget(self.share, 1)
        share.body.addLayout(share_row)
        buttons = QHBoxLayout()
        buttons.addWidget(self.share_button)
        buttons.addStretch(1)
        share.body.addLayout(buttons)
        self.verdict = self.facts["curve"].detail

        # What this result has to be read with, inside its own card.
        self._result_notes = QVBoxLayout()
        self._result_notes.setSpacing(6)
        card.body.addLayout(self._result_notes)

        self.detail_button = Button(_("memtest.detail.show"))
        self.detail_button.setObjectName("GhostButton")
        self.detail_button.setCheckable(True)
        self.detail_button.toggled.connect(self._toggle_detail)
        self.share_buttons = ShareButtons()
        fold = QHBoxLayout()
        fold.addWidget(self.detail_button)
        fold.addStretch(1)
        fold.addWidget(self.share_buttons)
        card.body.addLayout(fold)
        self.detail = QWidget()
        inside = QVBoxLayout(self.detail)
        inside.setContentsMargins(0, 0, 0, 0)
        self.chart = CurveChart(self._p)
        inside.addWidget(self.chart)
        self.rates_table = Table(
            [_("memtest.col.operation"), _("memtest.col.one"), _("memtest.col.all")],
            numeric=(False, True, True))
        inside.addWidget(self.rates_table)
        self.threads_note = QLabel("")
        self.threads_note.setObjectName("Muted")
        self.threads_note.setWordWrap(True)
        inside.addWidget(self.threads_note)
        self.method = QLabel("")
        self.method.setObjectName("Muted")
        self.method.setWordWrap(True)
        inside.addWidget(self.method)
        self.detail.hide()
        card.body.addWidget(self.detail)
        card.hide()
        return card

    def _build_history(self) -> Card:
        card = Card(_("memtest.card.history"))
        self.history = Table(
            [_("memtest.col.date"), _("memtest.col.ram"), _("memtest.col.read.all"),
             _("memtest.col.share"), _("memtest.col.frequency")],
            numeric=(False, True, True, True, True))
        card.body.addWidget(self.history)
        self.clear_button = Button(_("bench.button.clear"))
        self.clear_button.clicked.connect(self._clear_history)
        row = QHBoxLayout()
        row.addWidget(self.clear_button)
        row.addStretch(1)
        card.body.addLayout(row)
        card.hide()
        return card

    # -- running -------------------------------------------------------------

    @property
    def running(self) -> bool:
        return self._run.running

    def set_blocked(self, by: Optional[str]) -> None:
        """Another test is under way, called `by`, or none is."""
        self.run_button.setEnabled(by is None and not self.running)
        self.blocked_note.setText("" if by is None else _("bench.tabs.busy").format(test=by))
        self.blocked_note.setVisible(by is not None)

    def plan(self) -> memtest.Plan:
        native = memtest.native_module()
        allowed = native.allowed_cpus() if native else sorted(
            cpu for core_type in self._types for cpu in core_type.cpus)
        cpu, caches = memtest.pick_cpu(self._types, allowed)
        return memtest.make_plan(caches, allowed, cpu)

    def start(self) -> None:
        if self.running or not self.run_button.isEnabled():
            return
        if not self._run.start(self.plan(), self._memory):
            return
        self._show_running()
        self.running_changed.emit(True)

    def _show_running(self) -> None:
        self.run_button.setEnabled(False)
        self.cancel_button.setEnabled(True)
        self.cancel_button.show()
        self.progress.begin(_("bench.state.preparing"))
        self.progress.show()
        # The last result stays in view, with its notices, until the new one
        # arrives: only a failure of the run before goes.
        self._drop_failure()

    def _cancel(self) -> None:
        self._run.cancel()
        self.cancel_button.setEnabled(False)
        self.progress.set_state(_("bench.state.cancelling"))

    def _on_progress(self, step: str, done: float) -> None:
        plan = self._run.plan
        order = memtest.steps(plan) if plan is not None else ()
        if self._run.cancelling or step not in order:
            return
        what = (render.counted(STEPS[step], len(plan.cpus)) if step == "multi"
                else _(STEPS[step]))
        self.progress.set_state(_("memtest.step").format(
            what=what, n=order.index(step) + 1, of=len(order)), done, percent=False)

    def _drop_failure(self) -> None:
        if self._failure is not None:
            let_go(self._failure)
            self._failure = None

    def _on_finished(self, result: memtest.Result, history) -> None:
        self.run_button.setEnabled(True)
        self.cancel_button.hide()
        self.progress.hide()
        self.running_changed.emit(False)
        if not result.measured:
            if result.reason != "cancelled":
                self._failure = Notice(_("memtest.notice.failed"),
                                       _(REASONS.get(result.reason, "memtest.reason.failed")))
                self._notices.insertWidget(0, self._failure)
            return
        self._paint_history(history)
        self.show_result(result)
        self.measured.emit(result)

    # -- painting ------------------------------------------------------------

    def show_result(self, result: memtest.Result) -> None:
        self.result = result
        clear_layout(self._result_notes)
        frequencies = [p.frequency_hz for p in result.points if p.frequency_hz]
        parts = []
        if result.speed_mts:
            parts.append(f"{render.memory_speed(result.speed_mts)} MT/s")
        if result.channels:
            parts.append(render.counted("memtest.channels", result.channels))
        if frequencies:
            parts.append(render.hz(max(frequencies)))
        if result.governor:
            parts.append(result.governor)
        parts.append(when(result.timestamp))
        self.conditions.setText(" · ".join(parts))
        self.share_buttons.set_card(
            (lambda: tarjeta.draw_memory_test(result, self.cpu_name.text(), self._p))
            if tarjeta.shareable(result) else None,
            time.strftime(f"{_('share.test.file.memory')}-%Y%m%d-%H%M.png",
                          time.localtime(result.timestamp)))

        self.grid.set_result(result)
        self.grid.setVisible(bool(result.levels or result.rates))
        self._paint_verdict(result)
        self._paint_rates(result)
        self._paint_pages(result)
        self.facts_row.setVisible(any(f.isVisibleTo(self.facts_row) for f in self.facts.values()))
        self.chart.set_curve(result.points, result.caches)
        self.chart.setVisible(len(result.points) > 1)
        self.method.setText(self._method(result))
        self.result_card.show()

        if result.engine == "simple":
            self._note(Notice(_("memtest.notice.simple"), _("memtest.notice.simple.body"),
                              tone="info"))
        clock = memtest.clock_change(result)
        if clock is not None:
            low, high = clock
            self._note(Notice(
                _("memtest.notice.clock").format(
                    percent=render.whole_percent((high - low) / high * 100)),
                _("memtest.notice.clock.body").format(low=render.hz(low), high=render.hz(high))))
        noisy = sum(1 for p in result.points if p.noisy) + sum(1 for r in result.rates if r.noisy)
        if noisy:
            self._note(Notice(_("memtest.notice.noisy"),
                              render.counted("memtest.notice.noisy.body", noisy)))

    def _note(self, notice: Notice) -> None:
        self._result_notes.addWidget(notice)

    def _paint_verdict(self, result: memtest.Result) -> None:
        steps = memtest.curve_steps(result.points, result.levels, result.caches)
        wrong = next((s for s in steps if not s.matches), None)
        fact = self.facts["curve"]
        if wrong is not None:
            text = _("memtest.verdict.differs").format(
                level=wrong.level, flat=render.size(wrong.flat_until),
                rises=render.size(wrong.rises_by), declared=render.size(wrong.declared_bytes))
            if result.huge_fraction is not None and result.huge_fraction < 0.9:
                text += " " + _("memtest.verdict.smallpages")
            fact.show_fact(_("memtest.fact.curve.differs"), text)
        elif steps:
            fact.show_fact(_("memtest.fact.curve.matches"), _("memtest.verdict.matches").format(
                sizes=", ".join(f"{s.level} {render.size(s.declared_bytes)}" for s in steps)))
        fact.setVisible(bool(steps))

    def _paint_pages(self, result: memtest.Result) -> None:
        fact = self.facts["pages"]
        fact.setVisible(result.huge_fraction is not None and bool(result.ram_block))
        if fact.isVisibleTo(self.facts_row):
            fact.show_fact(render.whole_percent(result.huge_fraction * 100),
                           _("memtest.fact.pages.detail").format(
                               block=render.size(result.ram_block)))

    def _paint_rates(self, result: memtest.Result) -> None:
        self._paint_share(result)
        threads = max((r.threads for r in result.rates), default=1)
        rows = []
        for operation, non_temporal, key in RATE_ROWS:
            one = result.rate(operation, 1, non_temporal)
            every = result.rate(operation, threads, non_temporal) if threads > 1 else None
            if one is None and every is None:
                continue
            rows.append((_(key),
                         render.bandwidth(one.bytes_per_second, 1) if one else render.DASH,
                         render.bandwidth(every.bytes_per_second, 1) if every else render.DASH))
        self.rates_table.set_rows(rows)
        self.rates_table.setVisible(bool(rows))

        one, every = result.rate("read", 1), result.rate("read", threads) if threads > 1 else None
        lower = one is not None and every is not None \
            and every.bytes_per_second < one.bytes_per_second
        self.threads_note.setText(_("memtest.threads.lower").format(
            every=render.bandwidth(every.bytes_per_second, 1),
            one=render.bandwidth(one.bytes_per_second, 1)) if lower else "")
        self.threads_note.setVisible(lower)

    def _paint_share(self, result: memtest.Result) -> None:
        share = memtest.share_of_theoretical(result)
        locked = False
        if share is not None:
            read = result.rate("read")
            self.share_value.setText(render.whole_percent(share))
            self.share.setText(_("memtest.share").format(
                mts=render.memory_speed(result.speed_mts),
                rate=unbroken(render.bandwidth(read.bytes_per_second, 1)),
                threads=render.counted("memtest.threads", read.threads),
                channels=render.counted("memtest.channels", result.channels or 0),
                total=unbroken(render.bandwidth(result.theoretical_bytes_per_second, 1))))
            if share > 100:
                self._note(Notice(_("memtest.notice.over"), _("memtest.notice.over.body")))
        elif result.rates and self._channels_locked:
            # Rule 5: missing for want of permissions, with its padlock and
            # the way to give them.
            locked = True
            self.share.setText(_("memtest.share.locked"))
            self.share_button.setText(_("perm.replace.button" if self._helper_outdated
                                        else "perm.button.read"))
        else:
            self.share.setText(_("memtest.share.unknown") if result.rates else "")
        self.share_value.setVisible(share is not None)
        self.share.setVisible(bool(self.share.text()))
        self.facts["share"].setVisible(bool(self.share.text()))
        self.share.ensurePolished()
        self._lock_column.setContentsMargins(
            0, max(0, (self.share.fontMetrics().height() - self.share_lock.height()) // 2), 0, 0)
        self.share_lock.setVisible(locked)
        self.share_button.setVisible(locked)

    def _method(self, result: memtest.Result) -> str:
        if result.engine == "simple":
            return _("memtest.method.simple")
        sentences = []
        if result.ram_block:
            key = "memtest.method.limited" if result.ram_block_limited else "memtest.method.ram"
            sentences.append(_(key).format(block=render.size(result.ram_block)))
        else:
            sentences.append(_("memtest.method.noram"))
        if result.huge_fraction is not None:
            sentences.append(_("memtest.method.pages").format(
                pct=f"{result.huge_fraction * 100:.0f}"))
        if result.cpu is not None:
            sentences.append(_("memtest.method.cpu").format(cpu=result.cpu))
        source = {"cycles": "memtest.method.cycles", "cpufreq": "memtest.method.cpufreq"}.get(
            result.frequency_source, "memtest.method.nofrequency")
        sentences.append(_(source))
        return " ".join(sentences)

    def _toggle_detail(self, shown: bool) -> None:
        self.detail.setVisible(shown)
        self.detail_button.setText(_("memtest.detail.hide" if shown else "memtest.detail.show"))

    def _paint_history(self, results) -> None:
        # Whose read it is, in the header: the line above the table gives
        # one thread's.
        threads = max((r.threads for result in results[:1] for r in result.rates), default=0)
        self.history.set_header(2, render.counted("memtest.col.read.threads", threads)
                                if threads else _("memtest.col.read.all"))
        rows = []
        for result in results:
            threads = max((r.threads for r in result.rates), default=1)
            ram, read = result.level("RAM"), result.rate("read", threads)
            share = memtest.share_of_theoretical(result)
            frequencies = [p.frequency_hz for p in result.points if p.frequency_hz]
            rows.append((
                when(result.timestamp),
                render.nanoseconds(ram.nanoseconds) if ram else render.DASH,
                render.bandwidth(read.bytes_per_second, 1) if read else render.DASH,
                render.whole_percent(share),
                render.hz(max(frequencies)) if frequencies else render.DASH))
        self.history.set_rows(rows)
        self.history_card.setVisible(bool(rows))

    def _clear_history(self) -> None:
        from PySide6.QtWidgets import QMessageBox

        if QMessageBox.question(
                self, _("bench.button.clear"), _("memtest.dialog.clear"),
                QMessageBox.StandardButton.Cancel | QMessageBox.StandardButton.Yes,
                QMessageBox.StandardButton.Cancel) != QMessageBox.StandardButton.Yes:
            return
        memtest.clear_history()
        self._paint_history([])

    # -- the window's protocol -----------------------------------------------

    def apply(self, snapshot) -> None:
        """Nothing here follows the sampling: only which cores and which
        memory the next test will be measured against, and whether the
        channels wait for permissions."""
        self._types = tuple(snapshot.cpu.types)
        name = render.cpu_short_name(self._types[0].brand) if self._types else ""
        self.cpu_name.setText(name)
        self.cpu_name.setVisible(bool(name))
        parts = render.memory_theoretical_parts(snapshot.modules)
        self._memory = memtest.Memory(
            render.memory_theoretical_bandwidth(snapshot.modules), *(parts or (None, None)))
        state = snapshot.privileged
        # As Memory's card: without the modules, it's the permissions when
        # there is a helper to ask and we aren't root already.
        locked = not snapshot.modules and state.supported and not state.already_root
        outdated = bool(state.outdated)
        uptime = snapshot.system.uptime_seconds
        self._booted_at = time.time() - uptime if uptime else None
        changed = (locked, outdated) != (self._channels_locked, self._helper_outdated)
        self._channels_locked, self._helper_outdated = locked, outdated
        if self.result is None:
            return
        # Permissions just given: this boot's tests get their share.
        history = memtest.fill_history(self._memory, self._booted_at)
        if history is not None:
            self._paint_history(history)
        filled = memtest.with_memory(self.result, self._memory, self._booted_at)
        if filled is not self.result:
            self.show_result(filled)
            self.measured.emit(filled)
        elif changed:
            self.show_result(self.result)

    def stop(self) -> None:
        self._run.cancel()
