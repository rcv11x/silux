"""NVIDIA con el driver propietario, que no publica nada en sysfs.

Una Radeon cuenta su vida en `/sys/class/drm`; una GeForce con el driver de
NVIDIA no. Ahí solo hay el nodo PCI pelado: ni memoria, ni relojes, ni
temperatura. Todo eso está detrás de NVML, la biblioteca que trae el propio
driver y que es lo que usa por dentro `nvidia-smi`.

Se carga con `ctypes` como el resto de bibliotecas del programa. NVML lleva
más de una década con la misma ABI y versiona los símbolos que cambia (de ahí
los sufijos `_v2` y `_v3`), así que se piden los versionados y se cae a los
antiguos si el driver es viejo.

⚠ Ojo al mantenerlo: esto está escrito contra la API documentada, pero no se
ha podido probar con una NVIDIA delante. Los tipos de las estructuras y los
códigos están comprobados sobre el papel; el día que alguien lo ejecute con una
tarjeta puesta conviene contrastar las cifras con `nvidia-smi -q`.
"""

from __future__ import annotations

import ctypes
from dataclasses import dataclass
from typing import Optional

LIBRARIES = ("libnvidia-ml.so.1", "libnvidia-ml.so")

NVML_SUCCESS = 0
# nvmlReturn_t, as nvml.h names them: what the report says NVML answered.
NVML_ERRORS = {1: "UNINITIALIZED", 2: "INVALID_ARGUMENT", 3: "NOT_SUPPORTED",
               4: "NO_PERMISSION", 6: "NOT_FOUND", 9: "DRIVER_NOT_LOADED", 10: "TIMEOUT",
               13: "FUNCTION_NOT_FOUND", 15: "GPU_IS_LOST", 17: "OPERATING_SYSTEM",
               18: "LIB_RM_VERSION_MISMATCH", 21: "NO_DATA", 25: "ARGUMENT_VERSION_MISMATCH",
               26: "DEPRECATED", 999: "UNKNOWN"}


def nvml_error(code: int) -> str:
    name = NVML_ERRORS.get(code)
    return f"NVML_ERROR_{name} ({code})" if name else f"NVML return {code}"

GPU_TEMPERATURE = 0
# Los relojes que interesan, por su enumeración: gráfico, SM, memoria, vídeo.
CLOCK_GRAPHICS, CLOCK_SM, CLOCK_MEMORY, CLOCK_VIDEO = 0, 1, 2, 3
NAME_LENGTH = 96

# Por qué la tarjeta recorta sus relojes. Los define `nvmlClocksThrottleReasons`.
THROTTLE_REASONS = {
    0x0000000000000001: "en reposo",
    0x0000000000000002: "relojes fijados por la aplicación",
    0x0000000000000004: "límite de potencia del driver",
    0x0000000000000008: "protección del hardware",
    0x0000000000000010: "sincronización entre tarjetas",
    0x0000000000000020: "temperatura (driver)",
    0x0000000000000040: "temperatura (hardware)",
    0x0000000000000080: "freno de potencia del hardware",
    0x0000000000000100: "relojes fijados por la pantalla",
}
# Este no es un motivo: es la respuesta cuando no hay ninguno.
NO_REASON = 0x0000000000000001


# The GPU's power as a field value (nvml.h, NVML 13.4.92): the average over
# a second (Ampere and newer, but GA100) and the current one (every
# architecture). nvmlDeviceGetPowerUsage only answers where «power management
# mode» is supported, and the header points to these two for the rest: a
# tester's RTX 4060 with driver 595 gave its temperature, clocks and limit,
# and no power. Milliwatts, like nvmlDeviceGetPowerUsage and the limits of
# the same block; for these two the header does not write it.
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


# nvmlSamplingType_t: the board's total power, which the driver samples into
# a ring buffer whether or not the power usage call answers. nvidia-smi shows
# their mean as «Power Samples» where «Power Draw» is N/A.
TOTAL_POWER_SAMPLES = 0


class _Sample(ctypes.Structure):
    """nvmlSample_t."""
    _fields_ = [("timeStamp", ctypes.c_ulonglong), ("sampleValue", _Value)]


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
    """`nvmlPciInfo_t` en su versión 3, que es la que devuelve `GetPciInfo_v3`."""

    _fields_ = [
        ("busIdLegacy", ctypes.c_char * 16),
        ("domain", ctypes.c_uint), ("bus", ctypes.c_uint), ("device", ctypes.c_uint),
        ("pciDeviceId", ctypes.c_uint), ("pciSubSystemId", ctypes.c_uint),
        ("busId", ctypes.c_char * 32),
    ]


@dataclass(frozen=True, slots=True)
class NvidiaGpu:
    """Lo que NVML cuenta de una tarjeta."""

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
    # Without power: what NVML answered to each way of asking, for the report.
    power_error: Optional[str] = None
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
    """Sesión abierta con NVML. Hay que cerrarla, y por eso es un objeto.

    NVML pide inicializarse una vez y apagarse al terminar. Abrirla y cerrarla
    en cada muestreo cuesta bastante más que dejarla abierta, así que el
    proveedor la conserva mientras el programa vive.
    """

    def __init__(self) -> None:
        self._lib: Optional[ctypes.CDLL] = None
        self._active = False
        # The newest power sample already used, per card: each reading
        # averages only what the driver sampled since the previous one.
        self._last_power_sample: dict[int, int] = {}

    # -- ciclo de vida ------------------------------------------------------

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

    # -- consulta -----------------------------------------------------------

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

    # -- interno ------------------------------------------------------------

    def _symbol(self, *names: str):
        """El primero de estos símbolos que exista. NVML versiona los que cambia."""
        for name in names:
            symbol = getattr(self._lib, name, None)
            if symbol is not None:
                return symbol
        return None

    def _integer(self, name: str, handle, *extra, kind=ctypes.c_uint,
                reasons: Optional[list] = None) -> Optional[int]:
        """The value, or None; `motivos` collects why not."""
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
        """El uso de NVENC o NVDEC, en %.

        `nvmlDeviceGet{Encoder,Decoder}Utilization` escriben dos enteros, el
        uso y el periodo en que se midió: con un solo puntero, como en
        `_entero`, la biblioteca escribiría el segundo en memoria de nadie.
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
        `motivos` collects why each missing one is missing."""
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

    def _power(self, handle, index: int) -> tuple[Optional[float], Optional[str]]:
        """Watts: nvmlDeviceGetPowerUsage, else the power fields, else the
        mean of the power samples. Without any, what NVML answered to each."""
        reasons: list[str] = []
        milliwatts = self._integer("nvmlDeviceGetPowerUsage", handle, reasons=reasons)
        if milliwatts is None:
            fields = self._fields(handle, FIELD_POWER_AVERAGE, FIELD_POWER_INSTANT,
                                  reasons=reasons)
            milliwatts = fields.get(FIELD_POWER_AVERAGE, fields.get(FIELD_POWER_INSTANT))
        if milliwatts is None:
            milliwatts = self._power_samples(handle, index, reasons)
        if milliwatts is None:
            return None, "; ".join(reasons) or None
        return round(milliwatts / 1000, 1), None

    def _power_samples(self, handle, index: int, reasons: list) -> Optional[float]:
        """Mean of the power samples taken since the last reading, in mW.

        The first reading has nothing to start from and takes what the
        buffer holds, a few seconds' worth.
        """
        function = self._symbol("nvmlDeviceGetSamples")
        if function is None:
            reasons.append("nvmlDeviceGetSamples: not in the library")
            return None
        since = ctypes.c_ulonglong(self._last_power_sample.get(index, 0))
        kind, value_type, count = ctypes.c_uint(TOTAL_POWER_SAMPLES), ctypes.c_uint(), ctypes.c_uint()
        samples = None
        try:
            # A first call without a buffer says how many there are.
            code = function(handle, kind, since, ctypes.byref(value_type), ctypes.byref(count), None)
            if code == NVML_SUCCESS and count.value:
                samples = (_Sample * count.value)()
                code = function(handle, kind, since, ctypes.byref(value_type),
                                ctypes.byref(count), samples)
        except (ctypes.ArgumentError, OSError) as exc:
            reasons.append(f"nvmlDeviceGetSamples: {exc}")
            return None
        if code != NVML_SUCCESS:
            reasons.append(f"nvmlDeviceGetSamples: {nvml_error(code)}")
            return None
        member = MEMBER_BY_TYPE.get(value_type.value)
        taken = list(samples)[:count.value] if samples is not None else []
        if not taken or member is None:
            reasons.append(f"nvmlDeviceGetSamples: {len(taken)} samples, value type {value_type.value}")
            return None
        self._last_power_sample[index] = max(sample.timeStamp for sample in taken)
        return sum(float(getattr(sample.sampleValue, member)) for sample in taken) / len(taken)

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

        power, power_error = self._power(handle, index)
        # Renamed in R535 with the same bits; the old name is deprecated.
        flags = self._integer("nvmlDeviceGetCurrentClocksEventReasons", handle,
                                kind=ctypes.c_ulonglong)
        if flags is None:
            flags = self._integer("nvmlDeviceGetCurrentClocksThrottleReasons", handle,
                                    kind=ctypes.c_ulonglong)
        reasons = _reasons(flags) if flags is not None else ()

        return NvidiaGpu(
            index=index,
            # NVML da la dirección en mayúsculas y con dominio de ocho dígitos;
            # sysfs la escribe en minúsculas y con cuatro. Se normaliza para
            # poder casarla con la tarjeta que ya se enumeró.
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
            power_w=power,
            power_error=power_error,
            power_cap_w=watts("nvmlDeviceGetEnforcedPowerLimit", handle),
            **self._limits(handle),
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


def _slot(bus_id: str) -> Optional[str]:
    """«00000000:0C:00.0» de NVML → «0000:0c:00.0» como lo escribe sysfs."""
    parts = bus_id.strip().split(":")
    if len(parts) != 3:
        return None
    domain, bus, rest = parts
    return f"{int(domain, 16):04x}:{bus.lower()}:{rest.lower()}"


def _reasons(flags: int) -> tuple[str, ...]:
    """Los motivos de recorte, sin contar el «está en reposo»."""
    return tuple(reason for bit, reason in THROTTLE_REASONS.items()
                 if flags & bit and bit != NO_REASON)
