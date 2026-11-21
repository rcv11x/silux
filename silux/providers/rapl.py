"""The package's power, broken down, through RAPL (powercap).

The kernel publishes energy counters in microjoules that only go up. Watts
are their rate, so the previous reading is kept. The counter wraps at
`max_energy_range_uj`, which has to be handled or absurd peaks show.

The subdomains and the limits the processor declares are read too: a «7 W»
at idle looks like a measuring error until the breakdown shows the cores in
deep idle, and that the part's sustained limit is 65 W.
"""

from __future__ import annotations

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

# The kernel's name for each subdomain -> the model's field.
SUBDOMAINS = {"core": "core_w", "uncore": "uncore_w", "dram": "dram_w"}


# Where the `core` domain is not the sum of the cores. On Intel it is PP0, a
# package counter. On AMD the kernel takes it from
# `MSR_AMD_CORE_ENERGY_STATUS`, which is per core, and reads it on one core
# only, the package's first: a load pinned to another core does not move it.
CORE_DOMAIN_ON_ONE_CORE = frozenset(("AuthenticAMD", "HygonGenuine"))


def _core_is_one_cores(draft: Draft) -> bool:
    return any(t.get("vendor_id") in CORE_DOMAIN_ON_ONE_CORE for t in draft.types.values())


# The framework is called «intel-rapl» after its origin, but AMD uses it too
# and, depending on the kernel, it shows as «amd-rapl».
RAPL_ZONES = ("intel-rapl:*", "amd-rapl:*", "*-rapl:*")


def _packages() -> list[pathlib.Path]:
    if not sysroot.ruta(POWERCAP).is_dir():
        return []

    found: list[pathlib.Path] = []
    seen: set[str] = set()
    for pattern in RAPL_ZONES:
        for entry in sorted(sysroot.ruta(POWERCAP).glob(pattern)):
            if entry.name in seen:
                continue
            # Subdomains (core, uncore, dram) carry a second «:».
            if entry.name.count(":") > 1:
                continue
            if (read_text(str(entry / "name")) or "").startswith("package"):
                seen.add(entry.name)
                found.append(entry)
    return found


# Without any limit declared, no single package draws this for a second.
FALLBACK_CEILING_W = 1000.0
# Where a dropped reading is told: the report's diagnosis, no page.
DISCARDED_PATH = "report.power.discarded"


def package_ceiling_w() -> float:
    """The most a package can draw, from what RAPL declares: its PL4
    (`peak_power`) if declared; twice its highest limit if not (it goes above
    PL2 for an instant, never to twice); FALLBACK_CEILING_W without any."""
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
    """The readings dropped as impossible, told in the report with their
    numbers: a negative watt, or more than the part can draw."""

    def __init__(self, source: str) -> None:
        self.source = source
        self.count = 0
        self.last = ""

    def check(self, watts: float, ceiling: float, before: int, after: int,
              seconds: float) -> bool:
        """Whether those watts can be; if not, they are counted and kept."""
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


def _limits(package: pathlib.Path) -> dict[str, Optional[float]]:
    """PL1 and PL2, in watts, as the processor declares them, with each one's
    time window in seconds: the fields of `Power`."""
    limits: dict[str, Optional[float]] = {}
    for constraint in sorted(package.glob("constraint_*_name")):
        name = (read_text(str(constraint)) or "").lower()
        micro = read_int(str(constraint).replace("_name", "_power_limit_uw"))
        if micro is None:
            continue
        window = read_int(str(constraint).replace("_name", "_time_window_us"))
        kind = "long" if "long" in name else "short" if "short" in name else None
        if kind:
            limits[f"limit_{kind}_w"] = round(micro / 1e6, 1)
            limits[f"window_{kind}_s"] = window / 1e6 if window else None
    return limits


class PowerLimits(Provider):
    """PL1 and PL2: the limits the firmware set, without waiting for power.

    They sit next to the energy counters but are not the same: the kernel
    keeps the counters for root, and the limits are readable by any user.
    This runs before `RaplPower`, which writes the whole card when it has
    power.
    """

    name = "power-limits"
    provides = "cpu.power.limits"

    def __init__(self) -> None:
        self._limit_values: Optional[dict] = None

    def available(self) -> bool:
        return bool(_packages())

    def collect(self, draft: Draft) -> None:
        if self._limit_values is None:
            self._limit_values = _limits(_packages()[0])
        if self._limit_values.get("limit_long_w") or self._limit_values.get("limit_short_w"):
            draft.cpu_extra["power"] = Power(**self._limit_values)


class RaplPower(Provider):
    name = "rapl"
    provides = "cpu.power"

    def __init__(self, client: Optional[PrivilegedClient] = None) -> None:
        self._previous: dict[str, tuple[int, float]] = {}
        self._limits: Optional[dict[str, Optional[float]]] = None
        # The same helper the disks and memory use. Since kernel 5.10
        # `energy_uj` is not readable without privileges, and where that
        # applies (AMD above all) the processor's power came out blank.
        self.client = client
        self._by_the_helper = False
        self._cache: dict[str, int] = {}
        # When the helper's reading was taken: it may wait up to 100 ms for
        # its pace, and timing it from before the request skewed the watts.
        self._cache_instant = 0.0
        self._ceiling: Optional[float] = None
        self._discarded = Discarded("RAPL")

    def available(self) -> bool:
        packages = _packages()
        if not packages:
            return False
        if read_int(str(packages[0] / "energy_uj")) is not None:
            return True
        # With the helper connected it can, though the kernel refuses this
        # process.
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

        # One request to the helper per sample, not one per zone.
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
            return                          # the first pass only sets the base
        if totals["package_w"] == 0:
            # A package that is on always draws something: if its counter has
            # not moved in a whole sample it is stuck, and 0 W would look like
            # a value. Subdomains can stay still (an integrated GPU off); the
            # package cannot.
            draft.note("cpu.power", Need.HARDWARE,
                       _("prov.rapl.frozen"), _("prov.rapl.frozen.hint"))
            return

        draft.capabilities.add("rapl")
        if no_cores:
            draft.note("cpu.power.core_w", Need.HARDWARE,
                       _("prov.rapl.onecore"), _("prov.rapl.onecore.hint"))
        if self._limits is None:
            self._limits = _limits(packages[0])

        draft.cpu_extra["power"] = Power(
            package_w=round(totals["package_w"], 1),
            core_w=self._rounded(totals.get("core_w")),
            uncore_w=self._rounded(totals.get("uncore_w")),
            dram_w=self._rounded(totals.get("dram_w")),
            **self._limits,
        )

    # -- internals ----------------------------------------------------------

    @staticmethod
    def _rounded(value: Optional[float]) -> Optional[float]:
        return None if value is None else round(value, 2)

    def _by_helper(self, zone: str) -> Optional[int]:
        """A zone's microjoules when the kernel does not let them be read.

        All are asked at once and kept: with package, cores and DRAM that is
        four readings per sample, and four trips to the helper a second.
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
        """The zone's microjoules, where they came from and when."""
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
        # Not against a reading from the other source: they are the same
        # counter, but timed differently.
        if before is None or before[2] != source:
            return

        elapsed = window_s(before[1], instant, interval_s)
        if elapsed is None:
            return
        delta = increase(before[0], microjoules)
        if delta is None:
            # Gone round: the range is read only then.
            delta = increase(before[0], microjoules,
                             wrap=read_int(str(zone / "max_energy_range_uj")))
        if delta is None:
            return

        watts = delta / 1e6 / elapsed
        if self._ceiling is None:
            self._ceiling = package_ceiling_w()
        if self._discarded.check(watts, self._ceiling, before[0], microjoules, elapsed):
            totals[field] = totals.get(field, 0.0) + watts
