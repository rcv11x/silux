#!/usr/bin/env python3
"""Silux's privileged helper. It runs as root, and this is all it does.

Written to be read whole in one sitting, since a program running with
privileges has to be auditable. Hence a few decisions:

* **It imports nothing of the program's own**, only the standard library. A
  fault in any other module of the program can't reach here.
* **It doesn't interpret what it reads.** It returns the SMBIOS table's raw
  bytes and lets the unprivileged process parse them. Parsing binary
  formats is where most memory bugs come from, and doing it as root would
  hand the problem over.
* **It takes no paths or commands.** The two paths it opens are written here
  as constants, the MSR registers it allows are a closed list, and disk
  names must fit a pattern that only lets `sda`, `nvme0n1` and the like
  through.
* **From disks it only asks for diagnostics.** The two SMART commands it
  sends are read-only and fixed here; there's no way to ask it for a write
  or an erase, which travel the same road.
* **From the PMU it only counts, never samples.** The events it opens are
  graphics-engine busy and memory-controller traffic counters, aggregated
  over the whole machine and with no sampling period: no sample buffer, no
  call stack, nothing of any particular process. The same as
  `intel_gpu_top` shows. The helper enumerates the names itself; the client
  asks for a family (graphics or memory) and never for a PMU name or an
  event number.
* **Energy and busy counters at most every 100 ms**, whatever the client asks
  (`MIN_READ_INTERVAL_S`).
* **It loads a kernel module only from a closed list of sensor readers**, and
  only for this boot: `modprobe` by its absolute path, with the system's
  blacklist respected. It is the one program it runs, and it writes no file;
  making a module load at every boot is left to the user.

It speaks JSON by lines: one request per input line, one reply per output
line. It ends when its input closes.
"""

from __future__ import annotations

import base64
import ctypes
import fcntl
import json
import os
import re
import struct
import subprocess
import sys
import time

# Bumped when what the helper can do changes: new actions, or new registers
# on the allow list. The client compares it on connecting, because a copy
# installed in /usr/local/libexec stays frozen at the date it was installed
# and nobody updates it.
VERSION = 4

DMI_TABLE = "/sys/firmware/dmi/tables/DMI"
DMI_ENTRY_POINT = "/sys/firmware/dmi/tables/smbios_entry_point"

MAX_TABLE_BYTES = 2 * 1024 * 1024
MAX_REQUEST_BYTES = 64 * 1024

# Disk names allowed. Strict on purpose: without it, a name such as
# «../../dev/mem» would make it open anything.
DISK_NAME = re.compile(r"^(nvme\d+n\d+|nvme\d+|sd[a-z]{1,2}|hd[a-z])$")

# The powercap zones it lets be read. The kernel sets the name and it has no
# paths in it: checked anyway, because what arrives comes from the
# unprivileged process and here we're root.
# A package or psys zone (`intel-rapl:0`) and one level under it: core,
# uncore and dram (`intel-rapl:0:0`). Not the MMIO copy of the package.
RAPL_ZONE = re.compile(r"^[a-z]+-rapl:\d+(:\d+)?\Z")
POWERCAP = "/sys/class/powercap"
SMART_BYTES = 512

# NVMe: the admin ioctl and the health log.
NVME_ADMIN_CMD = 0xC0484E41           # _IOWR('N', 0x41, struct nvme_passthru_cmd)
NVME_GET_LOG_PAGE = 0x02
NVME_LOG_SMART = 0x02

# SATA: SMART READ DATA through ATA PASS-THROUGH.
SG_IO = 0x2285
SG_DXFER_FROM_DEV = -3
ATA_16 = 0x85
ATA_SMART = 0xB0
ATA_SMART_READ_DATA = 0xD0

# Closed list of MSR registers. All read-only and documented in Intel's and
# AMD's manuals; none has side effects when read.
MSR_ALLOWED = frozenset({
    0x0198, 0x0199, 0x019C, 0x01A2, 0x01AD,
    0x00CE, 0x0610, 0x0606,
    0xC0010293, 0xC0010299,
    # The core voltage on AMD: which P-state is active and the definition of
    # the first three, which carry the VID in bits 21:14. On Intel that datum
    # is in 0x198, already listed. Read-only and side-effect free, like the rest.
    0xC0010063,
    0xC0010064, 0xC0010065, 0xC0010066,
})

MAX_CPUS = 4096

# The modules it loads: they read a sensor or a memory module's SPD chip and
# change no setting. No buses, no Super I/O (the wrong one reads garbage).
MODULES_ALLOWED = frozenset({"drivetemp", "spd5118", "ee1004", "at24"})
MODPROBE = ("/usr/sbin/modprobe", "/sbin/modprobe", "/usr/bin/modprobe", "/bin/modprobe")
# What modprobe gets instead of the caller's environment.
MODPROBE_ENV = {"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "LC_ALL": "C"}

# Intel graphics' PMU: per-engine busy, which neither i915 nor xe publish in
# sysfs. The PMU's name and each event's are enumerated in here and filtered
# against these patterns; there's no asking for another.
PMU_ROOT = "/sys/bus/event_source/devices"
PMU_GPU = re.compile(r"^(i915|xe_[0-9a-f]{4}_[0-9a-f]{2}_[0-9a-f]{2}\.[0-9a-f])$")
PMU_EVENT = re.compile(r"^(rcs|bcs|vcs|vecs|ccs)\d+-busy$")

# The integrated graphics' energy plane, which on Intel desktops only shows
# here: /sys/class/powercap publishes package, core, uncore and dram, and none
# of the four is the graphics. This event is allowed and no other of RAPL's
# PMU; the other three are already read through powercap without privileges.
PMU_POWER = "power"
PMU_POWER_EVENT = re.compile(r"^energy-gpu$")

# The memory controller, which publishes how much traffic it moves to RAM.
# Intel renames it by generation and all three must be accepted:
# `uncore_imc` from Sandy Bridge to Comet Lake and still on client Ice Lake
# and Rocket Lake, `uncore_imc_free_running_N` on Tiger Lake, Alder Lake and
# server Ice Lake, and `uncore_imc_N` on servers, which also name their
# events by the DRAM command instead of by the direction. The free-running
# ones write their events in two fields (`event=0xff,umask=0x20`).
#
# `ia_requests` is the same traffic seen by origin (what the cores ask for)
# and is here because it was measured: against 10 GiB read on purpose it
# marked 9.92. Its siblings `gt_requests` and `io_requests` aren't, and not
# for lack of room: the second marks the same figure idle as under load.
PMU_IMC = re.compile(r"^uncore_imc(_free_running)?(_\d+)?$")
PMU_IMC_EVENT = re.compile(
    r"^(data_reads?|data_writes?|cas_count_read|cas_count_write|ia_requests)$")

# The fewest seconds between two reads of the same counters. Read at their own
# update rate, tens of microseconds, energy and busy counters show what other
# processes compute (Platypus, CVE-2020-8694): the kernel closed `energy_uj`
# to users for that. A request that comes sooner waits for the rest: answering
# it with the previous reading would read as 0 W on the client, which times
# energy with its own clock. The window samples every 200 ms at most.
MIN_READ_INTERVAL_S = 0.1
_LAST_READ: dict[str, float] = {}


def _paced(action: str) -> None:
    """Waits until `MIN_READ_INTERVAL_S` have passed since that action's last
    read, whatever the client asked."""
    last = _LAST_READ.get(action)
    if last is not None:
        wait = MIN_READ_INTERVAL_S - (time.monotonic() - last)
        if wait > 0:
            time.sleep(wait)
    _LAST_READ[action] = time.monotonic()


# The two families the client can ask for. They're all that travels over the
# protocol: within each, which PMU and which event is opened is this file's
# decision.
GPU_FAMILY = "gpu"
IMC_FAMILY = "imc"

# How many descriptors are opened at most, per family. The IMC's is higher
# because a server has a PMU per memory channel and all must be opened:
# stopping halfway gives no error, it gives a short, believable figure.
MAX_PMU_FDS = 32
MAX_IMC_FDS = 64

# perf_event_open has no libc wrapper: it's invoked by number, and the number
# depends on the architecture. Where it isn't known, it isn't tried.
PERF_EVENT_OPEN = {"x86_64": 298, "aarch64": 241, "i686": 336, "armv7l": 364}


def _fail(message: str, code: str = "error") -> dict:
    return {"ok": False, "error": code, "message": message}


def read_smbios() -> dict:
    """The SMBIOS table's bytes as they are, and its entry point's."""
    try:
        size = os.path.getsize(DMI_TABLE)
        if size > MAX_TABLE_BYTES:
            return _fail(f"la tabla mide {size} bytes, más de lo razonable", "too_large")
        with open(DMI_TABLE, "rb") as handle:
            table = handle.read(MAX_TABLE_BYTES)
    except FileNotFoundError:
        return _fail("este equipo no expone la tabla SMBIOS", "unsupported")
    except OSError as exc:
        return _fail(f"no se pudo leer la tabla SMBIOS: {exc}", "io")

    entry = b""
    try:
        with open(DMI_ENTRY_POINT, "rb") as handle:
            entry = handle.read(64)
    except OSError:
        pass                                  # the entry point is optional

    return {
        "ok": True,
        "table": base64.b64encode(table).decode("ascii"),
        "entry_point": base64.b64encode(entry).decode("ascii"),
    }


def read_msr(cpu: object, registers: object) -> dict:
    """Read allow-listed registers on a given CPU."""
    if not isinstance(cpu, int) or not 0 <= cpu < MAX_CPUS:
        return _fail("número de CPU no válido", "bad_request")
    if not isinstance(registers, list) or not registers:
        return _fail("hacen falta registros que leer", "bad_request")

    rejected = [r for r in registers
                if not isinstance(r, int) or r not in MSR_ALLOWED]
    if rejected:
        return _fail(f"registros no permitidos: {rejected}", "forbidden")

    path = f"/dev/cpu/{cpu}/msr"
    try:
        descriptor = os.open(path, os.O_RDONLY)
    except FileNotFoundError:
        return _fail("falta /dev/cpu/N/msr; hay que cargar el módulo «msr»", "no_module")
    except OSError as exc:
        return _fail(f"no se pudo abrir {path}: {exc}", "io")

    values: dict[str, int] = {}
    try:
        for register in registers:
            try:
                raw = os.pread(descriptor, 8, register)
            except OSError:
                continue                      # that MSR doesn't exist on this CPU
            if len(raw) == 8:
                values[str(register)] = struct.unpack("<Q", raw)[0]
    finally:
        os.close(descriptor)

    return {"ok": True, "cpu": cpu, "values": values}


def read_smart(name) -> dict:
    """A disk's 512-byte health log, without interpreting it.

    The two commands sent (`Get Log Page` on NVMe and `SMART READ DATA` on
    SATA) are diagnostic and read-only. Interpreting what they return is the
    unprivileged process's job: here only bytes are read.
    """
    if not isinstance(name, str) or not DISK_NAME.match(name):
        return _fail(f"nombre de disco no admitido: {name!r}", "bad_request")

    path = f"/dev/{name}"
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
    except OSError as error:
        return _fail(f"no se pudo abrir {path}: {error.strerror}", "io_error")

    try:
        if name.startswith("nvme"):
            data, kind = _smart_nvme(descriptor), "nvme"
        else:
            data, kind = _smart_ata(descriptor), "ata"
    except OSError as error:
        return _fail(f"el disco no respondió al diagnóstico: {error.strerror}",
                     "io_error")
    finally:
        os.close(descriptor)

    if data is None:
        return _fail("el disco no devolvió datos de diagnóstico", "io_error")
    return {"ok": True, "device": name, "kind": kind,
            "data": base64.b64encode(data).decode("ascii")}


def _smart_nvme(descriptor: int):
    """`Get Log Page` of log 0x02, the health one."""
    buffer = ctypes.create_string_buffer(SMART_BYTES)
    # struct nvme_passthru_cmd, 72 bytes. The number of dwords goes minus
    # one, as the specification says.
    numd = SMART_BYTES // 4 - 1
    request = bytearray(struct.pack(
        "<BBHIIIQQIIIIIIIIII",
        NVME_GET_LOG_PAGE, 0, 0,          # opcode, flags, reserved
        0xFFFFFFFF,                       # nsid: the whole controller
        0, 0,                             # cdw2, cdw3
        0,                                # metadata
        ctypes.addressof(buffer),         # addr
        0, SMART_BYTES,                   # metadata_len, data_len
        NVME_LOG_SMART | (numd << 16),    # cdw10
        0, 0, 0, 0, 0,                    # cdw11 to cdw15
        5000, 0,                          # timeout_ms, result
    ))
    fcntl.ioctl(descriptor, NVME_ADMIN_CMD, request)
    return buffer.raw


class _SgIoHdr(ctypes.Structure):
    """`struct sg_io_hdr`, the SCSI subsystem's generic request.

    Declared with ctypes rather than `struct.pack` because it mixes pointers
    with short integers, and the compiler inserts padding to align them.
    With a hand-packed format the fields land shifted and the kernel reads
    garbage where it expects a pointer.
    """

    _fields_ = [
        ("interface_id", ctypes.c_int),
        ("dxfer_direction", ctypes.c_int),
        ("cmd_len", ctypes.c_ubyte),
        ("mx_sb_len", ctypes.c_ubyte),
        ("iovec_count", ctypes.c_ushort),
        ("dxfer_len", ctypes.c_uint),
        ("dxferp", ctypes.c_void_p),
        ("cmdp", ctypes.c_void_p),
        ("sbp", ctypes.c_void_p),
        ("timeout", ctypes.c_uint),
        ("flags", ctypes.c_uint),
        ("pack_id", ctypes.c_int),
        ("usr_ptr", ctypes.c_void_p),
        ("status", ctypes.c_ubyte),
        ("masked_status", ctypes.c_ubyte),
        ("msg_status", ctypes.c_ubyte),
        ("sb_len_wr", ctypes.c_ubyte),
        ("host_status", ctypes.c_ushort),
        ("driver_status", ctypes.c_ushort),
        ("resid", ctypes.c_int),
        ("duration", ctypes.c_uint),
        ("info", ctypes.c_uint),
    ]


def _smart_ata(descriptor: int):
    """`SMART READ DATA` through ATA PASS-THROUGH, as SATA asks for it."""
    command = bytes((
        ATA_16,
        0x08,                     # protocol 4: PIO data in
        0x0E,                     # direction from the disk, count in sectors
        0x00, ATA_SMART_READ_DATA,
        0x00, 0x01,               # one sector
        0x00, 0x00,
        0x00, 0x4F,               # the signature SMART requires in LBA mid
        0x00, 0xC2,               # and in LBA high
        0x00, ATA_SMART, 0x00,
    ))
    buffer = ctypes.create_string_buffer(SMART_BYTES)
    direction = ctypes.create_string_buffer(32)
    cmd = ctypes.create_string_buffer(command, len(command))

    header = _SgIoHdr(
        interface_id=ord("S"),
        dxfer_direction=SG_DXFER_FROM_DEV,
        cmd_len=len(command),
        mx_sb_len=len(direction),
        dxfer_len=SMART_BYTES,
        dxferp=ctypes.cast(buffer, ctypes.c_void_p),
        cmdp=ctypes.cast(cmd, ctypes.c_void_p),
        sbp=ctypes.cast(direction, ctypes.c_void_p),
        timeout=5000,
    )
    fcntl.ioctl(descriptor, SG_IO, header)
    if header.status not in (0, 2):      # 2 is «with sense data»
        return None
    return buffer.raw


class _PerfEventAttr(ctypes.Structure):
    """`struct perf_event_attr`, exactly as the kernel expects it.

    Declared whole although only four fields are used: the kernel checks the
    `size` field against the versions it knows, so a piece won't do.
    Everything else is zero, which is exactly the point: a zero
    `sample_period` means the event **counts** and doesn't sample, so there's
    no buffer, no addresses, no one's registers.
    """

    _fields_ = [
        ("type", ctypes.c_uint32), ("size", ctypes.c_uint32),
        ("config", ctypes.c_uint64), ("sample_period", ctypes.c_uint64),
        ("sample_type", ctypes.c_uint64), ("read_format", ctypes.c_uint64),
        ("flags", ctypes.c_uint64), ("wakeup_events", ctypes.c_uint32),
        ("bp_type", ctypes.c_uint32), ("config1", ctypes.c_uint64),
        ("config2", ctypes.c_uint64), ("branch_sample_type", ctypes.c_uint64),
        ("sample_regs_user", ctypes.c_uint64),
        ("sample_stack_user", ctypes.c_uint32), ("clockid", ctypes.c_int32),
        ("sample_regs_intr", ctypes.c_uint64), ("aux_watermark", ctypes.c_uint32),
        ("sample_max_stack", ctypes.c_uint16), ("__reserved_2", ctypes.c_uint16),
        ("aux_sample_size", ctypes.c_uint32), ("__reserved_3", ctypes.c_uint32),
    ]


# Open PMU descriptors, by family, PMU and event. Opened once and kept alive:
# the counters accumulate from when they're opened, so closing and reopening
# them between samples would lose the reference.
_PMU_FDS: dict[str, dict[str, dict[str, int]]] = {}
_PMU_FAILURE: dict[str, str] = {}
# Whether the descriptor cap left events unopened. Only matters for the IMC,
# where counters are added across channels and missing one lowers the total.
_PMU_TRUNCATED: dict[str, bool] = {}


def _pmu_allowed(family: str, pmu: str):
    """Which events may be opened on that PMU, or None if not of the family.

    Here is the whole list of what this helper can count. The client asks for
    a family and nothing more: neither the PMU's name nor the event number
    ever come from outside.
    """
    if family == GPU_FAMILY:
        if PMU_GPU.match(pmu):
            return PMU_EVENT
        if pmu == PMU_POWER:
            return PMU_POWER_EVENT
    elif family == IMC_FAMILY:
        if PMU_IMC.match(pmu):
            return PMU_IMC_EVENT
    return None


def _pmu_bits(pmu: str, field: str):
    """The bits of `config` a field takes, (first, last), per the kernel.

    Each PMU publishes its format: «config:0-7» means the field is the low
    eight bits. i915 calls it `i915_eventid` and RAPL `event`, which is why
    it's looked up instead of assumed. A field split in two ranges, or in
    another register than `config`, isn't taken.
    """
    if field == "config":
        return 0, 63
    try:
        with open(f"{PMU_ROOT}/{pmu}/format/{field}", encoding="ascii") as handle:
            raw = handle.read(32).strip()
    except OSError:
        return None
    if not raw.startswith("config:") or "," in raw:
        return None
    first, _sep, last = raw[len("config:"):].partition("-")
    try:
        first_bit = int(first)
        last_bit = int(last) if last else first_bit
    except ValueError:
        return None
    return (first_bit, last_bit) if 0 <= first_bit <= last_bit <= 63 else None


def _pmu_field(pmu: str, field: str):
    """In which bit of `config` a field starts."""
    bits = _pmu_bits(pmu, field)
    return bits[0] if bits else None


def _pmu_config(pmu: str, event: str):
    """The event number the kernel publishes, read from its own sysfs.

    The client sends names, never numbers: what turns a name on the list
    into a `config` is this kernel file. Its content is «config=0x2000» on
    i915, «event=0x04» on RAPL and «event=0xff,umask=0x20» on a memory
    controller's free-running counters: each field goes in the bits the
    PMU's format says, as perf places them. A field the format doesn't
    declare, a value wider than its bits, or a parameter perf asks the user
    for («?»), and the event isn't opened.
    """
    try:
        with open(f"{PMU_ROOT}/{pmu}/events/{event}", encoding="ascii") as handle:
            raw = handle.read(64).strip()
    except OSError:
        return None
    if not raw:
        return None
    config = 0
    for part in raw.split(","):
        field, sep, value = part.partition("=")
        bits = _pmu_bits(pmu, field.strip()) if sep else None
        if bits is None:
            return None
        try:
            number = int(value.strip(), 0)
        except ValueError:
            return None
        first, last = bits
        if not 0 <= number < 1 << (last - first + 1):
            return None
        config |= number << first
    return config


def _open_pmu(family: str) -> None:
    """Open the counters of that family this machine publishes."""
    cap = MAX_IMC_FDS if family == IMC_FAMILY else MAX_PMU_FDS
    empty = ("no hay ningún controlador de memoria con contadores"
             if family == IMC_FAMILY
             else "no hay ninguna gráfica con contadores de ocupación")
    # There are, and this helper doesn't know how to ask for them: not «none».
    unknown = "este ayudante no sabe abrir los contadores que hay"
    unread = 0
    fds: dict[str, dict[str, int]] = {}
    failure = ""

    number = PERF_EVENT_OPEN.get(os.uname().machine)
    if number is None:
        _PMU_FAILURE[family] = f"perf_event_open no está mapeado en {os.uname().machine}"
        return
    try:
        names = sorted(os.listdir(PMU_ROOT))
    except OSError:
        _PMU_FAILURE[family] = "este kernel no publica ningún PMU"
        return

    libc = ctypes.CDLL(None, use_errno=True)
    opened = 0
    truncated = False
    for pmu in names:
        pattern = _pmu_allowed(family, pmu)
        if pattern is None:
            continue
        try:
            with open(f"{PMU_ROOT}/{pmu}/type", encoding="ascii") as handle:
                pmu_type = int(handle.read(16).strip())
            events = sorted(os.listdir(f"{PMU_ROOT}/{pmu}/events"))
        except (OSError, ValueError):
            continue

        for event in events:
            if not pattern.match(event):
                continue
            if opened >= cap:
                # Stopping halfway on the IMC gives no error, it gives a short
                # sum: it's flagged so nobody publishes that figure.
                truncated = True
                continue
            config = _pmu_config(pmu, event)
            if config is None:
                unread += 1
                continue
            attr = _PerfEventAttr()
            attr.type = pmu_type
            attr.size = ctypes.sizeof(_PerfEventAttr)
            attr.config = config
            # pid=-1 and cpu=0: a device PMU, not a per-core one, counting what
            # the whole machine does. It's tied to no process.
            descriptor = libc.syscall(number, ctypes.byref(attr), -1, 0, -1, 0)
            if descriptor < 0:
                if not failure:
                    failure = os.strerror(ctypes.get_errno())
                continue
            fds.setdefault(pmu, {})[event] = descriptor
            opened += 1

    if fds:
        _PMU_FDS[family] = fds
        _PMU_TRUNCATED[family] = truncated
    if not fds and not failure:
        failure = unknown if unread else empty
    if failure:
        _PMU_FAILURE[family] = failure


def _pmu_scale(pmu: str, event: str):
    """The factor the kernel publishes to turn the counter into its unit.

    Only energy counters carry one. Returning it passes a kernel datum as
    is; interpreting it is the unprivileged process's business.
    """
    try:
        with open(f"{PMU_ROOT}/{pmu}/events/{event}.scale", encoding="ascii") as h:
            return float(h.read(64).strip())
    except (OSError, ValueError):
        return None


def _pmu_unit(pmu: str, event: str):
    """The unit the kernel publishes for a counter, if any.

    It goes with the scale and for the same reason: a kernel datum passed
    as is. That the memory controller's counter counts MiB and nothing else
    is checked by the unprivileged process, which turns it into bytes per
    second.
    """
    try:
        with open(f"{PMU_ROOT}/{pmu}/events/{event}.unit", encoding="ascii") as h:
            return h.read(32).strip()
    except OSError:
        return None


def _read_family(family: str, with_unit: bool = False) -> dict:
    """Read every open counter of a family at once.

    Eight bytes per descriptor and nothing more. Subtracting against the
    previous round and converting to percentages, watts or bytes per second
    is the unprivileged process's business: no figure is interpreted here.

    The unit is only looked up where it's needed. The graphics' don't use
    it, and asking would be eight sysfs opens a second, as root, to throw
    away what was read.
    """
    counters: dict[str, dict[str, int]] = {}
    scales: dict[str, dict[str, float]] = {}
    units: dict[str, dict[str, str]] = {}
    for pmu, events in _PMU_FDS.get(family, {}).items():
        for event, descriptor in events.items():
            try:
                # os.read and not os.pread: a perf descriptor isn't seekable
                # and pread would return ESPIPE.
                raw = os.read(descriptor, 8)
            except OSError:
                continue
            if len(raw) != 8:
                continue
            counters.setdefault(pmu, {})[event] = struct.unpack("<Q", raw)[0]
            scale = _pmu_scale(pmu, event)
            if scale is not None:
                scales.setdefault(pmu, {})[event] = scale
            unit = _pmu_unit(pmu, event) if with_unit else None
            if unit:
                units.setdefault(pmu, {})[event] = unit
    return {"counters": counters, "scales": scales, "units": units}


def read_gpu_pmu() -> dict:
    """The per-engine busy counters, raw and with their clock.

    It returns nanoseconds accumulated since each counter was opened.
    Subtracting them and turning them into a percentage is the unprivileged
    process's job; here only eight bytes per descriptor are read.
    """
    _paced("gpu_pmu")
    if GPU_FAMILY not in _PMU_FDS:
        _open_pmu(GPU_FAMILY)
    if GPU_FAMILY not in _PMU_FDS:
        return _fail("no se pudo leer el PMU de la gráfica: "
                     f"{_PMU_FAILURE.get(GPU_FAMILY, '')}", "unsupported")

    reading = _read_family(GPU_FAMILY)
    if not reading["counters"]:
        return _fail("los contadores dejaron de responder", "io")
    return {"ok": True, "monotonic_ns": time.monotonic_ns(),
            "engines": reading["counters"], "scales": reading["scales"]}


def read_imc() -> dict:
    """How much traffic the memory controller moves, raw.

    Each count is a cache line moved between the controller and RAM since
    the counter was opened; how many bytes that is, the scale the kernel
    publishes says, which is why it travels alongside. The same
    `intel_gpu_top` shows next to the graphics, though the datum isn't the
    graphics': it's the whole controller, the processor's traffic included.
    """
    _paced("imc")
    if IMC_FAMILY not in _PMU_FDS:
        _open_pmu(IMC_FAMILY)
    if IMC_FAMILY not in _PMU_FDS:
        return _fail("no se pudo leer el PMU del controlador de memoria: "
                     f"{_PMU_FAILURE.get(IMC_FAMILY, '')}", "unsupported")

    reading = _read_family(IMC_FAMILY, with_unit=True)
    if not reading["counters"]:
        return _fail("los contadores dejaron de responder", "io")
    return {"ok": True, "monotonic_ns": time.monotonic_ns(),
            "counters": reading["counters"], "scales": reading["scales"],
            "units": reading["units"],
            "truncated": _PMU_TRUNCATED.get(IMC_FAMILY, False)}


def read_rapl() -> dict:
    """The processor's energy counters, in microjoules.

    Since kernel 5.10 `energy_uj` can't be read without privileges: it was
    restricted because sampling it at high rate reveals another process's
    power pattern. Reading it once a second, as this window does, is what
    `powertop` or `s-tui` do.

    Without this, on machines where the kernel restricts it (AMD above all)
    the processor power's «needs permissions» notice never went away: the
    user gave permissions, the helper started, and nobody read this.

    The raw microjoules are returned. Watts are their derivative, computed by
    the unprivileged process, which keeps the previous reading.
    """
    _paced("rapl")
    zones = {}
    try:
        names = sorted(os.listdir(POWERCAP))
    except OSError as error:
        return _fail(f"no se pudo leer {POWERCAP}: {error.strerror}", "io_error")

    for name in names:
        if not RAPL_ZONE.match(name):
            continue
        try:
            with open(f"{POWERCAP}/{name}/energy_uj", encoding="ascii") as fh:
                zones[name] = int(fh.read().strip())
        except (OSError, ValueError):
            continue
    if not zones:
        return _fail("ninguna zona de powercap respondió", "io_error")
    return {"ok": True, "zones": zones}


def load_module(name: object) -> dict:
    """Load one allow-listed module until the next boot."""
    if not isinstance(name, str) or name not in MODULES_ALLOWED:
        return _fail(f"módulo no permitido: {name!r}", "forbidden")
    if os.path.isdir(f"/sys/module/{name}"):
        return {"ok": True, "module": name}
    modprobe = next((path for path in MODPROBE
                     if os.path.isfile(path) and os.access(path, os.X_OK)), None)
    if modprobe is None:
        return _fail("no se encuentra modprobe", "unsupported")
    try:
        # No shell and a fixed argument list; `-b` keeps a module the system
        # blacklisted out, as it would be at boot.
        result = subprocess.run([modprobe, "-b", "--", name], env=MODPROBE_ENV,
                                stdin=subprocess.DEVNULL, capture_output=True,
                                text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return _fail(f"modprobe {name}: {exc}", "io")
    if result.returncode != 0:
        said = (result.stderr or "").strip().splitlines()
        return _fail(said[-1] if said else f"modprobe {name} falló", "io")
    # A blacklisted module makes modprobe -b succeed without loading anything.
    if not os.path.isdir(f"/sys/module/{name}"):
        return _fail(f"{name} no se cargó; puede estar en la lista negra del sistema",
                     "blacklisted")
    return {"ok": True, "module": name}


def handle(request: dict) -> dict:
    action = request.get("action")
    if action == "ping":
        return {"ok": True, "version": VERSION, "uid": os.geteuid()}
    if action == "smbios":
        return read_smbios()
    if action == "msr":
        return read_msr(request.get("cpu"), request.get("registers"))
    if action == "smart":
        return read_smart(request.get("device"))
    if action == "gpu_pmu":
        return read_gpu_pmu()
    if action == "imc":
        return read_imc()
    if action == "rapl":
        return read_rapl()
    if action == "load_module":
        return load_module(request.get("module"))
    return _fail(f"acción desconocida: {action!r}", "bad_request")


def requests(stream, limit: int = MAX_REQUEST_BYTES):
    """Each request line as bytes, or None for one over the limit.

    Read with a cap, as root: a line with no end is never held whole. What
    is left of a long line is read and dropped up to its end.
    """
    while True:
        line = stream.readline(limit + 1)
        if not line:
            return
        if len(line) > limit:
            while not line.endswith(b"\n"):
                line = stream.readline(limit)
                if not line:
                    break
            yield None
            continue
        yield line


def main() -> int:
    if os.geteuid() != 0:
        print(json.dumps(_fail("el ayudante tiene que ejecutarse como root", "not_root")),
              flush=True)
        return 1

    for raw in requests(sys.stdin.buffer):
        if raw is None:
            print(json.dumps(_fail("petición demasiado larga", "bad_request")), flush=True)
            continue
        line = raw.decode("utf-8", errors="replace").strip()
        if not line:
            continue
        try:
            request = json.loads(line)
        except ValueError:
            response = _fail("la petición no es JSON válido", "bad_request")
        else:
            response = handle(request) if isinstance(request, dict) else \
                _fail("la petición tiene que ser un objeto", "bad_request")
        print(json.dumps(response), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
