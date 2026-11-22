"""Presentation layer: turns values into text.

All the program's formatting lives here and only here. The model keeps
hertz, bytes and degrees; the interface and the CLI call these functions.
It's what allows a real JSON output, switching from °C to °F without
touching collection, and translating without rewriting anything.
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

# How many decimals each sensor quantity takes. Rounding them all alike
# spoils half: a voltage at one decimal stops being a voltage (0.845 V
# becomes 0.8 and says nothing) and a fan with decimals says no more. It
# lives here and not on the sensors page because the report uses it too.
SENSOR_DECIMALS = {
    SensorKind.TEMPERATURE: 1,
    SensorKind.VOLTAGE: 3,
    SensorKind.FAN: 0,
    SensorKind.POWER: 1,
    SensorKind.CURRENT: 2,
    SensorKind.ENERGY: 0,
}


def sensor_value(value: Optional[float], kind: SensorKind) -> str:
    """A sensor's value with the decimals it takes.

    No unit: whoever adds it decides first whether to convert, as the screen
    does with Fahrenheit.
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
    if (choice := voltage_choice(module)):
        return choice
    if module.voltage_mv is None:
        return DASH
    text = f"{module.voltage_mv / 1000:.2f} V"
    return f"{text} · {_('memory.source.bios')}" if module.voltage_from_firmware else text


def module_type(module) -> Optional[str]:
    """A module's technology: «DDR3L» for DDR3 its SPD declares at 1.35 V."""
    spd = module.spd
    name = memory_type(module.type) or (spd.dram_type if spd else None)
    if name == "DDR3" and spd is not None and 1.35 in spd.voltages_v:
        return "DDR3L"
    return name


def voltage_choice(module) -> Optional[str]:
    """«1.35 V o 1.50 V» when the SPD declares several and the firmware's
    table, which says the one in use, isn't read."""
    spd = module.spd
    if module.voltage_configured_mv or spd is None or len(spd.voltages_v) < 2:
        return None
    return enumeration([f"{v:.2f} V" for v in sorted(spd.voltages_v)], "list.or")


def memory_type(name: Optional[str], translate=_) -> Optional[str]:
    """A memory technology: its name, or SMBIOS 1Fh said in words."""
    if name == LOGICAL_NON_VOLATILE:
        return translate("smbios.type.logicalnvm")
    return name


def made(year: Optional[int], week: Optional[int], translate=_) -> Optional[str]:
    """When a piece was made, as its own standard dates it: «week 16 of
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
    # A zero isn't scaled: a GPU in deep idle reads 0 and came out as
    # «0 kHz», suggesting a tiny frequency rather than a stop. Choosing the
    # unit by magnitude makes no sense without a magnitude. Still not a
    # missing datum: stopped is the answer.
    if value == 0:
        return "0 MHz"
    return f"{value / 1e3:.0f} kHz"


def size(value: Optional[int]) -> str:
    """Always in the largest unit that applies.

    Preferring the unit the division came out exact in showed 13.9 MB of
    total cache as "14208 KB".
    """
    if _none(value):
        return DASH
    value = int(value)
    # Terabytes came with disks: until then the largest unit seen was RAM,
    # and «8849.3 GB» of total storage isn't read, it's counted.
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
    said «50 Wh» above a «Design 50.5 Wh»."""
    return DASH if _none(value) else f"{float(value):.1f} Wh"


def figure(value: Optional[float], decimals: int = 0) -> str:
    """A big tile's figure, without its unit, which goes apart.

    With the value font's tabular figures, what it measures only depends on
    how many it has: the width each tile reserves (`StatTile.reserve`)
    comes from here too, with the cap of what it can come to say.
    """
    return DASH if _none(value) else f"{float(value):.{decimals}f}"


def percent(value: Optional[float]) -> str:
    return DASH if _none(value) else f"{float(value):.1f} %"


def multiplier(value: Optional[float]) -> str:
    return DASH if _none(value) else f"× {float(value):.1f}"


def clock_and_multiplier(frequency: Optional[int],
                         factor: Optional[float]) -> str:
    """«3.40 GHz  × 34.0», or just the part that's known.

    Both go on the same row, and joining them bluntly left the missing one's
    gap showing: a processor without a published multiplier came out as
    «1.60 GHz  —», and one with neither as «—  —». A dash marks a missing
    datum, and there it read as a formatting fault.
    """
    pieces = [p for p in (hz(frequency), multiplier(factor)) if p != DASH]
    return "  ".join(pieces) or DASH


def dec(value: Optional[int]) -> str:
    """An integer as is. It exists so as not to write `x or DASH`: stepping 0
    is a real stepping, and `or` would turn it into a dash."""
    return DASH if value is None else str(value)


def hex_id(value: Optional[int]) -> str:
    """As datasheets show it: decimal and hexadecimal together."""
    if value is None:
        return DASH
    return f"{value} (0x{value:X})"


def signature(value: Optional[int]) -> str:
    """CPUID leaf 1's EAX register, as is."""
    return DASH if value is None else f"0x{value:08X}"


def signature_tooltip(cpu_type: CpuType) -> str:
    """Explain where the composed family and model come from.

    It's the question everyone asks seeing a "model 5" on a processor Intel
    calls 165: CPUID splits each value into a base and an extended field,
    and what counts is the sum.
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
    """Who's underneath, or nothing on bare metal.

    It lives here and not in each page because two ask for it (Home and CPU)
    and because it changes how everything else reads: a virtual machine's
    cores, sockets and caches are the ones the hypervisor made up, not those
    of the part whose name is in the headline.
    """
    if not cpu_type.in_virtual_machine:
        return None
    if cpu_type.hypervisor:
        return _("cpu.vm.named").format(nombre=cpu_type.hypervisor)
    return _("cpu.vm")


def load_average(values: tuple[float, ...], threads: int = 0) -> str:
    """Load at 1, 5 and 15 minutes, with the thread count as reference."""
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
    """«6 × 32 KB, 8 vías»: how a cache hierarchy reads."""
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
    """A datum that comes from the processor table and not the silicon.

    The codename, node and package aren't read from the processor: they're
    in a table that's a snapshot of the day it was made, and one released
    later isn't there. It's said so, not with a dash, which reads as «this
    machine doesn't have it». `translate_key`, as in `core_type_label`.
    """
    return value or (translate_key or _)("cpu.notintable")


def core_type_label(cpu_type: CpuType, hybrid: bool, translate_key=None) -> str:
    """`translate_key` lets fixed Spanish be asked for from outside the
    interface.

    The report is in Spanish whatever happens, so `in_spanish` goes in there
    instead of `_`; with the normal function, the report of someone with the
    interface in English would mix both languages on one page.
    """
    tr = translate_key or _
    if not hybrid:
        return tr("cpu.type.generic")
    # «P» and «E» are Intel's names; ARM calls the same thing big.LITTLE. The
    # split is the same, the name isn't, and whoever looks at their phone
    # doesn't recognize «E core» anywhere.
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
    """A short line putting the power draw in context: "of 65 W sustained"."""
    if power.package_w is None:
        return ""
    if power.limit_long_w:
        return _("cpu.power.headline").format(
            pct=f"{power.load_percent:.0f}", w=f"{power.limit_long_w:g}")
    return ""


# The idle bar's tones, from the lightest state to the deepest: the deeper it
# sleeps, the more it looks like the background. What stands out is the active.
_IDLE_TONES = ("accent/0.6", "accent/0.4", "accent/0.25", "accent/0.15", "line")


_CORETEMP_PACKAGE = re.compile(r"^Package id (\d+)$")
_CORETEMP_CORE = re.compile(r"^Core (\d+)$")


def sensor_label(sensor) -> str:
    """A sensor's name in the tree, in the interface's language.

    Only the labels `coretemp` publishes in English: «Package id 0» is
    «Paquete» and «Core 3», «Núcleo 3». The model keeps them as they are,
    which the report and the CSV want; other chips' are the maker's and
    aren't touched.
    """
    if sensor.chip == "coretemp":
        if (match := _CORETEMP_PACKAGE.match(sensor.label)):
            number = int(match.group(1))
            return _("sensor.package") if number == 0 else f'{_("sensor.package")} {number}'
        if (match := _CORETEMP_CORE.match(sensor.label)):
            return _("sensor.core").format(n=int(match.group(1)))
    return sensor.label


def idle_name(name: str) -> str:
    """«C2», not «C2_ACPI».

    `intel_idle` appends «_ACPI» to the states it takes from the firmware's
    table when it has none of its own for that processor. It says where the
    state came from, not which state it is.
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
    """The idle bar's segments: the active part and each state, out of 100."""
    asleep = sum(e.percent for e in states)
    spans = [Segment("active", _("cpu.idle.active"),
                      max(0.0, round(100.0 - asleep, 1)), "accent")]
    timed = [e for e in states if e.percent > 0]
    for i, state in enumerate(timed):
        # The deepest always in the background's tone.
        tone = _IDLE_TONES[-1] if i == len(timed) - 1 and len(timed) > 1 \
            else _IDLE_TONES[min(i, len(_IDLE_TONES) - 2)]
        spans.append(Segment(state.name, idle_name(state.name), state.percent, tone))
    return spans


def idle_deepest(states) -> Optional[str]:
    """«C2, the deepest idle: between 54 % and 73 % depending on the thread.»"""
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
    """The breakdown by domain, which explains a low idle power draw."""
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
    """The word that fits the quantity.

    Seems trivial until a machine with a single memory module reads «1
    modules read» and thinks the program is broken. When someone is going to
    trust the figures, agreement is part of trusting.
    """
    return singular if amount == 1 else plural_


def unique_id(raw: Optional[str]) -> Optional[str]:
    """A part's unique identifier, or nothing if it identifies nothing.

    All zeros is a driver's way of saying it doesn't have one.
    """
    if not raw or not raw.strip().strip("0"):
        return None
    return raw.strip()


_DMI_DATE = re.compile(r"(\d{1,2})/(\d{1,2})/(\d{4})")


def bios_date(raw: Optional[str]) -> Optional[str]:
    """The BIOS date without ambiguity: «2025-10-28».

    The firmware writes it as month/day/year, American style, and painted as
    is «06/08/2023» reads in Spain as the sixth of August when it's the
    eighth of June. Year-month-day can't be confused. What doesn't have that
    shape is left as it comes: better than inventing an order.
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
    """«AMI 1.80 (2023-06-08)»: whose the BIOS is, which, and from when."""
    together = " ".join(p for p in (short_vendor(board.bios_vendor), board.bios_version) if p)
    date = bios_date(board.bios_date)
    return f"{together} ({date})" if together and date else together or DASH


def lock_tooltip(note) -> str:
    """What a datum missing for permissions says on its padlock.

    Why it's missing, in the note's words, and what happens on clicking it.
    """
    return f"{note.message}\n\n{_('lock.tip.outdated' if note.helper_outdated else 'lock.tip')}"


def permission_action(note) -> str:
    """The button of a note that needs permissions: give them, or update the
    installed helper when it is from another version."""
    return _("perm.replace.button") if note.helper_outdated else _("perm.button.read")


def permission_title(note, title: str) -> str:
    """A notice's title: the page's own, or that the helper is out of date."""
    return _("perm.outdated.title") if note.helper_outdated else title


# How the kernel names a link's duplex, and by which key it's said here.
# What's not in the table («unknown», from an interface without a cable) isn't
# painted: it's not a duplex, there's just no negotiation.
DUPLEX = {"full": "net.duplex.full", "half": "net.duplex.half"}


def link_summary(interface) -> Optional[str]:
    """«2.5 Gb/s · dúplex completo»: how the link was negotiated."""
    if not interface.speed_mbps:
        return None
    if interface.speed_mbps >= 1000:
        speed = f"{interface.speed_mbps / 1000:g} Gb/s"
    else:
        speed = f"{interface.speed_mbps} Mb/s"
    key = DUPLEX.get((interface.duplex or "").lower())
    return f"{speed} · {_(key)}" if key else speed


def rate(value: Optional[float], bits: bool = False) -> str:
    """A transfer rate: «2.1 MB/s» or «17.6 Mb/s», to choose.

    Both units are right and differ by a factor of eight, which is exactly
    what confuses: the same link is 116 MB/s in a download manager and
    931 Mb/s in a speed test. As there's no answer good for everyone, both
    are offered and the viewer decides.

    Both in powers of a thousand, not 1024. That's networking's convention
    (a «gigabit» link is a billion bits per second), and following it makes
    the two units match each other and what a speed test shows, exactly eight
    times. With powers of 1024 it would come out 976 and nobody would see
    where the difference comes from. Accumulated totals do use 1024, like
    the rest of the program, since their reference is the disk, not the cable.
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
    """«↓ 1.2 GB · ↑ 456 MB», the history since the interface came up."""
    if not traffic.total_bytes:
        return DASH
    return f"↓ {size(traffic.rx_bytes)}   ↑ {size(traffic.tx_bytes)}"


def interface_state(interface: NetworkInterface) -> str:
    """The link's state, in one word."""
    if not interface.up:
        # Telling «off» from «on but unplugged» saves a look behind the
        # machine, but only makes sense where there's a cable: a bridge for
        # virtual machines or a tunnel is stopped, not unplugged.
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
    """The fan, with both figures or whichever there is.

    Each driver gives one thing: amdgpu publishes the revolutions and NVML
    only the percentage. Putting «—» with «(0.0 %)» looked as if one datum
    were missing and another extra, when both say it's stopped.
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


# What a legal name carries after the name, and nobody says.
_LEGAL_FORM = re.compile(
    r"[,\s]+(?:Co\.?,?\s*Ltd\.?|Inc\.?|Corp(?:oration)?\.?|Ltd\.?|Limited|LLC|GmbH"
    r"|S\.?A\.?|AG|B\.?V\.?)$", re.IGNORECASE)
_BRAND_IN_BRACKETS = re.compile(r"\[([^\]]+)\]\s*$")


def maker(name: Optional[str]) -> Optional[str]:
    """A maker's brand, not its legal name.

    «Micro-Star International Co., Ltd. [MSI]» is an MSI and «Tul
    Corporation / PowerColor» a PowerColor. The firmware and `pci.ids` give
    the company's name; what's on the box is kept here. First the known ones
    (`model.short_vendor`), then what `pci.ids` itself marks as the brand
    (in brackets, or after the slash) and, failing that, the legal form at
    the end is dropped.
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
    """A product's name starting with its brand.

    `pci.ids` gives the model without the maker: «RTL8111/8168/8211/8411 PCI
    Express Gigabit Ethernet Controller» doesn't say it's a Realtek, which
    is the first thing looked for. If the model already starts with the
    brand, it isn't repeated.
    """
    if not model:
        return None
    brand = maker(vendor)
    if not brand or model.lower().startswith(brand.lower()):
        return model
    return f"{brand} {model}"


def network_kind(kind: Optional[str]) -> str:
    """An interface's type, said in the interface's language: «Ethernet»,
    «Wi-Fi», «Bridge». The provider keeps the key, not the text."""
    if not kind:
        return DASH
    text = _(f"net.kind.{kind}")
    return kind if text == f"net.kind.{kind}" else text


# What an interface may lack, and how the card's foot names it.
INTERFACE_DEVICE_FIELDS = {
    "net.field.mac": "net.na.mac",
    "gpu.field.driver": "net.na.driver",
    "storage.col.model": "net.na.model",
    "net.field.slot": "net.na.slot",
}


def interface_missing(interface) -> list[str]:
    """The fields of INTERFACE_DEVICE_FIELDS this interface doesn't have."""
    values = {
        "net.field.mac": interface.mac,
        "gpu.field.driver": interface.driver,
        "storage.col.model": with_maker(interface.vendor, interface.model),
        "net.field.slot": interface.pci_slot,
    }
    return [key for key in INTERFACE_DEVICE_FIELDS if not values[key]]


def interface_footnote(interface) -> Optional[str]:
    """«No tiene dirección física, driver, modelo ni ranura PCI: es una
    interfaz virtual, sin tarjeta detrás.»"""
    missing = interface_missing(interface)
    if not missing:
        return None
    fields = enumeration([_(INTERFACE_DEVICE_FIELDS[key]) for key in missing], "list.nor")
    virtual = interface.kind in ("virtual", "loopback", "puente")
    return _("net.na.virtual" if virtual else "net.na.device").format(fields=fields)


def network_name(interface) -> str:
    """What a network card is called: its model with the brand, or the
    interface's name if the model isn't known."""
    return with_maker(interface.vendor, interface.model) or interface.name


# The kernel appends to some chips' names where it found them: the Super
# I/O's address («it8688_40050607») or the network card's MDIO bus
# («r8169_0_600:00»). It tells two identical ones apart; it's not for reading.
_CHIP_ADDRESS = re.compile(r"(?:_[0-9a-f]{6,}|_\d+_[0-9a-f]+:\d+)$")


def chip_name(chip: str) -> str:
    """A sensor chip's name without the address the kernel appends."""
    return _CHIP_ADDRESS.sub("", chip)


# How each bus is written. The kernel gives them in lower case, and putting
# them all in capitals leaves «NVME» next to a properly written «NVMe».
_BUSES = {"nvme": "NVMe"}


def disk_bus(transport: Optional[str]) -> str:
    """A disk's bus as it's written: «NVMe», «SATA», «USB»."""
    if not transport:
        return DASH
    return _BUSES.get(transport, transport.upper())


def pcie_link(link: PcieLink, maximum: bool = False) -> str:
    """«PCIe 5.0 × 16», as everyone but sysfs names it."""
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
    """Why the link runs slower than it can, when it does.

    Almost always the card is idle and the driver lowered the link to save
    power, so it's said as a remark, not a warning: on an idle machine it's
    what should happen.
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
    """«2.0 GB of 15.9 GB  (12 %)», or nothing if how much is used is unknown.

    Returning the total when the driver didn't publish the used memory had
    the page paint it under «In use», and integrated graphics claimed all of
    it occupied. A missing datum is said to be missing.
    """
    if memory.total_bytes is None or memory.used_bytes is None:
        return DASH
    return (_("gpu.vram.of").format(usado=size(memory.used_bytes),
                                    total=size(memory.total_bytes))
            + f"   ({memory.used_percent:.0f} %)")


def possible_texts(formatter, top: float) -> list[str]:
    """What `formatter` can write for a value between 0 and `top`.

    To reserve the longest one's width so the column doesn't dance as the
    figures change. The longest comes right before a change of unit or one
    more digit («1023.9 MB», «999.9 W»), so it's tried there in base 2 and
    base 10, and a little above the cap: a power draw can exceed its own for
    an instant. And closer still, where rounding already goes up and the
    unit hasn't changed: 999.96 MB/s is written «1000.0 MB/s», one figure
    more than «999.9».
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
    """Memory bandwidth, in spec sheets' units."""
    if _none(value):
        return DASH
    return f"{float(value) / 1e9:.0f} GB/s"


def vram_kind(memory: GpuMemory) -> str:
    """The memory type alone: GDDR6, HBM2e. Nothing more.

    The bus width is another datum with its own row.
    """
    return memory.kind or DASH


def vram_bus(memory: GpuMemory) -> str:
    """The memory bus width: «256 bits»."""
    return (_("gpu.bus.bits").format(n=memory.bus_bits)
            if memory.bus_bits else DASH)


# Each maker counts its processing units its own way, and they aren't
# equivalent.
PROCESSING_UNITS = {
    "NVIDIA": "gpu.units.cuda",
    "AMD": "gpu.units.cu",
    "Intel": "gpu.units.eu",
}


def compute_units(gpu) -> str:
    """«64 compute units», «2048 CUDA cores»."""
    if not gpu.compute_units:
        return DASH
    key = PROCESSING_UNITS.get(gpu.vendor or "", "gpu.units.generic")
    return f"{gpu.compute_units} {_(key)}"


def compute_units_short(gpu) -> Optional[str]:
    """The same for a badge: «64 CU», «2048 CUDA»."""
    if not gpu.compute_units:
        return None
    short = {"NVIDIA": "CUDA", "AMD": "CU", "Intel": "EU"}.get(gpu.vendor or "", "u.")
    return f"{gpu.compute_units} {short}"


def resizable_bar(memory: GpuMemory) -> str:
    """Whether the CPU reaches all of VRAM or only a 256 MB window."""
    if memory.resizable_bar is None:
        return DASH
    if memory.resizable_bar:
        return _("gpu.rebar.on")
    window = size(memory.visible_bytes) if memory.visible_bytes else DASH
    return _("gpu.rebar.off").format(ventana=window)


# Where to find which channel a module is on. The firmware writes it in
# several ways depending on who made the board, and none is mandatory:
# «P0 CHANNEL A» in the bank, «DIMM_A1» in the locator, «ChannelA-DIMM0» on
# laptops.
_CHANNEL = (
    re.compile(r"CHANNEL[\s_-]*([A-H])\b", re.I),
    re.compile(r"\bDIMM[\s_-]*([A-H])\d", re.I),
    re.compile(r"\bCH([A-H])\b", re.I),
)

# And which controller it hangs from, when the firmware says. Needed because
# the letter alone doesn't identify a channel: a laptop with two modules can
# call them «Controller0-ChannelA» and «Controller1-ChannelA-DIMM0», both
# «channel A» and two different channels, one per controller. Counting only
# letters said «single channel» on a machine running dual channel, and then
# advised spreading the modules, already spread.
_CONTROLLER = re.compile(r"CONTROLLER[\s_-]*(\d+)", re.I)

# What having so many channels populated is called. Above four the number is
# said: nobody uses «octuple channel».
CHANNEL_NAMES = {1: "mem.chan.1", 2: "mem.chan.2",
                     3: "mem.chan.3", 4: "mem.chan.4"}


def _channel_of(module) -> Optional[str]:
    """Which channel a module is on, if the firmware says.

    Not the letter but something that really identifies the channel: when
    the locator names the controller, the letter alone repeats between them
    and two well-spread modules looked to be in the same place.
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
    """How many channels have at least one module fitted.

    None when the firmware doesn't say which channel each slot is on, as on
    boards that number banks instead of naming them. Making it up would be
    worse than not giving it: in single channel memory performs half, and
    saying the opposite sends someone to open the machine for nothing.
    """
    populated = [m for m in modules if m.populated]
    if not populated:
        return None
    channels = {c for m in populated if (c := _channel_of(m))}
    return len(channels) or None


def memory_channel_label(modules) -> Optional[str]:
    """«Dual channel», «single channel»… with how many modules make it."""
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
    """«0.9 ns». One decimal: any processor's L1 is around there, and with
    no decimals all the fast caches would come out the same."""
    return DASH if _none(value) else f"{float(value):.1f} ns"


def memory_theoretical_bandwidth(modules) -> Optional[int]:
    """What this memory would give if nothing held it back, in bytes per second.

    A multiplication, not a measurement: transfers per second times the
    eight bytes each moves, times the populated channels. It's for setting
    next to what's measured to see how much is used; alone it says little,
    since no machine reaches its theoretical figure.

    Without the channels it isn't computed. Assuming two is the very mistake
    that once gave a wrong warning: in single channel memory performs half,
    and this would show a percentage double the real one.
    """
    channels = memory_channels(modules)
    if not channels:
        return None
    speeds = [m.configured_mts or m.speed_mts for m in modules
                   if m.populated and (m.configured_mts or m.speed_mts)]
    if not speeds:
        return None
    # The slowest: the controller runs everything at the lowest it's given.
    return min(speeds) * 1_000_000 * 8 * channels


def memory_bandwidth_share(measured_value: Optional[int], theoretical: Optional[int]) -> Optional[float]:
    """What fraction of the theoretical figure is reached, in percent."""
    if not measured_value or not theoretical:
        return None
    return round(measured_value / theoretical * 100, 1)


# The pieces firmware sticks into a slot's locator, written thus, without
# spaces and each maker its own way: «Controller0-ChannelA»,
# «ChannelA-DIMM0», «DIMM_A1», «DIMM A», «DIMM 0».
_SLOT_CONTROLLER = re.compile(r"controller\s*[-_]?\s*(\d+)", re.I)
_SLOT_CHANNEL = re.compile(r"chan(?:nel)?\s*[-_]?\s*([a-z])\b", re.I)
# «DIMM_A1» carries channel and number together; «DIMM 0» only the number;
# «DIMM A» only the channel. The order matters: the first that matches wins.
_SLOT_DIMM_CHANNEL_AND_NUMBER = re.compile(r"dimm\s*[-_]?\s*([a-z])\s*(\d+)", re.I)
_SLOT_DIMM_NUMBER = re.compile(r"dimm\s*[-_]?\s*(\d+)", re.I)
_SLOT_DIMM_CHANNEL = re.compile(r"dimm\s*[-_]?\s*([a-z])\b", re.I)


def _slot_parts(locator: str) -> dict:
    """What a slot's locator says, field by field.

    Empty if nothing is recognized, and then the caller keeps the raw text:
    making up a position from something not understood is worse than
    showing what the firmware wrote.
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


# What each USB speed is called. The negotiated one, not the device's
# version: a USB 2.0 keyboard runs at 12 Mb/s and that's fine.
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
    """«Full speed · 12 Mb/s», «SuperSpeed · 5 Gb/s»."""
    if _none(mbps):
        return DASH
    figure = f"{mbps / 1000:g} Gb/s" if mbps >= 1000 else f"{mbps:g} Mb/s"
    key = _USB_SPEEDS.get(float(mbps))
    return f"{_(key)} · {figure}" if key else figure


def usb_kind(device) -> str:
    return _(USB_KINDS.get(device.kind, "usb.kind.other"))


def usb_name(device) -> str:
    """The device's name; if it has none (or the snapshot is anonymous), what it is."""
    name = usb_kind(device)
    return device.product or (name[:1].upper() + name[1:])


def sound_card(card) -> str:
    """«The graphics card's HDMI», «Board · Realtek ALCS1200A», or the USB
    device's name. Not ALSA's («HDA ATI HDMI», «HD-Audio Generic»)."""
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
    outside any partition) is said apart. Without this, ext4's reserve read
    as unmounted space.
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
    """What shows of a drive's TRIM, claiming no more than what shows.

    «Supports it» is a fact. That it's being done is a sign: the partition
    mounted with `discard`, or `fstrim.timer` enabled, which may not cover
    that partition. A spinning disk that supports discards is an SMR, and
    it's said so; a virtual one isn't spinning even if it says so. One that
    doesn't support them doesn't show the row.
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


# A SATA disk's SMART attributes that mean the same on almost all of them.
# The rest are shown with their number: their name depends on the maker.
SMART_COMMON = {
    1: "smart.attr.1", 5: "smart.attr.5", 9: "smart.attr.9", 12: "smart.attr.12",
    187: "smart.attr.187", 188: "smart.attr.188", 194: "smart.attr.194",
    197: "smart.attr.197", 198: "smart.attr.198", 199: "smart.attr.199",
    241: "smart.attr.241", 242: "smart.attr.242",
}


def smart_rows(health) -> list[tuple[str, str]]:
    """A disk's whole diagnosis, in rows of name and value.

    First what has a fixed name (NVMe's comes so from the standard) and
    then, on SATA, the attribute table as is: number, name if it's a common
    one, normalized value and raw counter.
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
    """«active · 34 groups» or «not enabled»."""
    if not platform.iommu_groups:
        return _("plat.iommu.off")
    return _("plat.iommu.on").format(n=platform.iommu_groups)


def virtualization(platform) -> Optional[str]:
    """«active (AMD-V), in use by KVM», or that the processor has it.

    The flag being there doesn't say the BIOS left it on; `/dev/kvm`
    existing does. Without it there's no telling whether it's the BIOS or a
    missing module, and that's exactly what's said.
    """
    if not platform.virtualization:
        return None
    key = "plat.virt.active" if platform.virtualization == "active" else "plat.virt.present"
    return _(key).format(tipo=platform.virtualization_kind or "")


def above_4g(platform) -> Optional[str]:
    """«active · 4 devices use it». With none, nothing is claimed."""
    if not platform.above_4g_devices:
        return None
    return _("plat.above4g.one" if platform.above_4g_devices == 1
             else "plat.above4g.many").format(n=platform.above_4g_devices)


# The thousands separator: a thin no-break space (U+202F). Neither a point
# nor a comma, which each language reads as the other's decimal: «4.136 h»
# looked like four hours. It's what the standard asks for (ISO 80000-1, the
# SI), and reads the same in Spanish and English.
THOUSANDS_SPACE = "\u202f"


def thousands(value: Optional[int]) -> str:
    """«4 136»: an integer with its thousands separated, the same in any locale."""
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


# What a PCI device is by its class, to name what `pci.ids` doesn't have.
# Those of `providers/pci.CLASES`: what the Board table shows.
PCI_CLASSES = {
    "0300": "board.pci.class.vga", "0302": "board.pci.class.3d",
    "0380": "board.pci.class.display", "0108": "board.pci.class.nvme",
    "0106": "board.pci.class.ahci", "0104": "board.pci.class.raid",
    "0200": "board.pci.class.ethernet", "0280": "board.pci.class.network",
    "0c03": "board.pci.class.usb", "0403": "board.pci.class.hda",
    "0401": "board.pci.class.audio",
}


def pci_unnamed(device) -> Optional[str]:
    """«Intel, audio HD (8086:f0c8)»: what isn't in `pci.ids`, by what it is.

    The brand, the device class and its identifier, as whoever wants to
    report or find it searches for it.
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


# The boot phases, in order, with each one's `Boot` field.
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
    """«no», or the reasons: «out-of-tree module · unsigned module»."""
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
    """Each known phase with how long it took: [("sys.boot.phase.firmware", "5.2 s"), …].

    Each separately and the total apart, so there's no doubt whether one
    includes another: the loader publishes two instants counted from
    power-on, and shown as they are it's unclear whether the second adds to
    the first. Without the firmware there's no total (`Boot.total_s`).
    """
    return [(key, seconds(getattr(boot, field))) for key, field in BOOT_PHASES
            if getattr(boot, field) is not None]


def swap_summary(swap) -> str:
    """«45.0 MB of 31.3 GB · zstd · compresses 2.1 to 1 · priority 100»."""
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
    """«zram0 (in memory)», «/swapfile (file)», «/dev/sda2 (partition)»."""
    if swap.zram:
        return _("sys.swap.zram").format(nombre=swap.device.rsplit("/", 1)[-1])
    return _("sys.swap.file" if swap.kind == "file" else "sys.swap.partition").format(
        nombre=swap.device)


# The kernel drivers whose userspace side is Mesa.
_MESA_DRIVERS = ("amdgpu", "radeon", "i915", "xe", "nouveau")


def graphics_stack(snapshot) -> Optional[str]:
    """«Mesa 26.2.6», or «NVIDIA 570.86» on the proprietary driver.

    Nothing new is read: with a free driver, the version OpenGL declares is
    Mesa's («26.2.6-arch3.1», here without the package's suffix).
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
    """«the maker, the chips and the date»: a list as it's spoken.

    For the notes naming what's missing. A comma-separated list of field
    names reads like a form; a sentence doesn't. `last` is the conjunction's
    key: «y» by default, «ni» for what's negated.
    """
    pieces = [p for p in pieces if p]
    if len(pieces) <= 1:
        return "".join(pieces)
    return f"{', '.join(pieces[:-1])} {_(last)} {pieces[-1]}"


def slot_names(zocalos: list[tuple[Optional[str], Optional[str]]]) -> list[str]:
    """Each slot's name, in order: unique, and understandable.

    Takes each one's locator and bank, as the firmware gives them, and
    returns one name per slot in the same order. By position and not by
    locator because locators repeat: some boards call their four slots
    «DIMM 0», «DIMM 1», «DIMM 0», «DIMM 1» and put the channel in the bank
    («P0 CHANNEL A», «P0 CHANNEL B»). With a dictionary by locator, the two
    fitted modules were both «DIMM 1» and the two empty slots «DIMM 0».

    Each maker splits the datum its own way (ASUS «DIMM_A2», MSI «DIMM_A1»,
    OEMs «ChannelA-DIMM0», Lenovo «Controller0-ChannelA»), so what both
    fields say is put together. The rule: **the channel shows whenever it's
    known**, since it decides performance and is what's looked for here;
    the DIMM number and the controller only when without them two slots
    would be called the same.

    If one isn't understood, the firmware's text stays, which beats making
    up a position; and if two still match, the bank is added and, as a last
    resort, their order number. Two never come out the same.
    """
    raw_values = [(localizador or "").strip() for localizador, _bank in zocalos]
    pieces = []
    for localizador, bank_name in zocalos:
        own = _slot_parts(localizador or "")
        # The bank fills in what the locator leaves out, and never corrects it.
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
        # Least to most: a field is added only if without it two slots would
        # be called the same, one before two.
        # The controller before the DIMM number: a channel is a controller's
        # letter, and two «Channel A» on two controllers are two channels.
        for fields in ((), ("controlador",), ("dimm",), ("dimm", "controlador")):
            names = [tag(own, fields) for own in pieces]
            if all(names) and len(set(names)) == len(names):
                return names

    # Not understood, or not told apart even with everything: the firmware's
    # text, and the least needed so no two match.
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
    """The bank without repeating the word the row already carries.

    The firmware writes «BANK 0» and the row is titled «Bank», so it read
    «Bank: BANK 0». Dropped only when the value starts with it and something
    is left after: bank locators carrying more («Node0_Bank0») stay whole,
    since there the rest does tell apart.
    """
    if not bank:
        return bank
    clean = _REDUNDANT_BANK.sub("", bank.strip()).strip()
    return clean or bank


def memory_speed(mts: Optional[int]) -> Optional[int]:
    """The grade name a firmware speed belongs to.

    The SMBIOS table carries what the BIOS wrote, and each rounds the grades
    with a third its own way: DDR4-2666 is 2666.67 MT/s, and some write 2666
    and others 2667. Showing the raw value left two conventions on one card
    («Rated for 3200» and «Running at 2667»), when 2667 names no speed.

    Normalized **when painting** and not before: the model still keeps what
    the firmware said, which is what's needed to check against `dmidecode`,
    and the row's tooltip takes care of that.
    """
    if not mts:
        return mts
    return jedec_grade(mts) or mts


def memory_module_verdict(module, limit=None) -> Optional[str]:
    """Whether a module runs slower than it allows, and why.

    None if it runs at its own speed; «cpu_max» if at the processor's
    official maximum (`limit`, from `db.memory_limit`), which is neither a
    fault nor an inactive profile; «slow» if below without that explaining
    it.
    """
    if not module.underclocked:
        return None
    current = memory_speed(module.configured_mts or module.speed_mts)
    if limit and current and current >= limit.mts * (1 - ROUNDING_MARGIN):
        return "cpu_max"
    return "slow"


def memory_limit_label(limit) -> str:
    """«i5-10400», or «Ryzen 7 5800X3D with 2 single-rank modules».

    On AMD the figure holds for that module layout and no other: with four
    dual-rank modules the same processor guarantees less. It's said.
    """
    if not limit.layout:
        return limit.model
    count, ranges = limit.layout.rstrip("R").split("x")
    return _("mem.layout.one" if ranges == "1" else "mem.layout.many").format(
        modelo=limit.model, n=count, r=ranges)


def memory_speed_warning(modules, limit=None, chipset: bool = False) -> Optional[str]:
    """Why the memory doesn't run faster, when there's something to say.

    The set's ceiling isn't the fastest module's: it's the slowest's, since
    all run on the same clock. With one 3200 module and one 2667 the machine
    won't see 3200 whatever is enabled, so promising it sent someone to
    fight the BIOS for nothing.

    Three answers, not two: there's real headroom (and then the inactive
    fast profile is the usual explanation), there's none but one module
    declares more than another (which must be said, or the card's high
    figure makes no sense), or there's nothing to say.
    """
    fitted = [m for m in modules if m.populated and m.rated_mts]
    if not fitted:
        return None
    ceiling = min(m.rated_mts for m in fitted)
    highest = max(m.rated_mts for m in fitted)
    current = memory_speed(
        max((m.configured_mts or m.speed_mts or 0) for m in fitted))
    if not current:
        # Without the firmware's table the speed in use isn't known, but all
        # modules run on one clock: the slowest's rating is the ceiling.
        if highest > ceiling * (1 + ROUNDING_MARGIN):
            return _("mem.mixed.rated").format(lento=ceiling, rapido=highest)
        return None

    if current < ceiling * (1 - ROUNDING_MARGIN):
        # At the processor's maximum there's no profile to enable: it's what
        # its maker guarantees, and fast modules don't change it.
        if limit and current >= limit.mts * (1 - ROUNDING_MARGIN):
            return _("mem.cpumax").format(actual=current, rated=ceiling,
                                          modelo=memory_limit_label(limit))
        # With the controller in the chipset, the limit is the board's, not
        # the processor's.
        return _("mem.underclocked.chipset" if chipset else "mem.underclocked").format(
            actual=current, rated=ceiling)
    if highest > ceiling * (1 + ROUNDING_MARGIN):
        return _("mem.mixed").format(actual=current, lento=ceiling, rapido=highest)
    return None


def memory_channel_warning(modules) -> Optional[str]:
    """When memory performs below what it could.

    One of the few hardware problems at once very common, very costly in
    performance and completely invisible: nothing in the system warns that
    both modules are on the same channel, and with integrated graphics that
    takes away half the frames.
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

# Below this the SSD is said to have little left. The maker guarantees the
# disk down to 0 %, so 10 % isn't a fault: it's time to think about the
# backup, and saying so early is the only thing that helps.
LOW_LIFE_PCT = 10


def disk_warnings(health) -> list[tuple[str, str]]:
    """What a disk is saying about itself, as `(level, sentence)`.

    `critical_warning` is the field an NVMe warns through that it's on its
    way to losing data.

    Unsafe shutdowns aren't a warning: they count power cuts and reset
    buttons, normal on a desktop.
    """
    warnings: list[tuple[str, str]] = []
    if health is None:
        return warnings

    if health.critical_warning:
        for bit, key in NVME_WARNINGS.items():
            if health.critical_warning & (1 << bit):
                warnings.append(("crítico", _(key).capitalize() + "."))
        if not warnings:                     # a bit the specification doesn't cover
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
    """«40 s», «2 min 10 s». No decimals: nobody measures throttling in tenths."""
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
    """The version as shown: «0.4», not «0.4.0»; «0.4.1» for a fix release;
    «0.4-prueba1» for 0.4's first test release.

    Underneath it's always x.y.z (pyproject, the tag and `--version`, which
    are for machines). To whoever looks at the window or reads the report,
    the third number only says something when it isn't zero. The report
    passes `in_spanish`: it is always in Spanish.
    """
    # A test version goes as PEP 440 asks («0.4.0rc1») and is shown by its
    # name: «0.4-prueba1».
    run = re.fullmatch(r"(\d+\.\d+\.\d+)rc(\d+)", full)
    if run:
        return f"{version(run.group(1))}-{translate('app.version.rc')}{run.group(2)}"
    parts = full.split(".")
    if len(parts) == 3 and parts[2] == "0":
        return ".".join(parts[:2])
    return full


# The order of the engine bars, from the most looked at to the least.
ENGINE_ORDER = ("engine.render", "engine.compute", "engine.video",
                    "engine.decode", "engine.encode", "engine.videoenhance",
                    "engine.copy")


def engine_levels(gpu) -> list[tuple[str, Optional[float]]]:
    """A graphics card's usage bars per engine: (key, percentage).

    Only the engines this card lets be measured, each from where its driver
    gives it (docs/motores-de-graficas.md):

    - Intel (i915, xe) enumerates its engines: one bar per type, with each
      type's busiest, because two half-busy decoders aren't a video at full.
      With None, the engine is there and a permission holds its usage.
    - AMD doesn't enumerate engines: the graphics usage and its video
      engine's (VCN), which encodes and decodes with one figure. Since VCN 4
      decoding also goes through the encode queue, so there's no separating
      them: one bar, not two with a split datum.
    - NVIDIA has NVENC and NVDEC apart, and NVML measures them apart: two
      bars.

    A sleeping card has no bars: nothing was read from it.
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
    """The engines every card has and this one doesn't let be measured.

    Every card has a graphics and a video engine; on NVIDIA, the video one
    is two. What its driver doesn't publish gets no bar and is named at the
    foot, so it doesn't disappear silently. What's there and held by a
    permission isn't this: it carries a padlock (`engine_levels` with None).
    """
    if getattr(gpu, "suspended", False):
        return []
    if gpu.driver == "xe":
        # xe does publish its engines' usage, with a PMU silux doesn't read
        # yet (docs/pendientes.md): saying the card doesn't give it would be
        # false. Its notice says so.
        return []
    expected = (("engine.render", "engine.decode", "engine.encode")
                 if gpu.vendor == "NVIDIA" else ("engine.render", "engine.video"))
    measured = {key for key, _level in engine_levels(gpu)}
    return [key for key in expected if key not in measured]


def gpu_asleep(gpu, fahrenheit: bool = False) -> str:
    """What's said of a suspended card, or "" if it's awake.

    No figures for now, which weren't read, and with the last thing known
    and when, if it was seen awake: a temperature without its time would
    read as the current one.
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
    """How long it's been (or was) throttling, and why.

    «Throttling for hot-spot temperature» says what happens now and not what
    one wants to know. A card touching its power limit half a second at each
    scene change works as designed; one held against its thermal limit for a
    minute has a cooling problem. Same datum, opposite conclusion.
    """
    if episode is None:
        return None
    how_long = duration(episode.duration_s(ahora_ns))
    reasons = ", ".join(sorted(episode.reasons)) or _("throttle.unknown")
    key = "throttle.ongoing" if episode.ongoing() else "throttle.past"
    return _(key).format(tiempo=how_long, motivos=reasons)


def gpu_clock_limits(clocks) -> Optional[str]:
    """«350 MHz – 900 MHz», only if someone changed the engine's limits.

    From the factory the set minimum and maximum are the silicon's (RPn and
    RP0), and repeating them would say the same twice. Without the silicon's
    there's nothing to compare with.
    """
    fitted = (clocks.core_min_hz, clocks.core_max_hz)
    silicon = (clocks.silicon_min_hz, clocks.silicon_max_hz)
    if None in fitted or None in silicon or fitted == silicon:
        return None
    return f"{hz(fitted[0])} – {hz(fitted[1])}"


def gpu_sleep(gpu) -> str:
    """How long the card has slept, or that it isn't allowed to."""
    if gpu.sleep_enabled is False:
        return _("gpu.engines.rc6off")
    return percent(gpu.sleep_percent)


def throttle_state(gpu) -> str:
    """Whether the card is throttling, and for what reasons."""
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
    """The model as the sticker on the back would show it."""
    if monitor is None:
        return DASH
    # The brand, not the legal name: «GIGA-BYTE TECHNOLOGY CO., LTD. AORUS
    # FO27Q2» ate up the outputs table's width.
    parts = [p for p in (maker(monitor.manufacturer), monitor.model) if p]
    return " ".join(parts) if parts else (monitor.manufacturer_id or DASH)


def monitor_diagonal(monitor: Optional[Edid]) -> Optional[str]:
    """«26.7"», or «≈ 27"» when the monitor only gives whole centimetres.

    With half a centimetre of error per side the diagonal moves a quarter of
    an inch: one decimal there is a precision the datum doesn't have.
    """
    if monitor is None or not monitor.diagonal_inches:
        return None
    if monitor.size_exact:
        return f'{monitor.diagonal_inches}"'
    return f'≈ {monitor.diagonal_inches:.0f}"'


def monitor_summary(monitor: Optional[Edid]) -> str:
    """«26.7" · 590 × 334 mm · week 16 of 2024»."""
    if monitor is None:
        return DASH
    inches = monitor_diagonal(monitor)
    measurement = (f"{monitor.width_mm} × {monitor.height_mm} mm"
              if monitor.width_mm and monitor.height_mm else None)
    parts = [p for p in (inches, measurement, made(monitor.year, monitor.week)) if p]
    return " · ".join(parts) if parts else DASH


def display_mode(display: Display) -> str:
    """The native resolution with its refresh: «2560 × 1440 · 48–240 Hz»."""
    if not display.connected:
        return DASH
    range_ = display.monitor.refresh_range if display.monitor else None
    if not range_ and display.refresh_hz:
        range_ = f"{display.refresh_hz:g} Hz"
    parts = [p for p in (display.resolution, range_) if p]
    return " · ".join(parts) if parts else DASH


def display_summary(display: Display) -> str:
    """A video output: what's plugged in and at what resolution.

    On purpose it doesn't say whether the display is on. The kernel
    publishes an `enabled` and a `dpms` that seem to, but under Wayland the
    compositor takes over the modeset and sysfs says «disabled» and «Off» of
    displays working right in front of you. A datum that lies on the most
    common desktop isn't shown.
    """
    if not display.connected:
        return _("display.unplugged")
    return display.resolution or _("display.connected")


def gpu_api_summary(api: GpuApi) -> str:
    """«1.4.354 · Mesa 26.2.1 · 64 compute units»."""
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


def without_energy_preference(clocks: Clocks) -> bool:
    """A frequency driver that offers no energy preference (EPP).

    intel_pstate offers it in active mode with HWP and amd-pstate in active
    mode; in passive mode, or with acpi-cpufreq, the file doesn't exist.
    """
    return bool(clocks.driver) and not clocks.energy_preference


def clocks_footnote(clocks: Clocks) -> Optional[str]:
    """What the Clocks card hides and why: no frequency driver, no turbo,
    no energy preference."""
    parts = [p for p in (
        without_frequency_driver(clocks),
        _("cpu.clocks.noturbo") if clocks.turbo_supported is False else None,
        _("cpu.clocks.noepp").format(driver=clocks.driver)
        if without_energy_preference(clocks) else None) if p]
    return " ".join(parts) or None


def turbo_note(clocks: Clocks) -> Optional[str]:
    """A short sentence when the real ceiling falls short of the silicon's."""
    if clocks.turbo_enabled is False and clocks.max_turbo_hz:
        return _("clock.turbo.off").format(max=hz(clocks.max_turbo_hz))
    if clocks.turbo_headroom_hz:
        return _("clock.turbo.capped").format(
            actual=hz(clocks.max_hz), max=hz(clocks.max_turbo_hz))
    return None


def _cpu_range(cpus: tuple[int, ...]) -> str:
    """«0-7» instead of «0, 1, 2, 3, 4, 5, 6, 7» when they're consecutive."""
    if not cpus:
        return ""
    if len(cpus) > 2 and list(cpus) == list(range(cpus[0], cpus[-1] + 1)):
        return f"{cpus[0]}-{cpus[-1]}"
    return ", ".join(str(c) for c in cpus)


def asymmetric_l3(cpu_type) -> Optional[str]:
    """When L3 isn't the same across the processor, what each part gets.

    As in a two-chiplet Ryzen with V-Cache on one only: half its cores have
    96 MB and the other half 32. Not a spec-sheet detail: it's the part's
    reason to exist, and which chiplet the scheduler picks decides whether a
    game performs like the expensive model or the cheap one.

    It describes what's read and doesn't diagnose: the asymmetry is a sysfs
    fact. That it's V-Cache is confirmed by the commercial name, and only if
    it carries it.
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
    """«3D V-Cache» when the part has it, per its own name.

    The commercial name comes from CPUID and the maker writes it: a «Ryzen 7
    5800X3D» says so itself. It isn't deduced from the L3's size, which also
    grows for other reasons depending on the family.
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
    """By core type, the physical cores sorted best to worst.

    Each row is `(core_id, raw grade, fraction of its type's best)`. The
    fraction is the only thing comparable between machines: the raw grade
    is this part's CPPC performance scale and means something else on
    another.

    Split by type because on an Intel hybrid comparing a P core with an E
    core says nothing about silicon quality: an E core with half the grade
    didn't «come out worse from the wafer», it's another core with another
    purpose and size, and the platform grades it lower by design.

    And grouped by physical core because a core's two threads share silicon
    and necessarily carry the same grade; showing it twice would suggest
    they were measured separately.
    """
    by_type: dict[str, dict[int, int]] = {}
    for cpu in logical:
        if not cpu.quality:
            continue
        cores = by_type.setdefault(cpu.type_key, {})
        cores.setdefault(cpu.core_id, cpu.quality)

    result = {}
    for key, cores in by_type.items():
        # A type whose cores all carry the same grade wasn't measured: the
        # firmware filled the field with the family's constant.
        if len(set(cores.values())) < 2:
            continue
        best = max(cores.values())
        result[key] = sorted(
            ((core, note, note / best) for core, note in cores.items()),
            key=lambda row: (-row[1], row[0]),
        )
    return result


def core_quality(logical) -> list[tuple[int, int, float]]:
    """Like `core_quality_by_type`, flattened, for a single-type CPU."""
    by_type = core_quality_by_type(logical)
    if len(by_type) != 1:
        return []
    return next(iter(by_type.values()))


def best_core_ids(logical, count: int = 2) -> set[int]:
    """The physical cores that get a star: each type's best.

    Each type separately, because the best P core and the best E core are
    two answers to the same question asked of different parts.
    """
    head: set[int] = set()
    for order in core_quality_by_type(logical).values():
        best = order[0][1]
        # Those tied with the best all go: many parts have two, and keeping
        # one by the loop's order would be making up a tiebreak.
        equal = [core for core, note, _fraction in order if note == best]
        head.update(equal[:count])
    return head


def best_cores(logical, count: int = 2) -> str:
    """«Core 1 and core 3», the ones the firmware marks as the best."""
    head = sorted(best_core_ids(logical, count))
    if not head:
        return DASH
    names = [_("core.name").format(n=core) for core in head]
    if len(names) == 1:
        return names[0].capitalize()
    return (", ".join(names[:-1]) + _("core.join") + names[-1]).capitalize()


def starred_cpus(logical) -> str:
    """The logical CPUs that get a star, so the count adds up.

    With SMT each good core marks its two threads, so four stars show while
    the sentence names two cores. Both are true and don't look it: whoever
    looks counts four and reads two.
    """
    order = core_quality(logical)
    if not order:
        return ""
    best = order[0][1]
    head = {core for core, note, _fraction in order if note == best}
    indexes = sorted(c.index for c in logical if c.core_id in head)
    if len(indexes) <= len(head):        # without SMT there's nothing to clarify
        return ""
    names = [thread_name(i) for i in indexes]
    return ", ".join(names[:-1]) + _("core.join") + names[-1]


def core_quality_spread(logical) -> Optional[str]:
    """How far it is from the best core to the worst within its own type.

    On a hybrid it's said of the type with the widest spread, where the
    difference matters; comparing across types would give a large figure
    with no meaning. See `core_quality_by_type`.
    """
    by_type = core_quality_by_type(logical)
    if not by_type:
        return None
    order = min(by_type.values(), key=lambda rows: rows[-1][2])
    worst = order[-1]
    key = "core.spread.type" if len(by_type) > 1 else "core.spread"
    return _(key).format(n=worst[0], pct=f"{worst[2] * 100:.0f}")


# Tails makers put in the brand string that don't tell one processor from
# another.
_RELLENO_DE_MARCA = re.compile(
    r"\s*(?:\d+-Core\s+Processor|Processor|CPU(?!\s+version)|\(R\)|\(TM\)|™|®"
    r"|@\s*[\d.]+\s*[GM]Hz|with\s+Radeon\s+Graphics"
    r"|w/\s+Radeon[\w\s]*Graphics)",
    re.IGNORECASE)


def lost_packets(n: int) -> str:
    """«1 packet discarded», «12 682 packets discarded»."""
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
    """The processor's name without the chaff: «Ryzen 7 5800X3D».

    The brand string comes with tails that don't tell one model from another
    («8-Core Processor», «(R)», «@ 2.90GHz») and in a headline take two
    lines to say nothing: cores and frequency are already next to it, with
    their own label.
    """
    if not brand:
        return DASH
    clean = _RELLENO_DE_MARCA.sub("", brand)
    clean = re.sub(r"\s{2,}", " ", clean).strip(" -·")
    return clean or brand


def monitor_color(edid) -> str:
    """What the monitor declares in its extensions: HDR and colour spaces.

    From the CTA-861 blocks, where the modern things live. The EDID's base
    block dates from 1994 and has no room for any of this: without the
    extensions, a panel with HDR10 and BT.2020 is described like one from
    twenty years ago.
    """
    pieces = list(edid.hdr)
    # Of the colour spaces only the widest: showing all six a monitor
    # declares fills the cell without saying much more than the largest.
    for wide in ("BT.2020 RGB", "BT.2020 YCC", "opRGB", "xvYCC709"):
        if wide in edid.color_spaces:
            pieces.append(wide)
            break
    return " · ".join(pieces) if pieces else DASH
