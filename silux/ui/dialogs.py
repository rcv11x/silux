"""Los diálogos de la ventana que no son de una sola página."""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from ..i18n import _
from . import theme

# Los cuatro párrafos, en este orden: qué lee, qué pasa si se dan esta vez,
# qué pasa si se dan para siempre y quién pide la contraseña. Cortos: se leen
# justo antes de teclear una contraseña.
PARRAFOS = ("perm.explain.reads", "perm.explain.once", "perm.explain.always",
            "perm.explain.polkit")


def ajustar_tope(dialogo: QDialog) -> None:
    """El ancho máximo: el de leer a gusto, o lo que pida la orden.

    Con un tope más estrecho que la orden, el campo se sale por la
    derecha y los párrafos se quedan sin altura. Se vuelve a calcular
    justo antes de enseñarse, que es cuando Qt decide el tamaño y cuando
    el tema ya ha pasado por los botones.
    """
    pide = dialogo.layout().minimumSize().width()
    # El mínimo también: uno puesto a mano manda sobre el del contenido,
    # y con él más bajo Qt deja el diálogo más estrecho que la orden.
    ancho = max(theme.METRICS.base_pt * 40, pide)
    dialogo.setMinimumWidth(ancho)
    dialogo.setMaximumWidth(max(theme.METRICS.base_pt * 52, pide))
    # Y el alto que piden los párrafos a ese ancho, que es el más
    # estrecho y por tanto el más alto. El mínimo que calcula Qt cuenta
    # cada párrafo como una línea: en Wayland la ventana abría con ese
    # tamaño (573x299 donde hacían falta 425) y salían cortados los
    # párrafos y los botones. Sin pantalla no pasa, y por eso no se veía
    # en las capturas.
    alto = dialogo.layout().totalHeightForWidth(ancho)
    dialogo.setMinimumHeight(alto)
    if dialogo.height() < alto or not dialogo.isVisible():
        dialogo.resize(max(dialogo.width(), ancho), alto)


class PermissionsDialog(QDialog):
    """«Qué hace esto»: lo que pasa al dar permisos, antes de darlos.

    El botón pide la contraseña de administrador, y eso no se le da a un
    programa que no dice para qué la quiere. Aquí lo dice: qué lee el
    ayudante, que solo lee, cuánto dura y que la contraseña no pasa por silux.
    """

    grant_requested = Signal()
    permanent_requested = Signal()

    def __init__(self, permanente: bool = True, concedidos: bool = False,
                 parent: Optional[QWidget] = None):
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
        titulo.setWordWrap(True)
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
        self.grant_button.clicked.connect(self._dar)
        # Sin la regla de polkit, la ventana de la contraseña enseña la orden
        # de `python3` con código dentro, y no se puede cambiar: pkexec elige
        # su texto por la ruta del programa (docs/privilegios.md). Se dice en
        # pequeño debajo de los botones y en el globo del de «esta vez».
        self.window_note = QLabel(_("perm.explain.window"))
        self.window_note.setObjectName("Muted")
        self.window_note.setWordWrap(True)
        self.window_note.setFont(theme.ui_font(theme.METRICS.small_pt))
        self.window_note.setVisible(permanente)
        if permanente:
            self.grant_button.setToolTip(_("perm.explain.window"))
        # Con los permisos ya concedidos, «Dar permisos esta vez» no hace
        # nada: no se ofrece. Se dice que ya están, y queda «para siempre»
        # si el ayudante no está instalado.
        self.grant_button.setVisible(not concedidos)
        self.granted_label = QLabel(_("perm.explain.granted"))
        self.granted_label.setObjectName("FieldName")
        self.granted_label.setVisible(concedidos)
        # Con los puntos suspensivos: abre otro diálogo, el de polkit, y no
        # es lo mismo que el de al lado.
        self.permanent_button = QPushButton(_("perm.explain.permanent"))
        self.permanent_button.clicked.connect(self._para_siempre)
        # Si el ayudante ya está instalado, «para siempre» ya está hecho.
        self.permanent_button.setVisible(permanente)
        # «Para siempre» es la forma recomendada: desde la segunda vez, la
        # ventana de la contraseña dice con nuestras palabras qué se lee. Si
        # ya está hecho, el principal es dar los permisos.
        principal = self.permanent_button if permanente else self.grant_button
        principal.setObjectName("Primary")
        principal.setDefault(True)
        self.close_button = QPushButton(_("perm.explain.close"))
        self.close_button.setObjectName("TextButton")
        self.close_button.setFlat(True)
        self.close_button.clicked.connect(self.reject)

        botones = QHBoxLayout()
        botones.setContentsMargins(0, 6, 0, 0)
        botones.addWidget(self.grant_button)
        botones.addWidget(self.granted_label)
        botones.addWidget(self.permanent_button)
        botones.addStretch(1)
        botones.addWidget(self.close_button)
        layout.addLayout(botones)
        layout.addWidget(self.window_note)

        ajustar_tope(self)

    def setVisible(self, visible: bool) -> None:  # noqa: N802
        if visible:
            ajustar_tope(self)
        super().setVisible(visible)

    def _dar(self) -> None:
        self.accept()
        self.grant_requested.emit()

    def _para_siempre(self) -> None:
        self.accept()
        self.permanent_requested.emit()


class MoveAppImageDialog(QDialog):
    """Before a shortcut to an AppImage outside ~/AppImages: move it there?

    Two answers, as asked: «Mover y añadir» (the default) and «Dejarlo donde
    está». Closing it (Esc, the X) changes nothing: `choice` stays None.
    """

    def __init__(self, path: str, parent: Optional[QWidget] = None):
        super().__init__(parent)
        import html

        from .. import render

        self.choice: Optional[str] = None
        self.setWindowTitle(_("settings.shortcut.move.title"))
        self.setModal(True)
        m = theme.METRICS
        layout = QVBoxLayout(self)
        layout.setContentsMargins(m.page_margin + 6, m.page_margin + 4,
                                  m.page_margin + 6, m.page_margin + 2)
        layout.setSpacing(m.card_gap + 4)
        title = QLabel(_("settings.shortcut.move.title"))
        title.setObjectName("Headline")
        title.setWordWrap(True)
        layout.addWidget(title)
        self.paragraphs: list[QLabel] = []
        for key in ("settings.shortcut.move.text", "settings.shortcut.move.detail"):
            texto = html.escape(_(key).format(ruta=render.home_path(path)))
            # «~/AppImages» in one piece: the line broke after the slash.
            texto = texto.replace("~/AppImages", "<nobr>~/AppImages</nobr>")
            paragraph = QLabel(texto)
            paragraph.setWordWrap(True)
            paragraph.setTextFormat(Qt.TextFormat.RichText)
            paragraph.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            layout.addWidget(paragraph)
            self.paragraphs.append(paragraph)

        self.leave_button = QPushButton(_("settings.shortcut.move.no"))
        self.leave_button.clicked.connect(lambda: self._answer("leave"))
        self.move_button = QPushButton(_("settings.shortcut.move.yes"))
        self.move_button.setObjectName("Primary")
        self.move_button.setDefault(True)
        self.move_button.clicked.connect(lambda: self._answer("move"))
        buttons = QHBoxLayout()
        buttons.setContentsMargins(0, 6, 0, 0)
        buttons.addStretch(1)
        buttons.addWidget(self.leave_button)
        buttons.addWidget(self.move_button)
        layout.addLayout(buttons)
        ajustar_tope(self)

    def setVisible(self, visible: bool) -> None:  # noqa: N802
        if visible:
            ajustar_tope(self)
        super().setVisible(visible)

    def _answer(self, choice: str) -> None:
        self.choice = choice
        self.accept()
