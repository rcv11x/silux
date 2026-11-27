"""Página de ajustes.

No guarda nada por su cuenta: emite las preferencias nuevas y quien la usa
decide qué hacer con ellas. Así la página no sabe si el cambio se persiste,
se aplica en caliente o las dos cosas.

Una columna de grupos, cada opción en un renglón: su nombre y para qué sirve
a la izquierda, el control a la derecha. La columna va pegada a la izquierda
con un ancho máximo: centrada, en una pantalla de 2560 dejaba un hueco a cada
lado y el control quedaba a un palmo de lo que explica.

Dos grupos dicen un estado además de guardar preferencias: Permisos, con lo
que sabe la ventana del ayudante, y la integración con el escritorio, con lo
que dice `desktop.status`. Los dos se repintan con cada foto (regla 9): si
alguien instala la entrada desde la terminal con la página abierta, se ve.
"""

from __future__ import annotations

import html
import math
import pathlib
import platform
from typing import Callable, Optional

import PySide6
from PySide6.QtCore import QLocale, QPoint, QRectF, QSize, Qt, QThread, Signal, qVersion
from PySide6.QtGui import QColor, QFontMetrics, QPainter, QTextCursor, QTextDocument
from PySide6.QtWidgets import (
    QAbstractButton,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from ... import __version__, db, desktop, i18n, render, system_env, updates
from ...i18n import _
from ...settings import Preferences, config_path
from .. import theme
from ..theme import Palette, ui_font
from ..widgets import (
    Button,
    Card,
    ChipRow,
    Divider,
    ElidingComboBox,
    FoldingRow,
    Plegable,
    ResponsiveRow,
    ScrollPage,
    match_widths,
)

# The UniversoLinux Discord server, where Silux has its channel.
COMMUNITY_URL = "https://discord.gg/YEctcwHZCQ"

# The names in these tables that are said in the interface's language.
TRANSLATED_NAMES = ("about.claude.name",)
AUTORIA = (
    ("rcv11x", "about.author"),
    ("about.claude.name", "about.claude"),
)

# The versions this copy runs on: an AppImage carries its own Python and Qt.
CONSTRUIDO_CON = (
    (f"Python {platform.python_version()}", "about.python"),
    (f"PySide6 {PySide6.__version__} / Qt {qVersion()}", "about.qt"),
    ("ctypes y mmap", "about.ctypes"),
    ("polkit", "about.polkit"),
)

DATOS_DE_TERCEROS = (
    ("libcpuid", "about.libcpuid"),
    ("CPU-X", "about.cpux"),
    ("Linux", "about.linux"),
    ("AMD", "about.amdcom"),
    ("cpuid", "about.cpuid"),
    ("hwdata", "about.hwdata"),
    ("smartmontools", "about.smartmontools"),
    ("OpenOCD", "about.openocd"),
    ("Mesa", "about.mesa"),
    ("PyO3", "about.pyo3"),
)

AVISOS = pathlib.Path(db.__file__).parent / "THIRD_PARTY_NOTICES.md"


def _colorear_enlaces(documento: QTextDocument, color: str) -> None:
    """Los enlaces, del color del acento.

    El azul de serie no se lee sobre el fondo oscuro. Con Markdown, Qt fija
    el color de cada enlace al importar el texto, y ni la paleta del widget
    ni una hoja de estilo del documento lo cambian después: hay que tocar
    cada fragmento.
    """
    bloque = documento.begin()
    while bloque.isValid():
        trozo = bloque.begin()
        while not trozo.atEnd():
            fragmento = trozo.fragment()
            formato = fragmento.charFormat()
            if formato.isAnchor():
                cursor = QTextCursor(documento)
                cursor.setPosition(fragmento.position())
                cursor.setPosition(fragmento.position() + fragmento.length(),
                                   QTextCursor.MoveMode.KeepAnchor)
                formato.setForeground(QColor(color))
                cursor.setCharFormat(formato)
            trozo += 1
        bloque = bloque.next()


class _DialogoDeAvisos(QDialog):
    """Los avisos de licencia de lo que Silux lleva de otros, enteros."""

    def __init__(self, palette: Palette, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(_("about.notices.button"))
        m = theme.METRICS
        capa = QVBoxLayout(self)
        capa.setContentsMargins(m.page_margin, m.page_margin, m.page_margin, m.page_margin)
        capa.setSpacing(m.card_gap)
        self.texto = QTextBrowser()
        self.texto.setOpenExternalLinks(True)
        try:
            self.texto.setMarkdown(AVISOS.read_text(encoding="utf-8"))
            _colorear_enlaces(self.texto.document(), palette.accent)
        except OSError:
            self.texto.setPlainText(_("about.notices.missing"))
        capa.addWidget(self.texto)
        cerrar = Button(_("perm.explain.close"))
        cerrar.clicked.connect(self.close)
        abajo = QHBoxLayout()
        abajo.addStretch(1)
        abajo.addWidget(cerrar)
        capa.addLayout(abajo)
        self.resize(760, 640)


THEMES = (("opt.theme.system", "system"), ("opt.theme.light", "light"), ("opt.theme.dark", "dark"))
# In the order of `settings.ACCENTS`, the default first.
ACCENT_NAMES = (("settings.accent.amber", "amber"), ("settings.accent.blue", "blue"),
                ("settings.accent.green", "green"), ("settings.accent.red", "red"),
                ("settings.accent.purple", "purple"))
UNITS = (("opt.temp.celsius", "c"), ("opt.temp.fahrenheit", "f"))
DENSITIES = (("opt.density.spacious", "spacious"), ("opt.density.normal", "normal"), ("opt.density.compact", "compact"))
# El tamaño de la letra va aparte de la densidad a propósito: son dos cosas
# distintas. La densidad decide cuánto aire hay entre las filas; esto, cómo de
# grande se lee lo que hay dentro. Quien necesita letra grande no tiene por qué
# querer además que todo ocupe el doble.
FONT_SCALES = (("opt.density.normal", "normal"), ("opt.font.large", "grande"),
               ("opt.font.larger", "mayor"), ("opt.font.largest", "máximo"))
NETWORK_UNITS = (("opt.net.bytes", "bytes"),
                 ("opt.net.bits", "bits"))

# The number boxes' least width; they all end up as wide as the widest asks
# (`_igualar_controles`).
ANCHO_DEL_CONTROL = 170
# El ancho de la columna, en anchos de letra: crece con el tamaño de la letra.
COLUMNA_EN_LETRAS = 120

# What the menu entry says when there is something to put right; the path it
# opens goes in the tooltip, not in the text.
ESTADOS_DEL_MENU_CON_ARREGLO = {
    "elsewhere": "settings.shortcut.elsewhere",
    "broken": "settings.shortcut.broken",
    "outdated": "settings.desktop.outdated.help",
}

# Lo mismo para los permisos.
ESTADOS_DE_PERMISOS = {
    "root": ("settings.perm.root", "settings.perm.root.help", "ok"),
    "connected": ("settings.perm.connected", "settings.perm.connected.help", "ok"),
    "installed_connected": ("settings.perm.installed.connected",
                            "settings.perm.installed.connected.help", "ok"),
    "notneeded": ("settings.perm.notneeded", "settings.perm.notneeded.help", "ok"),
    "unsupported": ("settings.perm.unsupported", "settings.perm.unsupported.help", "muted"),
    "outdated": ("settings.perm.outdated", "settings.perm.outdated.help", "warn"),
    "installed": ("settings.perm.installed", "settings.perm.installed.help", "info"),
    "none": ("settings.perm.none", "settings.perm.none.help", "muted"),
}


class Interruptor(QAbstractButton):
    """Un interruptor de encendido y apagado, en vez de una casilla.

    Se pinta a mano: Qt no trae uno, y una casilla dentro de un renglón cuyo
    control va a la derecha se leía como una viñeta suelta.

    Encendido va en el acento, como una casilla marcada, la sección abierta
    o el botón principal: es algo que el usuario ha elegido. No en azul: el
    azul dice que falta un dato y tiene arreglo (candados, avisos de
    permisos), y a un interruptor encendido no le falta nada. Con el azul,
    Ajustes enseñaba dos colores para lo mismo, uno en el interruptor y otro
    en el botón de al lado.
    """

    def __init__(self, palette: Palette, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._p = palette
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

    def sizeHint(self) -> QSize:  # noqa: N802
        alto = max(18, QFontMetrics(self.font()).height() + 2)
        return QSize(alto * 2 - 2, alto)

    def paintEvent(self, _event) -> None:  # noqa: N802
        pintor = QPainter(self)
        pintor.setRenderHint(QPainter.RenderHint.Antialiasing)
        # Half a pixel in: a 1 px outline on whole coordinates falls between
        # two rows of pixels and comes out as a blurred 2 px line.
        caja = QRectF(self.rect()).adjusted(1.5, 1.5, -1.5, -1.5)
        radio = caja.height() / 2
        encendido = self.isChecked()
        # Apagado es un carril vacío con su contorno y la bola en `muted`,
        # como el borde de un desplegable. Relleno de `line`, sobre la
        # tarjeta en oscuro daba 1.2:1 y el interruptor no se veía.
        if not self.isEnabled():
            fondo, contorno, bola = self._p.q("disabled"), None, self._p.q("surface")
        elif encendido:
            fondo, contorno, bola = self._p.q("accent"), None, self._p.q("surface")
        else:
            fondo, contorno, bola = self._p.q("surface_alt"), self._p.q("muted"), self._p.q("muted")
        if self.hasFocus():
            contorno = self._p.q("accent")
        pintor.setPen(contorno if contorno is not None else Qt.PenStyle.NoPen)
        pintor.setBrush(fondo)
        pintor.drawRoundedRect(caja, radio, radio)
        lado = caja.height() - 4
        x = caja.right() - lado - 2 if encendido else caja.left() + 2
        pintor.setPen(Qt.PenStyle.NoPen)
        pintor.setBrush(bola)
        pintor.drawEllipse(QRectF(x, caja.top() + 2, lado, lado))
        pintor.end()


class Insignia(QLabel):
    """Un estado en una pastilla de color: «En el menú», «Sin conceder»."""

    def __init__(self, palette: Palette, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._p = palette
        self.tono = ""
        self.setFont(ui_font(theme.METRICS.small_pt))
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

    def poner(self, texto: str, tono: str) -> None:
        if (self.text(), self.tono) == (texto, tono):
            return
        self.tono = tono
        self.setText(texto)
        # El gris de «Sin conceder» o «No está en el menú» se leía a 4.1:1
        # sobre su propia pastilla; el texto sube a `ink_dim` y la pastilla
        # se queda gris. El lavado, al 12 %: al 16 % el amarillo de un estado
        # en el tema claro bajaba de 4.5:1.
        color = self._p.q("ink_dim" if tono == "muted" else tono)
        fondo = self._p.q(tono, 0.12)
        self.setStyleSheet(
            f"QLabel {{ color: {color.name()}; "
            f"background: rgba({fondo.red()}, {fondo.green()}, {fondo.blue()}, "
            f"{fondo.alphaF():.2f}); border-radius: 9px; padding: 2px 10px; }}")


class _Renglon(FoldingRow):
    """Un ajuste: su nombre y para qué sirve a la izquierda, el control a la
    derecha, centrado en vertical con el texto. In a narrow window the
    control goes under the text."""

    def __init__(self, nombre: str, control: Optional[QWidget], explicacion: str = "",
                 parent: Optional[QWidget] = None):
        super().__init__(parent, spacing=24)
        m = theme.METRICS
        self.set_margins(0, 2, 0, 2)

        textos = QVBoxLayout()
        textos.setSpacing(2)
        self.nombre = QLabel(nombre)
        self.nombre.setObjectName("FieldValue")
        self.nombre.setWordWrap(True)
        self.nombre.setFont(ui_font(m.base_pt))
        textos.addWidget(self.nombre)
        self.explicacion = QLabel(explicacion)
        self.explicacion.setObjectName("Muted")
        self.explicacion.setWordWrap(True)
        # Más pequeña que el nombre: acompaña al ajuste, no compite con él.
        self.explicacion.setFont(ui_font(max(7, m.small_pt - 1)))
        self.explicacion.setVisible(bool(explicacion))
        textos.addWidget(self.explicacion)
        self.add_layout(textos, 1)

        if control is not None:
            if isinstance(control, QDoubleSpinBox):
                control.setMinimumWidth(ANCHO_DEL_CONTROL)
            self.add_widget(control, 0, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)


class _Tarea(QThread):
    """Lo que toca el escritorio, fuera del hilo de la interfaz.

    Instalar dibuja diez iconos y avisa a Plasma (`kbuildsycoca6` tarda su
    segundo): con la ventana esperando, el botón se quedaba pulsado.
    """

    terminada = Signal(str)          # el error, o "" si fue bien

    def __init__(self, trabajo: Callable[[], object], parent=None):
        super().__init__(parent)
        self._trabajo = trabajo

    def run(self) -> None:
        try:
            self._trabajo()
        except (OSError, desktop.DesktopError) as error:
            self.terminada.emit(str(error) or type(error).__name__)
            return
        self.terminada.emit("")


class SettingsPage(ScrollPage):
    changed = Signal(object)          # Preferences
    # La página de ajustes no tiene la foto del hardware; la pide y ya la
    # guarda la ventana, que sí la tiene.
    report_requested = Signal()
    share_copy_requested = Signal()
    share_save_requested = Signal()
    # Los permisos los pide la ventana, que es quien sabe hacerlo; la página
    # solo enseña el botón que toca según el estado.
    elevation_requested = Signal()
    explain_requested = Signal()
    permanent_requested = Signal()
    remove_helper_requested = Signal()
    # «Buscar ahora»: la ventana busca fuera del hilo de la interfaz y
    # contesta con `set_update_status`.
    update_check_requested = Signal()
    # «Update to …»: the window downloads it, as from the sidebar's button.
    update_install_requested = Signal()
    # Silux was moved to ~/AppImages: open it from there and close this one.
    relaunch_requested = Signal(str)
    welcome_requested = Signal()

    def __init__(self, prefs: Preferences, palette: Optional[Palette] = None, parent=None):
        super().__init__(parent)
        from PySide6.QtWidgets import QApplication

        self._prefs = prefs
        self._p = palette or theme.palette_for(QApplication.instance(), prefs.theme, prefs.accent)
        self._loading = True
        self._tarea: Optional[_Tarea] = None
        self._error_del_escritorio = ""
        # (old path, desktop.Moved) once the AppImage has been moved.
        self._movido: Optional[tuple] = None
        m = theme.METRICS

        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        root = QWidget()
        root.setObjectName("Root")
        self.setWidget(root)

        fuera = QHBoxLayout(root)
        fuera.setContentsMargins(m.page_margin, m.page_margin, m.page_margin, m.page_margin)
        self.columna = QWidget()
        ancho = QFontMetrics(ui_font(m.base_pt)).averageCharWidth() * COLUMNA_EN_LETRAS
        self.columna.setMaximumWidth(ancho)
        fuera.addWidget(self.columna, 1)
        # Lo que sobra va a la derecha: la columna se queda a la izquierda,
        # donde empieza la lectura, y no centrada con un hueco a cada lado.
        fuera.addStretch(0)

        layout = QVBoxLayout(self.columna)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(m.section_gap)
        layout.addWidget(self._build_general())
        layout.addWidget(self._build_appearance())
        layout.addWidget(self._build_sampling())
        layout.addWidget(self._build_permissions())
        layout.addWidget(self._build_desktop())
        layout.addWidget(self._build_share())
        layout.addWidget(self._build_updates())
        layout.addWidget(self._build_about())
        layout.addStretch(1)
        self._igualar_controles()

        self._loading = False
        self.refresh_desktop()

    def _igualar_controles(self) -> None:
        """The number boxes, as wide as the widest asks, and the lists as the
        widest of them: one under another down the page, at their own widths
        they made a saw."""
        controles = self.columna.findChildren(QDoubleSpinBox)
        ancho = max([ANCHO_DEL_CONTROL] + [c.sizeHint().width() for c in controles])
        for control in controles:
            control.setFixedWidth(ancho)
        match_widths(self.columna.findChildren(ElidingComboBox))

    # -- construcción -------------------------------------------------------

    @staticmethod
    def _grupo(titulo: str, *renglones: QWidget) -> Card:
        card = Card(titulo)
        for i, renglon in enumerate(renglones):
            if i:
                card.body.addWidget(Divider())
            card.body.addWidget(renglon)
        return card

    def _combo(self, opciones, actual: str) -> QComboBox:
        caja = ElidingComboBox()
        for etiqueta, valor in opciones:
            caja.addItem(_(etiqueta), valor)
        valores = [v for _etiqueta, v in opciones]
        caja.setCurrentIndex(valores.index(actual) if actual in valores else 0)
        caja.currentIndexChanged.connect(self._emit)
        return caja

    def _interruptor(self, encendido: bool) -> Interruptor:
        boton = Interruptor(self._p)
        boton.setChecked(encendido)
        boton.toggled.connect(self._emit)
        return boton

    def _build_general(self) -> Card:
        # El idioma va el primero: es lo que cambia todo lo demás, y quien lo
        # busca no viene a mirar el tema.
        self.language_box = ElidingComboBox()
        idiomas = i18n.available()
        for codigo, nombre in idiomas.items():
            self.language_box.addItem(nombre, codigo)
        actual = self._prefs.language if self._prefs.language in idiomas else "es"
        self.language_box.setCurrentIndex(list(idiomas).index(actual))
        self.language_box.currentIndexChanged.connect(self._emit)

        self.unit_box = self._combo(UNITS, self._prefs.temperature_unit)
        self.network_box = self._combo(NETWORK_UNITS, self._prefs.network_unit)
        self.welcome_button = Button(_("settings.welcome.button"))
        self.welcome_button.clicked.connect(self.welcome_requested)
        return self._grupo(
            _("settings.group.general"),
            _Renglon(_("settings.language.label"), self.language_box,
                     _("settings.language.help")),
            _Renglon(_("settings.tempunit.label"), self.unit_box),
            _Renglon(_("settings.netunit.label"), self.network_box, _("net.units.note")),
            _Renglon(_("settings.welcome.label"), self.welcome_button,
                     _("settings.welcome.help")),
        )

    def _build_appearance(self) -> Card:
        self.theme_box = self._combo(THEMES, self._prefs.theme)
        self.accent_box = self._combo(ACCENT_NAMES, self._prefs.accent)
        self.density_box = self._combo(DENSITIES, self._prefs.density)
        self.font_box = self._combo(FONT_SCALES, self._prefs.font_scale)
        # Las gráficas fluidas no cambian ninguna cifra, solo cómo se pintan:
        # son apariencia.
        self.fluid_charts = self._interruptor(self._prefs.fluid_charts)
        return self._grupo(
            _("settings.card.appearance"),
            _Renglon(_("settings.theme.label"), self.theme_box),
            _Renglon(_("settings.accent.label"), self.accent_box, _("settings.accent.help")),
            _Renglon(_("settings.density.label"), self.density_box, _("settings.density.help")),
            _Renglon(_("settings.fontsize.label"), self.font_box, _("settings.fontsize.help")),
            _Renglon(_("settings.fluid.label"), self.fluid_charts, _("settings.fluid.help")),
        )

    def _build_sampling(self) -> Card:
        self.interval = QDoubleSpinBox()
        self.interval.setRange(0.2, 10.0)
        self.interval.setSingleStep(0.1)
        self.interval.setDecimals(1)
        self.interval.setSuffix(" s")
        # «1.0 s» y no «1,0 s»: con la configuración regional del sistema la
        # coma salía aquí y el punto en el resto del programa, que escribe
        # todas las cifras con punto.
        self.interval.setLocale(QLocale.c())
        self.interval.setValue(self._prefs.interval_s)
        self.interval.valueChanged.connect(self._emit)
        # Qué se lee y cuánto se enseña de lo leído: las instrucciones de la
        # CPU van con el muestreo, no con el idioma y las unidades.
        self.all_features = self._interruptor(self._prefs.show_all_features)
        return self._grupo(
            _("settings.card.sampling"),
            _Renglon(_("settings.interval.label"), self.interval, _("settings.interval.help")),
            _Renglon(_("settings.allflags.label"), self.all_features, _("settings.allflags.help")),
        )

    def _build_permissions(self) -> Card:
        self.permission_badge = Insignia(self._p)
        self.permission_row = _Renglon(_("settings.perm.state"), self.permission_badge)

        self.permission_button = Button(_("perm.read.button"))
        self.permission_button.setObjectName("Primary")
        self.permission_button.clicked.connect(self._on_permission_button)
        self.explain_button = Button(_("perm.notice.explain"))
        self.explain_button.clicked.connect(self.explain_requested.emit)
        # Quitar lo instalado para siempre: borra sus dos archivos, como root.
        # Antes solo se podía copiando una orden `sudo rm` del diálogo.
        self.remove_helper_button = Button(_("settings.perm.remove"))
        self.remove_helper_button.setObjectName("GhostButton")
        self.remove_helper_button.setToolTip(_("settings.perm.remove.tip"))
        self.remove_helper_button.clicked.connect(self.remove_helper_requested.emit)
        botones = FoldingRow()
        botones.add_widget(self.remove_helper_button)
        botones.add_stretch(1)
        botones.add_widget(self.explain_button)
        botones.add_widget(self.permission_button)
        self._accion_de_permisos = "grant"
        card = self._grupo(_("settings.group.permissions"), self.permission_row, botones)
        self.set_privileges(None)
        return card

    def _build_desktop(self) -> Card:
        """«Accesos directos»: each one with its switch, applied at once."""
        m = theme.METRICS
        self.menu_switch = Interruptor(self._p)
        self.menu_switch.toggled.connect(lambda encendido: self._on_switch("menu", encendido))
        self.menu_row = _Renglon(_("settings.shortcut.menu"), self.menu_switch,
                                 _("settings.shortcut.menu.help"))
        self.desktop_shortcut = Interruptor(self._p)
        self.desktop_shortcut.toggled.connect(
            lambda encendido: self._on_switch("desktop", encendido))
        self.shortcut_row = _Renglon(_("settings.shortcut.desktop"), self.desktop_shortcut,
                                     _("settings.shortcut.desktop.help"))
        # Only when an entry opens another copy, a file that is gone or an
        # older version: there is something to put right.
        self.desktop_fix = Button(_("settings.shortcut.fix"))
        self.desktop_fix.clicked.connect(lambda: self._poner(
            self.menu_switch.isChecked(), self.desktop_shortcut.isChecked(), preguntar=True))
        arreglo = QWidget()
        fila = QHBoxLayout(arreglo)
        fila.setContentsMargins(0, 0, 0, 0)
        fila.addStretch(1)
        fila.addWidget(self.desktop_fix)
        self._arreglo = arreglo
        # Where this copy is, small: the whole path in the tooltip.
        self.desktop_path = QLabel("")
        self.desktop_path.setObjectName("Muted")
        self.desktop_path.setWordWrap(True)
        self.desktop_path.setFont(ui_font(m.small_pt))
        self.desktop_fragile = QLabel(_("settings.shortcut.fragile"))
        self.desktop_fragile.setObjectName("WarnText")
        self.desktop_fragile.setWordWrap(True)
        self.desktop_fragile.setFont(ui_font(m.small_pt))
        card = self._grupo(_("settings.group.desktop"), self.menu_row, self.shortcut_row, arreglo)
        card.body.addWidget(self.desktop_fragile)
        card.body.addWidget(self.desktop_path)
        return card

    def _build_share(self) -> Card:
        # Juntos porque responden a la misma intención: sacar algo de aquí
        # para enseñárselo a otro. El informe es para diagnosticar y la
        # imagen para presumir, y las dos cosas acaban pegadas en un chat.
        copiar = Button(_("share.button.copy"))
        copiar.setToolTip(_("share.tip"))
        copiar.clicked.connect(self.share_copy_requested.emit)
        guardar = Button(_("share.button.save"))
        guardar.setToolTip(_("share.tip"))
        guardar.clicked.connect(self.share_save_requested.emit)
        imagen = QWidget()
        fila = QHBoxLayout(imagen)
        fila.setContentsMargins(0, 0, 0, 0)
        fila.addWidget(copiar)
        fila.addWidget(guardar)

        informe = Button(_("settings.report.button"))
        informe.setToolTip(_("settings.tip.report"))
        informe.clicked.connect(self.report_requested.emit)
        return self._grupo(
            _("settings.group.share"),
            _Renglon(_("settings.share.image"), imagen, _("settings.share.image.help")),
            _Renglon(_("settings.share.report"), informe, _("settings.share.report.help")),
        )

    def _build_updates(self) -> Card:
        """Checking for new versions, at startup and by hand, and the button
        that installs the one found."""
        self.check_updates = self._interruptor(self._prefs.check_updates)
        self.update_now = Button(_("settings.updates.now"))
        self.update_now.clicked.connect(self.update_check_requested.emit)
        self.update_status = QLabel("")
        self.update_status.setObjectName("Muted")
        self.update_status.setWordWrap(True)
        self.update_status.hide()
        self.update_install = Button("")
        self.update_install.setObjectName("Primary")
        self.update_install.clicked.connect(self.update_install_requested.emit)
        self.update_install_row = _Renglon(_("settings.updates.new"), self.update_install)
        self.update_install_row.hide()
        card = self._grupo(
            _("settings.group.updates"),
            _Renglon(_("settings.updates.label"), self.check_updates,
                     _("settings.updates.help")),
            _Renglon(_("settings.updates.manual"), self.update_now),
        )
        card.body.addWidget(self.update_status)
        card.body.addWidget(self.update_install_row)
        self.updates_card = card
        return card

    def set_update_status(self, texto: str, buscando: bool = False) -> None:
        """Lo que contestó la última búsqueda, o que se está buscando."""
        self.update_now.setEnabled(not buscando)
        self.update_status.setText(texto)
        self.update_status.setVisible(bool(texto))

    def set_new_version(self, text: Optional[str], enabled: bool = True) -> None:
        """The install button's text, or None to hide it."""
        if text is not None:
            self.update_install.setText(text)
            self.update_install.setEnabled(enabled)
        self.update_install_row.setVisible(text is not None)

    def show_updates(self) -> None:
        """Scroll down to the updates group, its top at the page's top."""
        top = self.updates_card.mapTo(self.widget(), QPoint(0, 0)).y()
        self.verticalScrollBar().setValue(top - theme.METRICS.page_margin)

    def _build_about(self) -> Card:
        """Quién lo hace, sobre qué está construido, y dónde guarda las cosas."""
        card = Card(_("about.card"))
        m = theme.METRICS

        titulo = QLabel(f"Silux {render.version(__version__)}")
        titulo.setObjectName("Headline")
        titulo.setWordWrap(True)
        card.body.addWidget(titulo)
        lema = QLabel(_("about.tagline"))
        lema.setObjectName("Subhead")
        lema.setWordWrap(True)
        card.body.addWidget(lema)
        self.compat_note: Optional[QLabel] = None
        if updates.normal_would_run():
            self.compat_note = QLabel(_("about.compat.normal").format(archivo=updates.NORMAL))
            self.compat_note.setObjectName("Muted")
            self.compat_note.setWordWrap(True)
            card.body.addWidget(self.compat_note)

        fila = ResponsiveRow(min_item_width=220)
        fila.add(self._bloque(_("about.credits"), AUTORIA))
        fila.add(self._bloque(_("about.builtwith"), CONSTRUIDO_CON))
        card.body.addWidget(fila)
        gente = ResponsiveRow(min_item_width=220)
        if nombres := db.thanks():
            gente.add(self._gracias(nombres))
        gente.add(self._community())
        card.body.addWidget(gente)
        # Folded: a list as long as the rest of the card, which few open.
        self.third_party = Plegable(_("about.thirdparty.fold"))
        third = ResponsiveRow(min_item_width=220)
        size = math.ceil(len(DATOS_DE_TERCEROS) / 3)
        for start in range(0, len(DATOS_DE_TERCEROS), size):
            third.add(self._bloque(None, DATOS_DE_TERCEROS[start:start + size]))
        self.third_party.body.addWidget(third)
        card.body.addWidget(self.third_party)
        card.body.addWidget(Divider())

        self.db_info = QLabel(self._texto_de_la_base())
        self.db_info.setObjectName("Muted")
        self.db_info.setWordWrap(True)
        self.db_info.setFont(ui_font(m.small_pt))
        self.db_info.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        card.body.addWidget(self.db_info)

        # Los avisos enteros, como piden las licencias de lo que va dentro: en
        # un AppImage el archivo está en un montaje temporal, así que una ruta
        # no le sirve a nadie.
        self.notices_button = Button(_("about.notices.button"))
        self.notices_button.setObjectName("GhostButton")
        self.notices_button.clicked.connect(self._ver_avisos)
        self._dialogo_avisos: Optional[_DialogoDeAvisos] = None
        avisos = QHBoxLayout()
        avisos.addWidget(self.notices_button)
        avisos.addStretch(1)
        card.body.addLayout(avisos)

        path = QLabel(_("settings.savedat").format(ruta=render.home_path(config_path())))
        path.setObjectName("Muted")
        path.setWordWrap(True)
        path.setFont(ui_font(m.small_pt))
        path.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        card.body.addWidget(path)

        # Al final de todo: es lo único de la página que deshace lo demás.
        reset = Button(_("settings.reset.button"))
        reset.clicked.connect(self._reset)
        abajo = QHBoxLayout()
        abajo.addStretch(1)
        abajo.addWidget(reset)
        card.body.addLayout(abajo)
        return card

    def _ver_avisos(self) -> None:
        if self._dialogo_avisos is None:
            self._dialogo_avisos = _DialogoDeAvisos(self._p, self)
        self._dialogo_avisos.show()
        self._dialogo_avisos.raise_()

    @staticmethod
    def _texto_de_la_base() -> str:
        if not db.available():
            return _("settings.db.none")
        data = db.load()
        counts = data.get("counts", {})
        sources = data.get("sources", {})
        # Each number with the source it comes from: they count different
        # things (rules, families, models, nodes) and do not add up.
        return _("settings.db.counts").format(
            intel=counts.get("x86_intel", 0),
            amd=counts.get("x86_amd", 0),
            arm=counts.get("arm_parts", 0),
            commit=sources.get("libcpuid", {}).get("commit", "?"),
            fecha=sources.get("libcpuid", {}).get("date", "?"),
            familias=counts.get("intel_family", 0),
            kernel=sources.get("linux", {}).get("tag", "?"),
            modelos=counts.get("amd_models", 0),
            nodos=counts.get("cpuid_nodes", 0),
            cpuid=sources.get("cpuid", {}).get("version", "?"),
            sockets=counts.get("sockets", 0),
            cpux=sources.get("cpu-x", {}).get("commit", "?"))

    def _gracias(self, nombres: tuple[str, ...]) -> QWidget:
        """Who sends reports, by name, with their permission (db.thanks)."""
        m = theme.METRICS
        caja = QWidget()
        columna = QVBoxLayout(caja)
        columna.setContentsMargins(0, m.card_gap, 0, 0)
        columna.setSpacing(3)
        encabezado = QLabel(_("about.thanks").upper())
        encabezado.setObjectName("ColumnTitle")
        columna.addWidget(encabezado)
        columna.addSpacing(2)
        # Each name in its badge, in the accent, as the chips of a part.
        self.thanks_names = ChipRow()
        self.thanks_names.set_chips(nombres, loud=True)
        columna.addWidget(self.thanks_names)
        porque = QLabel(_("about.thanks.why"))
        porque.setObjectName("Muted")
        porque.setWordWrap(True)
        porque.setFont(ui_font(max(7, m.small_pt - 1)))
        columna.addWidget(porque)
        return caja

    def _community(self) -> QWidget:
        """Where people who use Silux talk about it, as a link."""
        m = theme.METRICS
        caja = QWidget()
        columna = QVBoxLayout(caja)
        columna.setContentsMargins(0, m.card_gap, 0, 0)
        columna.setSpacing(3)
        encabezado = QLabel(_("about.community").upper())
        encabezado.setObjectName("ColumnTitle")
        columna.addWidget(encabezado)
        columna.addSpacing(2)
        self.community_link = QLabel(
            f'<a href="{COMMUNITY_URL}" style="color: {self._p.info};">'
            f'{html.escape(_("about.community.discord"))}</a>')
        self.community_link.setTextFormat(Qt.TextFormat.RichText)
        self.community_link.setWordWrap(True)
        self.community_link.setFont(ui_font(m.small_pt))
        self.community_link.setToolTip(COMMUNITY_URL)
        # Through xdg-open with the system's environment, not the AppImage's.
        self.community_link.linkActivated.connect(system_env.open_path)
        columna.addWidget(self.community_link)
        columna.addStretch(1)
        return caja

    def _bloque(self, titulo: Optional[str], lineas: tuple[tuple[str, str], ...]) -> QWidget:
        """A column of «thing, what for», under its heading if it has one.
        A name that is a language key is said in the interface's language."""
        m = theme.METRICS
        caja = QWidget()
        columna = QVBoxLayout(caja)
        columna.setContentsMargins(0, 0, 0, 0)
        columna.setSpacing(3)

        if titulo is not None:
            encabezado = QLabel(titulo.upper())
            encabezado.setObjectName("ColumnTitle")
            columna.addWidget(encabezado)
            columna.addSpacing(2)

        for nombre, clave in lineas:
            if nombre in TRANSLATED_NAMES:
                nombre = _(nombre)
            # El nombre y su para-qué en dos renglones alineados por la
            # izquierda: así las tres columnas se leen a la misma altura.
            titulo_linea = QLabel(nombre)
            titulo_linea.setObjectName("FieldValue")
            titulo_linea.setFont(ui_font(m.small_pt))
            titulo_linea.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            columna.addWidget(titulo_linea)
            pie = QLabel(_(clave))
            pie.setObjectName("Muted")
            pie.setWordWrap(True)
            pie.setFont(ui_font(max(7, m.small_pt - 1)))
            pie.setContentsMargins(0, 0, 0, m.card_gap - 2)
            pie.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            columna.addWidget(pie)
        columna.addStretch(1)
        return caja

    # -- permisos -------------------------------------------------------------

    def set_privileges(self, snapshot) -> None:
        """El estado del ayudante y el botón que toca: no se ofrece lo que ya
        está. Con None, antes de la primera foto, como si no hubiera nada."""
        from ...privileged.client import PrivilegedClient

        privilegios = snapshot.privileged if snapshot is not None else None
        faltan = bool(snapshot.permission_notes) if snapshot is not None else True
        instalado = PrivilegedClient.installed()
        boton, explicar = None, False
        if privilegios is not None and privilegios.already_root:
            estado = "root"
        elif privilegios is not None and privilegios.connected and instalado:
            estado = "installed_connected"
        elif privilegios is not None and privilegios.connected:
            estado = "connected"
            # Concedidos mientras Silux siga abierto: lo único que queda por
            # ofrecer es instalar el ayudante, y eso se explica en «Qué hace esto».
            explicar = True
        elif privilegios is not None and not privilegios.supported:
            # Antes que «no hacen falta»: sin pkexec la foto no cuenta nada
            # como pendiente de permisos, y eso no es que no falte nada.
            estado = "unsupported"
        elif not faltan:
            estado = "notneeded"
        elif PrivilegedClient.needs_reinstall():
            estado, boton = "outdated", ("replace", "perm.replace.button")
        elif instalado:
            estado, boton = "installed", ("grant", "perm.read.button")
        else:
            estado, boton, explicar = "none", ("grant", "perm.read.button"), True

        self.permission_state = estado
        insignia, ayuda, tono = ESTADOS_DE_PERMISOS[estado]
        self.permission_badge.poner(_(insignia), tono)
        explicacion = _(ayuda)
        if snapshot is not None:
            # What to install on this distribution, as Diagnostics says it:
            # pkexec, or the polkit agent the session lacks.
            falta = "privileged.pkexec" if estado == "unsupported" else "privileged.agent"
            nota = next((n for n in snapshot.notes if n.path == falta), None)
            if nota is not None:
                extra = nota.hint if falta == "privileged.pkexec" else f"{nota.message} {nota.hint}"
                explicacion = " ".join(p for p in (explicacion, extra) if p)
        self.permission_row.explicacion.setText(explicacion)
        self.permission_row.explicacion.setVisible(True)
        if boton is None:
            self.permission_button.hide()
        else:
            self._accion_de_permisos = boton[0]
            # Mientras espera la contraseña lo lleva la ventana; aquí solo se
            # pone el texto de su estado cuando no está esperando.
            if self.permission_button.isEnabled():
                self.permission_button.setText(_(boton[1]))
            self.permission_button.show()
        self.explain_button.setVisible(explicar)
        self.remove_helper_button.setVisible(instalado)

    def _on_permission_button(self) -> None:
        if self._accion_de_permisos == "replace":
            self.permanent_requested.emit()
        else:
            self.elevation_requested.emit()

    # -- integración con el escritorio ----------------------------------------

    def refresh_desktop(self) -> None:
        """Lee cómo están los accesos y pone los interruptores y los textos.

        Son unas pocas lecturas de archivos pequeños de ~/.local/share, no de
        hardware: se hace aquí, al construir, tras cada acción y con cada foto.
        """
        if self._tarea is not None:
            return
        estado = desktop.status()
        self.desktop_state = estado.state
        lanzador = estado.launcher
        disponible = estado.state != "unsupported"
        en_menu = estado.state not in ("missing", "unsupported")
        for interruptor, valor in ((self.menu_switch, en_menu),
                                   (self.desktop_shortcut, estado.on_desktop)):
            interruptor.blockSignals(True)
            interruptor.setChecked(valor)
            interruptor.setEnabled(disponible)
            interruptor.blockSignals(False)

        if self._error_del_escritorio:
            ayuda = _("settings.desktop.failed").format(
                error=render.home_path(self._error_del_escritorio))
        elif estado.state in ESTADOS_DEL_MENU_CON_ARREGLO:
            ayuda = _(ESTADOS_DEL_MENU_CON_ARREGLO[estado.state])
        elif not disponible:
            ayuda = _("settings.desktop.unsupported.help")
        else:
            ayuda = _("settings.shortcut.menu.help")
        self.menu_row.explicacion.setText(ayuda)
        self.menu_row.setToolTip(render.home_path(estado.target) if estado.target else "")
        self._arreglo.setVisible(estado.state in ESTADOS_DEL_MENU_CON_ARREGLO)
        self.desktop_fix.setEnabled(True)
        self.desktop_fix.setText(_("settings.shortcut.fix"))

        ruta = lanzador.working_dir if lanzador.mode == "development" else (
            lanzador.command[0] if lanzador.command else "")
        clave = "settings.shortcut.dev" if lanzador.mode == "development" else "settings.shortcut.path"
        self.desktop_path.setText(_(clave).format(ruta=render.home_path(ruta)) if ruta else "")
        self.desktop_path.setToolTip(ruta)
        self.desktop_path.setVisible(bool(ruta))
        self.desktop_fragile.setVisible(
            lanzador.mode == "appimage" and bool(lanzador.command)
            and not desktop.in_appimages(lanzador.command[0]) and desktop.points_here(lanzador))

    def _on_switch(self, cual: str, encendido: bool) -> None:
        menu = encendido if cual == "menu" else self.menu_switch.isChecked()
        en_escritorio = encendido if cual == "desktop" else self.desktop_shortcut.isChecked()
        self._poner(menu, en_escritorio, preguntar=encendido)

    def _poner(self, menu: bool, en_escritorio: bool, preguntar: bool) -> None:
        """Writes the shortcuts; turning one on (or pointing them here) from an
        AppImage outside ~/AppImages first asks whether to move it there."""
        lanzador = desktop.current_launcher()
        if (preguntar and lanzador.mode == "appimage" and lanzador.command
                and not desktop.in_appimages(lanzador.command[0])):
            respuesta = self._preguntar_mover(lanzador.command[0])
            if respuesta is None:                   # cerrado: no se hace nada
                self.refresh_desktop()
                return
            if respuesta:
                self._mover_y_aplicar(lanzador.command[0], menu, en_escritorio)
                return
        self._aplicar(menu, en_escritorio)

    def add_to_menu(self) -> None:
        """The menu entry, as its switch here puts it: asking first whether to
        move an AppImage outside ~/AppImages."""
        self._poner(True, self.desktop_shortcut.isChecked(), preguntar=True)

    def _preguntar_mover(self, ruta: str) -> Optional[bool]:
        """True: move it; False: leave it where it is; None: closed."""
        from ..dialogs import MoveAppImageDialog

        dialogo = MoveAppImageDialog(ruta, self)
        self._caja_mover = dialogo
        dialogo.exec()
        dialogo.deleteLater()
        return {"move": True, "leave": False}.get(dialogo.choice)

    def repoint_shortcuts(self) -> None:
        """On start: shortcuts to an AppImage the user moved follow it, and
        those from an older version are brought up to date
        (`desktop.repoint`). Deciding is a few small reads; writing, with
        its icons and caches, goes to the background."""
        if any(desktop.stale_shortcuts()):
            self._en_segundo_plano(desktop.repoint)

    def _en_segundo_plano(self, trabajo: Callable[[], object]) -> None:
        if self._tarea is not None:
            return
        for control in (self.menu_switch, self.desktop_shortcut, self.desktop_fix):
            control.setEnabled(False)
        self.desktop_fix.setText(_("settings.desktop.working"))
        self._error_del_escritorio = ""
        self._tarea = _Tarea(trabajo, self)
        self._tarea.terminada.connect(self._tarea_terminada)
        self._tarea.start()

    def _tarea_terminada(self, error: str) -> None:
        tarea, self._tarea = self._tarea, None
        if tarea is not None:
            tarea.wait()
            tarea.deleteLater()
        self._error_del_escritorio = error
        self.refresh_desktop()
        # Once moved, the copy this window runs from is gone from its old
        # place: open it from the new one even if a shortcut failed, and the
        # new window says how the shortcuts are.
        movido, self._movido = self._movido, None
        if movido is not None:
            self._abrir_desde(movido)

    def _aplicar(self, menu: bool, en_escritorio: bool) -> None:
        self._en_segundo_plano(lambda: desktop.set_shortcuts(menu, en_escritorio))

    def _mover_y_aplicar(self, ruta: str, menu: bool, en_escritorio: bool) -> None:
        """Moves the AppImage into ~/AppImages, points the shortcuts there and,
        when it is done, opens Silux from the new place."""
        def trabajo() -> None:
            movido = desktop.move_to_appimages(ruta)
            self._movido = (ruta, movido)
            lanzador = desktop.current_launcher({"APPIMAGE": str(movido.path)})
            desktop.set_shortcuts(menu, en_escritorio, lanzador)
        self._en_segundo_plano(trabajo)

    def _abrir_desde(self, movido) -> None:
        from PySide6.QtWidgets import QMessageBox

        viejo, nuevo = movido
        if nuevo.copied:
            QMessageBox.information(self, _("settings.shortcut.move.title"),
                                    _("settings.shortcut.copied").format(
                                        nuevo=render.home_path(nuevo.path),
                                        viejo=render.home_path(viejo)))
        self.relaunch_requested.emit(str(nuevo.path))

    def wait_for_tasks(self) -> None:
        """Para cerrar la ventana sin dejar un hilo a medias."""
        if self._tarea is not None:
            self._tarea.wait()

    # -- lo que llega de la ventana ---------------------------------------------

    def apply(self, snapshot) -> None:
        self.set_privileges(snapshot)
        if self.isVisible():
            self.refresh_desktop()

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        self.refresh_desktop()

    # -- señales ------------------------------------------------------------

    def current(self) -> Preferences:
        from dataclasses import replace

        return replace(
            self._prefs,
            interval_s=self.interval.value(),
            language=self.language_box.currentData(),
            theme=self.theme_box.currentData(),
            accent=self.accent_box.currentData(),
            temperature_unit=self.unit_box.currentData(),
            density=self.density_box.currentData(),
            font_scale=self.font_box.currentData(),
            network_unit=self.network_box.currentData(),
            show_all_features=self.all_features.isChecked(),
            fluid_charts=self.fluid_charts.isChecked(),
            check_updates=self.check_updates.isChecked(),
        ).normalized()

    def _emit(self, *_args) -> None:
        if self._loading:
            return
        self._prefs = self.current()
        self.changed.emit(self._prefs)

    def _reset(self) -> None:
        from dataclasses import replace

        defaults = Preferences()
        # El tamaño de ventana no es un ajuste que el usuario toque aquí:
        # se recuerda solo, y restablecer no debería moverle la ventana.
        self._prefs = replace(defaults,
                              window_width=self._prefs.window_width,
                              window_height=self._prefs.window_height)
        self.changed.emit(self._prefs)
