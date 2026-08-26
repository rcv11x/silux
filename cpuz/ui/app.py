"""Ventana principal.

La navegación es una lista lateral en vez de pestañas superiores: caben más
secciones, se leen mejor los nombres largos y deja sitio para marcar cuáles
están disponibles. Las que aún no existen se ven en gris, para que se sepa
qué falta en lugar de fingir que la aplicación está completa.

Cambiar de tema o de densidad reconstruye la interfaz en vez de repintarla
pieza a pieza. Es una operación de milisegundos, ocurre solo cuando el
usuario toca un ajuste, y evita tener que propagar la paleta a mano por doce
clases —que es justo donde se cuelan los widgets que se quedan del color
anterior. El hilo de muestreo no se toca, así que no se pierde ni una
lectura ni el histórico de las gráficas.
"""

from __future__ import annotations

import argparse
import sys
import time
from typing import Optional

import pathlib

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QIcon
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

from .. import __version__, settings as prefs_module
from ..model import Snapshot
from ..settings import Preferences
from ..tracking import Tracker
from . import theme
from .pages.board import BoardPage
from .pages.caches import CachesPage
from .pages.cpu import CpuPage
from .pages.memory import MemoryPage
from .pages.monitor import MonitorPage
from .pages.settings import SettingsPage
from .pages.system import SystemPage
from .sampler import Sampler
from .theme import ui_font
from .widgets import ElidingLabel

# (etiqueta, ¿implementada?)
# El orden separa las dos preguntas del programa: qué hardware es esto
# (CPU, Cachés, Placa base…) y qué está haciendo ahora (Monitor).
SECTIONS = (
    ("CPU", True),
    ("Monitor", True),
    ("Cachés", True),
    ("Placa base", True),
    ("Memoria", True),
    ("Sistema", True),
    ("Gráficos", False),
    ("Ajustes", True),
)

# Por debajo de este ancho la barra lateral estorba más de lo que ayuda.
NAV_HIDE_BELOW = 620

# Debe coincidir con el nombre del fichero .desktop instalado, sin extensión.
DESKTOP_ID = "cpuz"
BUNDLED_ICON = pathlib.Path(__file__).parent / "assets" / "cpuz.svg"


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
        self.setWindowTitle("cpuz")
        self.resize(prefs.window_width, prefs.window_height)
        self.setMinimumSize(theme.METRICS.min_window_w, theme.METRICS.min_window_h)

        self._last_snapshot: Optional[Snapshot] = None
        self._palette = theme.resolve(QApplication.instance(), prefs.theme)
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
        self.system_page = SystemPage(self._palette, self.prefs)
        self.settings_page = SettingsPage(self.prefs)
        self.settings_page.changed.connect(self._on_preferences)
        for page in (self.cpu_page, self.monitor_page, self.caches_page,
                     self.board_page, self.memory_page, self.system_page,
                     self.settings_page):
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

        wordmark = QLabel("cpuz")
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

    def _on_preferences(self, prefs: Preferences) -> None:
        from dataclasses import replace

        previous = self.prefs
        self.prefs = prefs
        prefs_module.save(prefs)

        if prefs.interval_ms != previous.interval_ms and hasattr(self, "sampler"):
            self.sampler.set_interval(prefs.interval_ms)

        appearance_changed = (prefs.theme, prefs.density) != (previous.theme, previous.density)
        content_changed = (prefs.temperature_unit, prefs.show_all_features) != (
            previous.temperature_unit, previous.show_all_features
        )

        if prefs.density != previous.density:
            # Los anchos guardados se midieron con otra tipografía y otro
            # espaciado; conservarlos deja columnas que no encajan.
            self.prefs = replace(self.prefs, sensor_columns=())
            prefs_module.save(self.prefs)

        if appearance_changed:
            self._palette = theme.apply(QApplication.instance(), prefs.theme, prefs.density)
            self._build_ui()
        elif content_changed:
            self._build_ui()

    def _on_sample(self, snapshot: Snapshot) -> None:
        self._last_snapshot = snapshot
        if not self.memory_page.elevation_button.isEnabled():
            self.memory_page.elevation_button.setEnabled(True)
            self.memory_page.elevation_button.setText("Leer con permisos de administrador")
        self._distribute(snapshot)

        text = (f"Cada {self.prefs.interval_s:g} s · {len(snapshot.sensors)} sensores · "
                f"{', '.join(sorted(snapshot.capabilities)) or 'sin fuentes'}")
        if blocked := sum(1 for n in snapshot.notes if n.need.value == "root"):
            text += f" · {blocked} dato(s) requieren permisos"
        self._status.set_full_text(text)

    def _on_elevation_requested(self) -> None:
        """El usuario ha pedido los datos que exigen privilegios.

        Solo se deja la petición apuntada: el diálogo de autenticación lo abre
        el hilo de muestreo, que puede bloquear sin congelar la ventana. Se le
        da un toque para que no haya que esperar al siguiente intervalo.
        """
        self.memory_page.elevation_button.setEnabled(False)
        self.memory_page.elevation_button.setText("Esperando autorización…")
        self.sampler.request_elevation()

    def _on_columns_resized(self, widths: tuple) -> None:
        from dataclasses import replace

        if tuple(widths) != tuple(self.prefs.sensor_columns):
            self.prefs = replace(self.prefs, sensor_columns=tuple(widths))

    def _distribute(self, snapshot: Snapshot) -> None:
        for page in (self.cpu_page, self.monitor_page, self.caches_page,
                     self.board_page, self.memory_page, self.system_page):
            page.apply(snapshot)

    def _on_failure(self, message: str) -> None:
        self._status.set_full_text(f"Fallo en el muestreo: {message}")


def build_app(argv: Optional[list[str]] = None) -> tuple[QApplication, MainWindow, argparse.Namespace]:
    parser = argparse.ArgumentParser(prog="cpuz-gui", description="Perfilador de hardware.")
    parser.add_argument("--interval", type=float, metavar="SEGUNDOS",
                        help="anula el intervalo guardado solo para esta ejecución")
    parser.add_argument("--dark", action="store_true", help="fuerza el tema oscuro")
    parser.add_argument("--light", action="store_true", help="fuerza el tema claro")
    parser.add_argument("--compact", action="store_true", help="fuerza la densidad compacta")
    parser.add_argument("--size", metavar="ANCHOxALTO", help="tamaño de ventana, p. ej. 820x620")
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
    if args.size and "x" in args.size:
        width, _, height = args.size.partition("x")
        if width.isdigit() and height.isdigit():
            prefs = replace(prefs, window_width=int(width), window_height=int(height))
    prefs = prefs.normalized()

    app = QApplication(sys.argv[:1])
    app.setApplicationName("cpuz")
    app.setApplicationDisplayName("cpuz")
    app.setApplicationVersion(__version__)
    # En Wayland el compositor no adivina qué ventana pertenece a qué entrada
    # de menú: lo saca de aquí. Sin esta línea, la barra de tareas de Plasma
    # enseña un icono genérico aunque el .desktop esté bien instalado.
    app.setDesktopFileName(DESKTOP_ID)
    app.setWindowIcon(application_icon())

    theme.apply(app, prefs.theme, prefs.density)

    return app, MainWindow(prefs), args


def main(argv: Optional[list[str]] = None) -> int:
    app, window, args = build_app(argv)

    if args.screenshot:
        from ..collector import Collector

        if args.page:
            window.select_section(args.page)
        window.show()
        collector = Collector()
        collector.snapshot()
        for _ in range(10):
            time.sleep(0.08)
            window._on_sample(collector.snapshot())
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
