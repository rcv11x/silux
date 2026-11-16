"""Los diálogos de la ventana que no son de una sola página."""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QDialog, QHBoxLayout, QLabel, QPushButton,
                               QVBoxLayout, QWidget)

from ..i18n import _
from . import theme

# Los cuatro párrafos, en este orden: qué lee, qué pasa si se dan esta vez,
# qué pasa si se dan para siempre y quién pide la contraseña.
PARRAFOS = ("perm.explain.reads", "perm.explain.once", "perm.explain.always",
            "perm.explain.polkit")


class PermissionsDialog(QDialog):
    """«Qué hace esto»: lo que pasa al dar permisos, antes de darlos.

    El botón pide la contraseña de administrador, y eso no se le da a un
    programa que no dice para qué la quiere. Aquí lo dice: qué lee el
    ayudante, que solo lee, cuánto dura y que la contraseña no pasa por silux.
    """

    grant_requested = Signal()
    permanent_requested = Signal()

    def __init__(self, permanente: bool = True, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setWindowTitle(_("perm.explain.title"))
        self.setModal(True)
        m = theme.METRICS

        layout = QVBoxLayout(self)
        layout.setContentsMargins(m.page_margin + 6, m.page_margin + 4,
                                  m.page_margin + 6, m.page_margin + 2)
        layout.setSpacing(m.card_gap + 4)

        titulo = QLabel(_("perm.explain.title"))
        titulo.setObjectName("Headline")
        layout.addWidget(titulo)

        self.paragraphs: list[QLabel] = []
        for clave in PARRAFOS:
            parrafo = QLabel(_(clave))
            parrafo.setWordWrap(True)
            parrafo.setTextFormat(Qt.TextFormat.PlainText)
            parrafo.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            layout.addWidget(parrafo)
            self.paragraphs.append(parrafo)

        self.grant_button = QPushButton(_("perm.explain.grant"))
        self.grant_button.setObjectName("Primary")
        self.grant_button.setDefault(True)
        self.grant_button.clicked.connect(self._dar)
        # Con los puntos suspensivos: abre otro diálogo, el de polkit, y no
        # es lo mismo que el de al lado.
        self.permanent_button = QPushButton(_("perm.explain.permanent"))
        self.permanent_button.clicked.connect(self._para_siempre)
        # Si el ayudante ya está instalado, «para siempre» ya está hecho.
        self.permanent_button.setVisible(permanente)
        self.close_button = QPushButton(_("perm.explain.close"))
        self.close_button.setObjectName("TextButton")
        self.close_button.setFlat(True)
        self.close_button.clicked.connect(self.reject)

        botones = QHBoxLayout()
        botones.setContentsMargins(0, 6, 0, 0)
        botones.addWidget(self.grant_button)
        botones.addWidget(self.permanent_button)
        botones.addStretch(1)
        botones.addWidget(self.close_button)
        layout.addLayout(botones)

        self.setMinimumWidth(m.base_pt * 40)
        self.setMaximumWidth(m.base_pt * 52)

    def _dar(self) -> None:
        self.accept()
        self.grant_requested.emit()

    def _para_siempre(self) -> None:
        self.accept()
        self.permanent_requested.emit()
