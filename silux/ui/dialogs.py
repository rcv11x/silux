"""Los diálogos de la ventana que no son de una sola página."""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (QApplication, QDialog, QHBoxLayout, QLabel,
                               QPlainTextEdit, QPushButton, QVBoxLayout, QWidget)

from ..i18n import _
from . import theme

# Los cuatro párrafos, en este orden: qué lee, qué pasa si se dan esta vez,
# qué pasa si se dan para siempre y quién pide la contraseña. Sin la regla de
# polkit puesta va un quinto: qué dirá la ventana de la contraseña.
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
        layout.addWidget(titulo)

        self.paragraphs: list[QLabel] = []
        from ..privileged.instalar import orden_de_desinstalar

        claves = list(PARRAFOS)
        if permanente:
            # Sin la regla puesta, la ventana de polkit enseña la orden de un
            # intérprete con código dentro, y no se puede cambiar: pkexec elige
            # su texto por la ruta del programa (docs/privilegios.md). Se dice
            # aquí antes, con lo que dirá cuando la regla esté puesta.
            claves.append("perm.explain.window")
        for clave in claves:
            texto = _(clave)
            if clave == "perm.explain.window":
                texto = texto.format(mensaje=_("perm.polkit.message"))
            parrafo = QLabel(texto)
            parrafo.setWordWrap(True)
            parrafo.setTextFormat(Qt.TextFormat.PlainText)
            parrafo.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            layout.addWidget(parrafo)
            self.paragraphs.append(parrafo)
            if clave == "perm.explain.always":
                layout.addLayout(self._orden(orden_de_desinstalar()))

        self.grant_button = QPushButton(_("perm.explain.grant"))
        self.grant_button.clicked.connect(self._dar)
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

        self._ajustar_tope()

    def _ajustar_tope(self) -> None:
        """El ancho máximo: el de leer a gusto, o lo que pida la orden.

        Con un tope más estrecho que la orden, el campo se sale por la
        derecha y los párrafos se quedan sin altura. Se vuelve a calcular
        justo antes de enseñarse, que es cuando Qt decide el tamaño y cuando
        el tema ya ha pasado por los botones.
        """
        pide = self.layout().minimumSize().width()
        # El mínimo también: uno puesto a mano manda sobre el del contenido,
        # y con él más bajo Qt deja el diálogo más estrecho que la orden.
        ancho = max(theme.METRICS.base_pt * 40, pide)
        self.setMinimumWidth(ancho)
        self.setMaximumWidth(max(theme.METRICS.base_pt * 52, pide))
        # Y el alto que piden los párrafos a ese ancho, que es el más
        # estrecho y por tanto el más alto. El mínimo que calcula Qt cuenta
        # cada párrafo como una línea: en Wayland la ventana abría con ese
        # tamaño (573x299 donde hacían falta 425) y salían cortados los
        # párrafos y los botones. Sin pantalla no pasa, y por eso no se veía
        # en las capturas.
        alto = self.layout().totalHeightForWidth(ancho)
        self.setMinimumHeight(alto)
        if self.height() < alto or not self.isVisible():
            self.resize(max(self.width(), ancho), alto)

    def setVisible(self, visible: bool) -> None:  # noqa: N802
        if visible:
            self._ajustar_tope()
        super().setVisible(visible)

    def _orden(self, orden: str) -> QHBoxLayout:
        """La orden de quitar el ayudante, en su campo y con cómo copiarla.

        Dentro del párrafo, con ajuste de línea, se partía a mitad de una
        ruta. Aquí va en letra de ancho fijo y partida donde lo haría quien la
        escribe: una ruta por renglón, con la barra que la continúa, de modo
        que seleccionada y pegada en un terminal sigue siendo una sola orden.
        El botón copia la de un renglón. Sale de donde están las rutas, no del
        texto: si un día cambian, el diálogo no se queda diciendo otra.
        """
        self.command_text = orden
        verbo, *rutas = orden.split(" /")
        renglones = (verbo + " /" + " \\\n    /".join(rutas)) if rutas else orden
        self.command = QPlainTextEdit(renglones)
        self.command.setObjectName("Command")
        self.command.setReadOnly(True)
        self.command.setFont(theme.mono_font(theme.METRICS.small_pt))
        self.command.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.command.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.command.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        medida = self.command.fontMetrics()
        marco = 2 * (self.command.frameWidth() + int(self.command.document().documentMargin()))
        lineas = renglones.split("\n")
        self.command.setFixedHeight(medida.lineSpacing() * len(lineas) + marco + 2)
        self.command.setMinimumWidth(
            max(medida.horizontalAdvance(linea) for linea in lineas) + marco + 8)

        self.copy_button = QPushButton(_("perm.explain.copy"))
        self.copy_button.clicked.connect(self._copiar)

        fila = QHBoxLayout()
        fila.setContentsMargins(0, 0, 0, 0)
        fila.addWidget(self.command, 1)
        fila.addWidget(self.copy_button, 0, Qt.AlignmentFlag.AlignTop)
        return fila

    def _copiar(self) -> None:
        QApplication.clipboard().setText(self.command_text)
        self.copy_button.setText(_("app.copied"))
        QTimer.singleShot(1400, self._restaurar_boton)

    def _restaurar_boton(self) -> None:
        import shiboken6

        if shiboken6.isValid(self.copy_button):
            self.copy_button.setText(_("perm.explain.copy"))

    def _dar(self) -> None:
        self.accept()
        self.grant_requested.emit()

    def _para_siempre(self) -> None:
        self.accept()
        self.permanent_requested.emit()
