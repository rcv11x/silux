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
    power_cap_w: Optional[float] = None
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

    def _entero(self, nombre: str, asa, *extra, tipo=ctypes.c_uint) -> Optional[int]:
        funcion = self._sim(nombre)
        if funcion is None:
            return None
        valor = tipo()
        argumentos = (asa, *extra, ctypes.byref(valor))
        try:
            if funcion(*argumentos) != NVML_SUCCESS:
                return None
        except (ctypes.ArgumentError, OSError):
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

    def _campos(self, asa, *ids: int) -> dict[int, float]:
        """Field values that came back, by id. Each one carries its own
        return code and value type: one that fails does not spoil the rest."""
        funcion = self._sim("nvmlDeviceGetFieldValues")
        if funcion is None:
            return {}
        campos = (_Campo * len(ids))()
        for campo, ident in zip(campos, ids):
            campo.fieldId = ident
        try:
            if funcion(asa, ctypes.c_int(len(ids)), campos) != NVML_SUCCESS:
                return {}
        except (ctypes.ArgumentError, OSError):
            return {}
        leidos = {}
        for campo in campos:
            miembro = MIEMBRO_DEL_TIPO.get(campo.valueType)
            if campo.nvmlReturn == NVML_SUCCESS and miembro:
                leidos[campo.fieldId] = float(getattr(campo.value, miembro))
        return leidos

    def _potencia(self, asa) -> Optional[float]:
        """Watts: nvmlDeviceGetPowerUsage, or the power fields where it does
        not answer."""
        milivatios = self._entero("nvmlDeviceGetPowerUsage", asa)
        if milivatios is None:
            campos = self._campos(asa, CAMPO_POTENCIA_MEDIA, CAMPO_POTENCIA_AL_MOMENTO)
            milivatios = campos.get(CAMPO_POTENCIA_MEDIA, campos.get(CAMPO_POTENCIA_AL_MOMENTO))
        return round(milivatios / 1000, 1) if milivatios is not None else None

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
            temp_c=(lambda v: float(v) if v is not None else None)(
                self._entero("nvmlDeviceGetTemperature", asa, ctypes.c_uint(TEMPERATURA_GPU))),
            power_w=self._potencia(asa),
            power_cap_w=milis("nvmlDeviceGetEnforcedPowerLimit", asa),
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
