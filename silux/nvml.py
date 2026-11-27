"""NVIDIA's proprietary driver, which publishes nothing in sysfs.

A Radeon tells its life in `/sys/class/drm`; a GeForce on NVIDIA's driver
doesn't. There's only the bare PCI node: no memory, no clocks, no
temperature. All of that is behind NVML, the library the driver ships and
that `nvidia-smi` uses inside.

Loaded with `ctypes` like the program's other libraries. NVML has kept the
same ABI for over a decade and versions the symbols it changes (hence the
`_v2` and `_v3` suffixes), so the versioned ones are asked for first, with
the old ones as the fallback for old drivers. What each call needs from
which driver: docs/nvml.md.
"""

from __future__ import annotations

import ctypes
from dataclasses import dataclass
from typing import Optional

from .model import PLAUSIBLE

LIBRARIES = ("libnvidia-ml.so.1", "libnvidia-ml.so")

NVML_SUCCESS = 0
NVML_ERROR_NOT_SUPPORTED = 3
NVML_ERROR_INSUFFICIENT_SIZE = 7
# nvmlReturn_t, as nvml.h names them: what the report says NVML answered.
NVML_ERRORS = {1: "UNINITIALIZED", 2: "INVALID_ARGUMENT", 3: "NOT_SUPPORTED",
               4: "NO_PERMISSION", 6: "NOT_FOUND", 7: "INSUFFICIENT_SIZE",
               9: "DRIVER_NOT_LOADED", 10: "TIMEOUT",
               13: "FUNCTION_NOT_FOUND", 15: "GPU_IS_LOST", 17: "OPERATING_SYSTEM",
               18: "LIB_RM_VERSION_MISMATCH", 21: "NO_DATA", 25: "ARGUMENT_VERSION_MISMATCH",
               26: "DEPRECATED", 999: "UNKNOWN"}


def nvml_error(code: int) -> str:
    name = NVML_ERRORS.get(code)
    return f"NVML_ERROR_{name} ({code})" if name else f"NVML return {code}"

GPU_TEMPERATURE = 0
# The clocks of interest, by their enumeration: graphics, SM, memory, video.
CLOCK_GRAPHICS, CLOCK_SM, CLOCK_MEMORY, CLOCK_VIDEO = 0, 1, 2, 3
NAME_LENGTH = 96

# Why the card cuts its clocks, as `nvmlClocksThrottleReasons` defines them.
# Keys: the text is chosen when painting.
THROTTLE_REASONS = {
    0x0000000000000001: "gpu.throttle.nv.idle",
    0x0000000000000002: "gpu.throttle.nv.appclocks",
    0x0000000000000004: "gpu.throttle.nv.swpower",
    0x0000000000000008: "gpu.throttle.nv.hwslowdown",
    0x0000000000000010: "gpu.throttle.nv.sync",
    0x0000000000000020: "gpu.throttle.nv.swthermal",
    0x0000000000000040: "gpu.throttle.nv.hwthermal",
    0x0000000000000080: "gpu.throttle.nv.hwpower",
    0x0000000000000100: "gpu.throttle.nv.display",
}
# Not a reason: the answer when there is none.
NO_REASON = 0x0000000000000001


# The GPU's power as a field value (nvml.h, NVML 13.4.92): the average over
# a second (Ampere and newer, but GA100) and the current one (every
# architecture). nvmlDeviceGetPowerUsage only answers where «power management
# mode» is supported, and the header points to these two for the rest: some
# cards on driver 595 gave their temperature, clocks and limit, and no power.
# Milliwatts, like nvmlDeviceGetPowerUsage and the limits of the same block;
# for these two the header doesn't say.
FIELD_POWER_AVERAGE, FIELD_POWER_INSTANT = 185, 186


class _Value(ctypes.Union):
    """nvmlValue_t, its members in the header's order."""
    _fields_ = [("dVal", ctypes.c_double), ("siVal", ctypes.c_int), ("uiVal", ctypes.c_uint),
                ("ulVal", ctypes.c_ulong), ("ullVal", ctypes.c_ulonglong),
                ("sllVal", ctypes.c_longlong), ("usVal", ctypes.c_ushort)]


class _Field(ctypes.Structure):
    """nvmlFieldValue_t."""
    _fields_ = [("fieldId", ctypes.c_uint), ("scopeId", ctypes.c_uint),
                ("timestamp", ctypes.c_longlong), ("latencyUsec", ctypes.c_longlong),
                ("valueType", ctypes.c_uint), ("nvmlReturn", ctypes.c_uint),
                ("value", _Value)]


# nvmlValueType_t: which member of the union holds the value.
MEMBER_BY_TYPE = {0: "dVal", 1: "uiVal", 2: "ulVal", 3: "ullVal", 4: "sllVal",
                    5: "siVal", 6: "usVal"}


# nvmlDeviceArchitecture_t (nvml.h). The driver's power estimate on a card
# with no sensor is documented from Ada on (an RTX 4060); before it, what the
# samples buffer holds on such a card is no known figure.
ARCH_ADA = 8
ARCH_UNKNOWN = 0xFFFFFFFF


def estimates_power(architecture: Optional[int]) -> bool:
    """Whether the driver estimates the power of a card of this architecture
    that has no sensor."""
    return architecture is not None and ARCH_ADA <= architecture < ARCH_UNKNOWN


# nvmlSamplingType_t: the board's power, which the driver's power monitor
# samples into a ring buffer (nvidia-smi's «Power Samples»). On a card with
# no power sensor those samples are the driver's estimate, not a measurement.
TOTAL_POWER_SAMPLES = 0


class _Sample(ctypes.Structure):
    """nvmlSample_t: the CPU timestamp in microseconds, and the value."""
    _fields_ = [("timeStamp", ctypes.c_ulonglong), ("sampleValue", _Value)]


# A power reading above this many times the highest limit the card declares
# is impossible: a card at full load sits on its limit and passes it by a
# little (an RTX 3060's maximum is its factory 170 W), and the impossible
# ones seen are 4 to 16 times over.
IMPOSSIBLE_OVER_LIMIT = 1.5


class _Temperature(ctypes.Structure):
    """nvmlTemperature_v1_t, for nvmlDeviceGetTemperatureV (R570 and newer)."""
    _fields_ = [("version", ctypes.c_uint), ("sensorType", ctypes.c_uint),
                ("temperature", ctypes.c_int)]


# NVML_STRUCT_VERSION: the structure's size, and its version in the top byte.
TEMPERATURE_V1 = ctypes.sizeof(_Temperature) | 1 << 24


class _Memory(ctypes.Structure):
    _fields_ = [("total", ctypes.c_ulonglong), ("free", ctypes.c_ulonglong),
                ("used", ctypes.c_ulonglong)]


class _Utilization(ctypes.Structure):
    _fields_ = [("gpu", ctypes.c_uint), ("memory", ctypes.c_uint)]


class _Pci(ctypes.Structure):
    """`nvmlPciInfo_t` version 3, the one `GetPciInfo_v3` returns."""

    _fields_ = [
        ("busIdLegacy", ctypes.c_char * 16),
        ("domain", ctypes.c_uint), ("bus", ctypes.c_uint), ("device", ctypes.c_uint),
        ("pciDeviceId", ctypes.c_uint), ("pciSubSystemId", ctypes.c_uint),
        ("busId", ctypes.c_char * 32),
    ]


@dataclass(frozen=True, slots=True)
class NvidiaGpu:
    """What NVML says about a card."""

    index: int = 0
    pci_slot: Optional[str] = None
    name: Optional[str] = None
    vbios: Optional[str] = None
    driver_version: Optional[str] = None
    serial: Optional[str] = None
    uuid: Optional[str] = None
    cuda_cores: Optional[int] = None
    memory_total_bytes: Optional[int] = None
    memory_used_bytes: Optional[int] = None
    memory_bus_bits: Optional[int] = None
    busy_percent: Optional[float] = None
    memory_busy_percent: Optional[float] = None
    encode_busy_percent: Optional[float] = None
    decode_busy_percent: Optional[float] = None
    temp_c: Optional[float] = None
    power_w: Optional[float] = None
    # Which call gave it, for the dumps: two cards can show the same watts
    # from different calls.
    power_source: Optional[str] = None
    # False when nvmlDeviceGetPowerUsage answers NOT_SUPPORTED, which nvml.h
    # gives for a device that «does not support power readings».
    power_sensor: Optional[bool] = None
    # NVML_DEVICE_ARCH_*: whether the driver estimates what it can't read.
    architecture: Optional[int] = None
    # The performance state, 0 to 15 (nvidia-smi's «P8»).
    performance_state: Optional[int] = None
    # Without power: what NVML answered to each way of asking, for the report.
    power_error: Optional[str] = None
    # The driver's estimate where it measures none: the mean of its power
    # samples since the previous reading. Never `power_w` (docs/nvml.md).
    power_estimate_w: Optional[float] = None
    power_estimate_window_s: Optional[float] = None
    power_estimate_samples: Optional[int] = None
    # A reading thrown away as impossible (`power_ceiling_w`), and its way.
    power_discarded_w: Optional[float] = None
    power_discarded_source: Optional[str] = None
    # (way, answer) for each way of reading the power, the energy counter
    # included: only for the report.
    power_answers: tuple[tuple[str, str], ...] = ()
    # Compute processes running on the card. Only to decide whether Silux
    # keeps reading it; never shown.
    compute_processes: Optional[int] = None
    power_cap_w: Optional[float] = None
    power_cap_default_w: Optional[float] = None
    power_cap_min_w: Optional[float] = None
    power_cap_max_w: Optional[float] = None
    fan_percent: Optional[float] = None
    core_hz: Optional[int] = None
    core_max_hz: Optional[int] = None
    memory_hz: Optional[int] = None
    memory_max_hz: Optional[int] = None
    video_hz: Optional[int] = None
    link_generation: Optional[int] = None
    link_width: Optional[int] = None
    max_link_generation: Optional[int] = None
    max_link_width: Optional[int] = None
    throttled: Optional[bool] = None
    throttle_reasons: tuple[str, ...] = ()


class Nvml:
    """An open NVML session. It must be closed, hence an object.

    NVML asks to be initialized once and shut down at the end. Opening and
    closing it every sample costs far more than keeping it open, so the
    provider keeps it for as long as the program lives.
    """

    def __init__(self) -> None:
        self._lib: Optional[ctypes.CDLL] = None
        self._active = False
        # The newest power sample already averaged, per card: each estimate
        # covers only what the driver sampled since the previous reading.
        self._last_power_sample: dict[int, int] = {}

    # -- lifecycle ----------------------------------------------------------

    def open(self) -> bool:
        if self._active:
            return True
        for name in LIBRARIES:
            try:
                self._lib = ctypes.CDLL(name)
                break
            except OSError:
                continue
        if self._lib is None:
            return False
        init = self._symbol("nvmlInit_v2", "nvmlInit")
        if init is None or init() != NVML_SUCCESS:
            self._lib = None
            return False
        self._active = True
        return True

    def close(self) -> None:
        if self._active and self._lib is not None:
            shutdown = self._symbol("nvmlShutdown")
            if shutdown is not None:
                shutdown()
        self._active = False
        self._lib = None
        self._last_power_sample.clear()

    @property
    def is_open(self) -> bool:
        return self._active

    # -- queries ------------------------------------------------------------

    def devices(self) -> list[NvidiaGpu]:
        if not self._active or self._lib is None:
            return []
        get_count = self._symbol("nvmlDeviceGetCount_v2", "nvmlDeviceGetCount")
        get_handle = self._symbol("nvmlDeviceGetHandleByIndex_v2", "nvmlDeviceGetHandleByIndex")
        if get_count is None or get_handle is None:
            return []

        count = ctypes.c_uint()
        if get_count(ctypes.byref(count)) != NVML_SUCCESS:
            return []

        version = self._global_string("nvmlSystemGetDriverVersion", 80)
        found = []
        for index in range(count.value):
            handle = ctypes.c_void_p()
            if get_handle(ctypes.c_uint(index), ctypes.byref(handle)) != NVML_SUCCESS:
                continue
            found.append(self._read(index, handle, version))
        return found

    # -- internals ----------------------------------------------------------

    def _symbol(self, *names: str):
        """The first of these symbols that exists. NVML versions those it changes."""
        for name in names:
            symbol = getattr(self._lib, name, None)
            if symbol is not None:
                return symbol
        return None

    def _integer(self, name: str, handle, *extra, kind=ctypes.c_uint,
                reasons: Optional[list] = None) -> Optional[int]:
        """The value, or None; `reasons` collects why not."""
        function = self._symbol(name)
        if function is None:
            if reasons is not None:
                reasons.append(f"{name}: not in the library")
            return None
        value = kind()
        call_args = (handle, *extra, ctypes.byref(value))
        try:
            code = function(*call_args)
        except (ctypes.ArgumentError, OSError) as exc:
            if reasons is not None:
                reasons.append(f"{name}: {exc}")
            return None
        if code != NVML_SUCCESS:
            if reasons is not None:
                reasons.append(f"{name}: {nvml_error(code)}")
            return None
        return value.value

    def _utilization(self, name: str, handle) -> Optional[float]:
        """NVENC's or NVDEC's usage, in %.

        `nvmlDeviceGet{Encoder,Decoder}Utilization` write two integers, the
        usage and the period it was measured over: with a single pointer, as
        in `_integer`, the library would write the second into nobody's
        memory.
        """
        function = self._symbol(name)
        if function is None:
            return None
        usage, period_us = ctypes.c_uint(), ctypes.c_uint()
        try:
            if function(handle, ctypes.byref(usage), ctypes.byref(period_us)) != NVML_SUCCESS:
                return None
        except (ctypes.ArgumentError, OSError):
            return None
        return float(usage.value)

    def _string(self, name: str, handle, length: int = NAME_LENGTH) -> Optional[str]:
        function = self._symbol(name)
        if function is None:
            return None
        buffer = ctypes.create_string_buffer(length)
        try:
            if function(handle, buffer, ctypes.c_uint(length)) != NVML_SUCCESS:
                return None
        except (ctypes.ArgumentError, OSError):
            return None
        return buffer.value.decode("utf-8", "replace").strip() or None

    def _global_string(self, name: str, length: int) -> Optional[str]:
        function = self._symbol(name)
        if function is None:
            return None
        buffer = ctypes.create_string_buffer(length)
        if function(buffer, ctypes.c_uint(length)) != NVML_SUCCESS:
            return None
        return buffer.value.decode("utf-8", "replace").strip() or None

    def _fields(self, handle, *ids: int, reasons: Optional[list] = None) -> dict[int, float]:
        """Field values that came back, by id. Each one carries its own
        return code and value type: one that fails does not spoil the rest.
        `reasons` collects why each missing one is missing."""
        reasons = reasons if reasons is not None else []
        function = self._symbol("nvmlDeviceGetFieldValues")
        if function is None:
            reasons.append("nvmlDeviceGetFieldValues: not in the library")
            return {}
        fields = (_Field * len(ids))()
        for field, ident in zip(fields, ids):
            field.fieldId = ident
        try:
            code = function(handle, ctypes.c_int(len(ids)), fields)
        except (ctypes.ArgumentError, OSError) as exc:
            reasons.append(f"nvmlDeviceGetFieldValues: {exc}")
            return {}
        if code != NVML_SUCCESS:
            reasons.append(f"nvmlDeviceGetFieldValues: {nvml_error(code)}")
            return {}
        values = {}
        for field in fields:
            member = MEMBER_BY_TYPE.get(field.valueType)
            if field.nvmlReturn == NVML_SUCCESS and member:
                values[field.fieldId] = float(getattr(field.value, member))
            elif field.nvmlReturn != NVML_SUCCESS:
                reasons.append(f"field {field.fieldId}: {nvml_error(field.nvmlReturn)}")
            else:
                reasons.append(f"field {field.fieldId}: value type {field.valueType}")
        return values

    def _power(self, handle, index: int, highest_limit_w: Optional[float],
               architecture: Optional[int] = None) -> dict:
        """The power, the way that gave it, and what every way answered.

        nvmlDeviceGetPowerUsage, else the power fields, which are nvidia-smi's
        power.draw, .average and .instant: the same measurement by three doors.
        A reading over the ceiling (`power_ceiling_w`) is thrown away and the
        next door is not tried: the card answered, with something impossible.
        NOT_SUPPORTED from the first is a card with no power sensor: no other
        door's figure is its power.

        The samples buffer is asked too. Where no door gives the power and the
        driver estimates it (`estimates_power`), it is that estimate and goes
        in its own field; otherwise it only goes to the report, as does the
        energy counter.
        """
        reasons: list[str] = []
        answers: list[tuple[str, str]] = []
        result: dict = {"power_w": None, "power_source": None, "power_error": None}
        ceiling_w = power_ceiling_w(highest_limit_w)

        milliwatts = self._integer("nvmlDeviceGetPowerUsage", handle, reasons=reasons)
        answers.append(("nvmlDeviceGetPowerUsage", _answer(milliwatts, reasons)))
        no_sensor = (milliwatts is None and f"nvmlDeviceGetPowerUsage: {nvml_error(NVML_ERROR_NOT_SUPPORTED)}" in reasons)
        result["power_sensor"] = False if no_sensor else (True if milliwatts is not None else None)
        source = "nvmlDeviceGetPowerUsage" if milliwatts is not None else None
        if milliwatts is None:
            fields = self._fields(handle, FIELD_POWER_AVERAGE, FIELD_POWER_INSTANT,
                                  reasons=reasons)
            for field in (FIELD_POWER_AVERAGE, FIELD_POWER_INSTANT):
                answer = _answer(fields.get(field), reasons, f"field {field}")
                if no_sensor and field in fields:
                    answer += ", not taken: no power sensor"
                answers.append((f"field {field}", answer))
                if source is None and field in fields and not no_sensor:
                    milliwatts, source = fields[field], f"field {field}"
        else:
            answers += [(f"field {f}", "not asked")
                        for f in (FIELD_POWER_AVERAGE, FIELD_POWER_INSTANT)]

        estimate = self._power_samples(handle, index, ceiling_w, answers)
        energy_reasons: list[str] = []
        energy = self._integer("nvmlDeviceGetTotalEnergyConsumption", handle,
                               kind=ctypes.c_ulonglong, reasons=energy_reasons)
        answers.append(("nvmlDeviceGetTotalEnergyConsumption",
                        f"{energy} mJ" if energy is not None
                        else _answer(None, energy_reasons)))
        answers.append(("nvmlDeviceGetArchitecture",
                        str(architecture) if architecture is not None else "no answer"))
        answers.append(("ceiling", f"{ceiling_w:.1f} W, {IMPOSSIBLE_OVER_LIMIT} x "
                                   f"{highest_limit_w:.1f} W" if highest_limit_w
                        else f"{ceiling_w:.0f} W, no declared limit"))
        result["power_answers"] = tuple(answers)

        if milliwatts is not None:
            watts = milliwatts / 1000
            if watts > ceiling_w:
                result.update(power_discarded_w=round(watts, 2), power_discarded_source=source)
            else:
                result.update(power_w=round(watts, 1), power_source=source)
            return result
        result["power_error"] = "; ".join(reasons) or None
        if estimate is not None and estimates_power(architecture):
            result.update(estimate)
        return result

    def _power_samples(self, handle, index: int, ceiling_w: float,
                       answers: list) -> Optional[dict]:
        """The mean of the power samples taken since the previous reading.

        The first reading has nothing to start from and takes what the buffer
        holds, a few seconds' worth. Samples over `ceiling_w` are left out.
        """
        name = "nvmlDeviceGetSamples"
        function = self._symbol(name)
        if function is None:
            answers.append((name, "not in the library"))
            return None
        previous = self._last_power_sample.get(index)
        since = ctypes.c_ulonglong(previous or 0)
        kind, value_type, count = (ctypes.c_uint(TOTAL_POWER_SAMPLES), ctypes.c_uint(),
                                   ctypes.c_uint())
        samples = None
        try:
            # A first call without a buffer says how many there are.
            code = function(handle, kind, since, ctypes.byref(value_type),
                            ctypes.byref(count), None)
            if code == NVML_SUCCESS and count.value:
                samples = (_Sample * count.value)()
                code = function(handle, kind, since, ctypes.byref(value_type),
                                ctypes.byref(count), samples)
        except (ctypes.ArgumentError, OSError) as exc:
            answers.append((name, str(exc)))
            return None
        if code != NVML_SUCCESS:
            answers.append((name, nvml_error(code)))
            return None
        member = MEMBER_BY_TYPE.get(value_type.value)
        taken = list(samples)[:count.value] if samples is not None else []
        if not taken or member is None:
            answers.append((name, f"{len(taken)} samples, value type {value_type.value}"))
            return None
        self._last_power_sample[index] = max(sample.timeStamp for sample in taken)
        start = previous if previous is not None else min(s.timeStamp for s in taken)
        window_s = (self._last_power_sample[index] - start) / 1_000_000
        watts = [float(getattr(s.sampleValue, member)) / 1000 for s in taken]
        kept = [w for w in watts if w <= ceiling_w]
        answer = (f"{len(watts)} samples over {window_s:.2f} s, "
                  f"{min(watts):.2f}-{max(watts):.2f} W, mean {sum(watts) / len(watts):.2f} W")
        if len(kept) < len(watts):
            answer += f", {len(watts) - len(kept)} over the ceiling left out"
        answers.append((name, answer))
        if not kept:
            return {"power_discarded_w": round(max(watts), 2),
                    "power_discarded_source": name}
        return {"power_estimate_w": round(sum(kept) / len(kept), 1),
                "power_estimate_window_s": round(window_s, 2),
                "power_estimate_samples": len(kept)}

    def _compute_processes(self, handle) -> Optional[int]:
        """How many compute processes run on the card.

        Asked with an empty list: NVML then answers success when there are
        none, or INSUFFICIENT_SIZE with how many there are. No structure is
        read, so its version does not matter. Graphics processes are not
        asked: a hybrid laptop's display server is one, idle on the card.
        """
        function = self._symbol("nvmlDeviceGetComputeRunningProcesses_v3",
                                "nvmlDeviceGetComputeRunningProcesses_v2",
                                "nvmlDeviceGetComputeRunningProcesses")
        if function is None:
            return None
        count = ctypes.c_uint(0)
        try:
            code = function(handle, ctypes.byref(count), None)
        except (ctypes.ArgumentError, OSError):
            return None
        if code in (NVML_SUCCESS, NVML_ERROR_INSUFFICIENT_SIZE):
            return count.value
        return None

    def _limits(self, handle) -> dict[str, Optional[float]]:
        """The factory power limit and the range the card accepts, in watts."""
        minimum = maximum = None
        function = self._symbol("nvmlDeviceGetPowerManagementLimitConstraints")
        if function is not None:
            low, high = ctypes.c_uint(), ctypes.c_uint()
            try:
                if function(handle, ctypes.byref(low), ctypes.byref(high)) == NVML_SUCCESS:
                    minimum, maximum = low.value, high.value
            except (ctypes.ArgumentError, OSError):
                pass
        default = self._integer("nvmlDeviceGetPowerManagementDefaultLimit", handle)

        def watts(milliwatts: Optional[int]) -> Optional[float]:
            return round(milliwatts / 1000, 1) if milliwatts else None

        return {"power_cap_default_w": watts(default), "power_cap_min_w": watts(minimum),
                "power_cap_max_w": watts(maximum)}

    def _temperature(self, handle) -> Optional[float]:
        """The GPU's temperature. nvmlDeviceGetTemperature is deprecated
        since CUDA 13.0 and answers NVML_ERROR_DEPRECATED once removed; its
        replacement exists from R570, so older drivers keep the old one."""
        function = self._symbol("nvmlDeviceGetTemperatureV")
        if function is not None:
            reading = _Temperature(version=TEMPERATURE_V1, sensorType=GPU_TEMPERATURE)
            try:
                if function(handle, ctypes.byref(reading)) == NVML_SUCCESS:
                    return float(reading.temperature)
            except (ctypes.ArgumentError, OSError):
                pass
        value = self._integer("nvmlDeviceGetTemperature", handle, ctypes.c_uint(GPU_TEMPERATURE))
        return float(value) if value is not None else None

    def _struct(self, name: str, handle, kind, *fallbacks):
        function = self._symbol(name, *fallbacks)
        if function is None:
            return None
        data = kind()
        try:
            if function(handle, ctypes.byref(data)) != NVML_SUCCESS:
                return None
        except (ctypes.ArgumentError, OSError):
            return None
        return data

    def _read(self, index: int, handle, driver: Optional[str]) -> NvidiaGpu:
        memory = self._struct("nvmlDeviceGetMemoryInfo", handle, _Memory)
        usage = self._struct("nvmlDeviceGetUtilizationRates", handle, _Utilization)
        pci = self._struct("nvmlDeviceGetPciInfo_v3", handle, _Pci,
                               "nvmlDeviceGetPciInfo_v2", "nvmlDeviceGetPciInfo")

        mhz = lambda *args: (lambda v: v * 1_000_000 if v else None)(self._integer(*args))
        watts = lambda *args: (lambda v: round(v / 1000, 1) if v is not None else None)(
            self._integer(*args))

        limits = self._limits(handle)
        enforced = watts("nvmlDeviceGetEnforcedPowerLimit", handle)
        declared = [w for w in (enforced, *limits.values()) if w]
        architecture = self._integer("nvmlDeviceGetArchitecture", handle)
        power = self._power(handle, index, max(declared) if declared else None, architecture)
        # Renamed in R535 with the same bits; the old name is deprecated.
        flags = self._integer("nvmlDeviceGetCurrentClocksEventReasons", handle,
                                kind=ctypes.c_ulonglong)
        if flags is None:
            flags = self._integer("nvmlDeviceGetCurrentClocksThrottleReasons", handle,
                                    kind=ctypes.c_ulonglong)
        reasons = _reasons(flags) if flags is not None else ()

        return NvidiaGpu(
            index=index,
            # NVML writes the address in upper case with an eight-digit
            # domain; sysfs in lower case with four. Normalized so it matches
            # the card already listed.
            pci_slot=_slot(pci.busId.decode("ascii", "replace")) if pci else None,
            name=self._string("nvmlDeviceGetName", handle),
            vbios=self._string("nvmlDeviceGetVbiosVersion", handle, 32),
            driver_version=driver,
            serial=self._string("nvmlDeviceGetSerial", handle, 32),
            uuid=self._string("nvmlDeviceGetUUID", handle, 96),
            cuda_cores=self._integer("nvmlDeviceGetNumGpuCores", handle),
            memory_total_bytes=memory.total if memory else None,
            memory_used_bytes=memory.used if memory else None,
            memory_bus_bits=self._integer("nvmlDeviceGetMemoryBusWidth", handle),
            busy_percent=float(usage.gpu) if usage else None,
            memory_busy_percent=float(usage.memory) if usage else None,
            encode_busy_percent=self._utilization("nvmlDeviceGetEncoderUtilization", handle),
            decode_busy_percent=self._utilization("nvmlDeviceGetDecoderUtilization", handle),
            temp_c=self._temperature(handle),
            **power,
            architecture=architecture,
            performance_state=(lambda v: v if v is not None and 0 <= v <= 15 else None)(
                self._integer("nvmlDeviceGetPerformanceState", handle)),
            compute_processes=self._compute_processes(handle),
            power_cap_w=enforced,
            **limits,
            fan_percent=(lambda v: float(v) if v is not None else None)(
                self._integer("nvmlDeviceGetFanSpeed", handle)),
            core_hz=mhz("nvmlDeviceGetClockInfo", handle, ctypes.c_uint(CLOCK_GRAPHICS)),
            core_max_hz=mhz("nvmlDeviceGetMaxClockInfo", handle, ctypes.c_uint(CLOCK_GRAPHICS)),
            memory_hz=mhz("nvmlDeviceGetClockInfo", handle, ctypes.c_uint(CLOCK_MEMORY)),
            memory_max_hz=mhz("nvmlDeviceGetMaxClockInfo", handle, ctypes.c_uint(CLOCK_MEMORY)),
            video_hz=mhz("nvmlDeviceGetClockInfo", handle, ctypes.c_uint(CLOCK_VIDEO)),
            link_generation=self._integer("nvmlDeviceGetCurrPcieLinkGeneration", handle),
            link_width=self._integer("nvmlDeviceGetCurrPcieLinkWidth", handle),
            max_link_generation=self._integer("nvmlDeviceGetMaxPcieLinkGeneration", handle),
            max_link_width=self._integer("nvmlDeviceGetMaxPcieLinkWidth", handle),
            throttled=None if flags is None else bool(reasons),
            throttle_reasons=reasons,
        )


def power_ceiling_w(highest_limit_w: Optional[float]) -> float:
    """Above this a power reading is impossible: `IMPOSSIBLE_OVER_LIMIT` times
    the highest limit the card declares, or the general ceiling without one."""
    return IMPOSSIBLE_OVER_LIMIT * highest_limit_w if highest_limit_w else PLAUSIBLE["W"][1]


def _answer(value, reasons: list[str], prefix: str = "") -> str:
    """What one way answered: its milliwatts, or the reason it gave none."""
    if value is not None:
        return f"{value:.0f} mW"
    # A field's own reason, or the one of the call that asks for all of them.
    for reason in reversed(reasons):
        name, _sep, why = reason.partition(": ")
        if not prefix or name in (prefix, "nvmlDeviceGetFieldValues"):
            return why
    return "no answer"


def _slot(bus_id: str) -> Optional[str]:
    """NVML's «00000000:0C:00.0» → «0000:0c:00.0», as sysfs writes it."""
    parts = bus_id.strip().split(":")
    if len(parts) != 3:
        return None
    domain, bus, rest = parts
    return f"{int(domain, 16):04x}:{bus.lower()}:{rest.lower()}"


def _reasons(flags: int) -> tuple[str, ...]:
    """The throttle reasons, leaving out «idle»."""
    return tuple(reason for bit, reason in THROTTLE_REASONS.items()
                 if flags & bit and bit != NO_REASON)
