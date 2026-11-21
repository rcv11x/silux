"""What the report will say, shown before it is saved.

People are asked to send their report, and they should see what goes in it
first: every page as the window shows it, without the machine's name,
addresses or serial numbers. When some data needs administrator rights, the
dialog says how many are missing and asks for them right there; when they
arrive, the window refreshes the text (rule 9).

The saved file ends with the annex (`annex.py`): this machine's dump, made in
another process while the dialog is open. The preview says how big it is and
that it goes in, not its two hundred kilobytes.
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from .. import annex
from ..i18n import _
from . import theme
from .background import BackgroundCommand, CommandResult


def github_breaks(markdown: str) -> str:
    """Each line on its own, as GitHub shows a comment, where the report is
    pasted: plain Markdown would join the lines of a card into a paragraph."""
    lines = markdown.split("\n")
    for n, line in enumerate(lines[:-1]):
        following = lines[n + 1]
        if (line.strip() and following.strip()
                and not line.lstrip().startswith(("|", "#"))
                and not following.lstrip().startswith("|")):
            lines[n] = line + "  "
    return "\n".join(lines)


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

        # Formatted, as it reads once pasted in an issue; the file keeps the
        # Markdown exactly as it is (`report`).
        self.text = QTextBrowser()
        self.text.setOpenLinks(False)
        layout.addWidget(self.text, 1)
        self._report = ""
        self._annex_job: Optional[BackgroundCommand] = None
        # The block and why there is none; both None while it is made.
        self._annex: tuple[Optional[str], Optional[str]] = (None, None)

        self.save_button = QPushButton(_("report.preview.save"))
        self.save_button.setDefault(True)
        self.save_button.clicked.connect(self.save_requested.emit)
        close = QPushButton(_("perm.explain.close"))
        close.clicked.connect(self.close)
        # Where it shows whatever the reader is scrolled to: «Guardar…» waits
        # for the annex, and a disabled button says nothing about why.
        self.annex_status = QLabel()
        self.annex_status.setObjectName("Muted")
        buttons = QHBoxLayout()
        buttons.addWidget(self.annex_status)
        buttons.addStretch(1)
        buttons.addWidget(close)
        buttons.addWidget(self.save_button)
        layout.addLayout(buttons)
        self.resize(900, 700)

    def set_report(self, text: str, missing: int) -> None:
        """Show this report; `missing` is how many data need permissions."""
        self._report = text
        self._show()
        self.missing.setText(_("report.preview.missing").format(n=missing) if missing else "")
        self.missing.setVisible(bool(missing))
        self.grant_button.setVisible(bool(missing))

    def _show(self) -> None:
        # It is rebuilt when permissions arrive: the reader stays where they were.
        bar = self.text.verticalScrollBar()
        position = bar.value()
        self.text.setMarkdown(github_breaks(
            self._report.rstrip("\n") + "\n" + annex.section(*self._annex, preview=True)))
        bar.setValue(position)
        self.save_button.setEnabled(not self.annex_pending())
        block, reason = self._annex
        self.annex_status.setText(
            _("report.annex.preparing") if self.annex_pending()
            else _("report.annex.status").format(summary=annex.summary_of(block)) if block
            else _("report.annex.status.none"))

    def annex_pending(self) -> bool:
        return self._annex == (None, None)

    def start_annex(self) -> None:
        """Make this machine's annex again, unless it is being made."""
        if self._annex_job is not None:
            return
        self._annex = (None, None)
        self._annex_job = BackgroundCommand(annex.command(), timeout=annex.TIMEOUT_S, parent=self,
                                            env=annex.child_environment())
        self._annex_job.done.connect(self._annex_done)
        self._annex_job.start()
        self._show()

    def _annex_done(self, result: CommandResult) -> None:
        job, self._annex_job = self._annex_job, None
        if job is not None:
            job.wait()
            job.deleteLater()
        self._annex = ((None, result.error) if result.error is not None
                       else annex.outcome(result.returncode, result.stdout, result.stderr))
        self._show()

    def cancel_annex(self) -> None:
        """For when the window closes: a running QThread cannot be destroyed."""
        job, self._annex_job = self._annex_job, None
        if job is not None:
            job.done.disconnect(self._annex_done)
            job.cancel()

    def report(self) -> str:
        """What is saved: the report, and the annex once it is made."""
        if self.annex_pending():
            return self._report
        return self._report.rstrip("\n") + "\n" + annex.section(*self._annex)
