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

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
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
    Notice,
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
# Points measured this far below the fastest ran with the clock down, and
# their nanoseconds read high for it.
CLOCK_DROP = 0.97


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
        left = 10 + max(metrics.horizontalAdvance(render.nanoseconds(10 ** decade))
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
                             render.nanoseconds(10 ** decade))
        for name, size in self._caches:
            position = math.log2(size)
            if not x0 <= position <= x1:
                continue
            x = at(position, y0).x()
            painter.setPen(QPen(muted, 1, Qt.PenStyle.DashLine))
            painter.drawLine(QPointF(x, area.top()), QPointF(x, area.bottom()))
            painter.setPen(muted)
            label = f"{name} · {render.size(size)}"
            # Where the curve isn't: it only rises, so above it on the left
            # and under it once it has climbed past the middle.
            nearest = min(range(len(sizes)), key=lambda i: abs(sizes[i] - position))
            high = at(position, times[nearest]).y() < area.center().y()
            baseline = area.bottom() - metrics.descent() - 2 if high else area.top() + metrics.ascent()
            painter.drawText(QPointF(min(x + 4, area.right() - metrics.horizontalAdvance(label)),
                                     baseline), label)
        for edge, size in ((Qt.AlignmentFlag.AlignLeft, self._points[0].bytes_),
                           (Qt.AlignmentFlag.AlignRight, self._points[-1].bytes_)):
            painter.drawText(QRectF(area.left(), area.bottom() + 4, area.width(),
                                    metrics.height()), edge, render.size(size))
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


class MemoryTestTab(ScrollPage):
    _finished = Signal(object)
    _progressed = Signal(str, float)
    # Whether a test is under way: the other tabs wait for it.
    running_changed = Signal(bool)
    # A test just measured, for the pages that show part of it.
    measured = Signal(object)

    def __init__(self, palette: Palette, prefs: Preferences, parent=None):
        super().__init__(parent)
        self._p = palette
        self._prefs = prefs
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._types: tuple = ()
        self._memory = memtest.Memory()
        self.result: Optional[memtest.Result] = None
        m = theme.METRICS

        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        root = QWidget()
        root.setObjectName("Root")
        self.setWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(m.page_margin, m.page_margin, m.page_margin, m.page_margin)
        layout.setSpacing(m.section_gap)

        layout.addWidget(self._build_header())
        self._notices = QVBoxLayout()
        self._notices.setSpacing(6)
        layout.addLayout(self._notices)
        self.result_card = self._build_result()
        layout.addWidget(self.result_card)
        self.history_card = self._build_history()
        layout.addWidget(self.history_card)
        layout.addStretch(1)

        self._finished.connect(self._on_finished)
        self._progressed.connect(self._on_progress)
        history = memtest.load_history()
        self._paint_history(history)
        if history:
            self.show_result(history[0])

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
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setTextVisible(True)
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
        card.body.addWidget(self.share)

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
        return self._thread is not None and self._thread.is_alive()

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
        self._stop.clear()
        self.run_button.setEnabled(False)
        self.cancel_button.setEnabled(True)
        self.cancel_button.show()
        self.progress.setValue(0)
        self.progress.setFormat(_("bench.state.preparing"))
        self.progress.show()
        clear_layout(self._notices)
        plan, memory = self.plan(), self._memory

        def work() -> None:
            self._finished.emit(memtest.run(
                plan, lambda phase, done: self._progressed.emit(phase, done),
                self._stop, memory))

        self._thread = threading.Thread(target=work, daemon=True)
        self._thread.start()
        self.running_changed.emit(True)

    def _cancel(self) -> None:
        self._stop.set()
        self.cancel_button.setEnabled(False)
        self.progress.setFormat(_("bench.state.cancelling"))

    def _on_progress(self, phase: str, done: float) -> None:
        self.progress.setValue(int(done * 100))
        self.progress.setFormat(f"{_(PHASES.get(phase, 'memtest.phase.latency'))}  ·  %p %")

    def _on_finished(self, result: memtest.Result) -> None:
        self._thread = None
        self.run_button.setEnabled(True)
        self.cancel_button.hide()
        self.progress.hide()
        self.running_changed.emit(False)
        if not result.measured:
            if result.reason != "cancelled":
                self._notices.addWidget(Notice(
                    _("memtest.notice.failed"),
                    _(REASONS.get(result.reason, "memtest.reason.failed"))))
            return
        self._paint_history(memtest.append_history(result))
        self.show_result(result)
        self.measured.emit(result)

    # -- painting ------------------------------------------------------------

    def show_result(self, result: memtest.Result) -> None:
        self.result = result
        clear_layout(self._notices)
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
        if frequencies and min(frequencies) < max(frequencies) * CLOCK_DROP:
            self._notices.addWidget(Notice(
                _("memtest.notice.clock"), _("memtest.notice.clock.body").format(
                    low=render.hz(min(frequencies)), high=render.hz(max(frequencies)))))
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
        best = [(key, result.rate(operation)) for operation, key in
                (("read", "memtest.op.read"), ("write", "memtest.op.write"),
                 ("copy", "memtest.op.copy"))]
        self.rates.setText("  ·  ".join(
            f"{_(key)} {render.bandwidth(rate.bytes_per_second, 1)}"
            for key, rate in best if rate is not None))
        self.rates.setVisible(bool(result.rates))

        share = memtest.share_of_theoretical(result)
        self.share_bar.setVisible(share is not None)
        if share is not None:
            self.share_bar.setValue(int(min(share, 100)))
            self.share.setText(_("memtest.share").format(
                pct=f"{share:.0f}", mts=result.speed_mts,
                channels=render.counted("memtest.channels", result.channels or 0),
                total=render.bandwidth(result.theoretical_bytes_per_second, 1)))
            if share > 100:
                self._notices.addWidget(Notice(_("memtest.notice.over"),
                                               _("memtest.notice.over.body")))
        else:
            self.share.setText(_("memtest.share.unknown") if result.rates else "")
        self.share.setVisible(bool(self.share.text()))

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
                render.DASH if share is None else f"{share:.0f} %",
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
        memory the next test will be measured against."""
        self._types = tuple(snapshot.cpu.types)
        parts = render.memory_theoretical_parts(snapshot.modules)
        self._memory = memtest.Memory(
            render.memory_theoretical_bandwidth(snapshot.modules), *(parts or (None, None)))

    def stop(self) -> None:
        self._stop.set()
