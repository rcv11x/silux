"""Ventana principal.

La navegación es una lista lateral en vez de pestañas superiores: caben más
secciones, se leen mejor los nombres largos y deja sitio para marcar cuáles
están disponibles. Las que aún no existen se ven en gris, para que se sepa
qué falta en lugar de fingir que la aplicación está completa.

Cambiar de tema o de densidad reconstruye la interfaz en vez de repintarla
pieza a pieza. Es una operación de milisegundos, ocurre solo cuando el
usuario toca un ajuste, y evita tener que propagar la paleta a mano por doce
clases, que es justo donde se cuelan los widgets que se quedan del color
anterior. El hilo de muestreo no se toca, así que no se pierde ni una
lectura ni el histórico de las gráficas.
"""

from __future__ import annotations

import argparse
import math
import os
import sys
import time
from typing import Optional

import pathlib

# Antes que Qt, y por eso está aquí en medio y no arriba con los demás: en un
# procesador sin x86-64-v2 la línea siguiente es la que se lleva el programa
# por delante, y desde dentro de ella ya no hay forma de explicar nada.
from .guarda import comprobar as _comprobar_procesador

_comprobar_procesador()

from PySide6.QtCore import QEvent, Qt, QElapsedTimer, QSize, QThread, QTimer, Signal
from PySide6.QtGui import QFont, QFontMetricsF, QIcon, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QPushButton,
    QStackedWidget,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from .. import __version__, build_id, desktop, i18n, render, settings as prefs_module, updates
from ..i18n import _
from ..model import Snapshot
from ..settings import Preferences
from ..tracking import Tracker
from . import icons, theme
from .pages.battery import BatteryPage
from .pages.devices import DevicesPage
from .pages.board import BoardPage
from .pages.caches import CachesPage
from .pages.cpu import CpuPage
from .pages.home import HomePage
from .pages.graphics import GraphicsPage
from .pages.memory import MemoryPage
from .pages.network import NetworkPage
from .pages.performance import PerformancePage
from .pages.storage import StoragePage
from .pages.monitor import MonitorPage
from .pages.settings import SettingsPage
from .pages.system import SystemPage
from .sampler import Sampler
from .theme import ui_font
from .widgets import ElidingLabel

# (etiqueta, ¿implementada?)
# El orden va de arriba abajo por el equipo (procesador, cachés, placa, memoria,
# gráfica) y deja al final las dos secciones que no describen una pieza:
# Sensores, que es el estado de todo a la vez, y Ajustes.
# Dónde guarda cada entrada del menú su nombre en español, que es la clave.
ROL_SECCION = int(Qt.ItemDataRole.UserRole) + 1

SECTIONS = (
    ("nav.home", True),
    ("nav.cpu", True),
    ("nav.caches", True),
    ("nav.board", True),
    ("nav.memory", True),
    ("nav.graphics", True),
    ("nav.storage", True),
    ("nav.network", True),
    ("nav.devices", True),
    ("nav.battery", True),
    ("nav.system", True),
    ("nav.benchmark", True),
    ("nav.sensors", True),
    ("nav.settings", True),
)

# Por debajo de este ancho la barra lateral estorba más de lo que ayuda.
NAV_HIDE_BELOW = 620

# Cada cuánto se mueven las gráficas de líneas con «Movimiento fluido». Una
# curva avanza unos pocos píxeles por segundo, y a treinta fotogramas ya no
# se ve el paso.
LATIDO_GRAFICAS_MS = 33
# Lo más deprisa que se anima una barra, aunque la pantalla dé más. Una barra
# recorre en `Deslizador.DURACION` lo que una curva en todo el intervalo, y a
# treinta por segundo su primer fotograma haría casi la mitad del camino de
# golpe: se vería el salto. Por encima de esto el ojo no lo nota y el
# procesador sí.
FOTOGRAMA_MINIMO_MS = 7

# El del icono del tema, si faltara el del paquete. El de la ventana depende
# de cómo se ejecute: ver `desktop.current_launcher`.
DESKTOP_ID = "silux"
BUNDLED_ICON = pathlib.Path(__file__).parent / "assets" / "silux.svg"


def application_icon() -> QIcon:
    """El icono que viaja en el paquete; el del tema solo si ese falta.

    El del paquete es siempre el de esta versión. El del tema es el de la
    última vez que alguien instaló la entrada de menú, que puede ser de otro
    logo: con él delante, la barra de tareas enseñaba el icono viejo y la
    barra lateral el nuevo.
    """
    if BUNDLED_ICON.exists():
        return QIcon(str(BUNDLED_ICON))
    return QIcon.fromTheme(DESKTOP_ID)


class _TareaDeRed(QThread):
    """Una llamada que sale a la red, fuera del hilo de la interfaz (regla 4).

    Contesta con `done(resultado, error)`: uno de los dos es None.
    """

    done = Signal(object, object)

    def __init__(self, funcion, parent=None) -> None:
        super().__init__(parent)
        self._funcion = funcion

    def run(self) -> None:  # noqa: D102 - el de QThread
        try:
            resultado = self._funcion()
        except Exception as error:                     # noqa: BLE001
            self.done.emit(None, error)
            return
        self.done.emit(resultado, None)


# Qué dice cada motivo de `updates.UpdateError`.
ERRORES_DE_ACTUALIZACION = {
    "network": "updates.err.network", "badreply": "updates.err.badreply",
    "insecure": "updates.err.insecure", "noasset": "updates.err.noasset",
    "nosums": "updates.err.nosums", "badhash": "updates.err.badhash",
    "toolarge": "updates.err.toolarge", "write": "updates.err.write",
    "notls": "updates.err.notls",
}


class MainWindow(QMainWindow):
    def __init__(self, prefs: Preferences,
                 forzadas: Optional[dict[str, tuple]] = None):
        super().__init__()
        self.prefs = prefs
        # Lo que se forzó por la línea de órdenes: campo -> (lo que había
        # guardado, lo que se forzó). Ver `_guardar`.
        self._forzadas = dict(forzadas or {})
        # La instalación del ayudante mientras espera a pkexec, o None.
        self._instalacion = None
        # El aviso de permisos de Inicio: apartado con «Ahora no», que dura lo
        # que la sesión, y si en esta sesión llegó a leerse todo.
        self._aviso_pospuesto = False
        self._permisos_completos = False
        self.setWindowTitle("Silux")
        self.resize(prefs.window_width, prefs.window_height)
        self.setMinimumSize(theme.METRICS.min_window_w, theme.METRICS.min_window_h)

        self._last_snapshot: Optional[Snapshot] = None
        # The report preview, and how many permission notes its text had.
        self._report_preview = None
        self._report_missing: Optional[int] = None
        self._palette = theme.palette_for(QApplication.instance(), prefs.theme)
        # El seguimiento de mínimos y máximos vive en la ventana, no en la
        # página: cambiar de tema reconstruye las páginas, y perder por eso el
        # histórico de una sesión de pruebas sería inaceptable.
        self._tracker = Tracker()

        self.setStatusBar(QStatusBar())
        self.statusBar().setSizeGripEnabled(True)

        # Cuando la barra lateral se oculta por falta de ancho, este selector
        # ocupa su sitio: sin él, las secciones dejarían de ser alcanzables.
        self._compact_nav = QComboBox()
        self._compact_nav.setFixedWidth(112)
        self._compact_nav.hide()
        self._compact_nav.currentIndexChanged.connect(self._on_compact_nav)
        self.statusBar().addWidget(self._compact_nav)

        # Etiquetas que se recortan: con QLabel normal, el texto de la barra de
        # estado exigía 533 px y era lo que impedía encoger la ventana.
        self._status = ElidingLabel(_("app.sampling"))
        self._status.setObjectName("Muted")
        # Con aire a la izquierda: el texto empezaba pegado al borde de la
        # ventana, sin el margen que lleva todo lo de encima.
        self._status.setContentsMargins(8, 0, 0, 0)
        self.statusBar().addWidget(self._status, 1)
        # Los datos bloqueados se contaban aquí como texto, y decirlo no
        # servía de nada: quien lee «1 dato requiere permisos» es justo quien
        # querría darlos, y el único botón para hacerlo estaba dentro de tres
        # páginas concretas. Un usuario con el consumo del procesador en blanco
        # tenía el aviso en la barra y el botón en otra sección.
        self._blocked = QPushButton("")
        self._blocked.setObjectName("StatusAction")
        self._blocked.setCursor(Qt.CursorShape.PointingHandCursor)
        self._blocked.setToolTip(_("status.blocked.tip"))
        self._blocked.setFlat(True)
        self._blocked.clicked.connect(self._on_elevation_requested)
        self._blocked.hide()
        self.statusBar().addPermanentWidget(self._blocked)

        self._sources = ElidingLabel("")
        self._sources.setObjectName("Muted")
        self._sources.setMaximumWidth(220)
        self.statusBar().addPermanentWidget(self._sources)

        # Lo de buscar versiones: las funciones se pueden cambiar (los tests
        # no salen a la red) y la versión nueva encontrada, si la hay.
        self._buscar_version = updates.check
        self._instalar_version = updates.install
        self._version_nueva: Optional[updates.Release] = None
        self._tarea_de_red: Optional[_TareaDeRed] = None

        self._build_ui()
        if prefs.check_updates:
            # Un poco después de abrir: lo primero es enseñar el equipo.
            QTimer.singleShot(3000, self.buscar_actualizacion)

        self.sampler = Sampler(interval_ms=prefs.interval_ms)
        self.sampler.sampled.connect(self._on_sample)
        self.sampler.failed.connect(self._on_failure)

        # Uno solo para todas las gráficas. Con cuarenta y tantas en pantalla,
        # cuarenta temporizadores despertando por su cuenta cuestan más que
        # todo lo que se dibuja.
        self._congelado = False
        self._desde_la_muestra = QElapsedTimer()
        # Lo que tarda de verdad entre muestra y muestra, que no es lo que se
        # pidió: el hilo recorre sysfs, hwmon y los discos, y eso lleva su
        # rato. Animar contra el intervalo configurado dejaba la línea parada
        # en el último tramo esperando un dato que aún no había llegado, y de
        # ahí el tirón al llegar.
        self._intervalo_real = float(prefs.interval_ms)
        self._animables: list = []
        # Un solo temporizador con dos ritmos: el de las gráficas, y el de la
        # pantalla mientras alguna barra va hacia su dato nuevo, que son los
        # `Deslizador.DURACION` segundos después de cada muestra.
        self._latido = QTimer(self)
        self._latido.setInterval(LATIDO_GRAFICAS_MS)
        self._latido.timeout.connect(self._avanzar_graficas)
        self._fotograma_ms = LATIDO_GRAFICAS_MS
        # Lo que se hace cuando la ventana vuelve a verse, después de que Qt
        # la marque expuesta. Un temporizador hijo, que muere con la ventana:
        # con `QTimer.singleShot(0, metodo)` saltaba aunque la ventana ya se
        # hubiera borrado, y en el CI (PySide6 6.11) tumbaba el proceso.
        self._al_exponer = QTimer(self)
        self._al_exponer.setSingleShot(True)
        self._al_exponer.setInterval(0)
        self._al_exponer.timeout.connect(self._al_volver_a_verse)
        self._aplicar_fluidez()

        atajo = QShortcut(QKeySequence(Qt.Key.Key_Space), self)
        atajo.setContext(Qt.ShortcutContext.ApplicationShortcut)
        atajo.activated.connect(self.alternar_congelado)

    # -- construcción -------------------------------------------------------

    def _build_ui(self) -> None:
        m = theme.METRICS
        # El suelo depende de la densidad, así que se reajusta al reconstruir.
        self.setMinimumSize(m.min_window_w, m.min_window_h)
        current_row = getattr(self, "nav", None).currentRow() if hasattr(self, "nav") else 0
        if hasattr(self, "monitor_page"):
            # Una orden que espera a pkexec es hija de la página que se va a
            # destruir, y un QThread destruido en marcha aborta el proceso.
            self.monitor_page.cancelar_ordenes()
        if hasattr(self, "settings_page"):
            # Lo mismo con la entrada de menú que se está instalando.
            self.settings_page.wait_for_tasks()

        central = QWidget()
        central.setObjectName("Root")

        layout = QHBoxLayout(central)
        layout.setContentsMargins(8, 8, 8, 4)
        layout.setSpacing(6)

        self.nav_panel = self._build_nav()
        layout.addWidget(self.nav_panel, 0)

        self.stack = QStackedWidget()
        self.home_page = HomePage(self._palette, self.prefs)
        self.home_page.seccion_pedida.connect(self.select_section)
        aviso = self.home_page.permission_notice
        aviso.grant_requested.connect(self._on_elevation_requested)
        aviso.explain_requested.connect(self._explicar_permisos)
        aviso.snoozed.connect(self._posponer_aviso)
        aviso.dismissed.connect(self._quitar_aviso)
        self.cpu_page = CpuPage(self._palette, self.prefs)
        self.cpu_page.elevation_requested.connect(self._on_elevation_requested)
        self.monitor_page = MonitorPage(self._palette, self.prefs, self._tracker)
        self.monitor_page.columns_resized.connect(self._on_columns_resized)
        self.monitor_page.branches_changed.connect(self._on_branches_changed)
        self.caches_page = CachesPage(self._palette, self.prefs)
        self.board_page = BoardPage(self._palette, self.prefs)
        self.memory_page = MemoryPage(self._palette, self.prefs)
        self.memory_page.elevation_requested.connect(self._on_elevation_requested)
        self.memory_page.latencies_measured.connect(self.caches_page.set_latencies)
        self.graphics_page = GraphicsPage(self._palette, self.prefs)
        self.graphics_page.elevation_requested.connect(self._on_elevation_requested)
        self.storage_page = StoragePage(self._palette, self.prefs)
        self.storage_page.elevation_requested.connect(self._on_elevation_requested)
        self.memory_page.permanent_requested.connect(self._on_permanent_requested)
        self.memory_page.explain_requested.connect(self._explicar_permisos)
        self.storage_page.explain_requested.connect(self._explicar_permisos)
        self.storage_page.permanent_requested.connect(self._on_permanent_requested)
        # Los dos botones de apartar son los mismos en Inicio y en cada
        # página, y valen para todas a la vez: apartar el aviso de Memoria y
        # encontrárselo otra vez en Almacenamiento sería no haberlo apartado.
        for pagina in self._paginas_con_aviso():
            pagina.permission_snoozed.connect(self._posponer_aviso)
            pagina.permission_dismissed.connect(self._quitar_aviso)
        self._refrescar_botones_permanentes()
        self.network_page = NetworkPage(self._palette, self.prefs)
        self.devices_page = DevicesPage(self._palette, self.prefs)
        self.battery_page = BatteryPage(self._palette, self.prefs)
        self.network_page.unit_changed.connect(self._on_network_unit)
        self.system_page = SystemPage(self._palette, self.prefs)
        self.performance_page = PerformancePage(self._palette, self.prefs)
        self.settings_page = SettingsPage(self.prefs, self._palette)
        self.settings_page.changed.connect(self._on_preferences)
        self.settings_page.update_check_requested.connect(self.buscar_actualizacion)
        self.settings_page.elevation_requested.connect(self._on_elevation_requested)
        self.settings_page.explain_requested.connect(self._explicar_permisos)
        self.settings_page.permanent_requested.connect(self._on_permanent_requested)
        self.settings_page.remove_helper_requested.connect(self._quitar_ayudante)
        self.settings_page.report_requested.connect(self._on_report_requested)
        self.settings_page.share_copy_requested.connect(self._on_share_copy)
        self.home_page.share_copy_requested.connect(self._on_share_copy)
        self.settings_page.share_save_requested.connect(self._on_share_save)
        for page in (self.home_page, self.cpu_page, self.caches_page, self.board_page,
                     self.memory_page, self.graphics_page, self.storage_page,
                     self.network_page, self.devices_page, self.battery_page,
                     self.system_page, self.performance_page,
                     self.monitor_page, self.settings_page):
            self.stack.addWidget(page)
        self._atrasadas: set = set()
        self.stack.currentChanged.connect(self._poner_al_dia)
        layout.addWidget(self.stack, 1)

        self.setCentralWidget(central)

        self._status.setFont(ui_font(m.small_pt))
        self._sources.setFont(ui_font(m.small_pt))
        self._sources.set_full_text(self._sources_text())

        self._compact_nav.blockSignals(True)
        self._compact_nav.clear()
        for row, (name, enabled) in enumerate(SECTIONS):
            if enabled:
                self._compact_nav.addItem(_(name), row)
        self._compact_nav.blockSignals(False)

        if 0 <= current_row < self.nav.count():
            self.nav.setCurrentRow(current_row)
        self._sync_nav_visibility()

        if self._last_snapshot is not None:
            self._distribute(self._last_snapshot)

    MARGEN_DE_LA_BARRA = 2

    def _build_nav(self) -> QWidget:
        m = theme.METRICS
        panel = QWidget()
        panel.setFixedWidth(m.nav_width)

        column = QVBoxLayout(panel)
        column.setContentsMargins(self.MARGEN_DE_LA_BARRA, 6, self.MARGEN_DE_LA_BARRA, 6)
        column.setSpacing(4)

        # La marca y el nombre. La marca es la del logo, no un emoji: es el
        # mismo dibujo que el icono de la ventana y el del menú.
        oscuro = self._palette.bg == theme.DARK.bg
        lado_marca = round(m.headline_px * 1.15)
        self.brand_mark = QLabel()
        self.brand_mark.setPixmap(icons.mark(oscuro, lado_marca))
        self.brand_mark.setFixedSize(lado_marca, lado_marca)
        wordmark = QLabel("Silux")
        wordmark.setObjectName("Headline")
        cabecera = QHBoxLayout()
        cabecera.setContentsMargins(10, 4, 0, 6)
        cabecera.setSpacing(8)
        cabecera.addWidget(self.brand_mark)
        cabecera.addWidget(wordmark)
        cabecera.addStretch(1)

        version = QLabel(_("app.version").format(v=render.version(__version__)))
        version.setObjectName("Muted")
        version.setFont(ui_font(max(7, m.small_pt - 1)))
        version.setContentsMargins(10, 0, 0, 0 if build_id() else 4)

        # De qué copia exacta es esto. Sale en la barra lateral porque el sitio
        # donde hace falta es una captura de pantalla ajena: sin esto, una foto
        # de un fallo ya arreglado se investiga otra vez desde el principio.
        self.build_label = QLabel(build_id())
        self.build_label.setObjectName("Muted")
        self.build_label.setFont(ui_font(max(7, m.small_pt - 1)))
        self.build_label.setContentsMargins(10, 0, 0, 4)
        self.build_label.setToolTip(_("app.build.tip"))
        self.build_label.setVisible(bool(build_id()))

        self.nav = QListWidget()
        self.nav.setObjectName("Nav")
        self.nav.setFont(ui_font(m.base_pt))
        self.nav.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.nav.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        # Un icono por sección, gris, y en ámbar el de la que está abierta.
        lado_icono = max(14, m.base_pt + 7)
        self.nav.setIconSize(QSize(lado_icono, lado_icono))
        stack_index = 0
        for name, enabled in SECTIONS:
            item = QListWidgetItem(_(name))
            item.setIcon(icons.nav_icon(name, self._palette.muted,
                                        self._palette.accent, lado_icono))
            # El nombre en español va aparte del que se ve: es la clave con la
            # que `--page` pide una sección, y un script que dice «Sensores»
            # tiene que seguir funcionando con la interfaz en inglés.
            item.setData(ROL_SECCION, name)
            if enabled:
                item.setData(Qt.ItemDataRole.UserRole, stack_index)
                stack_index += 1
            else:
                item.setFlags(Qt.ItemFlag.NoItemFlags)
                item.setToolTip(_("nav.notyet"))
            self.nav.addItem(item)
        self.nav.setCurrentRow(0)
        self.nav.currentRowChanged.connect(self._on_section)
        panel.setFixedWidth(max(m.nav_width, self._ancho_de_la_barra()))

        # La versión y la copia, al pie: arriba eran dos renglones entre el
        # nombre y la navegación, y son de lo que se mira una vez.
        column.addLayout(cabecera)
        column.addWidget(self.nav, 1)
        column.addWidget(version)
        column.addWidget(self.build_label)
        # El aviso de versión nueva, junto a la versión. No sustituye nada
        # hasta que se pulsa.
        self.update_button = QPushButton()
        self.update_button.setObjectName("Primary")
        self.update_button.clicked.connect(self._actualizar)
        column.addWidget(self.update_button)
        self._pintar_version_nueva()
        return panel

    def _ancho_de_la_barra(self) -> int:
        """Lo que pide el nombre de sección más largo, con su icono.

        `nav_width` es un suelo, no la medida: en compacto «Almacenamiento»
        salía «Almacenamien…», y lo que ocupa depende de la tipografía del
        sistema, del tamaño de letra y del idioma. Se le pregunta a la lista,
        que ya cuenta el icono y el relleno de la hoja de estilos, y se suma
        lo que engorda el nombre de la sección abierta, que va en seminegrita.
        """
        self.nav.ensurePolished()
        normal = QFontMetricsF(self.nav.font())
        gruesa = QFont(self.nav.font())
        gruesa.setWeight(QFont.Weight.DemiBold)
        gruesa = QFontMetricsF(gruesa)
        nombres = [self.nav.item(i).text() for i in range(self.nav.count())]
        engorde = max((gruesa.horizontalAdvance(n) - normal.horizontalAdvance(n)
                       for n in nombres), default=0)
        return (math.ceil(self.nav.sizeHintForColumn(0) + engorde)
                + 2 * self.nav.frameWidth() + 2 * theme.NAV_PADDING
                + 2 * self.MARGEN_DE_LA_BARRA + 2)

    def _sources_text(self) -> str:
        from .. import db

        if not db.available():
            return _("app.db.none")
        counts = db.load().get("counts", {})
        total = counts.get("x86_intel", 0) + counts.get("x86_amd", 0)
        return _("app.db.count").format(n=total)

    # -- ciclo de vida ------------------------------------------------------

    def start(self) -> None:
        self.sampler.start()

    def closeEvent(self, event) -> None:  # noqa: N802
        self.sampler.stop()
        if self._instalacion is not None:
            self._instalacion.done.disconnect(self._instalacion_terminada)
            self._instalacion.cancel()
            self._instalacion = None
        self.monitor_page.cancelar_ordenes()
        self.settings_page.wait_for_tasks()
        # El registro se cierra a mano: lo escrito ya está en el disco, pero
        # dejar el descriptor abierto al salir deja la última fila a medias.
        self.monitor_page.cerrar_registro()
        from dataclasses import replace

        self._guardar(replace(self.prefs,
                              window_width=self.width(),
                              window_height=self.height()))
        super().closeEvent(event)

    def _guardar(self, prefs: Preferences) -> None:
        """Guarda las preferencias sin lo que se forzó para esta ejecución.

        `--dark`, `--compact` o `--size` son para esta vez, y guardando las
        preferencias en memoria tal cual se quedaban para siempre: una captura
        con `--compact` dejaba la densidad compacta. Un campo que sigue con el
        valor forzado vuelve al que había guardado; si alguien lo cambió
        durante la sesión, lo que eligió es una preferencia y se guarda.
        """
        from dataclasses import replace

        devolver = {campo: guardado
                    for campo, (guardado, forzado) in self._forzadas.items()
                    if getattr(prefs, campo) == forzado}
        prefs_module.save(replace(prefs, **devolver) if devolver else prefs)

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._sync_nav_visibility()

    def select_section(self, name: str) -> bool:
        """Abre una sección por su nombre, en español o en el idioma de ahora.

        Los dos valen: un script escrito contra `--page Sensores` no puede
        dejar de funcionar porque alguien se ponga la interfaz en inglés, y
        quien la tiene en inglés espera que `--page Sensors` le sirva.

        Devuelve si la encontró. Antes no devolvía nada y el nombre que no
        casaba se iba por el desagüe sin dejar rastro: `--screenshot --page
        Rendimiento` —que entonces no era el nombre de ninguna— guardaba una
        imagen de Inicio y decía «captura guardada». Qué hacer con el fallo lo
        decide quien llama, que es el único que sabe si hay alguien delante:
        desde el menú de Inicio la clave siempre existe, y desde la línea de
        órdenes hay que parar.
        """
        row = self.section_row(name)
        if row is None:
            return False
        self.nav.setCurrentRow(row)
        self._on_section(row)
        return True

    def section_row(self, name: str) -> Optional[int]:
        """La fila del menú de una sección, por cualquiera de sus nombres."""
        buscado = name.lower()
        for row in range(self.nav.count()):
            item = self.nav.item(row)
            clave = str(item.data(ROL_SECCION) or "")
            # Los tres: lo que se ve, la clave interna y el nombre en español.
            # El tercero es el que hace que `--page Sensores` siga valiendo con
            # la interfaz en inglés, que es como está escrito en cualquier
            # script o captura de antes.
            nombres = {item.text().lower(), clave.lower(),
                       i18n.en_español(clave).lower()}
            if buscado in nombres:
                return row
        return None

    def section_names(self) -> list[str]:
        """Los nombres de sección tal y como se ven, para poder ofrecerlos.

        Sin filtrar las escondidas a propósito: la de Batería se oculta con la
        primera lectura y esto se pregunta antes de que haya ninguna, así que
        filtrarlas aquí sería escribir código que no llega a hacer nada.
        """
        return [self.nav.item(row).text() for row in range(self.nav.count())]

    def _sync_nav_visibility(self) -> None:
        """En ventanas estrechas la barra lateral se lleva un tercio del ancho,
        así que se cambia por el selector compacto de la barra de estado."""
        if not hasattr(self, "nav_panel"):
            return
        roomy = self.width() >= NAV_HIDE_BELOW
        self.nav_panel.setVisible(roomy)
        self._compact_nav.setVisible(not roomy)
        if not roomy:
            self._sync_compact_selection()

    def _sync_compact_selection(self) -> None:
        row = self.nav.currentRow()
        index = self._compact_nav.findData(row)
        if index >= 0 and index != self._compact_nav.currentIndex():
            self._compact_nav.blockSignals(True)
            self._compact_nav.setCurrentIndex(index)
            self._compact_nav.blockSignals(False)

    def _on_compact_nav(self, index: int) -> None:
        row = self._compact_nav.itemData(index)
        if row is not None and row != self.nav.currentRow():
            self.nav.setCurrentRow(row)

    # -- señales ------------------------------------------------------------

    def _on_section(self, row: int) -> None:
        item = self.nav.item(row)
        if item is None:
            return
        index = item.data(Qt.ItemDataRole.UserRole)
        if index is not None:
            self.stack.setCurrentIndex(index)
        self._sync_compact_selection()

    def _on_report_requested(self) -> None:
        """The full report, shown before it is saved."""
        from PySide6.QtWidgets import QMessageBox

        from .report_preview import ReportPreviewDialog

        if self._last_snapshot is None:
            QMessageBox.information(self, _("app.report.card"), _("app.noreading"))
            return
        if self._report_preview is None:
            self._report_preview = ReportPreviewDialog(self)
            self._report_preview.save_requested.connect(self._save_report)
            self._report_preview.permissions_requested.connect(self._on_elevation_requested)
        self._report_missing = None
        self._refresh_report_preview(self._last_snapshot)
        self._report_preview.show()
        self._report_preview.raise_()

    def _refresh_report_preview(self, snapshot: Snapshot) -> None:
        """Rebuild the open preview when what needs permissions changed: the
        full report is too expensive to redo on every sample."""
        dialog = self._report_preview
        if dialog is None or not (dialog.isVisible() or self._report_missing is None):
            return
        missing = len(snapshot.permission_notes)
        if missing == self._report_missing:
            return
        from . import full_report
        self._report_missing = missing
        dialog.set_report(full_report.build(snapshot, anonymous=True, inside_app=True), missing)

    def _save_report(self) -> None:
        from PySide6.QtWidgets import QFileDialog, QMessageBox

        sugerido = str(pathlib.Path.home() / "informe-silux.md")
        destino, _filtro = QFileDialog.getSaveFileName(
            self, _("app.report.title"), sugerido, _("app.report.filter"))
        if not destino:
            return
        try:
            pathlib.Path(destino).write_text(self._report_preview.report(), encoding="utf-8")
        except OSError as error:
            QMessageBox.warning(self, _("app.report.card"),
                                _("app.report.failed").format(error=render.home_path(error)))
            return
        QMessageBox.information(
            self, _("app.report.card"),
            _("app.report.saved").format(ruta=render.home_path(destino)),
        )

    def _tarjeta(self):
        """La imagen del equipo, o None si todavía no hay lectura."""
        from PySide6.QtWidgets import QMessageBox

        from . import tarjeta

        if self._last_snapshot is None:
            QMessageBox.information(self, _("share.button.copy"),
                                    _("app.noreading"))
            return None
        # Anónima siempre desde la ventana: esto se hace para pegarlo en un
        # sitio público, y una casilla de «incluir mis datos» solo sirve para
        # que alguien la deje marcada sin querer. Quien los necesite tiene el
        # informe con `--with-identifiers`.
        return tarjeta.dibujar(self._last_snapshot, self._palette)

    def _on_share_copy(self) -> None:
        """Al portapapeles, que es como acaba en un chat.

        Guardar un archivo para luego buscarlo y arrastrarlo son tres pasos
        para algo que se hace con un Ctrl+V.
        """
        imagen = self._tarjeta()
        if imagen is None:
            return
        QApplication.clipboard().setPixmap(imagen)
        self._status.set_full_text(_("share.copied"))

    def _on_share_save(self) -> None:
        from PySide6.QtWidgets import QFileDialog, QMessageBox

        imagen = self._tarjeta()
        if imagen is None:
            return
        sugerido = str(pathlib.Path.home() / "mi-equipo-silux.png")
        destino, _filtro = QFileDialog.getSaveFileName(
            self, _("share.dialog"), sugerido, "PNG (*.png)")
        if not destino:
            return
        if not imagen.save(destino, "PNG"):
            QMessageBox.warning(self, _("share.dialog"), _("share.failed"))
            return
        QMessageBox.information(self, _("share.dialog"),
                                _("share.saved").format(ruta=render.home_path(destino)))

    def _on_network_unit(self, unidad: str) -> None:
        """El conmutador de bytes/bits de la pestaña de Red."""
        from dataclasses import replace

        self._on_preferences(replace(self.prefs, network_unit=unidad))

    # -- actualizaciones -----------------------------------------------------

    def buscar_actualizacion(self) -> None:
        """Pregunta a GitHub por la última versión, fuera de este hilo."""
        if self._tarea_de_red is not None and self._tarea_de_red.isRunning():
            return
        self.settings_page.set_update_status(_("updates.checking"), buscando=True)
        self._lanzar(self._buscar_version, self._buscada)

    def _lanzar(self, funcion, al_acabar) -> None:
        tarea = _TareaDeRed(funcion, self)
        tarea.done.connect(al_acabar)
        self._tarea_de_red = tarea
        tarea.start()

    @staticmethod
    def _motivo(error) -> str:
        clave = ERRORES_DE_ACTUALIZACION.get(getattr(error, "code", ""), "updates.err.network")
        return _("updates.error").format(motivo=_(clave))

    def _buscada(self, release, error) -> None:
        if error is not None:
            self.settings_page.set_update_status(self._motivo(error))
            return
        if updates.is_newer(release):
            self._version_nueva = release
            self.settings_page.set_update_status(
                _("updates.available").format(version=release.version_text))
        elif updates.is_current(release):
            self.settings_page.set_update_status(
                _("updates.latest").format(version=render.version(__version__)))
        else:
            self.settings_page.set_update_status(_("updates.none"))
        self._pintar_version_nueva()

    def _pintar_version_nueva(self) -> None:
        nueva = getattr(self, "_version_nueva", None)
        if nueva is not None:
            self.update_button.setText(
                _("updates.button").format(version=nueva.version_text))
        self.update_button.setVisible(nueva is not None)

    def _actualizar(self) -> None:
        """«Actualizar»: si esta copia se puede sustituir, se baja y se cambia."""
        from PySide6.QtWidgets import QMessageBox
        nueva = self._version_nueva
        if nueva is None:
            return
        ruta = updates.replaceable_path()
        if ruta is None:
            motivo = (_("updates.reason.readonly") if os.environ.get("APPIMAGE")
                      else _("updates.reason.source"))
            QMessageBox.information(self, _("settings.group.updates"),
                                    _("updates.manual").format(motivo=motivo, url=nueva.url))
            return
        self.update_button.setEnabled(False)
        self.update_button.setText(
            _("updates.downloading").format(version=nueva.version_text))
        self._lanzar(lambda: self._instalar_version(nueva, ruta), self._instalada)

    def _instalada(self, ruta, error) -> None:
        from PySide6.QtWidgets import QMessageBox
        self.update_button.setEnabled(True)
        if error is not None:
            self._pintar_version_nueva()
            QMessageBox.warning(self, _("settings.group.updates"), self._motivo(error))
            return
        nueva, self._version_nueva = self._version_nueva, None
        self._pintar_version_nueva()
        respuesta = QMessageBox.question(
            self, _("updates.done.title"),
            _("updates.done").format(version=nueva.version_text))
        if respuesta == QMessageBox.StandardButton.Yes:
            # El mismo camino: el acceso directo apunta a él y sigue valiendo.
            os.execv(str(ruta), [str(ruta), *sys.argv[1:]])

    def _on_preferences(self, prefs: Preferences) -> None:
        from dataclasses import replace

        previous = self.prefs
        self.prefs = prefs
        self._guardar(prefs)

        if prefs.interval_ms != previous.interval_ms and hasattr(self, "sampler"):
            self.sampler.set_interval(prefs.interval_ms)

        if prefs.fluid_charts != previous.fluid_charts:
            self._aplicar_fluidez()

        if prefs.language != previous.language:
            # Reconstruir la interfaz entera es lo que ya se hace al cambiar de
            # tema o de densidad, y aquí resuelve lo mismo de una vez: los
            # títulos y las etiquetas se ponen al montar cada página, así que
            # no hay forma de retraducirlos sin volver a montarlas.
            i18n.set_language(prefs.language)

        appearance_changed = ((prefs.theme, prefs.density, prefs.font_scale)
                              != (previous.theme, previous.density, previous.font_scale))
        content_changed = (prefs.temperature_unit, prefs.show_all_features,
                           prefs.network_unit) != (
            previous.temperature_unit, previous.show_all_features,
            previous.network_unit
        )

        if (prefs.density, prefs.font_scale) != (previous.density, previous.font_scale):
            # Los anchos guardados se midieron con otra tipografía y otro
            # espaciado; conservarlos deja columnas que no encajan.
            self.prefs = replace(self.prefs, sensor_columns=())
            self._guardar(self.prefs)

        if appearance_changed:
            self._palette = theme.apply(QApplication.instance(), prefs.theme,
                                        prefs.density, prefs.font_scale)
            self._build_ui()
        elif content_changed or prefs.language != previous.language:
            self._build_ui()

    def _aplicar_fluidez(self) -> None:
        """Enciende o apaga el deslizamiento de las gráficas y las barras."""
        from .widgets import Deslizador
        Deslizador.fluido = bool(self.prefs.fluid_charts)
        if self.prefs.fluid_charts and not self._congelado:
            self._animables = self._graficas(solo_visibles=True)
            self._latir_si_hace_falta()
        else:
            self._latido.stop()
            # Sin animación, cada gráfica se queda en su sitio definitivo.
            for grafica in self._graficas():
                grafica.advance(1.0)

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        # El `QWindow` existe desde que se enseña: ahí llega cuándo el
        # compositor vuelve a enseñarla (al restaurarla o al volver a su
        # escritorio), y es cuando se pone al día lo que se dejó de pintar.
        ventana = self.windowHandle()
        if ventana is not None and not getattr(self, "_escucha_exposicion", False):
            ventana.installEventFilter(self)
            self._escucha_exposicion = True

    def eventFilter(self, objeto, evento) -> bool:  # noqa: N802
        if evento.type() == QEvent.Type.Expose and objeto is self.windowHandle():
            # Después de que Qt la marque expuesta, no durante.
            self._al_exponer.start()
        return super().eventFilter(objeto, evento)

    def _al_volver_a_verse(self) -> None:
        if self._expuesta():
            self._se_ha_visto = True
            self._poner_al_dia()
            self._latir_si_hace_falta()

    def _latir_si_hace_falta(self) -> None:
        """El temporizador late solo si hay algo que mover y se ve.

        En una página sin gráficas ni barras, o con la ventana minimizada o en
        otro escritorio, latía treinta veces por segundo para nada: 1,8 puntos
        de un núcleo en Placa base y uno escondida. Se vuelve a encender con
        la muestra siguiente si hace falta.
        """
        hace_falta = (self.prefs.fluid_charts and not self._congelado
                      and bool(self._animables) and self._expuesta())
        if hace_falta and not self._latido.isActive():
            self._latido.start()
        elif not hace_falta and self._latido.isActive():
            self._latido.stop()

    def _expuesta(self) -> bool:
        """Si algo de la ventana llega a la pantalla. Minimizada o en otro
        escritorio, el compositor la deja de enseñar y Qt no pinta nada."""
        ventana = self.windowHandle()
        return ventana is not None and ventana.isExposed()

    def _graficas(self, solo_visibles: bool = False):
        """Lo que se desliza: las gráficas y las barras de la ventana; lo de
        las páginas cerradas no cuenta.

        Qt no repinta un widget oculto, así que avisarlas es gasto tonto: de
        las dieciséis gráficas que hay montadas, en pantalla no llegan a cinco.
        Una barra oculta se queda donde iba, y se pone en su sitio con la
        muestra siguiente.

        Las visibles se buscan solo en la página abierta, y ninguna con la
        ventana escondida: recorrer los casi dos mil widgets de la ventana
        eran 3 ms por muestreo, dos tercios de lo que tarda en repartirse.
        """
        from .corematrix import CoreMatrix
        from .widgets import LevelBar, Sparkline, StackedBar
        donde = self
        if solo_visibles:
            if self._escondida() or self.stack.currentWidget() is None:
                return []
            donde = self.stack.currentWidget()
        graficas = [w for clase in (Sparkline, LevelBar, StackedBar, CoreMatrix)
                    for w in donde.findChildren(clase)]
        return [g for g in graficas if g.isVisible()] if solo_visibles else graficas

    def _avanzar_graficas(self) -> None:
        if self._congelado or not self._desde_la_muestra.isValid():
            return
        if not self._expuesta():
            self._latido.stop()
            return
        fase = self._desde_la_muestra.elapsed() / max(1.0, self._intervalo_real)
        # La lista se hace una vez por muestreo (`_on_sample`), no a cada
        # latido: buscar entre todos los widgets de la ventana treinta veces
        # por segundo costaba más que pintar.
        barras_en_marcha = False
        for grafica in self._animables:
            if grafica.advance(fase):
                barras_en_marcha = True
        self._ritmo(barras_en_marcha)

    def _ritmo(self, barras_en_marcha: bool) -> None:
        """El de la pantalla mientras una barra se mueve; si no, el de las
        gráficas, que piden mucho menos."""
        intervalo = self._fotograma_ms if barras_en_marcha else LATIDO_GRAFICAS_MS
        if self._latido.interval() != intervalo:
            self._latido.setInterval(intervalo)

    def _medir_fotograma(self) -> int:
        """Lo que dura un fotograma de la pantalla donde está la ventana:
        animar más deprisa de lo que la pantalla enseña es dibujar para nadie."""
        pantalla = self.screen()
        hercios = pantalla.refreshRate() if pantalla is not None else 0.0
        if not hercios or hercios <= 1.0:
            hercios = 60.0
        return max(FOTOGRAMA_MINIMO_MS, round(1000.0 / hercios))

    def alternar_congelado(self) -> None:
        """Para lo que se pinta, para poder leer un pico antes de que se vaya.

        La recolección sigue: los mínimos y máximos no se pierden por mirar.
        Al soltar, la ventana se pone al día con la muestra que haya.
        """
        self._congelado = not self._congelado
        self._aplicar_fluidez()
        if self._congelado:
            self._status.set_full_text(
                _("app.frozen"))
        elif self._last_snapshot is not None:
            self._on_sample(self._last_snapshot)

    def _on_sample(self, snapshot: Snapshot) -> None:

        self._last_snapshot = snapshot
        transcurrido = (self._desde_la_muestra.restart()
                        if self._desde_la_muestra.isValid()
                        else self._desde_la_muestra.start() or 0)
        if transcurrido and 0 < transcurrido < 60_000:
            # Media corrida: un muestreo lento suelto no descoloca el ritmo,
            # pero si el equipo se pone en serio la animación lo sigue.
            self._intervalo_real = (self._intervalo_real * 3 + transcurrido) / 4
        if self._congelado:
            # Los datos siguen entrando: los mínimos y máximos no se pierden
            # por mirar. Lo que se para es lo que se pinta.
            return
        for boton in (self.memory_page.elevation_button,
                      self.storage_page.elevation_button,
                      self.settings_page.permission_button):
            if not boton.isEnabled():
                boton.setEnabled(True)
                boton.setText(_("perm.read.button"))
        # Graphics' live in its notices: after a cancelled window they stayed
        # disabled, «Esperando autorización…», until the notice was rebuilt.
        for boton in self.graphics_page.elevation_buttons:
            if not boton.isEnabled():
                boton.setEnabled(True)
                boton.setText(_("perm.button.read"))
        self.home_page.permission_notice.set_waiting(False)
        self._distribute(snapshot)
        self._refresh_report_preview(snapshot)
        self._animables = (self._graficas(solo_visibles=True)
                           if self.prefs.fluid_charts else [])
        self._latir_si_hace_falta()
        if self._latido.isActive():
            # Las barras acaban de recibir su dato: los fotogramas siguientes,
            # al ritmo de la pantalla, que puede haber cambiado si la ventana
            # pasó a otra.
            self._fotograma_ms = self._medir_fotograma()
            self._ritmo(True)

        # La pista del atajo va aquí porque es donde se mira sin buscar. Un
        # atajo que no se ve en ningún sitio no existe para quien no lo sabe.
        partes = [_("status.refresh").format(n=f"{self.prefs.interval_s:g}"),
                  _("status.freeze")]
        # El plural va bien puesto: «1 dato(s)» delataba que nadie lo había
        # mirado, en un programa cuyo argumento es que los datos están
        # cuidados. Y ya no es texto suelto: el mismo renglón es el botón que
        # los pide, porque quien lee que falta algo es quien quiere arreglarlo.
        #
        # Se cuenta lo mismo que en el aviso de Inicio: lo que el ayudante
        # sabe leer en este equipo. El enlace sigue aquí aunque el aviso se
        # haya quitado para siempre; es lo que queda para darlos después.
        bloqueados = len(snapshot.permission_notes)
        if bloqueados:
            plantilla = (_("status.blocked.action") if bloqueados == 1
                         else _("status.blocked.action.many"))
            self._blocked.setText(plantilla.format(n=bloqueados))
        self._blocked.setVisible(bool(bloqueados))
        # Ni la cuenta de sensores ni la lista de fuentes (`cppc, cpuid,
        # dmi…`): es jerga del programa, se cortaba en compacto, y quien la
        # necesita la tiene en el informe.
        self._status.set_full_text(" · ".join(partes))

    def _on_elevation_requested(self) -> None:
        """El usuario ha pedido los datos que exigen privilegios.

        Con el ayudante y su regla puestos y al día, la ventana de la
        contraseña dice con nuestras palabras qué se lee, y se piden sin más.
        Sin ellos, polkit enseña la orden de `python3` con código dentro, y
        eso no se le pone delante a nadie sin avisar: antes se abre «Qué pasa
        al dar permisos», que lo cuenta y ofrece «Para siempre».
        """
        from ..privileged.client import PrivilegedClient

        if PrivilegedClient.instalado() and PrivilegedClient.al_dia():
            self._elevar()
        else:
            self._explicar_permisos()

    def _elevar(self) -> None:
        """Pide los permisos ya, sin más avisos.

        Solo se deja la petición apuntada: el diálogo de autenticación lo abre
        el hilo de muestreo, que puede bloquear sin congelar la ventana. Se le
        da un toque para que no haya que esperar al siguiente intervalo.
        """
        # Todos los botones piden lo mismo y se lanza un solo ayudante, así
        # que todos se quedan esperando a la vez. Los de Gráficos van dentro
        # del aviso y nacen y mueren con él, así que se preguntan cada vez.
        for boton in [self.memory_page.elevation_button,
                      self.storage_page.elevation_button,
                      self.settings_page.permission_button,
                      *self.graphics_page.elevation_buttons]:
            boton.setEnabled(False)
            boton.setText(_("perm.waiting"))
        self.home_page.permission_notice.set_waiting(True)
        self.sampler.request_elevation()

    # -- permiso permanente -------------------------------------------------

    def _botones_permanentes(self) -> list:
        return [self.memory_page.permanent_button,
                self.storage_page.permanent_button]

    def _refrescar_botones_permanentes(self) -> None:
        """Un botón que no hace nada es peor que ninguno: si ya está puesto,
        se va."""
        from ..privileged.client import PrivilegedClient

        # Y vuelve cuando el que está puesto no es el de este programa: ahí
        # el botón no sobra, es lo que sustituye un ayudante que se quedó
        # atrás. Mientras no se pulse, el archivo viejo sigue en el sistema
        # siendo de root y con su acción de polkit apuntándole.
        #
        # Solo entonces. Darlos para siempre por primera vez se ofrece en
        # «Qué hace esto», que es donde se explica: aquí el botón («No volver
        # a pedirla») se leía como una tercera forma de apartar el aviso, al
        # lado de «Ahora no» y «No volver a mostrar».
        for boton in self._botones_permanentes():
            boton.setVisible(PrivilegedClient.necesita_reinstalar())
            boton.setText(_("perm.replace.button"))

    def _on_permanent_requested(self) -> None:
        """Instala el ayudante en el sistema con su propia acción de polkit.

        Va por `pkexec` como todo lo demás. A partir de ahí, la ventana de la
        contraseña dice qué se lee; la contraseña se sigue pidiendo al dar
        permisos.
        No va en el hilo de muestreo porque esto no lee hardware: copia dos
        archivos y termina. Pero tampoco se espera aquí: mientras alguien
        escribe la contraseña, la ventana tiene que seguir pintando.
        """
        from .background import BackgroundCommand

        if self._instalacion is not None:
            return                          # ya hay un diálogo abierto
        for boton in self._botones_permanentes():
            boton.setEnabled(False)
            boton.setText(_("perm.installing"))

        try:
            orden, ayudante = self._orden_de_instalacion()
        except (OSError, RuntimeError) as exc:
            self._aviso_permanente(
                _("perm.install.failed").format(error=exc))
            return
        # El ayudante va por la tubería y no por una ruta: el porqué está en
        # `instalar.instalar`, que es quien lo recibe.
        self._instalacion = BackgroundCommand(orden, stdin=ayudante, timeout=180)
        self._instalacion.done.connect(self._instalacion_terminada)
        self._instalacion.start()

    def _instalacion_terminada(self, resultado) -> None:
        orden, self._instalacion = self._instalacion, None
        if orden is not None:
            orden.wait()
        if resultado.error is not None:
            self._aviso_permanente(
                _("perm.install.failed").format(error=resultado.error))
            return

        if resultado.returncode != 0:
            # 126 y 127 son «el usuario canceló» y «no autorizado»: eso no es
            # un fallo del que haya que informar como si algo se hubiera roto.
            if resultado.returncode not in (126, 127):
                self._aviso_permanente(
                    (resultado.stderr or "").strip().splitlines()[-1:]
                    or [_("perm.failed")])
            self._restaurar_botones_permanentes()
            return

        self._refrescar_botones_permanentes()
        if self._last_snapshot is not None:
            self.settings_page.set_privileges(self._last_snapshot)
        self._status.set_full_text(
            _("perm.installed"))

    def _quitar_ayudante(self) -> None:
        """Borra el ayudante instalado y su regla, como root, tras preguntar.

        Es `instalar.py --uninstall` por la misma vía que la instalación:
        el guion por `argv`, sin ninguna ruta que el usuario pueda reescribir.
        Lo que ya esté leyendo con permisos sigue hasta cerrar Silux.
        """
        from PySide6.QtWidgets import QMessageBox

        from .background import BackgroundCommand

        if self._instalacion is not None:
            return
        if QMessageBox.question(
                self, _("settings.perm.remove.title"), _("settings.perm.remove.ask"),
                QMessageBox.StandardButton.Cancel | QMessageBox.StandardButton.Yes,
                QMessageBox.StandardButton.Cancel) != QMessageBox.StandardButton.Yes:
            return
        try:
            orden = self._orden_de_desinstalacion()
        except (OSError, RuntimeError) as exc:
            self._aviso_permanente(_("perm.install.failed").format(error=exc))
            return
        self.settings_page.remove_helper_button.setEnabled(False)
        self._instalacion = BackgroundCommand(orden, timeout=180)
        self._instalacion.done.connect(self._desinstalacion_terminada)
        self._instalacion.start()

    def _desinstalacion_terminada(self, resultado) -> None:
        orden, self._instalacion = self._instalacion, None
        if orden is not None:
            orden.wait()
        self.settings_page.remove_helper_button.setEnabled(True)
        if resultado.error is not None:
            self._aviso_permanente(_("perm.install.failed").format(error=resultado.error))
            return
        if resultado.returncode != 0:
            if resultado.returncode not in (126, 127):
                self._aviso_permanente(
                    (resultado.stderr or "").strip().splitlines()[-1:] or [_("perm.failed")])
            return
        self._refrescar_botones_permanentes()
        if self._last_snapshot is not None:
            self.settings_page.set_privileges(self._last_snapshot)
        self._status.set_full_text(_("settings.perm.removed"))

    @staticmethod
    def _orden_de_desinstalacion() -> list[str]:
        """La orden de pkexec para quitar el ayudante: el instalador con
        `--uninstall`, por `argv`, como al instalarlo."""
        from pathlib import Path

        from ..privileged import client as _client

        instalador = (Path(__file__).resolve().parent.parent
                      / "privileged" / "instalar.py")
        try:
            interprete = _client.interprete()
        except _client.HelperUnavailable:
            raise RuntimeError(_("perm.nopython.install")) from None
        return ["pkexec", *_client.en_linea(
            interprete, "silux-instalar.py",
            instalador.read_text(encoding="utf-8"), "--uninstall")]

    @staticmethod
    def _orden_de_instalacion() -> tuple[list[str], str]:
        """La orden de pkexec para instalar, y lo que se le manda por la tubería.

        Desde un AppImage nada de dentro sirve: el montaje va con `nosuid` —así
        que pkexec no ejecuta nada de ahí— y es de FUSE y del usuario, así que
        root ni siquiera puede leerlo.

        Antes se copiaban fuera el instalador y el ayudante y se le pasaban las
        dos rutas. Eran de ~/.cache, que escribe el usuario, y la ventana no era
        una carrera de microsegundos: iba desde la copia hasta que root abría el
        archivo, con el diálogo de la contraseña en medio. Y lo que quedaba
        instalado —de root, con su acción de polkit apuntándole— era lo que
        hubiera ahí al final, o sea que no era ejecutar una vez: era dejar
        puesta una puerta.

        Ahora el instalador va por `argv` y el ayudante por `stdin`. Ninguno de
        los dos es un nombre que se pueda repuntar, y en la orden no queda
        ninguna ruta que no sea de root. Es el mismo camino que recorre el
        cliente para lanzar el ayudante suelto.
        """
        from pathlib import Path

        from ..privileged import client as _client

        instalador = (Path(__file__).resolve().parent.parent
                      / "privileged" / "instalar.py")
        try:
            interprete = _client.interprete()
        except _client.HelperUnavailable:
            raise RuntimeError(_("perm.nopython.install")) from None

        orden = ["pkexec", *_client.en_linea(
            interprete, "silux-instalar.py",
            instalador.read_text(encoding="utf-8"), "--from-stdin")]
        return orden, _client.HELPER.read_text(encoding="utf-8")

    def _restaurar_botones_permanentes(self) -> None:
        for boton in self._botones_permanentes():
            boton.setEnabled(True)
            boton.setText(_("perm.replace.button"))

    def _aviso_permanente(self, detalle) -> None:
        from PySide6.QtWidgets import QMessageBox

        texto = detalle if isinstance(detalle, str) else " ".join(detalle)
        QMessageBox.warning(self, _("perm.dialog.title"), texto)
        self._restaurar_botones_permanentes()

    def _on_branches_changed(self, plegadas: tuple, abiertas: tuple) -> None:
        from dataclasses import replace

        if (tuple(plegadas), tuple(abiertas)) != (tuple(self.prefs.sensor_collapsed),
                                                 tuple(self.prefs.sensor_expanded)):
            self.prefs = replace(self.prefs, sensor_collapsed=tuple(plegadas),
                                 sensor_expanded=tuple(abiertas))

    def _on_columns_resized(self, widths: tuple) -> None:
        from dataclasses import replace

        if tuple(widths) != tuple(self.prefs.sensor_columns):
            self.prefs = replace(self.prefs, sensor_columns=tuple(widths))

    def _distribute(self, snapshot: Snapshot) -> None:
        """Da la foto a cada página: entera a la que se ve, y a las demás solo
        lo que guarda historia.

        Aplicarla entera a las catorce en cada muestreo reescribía tablas y
        árboles que nadie miraba: con la ventana escondida era la tercera
        parte de lo que gastaba silux. Las que guardan historia (gráficas, los
        mínimos y máximos de Sensores, su grabación) la reciben siempre, para
        que no se les pierda ningún punto; las que tienen un `record` reciben
        solo eso. Las que se saltan quedan atrasadas y se ponen al día al
        abrirlas o al volver a verse la ventana (`_poner_al_dia`): la regla 9.
        """
        # Antes de pintar: decide también si las páginas enseñan sus avisos
        # de permisos, y eso lo aplican al pintarse.
        self._poner_aviso_de_permisos(snapshot)
        a_la_vista = self._pagina_a_la_vista()
        con_historia = self._paginas_con_historia()
        for page in (self.home_page, self.cpu_page, self.monitor_page, self.caches_page,
                     self.board_page, self.memory_page, self.system_page,
                     self.graphics_page, self.network_page, self.storage_page,
                     self.devices_page, self.battery_page, self.performance_page,
                     self.settings_page):
            if page is a_la_vista or (page in con_historia and not hasattr(page, "record")):
                page.apply(snapshot)
                self._atrasadas.discard(page)
            else:
                if page in con_historia:
                    page.record(snapshot)
                self._atrasadas.add(page)

        self._ajustar_bateria(snapshot)

    def _paginas_con_historia(self) -> tuple:
        """Las que necesitan cada muestra aunque no se vean.

        Las de las gráficas, Sensores (sus mínimos y máximos, y lo que graba
        a CSV) y Rendimiento: necesita saber contra qué procesador se mide, y
        por quedarse fuera guardaba todas las pruebas con «?» en vez del
        nombre. Su `apply` solo mira una cadena.
        """
        return (self.home_page, self.cpu_page, self.monitor_page, self.graphics_page,
                self.network_page, self.storage_page, self.battery_page,
                self.performance_page)

    def _pagina_a_la_vista(self):
        """La página abierta, o ninguna si la ventana se llegó a ver y ya no
        se ve (minimizada o en otro escritorio). La que aún no ha llegado a la
        pantalla cuenta como a la vista: es la que se acaba de abrir, la que
        se monta para una captura o en un test."""
        if self._escondida():
            return None
        return self.stack.currentWidget()

    def _escondida(self) -> bool:
        ventana = self.windowHandle()
        return (getattr(self, "_se_ha_visto", False) and ventana is not None
                and not ventana.isExposed())

    def _poner_al_dia(self, *_args) -> None:
        """La página que se acaba de abrir, o la de la ventana que vuelve a
        verse, con la última foto si se quedó atrasada."""
        pagina = self._pagina_a_la_vista()
        if pagina in self._atrasadas and self._last_snapshot is not None:
            self._atrasadas.discard(pagina)
            pagina.apply(self._last_snapshot)

    # -- el aviso de permisos de Inicio ---------------------------------------

    def _poner_aviso_de_permisos(self, snapshot: Snapshot) -> None:
        """Decide en cada muestreo si el aviso sale y con qué.

        Sigue al estado, no a un botón: desaparece solo cuando ya no falta
        nada. Y vuelve aunque se hubiera apartado si lo que falta es algo que
        en esta sesión se estaba leyendo —un ayudante que se cae—: eso ya no
        es «hay datos que podrías ver», es «has dejado de ver datos».
        """
        faltan = tuple(nota.what for nota in snapshot.permission_notes)
        if not faltan:
            if snapshot.privileged.connected:
                self._permisos_completos = True
            self.home_page.set_permission_notice(())
            return
        recaida = self._permisos_completos
        apartado = self._aviso_pospuesto or self.prefs.permission_notice_dismissed
        visible = recaida or not apartado
        self.home_page.set_permission_notice(faltan if visible else (), recaida)
        for pagina in self._paginas_con_aviso():
            pagina.hide_permission_notices(not visible)

    def _paginas_con_aviso(self) -> tuple:
        """Las páginas que piden permisos por su cuenta."""
        return (self.cpu_page, self.memory_page, self.graphics_page, self.storage_page)

    def _explicar_permisos(self) -> None:
        """«Qué hace esto», antes de pedir la contraseña."""
        from ..privileged.client import PrivilegedClient
        from .dialogs import PermissionsDialog

        dialogo = PermissionsDialog(
            permanente=(not PrivilegedClient.instalado()
                        or PrivilegedClient.necesita_reinstalar()),
            concedidos=self._permisos_concedidos(),
            parent=self)
        dialogo.grant_requested.connect(self._elevar)
        dialogo.permanent_requested.connect(self._on_permanent_requested)
        # `open` y no `exec`: es modal para la ventana pero no para el
        # muestreo, que sigue pintando detrás.
        self._dialogo_permisos = dialogo
        dialogo.open()

    def _permisos_concedidos(self) -> bool:
        """Si esta sesión ya lee con permisos: el ayudante conectado, o root."""
        foto = self._last_snapshot
        if foto is None:
            return False
        return bool(foto.privileged.connected or foto.privileged.already_root)

    def _apartar_aviso(self) -> None:
        # Apartarlo también vale para el de la recaída: sale otra vez si
        # vuelve a pasar, no mientras dure.
        self._permisos_completos = False
        self.home_page.set_permission_notice(())
        for pagina in self._paginas_con_aviso():
            pagina.hide_permission_notices(True)
        # Las páginas lo aplican al pintar: se les da la última foto para que
        # el aviso se vaya ahora y no con el muestreo siguiente.
        if self._last_snapshot is not None and not self._congelado:
            for pagina in self._paginas_con_aviso():
                pagina.apply(self._last_snapshot)

    def _posponer_aviso(self) -> None:
        """«Ahora no»: hasta el próximo arranque."""
        self._aviso_pospuesto = True
        self._apartar_aviso()

    def _quitar_aviso(self) -> None:
        """«No volver a mostrar»: se guarda. El enlace de abajo sigue."""
        from dataclasses import replace

        self.prefs = replace(self.prefs, permission_notice_dismissed=True)
        self._guardar(self.prefs)
        self._apartar_aviso()

    def _ajustar_bateria(self, snapshot: Snapshot) -> None:
        """La sección de batería solo en los equipos que tienen una.

        No es lo mismo que un dato que falta, que se explica y se deja a la
        vista: un sobremesa no va a tener batería nunca, y dejar la entrada
        puesta para decir «este equipo no tiene batería» es ruido permanente en
        un menú que ya lleva doce. Se decide con la primera lectura y no se
        vuelve a tocar, salvo que aparezca una: eso pasa de verdad con las
        estaciones de acoplamiento y con un SAI enchufado a mitad de sesión.
        """
        fila = next((i for i, (clave, _hecha) in enumerate(SECTIONS)
                     if clave == "nav.battery"), None)
        if fila is None:
            return
        item = self.nav.item(fila)
        if item is None:
            return
        sobra = not snapshot.batteries
        if item.isHidden() != sobra:
            item.setHidden(sobra)
            # Si estábamos mirándola justo cuando desaparece, hay que irse a
            # algún sitio: una página escondida y seleccionada deja la ventana
            # en blanco sin nada seleccionado en el menú.
            if sobra and self.nav.currentRow() == fila:
                self.nav.setCurrentRow(0)

    def _on_failure(self, message: str) -> None:
        self._status.set_full_text(
            _("app.sample.failed").format(msg=message))


def seccion_que_falta(window: MainWindow, nombre: str) -> Optional[str]:
    """Por qué no se puede capturar esa sección ahora, o `None` si se puede.

    Existe por la de Batería: está en el menú desde el principio y se esconde
    con la primera lectura en un equipo sin batería. `--page` se valida antes
    de esa lectura, así que la daba por buena, y la captura salía después con
    la ventana ya en Inicio. Se pregunta otra vez cuando ya hay datos.
    """
    fila = window.section_row(nombre)
    if fila is None:
        return _("app.page.unknown").format(nombre=nombre)
    if window.nav.item(fila).isHidden():
        return _("app.page.hidden").format(nombre=nombre)
    return None


def _callar_el_portal() -> None:
    """Silencia un aviso de Qt que no le dice nada a nadie.

    Al arrancar, Qt se presenta al portal de escritorio con el identificador
    de la aplicación, y el portal lo busca entre los .desktop instalados. Un
    AppImage que no se ha integrado en el menú no tiene ninguno, así que suelta
    «Could not register app ID: App info not found for 'silux'» y sigue
    funcionando igual: el registro solo sirve para que el escritorio sepa de
    quién es la ventana.

    Se filtra ese mensaje y nada más; el resto de lo que diga Qt pasa tal cual,
    porque un aviso que sí importe no se puede perder por callar este.
    """
    from PySide6.QtCore import QtMsgType, qInstallMessageHandler

    def filtro(tipo, contexto, mensaje):
        if "Could not register app ID" in mensaje:
            return
        destino = sys.stderr if tipo != QtMsgType.QtInfoMsg else sys.stdout
        print(mensaje, file=destino)

    qInstallMessageHandler(filtro)


def build_parser():
    """Las opciones de la ventana, en inglés y con su alias en español.

    Aparte de `build_app` para poder leerlas sin crear la aplicación. Los
    textos salen del idioma que haya puesto quien llama.
    """
    from ..options import Parser, epilog_for_terminal, how_to_call

    ventana, _terminal = how_to_call()
    parser = Parser(prog=ventana, description=_("gui.description"),
                    epilog=epilog_for_terminal())
    parser.add_argument("--interval", type=float, metavar=_("cli.metavar.seconds"),
                        help=_("gui.opt.interval"))
    parser.add_argument("--dark", action="store_true", help=_("gui.opt.dark"))
    parser.add_argument("--light", action="store_true", help=_("gui.opt.light"))
    parser.add_argument("--compact", action="store_true", help=_("gui.opt.compact"))
    parser.add_argument("--font-scale", metavar=_("gui.metavar.size"),
                        choices=(*TAMANOS_DE_LETRA, *TAMANOS_DE_LETRA.values()),
                        help=_("gui.opt.fontscale"))
    parser.add_argument("--size", metavar=_("gui.metavar.window"), help=_("gui.opt.size"))
    parser.add_argument("--anonymous", action="store_true", help=_("gui.opt.anonymous"))
    parser.add_argument("--screenshot", metavar=_("cli.metavar.file"),
                        help=_("gui.opt.screenshot"))
    parser.add_argument("--samples", type=int, metavar="N", default=MUESTRAS_DE_CAPTURA,
                        help=_("gui.opt.samples"))
    parser.add_argument("--page", metavar=_("gui.metavar.page"), help=_("gui.opt.page"))
    for espanol, ingles in (("--intervalo", "--interval"), ("--oscuro", "--dark"),
                            ("--claro", "--light"), ("--compacto", "--compact"),
                            ("--letra", "--font-scale"), ("--tamano", "--size"),
                            ("--anonimo", "--anonymous"), ("--captura", "--screenshot"),
                            ("--muestras", "--samples"), ("--pagina", "--page")):
        parser.alias(espanol, de=ingles)
    return parser


def build_app(argv: Optional[list[str]] = None) -> tuple[QApplication, MainWindow, argparse.Namespace]:
    # El idioma antes de las opciones: la ayuda sale en el de la interfaz.
    i18n.set_language(prefs_module.load().language)
    parser = build_parser()
    args = parser.parse_args(argv)

    from dataclasses import replace

    guardadas = prefs = prefs_module.load()
    if args.interval is not None:
        prefs = replace(prefs, interval_s=args.interval)
    if args.dark:
        prefs = replace(prefs, theme="dark")
    if args.light:
        prefs = replace(prefs, theme="light")
    if args.compact:
        prefs = replace(prefs, density="compact")
    if args.font_scale:
        prefs = replace(prefs, font_scale=TAMANOS_DE_LETRA.get(args.font_scale,
                                                              args.font_scale))
    if args.size and "x" in args.size:
        width, _sep, height = args.size.partition("x")
        if width.isdigit() and height.isdigit():
            prefs = replace(prefs, window_width=int(width), window_height=int(height))
    prefs = prefs.normalized()
    # Lo que la línea de órdenes cambió respecto a lo guardado, para que la
    # ventana no lo guarde como si fuera una preferencia.
    forzadas = {campo: (getattr(guardadas, campo), getattr(prefs, campo))
                for campo in ("interval_s", "theme", "density", "font_scale",
                              "window_width", "window_height")
                if getattr(guardadas, campo) != getattr(prefs, campo)}

    _callar_el_portal()
    # El identificador de la entrada de menú que abre esta copia: `silux`, o
    # `silux-dev` desde el repositorio. En Wayland el compositor no adivina
    # qué ventana pertenece a qué entrada: lo saca de `setDesktopFileName`, y
    # sin él la barra de tareas de Plasma enseña un icono genérico aunque el
    # .desktop esté bien instalado. En X11 se compara `StartupWMClass` con la
    # clase de la ventana, que Qt forma con el nombre del programa (el primer
    # argumento) y el de la aplicación: los dos, el identificador.
    identificador = desktop.current_launcher().app_id
    app = QApplication([identificador])
    app.setApplicationName(identificador)
    app.setApplicationDisplayName("Silux")
    app.setApplicationVersion(__version__)
    app.setDesktopFileName(identificador)
    app.setWindowIcon(application_icon())

    # Antes de montar nada: las páginas traducen sus títulos al construirse, y
    # si el idioma llega después se quedan con el que hubiera. Guardarlo y
    # volver a abrir el programa devolvía la interfaz al español.
    i18n.set_language(prefs.language)
    theme.apply(app, prefs.theme, prefs.density, prefs.font_scale)

    return app, MainWindow(prefs, forzadas=forzadas), args


# Cuántas muestras se toman antes de una captura si no se dice otra cosa.
MUESTRAS_DE_CAPTURA = 10

# Los tamaños de letra de `--font-scale`, en inglés como las opciones, y el
# valor que guardan las preferencias. Los de las preferencias valen también.
TAMANOS_DE_LETRA = {"normal": "normal", "large": "grande", "larger": "mayor",
                    "largest": "máximo"}


def _anonimizador(activo: bool):
    """Lo que se le hace a cada foto antes de pintarla, si se pidió.

    Una captura de pantalla lleva el nombre del equipo y el número de serie
    de la gráfica, igual que el informe de fallos, y acaba en los mismos
    sitios públicos. Aquí se cambian por otros de la misma pinta.
    """
    if not activo:
        return lambda foto: foto
    from ..privacidad import anonimizar
    return anonimizar


def main(argv: Optional[list[str]] = None) -> int:
    app, window, args = build_app(argv)

    # Antes de las dos ramas y una sola vez. Un nombre que no existe se tragaba
    # sin decir nada, y en la de la captura eso es peor que un fallo: el archivo
    # se escribe, el programa dice «captura guardada» y dentro está la página
    # que no era. Para una bandera cuyo único uso es automatizar capturas —para
    # documentación, para un informe— entregar la equivocada en silencio es
    # justo lo que no puede hacer.
    if args.page and not window.select_section(args.page):
        print(_("app.page.unknown").format(nombre=args.page), file=sys.stderr)
        print(_("app.page.available").format(
            lista=", ".join(window.section_names())), file=sys.stderr)
        return 2

    if args.screenshot:
        from ..collector import Collector

        window.show()
        collector = Collector()
        collector.snapshot()
        preparar = _anonimizador(args.anonymous)
        # Las justas para que haya cifras derivadas, o las que se pidan: con
        # diez seguidas las gráficas de las fichas salen en una esquina, que
        # está bien para ver una página y mal para enseñar cómo queda.
        pausa = args.interval if args.interval and args.samples != MUESTRAS_DE_CAPTURA else 0.08
        for _paso in range(max(2, args.samples)):
            time.sleep(pausa)
            window._on_sample(preparar(collector.snapshot()))
            app.processEvents()
        if args.page and (motivo := seccion_que_falta(window, args.page)):
            print(motivo, file=sys.stderr)
            return 2
        # Una sola pasada de eventos no basta: los layouts anidados dentro del
        # área de desplazamiento necesitan asentarse antes de grabar.
        QTimer.singleShot(400, app.quit)
        app.exec()
        # La imagen se lleva dentro si se hizo anónima o no. Es lo único que
        # deja comprobarlo después: `tools/comprobar_privacidad.py` busca texto
        # y una captura es un mapa de píxeles, así que sin esta marca dio por
        # buena una con la MAC y la IPv6 pública de esta máquina a la vista.
        # El valor va sin tildes a propósito, y no por descuido del idioma: es
        # un metadato que lee un script, no texto de ventana. Con «sí», Qt lo
        # escribe en Latin-1 dentro del PNG —`s\xed`— y quien lo busque en
        # UTF-8 no lo encuentra; en ASCII no hay dos formas de escribirlo.
        imagen = window.grab().toImage()
        imagen.setText("silux-anonimo",
                       "anonima" if args.anonymous else "identificable")
        imagen.save(args.screenshot)
        print(f"captura guardada en {args.screenshot}")
        return 0

    window.show()
    window.start()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
