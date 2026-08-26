"""Capa de presentación: convierte valores en texto.

Todo el formateo del programa vive aquí y solo aquí. El modelo guarda
hercios, bytes y grados; la interfaz y la CLI llaman a estas funciones. Es lo
que permite tener una salida JSON de verdad, cambiar de °C a °F sin tocar la
recolección, y traducir sin reescribir nada.
"""

from __future__ import annotations

from typing import Optional

from .features import pretty as pretty_feature
from .model import Cache, Clocks, CpuType, Power

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
    for unit, factor in (("GB", 1024**3), ("MB", 1024**2), ("KB", 1024)):
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
    """"6 × 32 KB, 8 vías" — la forma en que se lee una jerarquía de caché."""
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


def turbo_note(clocks: Clocks) -> Optional[str]:
    """Una frase corta cuando el techo real no llega al del silicio."""
    if clocks.turbo_enabled is False and clocks.max_turbo_hz:
        return f"Turbo desactivado — el silicio llegaría a {hz(clocks.max_turbo_hz)}"
    if clocks.turbo_headroom_hz:
        return f"El kernel limita a {hz(clocks.max_hz)} de los {hz(clocks.max_turbo_hz)} del silicio"
    return None
