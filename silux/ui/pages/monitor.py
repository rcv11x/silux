"""Página de Monitor: todo lo que cambia con el tiempo.

Separar esto de la pestaña de CPU no es cosmética. Antes una sola página
respondía a dos preguntas («qué procesador es este» y «qué está haciendo
ahora») y no servía bien a ninguna: para mirar el socket había que pasar por
encima de gráficas, y para vigilar temperaturas había que pasar por encima de
la familia y el stepping. Aquí vive la segunda pregunta, con sitio para
hacerlo bien.

La columna de mínimos y máximos es lo que distingue a un monitor de hardware
de un visor de valores actuales: saber a cuánto llegó la temperatura mientras
jugabas importa más que saber a cuánto está ahora.
"""

from __future__ import annotations

import pathlib
from collections import defaultdict, deque
from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ... import render
from ...i18n import _
from ...model import Sensor, SensorKind, Snapshot
import os

from ... import registro
from ...privileged import cargar_modulo
from ...settings import Preferences
from ...tracking import Tracker
from .. import theme
from ..theme import Palette, ui_font
from ..widgets import (
    Card,
    CoreMatrix,
    Notice,
    ResponsiveRow,
    SensorTree,
    StatTile,
    clear_layout,
)

# Cuántos decimales tiene sentido enseñar en cada magnitud.
DECIMALS = {
    SensorKind.TEMPERATURE: 1,
    SensorKind.VOLTAGE: 3,
    SensorKind.FAN: 0,
    SensorKind.POWER: 1,
    SensorKind.CURRENT: 2,
    SensorKind.ENERGY: 0,
}


class MonitorPage(QScrollArea):
    # Lo emite el árbol cuando el usuario arrastra una columna; la ventana lo
    # guarda para que el ajuste sobreviva al cierre.
    columns_resized = Signal(tuple)
    branches_changed = Signal(tuple)

    def __init__(self, palette: Palette, prefs: Preferences, tracker: Tracker, parent=None):
        super().__init__(parent)
        self._p = palette
        self._prefs = prefs
        self._tracker = tracker
        m = theme.METRICS

        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        root = QWidget()
        root.setObjectName("Root")
        self.setWidget(root)

        self._layout = QVBoxLayout(root)
        self._layout.setContentsMargins(m.page_margin, m.page_margin, m.page_margin, m.page_margin)
        self._layout.setSpacing(m.section_gap)

        # Las cifras del procesador y la rejilla de núcleos se fueron a la
        # página de CPU, que es donde se buscan. Aquí ocupaban media pantalla
        # y dejaban el árbol —lo propio de esta página— en una rendija.
        sensors_card = Card()
        sensors_card.body.addWidget(self._build_sensor_header())
        self.tree = SensorTree(palette)
        self.tree.set_column_widths(prefs.sensor_columns)
        self.tree.set_collapsed(prefs.sensor_collapsed or None)
        self.tree.itemExpanded.connect(self._rama_movida)
        self.tree.itemCollapsed.connect(self._rama_movida)
        self.tree.columnsResized.connect(self.columns_resized)
        sensors_card.body.addWidget(self.tree)
        self._layout.addWidget(sensors_card)

        self._hint_host = QVBoxLayout()
        self._hint_host.setSpacing(6)
        self._layout.addLayout(self._hint_host)

        self._layout.addStretch(1)

        self._core_history: dict[int, deque] = defaultdict(lambda: deque(maxlen=40))
        self._structure: tuple = ()
        self._cuenta_completa = ""
        self._registro: Optional[registro.Registro] = None
        self._pendiente_abrir = False
        self._hint_signature: tuple = ()

    # -- construcción -------------------------------------------------------

    def _rama_movida(self, _item) -> None:
        self.tree.refresh_height()
        self.branches_changed.emit(self.tree.collapsed())

    def _build_sensor_header(self) -> QWidget:
        holder = QWidget()
        row = QHBoxLayout(holder)
        row.setContentsMargins(2, 4, 2, 0)
        row.setSpacing(10)

        title = QLabel(_("sensors.title"))
        title.setObjectName("CardTitle")

        self.count = QLabel("")
        self.count.setObjectName("Muted")
        self.count.setFont(ui_font(theme.METRICS.small_pt))

        self.search = QLineEdit()
        self.search.setPlaceholderText(_("sensors.search.placeholder"))
        self.search.setClearButtonEnabled(True)
        self.search.setToolTip(
            "Filtra por el nombre del sensor o del aparato.\n"
            "«memoria», «9070», «ventilador»…"
        )
        self.search.setFixedWidth(190)
        self.search.textChanged.connect(self._buscar)

        self.record_button = QPushButton(_("sensors.record.button"))
        self.record_button.setToolTip(
            "Escribe una fila por muestreo con todos los sensores.\n"
            "Se abre en cualquier hoja de cálculo, y sirve para ver en qué\n"
            "minuto pasó algo cuando ya no estabas mirando."
        )
        self.record_button.clicked.connect(self._alternar_registro)

        self.reset_button = QPushButton(_("sensors.reset.button"))
        self.reset_button.setToolTip(
            "Vuelve a empezar a contar los extremos desde este momento.\n"
            "Útil justo antes de lanzar una prueba de carga."
        )
        self.reset_button.clicked.connect(self._reset_extremes)

        row.addWidget(title)
        row.addWidget(self.count)
        row.addStretch(1)
        row.addWidget(self.search)
        row.addWidget(self.record_button)
        row.addWidget(self.reset_button)
        return holder

    # -- registro a CSV -----------------------------------------------------

    def _alternar_registro(self) -> None:
        from PySide6.QtWidgets import QFileDialog

        if self._registro is not None and self._registro.activo:
            self._registro.cerrar()
            self._pintar_estado_registro()
            return

        carpeta = registro.carpeta()
        carpeta.mkdir(parents=True, exist_ok=True)
        ruta, _filtro = QFileDialog.getSaveFileName(
            self, "Guardar el registro de sensores",
            str(carpeta / registro.nombre_sugerido()),
            _("csv.filter"))
        if not ruta:
            return
        self._registro = registro.Registro(pathlib.Path(ruta))
        self._pendiente_abrir = True
        self._pintar_estado_registro()

    def _pintar_estado_registro(self) -> None:
        """El botón dice qué hace ahora y, grabando, cuánto lleva."""
        activo = self._registro is not None and self._registro.activo
        pendiente = getattr(self, "_pendiente_abrir", False)
        if activo:
            # El plural va dentro de la clave y no fuera: en otras lenguas
            # no siempre son dos formas, y partir la frase para pegar el
            # número deja al traductor sin poder mover el orden.
            filas = self._registro.filas
            clave = ("sensors.record.stop.one" if filas == 1
                     else "sensors.record.stop.many")
            self.record_button.setText(_(clave).format(n=filas))
            self.record_button.setObjectName("Danger")
        elif pendiente:
            self.record_button.setText(_("sensors.record.starting"))
            self.record_button.setObjectName("Danger")
        else:
            self.record_button.setText(_("sensors.record.button"))
            self.record_button.setObjectName("")
        self.record_button.style().unpolish(self.record_button)
        self.record_button.style().polish(self.record_button)

    def cerrar_registro(self) -> None:
        """Al cerrar la ventana: el archivo se queda con lo que llevaba."""
        if self._registro is not None:
            self._registro.cerrar()

    def _buscar(self, texto: str) -> None:
        self.tree.set_filter(texto)
        self._actualizar_cuenta()

    def _actualizar_cuenta(self) -> None:
        """Buscando cuenta lo que queda; parado, lo que hay."""
        if self.search.text().strip():
            visibles = self.tree.coincidencias()
            clave = ("sensors.matches.none" if not visibles
                     else "sensors.matches.one" if visibles == 1
                     else "sensors.matches.many")
            self.count.setText(_(clave).format(n=visibles))
        else:
            self.count.setText(self._cuenta_completa)

    # -- actualización ------------------------------------------------------

    def apply(self, snapshot: Snapshot) -> None:
        self._apply_sensors(snapshot)
        self._apply_hints(snapshot)
        self._registrar(snapshot)

    def _registrar(self, snapshot: Snapshot) -> None:
        """La cabecera se escribe con el primer muestreo que llega después de
        pulsar, no en el momento de pulsar: así las columnas salen de una foto
        de verdad y no de la que hubiera cacheada."""
        if self._registro is None:
            return
        try:
            if self._pendiente_abrir:
                self._registro.abrir(snapshot)
                self._pendiente_abrir = False
            self._registro.escribir(snapshot)
        except OSError as error:
            self._registro.cerrar()
            self._registro = None
            self._pendiente_abrir = False
            self._aviso_de_registro(str(error))
        self._pintar_estado_registro()

    def _aviso_de_registro(self, detalle: str) -> None:
        from PySide6.QtWidgets import QMessageBox

        QMessageBox.warning(self, "Registro de sensores",
                            f"Se ha parado la grabación: {detalle}")

    def _temp(self, celsius: float) -> float:
        return celsius * 9 / 5 + 32 if self._prefs.fahrenheit else celsius

    def _apply_sensors(self, snapshot: Snapshot) -> None:
        tree = snapshot.sensor_tree()
        self._tracker.update_many((s.key, s.value) for s in snapshot.sensors)

        # La estructura solo cambia cuando aparece o desaparece hardware (al
        # cargar un módulo de sensores, por ejemplo), así que reconstruir es
        # excepcional y actualizar textos es lo normal.
        structure = tuple(
            (device, category, tuple(s.key for s in sensors))
            for device, categories in tree.items()
            for category, sensors in categories.items()
        )
        if structure != self._structure:
            self.tree.rebuild(tree)
            self._structure = structure
            self._cuenta_completa = (
                _("sensors.count.one" if len(tree) == 1
                  else "sensors.count.many").format(
                      n=len(snapshot.sensors), aparatos=len(tree))
            )
            self._actualizar_cuenta()

        avisos: dict[str, list[str]] = {}
        for sensor in snapshot.sensors:
            seguimiento = self._tracker.get(sensor.key)
            self.tree.update_row(
                sensor.key, self._values(sensor), self._tooltip(sensor),
                sensor.alarm_level,
                seguimiento.history if seguimiento else None,
                sensor.heat or 0.0,
                self._calor_del_maximo(sensor, seguimiento),
            )
            if sensor.alarm_level != "ok":
                avisos.setdefault(sensor.device, []).append(sensor.alarm_level)

        # El aviso tiene que llegar a la rama cerrada: con ocho aparatos y cien
        # sensores, uno en rojo dentro de una rama plegada no lo ve nadie.
        for device in tree:
            niveles = avisos.get(device, [])
            self.tree.marcar_aviso(device, len(niveles), "crítico" in niveles)

    @staticmethod
    def _calor_del_maximo(sensor: Sensor, seguimiento) -> float:
        """Lo cerca que llegó del umbral, que no es lo mismo que dónde está.

        Se pregunta al propio sensor sustituyendo su lectura por el máximo:
        así la escala y el umbral son los suyos y no hay que repetirlos aquí.
        """
        import dataclasses

        if seguimiento is None or sensor.heat is None:
            return 0.0
        return dataclasses.replace(sensor, value=seguimiento.maximum).heat or 0.0

    def _values(self, sensor: Sensor) -> list[str]:
        digits = DECIMALS.get(sensor.kind, 1)
        value, unit = self._converted(sensor)
        current = f"{value:.{digits}f} {unit}".strip()

        extremes = self._tracker.get(sensor.key)
        if extremes is None:
            return [current, "—", "—", "—"]

        low, high, average = (self._convert(sensor, v) for v in
                              (extremes.minimum, extremes.maximum, extremes.average))
        return [current, f"{low:.{digits}f}", f"{high:.{digits}f}", f"{average:.{digits}f}"]

    def _convert(self, sensor: Sensor, value: float) -> float:
        if sensor.kind is SensorKind.TEMPERATURE and self._prefs.fahrenheit:
            return value * 9 / 5 + 32
        return value

    def _converted(self, sensor: Sensor) -> tuple[float, str]:
        if sensor.kind is SensorKind.TEMPERATURE and self._prefs.fahrenheit:
            return sensor.value * 9 / 5 + 32, "°F"
        return sensor.value, sensor.unit

    def _tooltip(self, sensor: Sensor) -> str:
        lines = [f"{sensor.chip} · {sensor.key}"]
        limits = []
        if sensor.low is not None:
            limits.append(f"mínimo declarado {sensor.low:g} {sensor.unit}")
        if sensor.high is not None:
            limits.append(f"máximo declarado {sensor.high:g} {sensor.unit}")
        if sensor.critical is not None:
            limits.append(f"crítico {sensor.critical:g} {sensor.unit}")
        if limits:
            lines.append("\n".join(limits))
        if sensor.estimated_limits:
            lines.append("Este sensor no publica sus límites: los de arriba los "
                         "estima silux por el chip que es, y van del lado "
                         "prudente.")
        if sensor.alarm_level == "crítico":
            lines.append("⚠  Ha llegado al umbral crítico. Es donde el equipo "
                         "empieza a protegerse solo.")
        elif sensor.alarm_level == "alto":
            lines.append("⚠  Por encima del umbral alto. No es una avería, pero "
                         "conviene saberlo.")
        return "\n\n".join(lines)

    def _apply_hints(self, snapshot: Snapshot) -> None:
        signature = tuple(hint.module for hint in snapshot.driver_hints)
        if signature == self._hint_signature:
            return
        self._hint_signature = signature

        clear_layout(self._hint_host)
        for hint in snapshot.driver_hints:
            body = f"Cargando {hint.module} tendrías {hint.provides}."
            detail = hint.command + (f"\n{hint.caution}" if hint.caution else "")
            # El botón solo aparece donde hay un módulo concreto que cargar. El
            # aviso del Super I/O manda a `sensors-detect` a propósito: cada
            # placa lleva un chip distinto y cargar el que no es lee basura, así
            # que ahí no hay nada que automatizar.
            accion = (_("sensors.driver.button")
                      if cargar_modulo.se_puede(hint.module) else None)
            aviso = Notice(_("sensors.driver.title"), body, detail,
                           action=accion)
            if accion:
                aviso.action_clicked.connect(
                    lambda _=False, m=hint.module, a=aviso: self._cargar_driver(m, a))
            self._hint_host.addWidget(aviso)

    def _cargar_driver(self, modulo: str, aviso) -> None:
        """`modprobe` ahora y una línea en `/etc/modules-load.d` para después.

        Lo segundo es la mitad que importa —un modprobe suelto se pierde al
        reiniciar— y es también la que nadie recuerda.
        """
        import subprocess

        boton = aviso.action_button
        if boton is not None:
            boton.setEnabled(False)
            boton.setText("Cargando…")
        try:
            resultado = subprocess.run(self._orden_de_carga(modulo),
                                       capture_output=True, text=True, timeout=120)
        except (OSError, subprocess.TimeoutExpired, RuntimeError) as error:
            self._aviso_de_registro(f"no se pudo cargar {modulo}: {error}")
            return

        if resultado.returncode == 0:
            # El aviso desaparece solo en el muestreo siguiente, cuando el
            # proveedor vea el chip nuevo. Forzar la firma lo repinta antes.
            self._hint_signature = ()
            return
        if boton is not None:
            boton.setEnabled(True)
            boton.setText(_("sensors.driver.button"))
        # 126 y 127 son «el usuario canceló» y «no autorizado»: eso no es un
        # fallo del que haya que informar como si algo se hubiera roto.
        if resultado.returncode not in (126, 127):
            detalle = (resultado.stderr or resultado.stdout or "").strip()
            self._aviso_de_registro(detalle.splitlines()[-1] if detalle else "falló")

    def _orden_de_carga(self, modulo: str) -> list[str]:
        """Lo mismo que hace el instalador de permisos: desde un AppImage nada
        de dentro del montaje sirve, así que se copia fuera."""
        import shutil
        import sys as _sys

        from ...privileged.client import SYSTEM_PYTHON, PrivilegedClient, _cache_dir

        guion = pathlib.Path(cargar_modulo.__file__)
        if not PrivilegedClient.empaquetado():
            return ["pkexec", _sys.executable, str(guion), modulo]

        interprete = next((r for r in SYSTEM_PYTHON if os.path.exists(r)), None)
        if interprete is None:
            raise RuntimeError("no hay ningún Python del sistema")
        destino = _cache_dir()
        destino.mkdir(parents=True, exist_ok=True)
        copia = destino / "cargar_modulo.py"
        shutil.copyfile(guion, copia)
        return ["pkexec", interprete, str(copia), modulo]

    def _reset_extremes(self) -> None:
        self._tracker.reset()
