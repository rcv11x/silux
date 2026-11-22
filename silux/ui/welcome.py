"""The first time Silux opens: how to see it, the menu entry and permissions.

Two screens and a button to skip them. What the system already says comes
chosen: its language, and the desktop's theme. Each choice goes through the
same path as Settings, so the window behind changes as it is picked. Nothing
is written to the system unless the menu switch is turned on and «Start»
pressed; and permissions are only explained, never asked for.
"""

from __future__ import annotations

import dataclasses
from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QFontMetrics, QGuiApplication
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .. import desktop, i18n
from ..i18n import _
from ..settings import Preferences
from . import theme
from .pages.settings import FONT_SCALES, THEMES, Interruptor
from .theme import Palette, ui_font
from .widgets import clear_layout


def rounded_corners() -> bool:
    """Whether the dialog can draw its own rounded corners. That needs a
    compositor, which Wayland always has and X11 may not: without one the
    corners come out black, so there the window manager frames it."""
    return QGuiApplication.platformName() in ("wayland", "offscreen")


def can_add_to_menu() -> bool:
    """Whether this copy can put itself in the applications menu, and isn't
    there yet."""
    launcher = desktop.current_launcher()
    return bool(launcher.command) and not desktop.in_menu(launcher.app_id)


class _Screens(QWidget):
    """One screen at a time, as tall as the one on show: a QStackedWidget
    measures its height with all of them."""

    def __init__(self):
        super().__init__()
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._screens: list[QWidget] = []
        self._current = 0

    def addWidget(self, screen: QWidget) -> None:  # noqa: N802
        screen.setVisible(not self._screens)
        self._screens.append(screen)
        self._layout.addWidget(screen)

    def setCurrentIndex(self, index: int) -> None:  # noqa: N802
        self._current = index
        # Hidden first: showing one lays out the window at once, and with
        # two on show its minimum height would be both.
        for number, screen in enumerate(self._screens):
            if number != index:
                screen.hide()
        self._screens[index].show()
        # Until the next turn of the event loop, the heights cached are the
        # ones from before.
        self._layout.invalidate()
        self.updateGeometry()

    def currentIndex(self) -> int:  # noqa: N802
        return self._current


class WelcomeDialog(QDialog):
    changed = Signal(object)           # Preferences, as they are picked

    def __init__(self, prefs: Preferences, palette: Palette,
                 parent: Optional[QWidget] = None, page: int = 0):
        super().__init__(parent)
        self.setModal(True)
        self.setObjectName("Welcome")
        self._prefs = prefs
        self._p = palette
        self._page = page
        self._menu_offered = can_add_to_menu()
        # Whether «Start» was pressed with the menu switch on.
        self.menu_wanted = False
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        panel = QFrame()
        panel.setObjectName("WelcomePanel")
        if rounded_corners():
            self.setWindowFlag(Qt.WindowType.FramelessWindowHint, True)
            self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
            panel.setProperty("rounded", True)
        outer.addWidget(panel)
        self._root = QVBoxLayout(panel)
        self._build()

    def rebuild(self, prefs: Preferences, palette: Palette) -> None:
        """Again, in the language and the theme just picked."""
        self._prefs, self._p = prefs, palette
        self._page = self.pages.currentIndex()
        menu_on = self.menu_switch.isChecked() if self.menu_switch is not None else False
        self._build()
        if self.menu_switch is not None:
            self.menu_switch.setChecked(menu_on)

    # -- building -----------------------------------------------------------

    def _build(self) -> None:
        clear_layout(self._root)
        m = theme.METRICS
        self.setWindowTitle(_("welcome.window"))
        self._root.setContentsMargins(m.page_margin + 8, m.page_margin + 6,
                                      m.page_margin + 8, m.page_margin + 4)
        self.setMinimumWidth(QFontMetrics(ui_font(m.base_pt)).horizontalAdvance("M") * 34)
        self.pages = _Screens()
        self.pages.addWidget(self._first())
        self.pages.addWidget(self._second())
        self._root.addWidget(self.pages)
        self._go(self._page)

    def _title(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("Headline")
        label.setWordWrap(True)
        return label

    def _paragraph(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setWordWrap(True)
        label.setObjectName("Muted")
        label.setFont(ui_font(theme.METRICS.base_pt))
        return label

    def _buttons(self, left: tuple[str, object], right: tuple[str, object]) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setContentsMargins(0, theme.METRICS.card_gap, 0, 0)
        back = QPushButton(left[0])
        back.clicked.connect(left[1])
        forward = QPushButton(right[0])
        forward.setObjectName("Primary")
        forward.setDefault(True)
        forward.clicked.connect(right[1])
        row.addWidget(back)
        row.addStretch(1)
        row.addWidget(forward)
        self._last_buttons = (back, forward)
        return row

    def _combo(self, options, current: str) -> QComboBox:
        box = QComboBox()
        box.setFont(ui_font(theme.METRICS.base_pt))
        for label, value in options:
            box.addItem(label, value)
        box.setCurrentIndex(max(0, box.findData(current)))
        box.currentIndexChanged.connect(self._pick)
        return box

    def _first(self) -> QWidget:
        m = theme.METRICS
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(m.card_gap + 4)
        layout.addWidget(self._title(_("welcome.title")))

        dark = theme.system_prefers_dark(QApplication.instance())
        system = (f'{_("opt.theme.system")} '
                  f'({_("welcome.theme.dark" if dark else "welcome.theme.light")})')
        themes = [(system if value == "system" else _(key), value) for key, value in THEMES]
        self.language_box = self._combo(list((name, code) for code, name
                                             in i18n.available().items()),
                                        self._prefs.language)
        self.theme_box = self._combo(themes, self._prefs.theme)
        self.font_box = self._combo([(_(key), value) for key, value in FONT_SCALES],
                                    self._prefs.font_scale)
        grid = QGridLayout()
        grid.setHorizontalSpacing(24)
        grid.setVerticalSpacing(m.card_gap)
        for row, (key, box) in enumerate((("welcome.language", self.language_box),
                                          ("welcome.theme", self.theme_box),
                                          ("welcome.font", self.font_box))):
            name = QLabel(_(key))
            name.setFont(ui_font(m.base_pt))
            grid.addWidget(name, row, 0)
            grid.addWidget(box, row, 1)
        grid.setColumnStretch(1, 1)
        layout.addLayout(grid)
        layout.addWidget(self._paragraph(_("welcome.later")))
        layout.addStretch(1)
        layout.addLayout(self._buttons((_("welcome.skip"), self.reject),
                                       (_("welcome.next"), lambda: self._go(1))))
        self.skip_button, self.next_button = self._last_buttons
        return page

    def _second(self) -> QWidget:
        m = theme.METRICS
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(m.card_gap + 4)
        layout.addWidget(self._title(_("welcome.before.title")))

        self.menu_switch: Optional[Interruptor] = None
        if self._menu_offered:
            row = QHBoxLayout()
            texts = QVBoxLayout()
            texts.setSpacing(2)
            name = QLabel(_("welcome.menu"))
            name.setFont(ui_font(m.base_pt))
            texts.addWidget(name)
            texts.addWidget(self._paragraph(_("welcome.menu.help")))
            row.addLayout(texts, 1)
            self.menu_switch = Interruptor(self._p)
            row.addWidget(self.menu_switch, 0, Qt.AlignmentFlag.AlignVCenter)
            layout.addLayout(row)

        permissions = QLabel(_("welcome.permissions.title"))
        permissions.setFont(ui_font(m.base_pt, QFont.Weight.DemiBold))
        layout.addWidget(permissions)
        layout.addWidget(self._paragraph(_("welcome.permissions")))
        layout.addStretch(1)
        layout.addLayout(self._buttons((_("welcome.back"), lambda: self._go(0)),
                                       (_("welcome.start"), self._start)))
        self.back_button, self.start_button = self._last_buttons
        return page

    # -- what the user does -------------------------------------------------

    def _go(self, page: int) -> None:
        """To that screen, the dialog as tall as what it holds."""
        self.pages.setCurrentIndex(page)
        layout = self.layout()
        layout.activate()
        width = max(self.width() if self.isVisible() else self.sizeHint().width(),
                    self.minimumWidth())
        self.resize(width, layout.totalHeightForWidth(width))

    def _pick(self, *_args) -> None:
        prefs = dataclasses.replace(
            self._prefs, language=self.language_box.currentData(),
            theme=self.theme_box.currentData(),
            font_scale=self.font_box.currentData()).normalized()
        if prefs != self._prefs:
            self._prefs = prefs
            self.changed.emit(prefs)

    def _start(self) -> None:
        self.menu_wanted = self.menu_switch is not None and self.menu_switch.isChecked()
        self.accept()
