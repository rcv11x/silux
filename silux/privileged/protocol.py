"""The contract between the program and its privileged helper.

Both sides share it, and written in one place it can be audited at a
glance: these are *all* the things the privileged process knows how to do.
The helper travels alone (by argv or as an installed copy) and cannot import
this, so it keeps its own copies; the tests keep them equal.
"""

from __future__ import annotations

# The helper's version this program needs: what it can do (its actions and
# registers). A fix that keeps the contract does not raise it; the installed
# copy is compared by content anyway.
HELPER_VERSION = 4

# The actions it accepts. Anything else is refused unread.
ACTION_PING = "ping"
ACTION_SMBIOS = "smbios"
ACTION_MSR = "msr"
ACTION_SMART = "smart"
ACTION_GPU_PMU = "gpu_pmu"
ACTION_IMC = "imc"
ACTION_RAPL = "rapl"
ACTION_LOAD_MODULE = "load_module"
ACTIONS = frozenset({ACTION_PING, ACTION_SMBIOS, ACTION_MSR, ACTION_SMART,
                     ACTION_GPU_PMU, ACTION_IMC, ACTION_RAPL, ACTION_LOAD_MODULE})

# The kernel modules it loads, until the next boot and nothing else: each one
# reads a sensor or a memory module's identification chip.
MODULES_ALLOWED: dict[str, str] = {
    "drivetemp": "SATA disks' temperature",
    "spd5118": "DDR5 SPD chip and its thermometer",
    "ee1004": "DDR4 SPD chip",
    "at24": "DDR3 and older SPD chip",
}

# The SMBIOS table, the only firmware file it opens.
DMI_TABLE = "/sys/firmware/dmi/tables/DMI"

# The disk names it accepts. Strict on purpose: without it, «../../etc/shadow»
# would open anything. Only nvme0, nvme0n1, sda and the like fit.
DISK_NAME = r"^(nvme\d+n\d+|nvme\d+|sd[a-z]{1,2}|hd[a-z])$"

# The MSRs it reads, with what they mean. An arbitrary MSR can expose
# sensitive data or have side effects; these are read-only and documented.
MSR_ALLOWED: dict[int, str] = {
    0x0198: "IA32_PERF_STATUS",          # current voltage and ratio
    0x0199: "IA32_PERF_CTL",             # requested ratio
    0x019C: "IA32_THERM_STATUS",         # margin to the thermal limit
    0x01A2: "MSR_TEMPERATURE_TARGET",    # TjMax
    0x01AD: "MSR_TURBO_RATIO_LIMIT",     # turbo ratios by active cores
    0x00CE: "MSR_PLATFORM_INFO",         # base, minimum and max efficient ratio
    0x0610: "MSR_PKG_POWER_LIMIT",       # PL1 and PL2 as set
    0x0606: "MSR_RAPL_POWER_UNIT",       # units to read the ones above
    0xC0010293: "AMD_MSR_CORE_ENERGY",   # energy per core on AMD
    0xC0010299: "AMD_MSR_RAPL_UNIT",
    0xC0010063: "MSR_PSTATE_STATUS",     # which P-state is active
    0xC0010064: "MSR_PSTATE_0",          # and each one's definition, with
    0xC0010065: "MSR_PSTATE_1",          # the core VID in bits 21:14
    0xC0010066: "MSR_PSTATE_2",
}

# Intel graphics' PMU. It takes no parameters: the helper lists the PMUs and
# events itself and opens only those matching these two patterns; the client
# sends no names or event numbers. Busy counters are totals of the whole
# machine with no sampling: busy nanoseconds and nothing else, no call stacks,
# addresses or any process's activity.
PMU_ROOT = "/sys/bus/event_source/devices"
PMU_GPU = r"^(i915|xe_[0-9a-f]{4}_[0-9a-f]{2}_[0-9a-f]{2}\.[0-9a-f])$"
PMU_EVENT = r"^(rcs|bcs|vcs|vecs|ccs)\d+-busy$"

# The memory controller, by the same two patterns and the same rule: the
# client asks for «the memory controller» and the helper decides what it
# opens. The counters are cumulative totals of the whole machine (cache lines
# to and from RAM), so they say nothing of any process. Intel renames the PMU
# by generation: `uncore_imc` up to Comet Lake and on client Ice Lake and
# Rocket Lake, `uncore_imc_free_running_N` on Tiger Lake, Alder Lake and
# server Ice Lake, and `uncore_imc_N` on servers, whose events are named by
# the DRAM command instead of the direction.
PMU_IMC = r"^uncore_imc(_free_running)?(_\d+)?$"
PMU_IMC_EVENT = r"^(data_reads?|data_writes?|cas_count_read|cas_count_write|ia_requests)$"

# The largest message, in bytes: neither side can make the other allocate
# without limit.
MAX_MESSAGE = 4 * 1024 * 1024
