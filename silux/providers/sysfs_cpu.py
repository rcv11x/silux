"""Topology, caches and clocks from /sys/devices/system/cpu.

The most reliable source there is: the kernel writes it, no permission is
needed and it works the same on x86, ARM and RISC-V. It covers almost all
of the CPU page but the processor's identity, which only CPUID knows.
"""

from __future__ import annotations

import dataclasses
import os
import pathlib

from .. import sysroot
from ..i18n import _
from ..model import Cache, Clocks, Need
from .base import Draft, Provider, mean, parse_cpu_list, parse_size, read_int, read_text

SYS_CPU = "/sys/devices/system/cpu"

# On Intel's hybrid CPUs the kernel publishes one PMU per core type: the
# cleanest way to know which logical CPU is a P core and which an E.
HYBRID_PMUS = (
    ("/sys/devices/cpu_core", "performance"),
    ("/sys/devices/cpu_atom", "efficiency"),
)

_CACHE_KINDS = {"data": "data", "instruction": "instruction", "unified": "unified"}


def online_cpus() -> tuple[int, ...]:
    cpus = parse_cpu_list(read_text(f"{SYS_CPU}/online"))
    if cpus:
        return cpus
    # A safety net: without `online`, count the cpuN folders.
    found = []
    for entry in pathlib.Path(sysroot.ruta(SYS_CPU)).glob("cpu[0-9]*"):
        if entry.name[3:].isdigit():
            found.append(int(entry.name[3:]))
    return tuple(sorted(found)) or (0,)


def _arm_cores(cpus: tuple[int, ...]) -> dict[str, list[int]]:
    """Split an ARM's CPUs by the core each one carries.

    Empty unless there is more than one type, as outside ARM and on a
    single-core-type ARM: then the usual split stands.
    """
    from .armcpu import is_arm, midr_by_cpu

    if not is_arm():
        return {}
    midr = midr_by_cpu()
    groups: dict[tuple, list[int]] = {}
    for cpu in cpus:
        identity = midr.get(cpu)
        if identity is None or identity == (None, None):
            return {}                     # incomplete: not guessed
        groups.setdefault(identity, []).append(cpu)
    if len(groups) < 2:
        return {}

    # Big cores first, as the maker numbers them and as one expects to read
    # them: the part number orders them, higher for newer and bigger cores.
    order = sorted(groups, key=lambda k: (k[1] or 0), reverse=True)
    names = ["performance", "efficiency"] if len(order) == 2 else [
        f"nucleo{i}" for i in range(len(order))]
    return {names[i]: groups[key] for i, key in enumerate(order)}


class SysfsTopology(Provider):
    """CPUs by core type and socket, and the cache hierarchy."""

    name = "sysfs-topology"
    provides = "cpu.topology"
    static = True

    def available(self) -> bool:
        return os.path.isdir(sysroot.ruta(SYS_CPU))

    def unavailable_reason(self):
        if self.available():
            return None
        return ("cpu.topology", Need.PLATFORM,
                _("prov.cpu.nosysfs"), _("prov.cpu.nosysfs.hint"), "",
                _("prov.missing.detail").format(ruta="/sys/devices/system/cpu"))

    def collect(self, draft: Draft) -> None:
        draft.capabilities.add("sysfs-cpu")
        cpus = online_cpus()

        by_type = self._classify(cpus)
        draft.hybrid = len(by_type) > 1

        packages: set[int] = set()
        for key, members in by_type.items():
            entry = draft.type_for(key)
            entry["cpus"] = list(members)
            entry["threads"] = len(members)

            cores: set[tuple[int, int]] = set()
            for index in members:
                package_id = read_int(f"{SYS_CPU}/cpu{index}/topology/physical_package_id") or 0
                core_id = read_int(f"{SYS_CPU}/cpu{index}/topology/core_id")
                core_id = core_id if core_id is not None else index
                packages.add(package_id)
                cores.add((package_id, core_id))

                cpu = draft.cpu(index)
                cpu["core_id"] = core_id
                cpu["package_id"] = package_id
                cpu["type_key"] = key

            entry["cores"] = len(cores) or len(members)
            entry["smt"] = entry["threads"] > entry["cores"]
            entry["caches"] = self._caches_for(members)
            entry["microcode"] = self._microcode(members[0])
            entry["clocks"] = self._static_clocks(members[0])

        draft.sockets = len(packages) or 1

    # -- internals ----------------------------------------------------------

    @staticmethod
    def _classify(cpus: tuple[int, ...]) -> dict[str, list[int]]:
        buckets: dict[str, list[int]] = {}
        for path, key in HYBRID_PMUS:
            members = [c for c in parse_cpu_list(read_text(f"{path}/cpus")) if c in cpus]
            if members:
                buckets[key] = members

        assigned = {c for members in buckets.values() for c in members}
        leftover = [c for c in cpus if c not in assigned]
        if leftover:
            # Without separate PMUs there is one type; with them this should
            # not happen, but a CPU the kernel leaves out is not lost.
            buckets["general" if not buckets else "other"] = leftover

        if len(buckets) == 1 and "general" in buckets:
            # An ARM big.LITTLE is as hybrid as a 12th-gen Intel, but the
            # kernel publishes no PMU per type. It does publish which core each
            # CPU carries, which splits them just the same.
            if split := _arm_cores(tuple(buckets["general"])):
                return split
        return buckets or {"general": list(cpus)}

    @staticmethod
    def _caches_for(cpus: list[int]) -> list[Cache]:
        # Each physical cache shows in every CPU sharing it: deduplicated by
        # the set of CPUs that share it.
        seen: dict[tuple, set[frozenset[int]]] = {}
        for index in cpus:
            cache_dir = pathlib.Path(sysroot.ruta(f"{SYS_CPU}/cpu{index}/cache"))
            if not cache_dir.is_dir():
                continue
            for entry in sorted(cache_dir.glob("index*")):
                level = read_int(f"{entry}/level")
                kind_raw = (read_text(f"{entry}/type") or "").lower()
                size = parse_size(read_text(f"{entry}/size"))
                if level is None or size is None:
                    continue
                shared = frozenset(parse_cpu_list(read_text(f"{entry}/shared_cpu_list")) or (index,))
                key = (
                    level,
                    _CACHE_KINDS.get(kind_raw, kind_raw or "unified"),
                    size,
                    read_int(f"{entry}/ways_of_associativity"),
                    read_int(f"{entry}/coherency_line_size"),
                    read_int(f"{entry}/number_of_sets"),
                )
                seen.setdefault(key, set()).add(shared)

        caches = []
        for (level, kind, size, ways, line, sets), shared_sets in seen.items():
            groups = sorted((tuple(sorted(g)) for g in shared_sets), key=lambda g: g[0])
            caches.append(Cache(
                level=level,
                kind=kind,
                size_bytes=size,
                ways=ways,
                line_bytes=line,
                sets=sets,
                instances=len(groups),
                shared_by=len(groups[0]) if groups else 1,
                instance_cpus=tuple(groups),
            ))
        caches.sort(key=lambda c: (c.level, c.kind))
        return caches

    @staticmethod
    def _microcode(cpu_index: int) -> str | None:
        raw = read_text(f"{SYS_CPU}/cpu{cpu_index}/microcode/version")
        return raw or None

    @staticmethod
    def _static_clocks(cpu_index: int) -> Clocks:
        freq = f"{SYS_CPU}/cpu{cpu_index}/cpufreq"
        khz = lambda name: (lambda v: v * 1000 if v else None)(read_int(f"{freq}/{name}"))
        # Only what really does not change. The effective ceiling and the
        # governor are reread every sample: desktop power profiles change
        # them without notice.
        return Clocks(
            min_hz=khz("cpuinfo_min_freq"),
            base_configured_hz=khz("base_frequency"),
            driver=read_text(f"{freq}/scaling_driver"),
        )


# Where each thread's frequency comes from, most reliable first, as
# Documentation/admin-guide/pm/cpufreq.rst says:
#
# - `cpuinfo_avg_freq`: the mean the hardware measures over a few
#   milliseconds (APERF/MPERF on x86, AMU on ARM). Missing if it cannot be
#   measured; it may fail on a thread long idle (EAGAIN on ARM), and then the
#   next is tried.
# - `scaling_cur_freq`: «in most cases, the last P-state the driver asked
#   for», which may not be what it runs at. On x86 the kernel brings it close
#   to the real one, and there both agree (2 900 688 against 2 900 719 kHz).
#   On AMD, not checked against the other.
# - `cpuinfo_cur_freq`: the hardware's, but almost always readable by root
#   only.
FREQUENCY_SOURCES = ("cpuinfo_avg_freq", "scaling_cur_freq", "cpuinfo_cur_freq")


CPUINFO = "/proc/cpuinfo"


def cpuinfo_mhz() -> dict[int, float]:
    """`cpu MHz` of each processor in /proc/cpuinfo.

    It is there without a frequency driver: on x86 the kernel gives the
    APERF/MPERF measure of a thread that has been running, and the TSC's
    frequency otherwise (`arch_freq_get_on_cpu`).
    """
    found: dict[int, float] = {}
    processor = None
    for line in (read_text(CPUINFO) or "").splitlines():
        key, _sep, value = line.partition(":")
        key = key.strip()
        try:
            if key == "processor":
                processor = int(value)
            elif key == "cpu MHz" and processor is not None:
                found[processor] = float(value)
        except ValueError:
            continue
    return found


class SysfsClocks(Provider):
    """Each logical CPU's current frequency, and the ceiling in force."""

    name = "sysfs-clocks"
    provides = "cpu.clocks.current_hz"

    def available(self) -> bool:
        return os.path.isdir(sysroot.ruta(SYS_CPU))

    def collect(self, draft: Draft) -> None:
        any_read = False
        for index, cpu in draft.logical.items():
            khz = None
            for source_file in FREQUENCY_SOURCES:
                if (khz := read_int(f"{SYS_CPU}/cpu{index}/cpufreq/{source_file}")) is not None:
                    break
            if khz is not None:
                cpu["freq_hz"] = khz * 1000
                any_read = True
        source = "cpufreq" if any_read else None
        # Without a frequency driver /proc/cpuinfo still says it. Not in a
        # virtual machine: there it is the host's clock, not the guest's.
        virtual = any(t.get("in_virtual_machine") for t in draft.types.values())
        if not any_read and not virtual:
            for index, mhz in cpuinfo_mhz().items():
                if index in draft.logical and mhz > 0:
                    draft.logical[index]["freq_hz"] = int(mhz * 1_000_000)
                    source = "cpuinfo"

        for entry in draft.types.values():
            freqs = [draft.logical[i].get("freq_hz") for i in entry.get("cpus", ())]
            average = mean(freqs)
            if average is None:
                continue
            clocks: Clocks = entry.get("clocks") or Clocks()
            leader = entry["cpus"][0]
            ceiling = read_int(f"{SYS_CPU}/cpu{leader}/cpufreq/cpuinfo_max_freq")
            governor = read_text(f"{SYS_CPU}/cpu{leader}/cpufreq/scaling_governor")
            preference = read_text(
                f"{SYS_CPU}/cpu{leader}/cpufreq/energy_performance_preference"
            )
            # `replace` and not field by field: if Clocks gains a field, this
            # does not drop it in silence.
            entry["clocks"] = dataclasses.replace(
                clocks,
                current_hz=int(average),
                current_from=source,
                max_hz=ceiling * 1000 if ceiling else clocks.max_hz,
                governor=governor or clocks.governor,
                energy_preference=preference or clocks.energy_preference,
            )

        # No frequency driver is not «a kernel module is missing»: the firmware
        # may not give the system the frequency states (Cool'n'Quiet off in
        # the BIOS) or the driver may not have loaded, and from here the two
        # look the same. The notice says that much and no more.
        if source == "cpuinfo":
            draft.note("cpu.clocks.driver", Need.HARDWARE,
                       _("prov.cpu.nocpufreq"), _("prov.cpu.nocpufreq.hint"))
        elif source is None:
            # In a virtual machine there is no module to load: the hypervisor
            # exposes no cpufreq because it does not govern the clock.
            if virtual:
                draft.note(
                    "cpu.clocks.current_hz", Need.HARDWARE,
                    _("prov.cpu.nofreq.vm"), _("prov.cpu.nofreq.vm.hint"),
                )
            else:
                draft.note(
                    "cpu.clocks.current_hz", Need.HARDWARE,
                    _("prov.cpu.nofreq"), _("prov.cpu.nocpufreq.hint"),
                )
