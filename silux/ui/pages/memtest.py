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
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ... import memtest, render
from ...i18n import _
from ...settings import Preferences
from .. import theme
from ..theme import Palette, ui_font
from ..widgets import (
    Card,
    FoldingRow,
    LockMark,
    Notice,
    ProgressLine,
    ReadableRoot,
    ResponsiveRow,
    ScrollPage,
    Table,
    clear_layout,
    value_font,
)

LEVELS = ("L1", "L2", "L3", "RAM")
PHASES = {"latency": "memtest.phase.latency", "read": "memtest.phase.read",
          "write": "memtest.phase.write", "copy": "memtest.phase.copy",
          "write_nt": "memtest.phase.write", "copy_nt": "memtest.phase.copy"}
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
        self.setMinimumHeight(220)

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


class LevelTile(Card):
    """One level's latency, with what it is in cycles and the clock it ran at."""

    def __init__(self, name: str):
        super().__init__()
        self.name = QLabel(name)
        self.name.setObjectName("FieldName")
        self.value = QLabel("")
        self.value.setObjectName("Headline")
        self.value.setFont(ui_font(theme.METRICS.headline_px))
        self.detail = QLabel("")
        self.detail.setObjectName("Muted")
        self.detail.setWordWrap(True)
        for widget in (self.name, self.value, self.detail):
            self.body.addWidget(widget)

    def show_level(self, level: memtest.Level) -> None:
        self.value.setText(render.nanoseconds(level.nanoseconds))
        cycles = render.core_cycles(level.nanoseconds, level.frequency_hz)
        self.detail.setText("" if cycles is None else _("memtest.tile.cycles").format(
            n=f"{cycles:.1f}", freq=render.hz(level.frequency_hz)))
        self.detail.setVisible(cycles is not None)


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
        # The last step reported, for a tab that arrives half way.
        self.last: tuple[str, float] = ("", 0.0)
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
        root = ReadableRoot()
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
        for widget in (title, self.intro, buttons, self.progress):
            card.body.addWidget(widget)
        return card

    def _build_result(self) -> Card:
        card = Card(_("memtest.card.result"))
        self.conditions = QLabel("")
        self.conditions.setObjectName("Muted")
        self.conditions.setWordWrap(True)
        card.body.addWidget(self.conditions)

        self.tiles = {name: LevelTile(name) for name in LEVELS}
        row = ResponsiveRow(min_item_width=130)
        for tile in self.tiles.values():
            row.add(tile)
        self.tiles_row = row
        card.body.addWidget(row)

        self.verdict = QLabel("")
        self.verdict.setWordWrap(True)
        card.body.addWidget(self.verdict)

        self.rates = QLabel("")
        self.rates.setWordWrap(True)
        self.rates.setFont(value_font())
        card.body.addWidget(self.rates)
        self.share_bar = QProgressBar()
        self.share_bar.setRange(0, 100)
        self.share_bar.setTextVisible(False)
        self.share_bar.setFixedHeight(8)
        card.body.addWidget(self.share_bar)
        self.share = QLabel("")
        self.share.setObjectName("Muted")
        self.share.setWordWrap(True)
        self.share.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        self.share_lock = LockMark(self._p.info, theme.METRICS.small_pt + 3)
        self.share_lock.hacer_pulsable()
        self.share_lock.clicked.connect(self.elevation_requested)
        self.share_button = QPushButton("")
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
        share_row.addWidget(self.share, 1)
        share_row.addWidget(self.share_button, 0, Qt.AlignmentFlag.AlignTop)
        card.body.addLayout(share_row)

        self.detail_button = QPushButton(_("memtest.detail.show"))
        self.detail_button.setObjectName("GhostButton")
        self.detail_button.setCheckable(True)
        self.detail_button.toggled.connect(self._toggle_detail)
        fold = QHBoxLayout()
        fold.addWidget(self.detail_button)
        fold.addStretch(1)
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
            [_("memtest.col.date"), _("memtest.col.ram"), _("memtest.col.read"),
             _("memtest.col.share"), _("memtest.col.frequency")],
            numeric=(False, True, True, True, True))
        card.body.addWidget(self.history)
        self.clear_button = QPushButton(_("bench.button.clear"))
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

    def _on_progress(self, phase: str, done: float) -> None:
        if self._run.cancelling:
            return
        self.progress.set_state(_(PHASES.get(phase, "memtest.phase.latency")), done)

    def _drop_failure(self) -> None:
        if self._failure is not None:
            self._failure.setParent(None)
            self._failure.deleteLater()
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
        clear_layout(self._notices)
        self._failure = None
        frequencies = [p.frequency_hz for p in result.points if p.frequency_hz]
        parts = [when(result.timestamp)]
        if result.governor:
            parts.append(result.governor)
        if frequencies:
            parts.append(_("memtest.conditions.at").format(freq=render.hz(max(frequencies))))
        self.conditions.setText(" · ".join(parts))

        for name, tile in self.tiles.items():
            level = result.level(name)
            tile.setVisible(level is not None)
            if level is not None:
                tile.show_level(level)
        self.tiles_row.setVisible(bool(result.levels))

        self._paint_verdict(result)
        self._paint_rates(result)
        self.chart.set_curve(result.points, result.caches)
        self.chart.setVisible(len(result.points) > 1)
        self.method.setText(self._method(result))
        self.result_card.show()

        if result.engine == "simple":
            self._notices.addWidget(Notice(_("memtest.notice.simple"),
                                           _("memtest.notice.simple.body"), tone="info"))
        clock = memtest.clock_change(result)
        if clock is not None:
            low, high = clock
            self._notices.addWidget(Notice(
                _("memtest.notice.clock").format(
                    percent=render.whole_percent((high - low) / high * 100)),
                _("memtest.notice.clock.body").format(low=render.hz(low), high=render.hz(high))))
        noisy = sum(1 for p in result.points if p.noisy) + sum(1 for r in result.rates if r.noisy)
        if noisy:
            self._notices.addWidget(Notice(
                _("memtest.notice.noisy"), render.counted("memtest.notice.noisy.body", noisy)))

    def _paint_verdict(self, result: memtest.Result) -> None:
        steps = memtest.curve_steps(result.points, result.levels, result.caches)
        wrong = next((s for s in steps if not s.matches), None)
        if wrong is not None:
            text = _("memtest.verdict.differs").format(
                level=wrong.level, flat=render.size(wrong.flat_until),
                rises=render.size(wrong.rises_by), declared=render.size(wrong.declared_bytes))
            if result.huge_fraction is not None and result.huge_fraction < 0.9:
                text += " " + _("memtest.verdict.smallpages")
        elif steps:
            text = _("memtest.verdict.matches").format(sizes=", ".join(
                f"{s.level} {render.size(s.declared_bytes)}" for s in steps))
        else:
            text = ""
        self.verdict.setText(text)
        self.verdict.setProperty("tone", "no" if wrong is not None else "")
        self.verdict.setVisible(bool(text))

    def _paint_rates(self, result: memtest.Result) -> None:
        one_thread = [(key, result.rate(operation, 1)) for operation, key in
                      (("read", "memtest.op.read"), ("write", "memtest.op.write"),
                       ("copy", "memtest.op.copy"))]
        rates = "  ·  ".join(f"{_(key)} {render.bandwidth(rate.bytes_per_second, 1)}"
                             for key, rate in one_thread if rate is not None)
        self.rates.setText(_("memtest.rates.one").format(rates=rates) if rates else "")
        self.rates.setVisible(bool(rates))
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
        self.share_bar.setVisible(share is not None)
        locked = False
        if share is not None:
            read = result.rate("read")
            self.share_bar.setValue(int(min(share, 100)))
            self.share.setText(_("memtest.share").format(
                pct=f"{share:.0f}", mts=result.speed_mts,
                rate=render.bandwidth(read.bytes_per_second, 1),
                threads=render.counted("memtest.threads", read.threads),
                channels=render.counted("memtest.channels", result.channels or 0),
                total=render.bandwidth(result.theoretical_bytes_per_second, 1)))
            if share > 100:
                self._notices.addWidget(Notice(_("memtest.notice.over"),
                                               _("memtest.notice.over.body")))
        elif result.rates and self._channels_locked:
            # Rule 5: missing for want of permissions, with its padlock and
            # the way to give them.
            locked = True
            self.share.setText(_("memtest.share.locked"))
            self.share_button.setText(_("perm.replace.button" if self._helper_outdated
                                        else "perm.button.read"))
        else:
            self.share.setText(_("memtest.share.unknown") if result.rates else "")
        self.share.setVisible(bool(self.share.text()))
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
        rows = []
        for result in results:
            ram, read = result.level("RAM"), result.rate("read")
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
