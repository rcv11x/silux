"""Capa de presentación: convierte valores en texto.

Todo el formateo del programa vive aquí y solo aquí. El modelo guarda
hercios, bytes y grados; la interfaz y la CLI llaman a estas funciones. Es lo
que permite tener una salida JSON de verdad, cambiar de °C a °F sin tocar la
recolección, y traducir sin reescribir nada.
"""

from __future__ import annotations

import pathlib
import re
from typing import Optional

from .features import pretty as pretty_feature
from .i18n import _
from .spd import grado_jedec
from .model import (MARGEN_DE_REDONDEO, Cache, Clocks, CpuType, Display,
                    Edid, GpuApi, PcieLink, GpuMemory, NetworkInterface,
                    NetworkTraffic, Power, SensorKind, short_vendor,
                    thread_name)

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


def clock_and_multiplier(frecuencia: Optional[int],
                         factor: Optional[float]) -> str:
    """«3.40 GHz  × 34.0», o solo la parte que se sepa.

    Los dos van juntos en el mismo renglón, y unirlos a pelo dejaba a la vista
    el hueco del que falta: un Broadwell sin multiplicador publicado salía
    «1.60 GHz  —», y uno sin ninguno de los dos, «—  —». El guion marca un
    dato ausente, y ahí se leía como un fallo de formato.
    """
    piezas = [p for p in (hz(frecuencia), multiplier(factor)) if p != DASH]
    return "  ".join(piezas) or DASH


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


def cache_summary(cache: Cache) -> str:
    """«6 × 32 KB, 8 vías»: la forma en que se lee una jerarquía de caché."""
    parts = [size(cache.size_bytes)]
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
    parts = [f"{c.instances} × {size(c.size_bytes)}" if c.instances > 1 else size(c.size_bytes)
             for c in ordered]
    text = " + ".join(parts)
    ways = {c.ways for c in ordered}
    if len(ways) == 1 and None not in ways:
        text += ", " + _("cache.ways").format(n=ways.pop())
    return text


def cache_label(cache: Cache) -> str:
    claves = {"data": "cache.label.data", "instruction": "cache.label.instr"}
    return _(claves.get(cache.kind, "cache.label.unified")).format(n=cache.level)


def from_cpu_table(valor: Optional[str], traducir=None) -> str:
    """Un dato que sale de la tabla de procesadores y no del propio silicio.

    El nombre en clave, el nodo y el encapsulado no se leen del procesador:
    están en una tabla que es una foto del día en que se hizo, y uno que
    salga después no está. Se dice así y no con un guion, que se lee como
    «este equipo no lo tiene». `traducir`, como en `core_type_label`.
    """
    return valor or (traducir or _)("cpu.notintable")


def core_type_label(cpu_type: CpuType, hybrid: bool, traducir=None) -> str:
    """`traducir` deja pedir el castellano fijo desde fuera de la interfaz.

    El informe va en español pase lo que pase, así que ahí entra `en_español`
    en vez de `_`; con la función normal, el informe de alguien con la interfaz
    en inglés mezclaría los dos idiomas en la misma página.
    """
    tr = traducir or _
    if not hybrid:
        return tr("cpu.type.generic")
    # «P» y «E» son como los llama Intel; ARM llama a lo mismo big.LITTLE.
    # El reparto es el mismo, el nombre no, y quien mira su teléfono no
    # reconoce «núcleo E» por ninguna parte.
    if (cpu_type.architecture or "").lower().startswith(("aarch64", "arm")):
        claves = {"performance": "core.type.big", "efficiency": "core.type.little"}
    else:
        claves = {"performance": "core.type.p", "efficiency": "core.type.e"}
    if cpu_type.key in claves:
        return tr(claves[cpu_type.key])
    return tr("core.type.named").format(nombre=cpu_type.key)


def instructions(cpu_type: CpuType, limit: int | None = None) -> str:
    from .features import para_arquitectura

    destacadas, bonitos = para_arquitectura(cpu_type.architecture)
    present = set(cpu_type.features)
    shown = [bonitos.get(f, f.upper()) for f in destacadas if f in present]
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
_TONOS_DE_REPOSO = ("accent/0.6", "accent/0.4", "accent/0.25", "accent/0.15", "line")


_CORETEMP_PAQUETE = re.compile(r"^Package id (\d+)$")
_CORETEMP_NUCLEO = re.compile(r"^Core (\d+)$")


def sensor_label(sensor) -> str:
    """El nombre de un sensor en el árbol, en el idioma de la interfaz.

    Solo las etiquetas que `coretemp` publica en inglés: «Package id 0» es
    «Paquete» y «Core 3», «Núcleo 3». El modelo las guarda tal cual, que es
    lo que quieren el informe y el CSV; las de los demás chips son las que
    puso el fabricante y no se tocan.
    """
    if sensor.chip == "coretemp":
        if (encaje := _CORETEMP_PAQUETE.match(sensor.label)):
            numero = int(encaje.group(1))
            return _("sensor.package") if numero == 0 else f'{_("sensor.package")} {numero}'
        if (encaje := _CORETEMP_NUCLEO.match(sensor.label)):
            return _("sensor.core").format(n=int(encaje.group(1)))
    return sensor.label


def idle_name(nombre: str) -> str:
    """«C2», no «C2_ACPI».

    `intel_idle` pone «_ACPI» detrás de los estados que toma de la tabla del
    firmware cuando no tiene una propia para ese procesador (un Comet Lake-S,
    por ejemplo). Dice de dónde salió el estado, no qué estado es.
    """
    return nombre[:-len("_ACPI")] if nombre.endswith("_ACPI") else nombre


def idle_segments(estados) -> list[tuple[str, float, str]]:
    """Los tramos de la barra de reposo: lo activo y cada estado, sobre 100."""
    dormido = sum(e.percent for e in estados)
    tramos = [(_("cpu.idle.active"), max(0.0, round(100.0 - dormido, 1)), "accent")]
    con_tiempo = [e for e in estados if e.percent > 0]
    for i, estado in enumerate(con_tiempo):
        # El más hondo siempre con el tono del fondo.
        tono = _TONOS_DE_REPOSO[-1] if i == len(con_tiempo) - 1 and len(con_tiempo) > 1 \
            else _TONOS_DE_REPOSO[min(i, len(_TONOS_DE_REPOSO) - 2)]
        tramos.append((idle_name(estado.name), estado.percent, tono))
    return tramos


def idle_deepest(estados) -> Optional[str]:
    """«C2, el reposo más hondo: entre el 54 % y el 73 % según el hilo.»"""
    if not estados:
        return None
    hondo = estados[-1]
    return _("cpu.idle.deepest").format(nombre=idle_name(hondo.name), bajo=f"{hondo.low:.0f}",
                                        alto=f"{hondo.high:.0f}")


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


def plural(cantidad: int, singular: str, plural_: str) -> str:
    """La palabra que toca según la cantidad.

    Parece una tontería hasta que un equipo con un solo módulo de memoria lee
    «1 módulos leídos» y piensa que el programa está roto. Cuando alguien va a
    fiarse de las cifras, la concordancia es parte de fiarse.
    """
    return singular if cantidad == 1 else plural_


def unique_id(crudo: Optional[str]) -> Optional[str]:
    """El identificador único de una pieza, o nada si no identifica nada.

    Todo ceros es la forma que tiene un driver de decir que no lo tiene.
    """
    if not crudo or not crudo.strip().strip("0"):
        return None
    return crudo.strip()


_FECHA_DMI = re.compile(r"(\d{1,2})/(\d{1,2})/(\d{4})")


def bios_date(crudo: Optional[str]) -> Optional[str]:
    """La fecha de la BIOS sin ambigüedad: «2025-10-28».

    El firmware la escribe como mes/día/año, a la americana, y pintada tal
    cual «06/08/2023» se lee en España como el seis de agosto y es el ocho de
    junio. Año-mes-día no se confunde con nada. Lo que no tenga esa forma se
    deja como viene: es mejor que inventarle un orden.
    """
    if not crudo:
        return None
    partes = _FECHA_DMI.fullmatch(crudo.strip())
    if partes is None:
        return crudo.strip()
    mes, dia, anno = (int(p) for p in partes.groups())
    if not (1 <= mes <= 12 and 1 <= dia <= 31):
        return crudo.strip()
    return f"{anno:04d}-{mes:02d}-{dia:02d}"


def bios_summary(board) -> str:
    """«AMI 1.80 (2023-06-08)»: de quién es la BIOS, cuál y de cuándo."""
    junto = " ".join(p for p in (short_vendor(board.bios_vendor), board.bios_version) if p)
    fecha = bios_date(board.bios_date)
    return f"{junto} ({fecha})" if junto and fecha else junto or DASH


def lock_tooltip(nota) -> str:
    """Lo que dice el candado de un dato que falta por permisos.

    Por qué falta, con las palabras de la nota, y qué pasa al pulsarlo.
    """
    return f"{nota.message}\n\n{_('lock.tip.outdated' if nota.helper_outdated else 'lock.tip')}"


def permission_action(nota) -> str:
    """The button of a note that needs permissions: give them, or update the
    installed helper when it is from another version."""
    return _("perm.replace.button") if nota.helper_outdated else _("perm.button.read")


def permission_title(nota, titulo: str) -> str:
    """A notice's title: the page's own, or that the helper is out of date."""
    return _("perm.outdated.title") if nota.helper_outdated else titulo


# Cómo llama el kernel al dúplex de un enlace, y con qué clave se dice aquí.
# Lo que no esté en la tabla —«unknown», que es lo que da una interfaz sin
# cable— no se pinta: no es un dúplex, es que no hay negociación.
DUPLEX = {"full": "net.duplex.full", "half": "net.duplex.half"}


def link_summary(interfaz) -> Optional[str]:
    """«2.5 Gb/s · dúplex completo»: cómo quedó negociado el enlace.

    Estaba en el modelo, que lo componía con la palabra del kernel tal cual:
    la página de Red decía «2.5 Gb/s · full» con la interfaz en español.
    """
    if not interfaz.speed_mbps:
        return None
    if interfaz.speed_mbps >= 1000:
        velocidad = f"{interfaz.speed_mbps / 1000:g} Gb/s"
    else:
        velocidad = f"{interfaz.speed_mbps} Mb/s"
    clave = DUPLEX.get((interfaz.duplex or "").lower())
    return f"{velocidad} · {_(clave)}" if clave else velocidad


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
    escala = ((1e9, "Gb/s" if bits else "GB/s"),
              (1e6, "Mb/s" if bits else "MB/s"),
              (1e3, "kb/s" if bits else "kB/s"))
    for factor, unidad in escala:
        if value >= factor:
            return f"{value / factor:.1f} {unidad}"
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
        con_cable = interface.kind in ("ethernet", "wifi")
        if con_cable and interface.carrier is False:
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
    parado = (rpm_value == 0) or (percent_value == 0)
    if _none(rpm_value) and _none(percent_value):
        return DASH
    if parado:
        return "parado"
    partes = []
    if not _none(rpm_value):
        partes.append(f"{int(rpm_value)} RPM")
    if not _none(percent_value):
        partes.append(f"({percent(percent_value)})" if partes else percent(percent_value))
    return "   ".join(partes)


# Lo que una razón social lleva detrás del nombre, y que nadie dice.
_FORMA_JURIDICA = re.compile(
    r"[,\s]+(?:Co\.?,?\s*Ltd\.?|Inc\.?|Corp(?:oration)?\.?|Ltd\.?|Limited|LLC|GmbH"
    r"|S\.?A\.?|AG|B\.?V\.?)$", re.IGNORECASE)
_MARCA_ENTRE_CORCHETES = re.compile(r"\[([^\]]+)\]\s*$")


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
    conocido = short_vendor(name)
    if conocido != name:
        return conocido
    if (corchetes := _MARCA_ENTRE_CORCHETES.search(name)):
        return corchetes.group(1).split("/")[0]
    if " / " in name:
        return name.rsplit(" / ", 1)[1].strip()
    limpio = name.strip()
    while (corto := _FORMA_JURIDICA.sub("", limpio)) != limpio and corto:
        limpio = corto
    return limpio


def with_maker(vendor: Optional[str], model: Optional[str]) -> Optional[str]:
    """El nombre de un producto empezando por su marca.

    `pci.ids` da el modelo sin el fabricante: «RTL8111/8168/8211/8411 PCI
    Express Gigabit Ethernet Controller» no dice que es una Realtek, y es
    lo primero que se busca. Si el modelo ya empieza por la marca, no se
    repite.
    """
    if not model:
        return None
    marca = maker(vendor)
    if not marca or model.lower().startswith(marca.lower()):
        return model
    return f"{marca} {model}"


def network_kind(clase: Optional[str]) -> str:
    """El tipo de una interfaz, dicho en el idioma de la interfaz: «Ethernet»,
    «Wi-Fi», «Puente». El proveedor guarda la clave y no el texto."""
    if not clase:
        return DASH
    texto = _(f"net.kind.{clase}")
    return clase if texto == f"net.kind.{clase}" else texto


def network_name(interfaz) -> str:
    """Cómo se llama una tarjeta de red: su modelo con la marca, o el nombre
    de la interfaz si no se sabe el modelo."""
    return with_maker(interfaz.vendor, interfaz.model) or interfaz.name


# El kernel le pega al nombre de algunos chips dónde los encontró: la
# dirección del Super I/O («it8688_40050607») o el bus MDIO de la tarjeta de
# red («r8169_0_600:00»). Sirve para distinguir dos iguales, no para leerlo.
_DIRECCION_DEL_CHIP = re.compile(r"(?:_[0-9a-f]{6,}|_\d+_[0-9a-f]+:\d+)$")


def chip_name(chip: str) -> str:
    """El nombre de un chip de sensores sin la dirección que le pega el kernel."""
    return _DIRECCION_DEL_CHIP.sub("", chip)


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
    nombre = f"PCIe {generation}.0" if generation else f"{speed:g} GT/s"
    return f"{nombre} × {width}" if width else nombre


def pcie_note(link: PcieLink) -> Optional[str]:
    """Por qué el enlace va más lento de lo que puede, cuando pasa.

    Casi siempre es que la tarjeta está en reposo y el driver ha bajado el
    enlace para gastar menos, así que se dice como apunte y no como aviso: en
    una máquina parada es lo que tiene que ocurrir.
    """
    if not link.downgraded:
        return None
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
    techo = float(top) * 1.1
    pruebas = {0.0, float(top), techo}
    for base in (2, 10):
        potencia = 1.0
        while potencia <= techo:
            for margen in (1e-4, 1e-6):
                pruebas.add(potencia * (1 - margen))
            potencia *= base
    textos = []
    for valor in sorted(pruebas):
        texto = formatter(valor)
        if texto not in textos:
            textos.append(texto)
    return textos


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
UNIDADES_DE_PROCESO = {
    "NVIDIA": "gpu.units.cuda",
    "AMD": "gpu.units.cu",
    "Intel": "gpu.units.eu",
}


def compute_units(gpu) -> str:
    """«64 unidades de cómputo», «2048 núcleos CUDA»."""
    if not gpu.compute_units:
        return DASH
    clave = UNIDADES_DE_PROCESO.get(gpu.vendor or "", "gpu.units.generic")
    return f"{gpu.compute_units} {_(clave)}"


def compute_units_short(gpu) -> Optional[str]:
    """Lo mismo pero para una insignia: «64 CU», «2048 CUDA»."""
    if not gpu.compute_units:
        return None
    corto = {"NVIDIA": "CUDA", "AMD": "CU", "Intel": "EU"}.get(gpu.vendor or "", "u.")
    return f"{gpu.compute_units} {corto}"


def resizable_bar(memory: GpuMemory) -> str:
    """Si la CPU alcanza toda la VRAM o solo una ventana de 256 MB."""
    if memory.resizable_bar is None:
        return DASH
    if memory.resizable_bar:
        return _("gpu.rebar.on")
    ventana = size(memory.visible_bytes) if memory.visible_bytes else DASH
    return _("gpu.rebar.off").format(ventana=ventana)


# Los bits de `critical_warning` del registro de salud de NVMe, que es donde
# un disco dice que tiene un problema. Están definidos por la especificación y
# significan lo mismo en todas las marcas.
# De dónde sacar en qué canal está un módulo. El firmware lo escribe de varias
# maneras según quién haga la placa, y ninguna es obligatoria: «P0 CHANNEL A»
# en el banco, «DIMM_A1» en el localizador, «ChannelA-DIMM0» en los portátiles.
_CANAL = (
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
_CONTROLADOR = re.compile(r"CONTROLLER[\s_-]*(\d+)", re.I)

# Cómo se llama tener tantos canales poblados. Por encima de cuatro se dice el
# número, que «óctuple canal» no lo usa nadie.
NOMBRE_DE_CANALES = {1: "mem.chan.1", 2: "mem.chan.2",
                     3: "mem.chan.3", 4: "mem.chan.4"}


def _canal_de(modulo) -> Optional[str]:
    """Qué canal ocupa un módulo, si el firmware lo dice.

    No devuelve la letra sino algo que identifique el canal de verdad: cuando
    el localizador nombra el controlador, la letra por sí sola se repite entre
    ellos y dos módulos bien repartidos parecían estar en el mismo sitio.
    """
    for texto in (modulo.bank, modulo.locator):
        if not texto:
            continue
        for patron in _CANAL:
            if (encaje := patron.search(texto)):
                letra = encaje.group(1).upper()
                controlador = _CONTROLADOR.search(texto)
                return f"{controlador.group(1)}:{letra}" if controlador else letra
    return None


def memory_channels(modulos) -> Optional[int]:
    """Cuántos canales tienen al menos un módulo puesto.

    Devuelve None cuando el firmware no dice en qué canal está cada zócalo, que
    pasa en placas que numeran los bancos en vez de nombrarlos. Inventarse el
    dato ahí sería peor que no darlo: en canal único la memoria rinde la mitad,
    y decirlo al revés manda a alguien a abrir el equipo para nada.
    """
    poblados = [m for m in modulos if m.populated]
    if not poblados:
        return None
    canales = {c for m in poblados if (c := _canal_de(m))}
    return len(canales) or None


def memory_channel_label(modulos) -> Optional[str]:
    """«Doble canal», «canal único»… con cuántos módulos lo forman."""
    cuantos = memory_channels(modulos)
    if cuantos is None:
        return None
    nombre = (_(NOMBRE_DE_CANALES[cuantos]) if cuantos in NOMBRE_DE_CANALES
              else _("mem.chan.n").format(n=cuantos))
    puestos = sum(1 for m in modulos if m.populated)
    modulos_txt = _("mem.modules.one" if puestos == 1
                    else "mem.modules.many").format(n=puestos)
    return f"{nombre} · {modulos_txt}"


def nanoseconds(value: Optional[float]) -> str:
    """«0.9 ns». Un decimal: la L1 de cualquier procesador anda por ahí y con
    cero decimales todas las cachés rápidas saldrían iguales."""
    return DASH if _none(value) else f"{float(value):.1f} ns"


def memory_theoretical_bandwidth(modulos) -> Optional[int]:
    """Lo que daría esta memoria si nada la frenara, en bytes por segundo.

    Es una multiplicación, no una medida: las transferencias por segundo por
    los ocho bytes que mueve cada una, por los canales que estén poblados. Vale
    para poner al lado de lo medido y ver cuánto se aprovecha; sola no dice
    gran cosa, porque ninguna máquina llega a su teórico.

    Sin saber los canales no se calcula. Suponer dos es justo el error que ya
    costó un aviso equivocado en la ficha de al lado: en canal único la memoria
    rinde la mitad, y aquí saldría un porcentaje que dobla al de verdad.
    """
    canales = memory_channels(modulos)
    if not canales:
        return None
    velocidades = [m.configured_mts or m.speed_mts for m in modulos
                   if m.populated and (m.configured_mts or m.speed_mts)]
    if not velocidades:
        return None
    # La más lenta: el controlador iguala a la baja lo que le pongan.
    return min(velocidades) * 1_000_000 * 8 * canales


def memory_bandwidth_share(medido: Optional[int], teorico: Optional[int]) -> Optional[float]:
    """Qué fracción del teórico se está consiguiendo, en tanto por ciento."""
    if not medido or not teorico:
        return None
    return round(medido / teorico * 100, 1)


# Los trozos que los firmwares pegan en el localizador de un zócalo. Salen así,
# sin espacios y cada fabricante a su manera: «Controller0-ChannelA»,
# «ChannelA-DIMM0», «DIMM_A1», «DIMM A», «DIMM 0».
_ZOC_CONTROLADOR = re.compile(r"controller\s*[-_]?\s*(\d+)", re.I)
_ZOC_CANAL = re.compile(r"chan(?:nel)?\s*[-_]?\s*([a-z])\b", re.I)
# «DIMM_A1» lleva canal y número pegados; «DIMM 0» solo número; «DIMM A» solo
# canal. El orden importa: el primero que casa gana.
_ZOC_DIMM_CANAL_Y_NUM = re.compile(r"dimm\s*[-_]?\s*([a-z])\s*(\d+)", re.I)
_ZOC_DIMM_NUM = re.compile(r"dimm\s*[-_]?\s*(\d+)", re.I)
_ZOC_DIMM_CANAL = re.compile(r"dimm\s*[-_]?\s*([a-z])\b", re.I)


def _piezas_del_zocalo(locator: str) -> dict:
    """Qué dice el localizador de un zócalo, campo a campo.

    Vacío si no se reconoce nada, y entonces quien llama deja el texto crudo:
    inventarse una posición a partir de algo que no se entiende es peor que
    enseñar lo que puso el firmware.
    """
    piezas: dict = {}
    if (casa := _ZOC_CONTROLADOR.search(locator)):
        piezas["controlador"] = casa.group(1)
    if (casa := _ZOC_CANAL.search(locator)):
        piezas["canal"] = casa.group(1).upper()

    if (casa := _ZOC_DIMM_CANAL_Y_NUM.search(locator)):
        piezas.setdefault("canal", casa.group(1).upper())
        piezas["dimm"] = casa.group(2)
    elif (casa := _ZOC_DIMM_NUM.search(locator)):
        piezas["dimm"] = casa.group(1)
    elif (casa := _ZOC_DIMM_CANAL.search(locator)):
        piezas.setdefault("canal", casa.group(1).upper())
    return piezas


# Cómo se llama cada velocidad de USB. Es la negociada, no la versión del
# dispositivo: un teclado USB 2.0 va a 12 Mb/s y está bien.
_USB_VELOCIDADES = {1.5: "usb.speed.low", 12.0: "usb.speed.full", 480.0: "usb.speed.high",
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
    cifra = f"{mbps / 1000:g} Gb/s" if mbps >= 1000 else f"{mbps:g} Mb/s"
    clave = _USB_VELOCIDADES.get(float(mbps))
    return f"{_(clave)} · {cifra}" if clave else cifra


def usb_kind(dispositivo) -> str:
    return _(USB_KINDS.get(dispositivo.kind, "usb.kind.other"))


def usb_name(dispositivo) -> str:
    """El nombre del dispositivo; si no lo trae (o la foto es anónima), lo que es."""
    nombre = usb_kind(dispositivo)
    return dispositivo.product or (nombre[:1].upper() + nombre[1:])


def sound_card(tarjeta) -> str:
    """«HDMI de la gráfica», «Placa base · Realtek ALCS1200A», o el nombre
    del aparato USB. No los de ALSA («HDA ATI HDMI», «HD-Audio Generic»)."""
    if tarjeta.kind == "hdmi":
        return _("sound.hdmi")
    if tarjeta.kind == "board":
        return _("sound.board").format(codec=tarjeta.codec) if tarjeta.codec else _("sound.board.plain")
    if tarjeta.kind == "usb":
        return tarjeta.name or _("sound.usb.camera" if tarjeta.camera else "sound.usb")
    return tarjeta.name or _("sound.other")


def trim(disco) -> Optional[str]:
    """Lo que se ve del TRIM de una unidad, sin afirmar más de lo que se ve.

    «Lo admite» es un hecho. Que se esté haciendo es una señal: la partición
    montada con `discard`, o el temporizador `fstrim.timer` activado, que
    puede no cubrir esa partición. Un disco de platos que admite descartes es
    un SMR, y se dice así; uno virtual no es de platos aunque lo diga. El que
    no los admite no enseña la fila.
    """
    if not disco.discard:
        return None
    partes = [_("disk.trim.smr") if disco.kind == "HDD" else _("disk.trim.yes")]
    if disco.discard_mounted:
        partes.append(_("disk.trim.mounted"))
    if disco.fstrim_timer:
        partes.append(_("disk.trim.timer"))
    if len(partes) == 1 and disco.kind != "HDD":
        partes.append(_("disk.trim.unseen"))
    return " · ".join(partes)


# Los atributos SMART de un disco SATA que significan lo mismo en casi todos.
# Los demás se enseñan con su número: su nombre depende del fabricante.
SMART_COMUNES = {
    1: "smart.attr.1", 5: "smart.attr.5", 9: "smart.attr.9", 12: "smart.attr.12",
    187: "smart.attr.187", 188: "smart.attr.188", 194: "smart.attr.194",
    197: "smart.attr.197", 198: "smart.attr.198", 199: "smart.attr.199",
    241: "smart.attr.241", 242: "smart.attr.242",
}


def smart_rows(salud) -> list[tuple[str, str]]:
    """El diagnóstico entero de un disco, en filas de nombre y valor.

    Primero lo que tiene nombre fijo (lo de NVMe viene así de la norma) y
    después, en un SATA, la tabla de atributos tal cual: número, nombre si es
    de los comunes, valor normalizado y contador en crudo.
    """
    filas: list[tuple[str, str]] = []
    for clave, valor in (
            ("smart.cycles", salud.power_cycles), ("smart.unsafe", salud.unsafe_shutdowns),
            ("smart.mediaerrors", salud.media_errors),
            ("smart.spare", f"{salud.spare_percent} %" if salud.spare_percent is not None else None),
            ("smart.read", size(salud.read_bytes) if salud.read_bytes else None),
            ("smart.warning", None if salud.critical_warning is None
             else _("smart.warning.none") if salud.critical_warning == 0
             else f"0x{salud.critical_warning:02x}")):
        if valor is not None:
            filas.append((_(clave), thousands(valor) if isinstance(valor, int) else str(valor)))
    for numero, normalizado, crudo in salud.attributes:
        nombre = _(SMART_COMUNES[numero]) if numero in SMART_COMUNES else _("smart.attr.other")
        filas.append((f"{numero} · {nombre}", _("smart.attr.value").format(
            normalizado=normalizado, crudo=thousands(crudo))))
    return filas


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
    clave = "plat.virt.active" if platform.virtualization == "active" else "plat.virt.present"
    return _(clave).format(tipo=platform.virtualization_kind or "")


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
ESPACIO_DE_MILES = "\u202f"


def thousands(valor: Optional[int]) -> str:
    """«4 136»: un entero con los miles separados, igual en cualquier locale."""
    if _none(valor):
        return DASH
    return f"{int(valor):,}".replace(",", ESPACIO_DE_MILES)


def seconds(valor: Optional[float]) -> str:
    """«13.3 s»."""
    return DASH if _none(valor) else f"{float(valor):.1f} s"


def time_window(valor: Optional[float]) -> str:
    """A RAPL time window, which goes from milliseconds to tens of seconds:
    «28.0 s», «2.4 ms»."""
    if _none(valor):
        return DASH
    if valor >= 1:
        return seconds(valor)
    if valor >= 1e-3:
        return f"{valor * 1e3:.1f} ms"
    return f"{valor * 1e6:.0f} µs"


def thermal_throttle(frenos) -> str:
    """«ninguno desde el arranque», or «5 en los núcleos (0.6 s) · 2 del
    procesador entero (1.4 s)»."""
    if frenos is None:
        return DASH
    partes = []
    if frenos.core_count:
        partes.append(_("cpu.throttle.cores").format(
            n=frenos.core_count, tiempo=seconds(frenos.core_ms / 1000)))
    if frenos.package_count:
        partes.append(_("cpu.throttle.package").format(
            n=frenos.package_count, tiempo=seconds(frenos.package_ms / 1000)))
    return " · ".join(partes) or _("cpu.throttle.none")


def power_limit(limite_w: Optional[float], ventana_s: Optional[float]) -> str:
    """«65.0 W · ventana de 28.0 s», or the watts alone without a window."""
    if _none(ventana_s):
        return watts(limite_w)
    return _("cpu.limit.window").format(limite=watts(limite_w), ventana=time_window(ventana_s))


# Qué es un dispositivo PCI por su clase, para nombrar lo que `pci.ids` no
# tiene. Las de `providers/pci.CLASES`: lo que la tabla de Placa enseña.
CLASES_PCI = {
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
    marca = maker(device.vendor)
    ids = (f"{device.vendor_id:04x}:{device.device_id:04x}"
           if device.vendor_id is not None and device.device_id is not None else None)
    clase = CLASES_PCI.get(device.pci_class or "")
    if marca and clase:
        texto = _("board.pci.unnamed").format(marca=marca, clase=_(clase))
    else:
        texto = marca or (_(clase) if clase else None)
    if ids:
        texto = f"{texto} ({ids})" if texto else ids
    return texto


# Las fases del arranque, en orden, con el campo de `Boot` de cada una.
FASES_DE_ARRANQUE = (("sys.boot.phase.firmware", "firmware_s"),
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
    if gpu.power_cap_min_w is not None and gpu.power_cap_max_w is not None:
        parts.append(_("gpu.power.range").format(desde=figure(gpu.power_cap_min_w, 1),
                                                  hasta=watts(gpu.power_cap_max_w)))
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
    return [(clave, seconds(getattr(boot, campo))) for clave, campo in FASES_DE_ARRANQUE
            if getattr(boot, campo) is not None]


def swap_summary(swap) -> str:
    """«45.0 MB de 31.3 GB · zstd · comprime 2.1 a 1 · prioridad 100»."""
    partes = [_("sys.swap.used").format(usado=size(swap.used_bytes), total=size(swap.size_bytes))]
    if swap.zram:
        if swap.algorithm:
            partes.append(swap.algorithm)
        if swap.ratio:
            partes.append(_("sys.swap.ratio").format(n=f"{swap.ratio:.1f}"))
    if swap.priority is not None:
        partes.append(_("sys.swap.priority").format(n=swap.priority))
    return " · ".join(partes)


def swap_name(swap) -> str:
    """«zram0 (en memoria)», «/swapfile (archivo)», «/dev/sda2 (partición)»."""
    if swap.zram:
        return _("sys.swap.zram").format(nombre=swap.device.rsplit("/", 1)[-1])
    return _("sys.swap.file" if swap.kind == "file" else "sys.swap.partition").format(
        nombre=swap.device)


# Los drivers del kernel cuya parte de usuario es Mesa.
_CON_MESA = ("amdgpu", "radeon", "i915", "xe", "nouveau")


def graphics_stack(snapshot) -> Optional[str]:
    """«Mesa 26.2.6», o «NVIDIA 570.86» con el driver propietario.

    No se lee nada nuevo: con un driver libre, la versión que declara OpenGL
    es la de Mesa («26.2.6-arch3.1», y aquí sin la coletilla del paquete).
    """
    for gpu in snapshot.gpus:
        if gpu.driver in _CON_MESA:
            for api in gpu.apis:
                if api.name == "OpenGL" and api.driver:
                    return f"Mesa {api.driver.split('-')[0]}"
        elif gpu.driver == "nvidia" and gpu.driver_version:
            return f"NVIDIA {gpu.driver_version}"
    return None


def enumeration(piezas, ultima: str = "list.and") -> str:
    """«el fabricante, los chips y la fecha»: una lista como se dice.

    Para las notas que nombran lo que falta. Una lista de nombres de campo
    separados por comas («Sin Chips, Perfiles rápidos, Fabricado») se lee
    como un formulario; una frase no. `ultima` es la clave de la conjunción:
    «y» por omisión, «ni» para lo que se niega.
    """
    piezas = [p for p in piezas if p]
    if len(piezas) <= 1:
        return "".join(piezas)
    return f"{', '.join(piezas[:-1])} {_(ultima)} {piezas[-1]}"


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
    crudos = [(localizador or "").strip() for localizador, _banco in zocalos]
    piezas = []
    for localizador, banco in zocalos:
        suyas = _piezas_del_zocalo(localizador or "")
        # El banco completa lo que el localizador calla, y nunca lo corrige.
        for campo, valor in _piezas_del_zocalo(banco or "").items():
            if campo != "dimm":
                suyas.setdefault(campo, valor)
        piezas.append(suyas)

    def etiqueta(suyas: dict, campos: tuple) -> str:
        partes = []
        if "controlador" in campos and "controlador" in suyas:
            partes.append(_("memory.slot.controller").format(n=suyas["controlador"]))
        if "canal" in suyas:
            partes.append(_("memory.slot.channel").format(c=suyas["canal"]))
        if "dimm" in campos and "dimm" in suyas:
            partes.append(_("memory.slot.dimm").format(n=suyas["dimm"]))
        return " · ".join(partes)

    if piezas and all(piezas):
        # De menos a más: se añade un campo solo si sin él dos zócalos se
        # llamarían igual, y antes uno que dos.
        for campos in ((), ("dimm",), ("controlador",), ("dimm", "controlador")):
            nombres = [etiqueta(suyas, campos) for suyas in piezas]
            if all(nombres) and len(set(nombres)) == len(nombres):
                return nombres

    # No se entiende, o ni con todo se distinguen: lo del firmware, y lo
    # mínimo para que no haya dos iguales.
    nombres = [crudo or _("memory.slot") for crudo in crudos]
    if len(set(nombres)) < len(nombres):
        repetidos = {n for n in nombres if nombres.count(n) > 1}
        nombres = [f"{nombre} · {banco_de_memoria(banco)}"
                   if nombre in repetidos and banco and banco.strip() else nombre
                   for nombre, (_localizador, banco) in zip(nombres, zocalos)]
    if len(set(nombres)) < len(nombres):
        repetidos = {n for n in nombres if nombres.count(n) > 1}
        vistos: dict[str, int] = {}
        salida = []
        for nombre in nombres:
            if nombre in repetidos:
                vistos[nombre] = vistos.get(nombre, 0) + 1
                nombre = f"{nombre} ({vistos[nombre]})"
            salida.append(nombre)
        nombres = salida
    return nombres


_BANCO_REDUNDANTE = re.compile(r"^bank[\s_-]*", re.I)


def banco_de_memoria(bank: Optional[str]) -> Optional[str]:
    """El banco sin repetir la palabra que ya lleva la fila.

    El firmware escribe «BANK 0» y la fila se titula «Banco», así que se leía
    «Banco: BANK 0». Solo se quita cuando el valor empieza por ahí y queda algo
    detrás: los localizadores de banco que traen más cosas —«Node0_Bank0»— se
    dejan enteros, porque ahí el resto sí distingue.
    """
    if not bank:
        return bank
    limpio = _BANCO_REDUNDANTE.sub("", bank.strip()).strip()
    return limpio or bank


def velocidad_de_memoria(mts: Optional[int]) -> Optional[int]:
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
    return grado_jedec(mts) or mts


def memory_module_verdict(modulo, limite=None) -> Optional[str]:
    """Si un módulo va más lento de lo que admite, y por qué.

    None si va a lo suyo; «cpu_max» si va al máximo oficial del procesador
    (`limite`, de `db.memory_limit`), que no es un fallo ni un perfil sin
    activar; «slow» si va por debajo sin que eso lo explique.
    """
    if not modulo.underclocked:
        return None
    actual = velocidad_de_memoria(modulo.configured_mts or modulo.speed_mts)
    if limite and actual and actual >= limite.mts * (1 - MARGEN_DE_REDONDEO):
        return "cpu_max"
    return "slow"


def memory_limit_label(limite) -> str:
    """«i5-10400», o «Ryzen 7 5800X3D con 2 módulos de 1 rango».

    En AMD la cifra vale para esa disposición de módulos y no para otra: con
    cuatro de dos rangos el mismo procesador garantiza menos. Se dice.
    """
    if not limite.layout:
        return limite.model
    cuantos, rangos = limite.layout.rstrip("R").split("x")
    return _("mem.layout.one" if rangos == "1" else "mem.layout.many").format(
        modelo=limite.model, n=cuantos, r=rangos)


def memory_speed_warning(modulos, limite=None, chipset: bool = False) -> Optional[str]:
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
    puestos = [m for m in modulos if m.populated and m.rated_mts]
    if not puestos:
        return None
    actual = velocidad_de_memoria(
        max((m.configured_mts or m.speed_mts or 0) for m in puestos))
    if not actual:
        return None

    techo = min(m.rated_mts for m in puestos)
    mayor = max(m.rated_mts for m in puestos)

    if actual < techo * (1 - MARGEN_DE_REDONDEO):
        # Al máximo del procesador no hay perfil que activar: es lo que su
        # fabricante garantiza, y los módulos rápidos no lo cambian.
        if limite and actual >= limite.mts * (1 - MARGEN_DE_REDONDEO):
            return _("mem.cpumax").format(actual=actual, rated=techo,
                                          modelo=memory_limit_label(limite))
        # Con el controlador en el chipset el límite es de la placa, no del
        # procesador.
        return _("mem.underclocked.chipset" if chipset else "mem.underclocked").format(
            actual=actual, rated=techo)
    if mayor > techo * (1 + MARGEN_DE_REDONDEO):
        return _("mem.mixed").format(actual=actual, lento=techo, rapido=mayor)
    return None


def memory_channel_warning(modulos) -> Optional[str]:
    """Cuándo la memoria está rindiendo por debajo de lo que podría.

    Es de los pocos problemas de hardware que son a la vez muy comunes, muy
    caros en rendimiento y completamente invisibles: nada en el sistema avisa
    de que los dos módulos están en el mismo canal, y en un equipo con gráfica
    integrada eso se lleva por delante la mitad de los fotogramas.
    """
    canales = memory_channels(modulos)
    if canales is None or canales > 1:
        return None
    puestos = sum(1 for m in modulos if m.populated)
    libres = sum(1 for m in modulos if not m.populated)
    if puestos > 1:
        return _("mem.channel.same").format(n=puestos)
    if libres:
        return _("mem.channel.single")
    return None


AVISOS_NVME = {
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
VIDA_BAJA_PCT = 10


def disk_warnings(salud) -> list[tuple[str, str]]:
    """Lo que un disco está diciendo de sí mismo, como `(nivel, frase)`.

    El registro de salud se leía entero y no se enseñaba ni una línea de él:
    `critical_warning` es el campo por el que un NVMe avisa de que va camino
    de perder datos, y estaba ahí sin que lo mirara nadie.

    Los apagones bruscos no son un aviso: cuentan los cortes de luz y los
    botones de reinicio, y en un equipo de sobremesa son normales.
    """
    avisos: list[tuple[str, str]] = []
    if salud is None:
        return avisos

    if salud.critical_warning:
        for bit, clave in AVISOS_NVME.items():
            if salud.critical_warning & (1 << bit):
                avisos.append(("crítico", _(clave).capitalize() + "."))
        if not avisos:                     # un bit que la especificación no cubre
            avisos.append(("crítico", _("disk.warn.unknown").format(
                codigo=f"{salud.critical_warning:#04x}")))

    if salud.media_errors:
        clave = ("disk.warn.media.one" if salud.media_errors == 1
                 else "disk.warn.media.many")
        avisos.append(("alto", _(clave).format(n=thousands(salud.media_errors))))

    vida = salud.life_left_percent
    if vida is not None and vida <= VIDA_BAJA_PCT:
        avisos.append(("alto", _("disk.warn.life").format(pct=vida)))
    return avisos


def duracion(segundos: float) -> str:
    """«40 s», «2 min 10 s». Sin decimales: nadie mide un recorte en décimas."""
    if segundos < 60:
        return _("time.seconds").format(n=f"{segundos:.0f}")
    minutos, resto = divmod(int(segundos), 60)
    if resto:
        return _("time.minsec").format(m=minutos, s=resto)
    return _("time.minutes").format(m=minutos)


def home_path(text, home: Optional[str] = None) -> str:
    """Paths as they are shown: the home folder as «~», wherever it is in
    the text (an error message carries its path). People share
    screenshots, and the home folder has the user's name in it."""
    text = str(text)
    home = (home if home is not None else str(pathlib.Path.home())).rstrip("/")
    if not home:
        return text
    return re.sub(r"(?<![\w/.-])" + re.escape(home) + r"(?=$|[/\s'\"),:;])", "~", text)


def version(completa: str, translate=_) -> str:
    """La versión como se enseña: «0.4» y no «0.4.0»; «0.4.1» en un arreglo;
    «0.4-prueba1» en la primera de prueba de la 0.4.

    Por debajo siempre es x.y.z (pyproject, la etiqueta y `--version`, que
    son para máquinas). A quien mira la ventana o lee el informe, el tercer
    número solo le dice algo cuando no es cero: es la versión de arreglos de
    esa. The report passes `en_español`: it is always in Spanish.
    """
    # Una versión de prueba va como la pide PEP 440 («0.4.0rc1») y se
    # enseña con su nombre: «0.4-prueba1».
    prueba = re.fullmatch(r"(\d+\.\d+\.\d+)rc(\d+)", completa)
    if prueba:
        return f"{version(prueba.group(1))}-{translate('app.version.rc')}{prueba.group(2)}"
    partes = completa.split(".")
    if len(partes) == 3 and partes[2] == "0":
        return ".".join(partes[:2])
    return completa


# El orden de las barras de motores, del que más se mira al que menos.
ORDEN_DE_MOTORES = ("engine.render", "engine.compute", "engine.video",
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
        por_tipo: dict[str, list] = {}
        for motor in gpu.engines:
            if motor.kind:
                por_tipo.setdefault(motor.kind, []).append(motor.busy_percent)
        salida = []
        for clave in ORDEN_DE_MOTORES:
            if clave in por_tipo:
                leidos = [v for v in por_tipo[clave] if v is not None]
                salida.append((clave, max(leidos) if leidos else None))
        return salida
    if gpu.vendor == "AMD":
        salida = [("engine.render", gpu.busy_percent),
                  ("engine.video", gpu.video_busy_percent)]
    elif gpu.vendor == "NVIDIA":
        salida = [("engine.render", gpu.busy_percent),
                  ("engine.decode", gpu.decode_busy_percent),
                  ("engine.encode", gpu.encode_busy_percent)]
    else:
        return []
    return [(k, v) for k, v in salida if v is not None]


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
    esperados = (("engine.render", "engine.decode", "engine.encode")
                 if gpu.vendor == "NVIDIA" else ("engine.render", "engine.video"))
    medidos = {clave for clave, _valor in engine_levels(gpu)}
    return [clave for clave in esperados if clave not in medidos]


def gpu_asleep(gpu, fahrenheit: bool = False) -> str:
    """Qué se dice de una gráfica suspendida, o "" si está despierta.

    Sin cifras de ahora, que no se han leído, y con lo último que se supo y
    de cuándo, si se llegó a ver despierta: una temperatura sin su hora se
    leería como la de este momento.
    """
    if not getattr(gpu, "suspended", False):
        return ""
    texto = _("gpu.asleep")
    if gpu.last_awake_s is not None:
        import time
        hora = time.strftime("%H:%M", time.localtime(gpu.last_awake_s))
        if gpu.last_temp_c is not None:
            texto += " " + _("gpu.asleep.lasttemp").format(
                hora=hora, valor=temperature(gpu.last_temp_c, fahrenheit))
        else:
            texto += " " + _("gpu.asleep.last").format(hora=hora)
    return texto


def throttle_episode(episodio, ahora_ns: int) -> Optional[str]:
    """Cuánto lleva —o llevó— frenándose, y por qué.

    «Recortando por temperatura del punto caliente» dice qué pasa ahora y no
    dice lo que se quiere saber. Una tarjeta que toca su límite de potencia
    medio segundo en cada cambio de escena funciona como se diseñó; una que
    lleva un minuto contra el límite térmico tiene un problema de
    refrigeración. El dato es el mismo y la conclusión es la contraria.
    """
    if episodio is None:
        return None
    cuanto = duracion(episodio.duracion_s(ahora_ns))
    motivos = ", ".join(sorted(episodio.motivos)) or _("throttle.unknown")
    clave = "throttle.ongoing" if episodio.en_curso() else "throttle.past"
    return _(clave).format(tiempo=cuanto, motivos=motivos)


def gpu_clock_limits(relojes) -> Optional[str]:
    """«350 MHz – 900 MHz», solo si alguien cambió los límites del motor.

    De fábrica el mínimo y el máximo puestos son los del silicio (RPn y
    RP0), y repetirlos sería decir lo mismo dos veces. Si no se saben los
    del silicio no hay con qué comparar.
    """
    puestos = (relojes.core_min_hz, relojes.core_max_hz)
    silicio = (relojes.silicon_min_hz, relojes.silicon_max_hz)
    if None in puestos or None in silicio or puestos == silicio:
        return None
    return f"{hz(puestos[0])} – {hz(puestos[1])}"


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


def monitor_name(monitor: Optional[Edid]) -> str:
    """El modelo tal y como lo enseñaría la pegatina de detrás."""
    if monitor is None:
        return DASH
    # La marca, no la razón social: «GIGA-BYTE TECHNOLOGY CO., LTD. AORUS
    # FO27Q2» se comía el ancho de la tabla de salidas.
    partes = [p for p in (maker(monitor.manufacturer), monitor.model) if p]
    return " ".join(partes) if partes else (monitor.manufacturer_id or DASH)


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
    pulgadas = monitor_diagonal(monitor)
    medida = (f"{monitor.width_mm} × {monitor.height_mm} mm"
              if monitor.width_mm and monitor.height_mm else None)
    partes = [p for p in (pulgadas, medida, monitor.made) if p]
    return " · ".join(partes) if partes else DASH


def display_mode(display: Display) -> str:
    """La resolución nativa con su refresco: «2560 × 1440 · 48–240 Hz»."""
    if not display.connected:
        return DASH
    rango = display.monitor.refresh_range if display.monitor else None
    if not rango and display.refresh_hz:
        rango = f"{display.refresh_hz:g} Hz"
    partes = [p for p in (display.resolution, rango) if p]
    return " · ".join(partes) if partes else DASH


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
    partes = [api.version or DASH]
    if api.driver:
        partes.append(api.driver)
    if api.extra:
        partes.append(api.extra)
    return " · ".join(partes)


def turbo_note(clocks: Clocks) -> Optional[str]:
    """Una frase corta cuando el techo real no llega al del silicio."""
    if clocks.turbo_enabled is False and clocks.max_turbo_hz:
        return _("clock.turbo.off").format(max=hz(clocks.max_turbo_hz))
    if clocks.turbo_headroom_hz:
        return _("clock.turbo.capped").format(
            actual=hz(clocks.max_hz), max=hz(clocks.max_turbo_hz))
    return None


def _rango_de_cpus(cpus: tuple[int, ...]) -> str:
    """«0-7» en vez de «0, 1, 2, 3, 4, 5, 6, 7» cuando son consecutivas."""
    if not cpus:
        return ""
    if len(cpus) > 2 and list(cpus) == list(range(cpus[0], cpus[-1] + 1)):
        return f"{cpus[0]}-{cpus[-1]}"
    return ", ".join(str(c) for c in cpus)


def l3_asimetrica(cpu_type) -> Optional[str]:
    """Cuando la L3 no es igual en todo el procesador, qué le toca a cada cual.

    Es lo que pasa en un Ryzen de dos chiplets con V-Cache en uno solo: un
    7950X3D lleva 96 MB en la mitad de sus núcleos y 32 en la otra. La
    diferencia no es un detalle de ficha técnica —es la razón de ser de la
    pieza, y de qué chiplet coja el planificador depende que un juego rinda
    como el modelo caro o como el barato.

    Se describe lo que se lee y no se diagnostica: la asimetría es un hecho de
    sysfs. Que sea V-Cache lo confirma el nombre comercial, y solo si lo trae.
    """
    ele3 = [c for c in cpu_type.caches if c.level == 3]
    if len({c.size_bytes for c in ele3}) < 2:
        return None

    partes = []
    for cache in sorted(ele3, key=lambda c: -c.size_bytes):
        cpus = cache.instance_cpus[0] if cache.instance_cpus else ()
        donde = _rango_de_cpus(cpus)
        partes.append(
            _("cache.l3.part").format(tam=size(cache.size_bytes), donde=donde)
            if donde else _("cache.l3.partsome").format(tam=size(cache.size_bytes)))
    frase = _("cache.l3.uneven").format(reparto=_("core.join").join(partes))
    if "3D" in (cpu_type.brand or "").upper():
        frase += _("cache.l3.vcache")
    return frase


def vcache(cpu_type) -> Optional[str]:
    """«3D V-Cache» cuando la pieza lo lleva, según su propio nombre.

    El nombre comercial sale de CPUID y lo escribe el fabricante: un
    «Ryzen 7 5800X3D» lo dice él. No se deduce del tamaño de la L3, que
    también crece por otros motivos según la familia.
    """
    marca = (cpu_type.brand or "").upper()
    if "X3D" not in marca:
        return None
    grande = max((c.size_bytes for c in cpu_type.caches if c.level == 3),
                 default=None)
    if grande is None:
        return _("cache.vcache.plain")
    return _("cache.vcache.size").format(tam=size(grande))


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
    por_tipo: dict[str, dict[int, int]] = {}
    for cpu in logical:
        if not cpu.quality:
            continue
        nucleos = por_tipo.setdefault(cpu.type_key, {})
        nucleos.setdefault(cpu.core_id, cpu.quality)

    resultado = {}
    for clave, nucleos in por_tipo.items():
        # Un tipo cuyos núcleos traen todos la misma nota no se ha medido:
        # el firmware ha rellenado el campo con la constante de la familia.
        if len(set(nucleos.values())) < 2:
            continue
        mejor = max(nucleos.values())
        resultado[clave] = sorted(
            ((core, nota, nota / mejor) for core, nota in nucleos.items()),
            key=lambda fila: (-fila[1], fila[0]),
        )
    return resultado


def core_quality(logical) -> list[tuple[int, int, float]]:
    """Como `core_quality_by_type`, aplanado, para una CPU de un solo tipo."""
    por_tipo = core_quality_by_type(logical)
    if len(por_tipo) != 1:
        return []
    return next(iter(por_tipo.values()))


def best_core_ids(logical, cuantos: int = 2) -> set[int]:
    """Los núcleos físicos que llevan estrella: los mejores de cada tipo.

    De cada tipo por separado, porque el mejor P-core y el mejor E-core son dos
    respuestas a la misma pregunta hecha sobre piezas distintas.
    """
    cabeza: set[int] = set()
    for orden in core_quality_by_type(logical).values():
        mejor = orden[0][1]
        # Los empatados con el mejor van todos: en muchas piezas hay dos, y
        # quedarse con uno por el orden del bucle sería inventar un desempate.
        iguales = [core for core, nota, _fraccion in orden if nota == mejor]
        cabeza.update(iguales[:cuantos])
    return cabeza


def best_cores(logical, cuantos: int = 2) -> str:
    """«Núcleo 1 y núcleo 3», los que el firmware marca como los mejores."""
    cabeza = sorted(best_core_ids(logical, cuantos))
    if not cabeza:
        return DASH
    nombres = [_("core.name").format(n=core) for core in cabeza]
    if len(nombres) == 1:
        return nombres[0].capitalize()
    return (", ".join(nombres[:-1]) + _("core.join") + nombres[-1]).capitalize()


def starred_cpus(logical) -> str:
    """Las CPU lógicas que llevan estrella, para que la cuenta cuadre.

    Con SMT cada núcleo bueno marca sus dos hilos, así que en un 5800X3D se
    ven cuatro estrellas y la frase decía «núcleo 1 y núcleo 3». Las dos cosas
    son ciertas y no lo parecen: quien mira cuenta cuatro y lee dos.
    """
    orden = core_quality(logical)
    if not orden:
        return ""
    mejor = orden[0][1]
    cabeza = {core for core, nota, _fraccion in orden if nota == mejor}
    indices = sorted(c.index for c in logical if c.core_id in cabeza)
    if len(indices) <= len(cabeza):        # sin SMT no hay nada que aclarar
        return ""
    nombres = [thread_name(i) for i in indices]
    return ", ".join(nombres[:-1]) + _("core.join") + nombres[-1]


def core_quality_spread(logical) -> Optional[str]:
    """Cuánto va del mejor núcleo al peor dentro de su propio tipo.

    En un híbrido se dice del tipo con más recorrido, que es donde la
    diferencia importa; comparar entre tipos daría una cifra grande y sin
    significado. Ver `core_quality_by_type`.
    """
    por_tipo = core_quality_by_type(logical)
    if not por_tipo:
        return None
    orden = min(por_tipo.values(), key=lambda filas: filas[-1][2])
    peor = orden[-1]
    clave = "core.spread.type" if len(por_tipo) > 1 else "core.spread"
    return _(clave).format(n=peor[0], pct=f"{peor[2] * 100:.0f}")


# Coletillas que los fabricantes meten en la cadena de marca y que no
# distinguen a un procesador de otro.
_RELLENO_DE_MARCA = re.compile(
    r"\s*(?:\d+-Core\s+Processor|Processor|CPU|\(R\)|\(TM\)|™|®"
    r"|@\s*[\d.]+\s*[GM]Hz|with\s+Radeon\s+Graphics"
    r"|w/\s+Radeon[\w\s]*Graphics)",
    re.IGNORECASE)


def cpu_short_name(brand: Optional[str]) -> str:
    """El nombre del procesador sin la paja: «Ryzen 7 5800X3D».

    La cadena de marca viene con coletillas que no distinguen un modelo de
    otro —«8-Core Processor», «(R)», «@ 2.90GHz»— y que en un titular ocupan
    dos líneas para no decir nada: los núcleos y la frecuencia ya están al
    lado, con su propia etiqueta.
    """
    if not brand:
        return DASH
    limpio = _RELLENO_DE_MARCA.sub("", brand)
    limpio = re.sub(r"\s{2,}", " ", limpio).strip(" -·")
    return limpio or brand


def monitor_color(edid) -> str:
    """Lo que el monitor declara en sus extensiones: HDR y espacios de color.

    Sale de los bloques CTA-861, que es donde vive lo moderno. El bloque base
    del EDID es de 1994 y no tiene sitio para nada de esto: sin mirar las
    extensiones, un panel con HDR10 y BT.2020 se describe igual que uno de
    hace veinte años.
    """
    piezas = list(edid.hdr)
    # De los espacios de color solo el más ancho: enseñar los seis que declara
    # un monitor llena la celda sin decir mucho más que el mayor de ellos.
    for amplio in ("BT.2020 RGB", "BT.2020 YCC", "opRGB", "xvYCC709"):
        if amplio in edid.color_spaces:
            piezas.append(amplio)
            break
    return " · ".join(piezas) if piezas else DASH
