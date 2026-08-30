"""Capa de presentación: convierte valores en texto.

Todo el formateo del programa vive aquí y solo aquí. El modelo guarda
hercios, bytes y grados; la interfaz y la CLI llaman a estas funciones. Es lo
que permite tener una salida JSON de verdad, cambiar de °C a °F sin tocar la
recolección, y traducir sin reescribir nada.
"""

from __future__ import annotations

import re
from typing import Optional

from .features import pretty as pretty_feature
from .i18n import _
from .model import (Cache, Clocks, CpuType, Display, Edid, GpuApi, PcieLink,
                    GpuMemory, NetworkInterface, NetworkTraffic, Power,
                    SensorKind)

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


def cache_label(cache: Cache) -> str:
    claves = {"data": "cache.label.data", "instruction": "cache.label.instr"}
    return _(claves.get(cache.kind, "cache.label.unified")).format(n=cache.level)


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
        avisos.append(("alto", _(clave).format(n=f"{salud.media_errors:n}")))

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
    partes = [p for p in (monitor.manufacturer, monitor.model) if p]
    return " ".join(partes) if partes else (monitor.manufacturer_id or DASH)


def monitor_summary(monitor: Optional[Edid]) -> str:
    """«26.6" · 590 × 330 mm · semana 16 de 2024»."""
    if monitor is None:
        return DASH
    pulgadas = f'{monitor.diagonal_inches}"' if monitor.diagonal_inches else None
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
    nombres = [f"CPU {i}" for i in indices]
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
