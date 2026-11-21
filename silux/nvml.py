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

BIBLIOTECAS = ("libnvidia-ml.so.1", "libnvidia-ml.so")

NVML_SUCCESS = 0
# nvmlReturn_t, as nvml.h names them: what the report says NVML answered.
NVML_ERRORS = {1: "UNINITIALIZED", 2: "INVALID_ARGUMENT", 3: "NOT_SUPPORTED",
               4: "NO_PERMISSION", 6: "NOT_FOUND", 9: "DRIVER_NOT_LOADED", 10: "TIMEOUT",
               13: "FUNCTION_NOT_FOUND", 15: "GPU_IS_LOST", 17: "OPERATING_SYSTEM",
               18: "LIB_RM_VERSION_MISMATCH", 21: "NO_DATA", 25: "ARGUMENT_VERSION_MISMATCH",
               26: "DEPRECATED", 999: "UNKNOWN"}


def nvml_error(codigo: int) -> str:
    nombre = NVML_ERRORS.get(codigo)
    return f"NVML_ERROR_{nombre} ({codigo})" if nombre else f"NVML return {codigo}"

TEMPERATURA_GPU = 0
# Los relojes que interesan, por su enumeración: gráfico, SM, memoria, vídeo.
RELOJ_GRAFICO, RELOJ_SM, RELOJ_MEMORIA, RELOJ_VIDEO = 0, 1, 2, 3
LONGITUD_NOMBRE = 96

# Por qué la tarjeta recorta sus relojes. Los define `nvmlClocksThrottleReasons`.
MOTIVOS = {
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
SIN_MOTIVO = 0x0000000000000001


# The GPU's power as a field value (nvml.h, NVML 13.4.92): the average over
# a second (Ampere and newer, but GA100) and the current one (every
# architecture). nvmlDeviceGetPowerUsage only answers where «power management
# mode» is supported, and the header points to these two for the rest: a
# tester's RTX 4060 with driver 595 gave its temperature, clocks and limit,
# and no power. Milliwatts, like nvmlDeviceGetPowerUsage and the limits of
# the same block; for these two the header does not write it.
CAMPO_POTENCIA_MEDIA, CAMPO_POTENCIA_AL_MOMENTO = 185, 186


class _Valor(ctypes.Union):
    """nvmlValue_t, its members in the header's order."""
    _fields_ = [("dVal", ctypes.c_double), ("siVal", ctypes.c_int), ("uiVal", ctypes.c_uint),
                ("ulVal", ctypes.c_ulong), ("ullVal", ctypes.c_ulonglong),
                ("sllVal", ctypes.c_longlong), ("usVal", ctypes.c_ushort)]


class _Campo(ctypes.Structure):
    """nvmlFieldValue_t."""
    _fields_ = [("fieldId", ctypes.c_uint), ("scopeId", ctypes.c_uint),
                ("timestamp", ctypes.c_longlong), ("latencyUsec", ctypes.c_longlong),
                ("valueType", ctypes.c_uint), ("nvmlReturn", ctypes.c_uint),
                ("value", _Valor)]


# nvmlValueType_t: which member of the union holds the value.
MIEMBRO_DEL_TIPO = {0: "dVal", 1: "uiVal", 2: "ulVal", 3: "ullVal", 4: "sllVal",
                    5: "siVal", 6: "usVal"}


# nvmlSamplingType_t: the board's total power, which the driver samples into
# a ring buffer whether or not the power usage call answers. nvidia-smi shows
# their mean as «Power Samples» where «Power Draw» is N/A.
TOTAL_POWER_SAMPLES = 0


class _Sample(ctypes.Structure):
    """nvmlSample_t."""
    _fields_ = [("timeStamp", ctypes.c_ulonglong), ("sampleValue", _Valor)]


class _Temperature(ctypes.Structure):
    """nvmlTemperature_v1_t, for nvmlDeviceGetTemperatureV (R570 and newer)."""
    _fields_ = [("version", ctypes.c_uint), ("sensorType", ctypes.c_uint),
                ("temperature", ctypes.c_int)]


# NVML_STRUCT_VERSION: the structure's size, and its version in the top byte.
TEMPERATURE_V1 = ctypes.sizeof(_Temperature) | 1 << 24


class _Memoria(ctypes.Structure):
    _fields_ = [("total", ctypes.c_ulonglong), ("free", ctypes.c_ulonglong),
                ("used", ctypes.c_ulonglong)]


class _Uso(ctypes.Structure):
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
        self._activa = False
        # The newest power sample already used, per card: each reading
        # averages only what the driver sampled since the previous one.
        self._last_power_sample: dict[int, int] = {}

    # -- ciclo de vida ------------------------------------------------------

    def open(self) -> bool:
        if self._activa:
            return True
        for nombre in BIBLIOTECAS:
            try:
                self._lib = ctypes.CDLL(nombre)
                break
            except OSError:
                continue
        if self._lib is None:
            return False
        iniciar = self._sim("nvmlInit_v2", "nvmlInit")
        if iniciar is None or iniciar() != NVML_SUCCESS:
            self._lib = None
            return False
        self._activa = True
        return True

    def close(self) -> None:
        if self._activa and self._lib is not None:
            apagar = self._sim("nvmlShutdown")
            if apagar is not None:
                apagar()
        self._activa = False
        self._lib = None

    # -- consulta -----------------------------------------------------------

    def devices(self) -> list[NvidiaGpu]:
        if not self._activa or self._lib is None:
            return []
        contar = self._sim("nvmlDeviceGetCount_v2", "nvmlDeviceGetCount")
        traer = self._sim("nvmlDeviceGetHandleByIndex_v2", "nvmlDeviceGetHandleByIndex")
        if contar is None or traer is None:
            return []

        cuantas = ctypes.c_uint()
        if contar(ctypes.byref(cuantas)) != NVML_SUCCESS:
            return []

        version = self._cadena_global("nvmlSystemGetDriverVersion", 80)
        encontradas = []
        for indice in range(cuantas.value):
            asa = ctypes.c_void_p()
            if traer(ctypes.c_uint(indice), ctypes.byref(asa)) != NVML_SUCCESS:
                continue
            encontradas.append(self._leer(indice, asa, version))
        return encontradas

    # -- interno ------------------------------------------------------------

    def _sim(self, *nombres: str):
        """El primero de estos símbolos que exista. NVML versiona los que cambia."""
        for nombre in nombres:
            simbolo = getattr(self._lib, nombre, None)
            if simbolo is not None:
                return simbolo
        return None

    def _entero(self, nombre: str, asa, *extra, tipo=ctypes.c_uint,
                motivos: Optional[list] = None) -> Optional[int]:
        """The value, or None; `motivos` collects why not."""
        funcion = self._sim(nombre)
        if funcion is None:
            if motivos is not None:
                motivos.append(f"{nombre}: not in the library")
            return None
        valor = tipo()
        argumentos = (asa, *extra, ctypes.byref(valor))
        try:
            codigo = funcion(*argumentos)
        except (ctypes.ArgumentError, OSError) as exc:
            if motivos is not None:
                motivos.append(f"{nombre}: {exc}")
            return None
        if codigo != NVML_SUCCESS:
            if motivos is not None:
                motivos.append(f"{nombre}: {nvml_error(codigo)}")
            return None
        return valor.value

    def _utilizacion(self, nombre: str, asa) -> Optional[float]:
        """El uso de NVENC o NVDEC, en %.

        `nvmlDeviceGet{Encoder,Decoder}Utilization` escriben dos enteros, el
        uso y el periodo en que se midió: con un solo puntero, como en
        `_entero`, la biblioteca escribiría el segundo en memoria de nadie.
        """
        funcion = self._sim(nombre)
        if funcion is None:
            return None
        uso, periodo_us = ctypes.c_uint(), ctypes.c_uint()
        try:
            if funcion(asa, ctypes.byref(uso), ctypes.byref(periodo_us)) != NVML_SUCCESS:
                return None
        except (ctypes.ArgumentError, OSError):
            return None
        return float(uso.value)

    def _cadena(self, nombre: str, asa, longitud: int = LONGITUD_NOMBRE) -> Optional[str]:
        funcion = self._sim(nombre)
        if funcion is None:
            return None
        buffer = ctypes.create_string_buffer(longitud)
        try:
            if funcion(asa, buffer, ctypes.c_uint(longitud)) != NVML_SUCCESS:
                return None
        except (ctypes.ArgumentError, OSError):
            return None
        return buffer.value.decode("utf-8", "replace").strip() or None

    def _cadena_global(self, nombre: str, longitud: int) -> Optional[str]:
        funcion = self._sim(nombre)
        if funcion is None:
            return None
        buffer = ctypes.create_string_buffer(longitud)
        if funcion(buffer, ctypes.c_uint(longitud)) != NVML_SUCCESS:
            return None
        return buffer.value.decode("utf-8", "replace").strip() or None

    def _campos(self, asa, *ids: int, motivos: Optional[list] = None) -> dict[int, float]:
        """Field values that came back, by id. Each one carries its own
        return code and value type: one that fails does not spoil the rest.
        `motivos` collects why each missing one is missing."""
        motivos = motivos if motivos is not None else []
        funcion = self._sim("nvmlDeviceGetFieldValues")
        if funcion is None:
            motivos.append("nvmlDeviceGetFieldValues: not in the library")
            return {}
        campos = (_Campo * len(ids))()
        for campo, ident in zip(campos, ids):
            campo.fieldId = ident
        try:
            codigo = funcion(asa, ctypes.c_int(len(ids)), campos)
        except (ctypes.ArgumentError, OSError) as exc:
            motivos.append(f"nvmlDeviceGetFieldValues: {exc}")
            return {}
        if codigo != NVML_SUCCESS:
            motivos.append(f"nvmlDeviceGetFieldValues: {nvml_error(codigo)}")
            return {}
        leidos = {}
        for campo in campos:
            miembro = MIEMBRO_DEL_TIPO.get(campo.valueType)
            if campo.nvmlReturn == NVML_SUCCESS and miembro:
                leidos[campo.fieldId] = float(getattr(campo.value, miembro))
            elif campo.nvmlReturn != NVML_SUCCESS:
                motivos.append(f"field {campo.fieldId}: {nvml_error(campo.nvmlReturn)}")
            else:
                motivos.append(f"field {campo.fieldId}: value type {campo.valueType}")
        return leidos

    def _potencia(self, asa, index: int) -> tuple[Optional[float], Optional[str]]:
        """Watts: nvmlDeviceGetPowerUsage, else the power fields, else the
        mean of the power samples. Without any, what NVML answered to each."""
        motivos: list[str] = []
        milivatios = self._entero("nvmlDeviceGetPowerUsage", asa, motivos=motivos)
        if milivatios is None:
            campos = self._campos(asa, CAMPO_POTENCIA_MEDIA, CAMPO_POTENCIA_AL_MOMENTO,
                                  motivos=motivos)
            milivatios = campos.get(CAMPO_POTENCIA_MEDIA, campos.get(CAMPO_POTENCIA_AL_MOMENTO))
        if milivatios is None:
            milivatios = self._power_samples(asa, index, motivos)
        if milivatios is None:
            return None, "; ".join(motivos) or None
        return round(milivatios / 1000, 1), None

    def _power_samples(self, handle, index: int, reasons: list) -> Optional[float]:
        """Mean of the power samples taken since the last reading, in mW.

        The first reading has nothing to start from and takes what the
        buffer holds, a few seconds' worth.
        """
        function = self._sim("nvmlDeviceGetSamples")
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
        member = MIEMBRO_DEL_TIPO.get(value_type.value)
        taken = list(samples)[:count.value] if samples is not None else []
        if not taken or member is None:
            reasons.append(f"nvmlDeviceGetSamples: {len(taken)} samples, value type {value_type.value}")
            return None
        self._last_power_sample[index] = max(sample.timeStamp for sample in taken)
        return sum(float(getattr(sample.sampleValue, member)) for sample in taken) / len(taken)

    def _limits(self, handle) -> dict[str, Optional[float]]:
        """The factory power limit and the range the card accepts, in watts."""
        minimum = maximum = None
        function = self._sim("nvmlDeviceGetPowerManagementLimitConstraints")
        if function is not None:
            low, high = ctypes.c_uint(), ctypes.c_uint()
            try:
                if function(handle, ctypes.byref(low), ctypes.byref(high)) == NVML_SUCCESS:
                    minimum, maximum = low.value, high.value
            except (ctypes.ArgumentError, OSError):
                pass
        default = self._entero("nvmlDeviceGetPowerManagementDefaultLimit", handle)

        def watts(milliwatts: Optional[int]) -> Optional[float]:
            return round(milliwatts / 1000, 1) if milliwatts else None

        return {"power_cap_default_w": watts(default), "power_cap_min_w": watts(minimum),
                "power_cap_max_w": watts(maximum)}

    def _temperature(self, handle) -> Optional[float]:
        """The GPU's temperature. nvmlDeviceGetTemperature is deprecated
        since CUDA 13.0 and answers NVML_ERROR_DEPRECATED once removed; its
        replacement exists from R570, so older drivers keep the old one."""
        function = self._sim("nvmlDeviceGetTemperatureV")
        if function is not None:
            reading = _Temperature(version=TEMPERATURE_V1, sensorType=TEMPERATURA_GPU)
            try:
                if function(handle, ctypes.byref(reading)) == NVML_SUCCESS:
                    return float(reading.temperature)
            except (ctypes.ArgumentError, OSError):
                pass
        value = self._entero("nvmlDeviceGetTemperature", handle, ctypes.c_uint(TEMPERATURA_GPU))
        return float(value) if value is not None else None

    def _estructura(self, nombre: str, asa, tipo, *alternativas):
        funcion = self._sim(nombre, *alternativas)
        if funcion is None:
            return None
        dato = tipo()
        try:
            if funcion(asa, ctypes.byref(dato)) != NVML_SUCCESS:
                return None
        except (ctypes.ArgumentError, OSError):
            return None
        return dato

    def _leer(self, indice: int, asa, driver: Optional[str]) -> NvidiaGpu:
        memoria = self._estructura("nvmlDeviceGetMemoryInfo", asa, _Memoria)
        uso = self._estructura("nvmlDeviceGetUtilizationRates", asa, _Uso)
        pci = self._estructura("nvmlDeviceGetPciInfo_v3", asa, _Pci,
                               "nvmlDeviceGetPciInfo_v2", "nvmlDeviceGetPciInfo")

        mhz = lambda *args: (lambda v: v * 1_000_000 if v else None)(self._entero(*args))
        milis = lambda *args: (lambda v: round(v / 1000, 1) if v is not None else None)(
            self._entero(*args))

        potencia, sin_potencia = self._potencia(asa, indice)
        # Renamed in R535 with the same bits; the old name is deprecated.
        banderas = self._entero("nvmlDeviceGetCurrentClocksEventReasons", asa,
                                tipo=ctypes.c_ulonglong)
        if banderas is None:
            banderas = self._entero("nvmlDeviceGetCurrentClocksThrottleReasons", asa,
                                    tipo=ctypes.c_ulonglong)
        motivos = _motivos(banderas) if banderas is not None else ()

        return NvidiaGpu(
            index=indice,
            # NVML da la dirección en mayúsculas y con dominio de ocho dígitos;
            # sysfs la escribe en minúsculas y con cuatro. Se normaliza para
            # poder casarla con la tarjeta que ya se enumeró.
            pci_slot=_ranura(pci.busId.decode("ascii", "replace")) if pci else None,
            name=self._cadena("nvmlDeviceGetName", asa),
            vbios=self._cadena("nvmlDeviceGetVbiosVersion", asa, 32),
            driver_version=driver,
            serial=self._cadena("nvmlDeviceGetSerial", asa, 32),
            uuid=self._cadena("nvmlDeviceGetUUID", asa, 96),
            cuda_cores=self._entero("nvmlDeviceGetNumGpuCores", asa),
            memory_total_bytes=memoria.total if memoria else None,
            memory_used_bytes=memoria.used if memoria else None,
            memory_bus_bits=self._entero("nvmlDeviceGetMemoryBusWidth", asa),
            busy_percent=float(uso.gpu) if uso else None,
            memory_busy_percent=float(uso.memory) if uso else None,
            encode_busy_percent=self._utilizacion("nvmlDeviceGetEncoderUtilization", asa),
            decode_busy_percent=self._utilizacion("nvmlDeviceGetDecoderUtilization", asa),
            temp_c=self._temperature(asa),
            power_w=potencia,
            power_error=sin_potencia,
            power_cap_w=milis("nvmlDeviceGetEnforcedPowerLimit", asa),
            **self._limits(asa),
            fan_percent=(lambda v: float(v) if v is not None else None)(
                self._entero("nvmlDeviceGetFanSpeed", asa)),
            core_hz=mhz("nvmlDeviceGetClockInfo", asa, ctypes.c_uint(RELOJ_GRAFICO)),
            core_max_hz=mhz("nvmlDeviceGetMaxClockInfo", asa, ctypes.c_uint(RELOJ_GRAFICO)),
            memory_hz=mhz("nvmlDeviceGetClockInfo", asa, ctypes.c_uint(RELOJ_MEMORIA)),
            memory_max_hz=mhz("nvmlDeviceGetMaxClockInfo", asa, ctypes.c_uint(RELOJ_MEMORIA)),
            video_hz=mhz("nvmlDeviceGetClockInfo", asa, ctypes.c_uint(RELOJ_VIDEO)),
            link_generation=self._entero("nvmlDeviceGetCurrPcieLinkGeneration", asa),
            link_width=self._entero("nvmlDeviceGetCurrPcieLinkWidth", asa),
            max_link_generation=self._entero("nvmlDeviceGetMaxPcieLinkGeneration", asa),
            max_link_width=self._entero("nvmlDeviceGetMaxPcieLinkWidth", asa),
            throttled=None if banderas is None else bool(motivos),
            throttle_reasons=motivos,
        )


def _ranura(bus_id: str) -> Optional[str]:
    """«00000000:0C:00.0» de NVML → «0000:0c:00.0» como lo escribe sysfs."""
    partes = bus_id.strip().split(":")
    if len(partes) != 3:
        return None
    dominio, bus, resto = partes
    return f"{int(dominio, 16):04x}:{bus.lower()}:{resto.lower()}"


def _motivos(banderas: int) -> tuple[str, ...]:
    """Los motivos de recorte, sin contar el «está en reposo»."""
    return tuple(motivo for bit, motivo in MOTIVOS.items()
                 if banderas & bit and bit != SIN_MOTIVO)
