"""What the report will say, shown before it is saved.

People are asked to send their report, and they should see what goes in it
first: every page as the window shows it, without the machine's name,
addresses or serial numbers. When some data needs administrator rights, the
dialog says how many are missing and asks for them right there; when they
arrive, the window refreshes the text (rule 9).
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (QDialog, QHBoxLayout, QLabel, QPlainTextEdit, QPushButton,
                               QVBoxLayout, QWidget)

from ..i18n import _
from . import theme
from .theme import value_font


class ReportPreviewDialog(QDialog):
    save_requested = Signal()
    permissions_requested = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(_("report.preview.title"))
        m = theme.METRICS
        layout = QVBoxLayout(self)
        layout.setContentsMargins(m.page_margin, m.page_margin, m.page_margin, m.page_margin)
        layout.setSpacing(m.card_gap)

        intro = QLabel(_("report.preview.intro"))
        intro.setWordWrap(True)
        layout.addWidget(intro)

        self.missing = QLabel()
        self.missing.setObjectName("Muted")
        self.missing.setWordWrap(True)
        self.grant_button = QPushButton(_("perm.button.read"))
        self.grant_button.setObjectName("GhostButton")
        self.grant_button.clicked.connect(self.permissions_requested.emit)
        missing_row = QHBoxLayout()
        missing_row.addWidget(self.missing, 1)
        missing_row.addWidget(self.grant_button)
        layout.addLayout(missing_row)

        # Plain text, exactly what the file will hold.
        self.text = QPlainTextEdit()
        self.text.setReadOnly(True)
        self.text.setFont(value_font())
        layout.addWidget(self.text, 1)

        self.save_button = QPushButton(_("report.preview.save"))
        self.save_button.setDefault(True)
        self.save_button.clicked.connect(self.save_requested.emit)
        close = QPushButton(_("perm.explain.close"))
        close.clicked.connect(self.close)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        buttons.addWidget(close)
        buttons.addWidget(self.save_button)
        layout.addLayout(buttons)
        self.resize(900, 700)

    def set_report(self, text: str, missing: int) -> None:
        """Show this report; `missing` is how many data need permissions."""
        self.text.setPlainText(text)
        self.missing.setText(_("report.preview.missing").format(n=missing) if missing else "")
        self.missing.setVisible(bool(missing))
        self.grant_button.setVisible(bool(missing))

    def report(self) -> str:
        return self.text.toPlainText()
