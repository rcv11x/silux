"""Capa de presentación: convierte valores en texto.

Todo el formateo del programa vive aquí y solo aquí. El modelo guarda
hercios, bytes y grados; la interfaz y la CLI llaman a estas funciones. Es lo
que permite tener una salida JSON de verdad, cambiar de °C a °F sin tocar la
recolección, y traducir sin reescribir nada.
"""

from __future__ import annotations

import pathlib
import re
from typing import NamedTuple, Optional

from .i18n import _
from .model import (
    LOGICAL_NON_VOLATILE,
    ROUNDING_MARGIN,
    Cache,
    Clocks,
    CpuType,
    Display,
    Edid,
    GpuApi,
    GpuMemory,
    NetworkInterface,
    NetworkTraffic,
    PcieLink,
    Power,
    SensorKind,
    short_vendor,
    thread_name,
)
from .spd import jedec_grade

DASH = "—"

# Cuántos decimales lleva cada magnitud de un sensor. Redondear todas igual
# estropea la mitad: un voltaje a un decimal deja de ser un voltaje —0,845 V se
# queda en 0,8 y ya no dice nada— y un ventilador con decimales no dice más.
#
# Vive aquí y no en la página de sensores porque ahora también la usa el
# informe, y dos tablas iguales en dos archivos se desincronizan solas.
SENSOR_DECIMALS = {
    SensorKind.TEMPERATURE: 1,
    SensorKind.VOLTAGE: 3,
    SensorKind.FAN: 0,
    SensorKind.POWER: 1,
    SensorKind.CURRENT: 2,
    SensorKind.ENERGY: 0,
}


def sensor_value(value: Optional[float], kind: SensorKind) -> str:
    """El valor de un sensor con los decimales que le corresponden.

    Sin unidad: quien la pone decide antes si la convierte, que es lo que hace
    la pantalla con los grados Fahrenheit.
    """
    if value is None:
        return DASH
    return f"{value:.{SENSOR_DECIMALS.get(kind, 1)}f}"


def _none(value: object) -> bool:
    return value is None or value == ""


# SMBIOS memory enumerations, by the specification's code (DSP0134 tables 75
# and 78): the model keeps the code and its name is said here.
FORM_FACTOR_KEYS = {
    0x03: "smbios.form.simm", 0x04: "smbios.form.sip", 0x05: "smbios.form.chip",
    0x06: "smbios.form.dip", 0x07: "smbios.form.zip", 0x08: "smbios.form.card",
    0x09: "smbios.form.dimm", 0x0A: "smbios.form.tsop", 0x0B: "smbios.form.rowofchips",
    0x0C: "smbios.form.rimm", 0x0D: "smbios.form.sodimm", 0x0E: "smbios.form.srimm",
    0x0F: "smbios.form.fbdimm", 0x10: "smbios.form.die",
}
ERROR_CORRECTION_KEYS = {
    0x03: "smbios.ecc.none", 0x04: "smbios.ecc.parity", 0x05: "smbios.ecc.single",
    0x06: "smbios.ecc.multi", 0x07: "smbios.ecc.crc",
}


def memory_form_factor(code: Optional[int], translate=_) -> Optional[str]:
    """A memory module's form factor by its SMBIOS code; None if unknown."""
    key = FORM_FACTOR_KEYS.get(code) if code is not None else None
    return translate(key) if key else None


def memory_error_correction(code: Optional[int], translate=_) -> Optional[str]:
    """The memory's error correction by its SMBIOS code; None if unknown."""
    key = ERROR_CORRECTION_KEYS.get(code) if code is not None else None
    return translate(key) if key else None


def disk_kind(kind: Optional[str]) -> str:
    """A disk's kind as shown: the acronyms as they are, flash by name."""
    if kind == "Flash":
        return _("storage.kind.flash")
    return kind or DASH


def memory_rated(module) -> str:
    """«3200 MT/s», saying so when only the firmware's table gives it."""
    if not module.rated_mts:
        return DASH
    text = f"{module.rated_mts} MT/s"
    return f"{text} · {_('memory.source.bios')}" if module.rated_from_firmware else text


def memory_voltage(module) -> str:
    """«1.35 V», saying so when only the firmware's table gives it."""
    if module.voltage_mv is None:
        return DASH
    text = f"{module.voltage_mv / 1000:.2f} V"
    return f"{text} · {_('memory.source.bios')}" if module.voltage_from_firmware else text


def memory_type(name: Optional[str], translate=_) -> Optional[str]:
    """A memory technology: its name, or SMBIOS 1Fh said in words."""
    if name == LOGICAL_NON_VOLATILE:
        return translate("smbios.type.logicalnvm")
    return name


def made(year: Optional[int], week: Optional[int], translate=_) -> Optional[str]:
    """When a piece was made, as its own standard dates it: «semana 16 de
    2024» (EDID, SPD). The year alone without its week."""
    if not year:
        return None
    return translate("date.week").format(semana=week, anio=year) if week else str(year)


def gpu_clock(value: Optional[float]) -> str:
    """A GPU's engine clock: at 0 it is asleep, and asleep is not a clock."""
    if value == 0:
        return _("gpu.clock.idle")
    return hz(value)


def hz(value: Optional[float], decimals: int | None = None) -> str:
    if _none(value):
        return DASH
    value = float(value)
    if value >= 1e9:
        return f"{value / 1e9:.{2 if decimals is None else decimals}f} GHz"
    if value >= 1e6:
        return f"{value / 1e6:.{0 if decimals is None else decimals}f} MHz"
    # Un cero no se escala: una GPU en reposo profundo marca 0 y salía como
    # «0 kHz», que sugiere una frecuencia diminuta en vez de una parada. La
    # unidad que se elige por magnitud deja de tener sentido cuando no hay
    # magnitud. Sigue sin ser un dato ausente: parada es la respuesta.
    if value == 0:
        return "0 MHz"
    return f"{value / 1e3:.0f} kHz"


def size(value: Optional[int]) -> str:
    """Siempre en la unidad más grande que aplique.

    La versión anterior prefería la unidad en la que la división saliera
    exacta, y por eso 13,9 MB de caché total se enseñaban como "14208 KB".
    """
    if _none(value):
        return DASH
    value = int(value)
    # Los terabytes aparecieron con los discos: hasta entonces la unidad más
    # grande que se veía era la RAM, y «8849.3 GB» de almacenamiento total no
    # se lee, se cuenta.
    for unit, factor in (("TB", 1024**4), ("GB", 1024**3), ("MB", 1024**2), ("KB", 1024)):
        if value >= factor:
            scaled = value / factor
            return f"{int(scaled)} {unit}" if scaled.is_integer() else f"{scaled:.1f} {unit}"
    return f"{value} B"


def temperature(value: Optional[float], fahrenheit: bool = False) -> str:
    if _none(value):
        return DASH
    if fahrenheit:
        return f"{float(value) * 9 / 5 + 32:.1f} °F"
    return f"{float(value):.1f} °C"


def volts(value: Optional[float]) -> str:
    return DASH if _none(value) else f"{float(value):.3f} V"


def watts(value: Optional[float]) -> str:
    return DASH if _none(value) else f"{float(value):.1f} W"


def watt_hours(value: Optional[float]) -> str:
    """A battery's energy, with the same decimal wherever it is: the badge
    said «50 Wh» above a «Diseño 50.5 Wh»."""
    return DASH if _none(value) else f"{float(value):.1f} Wh"


def figure(value: Optional[float], decimals: int = 0) -> str:
    """La cifra de una ficha grande, sin su unidad, que va aparte.

    Con las cifras tabulares de la letra de los valores, lo que mide solo
    depende de cuántas tiene: el ancho que reserva cada ficha
    (`StatTile.reserve`) sale de aquí mismo, con el tope de lo que puede
    llegar a decir.
    """
    return DASH if _none(value) else f"{float(value):.{decimals}f}"


def percent(value: Optional[float]) -> str:
    return DASH if _none(value) else f"{float(value):.1f} %"


def multiplier(value: Optional[float]) -> str:
    return DASH if _none(value) else f"× {float(value):.1f}"


def clock_and_multiplier(frequency: Optional[int],
                         factor: Optional[float]) -> str:
    """«3.40 GHz  × 34.0», o solo la parte que se sepa.

    Los dos van juntos en el mismo renglón, y unirlos a pelo dejaba a la vista
    el hueco del que falta: un Broadwell sin multiplicador publicado salía
    «1.60 GHz  —», y uno sin ninguno de los dos, «—  —». El guion marca un
    dato ausente, y ahí se leía como un fallo de formato.
    """
    pieces = [p for p in (hz(frequency), multiplier(factor)) if p != DASH]
    return "  ".join(pieces) or DASH


def dec(value: Optional[int]) -> str:
    """Un entero tal cual. Existe para no escribir `x or DASH`: un stepping 0
    es un stepping de verdad, y con `or` se convertiría en un guion."""
    return DASH if value is None else str(value)


def hex_id(value: Optional[int]) -> str:
    """Como lo enseñan las hojas de datos: decimal y hexadecimal juntos."""
    if value is None:
        return DASH
    return f"{value} (0x{value:X})"


def signature(value: Optional[int]) -> str:
    """El registro EAX de la hoja 1 de CPUID, tal cual."""
    return DASH if value is None else f"0x{value:08X}"


def signature_tooltip(cpu_type: CpuType) -> str:
    """Explica de dónde salen la familia y el modelo compuestos.

    Es la pregunta que hace todo el mundo al ver un "modelo 5" en un
    procesador que Intel llama 165: CPUID reparte cada valor entre un campo
    base y otro extendido, y lo que vale es la suma.
    """
    if cpu_type.signature is None:
        return ""
    raw = cpu_type.signature
    return _("cpu.sig.tooltip").format(
        eax=signature(raw),
        fb=(raw >> 8) & 0xF, fe=(raw >> 20) & 0xFF, familia=cpu_type.disp_family,
        mb=(raw >> 4) & 0xF, me=(raw >> 16) & 0xF, modelo=cpu_type.disp_model,
        stepping=raw & 0xF)


def virtual_machine(cpu_type: CpuType) -> Optional[str]:
    """Quién está debajo, o nada si esto es hierro de verdad.

    Vive aquí y no en cada página porque lo piden dos —Inicio y CPU— y porque
    es justo lo que cambia cómo se lee todo lo demás: los núcleos, los
    sockets y las cachés de una máquina virtual son los que le inventó el
    hipervisor, no los de la pieza cuyo nombre sale en el titular.
    """
    if not cpu_type.in_virtual_machine:
        return None
    if cpu_type.hypervisor:
        return _("cpu.vm.named").format(nombre=cpu_type.hypervisor)
    return _("cpu.vm")


def load_average(values: tuple[float, ...], threads: int = 0) -> str:
    """Carga a 1, 5 y 15 minutos, con el número de hilos como referencia."""
    if not values:
        return DASH
    text = " · ".join(f"{v:.2f}" for v in values)
    return (_("cpu.load.threads").format(carga=text, n=threads)
            if threads else text)


def cache_size(value: Optional[int]) -> str:
    """«1.25 MB»: a cache's size with the decimals it needs, so that «4 ×
    1.25 MB» adds up to the 5 MB of the level."""
    if _none(value):
        return DASH
    for unit, factor in (("MB", 1024**2), ("KB", 1024)):
        if value >= factor:
            scaled = value / factor
            for digits in (0, 1, 2):
                if round(scaled, digits) == scaled:
                    return f"{scaled:.{digits}f} {unit}"
            return size(value)
    return f"{value} B"


def cache_summary(cache: Cache) -> str:
    """«6 × 32 KB, 8 vías»: la forma en que se lee una jerarquía de caché."""
    parts = [cache_size(cache.size_bytes)]
    if cache.instances > 1:
        parts[0] = f"{cache.instances} × {parts[0]}"
    if cache.ways:
        parts.append(_("cache.ways").format(n=cache.ways))
    return ", ".join(parts)


def caches_summary(caches) -> str:
    """One row for all the caches of a level: «2 × 32 MB, 16 vías», or
    «96 MB + 32 MB, 16 vías» when the level is not the same everywhere, as in
    a Ryzen with V-Cache on one of its two chiplets."""
    if len(caches) == 1:
        return cache_summary(caches[0])
    ordered = sorted(caches, key=lambda c: -c.size_bytes)
    parts = [f"{c.instances} × {cache_size(c.size_bytes)}" if c.instances > 1
             else cache_size(c.size_bytes) for c in ordered]
    text = " + ".join(parts)
    ways = {c.ways for c in ordered}
    if len(ways) == 1 and None not in ways:
        text += ", " + _("cache.ways").format(n=ways.pop())
    return text


def cache_label(cache: Cache) -> str:
    keys = {"data": "cache.label.data", "instruction": "cache.label.instr"}
    return _(keys.get(cache.kind, "cache.label.unified")).format(n=cache.level)


def from_cpu_table(value: Optional[str], translate_key=None) -> str:
    """Un dato que sale de la tabla de procesadores y no del propio silicio.

    El nombre en clave, el nodo y el encapsulado no se leen del procesador:
    están en una tabla que es una foto del día en que se hizo, y uno que
    salga después no está. Se dice así y no con un guion, que se lee como
    «este equipo no lo tiene». `traducir`, como en `core_type_label`.
    """
    return value or (translate_key or _)("cpu.notintable")


def core_type_label(cpu_type: CpuType, hybrid: bool, translate_key=None) -> str:
    """`traducir` deja pedir el castellano fijo desde fuera de la interfaz.

    El informe va en español pase lo que pase, así que ahí entra `en_español`
    en vez de `_`; con la función normal, el informe de alguien con la interfaz
    en inglés mezclaría los dos idiomas en la misma página.
    """
    tr = translate_key or _
    if not hybrid:
        return tr("cpu.type.generic")
    # «P» y «E» son como los llama Intel; ARM llama a lo mismo big.LITTLE.
    # El reparto es el mismo, el nombre no, y quien mira su teléfono no
    # reconoce «núcleo E» por ninguna parte.
    if (cpu_type.architecture or "").lower().startswith(("aarch64", "arm")):
        keys = {"performance": "core.type.big", "efficiency": "core.type.little"}
    else:
        keys = {"performance": "core.type.p", "efficiency": "core.type.e"}
    if cpu_type.key in keys:
        return tr(keys[cpu_type.key])
    return tr("core.type.named").format(nombre=cpu_type.key)


def instructions(cpu_type: CpuType, limit: int | None = None) -> str:
    from .features import for_architecture

    starred, pretty = for_architecture(cpu_type.architecture)
    present = set(cpu_type.features)
    shown = [pretty.get(f, f.upper()) for f in starred if f in present]
    if cpu_type.smt:
        shown.insert(0, "HT" if cpu_type.vendor == "Intel" else "SMT")
    if limit is not None and len(shown) > limit:
        return ", ".join(shown[:limit]) + f" (+{len(shown) - limit})"
    return ", ".join(shown) if shown else DASH


def power_headline(power: Power) -> str:
    """Una línea corta que pone el consumo en contexto: "de 65 W sostenidos"."""
    if power.package_w is None:
        return ""
    if power.limit_long_w:
        return _("cpu.power.headline").format(
            pct=f"{power.load_percent:.0f}", w=f"{power.limit_long_w:g}")
    return ""


# Los tonos de la barra de reposo, del estado más ligero al más hondo: cuanto
# más hondo duerme, más se parece al fondo. Lo que resalta es lo activo.
_IDLE_TONES = ("accent/0.6", "accent/0.4", "accent/0.25", "accent/0.15", "line")


_CORETEMP_PACKAGE = re.compile(r"^Package id (\d+)$")
_CORETEMP_CORE = re.compile(r"^Core (\d+)$")


def sensor_label(sensor) -> str:
    """El nombre de un sensor en el árbol, en el idioma de la interfaz.

    Solo las etiquetas que `coretemp` publica en inglés: «Package id 0» es
    «Paquete» y «Core 3», «Núcleo 3». El modelo las guarda tal cual, que es
    lo que quieren el informe y el CSV; las de los demás chips son las que
    puso el fabricante y no se tocan.
    """
    if sensor.chip == "coretemp":
        if (match := _CORETEMP_PACKAGE.match(sensor.label)):
            number = int(match.group(1))
            return _("sensor.package") if number == 0 else f'{_("sensor.package")} {number}'
        if (match := _CORETEMP_CORE.match(sensor.label)):
            return _("sensor.core").format(n=int(match.group(1)))
    return sensor.label


def idle_name(name: str) -> str:
    """«C2», no «C2_ACPI».

    `intel_idle` pone «_ACPI» detrás de los estados que toma de la tabla del
    firmware cuando no tiene una propia para ese procesador (un Comet Lake-S,
    por ejemplo). Dice de dónde salió el estado, no qué estado es.
    """
    return name[:-len("_ACPI")] if name.endswith("_ACPI") else name


class Segment(NamedTuple):
    """A stacked bar's segment. `key` is what it is, raw, and what the bar
    goes by; `label` and `tooltip` are only painted."""

    key: str
    label: str
    value: float
    token: str
    tooltip: str = ""


def idle_segments(states) -> list[Segment]:
    """Los tramos de la barra de reposo: lo activo y cada estado, sobre 100."""
    asleep = sum(e.percent for e in states)
    spans = [Segment("active", _("cpu.idle.active"),
                      max(0.0, round(100.0 - asleep, 1)), "accent")]
    timed = [e for e in states if e.percent > 0]
    for i, state in enumerate(timed):
        # El más hondo siempre con el tono del fondo.
        tone = _IDLE_TONES[-1] if i == len(timed) - 1 and len(timed) > 1 \
            else _IDLE_TONES[min(i, len(_IDLE_TONES) - 2)]
        spans.append(Segment(state.name, idle_name(state.name), state.percent, tone))
    return spans


def idle_deepest(states) -> Optional[str]:
    """«C2, el reposo más hondo: entre el 54 % y el 73 % según el hilo.»"""
    if not states:
        return None
    deepest = states[-1]
    # «C2_ACPI»: intel_idle took the states from the firmware's _CST table
    # (intel_idle_init_cstates_acpi), and the number is ACPI's level, not the
    # processor's C-state. «C2 is this processor's deepest», on a Comet
    # Lake that goes far deeper, was not true.
    sentence = (_("cpu.idle.deepest.acpi") if deepest.name.endswith("_ACPI")
             else _("cpu.idle.deepest"))
    return sentence.format(nombre=idle_name(deepest.name), bajo=f"{deepest.low:.0f}",
                        alto=f"{deepest.high:.0f}")


def power_breakdown(power: Power) -> str:
    """El reparto por dominio, que es lo que explica un consumo en reposo bajo."""
    parts = [
        (f'{_("power.cores")} {watts(power.core_w)}', power.core_w),
        (f'{_("power.uncore")} {watts(power.uncore_w)}', power.uncore_w),
        (f"DRAM {watts(power.dram_w)}", power.dram_w),
    ]
    return " · ".join(text for text, value in parts if value is not None)


def power_tooltip(power: Power) -> str:
    lines = [f'{_("power.package")} {watts(power.package_w)}']
    if breakdown := power_breakdown(power):
        lines.append(breakdown.replace(" · ", "\n"))
    if power.limit_long_w:
        lines.append(f'\n{_("power.pl1")} {watts(power.limit_long_w)}')
    if power.limit_short_w:
        lines.append(f'{_("power.pl2")} {watts(power.limit_short_w)}')
    return "\n".join(lines)


def plural(amount: int, singular: str, plural_: str) -> str:
    """La palabra que toca según la cantidad.

    Parece una tontería hasta que un equipo con un solo módulo de memoria lee
    «1 módulos leídos» y piensa que el programa está roto. Cuando alguien va a
    fiarse de las cifras, la concordancia es parte de fiarse.
    """
    return singular if amount == 1 else plural_


def unique_id(raw: Optional[str]) -> Optional[str]:
    """El identificador único de una pieza, o nada si no identifica nada.

    Todo ceros es la forma que tiene un driver de decir que no lo tiene.
    """
    if not raw or not raw.strip().strip("0"):
        return None
    return raw.strip()


_DMI_DATE = re.compile(r"(\d{1,2})/(\d{1,2})/(\d{4})")


def bios_date(raw: Optional[str]) -> Optional[str]:
    """La fecha de la BIOS sin ambigüedad: «2025-10-28».

    El firmware la escribe como mes/día/año, a la americana, y pintada tal
    cual «06/08/2023» se lee en España como el seis de agosto y es el ocho de
    junio. Año-mes-día no se confunde con nada. Lo que no tenga esa forma se
    deja como viene: es mejor que inventarle un orden.
    """
    if not raw:
        return None
    parts = _DMI_DATE.fullmatch(raw.strip())
    if parts is None:
        return raw.strip()
    month, day, year = (int(p) for p in parts.groups())
    if not (1 <= month <= 12 and 1 <= day <= 31):
        return raw.strip()
    return f"{year:04d}-{month:02d}-{day:02d}"


def bios_summary(board) -> str:
    """«AMI 1.80 (2023-06-08)»: de quién es la BIOS, cuál y de cuándo."""
    together = " ".join(p for p in (short_vendor(board.bios_vendor), board.bios_version) if p)
    date = bios_date(board.bios_date)
    return f"{together} ({date})" if together and date else together or DASH


def lock_tooltip(note) -> str:
    """Lo que dice el candado de un dato que falta por permisos.

    Por qué falta, con las palabras de la nota, y qué pasa al pulsarlo.
    """
    return f"{note.message}\n\n{_('lock.tip.outdated' if note.helper_outdated else 'lock.tip')}"


def permission_action(note) -> str:
    """The button of a note that needs permissions: give them, or update the
    installed helper when it is from another version."""
    return _("perm.replace.button") if note.helper_outdated else _("perm.button.read")


def permission_title(note, title: str) -> str:
    """A notice's title: the page's own, or that the helper is out of date."""
    return _("perm.outdated.title") if note.helper_outdated else title


# Cómo llama el kernel al dúplex de un enlace, y con qué clave se dice aquí.
# Lo que no esté en la tabla —«unknown», que es lo que da una interfaz sin
# cable— no se pinta: no es un dúplex, es que no hay negociación.
DUPLEX = {"full": "net.duplex.full", "half": "net.duplex.half"}


def link_summary(interface) -> Optional[str]:
    """«2.5 Gb/s · dúplex completo»: cómo quedó negociado el enlace.

    Estaba en el modelo, que lo componía con la palabra del kernel tal cual:
    la página de Red decía «2.5 Gb/s · full» con la interfaz en español.
    """
    if not interface.speed_mbps:
        return None
    if interface.speed_mbps >= 1000:
        speed = f"{interface.speed_mbps / 1000:g} Gb/s"
    else:
        speed = f"{interface.speed_mbps} Mb/s"
    key = DUPLEX.get((interface.duplex or "").lower())
    return f"{speed} · {_(key)}" if key else speed


def rate(value: Optional[float], bits: bool = False) -> str:
    """Un ritmo de transferencia: «2.1 MB/s» o «17.6 Mb/s», a elegir.

    Las dos unidades son correctas y se llevan un factor de ocho, que es
    justo lo que confunde: el mismo enlace son 116 MB/s en un gestor de
    descargas y 931 Mb/s en un test de velocidad. Como no hay una respuesta
    buena para todo el mundo, se ofrecen las dos y decide quien mira.

    Las dos van en potencias de mil, no de 1024. En redes esa es la convención
    (un enlace «gigabit» son mil millones de bits por segundo) y respetarla
    hace que las dos unidades cuadren entre sí y con lo que enseña un test de
    velocidad: los mismos datos son 116 MB/s y 931 Mb/s, exactamente ocho
    veces. Con potencias de 1024 saldrían 976 y nadie entendería de dónde sale
    la diferencia. Los totales acumulados sí usan 1024, como el resto del
    programa, porque ahí la referencia es el disco y no el cable.
    """
    if _none(value):
        return DASH
    value = float(value) * (8 if bits else 1)
    scale = ((1e9, "Gb/s" if bits else "GB/s"),
              (1e6, "Mb/s" if bits else "MB/s"),
              (1e3, "kb/s" if bits else "kB/s"))
    for factor, unit in scale:
        if value >= factor:
            return f"{value / factor:.1f} {unit}"
    return f"{value:.0f} {'b/s' if bits else 'B/s'}"


def traffic_summary(traffic: NetworkTraffic) -> str:
    """«↓ 1.2 GB · ↑ 456 MB», el histórico desde que se levantó la interfaz."""
    if not traffic.total_bytes:
        return DASH
    return f"↓ {size(traffic.rx_bytes)}   ↑ {size(traffic.tx_bytes)}"


def interface_state(interface: NetworkInterface) -> str:
    """En qué estado está el enlace, en una palabra."""
    if not interface.up:
        # Distinguir «apagada» de «encendida pero sin cable» ahorra ir a mirar
        # detrás del equipo, pero solo tiene sentido donde hay un cable que
        # mirar: un puente de máquinas virtuales o un túnel están parados, no
        # desenchufados.
        cabled = interface.kind in ("ethernet", "wifi")
        if cabled and interface.carrier is False:
            return _("net.state.nosignal" if interface.kind == "wifi"
                     else "net.state.nocable")
        return _("net.state.down")
    if interface.ipv4 or interface.ipv6:
        return _("net.state.up")
    return _("net.state.noaddress")


def rpm(value: Optional[int]) -> str:
    return DASH if _none(value) else f"{int(value)} RPM"


def fan(rpm_value: Optional[int], percent_value: Optional[float]) -> str:
    """El ventilador, con las dos cifras o con la que haya.

    Cada driver da una cosa: amdgpu publica las revoluciones y NVML solo el
    porcentaje. Juntar «—» con «(0.0 %)» quedaba como si faltara un dato y
    sobrara otro, cuando lo que dicen los dos es que está parado.
    """
    stopped = (rpm_value == 0) or (percent_value == 0)
    if _none(rpm_value) and _none(percent_value):
        return DASH
    if stopped:
        return _("fan.stopped")
    parts = []
    if not _none(rpm_value):
        parts.append(f"{int(rpm_value)} RPM")
    if not _none(percent_value):
        parts.append(f"({percent(percent_value)})" if parts else percent(percent_value))
    return "   ".join(parts)


# Lo que una razón social lleva detrás del nombre, y que nadie dice.
_LEGAL_FORM = re.compile(
    r"[,\s]+(?:Co\.?,?\s*Ltd\.?|Inc\.?|Corp(?:oration)?\.?|Ltd\.?|Limited|LLC|GmbH"
    r"|S\.?A\.?|AG|B\.?V\.?)$", re.IGNORECASE)
_BRAND_IN_BRACKETS = re.compile(r"\[([^\]]+)\]\s*$")


def maker(name: Optional[str]) -> Optional[str]:
    """La marca de un fabricante, no su razón social.

    «Micro-Star International Co., Ltd. [MSI]» es una MSI y «Tul Corporation
    / PowerColor» una PowerColor. El firmware y `pci.ids` dan el nombre de la
    empresa; aquí se deja el que lleva la caja. Primero los que se conocen
    (`model.short_vendor`), después lo que el propio `pci.ids` marca como
    nombre comercial —entre corchetes, o tras la barra— y, si no, se le quita
    la forma jurídica del final.
    """
    if not name:
        return None
    known = short_vendor(name)
    if known != name:
        return known
    if (bracketed := _BRAND_IN_BRACKETS.search(name)):
        return bracketed.group(1).split("/")[0]
    if " / " in name:
        return name.rsplit(" / ", 1)[1].strip()
    clean = name.strip()
    while (short := _LEGAL_FORM.sub("", clean)) != clean and short:
        clean = short
    return clean


def memory_maker(name: Optional[str]) -> Optional[str]:
    """A memory module's maker, also when the firmware writes its JEDEC code.

    MSI's writes «04EF» (bank 5, Team Group) where others write the name: the
    first byte counts continuation codes, the second is the code, both with
    their parity bit.
    """
    if name and re.fullmatch(r"[0-9A-Fa-f]{4}", name.strip()):
        from .spd import _vendor
        code = int(name.strip(), 16)
        vendor_name = _vendor(code >> 8, code & 0xFF)
        return maker(vendor_name) if vendor_name else _("mem.maker.code").format(codigo=name.strip())
    return maker(name)


def with_maker(vendor: Optional[str], model: Optional[str]) -> Optional[str]:
    """El nombre de un producto empezando por su marca.

    `pci.ids` da el modelo sin el fabricante: «RTL8111/8168/8211/8411 PCI
    Express Gigabit Ethernet Controller» no dice que es una Realtek, y es
    lo primero que se busca. Si el modelo ya empieza por la marca, no se
    repite.
    """
    if not model:
        return None
    brand = maker(vendor)
    if not brand or model.lower().startswith(brand.lower()):
        return model
    return f"{brand} {model}"


def network_kind(kind: Optional[str]) -> str:
    """El tipo de una interfaz, dicho en el idioma de la interfaz: «Ethernet»,
    «Wi-Fi», «Puente». El proveedor guarda la clave y no el texto."""
    if not kind:
        return DASH
    text = _(f"net.kind.{kind}")
    return kind if text == f"net.kind.{kind}" else text


def network_name(interface) -> str:
    """Cómo se llama una tarjeta de red: su modelo con la marca, o el nombre
    de la interfaz si no se sabe el modelo."""
    return with_maker(interface.vendor, interface.model) or interface.name


# El kernel le pega al nombre de algunos chips dónde los encontró: la
# dirección del Super I/O («it8688_40050607») o el bus MDIO de la tarjeta de
# red («r8169_0_600:00»). Sirve para distinguir dos iguales, no para leerlo.
_CHIP_ADDRESS = re.compile(r"(?:_[0-9a-f]{6,}|_\d+_[0-9a-f]+:\d+)$")


def chip_name(chip: str) -> str:
    """El nombre de un chip de sensores sin la dirección que le pega el kernel."""
    return _CHIP_ADDRESS.sub("", chip)


# Cómo se escribe cada bus. El kernel los da en minúsculas, y pasarlos todos
# a mayúsculas deja «NVME» al lado de un «NVMe» bien escrito.
_BUSES = {"nvme": "NVMe"}


def disk_bus(transport: Optional[str]) -> str:
    """El bus de un disco como se escribe: «NVMe», «SATA», «USB»."""
    if not transport:
        return DASH
    return _BUSES.get(transport, transport.upper())


def pcie_link(link: PcieLink, maximum: bool = False) -> str:
    """«PCIe 5.0 × 16», que es como lo nombra todo el mundo menos sysfs."""
    generation = link.max_generation if maximum else link.generation
    width = link.max_width if maximum else link.current_width
    speed = link.max_speed_gts if maximum else link.current_speed_gts
    if generation is None and speed is None:
        return DASH
    name = f"PCIe {generation}.0" if generation else f"{speed:g} GT/s"
    return f"{name} × {width}" if width else name


def gpu_link(gpu) -> str:
    """The link a card reaches, which names it: the maximum, not the one of
    the moment, which drops at idle; the current one when that's all."""
    if not gpu.link:
        return DASH
    reached = pcie_link(gpu.link, maximum=True)
    return reached if reached != DASH else pcie_link(gpu.link)


def pcie_note(link: PcieLink) -> Optional[str]:
    """Por qué el enlace va más lento de lo que puede, cuando pasa.

    Casi siempre es que la tarjeta está en reposo y el driver ha bajado el
    enlace para gastar menos, así que se dice como apunte y no como aviso: en
    una máquina parada es lo que tiene que ocurrir.
    """
    if not link.downgraded:
        return None
    if link.fewer_lanes_at_full_speed:
        # Saving power usually lowers the speed; fewer lanes at full speed
        # may be the card's own power saving or a link trained narrower.
        return _("pcie.now.lanes").format(actual=pcie_link(link),
                                          max=pcie_link(link, maximum=True))
    return _("pcie.now").format(actual=pcie_link(link),
                                max=pcie_link(link, maximum=True))


def gpu_memory_summary(memory: GpuMemory) -> str:
    """«2.0 GB de 15.9 GB  (12 %)», o nada si no se sabe cuánta se usa.

    Antes, cuando el driver no publicaba la memoria ocupada, esto devolvía el
    total. La página lo pintaba bajo el renglón «En uso» y el resultado era
    que una integrada de Intel declaraba tener los 11,6 GB ocupados al
    completo. Un dato que falta se dice que falta.
    """
    if memory.total_bytes is None or memory.used_bytes is None:
        return DASH
    return (_("gpu.vram.of").format(usado=size(memory.used_bytes),
                                    total=size(memory.total_bytes))
            + f"   ({memory.used_percent:.0f} %)")


def possible_texts(formatter, top: float) -> list[str]:
    """Lo que `formatter` puede escribir para un valor entre 0 y `top`.

    Para reservar el ancho del más largo y que la columna no baile al
    cambiar las cifras. Lo más largo sale justo antes de un cambio de unidad
    o de un dígito más («1023.9 MB», «999.9 W»), así que se prueba ahí en
    base 2 y en base 10, y un poco por encima del tope: un consumo puede
    pasar un instante del suyo. Y más cerca todavía, donde el redondeo ya
    sube y la unidad aún no ha cambiado: 999,96 MB/s se escribe «1000.0
    MB/s», una cifra más que «999.9».
    """
    ceiling = float(top) * 1.1
    runs = {0.0, float(top), ceiling}
    for base in (2, 10):
        power_value = 1.0
        while power_value <= ceiling:
            for margin in (1e-4, 1e-6):
                runs.add(power_value * (1 - margin))
            power_value *= base
    texts = []
    for value in sorted(runs):
        text = formatter(value)
        if text not in texts:
            texts.append(text)
    return texts


def bandwidth(value: Optional[int]) -> str:
    """El ancho de banda de la memoria, en las unidades de las fichas técnicas."""
    if _none(value):
        return DASH
    return f"{float(value) / 1e9:.0f} GB/s"


def vram_kind(memory: GpuMemory) -> str:
    """El tipo de memoria a secas: GDDR6, HBM2e. Nada más.

    Antes devolvía «GDDR6 · 256 bits» y, cuando no se conocía el tipo, un
    escueto «128 bits» en un campo que se llamaba «Tipo». La anchura del bus es
    otro dato distinto y tiene su propia fila.
    """
    return memory.kind or DASH


def vram_bus(memory: GpuMemory) -> str:
    """La anchura del bus de memoria: «256 bits»."""
    return (_("gpu.bus.bits").format(n=memory.bus_bits)
            if memory.bus_bits else DASH)


# Cada fabricante cuenta sus unidades de proceso de una forma y no son
# equivalentes entre sí.
PROCESSING_UNITS = {
    "NVIDIA": "gpu.units.cuda",
    "AMD": "gpu.units.cu",
    "Intel": "gpu.units.eu",
}


def compute_units(gpu) -> str:
    """«64 unidades de cómputo», «2048 núcleos CUDA»."""
    if not gpu.compute_units:
        return DASH
    key = PROCESSING_UNITS.get(gpu.vendor or "", "gpu.units.generic")
    return f"{gpu.compute_units} {_(key)}"


def compute_units_short(gpu) -> Optional[str]:
    """Lo mismo pero para una insignia: «64 CU», «2048 CUDA»."""
    if not gpu.compute_units:
        return None
    short = {"NVIDIA": "CUDA", "AMD": "CU", "Intel": "EU"}.get(gpu.vendor or "", "u.")
    return f"{gpu.compute_units} {short}"


def resizable_bar(memory: GpuMemory) -> str:
    """Si la CPU alcanza toda la VRAM o solo una ventana de 256 MB."""
    if memory.resizable_bar is None:
        return DASH
    if memory.resizable_bar:
        return _("gpu.rebar.on")
    window = size(memory.visible_bytes) if memory.visible_bytes else DASH
    return _("gpu.rebar.off").format(ventana=window)


# Los bits de `critical_warning` del registro de salud de NVMe, que es donde
# un disco dice que tiene un problema. Están definidos por la especificación y
# significan lo mismo en todas las marcas.
# De dónde sacar en qué canal está un módulo. El firmware lo escribe de varias
# maneras según quién haga la placa, y ninguna es obligatoria: «P0 CHANNEL A»
# en el banco, «DIMM_A1» en el localizador, «ChannelA-DIMM0» en los portátiles.
_CHANNEL = (
    re.compile(r"CHANNEL[\s_-]*([A-H])\b", re.I),
    re.compile(r"\bDIMM[\s_-]*([A-H])\d", re.I),
    re.compile(r"\bCH([A-H])\b", re.I),
)

# Y de qué controlador cuelga, cuando el firmware lo dice. Hace falta porque la
# letra sola no identifica un canal: un ThinkPad con dos módulos los llama
# «Controller0-ChannelA» y «Controller1-ChannelA-DIMM0», que son los dos
# «canal A» y son dos canales distintos, uno por controlador. Contando solo
# letras salía «canal único» en una máquina que va en doble canal, con el
# agravante de que entonces aconseja repartir los módulos: repartidos ya
# estaban.
_CONTROLLER = re.compile(r"CONTROLLER[\s_-]*(\d+)", re.I)

# Cómo se llama tener tantos canales poblados. Por encima de cuatro se dice el
# número, que «óctuple canal» no lo usa nadie.
CHANNEL_NAMES = {1: "mem.chan.1", 2: "mem.chan.2",
                     3: "mem.chan.3", 4: "mem.chan.4"}


def _channel_of(module) -> Optional[str]:
    """Qué canal ocupa un módulo, si el firmware lo dice.

    No devuelve la letra sino algo que identifique el canal de verdad: cuando
    el localizador nombra el controlador, la letra por sí sola se repite entre
    ellos y dos módulos bien repartidos parecían estar en el mismo sitio.
    """
    for text in (module.bank, module.locator):
        if not text:
            continue
        for pattern in _CHANNEL:
            if (match := pattern.search(text)):
                letter = match.group(1).upper()
                controller = _CONTROLLER.search(text)
                return f"{controller.group(1)}:{letter}" if controller else letter
    return None


def memory_channels(modules) -> Optional[int]:
    """Cuántos canales tienen al menos un módulo puesto.

    Devuelve None cuando el firmware no dice en qué canal está cada zócalo, que
    pasa en placas que numeran los bancos en vez de nombrarlos. Inventarse el
    dato ahí sería peor que no darlo: en canal único la memoria rinde la mitad,
    y decirlo al revés manda a alguien a abrir el equipo para nada.
    """
    populated = [m for m in modules if m.populated]
    if not populated:
        return None
    channels = {c for m in populated if (c := _channel_of(m))}
    return len(channels) or None


def memory_channel_label(modules) -> Optional[str]:
    """«Doble canal», «canal único»… con cuántos módulos lo forman."""
    count = memory_channels(modules)
    if count is None:
        return None
    name = (_(CHANNEL_NAMES[count]) if count in CHANNEL_NAMES
              else _("mem.chan.n").format(n=count))
    fitted = sum(1 for m in modules if m.populated)
    modules_text = _("mem.modules.one" if fitted == 1
                    else "mem.modules.many").format(n=fitted)
    return f"{name} · {modules_text}"


def nanoseconds(value: Optional[float]) -> str:
    """«0.9 ns». Un decimal: la L1 de cualquier procesador anda por ahí y con
    cero decimales todas las cachés rápidas saldrían iguales."""
    return DASH if _none(value) else f"{float(value):.1f} ns"


def memory_theoretical_bandwidth(modules) -> Optional[int]:
    """Lo que daría esta memoria si nada la frenara, en bytes por segundo.

    Es una multiplicación, no una medida: las transferencias por segundo por
    los ocho bytes que mueve cada una, por los canales que estén poblados. Vale
    para poner al lado de lo medido y ver cuánto se aprovecha; sola no dice
    gran cosa, porque ninguna máquina llega a su teórico.

    Sin saber los canales no se calcula. Suponer dos es justo el error que ya
    costó un aviso equivocado en la ficha de al lado: en canal único la memoria
    rinde la mitad, y aquí saldría un porcentaje que dobla al de verdad.
    """
    channels = memory_channels(modules)
    if not channels:
        return None
    speeds = [m.configured_mts or m.speed_mts for m in modules
                   if m.populated and (m.configured_mts or m.speed_mts)]
    if not speeds:
        return None
    # La más lenta: el controlador iguala a la baja lo que le pongan.
    return min(speeds) * 1_000_000 * 8 * channels


def memory_bandwidth_share(measured_value: Optional[int], theoretical: Optional[int]) -> Optional[float]:
    """Qué fracción del teórico se está consiguiendo, en tanto por ciento."""
    if not measured_value or not theoretical:
        return None
    return round(measured_value / theoretical * 100, 1)


# Los trozos que los firmwares pegan en el localizador de un zócalo. Salen así,
# sin espacios y cada fabricante a su manera: «Controller0-ChannelA»,
# «ChannelA-DIMM0», «DIMM_A1», «DIMM A», «DIMM 0».
_SLOT_CONTROLLER = re.compile(r"controller\s*[-_]?\s*(\d+)", re.I)
_SLOT_CHANNEL = re.compile(r"chan(?:nel)?\s*[-_]?\s*([a-z])\b", re.I)
# «DIMM_A1» lleva canal y número pegados; «DIMM 0» solo número; «DIMM A» solo
# canal. El orden importa: el primero que casa gana.
_SLOT_DIMM_CHANNEL_AND_NUMBER = re.compile(r"dimm\s*[-_]?\s*([a-z])\s*(\d+)", re.I)
_SLOT_DIMM_NUMBER = re.compile(r"dimm\s*[-_]?\s*(\d+)", re.I)
_SLOT_DIMM_CHANNEL = re.compile(r"dimm\s*[-_]?\s*([a-z])\b", re.I)


def _slot_parts(locator: str) -> dict:
    """Qué dice el localizador de un zócalo, campo a campo.

    Vacío si no se reconoce nada, y entonces quien llama deja el texto crudo:
    inventarse una posición a partir de algo que no se entiende es peor que
    enseñar lo que puso el firmware.
    """
    pieces: dict = {}
    if (home := _SLOT_CONTROLLER.search(locator)):
        pieces["controlador"] = home.group(1)
    if (home := _SLOT_CHANNEL.search(locator)):
        pieces["canal"] = home.group(1).upper()

    if (home := _SLOT_DIMM_CHANNEL_AND_NUMBER.search(locator)):
        pieces.setdefault("canal", home.group(1).upper())
        pieces["dimm"] = home.group(2)
    elif (home := _SLOT_DIMM_NUMBER.search(locator)):
        pieces["dimm"] = home.group(1)
    elif (home := _SLOT_DIMM_CHANNEL.search(locator)):
        pieces.setdefault("canal", home.group(1).upper())
    return pieces


# Cómo se llama cada velocidad de USB. Es la negociada, no la versión del
# dispositivo: un teclado USB 2.0 va a 12 Mb/s y está bien.
_USB_SPEEDS = {1.5: "usb.speed.low", 12.0: "usb.speed.full", 480.0: "usb.speed.high",
                    5000.0: "usb.speed.super", 10000.0: "usb.speed.superplus",
                    20000.0: "usb.speed.superplus", 40000.0: "usb.speed.usb4"}
USB_KINDS = {
    "hub": "usb.kind.hub", "keyboard": "usb.kind.keyboard", "mouse": "usb.kind.mouse",
    "keyboard_mouse": "usb.kind.keyboardmouse", "input": "usb.kind.input",
    "audio": "usb.kind.audio", "video": "usb.kind.video", "storage": "usb.kind.storage",
    "wireless": "usb.kind.wireless", "smartcard": "usb.kind.smartcard",
    "comm": "usb.kind.comm", "printer": "usb.kind.printer", "vendor": "usb.kind.vendor",
    "other": "usb.kind.other",
}


def usb_speed(mbps: Optional[float]) -> str:
    """«Velocidad completa · 12 Mb/s», «SuperSpeed · 5 Gb/s»."""
    if _none(mbps):
        return DASH
    figure = f"{mbps / 1000:g} Gb/s" if mbps >= 1000 else f"{mbps:g} Mb/s"
    key = _USB_SPEEDS.get(float(mbps))
    return f"{_(key)} · {figure}" if key else figure


def usb_kind(device) -> str:
    return _(USB_KINDS.get(device.kind, "usb.kind.other"))


def usb_name(device) -> str:
    """El nombre del dispositivo; si no lo trae (o la foto es anónima), lo que es."""
    name = usb_kind(device)
    return device.product or (name[:1].upper() + name[1:])


def sound_card(card) -> str:
    """«HDMI de la gráfica», «Placa base · Realtek ALCS1200A», o el nombre
    del aparato USB. No los de ALSA («HDA ATI HDMI», «HD-Audio Generic»)."""
    if card.kind == "hdmi":
        return _("sound.hdmi")
    if card.kind == "board":
        return _("sound.board").format(codec=card.codec) if card.codec else _("sound.board.plain")
    if card.kind == "usb":
        return card.name or _("sound.usb.camera" if card.camera else "sound.usb")
    return card.name or _("sound.other")


def space(disks) -> tuple[int, int, int, int]:
    """Used, free, reserved and unmounted bytes of these disks.

    Free is what the mounted partitions say; what is mounted and is neither
    used nor free is the filesystem's own (ext4 keeps 5 % for root, and its
    tables); what is not mounted (another system, a swap partition, space
    outside any partition) is said apart. A tester's laptop, all of it
    mounted, read «Sin montar 8.6 GB» that were ext4's.
    """
    used = free = reserved = mounted = 0
    for disk in disks:
        for partition in disk.mounted_partitions:
            used += partition.used_bytes or 0
            free += partition.free_bytes or 0
            if partition.size_bytes:
                mounted += partition.size_bytes
                reserved += max(0, partition.size_bytes - (partition.used_bytes or 0)
                                 - (partition.free_bytes or 0))
    total = sum(d.size_bytes or 0 for d in disks)
    unmounted = max(0, total - mounted)
    # Below 1 % of what they are part of it is a vfat's clusters and the
    # partitions' alignment: «Sin montar 1.6 MB» is not space anyone looks for.
    return (used, free, reserved if reserved >= mounted / 100 else 0,
            unmounted if unmounted >= total / 100 else 0)


def trim(disk) -> Optional[str]:
    """Lo que se ve del TRIM de una unidad, sin afirmar más de lo que se ve.

    «Lo admite» es un hecho. Que se esté haciendo es una señal: la partición
    montada con `discard`, o el temporizador `fstrim.timer` activado, que
    puede no cubrir esa partición. Un disco de platos que admite descartes es
    un SMR, y se dice así; uno virtual no es de platos aunque lo diga. El que
    no los admite no enseña la fila.
    """
    if not disk.discard:
        return None
    parts = [_("disk.trim.smr") if disk.kind == "HDD" else _("disk.trim.yes")]
    if disk.discard_mounted:
        parts.append(_("disk.trim.mounted"))
    if disk.fstrim_timer:
        parts.append(_("disk.trim.timer"))
    if len(parts) == 1 and disk.kind != "HDD":
        parts.append(_("disk.trim.unseen"))
    return " · ".join(parts)


# Los atributos SMART de un disco SATA que significan lo mismo en casi todos.
# Los demás se enseñan con su número: su nombre depende del fabricante.
SMART_COMMON = {
    1: "smart.attr.1", 5: "smart.attr.5", 9: "smart.attr.9", 12: "smart.attr.12",
    187: "smart.attr.187", 188: "smart.attr.188", 194: "smart.attr.194",
    197: "smart.attr.197", 198: "smart.attr.198", 199: "smart.attr.199",
    241: "smart.attr.241", 242: "smart.attr.242",
}


def smart_rows(health) -> list[tuple[str, str]]:
    """El diagnóstico entero de un disco, en filas de nombre y valor.

    Primero lo que tiene nombre fijo (lo de NVMe viene así de la norma) y
    después, en un SATA, la tabla de atributos tal cual: número, nombre si es
    de los comunes, valor normalizado y contador en crudo.
    """
    rows: list[tuple[str, str]] = []
    for key, value in (
            ("smart.cycles", health.power_cycles), ("smart.unsafe", health.unsafe_shutdowns),
            ("smart.mediaerrors", health.media_errors),
            ("smart.spare", f"{health.spare_percent} %" if health.spare_percent is not None else None),
            ("smart.read", size(health.read_bytes) if health.read_bytes else None),
            ("smart.warning", None if health.critical_warning is None
             else _("smart.warning.none") if health.critical_warning == 0
             else f"0x{health.critical_warning:02x}")):
        if value is not None:
            rows.append((_(key), thousands(value) if isinstance(value, int) else str(value)))
    for number, normalized, raw in health.attributes:
        name = _(SMART_COMMON[number]) if number in SMART_COMMON else _("smart.attr.other")
        rows.append((f"{number} · {name}", _("smart.attr.value").format(
            normalizado=normalized, crudo=thousands(raw))))
    return rows


def iommu(platform) -> str:
    """«activa · 34 grupos» o «sin activar»."""
    if not platform.iommu_groups:
        return _("plat.iommu.off")
    return _("plat.iommu.on").format(n=platform.iommu_groups)


def virtualization(platform) -> Optional[str]:
    """«activa (AMD-V), en uso por KVM», o que el procesador la tiene.

    Que la bandera esté no dice que la BIOS la haya dejado encendida; que
    exista `/dev/kvm` sí. Sin él no se sabe si es la BIOS o que falta el
    módulo, y se dice justo eso.
    """
    if not platform.virtualization:
        return None
    key = "plat.virt.active" if platform.virtualization == "active" else "plat.virt.present"
    return _(key).format(tipo=platform.virtualization_kind or "")


def above_4g(platform) -> Optional[str]:
    """«activo · 4 dispositivos lo usan». Sin ninguno no se afirma nada."""
    if not platform.above_4g_devices:
        return None
    return _("plat.above4g.one" if platform.above_4g_devices == 1
             else "plat.above4g.many").format(n=platform.above_4g_devices)


# El separador de miles: un espacio fino que no parte la línea (U+202F). Ni
# punto ni coma, que cada idioma lee como decimal el del otro: «4.136 h»
# parecían cuatro horas. Es lo que pide la norma (ISO 80000-1, el SI), y se
# lee igual en español que en inglés.
THOUSANDS_SPACE = "\u202f"


def thousands(value: Optional[int]) -> str:
    """«4 136»: un entero con los miles separados, igual en cualquier locale."""
    if _none(value):
        return DASH
    return f"{int(value):,}".replace(",", THOUSANDS_SPACE)


def seconds(value: Optional[float]) -> str:
    """«13.3 s»."""
    return DASH if _none(value) else f"{float(value):.1f} s"


def time_window(value: Optional[float]) -> str:
    """A RAPL time window, which goes from milliseconds to tens of seconds:
    «28.0 s», «2.4 ms»."""
    if _none(value):
        return DASH
    if value >= 1:
        return seconds(value)
    if value >= 1e-3:
        return f"{value * 1e3:.1f} ms"
    return f"{value * 1e6:.0f} µs"


def thermal_throttle(throttles) -> str:
    """«ninguno desde el arranque», or «5 en los núcleos (0.6 s) · 2 del
    procesador entero (1.4 s)»."""
    if throttles is None:
        return DASH
    parts = []
    if throttles.core_count:
        parts.append(_("cpu.throttle.cores").format(
            n=throttles.core_count, tiempo=seconds(throttles.core_ms / 1000)))
    if throttles.package_count:
        parts.append(_("cpu.throttle.package").format(
            n=throttles.package_count, tiempo=seconds(throttles.package_ms / 1000)))
    return " · ".join(parts) or _("cpu.throttle.none")


def power_limit(limit_w: Optional[float], window_s: Optional[float]) -> str:
    """«65.0 W · ventana de 28.0 s», or the watts alone without a window."""
    if _none(window_s):
        return watts(limit_w)
    return _("cpu.limit.window").format(limite=watts(limit_w), ventana=time_window(window_s))


# Qué es un dispositivo PCI por su clase, para nombrar lo que `pci.ids` no
# tiene. Las de `providers/pci.CLASES`: lo que la tabla de Placa enseña.
PCI_CLASSES = {
    "0300": "board.pci.class.vga", "0302": "board.pci.class.3d",
    "0380": "board.pci.class.display", "0108": "board.pci.class.nvme",
    "0106": "board.pci.class.ahci", "0104": "board.pci.class.raid",
    "0200": "board.pci.class.ethernet", "0280": "board.pci.class.network",
    "0c03": "board.pci.class.usb", "0403": "board.pci.class.hda",
    "0401": "board.pci.class.audio",
}


def pci_unnamed(device) -> Optional[str]:
    """«Intel, audio HD (8086:f0c8)»: lo que no está en `pci.ids`, por lo que es.

    La marca, la clase del dispositivo y su identificador, como lo busca quien
    lo quiera reportar o encontrar. Decir solo que no está en la lista era
    explicar el hueco sin decir qué hay.
    """
    brand = maker(device.vendor)
    ids = (f"{device.vendor_id:04x}:{device.device_id:04x}"
           if device.vendor_id is not None and device.device_id is not None else None)
    kind = PCI_CLASSES.get(device.pci_class or "")
    if brand and kind:
        text = _("board.pci.unnamed").format(marca=brand, clase=_(kind))
    else:
        text = brand or (_(kind) if kind else None)
    if ids:
        text = f"{text} ({ids})" if text else ids
    return text


# Las fases del arranque, en orden, con el campo de `Boot` de cada una.
BOOT_PHASES = (("sys.boot.phase.firmware", "firmware_s"),
                     ("sys.boot.phase.loader", "loader_s"),
                     ("sys.boot.phase.kernel", "kernel_s"),
                     ("sys.boot.phase.initrd", "initrd_s"),
                     ("sys.boot.phase.userspace", "userspace_s"),
                     ("sys.boot.phase.total", "total_s"))


def pcie_errors(link) -> str:
    """«ninguno desde el arranque», or «3 corregidos · 1 fatal»."""
    if link is None or link.correctable_errors is None:
        return DASH
    parts = []
    for count, key in ((link.correctable_errors, "pcie.errors.correctable"),
                       (link.nonfatal_errors, "pcie.errors.nonfatal"),
                       (link.fatal_errors, "pcie.errors.fatal")):
        if count:
            parts.append(_(key + (".one" if count == 1 else "")).format(n=thousands(count)))
    return " · ".join(parts) or _("pcie.errors.none")


def gpu_factory_power_limit(gpu) -> str:
    """«330.0 W · admite 231.0–340.0 W». The current cap isn't here: it
    is already in the power bar of «Right now»."""
    parts = []
    if gpu.power_cap_default_w is not None:
        parts.append(watts(gpu.power_cap_default_w))
    if gpu.power_cap_min_w and gpu.power_cap_max_w is not None:
        parts.append(_("gpu.power.range").format(desde=figure(gpu.power_cap_min_w, 1),
                                                  hasta=watts(gpu.power_cap_max_w)))
    elif gpu.power_cap_max_w is not None and gpu.power_cap_max_w != gpu.power_cap_default_w:
        # A minimum of 0 W is no limit: some drivers write it as «none».
        parts.append(_("gpu.power.upto").format(hasta=watts(gpu.power_cap_max_w)))
    return " · ".join(parts) or DASH


def gpu_power_limit_tip(gpu) -> str:
    """The current cap, and whether someone raised it above the factory one."""
    tip = _("gpu.tip.powercap").format(ahora=watts(gpu.power_cap_w))
    if (gpu.power_cap_w is not None and gpu.power_cap_default_w is not None
            and gpu.power_cap_w > gpu.power_cap_default_w):
        tip += " " + _("gpu.power.raised")
    return tip


# Bit by bit, as Documentation/admin-guide/tainted-kernels.rst lists them,
# with the letter each one has in /sys/module/<name>/taint.
TAINT_BITS = 20
TAINT_LETTERS = "PFSRMBUDAWCIOELKXTNJ"


def taint_reasons(mask: int, modules: tuple = ()) -> list[str]:
    """Why the kernel is tainted, one translated reason per bit set, with the
    modules that set it: «un módulo de fuera del kernel (nvidia)»."""
    reasons = []
    for bit in range(TAINT_BITS):
        if mask >> bit & 1:
            names = [name for name, letters in modules if TAINT_LETTERS[bit] in letters]
            reason = _(f"sys.taint.{bit}")
            reasons.append(f"{reason} ({', '.join(names)})" if names else reason)
    return reasons


def tainted(mask: int | None, modules: tuple = ()) -> str:
    """«no», or the reasons: «módulo de fuera del kernel · módulo sin firmar»."""
    if mask is None:
        return DASH
    if not mask:
        return _("sys.taint.no")
    reasons = taint_reasons(mask, modules)
    unknown = mask >> TAINT_BITS
    if unknown:
        reasons.append(_("sys.taint.other").format(mask=mask))
    return " · ".join(reasons)


def boot_phases(boot) -> list[tuple[str, str]]:
    """Cada fase que se sabe, con lo que tardó: [("sys.boot.phase.firmware", "5.2 s"), …].

    Cada una por separado y el total aparte, para que no quede la duda de si
    una incluye a otra: el cargador publica dos instantes contados desde el
    encendido, y enseñados tal cual no se sabe si el segundo suma al primero.
    Sin el firmware no hay total (`Boot.total_s`).
    """
    return [(key, seconds(getattr(boot, field))) for key, field in BOOT_PHASES
            if getattr(boot, field) is not None]


def swap_summary(swap) -> str:
    """«45.0 MB de 31.3 GB · zstd · comprime 2.1 a 1 · prioridad 100»."""
    parts = [_("sys.swap.used").format(usado=size(swap.used_bytes), total=size(swap.size_bytes))]
    if swap.zram:
        if swap.algorithm:
            parts.append(swap.algorithm)
        if swap.ratio:
            parts.append(_("sys.swap.ratio").format(n=f"{swap.ratio:.1f}"))
    if swap.priority is not None:
        parts.append(_("sys.swap.priority").format(n=swap.priority))
    return " · ".join(parts)


def swap_name(swap) -> str:
    """«zram0 (en memoria)», «/swapfile (archivo)», «/dev/sda2 (partición)»."""
    if swap.zram:
        return _("sys.swap.zram").format(nombre=swap.device.rsplit("/", 1)[-1])
    return _("sys.swap.file" if swap.kind == "file" else "sys.swap.partition").format(
        nombre=swap.device)


# Los drivers del kernel cuya parte de usuario es Mesa.
_MESA_DRIVERS = ("amdgpu", "radeon", "i915", "xe", "nouveau")


def graphics_stack(snapshot) -> Optional[str]:
    """«Mesa 26.2.6», o «NVIDIA 570.86» con el driver propietario.

    No se lee nada nuevo: con un driver libre, la versión que declara OpenGL
    es la de Mesa («26.2.6-arch3.1», y aquí sin la coletilla del paquete).
    """
    for gpu in snapshot.gpus:
        if gpu.driver in _MESA_DRIVERS:
            for api in gpu.apis:
                if api.name == "OpenGL" and api.driver:
                    return f"Mesa {api.driver.split('-')[0]}"
        elif gpu.driver == "nvidia" and gpu.driver_version:
            return f"NVIDIA {gpu.driver_version}"
    return None


def enumeration(pieces, last: str = "list.and") -> str:
    """«el fabricante, los chips y la fecha»: una lista como se dice.

    Para las notas que nombran lo que falta. Una lista de nombres de campo
    separados por comas («Sin Chips, Perfiles rápidos, Fabricado») se lee
    como un formulario; una frase no. `ultima` es la clave de la conjunción:
    «y» por omisión, «ni» para lo que se niega.
    """
    pieces = [p for p in pieces if p]
    if len(pieces) <= 1:
        return "".join(pieces)
    return f"{', '.join(pieces[:-1])} {_(last)} {pieces[-1]}"


def slot_names(zocalos: list[tuple[Optional[str], Optional[str]]]) -> list[str]:
    """El nombre de cada zócalo, por orden: único, y que se entienda.

    Recibe el localizador y el banco de cada uno, como los da el firmware, y
    devuelve un nombre por zócalo en el mismo orden. Es por posición y no por
    localizador porque el localizador se repite: una Gigabyte X570 llama a
    sus cuatro zócalos «DIMM 0», «DIMM 1», «DIMM 0», «DIMM 1» y pone el canal
    en el banco («P0 CHANNEL A», «P0 CHANNEL B»). Con un diccionario por
    localizador los dos módulos puestos se llamaban «DIMM 1» y los dos huecos
    «DIMM 0».

    Cada fabricante reparte el dato a su manera —ASUS «DIMM_A2», MSI
    «DIMM_A1», los OEM «ChannelA-DIMM0», Lenovo «Controller0-ChannelA»—, así
    que se junta lo que digan los dos campos. La regla: **el canal sale
    siempre que se conozca**, porque es lo que decide el rendimiento y es lo
    que se busca al abrir esto; el número de DIMM y el controlador solo
    cuando sin ellos dos zócalos se llamarían igual.

    Si alguno no se entiende se deja lo que puso el firmware, que es mejor que
    inventar una posición; y si aun así dos coinciden, se les añade el banco
    y, en último caso, su número de orden. Nunca salen dos iguales.
    """
    raw_values = [(localizador or "").strip() for localizador, _bank in zocalos]
    pieces = []
    for localizador, bank_name in zocalos:
        own = _slot_parts(localizador or "")
        # El banco completa lo que el localizador calla, y nunca lo corrige.
        for field, value in _slot_parts(bank_name or "").items():
            if field != "dimm":
                own.setdefault(field, value)
        pieces.append(own)

    def tag(own: dict, fields: tuple) -> str:
        parts = []
        if "controlador" in fields and "controlador" in own:
            parts.append(_("memory.slot.controller").format(n=own["controlador"]))
        if "canal" in own:
            parts.append(_("memory.slot.channel").format(c=own["canal"]))
        if "dimm" in fields and "dimm" in own:
            parts.append(_("memory.slot.dimm").format(n=own["dimm"]))
        return " · ".join(parts)

    if pieces and all(pieces):
        # De menos a más: se añade un campo solo si sin él dos zócalos se
        # llamarían igual, y antes uno que dos.
        # The controller before the DIMM number: a channel is a controller's
        # letter, and two «Channel A» on two controllers are two channels.
        for fields in ((), ("controlador",), ("dimm",), ("dimm", "controlador")):
            names = [tag(own, fields) for own in pieces]
            if all(names) and len(set(names)) == len(names):
                return names

    # No se entiende, o ni con todo se distinguen: lo del firmware, y lo
    # mínimo para que no haya dos iguales.
    names = [raw or _("memory.slot") for raw in raw_values]
    if len(set(names)) < len(names):
        repeated = {n for n in names if names.count(n) > 1}
        names = [f"{name} · {memory_bank(bank_name)}"
                   if name in repeated and bank_name and bank_name.strip() else name
                   for name, (_locator, bank_name) in zip(names, zocalos)]
    if len(set(names)) < len(names):
        repeated = {n for n in names if names.count(n) > 1}
        vistos: dict[str, int] = {}
        out = []
        for name in names:
            if name in repeated:
                vistos[name] = vistos.get(name, 0) + 1
                name = f"{name} ({vistos[name]})"
            out.append(name)
        names = out
    return names


_REDUNDANT_BANK = re.compile(r"^bank[\s_-]*", re.I)


def memory_bank(bank: Optional[str]) -> Optional[str]:
    """El banco sin repetir la palabra que ya lleva la fila.

    El firmware escribe «BANK 0» y la fila se titula «Banco», así que se leía
    «Banco: BANK 0». Solo se quita cuando el valor empieza por ahí y queda algo
    detrás: los localizadores de banco que traen más cosas —«Node0_Bank0»— se
    dejan enteros, porque ahí el resto sí distingue.
    """
    if not bank:
        return bank
    clean = _REDUNDANT_BANK.sub("", bank.strip()).strip()
    return clean or bank


def memory_speed(mts: Optional[int]) -> Optional[int]:
    """El nombre del grado al que corresponde una velocidad del firmware.

    La tabla SMBIOS trae lo que la BIOS haya escrito, y cada una redondea a su
    manera los grados que llevan tercio: DDR4-2666 son 2666,67 MT/s y unas
    ponen 2666 y otras 2667. Enseñar el crudo dejaba en la misma ficha dos
    convenciones —«Catalogado a 3200» y «Funcionando a 2667»— cuando 2667 no es
    el nombre de ninguna velocidad.

    Se normaliza **al pintar** y no antes: el modelo sigue guardando lo que dijo
    el firmware, que es lo que hace falta para contrastar con `dmidecode`, y de
    eso se encarga el tooltip de la fila.
    """
    if not mts:
        return mts
    return jedec_grade(mts) or mts


def memory_module_verdict(module, limit=None) -> Optional[str]:
    """Si un módulo va más lento de lo que admite, y por qué.

    None si va a lo suyo; «cpu_max» si va al máximo oficial del procesador
    (`limite`, de `db.memory_limit`), que no es un fallo ni un perfil sin
    activar; «slow» si va por debajo sin que eso lo explique.
    """
    if not module.underclocked:
        return None
    current = memory_speed(module.configured_mts or module.speed_mts)
    if limit and current and current >= limit.mts * (1 - ROUNDING_MARGIN):
        return "cpu_max"
    return "slow"


def memory_limit_label(limit) -> str:
    """«i5-10400», o «Ryzen 7 5800X3D con 2 módulos de 1 rango».

    En AMD la cifra vale para esa disposición de módulos y no para otra: con
    cuatro de dos rangos el mismo procesador garantiza menos. Se dice.
    """
    if not limit.layout:
        return limit.model
    count, ranges = limit.layout.rstrip("R").split("x")
    return _("mem.layout.one" if ranges == "1" else "mem.layout.many").format(
        modelo=limit.model, n=count, r=ranges)


def memory_speed_warning(modules, limit=None, chipset: bool = False) -> Optional[str]:
    """Por qué la memoria no va más rápido, cuando hay algo que decir.

    El techo del conjunto no es el del módulo más rápido: es el del más lento,
    porque todos van al mismo reloj. Con uno de 3200 y otro de 2667 el equipo
    no verá 3200 active lo que active, así que prometerlo mandaba a alguien a
    pelearse con la BIOS para nada. Lo trajo un ThinkCentre M80q, que además
    llevaba los dos módulos desparejos.

    Tres respuestas y no dos: hay margen de verdad —y entonces el perfil
    rápido sin activar es la explicación de siempre—, no hay margen pero un
    módulo declara más que otro —y eso es lo que hay que contar, porque si no
    la cifra alta de la ficha no se entiende—, o no hay nada que decir.
    """
    fitted = [m for m in modules if m.populated and m.rated_mts]
    if not fitted:
        return None
    current = memory_speed(
        max((m.configured_mts or m.speed_mts or 0) for m in fitted))
    if not current:
        return None

    ceiling = min(m.rated_mts for m in fitted)
    highest = max(m.rated_mts for m in fitted)

    if current < ceiling * (1 - ROUNDING_MARGIN):
        # Al máximo del procesador no hay perfil que activar: es lo que su
        # fabricante garantiza, y los módulos rápidos no lo cambian.
        if limit and current >= limit.mts * (1 - ROUNDING_MARGIN):
            return _("mem.cpumax").format(actual=current, rated=ceiling,
                                          modelo=memory_limit_label(limit))
        # Con el controlador en el chipset el límite es de la placa, no del
        # procesador.
        return _("mem.underclocked.chipset" if chipset else "mem.underclocked").format(
            actual=current, rated=ceiling)
    if highest > ceiling * (1 + ROUNDING_MARGIN):
        return _("mem.mixed").format(actual=current, lento=ceiling, rapido=highest)
    return None


def memory_channel_warning(modules) -> Optional[str]:
    """Cuándo la memoria está rindiendo por debajo de lo que podría.

    Es de los pocos problemas de hardware que son a la vez muy comunes, muy
    caros en rendimiento y completamente invisibles: nada en el sistema avisa
    de que los dos módulos están en el mismo canal, y en un equipo con gráfica
    integrada eso se lleva por delante la mitad de los fotogramas.
    """
    channels = memory_channels(modules)
    if channels is None or channels > 1:
        return None
    fitted = sum(1 for m in modules if m.populated)
    free_slots = sum(1 for m in modules if not m.populated)
    if fitted > 1:
        return _("mem.channel.same").format(n=fitted)
    if free_slots:
        return _("mem.channel.single")
    return None


NVME_WARNINGS = {
    0: "disk.warn.spare",
    1: "disk.warn.temp",
    2: "disk.warn.reliability",
    3: "disk.warn.readonly",
    4: "disk.warn.backup",
    5: "disk.warn.pmr",
}

# Por debajo de esto se avisa de que al SSD le queda poco. El fabricante
# garantiza el disco hasta el 0 %, así que un 10 % no es una avería: es el
# momento de ir pensando en la copia de seguridad, y decirlo antes es lo único
# que sirve de algo.
LOW_LIFE_PCT = 10


def disk_warnings(health) -> list[tuple[str, str]]:
    """Lo que un disco está diciendo de sí mismo, como `(nivel, frase)`.

    El registro de salud se leía entero y no se enseñaba ni una línea de él:
    `critical_warning` es el campo por el que un NVMe avisa de que va camino
    de perder datos, y estaba ahí sin que lo mirara nadie.

    Los apagones bruscos no son un aviso: cuentan los cortes de luz y los
    botones de reinicio, y en un equipo de sobremesa son normales.
    """
    warnings: list[tuple[str, str]] = []
    if health is None:
        return warnings

    if health.critical_warning:
        for bit, key in NVME_WARNINGS.items():
            if health.critical_warning & (1 << bit):
                warnings.append(("crítico", _(key).capitalize() + "."))
        if not warnings:                     # un bit que la especificación no cubre
            warnings.append(("crítico", _("disk.warn.unknown").format(
                codigo=f"{health.critical_warning:#04x}")))

    if health.media_errors:
        key = ("disk.warn.media.one" if health.media_errors == 1
                 else "disk.warn.media.many")
        warnings.append(("alto", _(key).format(n=thousands(health.media_errors))))

    life = health.life_left_percent
    if life is not None and life <= LOW_LIFE_PCT:
        warnings.append(("alto", _("disk.warn.life").format(pct=life)))
    return warnings


def duration(seconds: float) -> str:
    """«40 s», «2 min 10 s». Sin decimales: nadie mide un recorte en décimas."""
    if seconds < 60:
        return _("time.seconds").format(n=f"{seconds:.0f}")
    minutes, rest = divmod(int(seconds), 60)
    if rest:
        return _("time.minsec").format(m=minutes, s=rest)
    return _("time.minutes").format(m=minutes)


def home_path(text, home: Optional[str] = None) -> str:
    """Paths as they are shown: the home folder as «~», wherever it is in
    the text (an error message carries its path). People share
    screenshots, and the home folder has the user's name in it."""
    text = str(text)
    home = (home if home is not None else str(pathlib.Path.home())).rstrip("/")
    if not home:
        return text
    return re.sub(r"(?<![\w/.-])" + re.escape(home) + r"(?=$|[/\s'\"),:;])", "~", text)


def version(full: str, translate=_) -> str:
    """La versión como se enseña: «0.4» y no «0.4.0»; «0.4.1» en un arreglo;
    «0.4-prueba1» en la primera de prueba de la 0.4.

    Por debajo siempre es x.y.z (pyproject, la etiqueta y `--version`, que
    son para máquinas). A quien mira la ventana o lee el informe, el tercer
    número solo le dice algo cuando no es cero: es la versión de arreglos de
    esa. The report passes `en_español`: it is always in Spanish.
    """
    # Una versión de prueba va como la pide PEP 440 («0.4.0rc1») y se
    # enseña con su nombre: «0.4-prueba1».
    run = re.fullmatch(r"(\d+\.\d+\.\d+)rc(\d+)", full)
    if run:
        return f"{version(run.group(1))}-{translate('app.version.rc')}{run.group(2)}"
    parts = full.split(".")
    if len(parts) == 3 and parts[2] == "0":
        return ".".join(parts[:2])
    return full


# El orden de las barras de motores, del que más se mira al que menos.
ENGINE_ORDER = ("engine.render", "engine.compute", "engine.video",
                    "engine.decode", "engine.encode", "engine.videoenhance",
                    "engine.copy")


def engine_levels(gpu) -> list[tuple[str, Optional[float]]]:
    """Las barras de uso por motor de una gráfica: (clave, porcentaje).

    Solo los motores que esta gráfica deja medir, cada uno de donde lo da su
    driver (docs/motores-de-graficas.md):

    - Intel (i915, xe) enumera sus motores: una barra por tipo, con el más
      ocupado de cada tipo, porque dos decodificadores a medias no son un
      video al cien. Con None, el motor está y su uso lo guarda un permiso.
    - AMD no enumera motores: el uso de la gráfica y el de su motor de video
      (VCN), que codifica y decodifica con una sola cifra. Desde el VCN 4
      decodificar también va por la cola de codificar, así que no hay forma
      de separarlos: una barra, no dos con un dato repartido.
    - NVIDIA tiene NVENC y NVDEC aparte, y NVML los mide aparte: dos barras.

    Una gráfica dormida no tiene barras: no se ha leído nada de ella.
    """
    if getattr(gpu, "suspended", False):
        return []
    if gpu.engines:
        by_type: dict[str, list] = {}
        for engine in gpu.engines:
            if engine.kind:
                by_type.setdefault(engine.kind, []).append(engine.busy_percent)
        out = []
        for key in ENGINE_ORDER:
            if key in by_type:
                read_values = [v for v in by_type[key] if v is not None]
                out.append((key, max(read_values) if read_values else None))
        return out
    if gpu.vendor == "AMD":
        out = [("engine.render", gpu.busy_percent),
                  ("engine.video", gpu.video_busy_percent)]
    elif gpu.vendor == "NVIDIA":
        out = [("engine.render", gpu.busy_percent),
                  ("engine.decode", gpu.decode_busy_percent),
                  ("engine.encode", gpu.encode_busy_percent)]
    else:
        return []
    return [(k, v) for k, v in out if v is not None]


def engine_gaps(gpu) -> list[str]:
    """Los motores que toda gráfica tiene y esta no deja medir.

    Toda gráfica tiene un motor gráfico y uno de video; en NVIDIA, el de
    video son dos. Lo que su driver no publica no lleva barra y se nombra al
    pie, que es lo que evita que desaparezca en silencio. Lo que está y
    guarda un permiso no es esto: lleva candado (`engine_levels` con None).
    """
    if getattr(gpu, "suspended", False):
        return []
    if gpu.driver == "xe":
        # xe sí publica el uso de sus motores, con un PMU que silux todavía
        # no lee (docs/pendientes.md): decir que la
        # gráfica no lo da sería falso. Lo cuenta su aviso.
        return []
    expected = (("engine.render", "engine.decode", "engine.encode")
                 if gpu.vendor == "NVIDIA" else ("engine.render", "engine.video"))
    measured = {key for key, _level in engine_levels(gpu)}
    return [key for key in expected if key not in measured]


def gpu_asleep(gpu, fahrenheit: bool = False) -> str:
    """Qué se dice de una gráfica suspendida, o "" si está despierta.

    Sin cifras de ahora, que no se han leído, y con lo último que se supo y
    de cuándo, si se llegó a ver despierta: una temperatura sin su hora se
    leería como la de este momento.
    """
    if not getattr(gpu, "suspended", False):
        return ""
    text = _("gpu.asleep")
    if gpu.last_awake_s is not None:
        import time
        hour = time.strftime("%H:%M", time.localtime(gpu.last_awake_s))
        if gpu.last_temp_c is not None:
            text += " " + _("gpu.asleep.lasttemp").format(
                hora=hour, valor=temperature(gpu.last_temp_c, fahrenheit))
        else:
            text += " " + _("gpu.asleep.last").format(hora=hour)
    return text


def throttle_episode(episode, ahora_ns: int) -> Optional[str]:
    """Cuánto lleva —o llevó— frenándose, y por qué.

    «Recortando por temperatura del punto caliente» dice qué pasa ahora y no
    dice lo que se quiere saber. Una tarjeta que toca su límite de potencia
    medio segundo en cada cambio de escena funciona como se diseñó; una que
    lleva un minuto contra el límite térmico tiene un problema de
    refrigeración. El dato es el mismo y la conclusión es la contraria.
    """
    if episode is None:
        return None
    how_long = duration(episode.duration_s(ahora_ns))
    reasons = ", ".join(sorted(episode.reasons)) or _("throttle.unknown")
    key = "throttle.ongoing" if episode.ongoing() else "throttle.past"
    return _(key).format(tiempo=how_long, motivos=reasons)


def gpu_clock_limits(clocks) -> Optional[str]:
    """«350 MHz – 900 MHz», solo si alguien cambió los límites del motor.

    De fábrica el mínimo y el máximo puestos son los del silicio (RPn y
    RP0), y repetirlos sería decir lo mismo dos veces. Si no se saben los
    del silicio no hay con qué comparar.
    """
    fitted = (clocks.core_min_hz, clocks.core_max_hz)
    silicon = (clocks.silicon_min_hz, clocks.silicon_max_hz)
    if None in fitted or None in silicon or fitted == silicon:
        return None
    return f"{hz(fitted[0])} – {hz(fitted[1])}"


def gpu_sleep(gpu) -> str:
    """Cuánto ha dormido la gráfica, o que no la dejan dormir."""
    if gpu.sleep_enabled is False:
        return _("gpu.engines.rc6off")
    return percent(gpu.sleep_percent)


def throttle_state(gpu) -> str:
    """Si la tarjeta se está frenando, y por qué motivos."""
    if gpu.throttled is None:
        return DASH
    if not gpu.throttled:
        return _("gpu.throttle.none")
    if not gpu.throttle_reasons:
        return _("gpu.throttle.some")
    return _("gpu.throttle.why").format(motivos=", ".join(gpu.throttle_reasons))


def board_name(board) -> str:
    """The board's or the machine's name, or that the firmware gives none."""
    return board.display_name or _("board.unnamed")


def gpu_name(gpu) -> str:
    """The card's name, or which one it is when nothing names it."""
    return gpu.display_name or _("sensor.dev.gpu").format(n=gpu.index)


def monitor_name(monitor: Optional[Edid]) -> str:
    """El modelo tal y como lo enseñaría la pegatina de detrás."""
    if monitor is None:
        return DASH
    # La marca, no la razón social: «GIGA-BYTE TECHNOLOGY CO., LTD. AORUS
    # FO27Q2» se comía el ancho de la tabla de salidas.
    parts = [p for p in (maker(monitor.manufacturer), monitor.model) if p]
    return " ".join(parts) if parts else (monitor.manufacturer_id or DASH)


def monitor_diagonal(monitor: Optional[Edid]) -> Optional[str]:
    """«26.7"», o «≈ 27"» cuando el monitor solo da centímetros enteros.

    Con medio centímetro de error por lado la diagonal baila un cuarto de
    pulgada: un decimal ahí es una precisión que el dato no tiene.
    """
    if monitor is None or not monitor.diagonal_inches:
        return None
    if monitor.size_exact:
        return f'{monitor.diagonal_inches}"'
    return f'≈ {monitor.diagonal_inches:.0f}"'


def monitor_summary(monitor: Optional[Edid]) -> str:
    """«26.7" · 590 × 334 mm · semana 16 de 2024»."""
    if monitor is None:
        return DASH
    inches = monitor_diagonal(monitor)
    measurement = (f"{monitor.width_mm} × {monitor.height_mm} mm"
              if monitor.width_mm and monitor.height_mm else None)
    parts = [p for p in (inches, measurement, made(monitor.year, monitor.week)) if p]
    return " · ".join(parts) if parts else DASH


def display_mode(display: Display) -> str:
    """La resolución nativa con su refresco: «2560 × 1440 · 48–240 Hz»."""
    if not display.connected:
        return DASH
    range_ = display.monitor.refresh_range if display.monitor else None
    if not range_ and display.refresh_hz:
        range_ = f"{display.refresh_hz:g} Hz"
    parts = [p for p in (display.resolution, range_) if p]
    return " · ".join(parts) if parts else DASH


def display_summary(display: Display) -> str:
    """Una salida de vídeo: qué hay enchufado y a qué resolución.

    A propósito no dice si la pantalla está encendida. El kernel publica un
    `enabled` y un `dpms` que lo parecen, pero bajo Wayland el compositor toma
    el control del modeset y sysfs pasa a decir «disabled» y «Off» de pantallas
    que están funcionando delante de uno. Un dato que miente en el escritorio
    más común no se enseña.
    """
    if not display.connected:
        return _("display.unplugged")
    return display.resolution or _("display.connected")


def gpu_api_summary(api: GpuApi) -> str:
    """«1.4.354 · Mesa 26.2.1 · 64 unidades de cómputo»."""
    parts = [api.version or DASH]
    if api.driver:
        parts.append(api.driver)
    if api.extra:
        parts.append(api.extra)
    return " · ".join(parts)


# A field the anonymized photo would still change, by its top field and its
# last name, as the kind of data it is (`annex.what.*`).
_ANNEX_FIELDS = {
    ("gpus", "unique_id"): "gpu_id", ("gpus", "serial"): "monitor_serial",
    ("disks", "serial"): "disk_serial", ("disks", "mountpoint"): "mount",
    ("batteries", "serial"): "battery_serial", ("system", "hostname"): "machine_name",
    ("network", "name"): "interface", ("network", "mac"): "mac", ("network", "ipv4"): "ip",
    ("network", "ipv6"): "ipv6", ("network", "gateway"): "router",
    ("usb_devices", ""): "usb", ("sound_cards", ""): "sound", ("cameras", ""): "camera",
    ("bluetooth", ""): "bluetooth", ("sensors", ""): "text", ("notes", ""): "text",
}


ANNEX_WHAT = {
    "email": "annex.what.email",
    "serial": "annex.what.serial",
    "disk_serial": "annex.what.disk_serial",
    "monitor_serial": "annex.what.monitor_serial",
    "memory_serial": "annex.what.memory_serial",
    "battery_serial": "annex.what.battery_serial",
    "mac": "annex.what.mac",
    "usb": "annex.what.usb",
    "sound": "annex.what.sound",
    "camera": "annex.what.camera",
    "bluetooth": "annex.what.bluetooth",
    "router": "annex.what.router",
    "ip": "annex.what.ip",
    "ipv6": "annex.what.ipv6",
    "gpu_id": "annex.what.gpu_id",
    "interface": "annex.what.interface",
    "machine": "annex.what.machine",
    "machine_name": "annex.what.machine_name",
    "mount": "annex.what.mount",
    "text": "annex.what.text",
}


def annex_what(kind: str) -> str:
    """What kind of data held back the annex, in words («una dirección IP»)."""
    return _(ANNEX_WHAT.get(kind, ANNEX_WHAT["machine"]))


def annex_refusal(fields: list[str]) -> str:
    """Why the annex was not written: what was still to cover, never its value."""
    kinds = []
    for field in fields:
        top = re.split(r"[.\[]", field, maxsplit=1)[0]
        leaf = field.rsplit(".", 1)[-1] if "." in field else ""
        kind = _ANNEX_FIELDS.get((top, leaf)) or _ANNEX_FIELDS.get((top, ""), "machine")
        if kind not in kinds:
            kinds.append(kind)
    return _("report.annex.refused").format(
        que=", ".join(annex_what(c) for c in kinds), campos=", ".join(fields[:5]))


def annex_removed(removed: list[dict]) -> Optional[str]:
    """The files taken out of the annex and what each held, or None."""
    if not removed:
        return None
    items = "; ".join(_("report.annex.removed.item").format(
        que=annex_what(str(q.get("dato", ""))), ruta=q.get("ruta", "")) for q in removed[:10])
    return _("report.annex.removed").format(n=len(removed), lista=items)


def turbo(clocks: Clocks) -> str:
    """«activado», «desactivado», or «no tiene» for a part without one."""
    if clocks.turbo_supported is False:
        return _("cpu.turbo.none")
    if clocks.turbo_enabled is None:
        return DASH
    return _("board.on") if clocks.turbo_enabled else _("board.off")


def configured_base(clocks: Clocks) -> Optional[str]:
    """The base the configured TDP gives, when it isn't the specification's."""
    now = clocks.base_configured_hz
    if clocks.base_hz and now and abs(now - clocks.base_hz) >= 50_000_000:
        return hz(now)
    return None


def without_frequency_driver(clocks: Clocks) -> Optional[str]:
    """What a machine without cpufreq has not, and where its frequency
    comes from; None with a driver."""
    if clocks.current_from == "cpuinfo":
        return _("cpu.clocks.nodriver.cpuinfo")
    if clocks.current_from == "msr":
        return _("cpu.clocks.nodriver.msr")
    return None


def clocks_footnote(clocks: Clocks) -> Optional[str]:
    """What the Clocks card hides and why: no frequency driver, no turbo."""
    parts = [p for p in (without_frequency_driver(clocks),
                         _("cpu.clocks.noturbo") if clocks.turbo_supported is False else None) if p]
    return " ".join(parts) or None


def turbo_note(clocks: Clocks) -> Optional[str]:
    """Una frase corta cuando el techo real no llega al del silicio."""
    if clocks.turbo_enabled is False and clocks.max_turbo_hz:
        return _("clock.turbo.off").format(max=hz(clocks.max_turbo_hz))
    if clocks.turbo_headroom_hz:
        return _("clock.turbo.capped").format(
            actual=hz(clocks.max_hz), max=hz(clocks.max_turbo_hz))
    return None


def _cpu_range(cpus: tuple[int, ...]) -> str:
    """«0-7» en vez de «0, 1, 2, 3, 4, 5, 6, 7» cuando son consecutivas."""
    if not cpus:
        return ""
    if len(cpus) > 2 and list(cpus) == list(range(cpus[0], cpus[-1] + 1)):
        return f"{cpus[0]}-{cpus[-1]}"
    return ", ".join(str(c) for c in cpus)


def asymmetric_l3(cpu_type) -> Optional[str]:
    """Cuando la L3 no es igual en todo el procesador, qué le toca a cada cual.

    Es lo que pasa en un Ryzen de dos chiplets con V-Cache en uno solo: un
    7950X3D lleva 96 MB en la mitad de sus núcleos y 32 en la otra. La
    diferencia no es un detalle de ficha técnica —es la razón de ser de la
    pieza, y de qué chiplet coja el planificador depende que un juego rinda
    como el modelo caro o como el barato.

    Se describe lo que se lee y no se diagnostica: la asimetría es un hecho de
    sysfs. Que sea V-Cache lo confirma el nombre comercial, y solo si lo trae.
    """
    l3 = [c for c in cpu_type.caches if c.level == 3]
    if len({c.size_bytes for c in l3}) < 2:
        return None

    parts = []
    for cache in sorted(l3, key=lambda c: -c.size_bytes):
        cpus = cache.instance_cpus[0] if cache.instance_cpus else ()
        where = _cpu_range(cpus)
        parts.append(
            _("cache.l3.part").format(tam=size(cache.size_bytes), donde=where)
            if where else _("cache.l3.partsome").format(tam=size(cache.size_bytes)))
    sentence = _("cache.l3.uneven").format(reparto=_("core.join").join(parts))
    if "3D" in (cpu_type.brand or "").upper():
        sentence += _("cache.l3.vcache")
    return sentence


def vcache(cpu_type) -> Optional[str]:
    """«3D V-Cache» cuando la pieza lo lleva, según su propio nombre.

    El nombre comercial sale de CPUID y lo escribe el fabricante: un
    «Ryzen 7 5800X3D» lo dice él. No se deduce del tamaño de la L3, que
    también crece por otros motivos según la familia.
    """
    brand = (cpu_type.brand or "").upper()
    if "X3D" not in brand:
        return None
    large = max((c.size_bytes for c in cpu_type.caches if c.level == 3),
                 default=None)
    if large is None:
        return _("cache.vcache.plain")
    return _("cache.vcache.size").format(tam=size(large))


def core_quality_by_type(logical) -> dict[str, list[tuple[int, int, float]]]:
    """Por tipo de núcleo, los físicos ordenados de mejor a peor.

    Cada fila es `(core_id, nota cruda, fracción del mejor de su tipo)`. La
    fracción es lo único comparable entre máquinas: la nota cruda es la escala
    de rendimiento de CPPC de esta pieza y no significa lo mismo en otra.

    Se separa por tipo porque en un Intel híbrido comparar un P-core con un
    E-core no dice nada de la calidad del silicio. Un E-core con la mitad de
    nota no «salió peor de la oblea»: es otro núcleo, con otro propósito y
    otro tamaño, y la plataforma lo puntúa más bajo por diseño. Sin separarlos,
    un 12900K decía que su núcleo más flojo se quedaba en el 35 % del mejor,
    que es cierto en el número y falso en lo que da a entender.

    Y se agrupa por núcleo físico porque los dos hilos de un mismo núcleo
    comparten silicio y traen por fuerza la misma nota; enseñarla dos veces
    sugeriría que se midieron por separado.
    """
    by_type: dict[str, dict[int, int]] = {}
    for cpu in logical:
        if not cpu.quality:
            continue
        cores = by_type.setdefault(cpu.type_key, {})
        cores.setdefault(cpu.core_id, cpu.quality)

    result = {}
    for key, cores in by_type.items():
        # Un tipo cuyos núcleos traen todos la misma nota no se ha medido:
        # el firmware ha rellenado el campo con la constante de la familia.
        if len(set(cores.values())) < 2:
            continue
        best = max(cores.values())
        result[key] = sorted(
            ((core, note, note / best) for core, note in cores.items()),
            key=lambda row: (-row[1], row[0]),
        )
    return result


def core_quality(logical) -> list[tuple[int, int, float]]:
    """Como `core_quality_by_type`, aplanado, para una CPU de un solo tipo."""
    by_type = core_quality_by_type(logical)
    if len(by_type) != 1:
        return []
    return next(iter(by_type.values()))


def best_core_ids(logical, count: int = 2) -> set[int]:
    """Los núcleos físicos que llevan estrella: los mejores de cada tipo.

    De cada tipo por separado, porque el mejor P-core y el mejor E-core son dos
    respuestas a la misma pregunta hecha sobre piezas distintas.
    """
    head: set[int] = set()
    for order in core_quality_by_type(logical).values():
        best = order[0][1]
        # Los empatados con el mejor van todos: en muchas piezas hay dos, y
        # quedarse con uno por el orden del bucle sería inventar un desempate.
        equal = [core for core, note, _fraction in order if note == best]
        head.update(equal[:count])
    return head


def best_cores(logical, count: int = 2) -> str:
    """«Núcleo 1 y núcleo 3», los que el firmware marca como los mejores."""
    head = sorted(best_core_ids(logical, count))
    if not head:
        return DASH
    names = [_("core.name").format(n=core) for core in head]
    if len(names) == 1:
        return names[0].capitalize()
    return (", ".join(names[:-1]) + _("core.join") + names[-1]).capitalize()


def starred_cpus(logical) -> str:
    """Las CPU lógicas que llevan estrella, para que la cuenta cuadre.

    Con SMT cada núcleo bueno marca sus dos hilos, así que en un 5800X3D se
    ven cuatro estrellas y la frase decía «núcleo 1 y núcleo 3». Las dos cosas
    son ciertas y no lo parecen: quien mira cuenta cuatro y lee dos.
    """
    order = core_quality(logical)
    if not order:
        return ""
    best = order[0][1]
    head = {core for core, note, _fraction in order if note == best}
    indexes = sorted(c.index for c in logical if c.core_id in head)
    if len(indexes) <= len(head):        # sin SMT no hay nada que aclarar
        return ""
    names = [thread_name(i) for i in indexes]
    return ", ".join(names[:-1]) + _("core.join") + names[-1]


def core_quality_spread(logical) -> Optional[str]:
    """Cuánto va del mejor núcleo al peor dentro de su propio tipo.

    En un híbrido se dice del tipo con más recorrido, que es donde la
    diferencia importa; comparar entre tipos daría una cifra grande y sin
    significado. Ver `core_quality_by_type`.
    """
    by_type = core_quality_by_type(logical)
    if not by_type:
        return None
    order = min(by_type.values(), key=lambda rows: rows[-1][2])
    worst = order[-1]
    key = "core.spread.type" if len(by_type) > 1 else "core.spread"
    return _(key).format(n=worst[0], pct=f"{worst[2] * 100:.0f}")


# Coletillas que los fabricantes meten en la cadena de marca y que no
# distinguen a un procesador de otro.
_RELLENO_DE_MARCA = re.compile(
    r"\s*(?:\d+-Core\s+Processor|Processor|CPU(?!\s+version)|\(R\)|\(TM\)|™|®"
    r"|@\s*[\d.]+\s*[GM]Hz|with\s+Radeon\s+Graphics"
    r"|w/\s+Radeon[\w\s]*Graphics)",
    re.IGNORECASE)


def lost_packets(n: int) -> str:
    """«1 paquete descartado», «12 682 paquetes descartados»."""
    return _("net.lost.one") if n == 1 else _("net.lost").format(n=thousands(n))


def board_chipset(board) -> str:
    """«Intel 500 Series · in the processor's package» when it is there."""
    if not board.chipset:
        return DASH
    if board.chipset_on_package:
        return f"{board.chipset} · {_('board.chipset.onpackage')}"
    return board.chipset


def packet_problems(traffic) -> str:
    """«2 506 paquetes descartados», with the damaged ones apart: a discard
    is the kernel's choice, an error is a fault."""
    parts = [lost_packets(traffic.dropped)] if traffic.dropped else []
    if traffic.errors:
        parts.append(_("net.errors").format(n=thousands(traffic.errors)))
    return " · ".join(parts) or _("net.nolost")


def cpu_short_name(brand: Optional[str]) -> str:
    """El nombre del procesador sin la paja: «Ryzen 7 5800X3D».

    La cadena de marca viene con coletillas que no distinguen un modelo de
    otro —«8-Core Processor», «(R)», «@ 2.90GHz»— y que en un titular ocupan
    dos líneas para no decir nada: los núcleos y la frecuencia ya están al
    lado, con su propia etiqueta.
    """
    if not brand:
        return DASH
    clean = _RELLENO_DE_MARCA.sub("", brand)
    clean = re.sub(r"\s{2,}", " ", clean).strip(" -·")
    return clean or brand


def monitor_color(edid) -> str:
    """Lo que el monitor declara en sus extensiones: HDR y espacios de color.

    Sale de los bloques CTA-861, que es donde vive lo moderno. El bloque base
    del EDID es de 1994 y no tiene sitio para nada de esto: sin mirar las
    extensiones, un panel con HDR10 y BT.2020 se describe igual que uno de
    hace veinte años.
    """
    pieces = list(edid.hdr)
    # De los espacios de color solo el más ancho: enseñar los seis que declara
    # un monitor llena la celda sin decir mucho más que el mayor de ellos.
    for wide in ("BT.2020 RGB", "BT.2020 YCC", "opRGB", "xvYCC709"):
        if wide in edid.color_spaces:
            pieces.append(wide)
            break
    return " · ".join(pieces) if pieces else DASH
