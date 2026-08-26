"""Capa de presentación: convierte valores en texto.

Todo el formateo del programa vive aquí y solo aquí. El modelo guarda
hercios, bytes y grados; la interfaz y la CLI llaman a estas funciones. Es lo
que permite tener una salida JSON de verdad, cambiar de °C a °F sin tocar la
recolección, y traducir sin reescribir nada.
"""

from __future__ import annotations

from typing import Optional

from .features import pretty as pretty_feature
from .model import (Cache, Clocks, CpuType, Display, Edid, GpuApi, PcieLink,
                    GpuMemory, NetworkInterface, NetworkTraffic, Power)

DASH = "—"


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
    return (
        f"EAX de la hoja 1 de CPUID = {signature(raw)}\n\n"
        f"familia base {(raw >> 8) & 0xF}  +  familia extendida {(raw >> 20) & 0xFF}"
        f"  →  familia {cpu_type.disp_family}\n"
        f"modelo base {(raw >> 4) & 0xF}  +  modelo extendido {(raw >> 16) & 0xF} << 4"
        f"  →  modelo {cpu_type.disp_model}\n"
        f"stepping {raw & 0xF}"
    )


def load_average(values: tuple[float, ...], threads: int = 0) -> str:
    """Carga a 1, 5 y 15 minutos, con el número de hilos como referencia."""
    if not values:
        return DASH
    text = " · ".join(f"{v:.2f}" for v in values)
    return f"{text}  (de {threads} hilos)" if threads else text


def cache_summary(cache: Cache) -> str:
    """«6 × 32 KB, 8 vías»: la forma en que se lee una jerarquía de caché."""
    parts = [size(cache.size_bytes)]
    if cache.instances > 1:
        parts[0] = f"{cache.instances} × {parts[0]}"
    if cache.ways:
        parts.append(f"{cache.ways} vías")
    return ", ".join(parts)


def cache_label(cache: Cache) -> str:
    kinds = {"data": "L%d datos", "instruction": "L%d instr.", "unified": "L%d"}
    return kinds.get(cache.kind, "L%d") % cache.level


def core_type_label(cpu_type: CpuType, hybrid: bool) -> str:
    if not hybrid:
        return "Procesador"
    return {
        "performance": "Núcleos P (rendimiento)",
        "efficiency": "Núcleos E (eficiencia)",
    }.get(cpu_type.key, f"Núcleos «{cpu_type.key}»")


def instructions(cpu_type: CpuType, limit: int | None = None) -> str:
    from .features import HIGHLIGHTS

    present = set(cpu_type.features)
    shown = [pretty_feature(f) for f in HIGHLIGHTS if f in present]
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
        return f"{power.load_percent:.0f} % de {power.limit_long_w:g} W"
    return ""


def power_breakdown(power: Power) -> str:
    """El reparto por dominio, que es lo que explica un consumo en reposo bajo."""
    parts = [
        (f"núcleos {watts(power.core_w)}", power.core_w),
        (f"uncore {watts(power.uncore_w)}", power.uncore_w),
        (f"DRAM {watts(power.dram_w)}", power.dram_w),
    ]
    return " · ".join(text for text, value in parts if value is not None)


def power_tooltip(power: Power) -> str:
    lines = [f"Paquete: {watts(power.package_w)}"]
    if breakdown := power_breakdown(power):
        lines.append(breakdown.replace(" · ", "\n"))
    if power.limit_long_w:
        lines.append(f"\nLímite sostenido (PL1): {watts(power.limit_long_w)}")
    if power.limit_short_w:
        lines.append(f"Límite de pico (PL2): {watts(power.limit_short_w)}")
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
            return "sin señal" if interface.kind == "wifi" else "sin cable"
        return "parada"
    if interface.ipv4 or interface.ipv6:
        return "activa"
    return "sin dirección"


def rpm(value: Optional[int]) -> str:
    return DASH if _none(value) else f"{int(value)} RPM"


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
    return f"Ahora a {pcie_link(link)}; la tarjeta y la ranura llegan a {pcie_link(link, maximum=True)}"


def gpu_memory_summary(memory: GpuMemory) -> str:
    """«2.0 GB de 15.9 GB  (12 %)»."""
    if memory.total_bytes is None:
        return DASH
    if memory.used_bytes is None:
        return size(memory.total_bytes)
    return (f"{size(memory.used_bytes)} de {size(memory.total_bytes)}"
            f"   ({memory.used_percent:.0f} %)")


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
    return f"{memory.bus_bits} bits" if memory.bus_bits else DASH


# Cada fabricante cuenta sus unidades de proceso de una forma y no son
# equivalentes entre sí.
UNIDADES_DE_PROCESO = {
    "NVIDIA": "núcleos CUDA",
    "AMD": "unidades de cómputo",
    "Intel": "unidades de ejecución",
}


def compute_units(gpu) -> str:
    """«64 unidades de cómputo», «2048 núcleos CUDA»."""
    if not gpu.compute_units:
        return DASH
    nombre = UNIDADES_DE_PROCESO.get(gpu.vendor or "", "unidades de proceso")
    return f"{gpu.compute_units} {nombre}"


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
        return "activo"
    ventana = size(memory.visible_bytes) if memory.visible_bytes else DASH
    return f"desactivado: la CPU solo alcanza {ventana}"


def throttle_state(gpu) -> str:
    """Si la tarjeta se está frenando, y por qué motivos."""
    if gpu.throttled is None:
        return DASH
    if not gpu.throttled:
        return "sin límites"
    if not gpu.throttle_reasons:
        return "recortando rendimiento"
    return "recortando por " + ", ".join(gpu.throttle_reasons)


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
        return "sin conectar"
    return display.resolution or "conectada"


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
        return f"Turbo desactivado: el silicio llegaría a {hz(clocks.max_turbo_hz)}"
    if clocks.turbo_headroom_hz:
        return f"El kernel limita a {hz(clocks.max_hz)} de los {hz(clocks.max_turbo_hz)} del silicio"
    return None
