"""The package's power, broken down, through RAPL (powercap).

The kernel publishes ever-increasing energy counters in microjoules; watts
are their rate, so the previous reading is kept. The counter wraps at
`max_energy_range_uj`, which must be handled or absurd peaks appear.

The subdomains and the processor's declared limits are read too: «7 W» at
idle looks like a measuring error until the breakdown shows the cores in
deep idle, and the part's sustained limit at 65 W.
"""

from __future__ import annotations

import dataclasses
import pathlib
import time
from typing import Optional

from .. import sysroot
from ..i18n import _
from ..model import Need, Power
from ..privileged.client import HelperError, PrivilegedClient
from .base import Draft, Provider, read_int, read_text
from .counters import increase, window_s

POWERCAP = pathlib.Path("/sys/class/powercap")

# The kernel's subdomain name → the model's field.
SUBDOMAINS = {"core": "core_w", "uncore": "uncore_w", "dram": "dram_w"}


# Where the `core` domain isn't the sum of the cores. On Intel it is PP0, a
# package counter. On AMD the kernel reads `MSR_AMD_CORE_ENERGY_STATUS`,
# which is per core, on the package's first core only, so a load pinned to
# another core doesn't move it.
CORE_DOMAIN_ON_ONE_CORE = frozenset(("AuthenticAMD", "HygonGenuine"))


def _core_is_one_cores(draft: Draft) -> bool:
    return any(t.get("vendor_id") in CORE_DOMAIN_ON_ONE_CORE for t in draft.types.values())


# The framework is named «intel-rapl» after its origin, but AMD uses it too
# and, depending on the kernel, it may show as «amd-rapl».
RAPL_ZONES = ("intel-rapl:*", "amd-rapl:*", "*-rapl:*")


def _packages() -> list[pathlib.Path]:
    if not sysroot.path(POWERCAP).is_dir():
        return []

    found: list[pathlib.Path] = []
    seen: set[str] = set()
    for pattern in RAPL_ZONES:
        for entry in sorted(sysroot.path(POWERCAP).glob(pattern)):
            if entry.name in seen:
                continue
            # Subdomains (core, uncore, dram) have a second «:».
            if entry.name.count(":") > 1:
                continue
            if (read_text(str(entry / "name")) or "").startswith("package"):
                seen.add(entry.name)
                found.append(entry)
    return found


# With no limit declared at all, no single package draws this for a second.
FALLBACK_CEILING_W = 1000.0
# Where dropped readings are reported: the report's diagnosis, on no page.
DISCARDED_PATH = "report.power.discarded"


def package_ceiling_w() -> float:
    """The most a package can draw, from what RAPL declares: its PL4
    (`peak_power`) if declared, otherwise twice its highest limit (it exceeds
    PL2 briefly, never by double), or FALLBACK_CEILING_W with none."""
    packages = _packages()
    if not packages:
        return FALLBACK_CEILING_W
    limits: dict[str, float] = {}
    for constraint in packages[0].glob("constraint_*_name"):
        micro = read_int(str(constraint).replace("_name", "_power_limit_uw"))
        if micro:
            limits[(read_text(str(constraint)) or "").lower()] = micro / 1e6
    if "peak_power" in limits:
        return limits["peak_power"]
    return 2 * max(limits.values()) if limits else FALLBACK_CEILING_W


class Discarded:
    """Readings dropped as impossible (a negative watt, or more than the part
    can draw), listed with their numbers in the report."""

    def __init__(self, source: str) -> None:
        self.source = source
        self.count = 0
        self.last = ""

    def check(self, watts: float, ceiling: float, before: int, after: int,
              seconds: float) -> bool:
        """Whether those watts are possible; if not, they are counted and kept."""
        if 0 <= watts <= ceiling:
            return True
        self.count += 1
        self.last = _("power.discarded.last").format(
            vatios=f"{watts:.1f}", techo=f"{ceiling:.0f}", antes=before, ahora=after,
            segundos=f"{seconds:.3f}")
        return False

    def note(self, draft: Draft) -> None:
        if self.count:
            draft.note(DISCARDED_PATH, Need.ERROR, _("power.discarded").format(
                n=self.count, fuente=self.source, ultima=self.last))


# Intel also keeps the package's limits in the memory controller's registers
# (MMIO), next to the MSR ones; the processor enforces the lower of the two.
MMIO_ZONES = "intel-rapl-mmio:*"


def _mmio_package() -> Optional[pathlib.Path]:
    if not sysroot.path(POWERCAP).is_dir():
        return None
    for entry in sorted(sysroot.path(POWERCAP).glob(MMIO_ZONES)):
        if entry.name.count(":") == 1 and (read_text(str(entry / "name")) or "").startswith("package"):
            return entry
    return None


def effective_limits(msr: dict, mmio: dict) -> dict:
    """Each limit as enforced: the lower of the MSR's and the MMIO's, with
    the other one kept when they differ, to say where it comes from."""
    limits = dict(msr)
    for kind in ("long", "short"):
        a, b = msr.get(f"limit_{kind}_w"), mmio.get(f"limit_{kind}_w")
        if b is None:
            continue
        if a is None or b < a:
            limits[f"limit_{kind}_w"] = b
            limits[f"window_{kind}_s"] = mmio.get(f"window_{kind}_s")
        if a is not None and a != b:
            limits[f"limit_{kind}_other_w"] = max(a, b)
    return limits


def _constraints(zone: pathlib.Path) -> list[tuple[str, str, str]]:
    """PL1's and PL2's files in a zone: each one's kind, power limit and time
    window. PL4 (`peak_power`) has no window, and the kernel answers ENODATA
    when asked for one: it isn't read here."""
    found = []
    for constraint in sorted(zone.glob("constraint_*_name")):
        name = (read_text(str(constraint)) or "").lower()
        kind = "long" if "long" in name else "short" if "short" in name else None
        if kind:
            found.append((kind, str(constraint).replace("_name", "_power_limit_uw"),
                          str(constraint).replace("_name", "_time_window_us")))
    return found


def _read_limits(constraints: list[tuple[str, str, str]]) -> dict[str, Optional[float]]:
    """PL1 and PL2 in watts, with each one's time window in seconds: the
    fields of `Power`."""
    limits: dict[str, Optional[float]] = {}
    for kind, power_file, window_file in constraints:
        micro = read_int(power_file)
        if micro is None:
            continue
        window = read_int(window_file)
        limits[f"limit_{kind}_w"] = round(micro / 1e6, 1)
        limits[f"window_{kind}_s"] = window / 1e6 if window else None
    return limits


class PowerLimits(Provider):
    """PL1 and PL2: the limits the firmware set, available before any power.

    They sit next to the energy counters but differ: the kernel keeps the
    counters root-only, while the limits are readable by anyone. They are
    read every sample, since many laptops change them when the charger is
    plugged in or out. `RaplPower` runs after this and adds the watts to the
    same card.
    """

    name = "power-limits"
    provides = "cpu.power.limits"

    def __init__(self) -> None:
        # Which file is which doesn't change: found once, read every sample.
        self._zones: Optional[tuple[list, list]] = None

    def available(self) -> bool:
        return bool(_packages())

    def collect(self, draft: Draft) -> None:
        if self._zones is None:
            mmio = _mmio_package()
            self._zones = (_constraints(_packages()[0]), _constraints(mmio) if mmio else [])
        msr, mmio = self._zones
        limits = effective_limits(_read_limits(msr), _read_limits(mmio))
        if limits.get("limit_long_w") or limits.get("limit_short_w"):
            draft.cpu_extra["power"] = Power(**limits)


class RaplPower(Provider):
    name = "rapl"
    provides = "cpu.power"

    def __init__(self, client: Optional[PrivilegedClient] = None) -> None:
        self._previous: dict[str, tuple[int, float]] = {}
        # The same helper the disks and memory use. Since kernel 5.10
        # `energy_uj` is root-only, and where that applies (above all AMD) the
        # processor's power was blank.
        self.client = client
        self._by_the_helper = False
        self._cache: dict[str, int] = {}
        # When the helper took its reading: it may wait up to 100 ms to keep
        # its pace, and timing from before the request skewed the watts.
        self._cache_instant = 0.0
        self._ceiling: Optional[float] = None
        self._discarded = Discarded("RAPL")

    def available(self) -> bool:
        packages = _packages()
        if not packages:
            return False
        if read_int(str(packages[0] / "energy_uj")) is not None:
            return True
        # Readable with the helper connected, even though the kernel refuses
        # this process.
        return bool(self.client and self.client.connected())

    def unavailable_reason(self):
        if self.available():
            return None
        if _packages():
            return ("cpu.power", Need.ROOT,
                    _("prov.rapl.denied"), _("prov.rapl.denied.hint"),
                    _("what.cpu.power"))
        return ("cpu.power", Need.HARDWARE,
                _("prov.rapl.none"), _("prov.rapl.none.hint"))

    def collect(self, draft: Draft) -> None:
        packages = _packages()
        if not packages:
            return

        # One helper request per sample, not one per zone.
        self._cache: dict[str, int] = {}
        totals: dict[str, float] = {}

        one_core = _core_is_one_cores(draft)
        no_cores = False
        for package in packages:
            self._accumulate(package, "package_w", totals, draft.interval_s)
            for child in sorted(package.glob(f"{package.name}:*")):
                field = SUBDOMAINS.get(read_text(str(child / "name")) or "")
                if field == "core_w" and one_core:
                    no_cores = True
                elif field:
                    self._accumulate(child, field, totals, draft.interval_s)
        self._discarded.note(draft)

        if "package_w" not in totals:
            return                          # the first pass only sets the baseline
        if totals["package_w"] == 0:
            # A powered package always draws something: a counter that didn't
            # move in a whole sample is stuck, and 0 W would look like a value.
            # Subdomains can stand still (an integrated GPU that's off); the
            # package can't.
            draft.note("cpu.power", Need.HARDWARE,
                       _("prov.rapl.frozen"), _("prov.rapl.frozen.hint"))
            return

        draft.capabilities.add("rapl")
        if no_cores:
            draft.note("cpu.power.core_w", Need.HARDWARE,
                       _("prov.rapl.onecore"), _("prov.rapl.onecore.hint"))
        uncore, graphics = self._rounded(totals.get("uncore_w")), None
        integrated = next((g for g in draft.gpus
                           if g.get("vendor") == "Intel" and g.get("integrated")), None)
        if integrated is not None and uncore is not None:
            # Intel's PP1 is its integrated GPU's plane: the GPU's power, the
            # same figure on its page as here.
            graphics, uncore = uncore, None
            integrated["power_w"] = graphics
        draft.cpu_extra["power"] = dataclasses.replace(
            draft.cpu_extra.get("power") or Power(),
            package_w=round(totals["package_w"], 1),
            core_w=self._rounded(totals.get("core_w")),
            uncore_w=uncore,
            graphics_w=graphics,
            dram_w=self._rounded(totals.get("dram_w")),
        )

    # -- internals ----------------------------------------------------------

    @staticmethod
    def _rounded(value: Optional[float]) -> Optional[float]:
        return None if value is None else round(value, 2)

    def _by_helper(self, zone: str) -> Optional[int]:
        """A zone's microjoules when the kernel won't let this process read
        them.

        All zones are asked for at once and cached: package, cores and DRAM
        would otherwise be four helper trips per sample.
        """
        if not (self.client and self.client.connected()):
            return None
        if not self._cache:
            try:
                self._cache = self.client.rapl()
                self._cache_instant = time.monotonic()
                self._by_the_helper = True
            except HelperError:
                return None
        return self._cache.get(zone)

    def _read(self, zone: pathlib.Path) -> tuple[Optional[int], str, float]:
        """The zone's microjoules, their source and when they were read."""
        microjoules = read_int(str(zone / "energy_uj"))
        if microjoules is not None:
            return microjoules, "sysfs", time.monotonic()
        microjoules = self._by_helper(zone.name)
        return microjoules, "helper", self._cache_instant

    def _accumulate(self, zone: pathlib.Path, field: str,
                    totals: dict[str, float], interval_s: float) -> None:
        microjoules, source, instant = self._read(zone)
        if microjoules is None:
            return

        key = zone.name
        before = self._previous.get(key)
        self._previous[key] = (microjoules, instant, source)
        # Not against a reading from the other source: same counter, read at
        # a different time.
        if before is None or before[2] != source:
            return

        elapsed = window_s(before[1], instant, interval_s)
        if elapsed is None:
            return
        delta = increase(before[0], microjoules)
        if delta is None:
            # It wrapped: only then is the range read.
            delta = increase(before[0], microjoules,
                             wrap=read_int(str(zone / "max_energy_range_uj")))
        if delta is None:
            return

        watts = delta / 1e6 / elapsed
        if self._ceiling is None:
            self._ceiling = package_ceiling_w()
        if self._discarded.check(watts, self._ceiling, before[0], microjoules, elapsed):
            totals[field] = totals.get(field, 0.0) + watts
