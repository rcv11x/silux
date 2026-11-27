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
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ... import registro, render
from ...i18n import _
from ...model import Sensor, SensorKind, Snapshot
from ...settings import Preferences
from ...tracking import Tracker
from .. import theme
from ..sensortree import SensorTree
from ..theme import Palette, ui_font
from ..widgets import (
    Card,
    ElidingLabel,
    FoldingRow,
    ModuleNotices,
    ScrollPage,
)

# Cuántos decimales tiene sentido enseñar en cada magnitud. La tabla está en
# `render` porque el informe enseña los mismos sensores y tenerla dos veces es
# tenerla mal la mitad de las veces.
DECIMALS = render.SENSOR_DECIMALS


class MonitorPage(ScrollPage):
    # Lo emite el árbol cuando el usuario arrastra una columna; la ventana lo
    # guarda para que el ajuste sobreviva al cierre.
    columns_resized = Signal(tuple)
    branches_changed = Signal(tuple, tuple)
    # The sensors pinned on top changed: their keys.
    pinned_changed = Signal(tuple)

    def __init__(self, palette: Palette, prefs: Preferences, tracker: Tracker, parent=None):
        super().__init__(parent)
        self._p = palette
        self._prefs = prefs
        self._tracker = tracker
        # La última foto que ya se contó en el `Tracker` (`record`).
        self._contada: Optional[Snapshot] = None
        self._last: Optional[Snapshot] = None
        # Las cargas de módulo que esperan a pkexec: qué módulo y qué botón.
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
        self.tree.set_collapsed(prefs.sensor_collapsed, prefs.sensor_expanded)
        self.tree.set_pinned(prefs.sensor_pinned)
        self.tree.pinnedChanged.connect(self._on_pinned)
        self.tree.itemExpanded.connect(lambda _item: self.tree.refresh_height())
        self.tree.itemCollapsed.connect(lambda _item: self.tree.refresh_height())
        self.tree.branchesChanged.connect(self.branches_changed)
        self.tree.columnsResized.connect(self.columns_resized)
        sensors_card.body.addWidget(self.tree)
        # Lo que este equipo no publica y por eso no tiene rama en el árbol.
        # Sin esto, quien busca la temperatura de la gráfica entre los
        # sensores no sabe si falta o si no la ha encontrado.
        self.absent = QLabel("")
        self.absent.setObjectName("Muted")
        self.absent.setWordWrap(True)
        self.absent.setFont(ui_font(theme.METRICS.small_pt))
        self.absent.hide()
        sensors_card.body.addWidget(self.absent)
        self._layout.addWidget(sensors_card)

        # msr gives no sensor: its notice goes with the processor.
        self.module_notices = ModuleNotices(exclude=frozenset({"msr"}))
        self._layout.addWidget(self.module_notices)

        self._layout.addStretch(1)

        self._core_history: dict[int, deque] = defaultdict(lambda: deque(maxlen=40))
        self._structure: tuple = ()
        self._cuenta_completa = ""
        self._registro: Optional[registro.SensorLog] = None
        self._pendiente_abrir = False

    # -- construcción -------------------------------------------------------

    def _build_sensor_header(self) -> QWidget:
        holder = row = FoldingRow(spacing=10)
        row.set_margins(2, 4, 2, 0)

        title = QLabel(_("sensors.title"))
        title.setObjectName("CardTitle")

        # Se corta si no cabe. Es lo único de esta fila que puede ceder: con
        # una tipografía ancha y un equipo con muchos sensores, la cabecera
        # pedía más ancho del que tiene la página en su tamaño mínimo y la
        # recortaba por la derecha.
        self.count = ElidingLabel("")
        self.count.setObjectName("Muted")
        self.count.setFont(ui_font(theme.METRICS.small_pt))

        self.search = QLineEdit()
        self.search.setPlaceholderText(_("sensors.search.placeholder"))
        self.search.setClearButtonEnabled(True)
        self.search.setToolTip(
            _("sensors.tip.search")
        )
        # Hasta 190 px, y encoge si hace falta. Con el ancho fijo, esta fila
        # pedía unos 650 px con una tipografía ancha (DejaVu, la del CI y la
        # de muchas instalaciones) y la página tiene 640 en su tamaño mínimo:
        # el botón de la derecha quedaba cortado. El contador solo no bastaba.
        self.search.setMinimumWidth(60)
        self.search.setMaximumWidth(190)
        self.search.textChanged.connect(self._buscar)

        self.record_button = QPushButton(_("sensors.record.button"))
        self.record_button.setToolTip(
            _("sensors.tip.record")
        )
        self.record_button.clicked.connect(self._alternar_registro)

        self.reset_button = QPushButton(_("sensors.reset.button"))
        self.reset_button.setToolTip(
            _("sensors.tip.reset")
        )
        self.reset_button.clicked.connect(self._reset_extremes)

        row.add_widget(title)
        row.add_widget(self.count)
        row.add_stretch(1)
        row.add_widget(self.search)
        row.add_widget(self.record_button)
        row.add_widget(self.reset_button)
        return holder

    # -- registro a CSV -----------------------------------------------------

    def _alternar_registro(self) -> None:
        from PySide6.QtWidgets import QFileDialog

        if self._registro is not None and self._registro.active:
            self._registro.close()
            self._pintar_estado_registro()
            return

        carpeta = registro.folder()
        carpeta.mkdir(parents=True, exist_ok=True)
        ruta, _filtro = QFileDialog.getSaveFileName(
            self, _("csv.save.title"),
            str(carpeta / registro.suggested_name()),
            _("csv.filter"))
        if not ruta:
            return
        self._registro = registro.SensorLog(pathlib.Path(ruta))
        self._pendiente_abrir = True
        self._pintar_estado_registro()

    def _pintar_estado_registro(self) -> None:
        """El botón dice qué hace ahora y, grabando, cuánto lleva."""
        activo = self._registro is not None and self._registro.active
        pendiente = getattr(self, "_pendiente_abrir", False)
        if activo:
            # El plural va dentro de la clave y no fuera: en otras lenguas
            # no siempre son dos formas, y partir la frase para pegar el
            # número deja al traductor sin poder mover el orden.
            filas = self._registro.rows
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
            self._registro.close()

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
            self.count.set_full_text(_(clave).format(n=visibles))
        else:
            self.count.set_full_text(self._cuenta_completa)

    # -- actualización ------------------------------------------------------

    def _on_pinned(self, keys: tuple) -> None:
        """Drawn at once, with the last sample, and kept by the window."""
        if self._last is not None:
            self._apply_sensors(self._last)
        self.pinned_changed.emit(keys)

    def apply(self, snapshot: Snapshot) -> None:
        self._last = snapshot
        self.record(snapshot)
        self._apply_sensors(snapshot)
        self._apply_absent(snapshot)
        self._apply_hints(snapshot)

    def record(self, snapshot: Snapshot) -> None:
        """Lo que no puede esperar a que se abra la página: los mínimos,
        máximos e historial de cada sensor, y la grabación a CSV.

        Con la página cerrada, la ventana llama solo a esto; reescribir el
        árbol que no se ve era lo que más gastaba silux escondido. Una vez por
        foto: al abrir la página se le pasa la última, que ya se contó.
        """
        if snapshot is self._contada:
            return
        self._contada = snapshot
        # A reading that cannot be of its kind (a raw counter) gets neither in
        # its history nor in its minimum, maximum or mean.
        self._tracker.update_many((s.key, s.value) for s in snapshot.sensors if s.plausible)
        self._registrar(snapshot)

    def _apply_absent(self, snapshot: Snapshot) -> None:
        """Nombra al pie lo que no tiene rama porque el equipo no lo publica."""
        faltan = [_("sensors.absent.gputemp").format(nombre=render.gpu_name(gpu))
                  for gpu in snapshot.gpus
                  if gpu.no_temperature_sensor and gpu.temp_c is None]
        # Los canales que el driver no nombra: «Tensión 0, 1, 2…». No se les
        # pone nombre aquí porque no se sabe: en un Super I/O, qué llega a cada
        # entrada lo decidió quien diseñó la placa. Se dice de qué chip son.
        # Los chips, por su nombre a secas: la dirección que les pega el
        # kernel queda para el tooltip de cada fila.
        sin_nombre = sorted({render.chip_name(s.chip) for s in snapshot.sensors
                             if s.unnamed and s.kind is SensorKind.VOLTAGE})
        if sin_nombre:
            faltan.append(_("sensors.unnamed.voltages").format(chips=", ".join(sin_nombre)))
        # Lo mismo con las temperaturas: «Temperatura 1…6» de un Super I/O o
        # de la interfaz WMI de la placa no dicen dónde está cada sonda. Un
        # chip con una sola no tiene nada que distinguir, y las de relleno
        # llevan su propia explicación.
        numeradas: dict[str, int] = {}
        for s in snapshot.sensors:
            if (s.unnamed and s.kind is SensorKind.TEMPERATURE and not s.placeholder
                    and not s.mirror_of):
                chip = render.chip_name(s.chip)
                numeradas[chip] = numeradas.get(chip, 0) + 1
        if varias := sorted(chip for chip, n in numeradas.items() if n > 1):
            faltan.append(_("sensors.unnamed.temps").format(chips=", ".join(varias)))
        # Lo que un driver repite de otro: se enseña una vez y se dice cuál.
        espejos: dict[tuple[str, str], int] = {}
        for s in snapshot.sensors:
            if s.mirror_of:
                par = (render.chip_name(s.chip), render.chip_name(s.mirror_of))
                espejos[par] = espejos.get(par, 0) + 1
        for (espejo, chip), cuantas in sorted(espejos.items()):
            faltan.append(_("sensors.mirror").format(espejo=espejo, chip=chip, n=cuantas))
        relleno: dict[str, set[float]] = {}
        for s in snapshot.sensors:
            if s.placeholder:
                relleno.setdefault(s.chip, set()).add(s.value)
        for chip, valores in sorted(relleno.items()):
            faltan.append(render.placeholder_note(chip, valores, self._prefs.fahrenheit))
        # Cada explicación en su renglón: seguidas en un párrafo no se leen.
        texto = "\n".join(faltan)
        if self.absent.text() != texto:
            self.absent.setText(texto)
        self.absent.setVisible(bool(texto))

    def _registrar(self, snapshot: Snapshot) -> None:
        """La cabecera se escribe con el primer muestreo que llega después de
        pulsar, no en el momento de pulsar: así las columnas salen de una foto
        de verdad y no de la que hubiera cacheada."""
        if self._registro is None:
            return
        try:
            if self._pendiente_abrir:
                self._registro.open(snapshot)
                self._pendiente_abrir = False
            self._registro.write(snapshot)
        except OSError as error:
            self._registro.close()
            self._registro = None
            self._pendiente_abrir = False
            self._aviso_de_registro(str(error))
        self._pintar_estado_registro()

    def _aviso_de_registro(self, detalle: str) -> None:
        from PySide6.QtWidgets import QMessageBox

        QMessageBox.warning(self, _("csv.title"),
                            _("csv.stopped").format(detalle=detalle))

    def _temp(self, celsius: float) -> float:
        return render.in_temperature_unit(celsius, self._prefs.fahrenheit)

    def _apply_sensors(self, snapshot: Snapshot) -> None:
        tree = snapshot.sensor_tree()

        # La estructura solo cambia cuando aparece o desaparece hardware (al
        # cargar un módulo de sensores, por ejemplo), así que reconstruir es
        # excepcional y actualizar textos es lo normal.
        structure = tuple(
            (device, category, tuple(s.key for s in sensors))
            for device, categories in tree.items()
            for category, sensors in categories.items()
        )
        inactivos = self._inactivos(snapshot)
        # Los ventiladores parados van aparte dentro de su categoría, así que
        # cuál lo está es parte de la estructura; el tráfico de una interfaz
        # no, que solo decide cómo nace su rama y cambia a cada segundo.
        structure += (tuple(sorted(k for k in inactivos if not k.startswith("net/"))),)
        structure += (self.tree.pinned,)
        if structure != self._structure:
            self.tree.rebuild(tree, inactivos)
            self._structure = structure
            self._cuenta_completa = (
                _("sensors.count.one" if len(tree) == 1
                  else "sensors.count.many").format(
                      n=sum(1 for s in snapshot.sensors if not s.mirror_of),
                      aparatos=len(tree))
            )
            self._actualizar_cuenta()

        avisos: dict[str, list[str]] = {}
        for sensor in snapshot.sensors:
            seguimiento = self._tracker.get(sensor.key)
            self.tree.update_row(
                sensor.key, self._values(sensor), self._tooltip(sensor),
                sensor.alarm_level,
                seguimiento.history if seguimiento else None,
                self._peak_level(sensor, seguimiento),
                apagada=sensor.placeholder,
            )
            if sensor.alarm_level != "ok":
                avisos.setdefault(sensor.group, []).append(sensor.alarm_level)

        # El aviso tiene que llegar a la rama cerrada: con ocho aparatos y cien
        # sensores, uno en rojo dentro de una rama plegada no lo ve nadie.
        for device in tree:
            niveles = avisos.get(device, [])
            self.tree.marcar_aviso(device, len(niveles), "crítico" in niveles)

    @staticmethod
    def _inactivos(snapshot: Snapshot) -> frozenset:
        """Los sensores que ahora no tienen nada que enseñar: se pliegan.

        Un ventilador a 0 RPM —un conector de la placa sin nada enchufado, o
        una gráfica con los suyos parados— y las interfaces de red por las
        que no pasa tráfico y que no son la que da servicio.
        """
        from .network import main_interface

        principal, _todas = main_interface(snapshot.network)
        calladas = {
            i.name for i in snapshot.network
            if i is not principal
            and not (i.traffic.rx_rate_bps or 0) and not (i.traffic.tx_rate_bps or 0)}
        return frozenset(
            s.key for s in snapshot.sensors
            if (s.kind is SensorKind.FAN and s.value == 0)
            or (s.key.startswith("net/") and s.key.split("/")[1] in calladas))

    @staticmethod
    def _peak_level(sensor: Sensor, tracked) -> str:
        """The level its peak reached, not where it is now: after a
        two-minute stress test, «Actual» has already cooled down by the time
        you look.

        The sensor itself is asked with its reading swapped for the peak, so
        its limits are its own and aren't repeated here.
        """
        import dataclasses

        if tracked is None or tracked.maximum is None:
            return "ok"
        return dataclasses.replace(sensor, value=tracked.maximum).alarm_level

    def _values(self, sensor: Sensor) -> list[str]:
        digits = DECIMALS.get(sensor.kind, 1)
        value, unit = self._converted(sensor)
        current = f"{value:.{digits}f} {unit}".strip() if sensor.plausible else render.DASH
        if sensor.gpu_core_rail:
            # Said as on Graphics: switched off at rest is not a voltage.
            current = render.gpu_voltage(sensor.value)
        elif sensor.gpu_core_clock and sensor.value == 0:
            # Nor a clock.
            current = render.gpu_clock(0)

        extremes = self._tracker.get(sensor.key)
        if extremes is None:
            return [current, "—", "—", "—"]

        low, high, average = (self._convert(sensor, v) for v in
                              (extremes.minimum, extremes.maximum, extremes.average))
        return [current, f"{low:.{digits}f}", f"{high:.{digits}f}", f"{average:.{digits}f}"]

    def _convert(self, sensor: Sensor, value: float) -> float:
        if sensor.kind is SensorKind.TEMPERATURE:
            return render.in_temperature_unit(value, self._prefs.fahrenheit)
        return value

    def _converted(self, sensor: Sensor) -> tuple[float, str]:
        if sensor.kind is SensorKind.TEMPERATURE:
            return (render.in_temperature_unit(sensor.value, self._prefs.fahrenheit),
                    render.temperature_unit(self._prefs.fahrenheit))
        return sensor.value, sensor.unit

    def _tooltip(self, sensor: Sensor) -> str:
        lines = [f"{sensor.chip} · {sensor.key}"]
        limits = []
        if sensor.kind is SensorKind.TEMPERATURE:
            shown = lambda v: render.temperature_whole(v, self._prefs.fahrenheit)
        else:
            shown = lambda v: f"{v:g} {sensor.unit}"
        if sensor.low is not None:
            limits.append(_("sensors.limit.low").format(v=shown(sensor.low)))
        if sensor.high is not None:
            limits.append(_("sensors.limit.high").format(v=shown(sensor.high)))
        if sensor.critical is not None:
            limits.append(_("sensors.limit.crit").format(v=shown(sensor.critical)))
        if not limits and sensor.sheet_high is not None:
            limits.append(_("sensors.limit.sheet").format(v=shown(sensor.sheet_high)))
        if limits:
            lines.append("\n".join(limits))
        if sensor.placeholder:
            lines.append(render.placeholder_note(
                sensor.chip, (sensor.value,), self._prefs.fahrenheit))
        if sensor.alarm_level == "crítico":
            lines.append(_("sensors.alarm.crit"))
        elif sensor.alarm_level == "alto":
            lines.append(_("sensors.alarm.high" if sensor.high is not None
                           else "sensors.alarm.sheet"))
        return "\n\n".join(lines)

    def _apply_hints(self, snapshot: Snapshot) -> None:
        self.module_notices.apply(snapshot.driver_hints)

    def _reset_extremes(self) -> None:
        self._tracker.reset()
