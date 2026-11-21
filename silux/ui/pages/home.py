"""La portada: qué equipo es esto y qué está haciendo, en una pantalla.

Antes el programa abría en la ficha del procesador, que es la respuesta a una
pregunta que nadie ha hecho todavía. Lo primero que quiere ver quien abre esto
—sobre todo la primera vez— es de qué equipo se trata: qué lleva dentro y si
algo está caliente o a tope ahora mismo.

Cada tarjeta lleva a su sección al pulsarla, así que esta página hace además
de índice: se mira, se elige y se entra.
"""

from __future__ import annotations

from typing import Optional, Sequence

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFontMetrics
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from ... import render
from ...i18n import _
from ...model import DISK_KINDS, Snapshot
from ...settings import Preferences
from .. import theme
from ..theme import Palette
from ..widgets import (
    Card,
    ChipRow,
    PermissionNotice,
    ResponsiveRow,
    ScrollPage,
    Series,
    Sparkline,
    StackedBar,
    memory_segments,
    ui_font,
)

# Cuántos grados tiene que sacarle una pieza a la que encabeza la tarjeta de
# temperaturas para quitarle el sitio.
MARGEN_DEL_TITULAR = 2.0


# Lo más ancho que puede escribir cada cifra, de `render.possible_texts`,
# como las fichas grandes. La tarjeta reserva ese ancho: sin reserva medía lo
# que el texto de cada muestra, y al ensancharse una tarjeta se repartía de
# nuevo la fila entera (lo cazó `test_nada_se_mueve` en el CI, con DejaVu y
# un ritmo de red que dependía de lo rápido que fuera el runner).
def _porcentajes() -> list[str]:
    return render.possible_texts(render.percent, 100.0)


def _relojes() -> list[str]:
    return render.possible_texts(render.hz, 10e9)


def _grados(fahrenheit: bool) -> list[str]:
    return render.possible_texts(lambda v: render.temperature(v, fahrenheit), 200.0)


def _vatios() -> list[str]:
    return render.possible_texts(render.watts, 1000.0)


def _ritmos(bits: bool) -> list[str]:
    return render.possible_texts(lambda v: render.rate(v, bits), 1.25e10)


class _TarjetaResumen(Card):
    """Una pieza del equipo: qué es, cómo está y una curva de su historia."""

    pulsada = Signal(str)

    def __init__(self, titulo: str, seccion: str, palette: Palette,
                 cuerpo: Optional[str] = "grafica", parent: Optional[QWidget] = None):
        """`cuerpo`: «grafica», «barra» o nada, que es lo que lleva debajo."""
        super().__init__(titulo, parent)
        self._seccion = seccion
        self._p = palette
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(_("home.goto").format(seccion=seccion))

        m = theme.METRICS
        self.nombre = QLabel("—")
        self.nombre.setObjectName("Headline")
        self.nombre.setWordWrap(True)
        self.detalle = QLabel("")
        self.detalle.setObjectName("Subhead")
        self.detalle.setWordWrap(True)

        self.cifras = QLabel("")
        self.cifras.setObjectName("FieldValue")
        self.cifras.setFont(ui_font(m.base_pt + 3))

        self.body.addWidget(self.nombre)
        self.body.addWidget(self.detalle)
        self.body.addWidget(self.cifras)

        self.grafica = Sparkline(palette) if cuerpo == "grafica" else None
        self.barra = StackedBar(palette) if cuerpo == "barra" else None
        if (debajo := self.grafica or self.barra) is not None:
            self.body.addWidget(debajo)

        # Lo que esta pieza no tiene y por eso no sale arriba: se nombra aquí
        # en vez de dejar un guion entre las cifras.
        self.pie = QLabel("")
        self.pie.setObjectName("Muted")
        self.pie.setWordWrap(True)
        self.pie.setFont(ui_font(m.small_pt))
        self.pie.hide()
        self.body.addWidget(self.pie)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self.pulsada.emit(self._seccion)
        super().mouseReleaseEvent(event)

    def reservar(self, piezas: Sequence[Sequence[str]], separador: str = "   ") -> None:
        """Reserva para las cifras el ancho de lo más largo que pueden decir.

        `piezas`, las mismas que se van a pintar y en el mismo orden; de cada
        una, todo lo que puede llegar a poner. Se mide con la letra que la
        etiqueta tiene de verdad, después de la hoja de estilos.
        """
        self.cifras.ensurePolished()
        metricas = QFontMetrics(self.cifras.font())
        anchos = [max(metricas.horizontalAdvance(t) for t in opciones)
                  for opciones in piezas if opciones]
        ancho = sum(anchos) + metricas.horizontalAdvance(separador) * max(len(anchos) - 1, 0)
        # No encoge: una pieza que falta un momento (la gráfica que se duerme)
        # también movería la fila al volver.
        ancho = max(ancho, self.cifras.minimumWidth())
        if self.cifras.minimumWidth() != ancho:
            self.cifras.setMinimumWidth(ancho)

    def poner(self, nombre: str, detalle: str, cifras: str, pie: str = "") -> None:
        for etiqueta, texto in ((self.nombre, nombre), (self.detalle, detalle),
                                (self.cifras, cifras), (self.pie, pie)):
            if etiqueta.text() != texto:
                etiqueta.setText(texto)
        # Una línea vacía también ocupa: las que no dicen nada no se montan.
        for etiqueta in (self.detalle, self.cifras, self.pie):
            etiqueta.setVisible(bool(etiqueta.text()))


class HomePage(ScrollPage):
    # La pide la ventana, que es quien tiene la foto y la paleta.
    share_copy_requested = Signal()

    seccion_pedida = Signal(str)

    def __init__(self, palette: Palette, prefs: Preferences, parent=None):
        super().__init__(parent)
        self._p = palette
        self._prefs = prefs
        m = theme.METRICS

        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        root = QWidget()
        root.setObjectName("Root")
        self.setWidget(root)

        layout = QVBoxLayout(root)
        layout.setContentsMargins(m.page_margin, m.page_margin,
                                  m.page_margin, m.page_margin)
        layout.setSpacing(m.section_gap)

        # Escondido hasta que la ventana diga que falta algo, y debajo de las
        # tarjetas: lo primero de esta página es el equipo. Arriba del todo
        # eran 130 px de aviso antes del primer dato, y lo que falta ya lo
        # señalan el candado de cada tarjeta y el enlace de la barra de estado.
        self.permission_notice = PermissionNotice(palette,
                                                  compact=prefs.density == "compact")
        self.permission_notice.hide()

        layout.addWidget(self._cabecera())

        arriba = ResponsiveRow(min_item_width=300)
        self.cpu = self._tarjeta(arriba, _("home.card.cpu"), _("nav.cpu"))
        self.gpu = self._tarjeta(arriba, _("home.card.gpu"), _("nav.graphics"))
        layout.addWidget(arriba)

        abajo = ResponsiveRow(min_item_width=300)
        self.memoria = self._tarjeta(abajo, _("nav.memory"), _("nav.memory"), cuerpo="barra")
        self.discos = self._tarjeta(abajo, _("nav.storage"), _("nav.storage"),
                                    cuerpo="barra")
        layout.addWidget(abajo)

        # Con la ventana grande quedaba media página vacía debajo de las
        # cuatro. Tres más, de lo que se viene a mirar sin saber dónde está:
        # qué va caliente, por dónde sale la red y qué placa es.
        tercera = ResponsiveRow(min_item_width=240)
        self.temperaturas = self._tarjeta(tercera, _("home.card.temps"), _("nav.sensors"))
        self.red = self._tarjeta(tercera, _("nav.network"), _("nav.network"))
        self.placa = self._tarjeta(tercera, _("nav.board"), _("nav.board"), cuerpo=None)
        layout.addWidget(tercera)
        layout.addWidget(self.permission_notice)

        layout.addStretch(1)
        self._chips: tuple = ()
        self._titular_de_temperaturas: Optional[str] = None

    def _tarjeta(self, host: ResponsiveRow, titulo: str, seccion: str,
                 cuerpo: Optional[str] = "grafica") -> _TarjetaResumen:
        tarjeta = _TarjetaResumen(titulo, seccion, self._p, cuerpo=cuerpo)
        tarjeta.pulsada.connect(self.seccion_pedida)
        host.add(tarjeta)
        return tarjeta

    def _cabecera(self) -> QWidget:
        card = Card()
        self.title = QLabel(_("home.loading"))
        self.title.setObjectName("Headline")
        self.title.setWordWrap(True)
        self.subtitle = QLabel("")
        self.subtitle.setObjectName("Subhead")
        self.subtitle.setWordWrap(True)
        self.badges = ChipRow()

        # Aquí y no solo en Ajustes: esta pantalla ya es el resumen del equipo,
        # con las mismas cuatro tarjetas que acaban en la imagen, así que es
        # donde alguien piensa «esto es lo que quiero enseñar». A Ajustes no se
        # entra con ganas de compartir nada.
        #
        # Va en la fila de las insignias, a la derecha: en una fila para él
        # solo se llevaba un renglón entero de la cabecera.
        self.share = QPushButton(_("share.button.copy"))
        self.share.setToolTip(_("share.tip"))
        self.share.clicked.connect(self.share_copy_requested)
        fila = QHBoxLayout()
        fila.setSpacing(max(6, theme.METRICS.card_gap))
        fila.addWidget(self.badges, 1)
        fila.addWidget(self.share, 0, Qt.AlignmentFlag.AlignTop)

        card.body.addWidget(self.title)
        card.body.addWidget(self.subtitle)
        card.body.addLayout(fila)
        return card

    # -- actualización ------------------------------------------------------

    def set_permission_notice(self, nombres, recaida: bool = False,
                              outdated: bool = False) -> None:
        """Qué falta por permisos, o nada. Lo decide la ventana, que es quien
        sabe si el aviso se apartó: esta página se rehace al cambiar de tema."""
        if nombres:
            self.permission_notice.set_missing(nombres, recaida, outdated)
        self.permission_notice.setVisible(bool(nombres))

    def apply(self, snapshot: Snapshot) -> None:
        self._cabecera_con(snapshot)
        self._procesador(snapshot)
        self._grafica(snapshot)
        self._memoria(snapshot)
        self._almacenamiento(snapshot)
        self._temperaturas(snapshot)
        self._red(snapshot)
        self._placa(snapshot)

    def _cabecera_con(self, snapshot: Snapshot) -> None:
        from .system import format_uptime

        sistema = snapshot.system
        equipo = snapshot.board.display_name if snapshot.board else None
        self.title.setText(equipo or sistema.hostname or _("home.thispc"))

        partes = [sistema.distribution, sistema.kernel]
        if sistema.desktop:
            partes.append(f"{sistema.desktop} · {sistema.session_type or ''}".strip(" ·"))
        if sistema.uptime_seconds:
            partes.append(_("home.uptime").format(
                tiempo=format_uptime(sistema.uptime_seconds)))
        self.subtitle.setText(" · ".join(p for p in partes if p))

        chips = []
        if sistema.hostname:
            chips.append(sistema.hostname)
        # La arquitectura no: está en CPU y en Sistema, y aquí era la tercera.
        if snapshot.cpu.types:
            chips.append(render.virtual_machine(snapshot.cpu.types[0]) or "")
        # Lo que falta por permisos no va aquí: lo dice el aviso de arriba,
        # con su lista y su botón, y el enlace de la barra de estado. Una
        # insignia más, sin nada que pulsar, solo lo repetía.

        # Lo que está fuera de umbral se dice en la portada, que es donde se
        # entra. Enterarse de que la GPU va a 100 grados solo si se abre la
        # pestaña de sensores y se despliega su rama es enterarse tarde.
        niveles = [s.alarm_level for s in snapshot.sensors if s.alarm_level != "ok"]
        if niveles:
            criticos = niveles.count("crítico")
            chips.append(
                "⚠ " + (_("home.alarm.crit.one" if criticos == 1
                          else "home.alarm.crit.many").format(n=criticos)
                        if criticos else
                        _("home.alarm.high.one" if len(niveles) == 1
                          else "home.alarm.high.many").format(n=len(niveles))))
        chips = [c for c in chips if c]
        if tuple(chips) != self._chips:
            self._chips = tuple(chips)
            self.badges.set_chips(chips, highlight_first=True)

    def _procesador(self, snapshot: Snapshot) -> None:
        cpu = snapshot.cpu
        if not cpu.types:
            self.cpu.poner("—", "", "")
            return
        principal = cpu.types[0]
        nucleos = sum(t.cores for t in cpu.types)
        hilos = sum(t.threads for t in cpu.types)
        detalle = " · ".join((
            _("home.cores.one" if nucleos == 1
              else "home.cores.many").format(n=nucleos),
            _("home.threads.one" if hilos == 1
              else "home.threads.many").format(n=hilos)))
        if principal.codename:
            detalle += f" · {principal.codename}"

        piezas, moldes = [], []
        fahrenheit = self._prefs.fahrenheit
        if cpu.usage_percent is not None:
            piezas.append(render.percent(cpu.usage_percent))
            moldes.append(_porcentajes())
            self.cpu.grafica.set_series(Series("cpu/usage", "%"))
            self.cpu.grafica.push(cpu.usage_percent)
            self.cpu.grafica.set_range(0.0, 100.0)
        if principal.clocks.current_hz:
            piezas.append(render.hz(principal.clocks.current_hz))
            moldes.append(_relojes())
        if (temp := cpu.temperature_c) is not None:
            piezas.append(render.temperature(temp, fahrenheit))
            moldes.append(_grados(fahrenheit))
        self.cpu.reservar(moldes)
        self.cpu.poner(render.cpu_short_name(principal.brand), detalle,
                       "   ".join(piezas))

    def _grafica(self, snapshot: Snapshot) -> None:
        if not snapshot.gpus:
            self.gpu.poner(_("home.gpu.none"), "", "")
            return
        indice = snapshot.working_gpu
        gpu = snapshot.gpus[indice]
        # Un guion aquí no es un dato: es el hueco de uno que falta, y en una
        # línea de tres piezas unidas por puntos se lee como si sobrara algo.
        # Una GTX con la memoria sin identificar salía «— · PCIe 1.0 × 16».
        #
        # De la memoria solo el tipo, que es de la tarjeta. Cuánta RAM del
        # equipo usa una integrada lo dice la página de Gráficos con su
        # explicación al lado; aquí, suelto, «usa 11 GB de la RAM» era un
        # susto y además no era lo que tiene cogido sino el tope.
        detalle = " · ".join(p for p in (
            _("gpu.chip.integrated") if gpu.integrated else None,
            render.vram_kind(gpu.memory) if gpu.memory.total_bytes else None,
            render.gpu_link(gpu),
            render.compute_units(gpu) if gpu.compute_units else None,
        ) if p and p != render.DASH)

        piezas, moldes = [], []
        fahrenheit = self._prefs.fahrenheit
        if gpu.suspended:
            # Solo si duermen todas: la que trabaja es la despierta.
            piezas.append(_("gpu.asleep.short"))
            moldes.append((piezas[-1],))
        elif gpu.busy_percent is not None:
            piezas.append(render.percent(gpu.busy_percent))
            moldes.append(_porcentajes())
            self.gpu.grafica.set_series(Series(f"{gpu.pci_slot}/usage", "%"))
            self.gpu.grafica.push(gpu.busy_percent)
            self.gpu.grafica.set_range(0.0, 100.0)
        if gpu.temp_c is not None:
            piezas.append(render.temperature(gpu.temp_c, fahrenheit))
            moldes.append(_grados(fahrenheit))
        if gpu.power_w is not None:
            piezas.append(render.watts(gpu.power_w))
            moldes.append(_vatios())
        if not piezas and gpu.clocks.core_hz:
            # Una Intel sin permisos no da uso, ni temperatura, ni vatios: las
            # tres salen del PMU del kernel y la primera no existe siquiera.
            # La tarjeta se quedaba con el nombre y nada más, que parece un
            # fallo del programa. El reloj del motor gráfico está en sysfs y se
            # lee sin pedir nada, así que al menos se ve que la cosa se mueve.
            piezas.append(render.hz(gpu.clocks.core_hz))
            moldes.append(_relojes())
            self.gpu.grafica.set_series(Series(f"{gpu.pci_slot}/clock", "MHz"))
            self.gpu.grafica.push(gpu.clocks.core_hz / 1e6)
            if gpu.clocks.core_max_hz:
                # Con su techo al lado: 350 MHz solos no dicen si es mucho.
                piezas.append(_("home.gpu.ofmax").format(
                    max=render.hz(gpu.clocks.core_max_hz)))
                moldes.append((piezas[-1],))
                self.gpu.grafica.set_range(0.0, gpu.clocks.core_max_hz / 1e6)
        elif not piezas and gpu.clocks.core_hz == 0:
            piezas.append(_("gpu.clock.idle"))
            moldes.append((piezas[-1], *_relojes()))
        self.gpu.reservar(moldes)
        # El uso y el consumo, si faltan por permisos, se dicen: sin esto la
        # tarjeta de una integrada parecía no tener nada más que un reloj.
        pie = (_("home.gpu.locked")
               if gpu.busy_percent is None and not gpu.suspended
               and snapshot.permission_note(f"gpus.{indice}.usage")
               else "")
        self.gpu.poner(render.gpu_name(gpu), detalle, "   ".join(piezas), pie)

    def _memoria(self, snapshot: Snapshot) -> None:
        memoria = snapshot.system.memory
        if not memoria.total_bytes:
            self.memoria.poner("—", "", "")
            return
        # Usado y total en el mismo renglón: en tres («8.9 GB en uso», «31.3
        # GB», «28 % ocupada») había que juntarlos de cabeza.
        usada = memoria.used_bytes
        detalle = " · ".join(p for p in (
            _("home.mem.used").format(pct=f"{usada / memoria.total_bytes * 100:.0f}"),
            _tipo_de_memoria(snapshot),
        ) if p)
        self.memoria.poner(
            _("home.mem.of").format(usada=render.size(usada),
                                    total=render.size(memoria.total_bytes)),
            detalle, "")
        # Los mismos tramos y colores que la página de Memoria: aquí la caché
        # iba con el color del fondo de la barra y no se veía dónde acababa.
        self.memoria.barra.set_segments(memory_segments(memoria),
                                        total=memoria.total_bytes, formatter=render.size)

    def _almacenamiento(self, snapshot: Snapshot) -> None:
        discos = snapshot.disks
        if not discos:
            self.discos.poner(_("home.storage.none"), "", "")
            return
        total = sum(d.size_bytes or 0 for d in discos)
        usado = sum(d.used_bytes or 0 for d in discos)
        libre = sum(p.free_bytes or 0 for d in discos for p in d.mounted_partitions)
        tipos = [f"{sum(1 for d in discos if d.kind == k)} × {k}"
                 for k in DISK_KINDS
                 if any(d.kind == k for d in discos)]
        self.discos.poner(
            _("home.storage.total.one" if len(discos) == 1
              else "home.storage.total").format(tam=render.size(total),
                                                n=len(discos)),
            " · ".join(tipos),
            _("home.storage.free").format(tam=render.size(libre)))
        _usado, _libre, reservado, sin_montar = render.space(discos)
        segmentos = [render.Segment("used", _("home.bar.used"), usado, "accent"),
                     render.Segment("free", _("home.bar.free"), libre, "line")]
        if reservado:
            segmentos.append(render.Segment("reserved", _("storage.bar.reserved"), reservado,
                                            "muted/0.45", _("storage.bar.reserved.tip")))
        if sin_montar:
            segmentos.append(render.Segment("unmounted", _("home.bar.unmounted"), sin_montar,
                                            "muted"))
        self.discos.barra.set_segments(segmentos, total=total, formatter=render.size)


    def _temperaturas(self, snapshot: Snapshot) -> None:
        """Lo más caliente del equipo, cada cifra con el nombre de lo que mide.

        Tres números sueltos —«60 °C  51 °C  48 °C»— obligan a adivinar cuál
        es cuál, y en un equipo sin sensor en la gráfica el segundo es otra
        cosa. La más caliente va arriba, que es la que se viene a mirar.
        """
        # (what it is, raw; its name; °C): the headline and its chart go by
        # the first, which no language changes.
        lecturas = []
        if (grados := snapshot.cpu.temperature_c) is not None:
            lecturas.append(("cpu", _("home.temp.cpu"), grados))
        grafica = (snapshot.gpus[snapshot.working_gpu] if snapshot.gpus else None)
        if grafica is not None and (grados := grafica.temp_c) is not None:
            lecturas.append(("gpu", _("home.temp.gpu"), grados))
        discos = [d.temp_c for d in snapshot.disks if d.temp_c is not None]
        if discos:
            lecturas.append(("disk", _("home.temp.disk"), max(discos)))

        # La gráfica que no publica su temperatura no deja un hueco entre las
        # cifras: se dice aquí abajo, que no es lo mismo que no haberla leído.
        pie = (_("gpu.na.notemp") if grafica is not None
               and grafica.no_temperature_sensor
               and grafica.temp_c is None else "")
        if not lecturas:
            self.temperaturas.poner(_("home.temp.none"), "", "", pie)
            return
        fahrenheit = self._prefs.fahrenheit
        # El titular no cambia por décimas. Con el procesador a 52,6 y la
        # gráfica a 53,0 saltaba de uno a otro cada segundo, y la tarjeta
        # entera bailaba. Quien está arriba se queda hasta que otro le saque
        # MARGEN_DEL_TITULAR grados; las demás van siempre en el mismo orden.
        por_clave = {clave: (nombre, grados) for clave, nombre, grados in lecturas}
        candidato = max(lecturas, key=lambda lectura: lectura[2])
        actual = self._titular_de_temperaturas
        # A reading that appears or goes (a disk's, once permissions are
        # given) starts the choice over: the page then reads as if opened now.
        leidas = frozenset(por_clave)
        if leidas != getattr(self, "_temperaturas_leidas", leidas):
            actual = None
        self._temperaturas_leidas = leidas
        if actual not in por_clave or \
                candidato[2] - por_clave[actual][1] >= MARGEN_DEL_TITULAR:
            actual = self._titular_de_temperaturas = candidato[0]
        nombre, grados = por_clave[actual]
        resto = [(n, g) for clave, n, g in lecturas if clave != actual]
        self.temperaturas.poner(
            f"{nombre}  {render.temperature(grados, fahrenheit)}",
            _("home.temp.hottest"),
            " · ".join(f"{n} {render.temperature(g, fahrenheit)}" for n, g in resto),
            pie)
        # The headline's: when another one takes it, the chart starts over.
        self.temperaturas.grafica.set_series(Series(f"temp/{actual}", "°C"))
        self.temperaturas.grafica.push(grados)
        self.temperaturas.grafica.set_range(20.0, 100.0)

    def _red(self, snapshot: Snapshot) -> None:
        from .network import link_ceiling, main_interface

        principal, _todas = main_interface(snapshot.network)
        if principal is None:
            self.red.poner(_("net.none"), _("net.none.body"), "")
            return
        bits = self._prefs.network_unit == "bits"
        trafico = principal.traffic
        presentes = [(flecha, ritmo) for flecha, ritmo
                     in (("↓", trafico.rx_rate_bps), ("↑", trafico.tx_rate_bps))
                     if ritmo is not None]
        cifras = "   ".join(f"{flecha} {render.rate(ritmo, bits)}" for flecha, ritmo in presentes)
        self.red.reservar([tuple(f"{flecha} {texto}" for texto in _ritmos(bits))
                           for flecha, _ritmo in presentes])
        # Lo mismo que el titular de la página de Red: la conexión primero
        # (interfaz y dirección) y la pieza debajo.
        self.red.poner(
            " · ".join(p for p in (principal.name, principal.ipv4) if p),
            " · ".join(p for p in (
                render.network_name(principal) if principal.model else None,
                render.link_summary(principal)) if p),
            cifras)
        if trafico.total_rate_bps is not None:
            enlace = link_ceiling(principal)
            self.red.grafica.set_series(Series(f"net:{principal.name}/total", "B/s",
                                               2 * enlace if enlace else None))
            self.red.grafica.push(trafico.total_rate_bps)

    def _placa(self, snapshot: Snapshot) -> None:
        placa = snapshot.board
        if placa is None or not placa.display_name:
            self.placa.poner(_("home.board.none"), "", "")
            return
        bios = " · ".join(p for p in (
            f"BIOS {placa.bios_version}" if placa.bios_version else None,
            render.bios_date(placa.bios_date)) if p)
        arranque = " · ".join(p for p in (
            placa.firmware,
            placa.tpm_version,
            _("board.field.secureboot") if placa.secure_boot else None) if p)
        # Si la placa ya es el titular de la página, aquí no se repite: manda
        # el chipset, que arriba no está. En un equipo de marca el titular es
        # el equipo y la placa sí es un dato nuevo.
        nombre = placa.display_name
        if nombre == self.title.text():
            nombre = placa.chipset or bios or nombre
            if nombre == bios:
                bios = ""
        self.placa.poner(nombre, bios, arranque)


def _tipo_de_memoria(snapshot: Snapshot) -> Optional[str]:
    """«DDR4-3200», si se sabe de qué son los módulos."""
    # Solo de los zócalos ocupados: la tabla trae también los vacíos, y de
    # uno vacío no se saca cómo es la memoria que hay puesta.
    for modulo in snapshot.modules:
        if modulo.populated and modulo.type:
            tipo = render.memory_type(modulo.type)
            return f"{tipo}-{modulo.speed_mts}" if modulo.speed_mts else tipo
    return None
