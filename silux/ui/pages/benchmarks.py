"""Performance: one tab per test, and one test at a time.

The side menu keeps a single entry however many tests there are. A tab that
doesn't exist yet isn't shown, greyed or announced.
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QHBoxLayout,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from ...i18n import _
from ...settings import Preferences
from .. import theme
from ..theme import Palette, ui_font
from .memtest import MemoryTestRun, MemoryTestTab
from .performance import PerformancePage

# Each tab's key, which `--tab` takes, and its name.
TABS = (("cpu", "bench.tab.cpu"), ("memory", "bench.tab.memory"))


class BenchmarksPage(QWidget):
    # The tab shown changed, by key.
    tab_changed = Signal(str)

    def __init__(self, palette: Palette, prefs: Preferences, parent=None,
                 memory_run: Optional[MemoryTestRun] = None):
        """`memory_run`: the window's memory test, which outlives this page
        when the window rebuilds it."""
        super().__init__(parent)
        self.cpu_tab = PerformancePage(palette, prefs)
        self.memory_tab = MemoryTestTab(palette, prefs, run=memory_run)
        self._tabs = {"cpu": self.cpu_tab, "memory": self.memory_tab}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        bar = QHBoxLayout()
        m = theme.METRICS
        bar.setContentsMargins(m.page_margin, m.page_margin // 2, m.page_margin, 0)
        bar.setSpacing(4)
        self._group = QButtonGroup(self)
        self.buttons: dict[str, QPushButton] = {}
        self.stack = QStackedWidget()
        for key, name in TABS:
            button = QPushButton(_(name))
            button.setObjectName("Tab")
            button.setCheckable(True)
            button.setFont(ui_font(m.base_pt))
            button.clicked.connect(lambda _checked=False, k=key: self.select_tab(k))
            self._group.addButton(button)
            self.buttons[key] = button
            bar.addWidget(button)
            self.stack.addWidget(self._tabs[key])
        bar.addStretch(1)
        layout.addLayout(bar)
        layout.addWidget(self.stack, 1)
        self.buttons["cpu"].setChecked(True)

        # One test at a time: while one runs, the others can't start.
        self.cpu_tab.running_changed.connect(
            lambda running: self.memory_tab.set_blocked(
                _("bench.tab.cpu") if running else None))
        self.memory_tab.running_changed.connect(
            lambda running: self.cpu_tab.set_blocked(
                _("bench.tab.memory") if running else None))
        if self.memory_tab.running:
            self.cpu_tab.set_blocked(_("bench.tab.memory"))

    @property
    def tab(self) -> str:
        return TABS[self.stack.currentIndex()][0]

    def select_tab(self, key: str) -> bool:
        """Show that tab. Starts nothing."""
        key = key.lower()
        if key not in self._tabs:
            return False
        self.buttons[key].setChecked(True)
        if self.stack.currentWidget() is not self._tabs[key]:
            self.stack.setCurrentWidget(self._tabs[key])
            self.tab_changed.emit(key)
        return True

    def running(self) -> Optional[str]:
        """The key of the tab whose test is under way, if any."""
        return next((key for key, tab in self._tabs.items() if tab.running), None)

    def apply(self, snapshot) -> None:
        for tab in self._tabs.values():
            tab.apply(snapshot)

    # The window treats each of its pages as a scroll area. This one's is the
    # tab shown.
    def verticalScrollBar(self):  # noqa: N802
        return self.stack.currentWidget().verticalScrollBar()

    def viewport(self):
        return self.stack.currentWidget().viewport()

    def ensureWidgetVisible(self, *args) -> None:  # noqa: N802
        self.stack.currentWidget().ensureWidgetVisible(*args)

    def stop(self) -> None:
        for tab in self._tabs.values():
            tab.stop()
