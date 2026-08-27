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
import sys
import time
from typing import Optional

import pathlib

from PySide6.QtCore import Qt, QElapsedTimer, QTimer
from PySide6.QtGui import QIcon, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QStackedWidget,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from .. import EMOJI, __version__, settings as prefs_module
from ..model import Snapshot
from ..settings import ACCENT_NAMES, Preferences
from ..tracking import Tracker
from . import theme
from .pages.board import BoardPage
from .pages.caches import CachesPage
from .pages.cpu import CpuPage
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
SECTIONS = (
    ("CPU", True),
    ("Cachés", True),
    ("Placa base", True),
    ("Memoria", True),
    ("Gráficos", True),
    ("Almacenamiento", True),
    ("Red", True),
    ("Sistema", True),
    ("Rendimiento", True),
    ("Sensores", True),
    ("Ajustes", True),
)

# Por debajo de este ancho la barra lateral estorba más de lo que ayuda.
NAV_HIDE_BELOW = 620

# Debe coincidir con el nombre del fichero .desktop instalado, sin extensión.
DESKTOP_ID = "silux"
BUNDLED_ICON = pathlib.Path(__file__).parent / "assets" / "silux.svg"


def application_icon() -> QIcon:
    """El icono del tema si está instalado; si no, el que viaja en el paquete.

    Así la ventana tiene icono aunque se ejecute desde el código fuente sin
    haber pasado por tools/install_desktop.py.
    """
    icon = QIcon.fromTheme(DESKTOP_ID)
    if not icon.isNull():
        return icon
    return QIcon(str(BUNDLED_ICON)) if BUNDLED_ICON.exists() else QIcon()


class MainWindow(QMainWindow):
    def __init__(self, prefs: Preferences):
        super().__init__()
        self.prefs = prefs
        self.setWindowTitle("Silux")
        self.resize(prefs.window_width, prefs.window_height)
        self.setMinimumSize(theme.METRICS.min_window_w, theme.METRICS.min_window_h)

        self._last_snapshot: Optional[Snapshot] = None
        self._palette = theme.palette_for(QApplication.instance(), prefs.theme,
                                          prefs.accent)
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
        self._status = ElidingLabel("Iniciando el muestreo…")
        self._status.setObjectName("Muted")
        self.statusBar().addWidget(self._status, 1)
        self._sources = ElidingLabel("")
        self._sources.setObjectName("Muted")
        self._sources.setMaximumWidth(220)
        self.statusBar().addPermanentWidget(self._sources)

        self._build_ui()

        self.sampler = Sampler(interval_ms=prefs.interval_ms)
        self.sampler.sampled.connect(self._on_sample)
        self.sampler.failed.connect(self._on_failure)

        # Uno solo para todas las gráficas. Con cuarenta y tantas en pantalla,
        # cuarenta temporizadores despertando por su cuenta cuestan más que
        # todo lo que se dibuja.
        self._congelado = False
        self._desde_la_muestra = QElapsedTimer()
        self._latido = QTimer(self)
        self._latido.setInterval(33)                  # unos 30 por segundo
        self._latido.timeout.connect(self._avanzar_graficas)
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

        central = QWidget()
        central.setObjectName("Root")

        layout = QHBoxLayout(central)
        layout.setContentsMargins(8, 8, 8, 4)
        layout.setSpacing(6)

        self.nav_panel = self._build_nav()
        layout.addWidget(self.nav_panel, 0)

        self.stack = QStackedWidget()
        self.cpu_page = CpuPage(self._palette, self.prefs)
        self.monitor_page = MonitorPage(self._palette, self.prefs, self._tracker)
        self.monitor_page.columns_resized.connect(self._on_columns_resized)
        self.caches_page = CachesPage(self._palette, self.prefs)
        self.board_page = BoardPage(self._palette, self.prefs)
        self.memory_page = MemoryPage(self._palette, self.prefs)
        self.memory_page.elevation_requested.connect(self._on_elevation_requested)
        self.graphics_page = GraphicsPage(self._palette, self.prefs)
        self.storage_page = StoragePage(self._palette, self.prefs)
        self.storage_page.elevation_requested.connect(self._on_elevation_requested)
        self.network_page = NetworkPage(self._palette, self.prefs)
        self.network_page.unit_changed.connect(self._on_network_unit)
        self.system_page = SystemPage(self._palette, self.prefs)
        self.performance_page = PerformancePage(self._palette, self.prefs)
        self.settings_page = SettingsPage(self.prefs)
        self.settings_page.changed.connect(self._on_preferences)
        self.settings_page.report_requested.connect(self._on_report_requested)
        for page in (self.cpu_page, self.caches_page, self.board_page,
                     self.memory_page, self.graphics_page, self.storage_page,
                     self.network_page, self.system_page, self.performance_page,
                     self.monitor_page, self.settings_page):
            self.stack.addWidget(page)
        layout.addWidget(self.stack, 1)

        self.setCentralWidget(central)

        self._status.setFont(ui_font(m.small_pt))
        self._sources.setFont(ui_font(m.small_pt))
        self._sources.set_full_text(self._sources_text())

        self._compact_nav.blockSignals(True)
        self._compact_nav.clear()
        for row, (name, enabled) in enumerate(SECTIONS):
            if enabled:
                self._compact_nav.addItem(name, row)
        self._compact_nav.blockSignals(False)

        if 0 <= current_row < self.nav.count():
            self.nav.setCurrentRow(current_row)
        self._sync_nav_visibility()

        if self._last_snapshot is not None:
            self._distribute(self._last_snapshot)

    def _build_nav(self) -> QWidget:
        m = theme.METRICS
        panel = QWidget()
        panel.setFixedWidth(m.nav_width)

        column = QVBoxLayout(panel)
        column.setContentsMargins(2, 6, 2, 6)
        column.setSpacing(4)

        wordmark = QLabel(f"{EMOJI} Silux")
        wordmark.setObjectName("Headline")
        wordmark.setContentsMargins(10, 0, 0, 0)

        version = QLabel(f"versión {__version__}")
        version.setObjectName("Muted")
        version.setFont(ui_font(max(7, m.small_pt - 1)))
        version.setContentsMargins(10, 0, 0, 4)

        self.nav = QListWidget()
        self.nav.setObjectName("Nav")
        self.nav.setFont(ui_font(m.base_pt))
        self.nav.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.nav.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        stack_index = 0
        for name, enabled in SECTIONS:
            item = QListWidgetItem(name)
            if enabled:
                item.setData(Qt.ItemDataRole.UserRole, stack_index)
                stack_index += 1
            else:
                item.setFlags(Qt.ItemFlag.NoItemFlags)
                item.setToolTip("Todavía no implementado")
            self.nav.addItem(item)
        self.nav.setCurrentRow(0)
        self.nav.currentRowChanged.connect(self._on_section)

        column.addWidget(wordmark)
        column.addWidget(version)
        column.addWidget(self.nav, 1)
        return panel

    def _sources_text(self) -> str:
        from .. import db

        if not db.available():
            return "sin base de datos"
        counts = db.load().get("counts", {})
        total = counts.get("x86_intel", 0) + counts.get("x86_amd", 0)
        return f"{total} procesadores en la base"

    # -- ciclo de vida ------------------------------------------------------

    def start(self) -> None:
        self.sampler.start()

    def closeEvent(self, event) -> None:  # noqa: N802
        self.sampler.stop()
        from dataclasses import replace

        prefs_module.save(replace(self.prefs,
                                  window_width=self.width(),
                                  window_height=self.height()))
        super().closeEvent(event)

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._sync_nav_visibility()

    def select_section(self, name: str) -> None:
        for row in range(self.nav.count()):
            if self.nav.item(row).text().lower() == name.lower():
                self.nav.setCurrentRow(row)
                self._on_section(row)
                return

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
        """Guarda el informe que se adjunta al reportar un fallo."""
        from PySide6.QtWidgets import QFileDialog, QMessageBox

        from .. import report

        if self._last_snapshot is None:
            QMessageBox.information(self, "Informe",
                                    "Todavía no hay ninguna lectura del equipo.")
            return

        sugerido = str(pathlib.Path.home() / "informe-silux.md")
        destino, _ = QFileDialog.getSaveFileName(
            self, "Guardar informe del equipo", sugerido, "Markdown (*.md);;Texto (*.txt)")
        if not destino:
            return

        try:
            texto = report.build(self._last_snapshot, anonymous=True)
            pathlib.Path(destino).write_text(texto, encoding="utf-8")
        except OSError as error:
            QMessageBox.warning(self, "Informe", f"No se pudo guardar:\n{error}")
            return
        QMessageBox.information(
            self, "Informe",
            f"Guardado en {destino}\n\n"
            "No incluye el nombre del equipo, las direcciones IP y MAC ni los "
            "números de serie.",
        )

    def _on_network_unit(self, unidad: str) -> None:
        """El conmutador de bytes/bits de la pestaña de Red."""
        from dataclasses import replace

        self._on_preferences(replace(self.prefs, network_unit=unidad))

    def _on_preferences(self, prefs: Preferences) -> None:
        from dataclasses import replace

        previous = self.prefs
        self.prefs = prefs
        prefs_module.save(prefs)

        if prefs.interval_ms != previous.interval_ms and hasattr(self, "sampler"):
            self.sampler.set_interval(prefs.interval_ms)

        if prefs.fluid_charts != previous.fluid_charts:
            self._aplicar_fluidez()

        appearance_changed = ((prefs.theme, prefs.density, prefs.font_scale, prefs.accent)
                              != (previous.theme, previous.density, previous.font_scale,
                                  previous.accent))
        content_changed = (prefs.temperature_unit, prefs.show_all_features,
                           prefs.network_unit) != (
            previous.temperature_unit, previous.show_all_features,
            previous.network_unit
        )

        if (prefs.density, prefs.font_scale) != (previous.density, previous.font_scale):
            # Los anchos guardados se midieron con otra tipografía y otro
            # espaciado; conservarlos deja columnas que no encajan.
            self.prefs = replace(self.prefs, sensor_columns=())
            prefs_module.save(self.prefs)

        if appearance_changed:
            self._palette = theme.apply(QApplication.instance(), prefs.theme,
                                        prefs.density, prefs.font_scale, prefs.accent)
            self._build_ui()
        elif content_changed:
            self._build_ui()

    def _aplicar_fluidez(self) -> None:
        """Enciende o apaga el deslizamiento de las gráficas."""
        if self.prefs.fluid_charts and not self._congelado:
            self._latido.start()
        else:
            self._latido.stop()
            # Sin animación, cada gráfica se queda en su sitio definitivo.
            for grafica in self._graficas():
                grafica.advance(1.0)

    def _graficas(self, solo_visibles: bool = False):
        """Las gráficas de la ventana; las de las páginas cerradas no cuentan.

        Qt no repinta un widget oculto, así que avisarlas es gasto tonto: de
        las dieciséis que hay montadas, en pantalla no llegan a cinco.
        """
        from .widgets import Sparkline
        graficas = self.findChildren(Sparkline)
        return [g for g in graficas if g.isVisible()] if solo_visibles else graficas

    def _avanzar_graficas(self) -> None:
        if self._congelado or not self._desde_la_muestra.isValid():
            return
        intervalo = max(1, self.prefs.interval_ms)
        fase = self._desde_la_muestra.elapsed() / intervalo
        for grafica in self._graficas(solo_visibles=True):
            grafica.advance(fase)

    def alternar_congelado(self) -> None:
        """Para lo que se pinta, para poder leer un pico antes de que se vaya.

        La recolección sigue: los mínimos y máximos no se pierden por mirar.
        Al soltar, la ventana se pone al día con la muestra que haya.
        """
        self._congelado = not self._congelado
        self._aplicar_fluidez()
        if self._congelado:
            self._status.set_full_text(
                "Congelado · pulsa espacio para seguir")
        elif self._last_snapshot is not None:
            self._on_sample(self._last_snapshot)

    def _on_sample(self, snapshot: Snapshot) -> None:

        self._last_snapshot = snapshot
        self._desde_la_muestra.restart()
        if self._congelado:
            # Los datos siguen entrando: los mínimos y máximos no se pierden
            # por mirar. Lo que se para es lo que se pinta.
            return
        for boton in (self.memory_page.elevation_button,
                      self.storage_page.elevation_button):
            if not boton.isEnabled():
                boton.setEnabled(True)
                boton.setText("Leer con permisos de administrador")
        self._distribute(snapshot)

        partes = [f"Se actualiza cada {self.prefs.interval_s:g} s"]
        if bloqueados := sum(1 for n in snapshot.notes if n.need.value == "root"):
            # El plural va bien puesto: «1 dato(s)» delataba que nadie lo había
            # mirado, en un programa cuyo argumento es que los datos están
            # cuidados.
            partes.append(f"{bloqueados} "
                          f"{'dato requiere' if bloqueados == 1 else 'datos requieren'} "
                          "permisos")
        partes.append(f"{len(snapshot.sensors)} sensores")
        partes.append(", ".join(sorted(snapshot.capabilities)) or "sin fuentes")
        self._status.set_full_text(" · ".join(partes))

    def _on_elevation_requested(self) -> None:
        """El usuario ha pedido los datos que exigen privilegios.

        Solo se deja la petición apuntada: el diálogo de autenticación lo abre
        el hilo de muestreo, que puede bloquear sin congelar la ventana. Se le
        da un toque para que no haya que esperar al siguiente intervalo.
        """
        # Los dos botones piden lo mismo y se lanza un solo ayudante, así que
        # los dos se quedan esperando a la vez.
        for boton in (self.memory_page.elevation_button,
                      self.storage_page.elevation_button):
            boton.setEnabled(False)
            boton.setText("Esperando autorización…")
        self.sampler.request_elevation()

    def _on_columns_resized(self, widths: tuple) -> None:
        from dataclasses import replace

        if tuple(widths) != tuple(self.prefs.sensor_columns):
            self.prefs = replace(self.prefs, sensor_columns=tuple(widths))

    def _distribute(self, snapshot: Snapshot) -> None:
        for page in (self.cpu_page, self.monitor_page, self.caches_page,
                     self.board_page, self.memory_page, self.system_page,
                     self.graphics_page, self.network_page, self.storage_page):
            page.apply(snapshot)

    def _on_failure(self, message: str) -> None:
        self._status.set_full_text(f"Fallo en el muestreo: {message}")


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


def build_app(argv: Optional[list[str]] = None) -> tuple[QApplication, MainWindow, argparse.Namespace]:
    parser = argparse.ArgumentParser(prog="silux-gui", description="Perfilador de hardware.")
    parser.add_argument("--interval", type=float, metavar="SEGUNDOS",
                        help="anula el intervalo guardado solo para esta ejecución")
    parser.add_argument("--dark", action="store_true", help="fuerza el tema oscuro")
    parser.add_argument("--light", action="store_true", help="fuerza el tema claro")
    parser.add_argument("--compact", action="store_true", help="fuerza la densidad compacta")
    parser.add_argument("--font-scale", metavar="TAMAÑO", choices=("normal", "grande", "mayor", "máximo"),
                        help="fuerza el tamaño de letra solo para esta ejecución")
    parser.add_argument("--accent", metavar="COLOR", choices=ACCENT_NAMES,
                        help="fuerza el color de acento solo para esta ejecución")
    parser.add_argument("--size", metavar="ANCHOxALTO", help="tamaño de ventana, p. ej. 820x620")
    parser.add_argument("--anonimo", action="store_true",
                        help="oculta lo que identifica al equipo: nombre, "
                             "direcciones y números de serie")
    parser.add_argument("--screenshot", metavar="RUTA",
                        help="captura la ventana en un PNG y sale (útil sin pantalla)")
    parser.add_argument("--page", metavar="NOMBRE", help="sección a mostrar al abrir")
    args = parser.parse_args(argv)

    from dataclasses import replace

    prefs = prefs_module.load()
    if args.interval is not None:
        prefs = replace(prefs, interval_s=args.interval)
    if args.dark:
        prefs = replace(prefs, theme="dark")
    if args.light:
        prefs = replace(prefs, theme="light")
    if args.compact:
        prefs = replace(prefs, density="compact")
    if args.font_scale:
        prefs = replace(prefs, font_scale=args.font_scale)
    if args.accent:
        prefs = replace(prefs, accent=args.accent)
    if args.size and "x" in args.size:
        width, _, height = args.size.partition("x")
        if width.isdigit() and height.isdigit():
            prefs = replace(prefs, window_width=int(width), window_height=int(height))
    prefs = prefs.normalized()

    _callar_el_portal()
    app = QApplication(sys.argv[:1])
    app.setApplicationName("silux")
    app.setApplicationDisplayName("Silux")
    app.setApplicationVersion(__version__)
    # En Wayland el compositor no adivina qué ventana pertenece a qué entrada
    # de menú: lo saca de aquí. Sin esta línea, la barra de tareas de Plasma
    # enseña un icono genérico aunque el .desktop esté bien instalado.
    app.setDesktopFileName(DESKTOP_ID)
    app.setWindowIcon(application_icon())

    theme.apply(app, prefs.theme, prefs.density, prefs.font_scale, prefs.accent)

    return app, MainWindow(prefs), args


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

    if args.screenshot:
        from ..collector import Collector

        if args.page:
            window.select_section(args.page)
        window.show()
        collector = Collector()
        collector.snapshot()
        preparar = _anonimizador(args.anonimo)
        for _ in range(10):
            time.sleep(0.08)
            window._on_sample(preparar(collector.snapshot()))
        # Una sola pasada de eventos no basta: los layouts anidados dentro del
        # área de desplazamiento necesitan asentarse antes de grabar.
        QTimer.singleShot(400, app.quit)
        app.exec()
        window.grab().save(args.screenshot)
        print(f"captura guardada en {args.screenshot}")
        return 0

    if args.page:
        window.select_section(args.page)

    window.show()
    window.start()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
