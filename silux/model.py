"""El modelo de datos: valores tipados, nunca texto ya formateado.

Todo lo que sale de aquí es inmutable. Un `Snapshot` es una foto completa
del sistema en un instante; la interfaz compara dos fotos consecutivas para
saber qué repintar, y el exportador de JSON serializa una sin más trabajo.

Los nombres de campo llevan la unidad (`freq_hz`, `size_bytes`, `temp_c`)
para que no haya ninguna duda de qué guarda cada uno.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, fields, is_dataclass
from enum import Enum
from typing import Any, Optional

from .edid import Edid, VideoMode  # noqa: F401  (se reexportan al modelo)
from .spd import SpdInfo, Timings  # noqa: F401  (se reexporta al modelo)


class Need(str, Enum):
    """Por qué falta un dato. Es lo que la interfaz enseña al usuario."""

    ROOT = "root"            # hace falta elevar privilegios
    DATABASE = "database"    # el hardware no está en la base de datos
    HARDWARE = "hardware"    # esta máquina simplemente no lo expone
    DRIVER = "driver"        # haría falta cargar un módulo del kernel
    PLATFORM = "platform"    # no aplica a esta arquitectura
    ERROR = "error"          # falló al leerse; esto es un fallo nuestro


@dataclass(frozen=True, slots=True)
class Note:
    """Explica la ausencia de un dato concreto, con su motivo."""

    path: str          # p. ej. "cpu.voltage_v"
    need: Need
    message: str
    hint: str = ""     # qué puede hacer el usuario al respecto


# --------------------------------------------------------------------------
# CPU
# --------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Cache:
    level: int
    kind: str                       # "data" | "instruction" | "unified"
    size_bytes: int
    ways: Optional[int] = None
    line_bytes: Optional[int] = None
    sets: Optional[int] = None
    instances: int = 1              # cuántas hay para este tipo de núcleo
    shared_by: int = 1              # cpus lógicas que comparten cada instancia
    # Qué CPUs lógicas comparten cada instancia. Es lo que permite dibujar el
    # mapa de la jerarquía: sin esto solo se sabe cuántas hay, no cuáles.
    instance_cpus: tuple[tuple[int, ...], ...] = ()

    @property
    def total_bytes(self) -> int:
        return self.size_bytes * self.instances


@dataclass(frozen=True, slots=True)
class Clocks:
    current_hz: Optional[int] = None      # media de los núcleos de este tipo
    min_hz: Optional[int] = None
    max_hz: Optional[int] = None          # techo efectivo que aplica el kernel
    base_hz: Optional[int] = None
    max_turbo_hz: Optional[int] = None    # techo del silicio, según CPUID 0x16
    bus_hz: Optional[int] = None          # BCLK / reloj de referencia
    turbo_enabled: Optional[bool] = None
    driver: Optional[str] = None
    governor: Optional[str] = None
    energy_preference: Optional[str] = None    # EPP: hacia rendimiento o hacia ahorro

    def _mult(self, hz: Optional[int]) -> Optional[float]:
        if not hz or not self.bus_hz:
            return None
        return round(hz / self.bus_hz, 1)

    @property
    def multiplier(self) -> Optional[float]:
        return self._mult(self.current_hz)

    @property
    def base_multiplier(self) -> Optional[float]:
        return self._mult(self.base_hz)

    @property
    def min_multiplier(self) -> Optional[float]:
        return self._mult(self.min_hz)

    @property
    def max_multiplier(self) -> Optional[float]:
        return self._mult(self.max_hz)

    @property
    def max_turbo_multiplier(self) -> Optional[float]:
        return self._mult(self.max_turbo_hz)

    @property
    def turbo_headroom_hz(self) -> Optional[int]:
        """Cuánta frecuencia deja sin usar el techo actual frente al del silicio."""
        if self.max_turbo_hz and self.max_hz and self.max_turbo_hz > self.max_hz:
            return self.max_turbo_hz - self.max_hz
        return None


@dataclass(frozen=True, slots=True)
class Power:
    """Consumo del paquete, desglosado y con los límites del hardware.

    Un solo número deja al usuario sin saber si está bien. El desglose por
    dominio y el límite declarado por el propio procesador convierten
    "7 W" en "7 de 65 W, y casi todo son los núcleos".
    """

    package_w: Optional[float] = None
    core_w: Optional[float] = None
    uncore_w: Optional[float] = None
    dram_w: Optional[float] = None
    limit_long_w: Optional[float] = None       # PL1: el sostenido, suele ser el TDP
    limit_short_w: Optional[float] = None      # PL2: el pico de unos segundos

    @property
    def load_percent(self) -> Optional[float]:
        """Qué fracción del límite sostenido se está usando."""
        if self.package_w is None or not self.limit_long_w:
            return None
        return round(100.0 * self.package_w / self.limit_long_w, 1)


@dataclass(frozen=True, slots=True)
class LogicalCpu:
    """Una CPU lógica: un hilo, tal y como lo ve el kernel."""

    index: int
    core_id: int
    package_id: int
    type_key: str = "general"
    freq_hz: Optional[int] = None
    temp_c: Optional[float] = None
    usage_percent: Optional[float] = None


@dataclass(frozen=True, slots=True)
class CpuType:
    """Un tipo de núcleo. En una CPU homogénea hay uno; en una híbrida, dos.

    Modelar esto como lista desde el principio es deliberado: convertirlo
    después obliga a reescribir el modelo entero y toda la interfaz.
    """

    key: str                    # "general" | "performance" | "efficiency"
    label: str                  # lo decide `render`, esto es solo un identificador
    vendor: str = ""            # "Intel", "AMD"…
    vendor_id: str = ""         # "GenuineIntel"
    brand: str = ""             # cadena de marca cruda de CPUID
    codename: Optional[str] = None
    technology: Optional[str] = None
    socket: Optional[str] = None
    architecture: str = ""

    # CPUID parte la familia y el modelo en un campo base y otro extendido,
    # por razones históricas: cuando los cuatro bits del campo base se
    # agotaron, se añadieron los extendidos y hay que recomponerlos. Los
    # campos "disp" son ya la suma, que es lo que el fabricante publica en su
    # hoja de datos; los otros son los bits en crudo, útiles solo para
    # depurar. `signature` es el registro EAX entero de la hoja 1.
    family: Optional[int] = None
    model: Optional[int] = None
    stepping: Optional[int] = None
    disp_family: Optional[int] = None
    disp_model: Optional[int] = None
    signature: Optional[int] = None

    virtualization: Optional[str] = None       # "VT-x", "AMD-V" o nada
    in_virtual_machine: bool = False

    cores: int = 0
    threads: int = 0
    cpus: tuple[int, ...] = ()
    smt: bool = False

    caches: tuple[Cache, ...] = ()
    features: tuple[str, ...] = ()
    clocks: Clocks = field(default_factory=Clocks)

    temp_c: Optional[float] = None
    voltage_v: Optional[float] = None
    microcode: Optional[str] = None

    def cache_at(self, level: int, kind: str | None = None) -> Optional[Cache]:
        for c in self.caches:
            if c.level == level and (kind is None or c.kind == kind):
                return c
        return None


@dataclass(frozen=True, slots=True)
class CpuInfo:
    sockets: int = 1
    hybrid: bool = False
    types: tuple[CpuType, ...] = ()
    logical: tuple[LogicalCpu, ...] = ()
    usage_percent: Optional[float] = None
    package_temp_c: Optional[float] = None
    power: Power = field(default_factory=Power)
    load_average: tuple[float, ...] = ()       # 1, 5 y 15 minutos

    @property
    def package_power_w(self) -> Optional[float]:
        return self.power.package_w

    @property
    def total_cores(self) -> int:
        return sum(t.cores for t in self.types)

    @property
    def total_threads(self) -> int:
        return sum(t.threads for t in self.types)


# --------------------------------------------------------------------------
# Sistema
# --------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Memory:
    """Reparto de la memoria, tal y como lo cuenta /proc/meminfo.

    Hay dos formas legítimas de contar la memoria usada y conviene no
    mezclarlas:

    * `used_bytes` = total − disponible. Es la definición de `free` y la de
      cualquier monitor del sistema: «cuánta no podría recuperar aunque
      quisiera». Incluye la parte de la caché que no es recuperable, como
      tmpfs y la memoria compartida.
    * `apps_bytes` = total − libre − buffers − caché recuperable. Es la que
      permite dibujar una barra cuyos trozos suman exactamente el total.

    La primera sale siempre algo mayor que la segunda, y no es un error: la
    diferencia es justo la caché que el kernel no puede devolver.
    """

    total_bytes: int = 0
    available_bytes: int = 0
    free_bytes: int = 0
    buffers_bytes: int = 0
    cached_bytes: int = 0
    shared_bytes: int = 0
    reclaimable_bytes: int = 0          # SReclaimable: slab que sí se devuelve
    swap_total_bytes: int = 0
    swap_free_bytes: int = 0

    @property
    def used_bytes(self) -> int:
        return max(0, self.total_bytes - self.available_bytes)

    @property
    def cache_bytes(self) -> int:
        """La caché que el kernel puede devolver si alguien pide memoria."""
        return max(0, self.cached_bytes + self.reclaimable_bytes - self.shared_bytes)

    @property
    def apps_bytes(self) -> int:
        """Lo que no es ni libre, ni buffers, ni caché recuperable."""
        return max(0, self.total_bytes - self.free_bytes
                   - self.buffers_bytes - self.cache_bytes)

    @property
    def used_percent(self) -> float:
        return round(100.0 * self.used_bytes / self.total_bytes, 1) if self.total_bytes else 0.0

    @property
    def swap_used_bytes(self) -> int:
        return max(0, self.swap_total_bytes - self.swap_free_bytes)

    @property
    def swap_used_percent(self) -> float:
        if not self.swap_total_bytes:
            return 0.0
        return round(100.0 * self.swap_used_bytes / self.swap_total_bytes, 1)


@dataclass(frozen=True, slots=True)
class System:
    distribution: Optional[str] = None
    distribution_id: Optional[str] = None
    version_id: Optional[str] = None
    variant: Optional[str] = None

    kernel: Optional[str] = None
    kernel_build: Optional[str] = None
    architecture: Optional[str] = None

    hostname: Optional[str] = None
    init: Optional[str] = None
    desktop: Optional[str] = None
    session_type: Optional[str] = None
    shell: Optional[str] = None

    uptime_seconds: float = 0.0
    boot_time: Optional[str] = None

    processes: int = 0
    threads: int = 0
    open_files: int = 0

    memory: Memory = field(default_factory=Memory)


@dataclass(frozen=True, slots=True)
class MemoryModule:
    """Un zócalo de memoria, esté ocupado o no.

    Los zócalos vacíos también salen: saber que quedan dos libres es la mitad
    de la razón por la que alguien abre esta pestaña.
    """

    locator: Optional[str] = None            # "DIMM A1"
    bank: Optional[str] = None               # "P0 CHANNEL A"
    populated: bool = False
    size_bytes: int = 0
    type: Optional[str] = None               # "DDR4"
    form_factor: Optional[str] = None        # "DIMM", "SODIMM"
    details: tuple[str, ...] = ()
    speed_mts: Optional[int] = None          # lo que el módulo puede dar
    configured_mts: Optional[int] = None     # a lo que va de verdad
    manufacturer: Optional[str] = None
    part_number: Optional[str] = None
    rank: Optional[int] = None
    data_width: Optional[int] = None
    total_width: Optional[int] = None
    voltage_min_mv: Optional[int] = None
    voltage_max_mv: Optional[int] = None
    voltage_configured_mv: Optional[int] = None

    @property
    def has_ecc(self) -> Optional[bool]:
        """Si el ancho total supera al de datos, esos bits de más son ECC."""
        if self.total_width is None or self.data_width is None or not self.data_width:
            return None
        return self.total_width > self.data_width

    # Se rellena desde el chip SPD del propio módulo, cuando se puede leer.
    spd: Optional[SpdInfo] = None

    @property
    def rated_mts(self) -> Optional[int]:
        """A cuánto puede ir el módulo, no a cuánto lo han puesto.

        El SPD lo sabe de verdad; la tabla SMBIOS solo repite lo que la BIOS
        ha negociado, que sin XMP son los valores conservadores de JEDEC.
        """
        if self.spd is not None and self.spd.rated_mts:
            return self.spd.rated_mts
        return self.speed_mts

    @property
    def underclocked(self) -> bool:
        """El módulo va por debajo de lo que sabe dar."""
        actual = self.configured_mts or self.speed_mts
        rated = self.rated_mts
        return bool(actual and rated and actual < rated)


@dataclass(frozen=True, slots=True)
class MemoryArray:
    slots: Optional[int] = None
    max_capacity_bytes: int = 0
    error_correction: Optional[str] = None


@dataclass(frozen=True, slots=True)
class PrivilegedState:
    """Qué se sabe del ayudante privilegiado, para poder explicarlo."""

    supported: bool = False                  # hay pkexec y ayudante
    connected: bool = False
    already_root: bool = False
    message: Optional[str] = None            # el último fallo, si lo hubo


# --------------------------------------------------------------------------
# Placa base
# --------------------------------------------------------------------------


# Los fabricantes se identifican en DMI con su razón social completa. Nadie
# llama "Micro-Star International Co., Ltd." a una MSI.
VENDOR_ALIASES: dict[str, str] = {
    "micro-star international": "MSI",
    "asustek computer": "ASUS",
    "gigabyte technology": "Gigabyte",
    "american megatrends": "AMI",
    "hewlett-packard": "HP",
    "lenovo": "Lenovo",
    "dell inc.": "Dell",
    "asrock": "ASRock",
    "biostar": "Biostar",
    "supermicro": "Supermicro",
    "acer": "Acer",
    "notebook": "",
}


def short_vendor(name: Optional[str]) -> Optional[str]:
    if not name:
        return name
    lowered = name.lower()
    for needle, alias in VENDOR_ALIASES.items():
        if lowered.startswith(needle):
            return alias or name
    return name


_BRAND_NOISE = re.compile(r"\((?:R|TM|tm|r)\)|\bCPU\b|\bProcessor\b|@.*$|\b\d+-Core\b")


def short_brand(brand: Optional[str]) -> str:
    """"Intel(R) Core(TM) i5-10400 CPU @ 2.90GHz" -> "Intel Core i5-10400"."""
    if not brand:
        return "Procesador"
    return " ".join(_BRAND_NOISE.sub("", brand).split()) or "Procesador"


# Valores que los fabricantes dejan sin rellenar en la tabla SMBIOS. Enseñar
# "Default string" como si fuera un dato es peor que no enseñar nada.
DMI_PLACEHOLDERS = frozenset({
    "default string", "to be filled by o.e.m.", "to be filled by oem",
    "system manufacturer", "system product name", "system version",
    "not specified", "not applicable", "none", "n/a", "unknown",
    "oem", "o.e.m.", "chassis manufacturer", "chassis version",
    "0123456789", "xxxxxxxx", "empty",
})


def clean_dmi(value: Optional[str]) -> Optional[str]:
    """Descarta los rellenos que dejan las BIOS sin configurar."""
    if not value:
        return None
    return None if value.strip().lower() in DMI_PLACEHOLDERS else value.strip()


@dataclass(frozen=True, slots=True)
class Board:
    vendor: Optional[str] = None
    name: Optional[str] = None
    version: Optional[str] = None

    bios_vendor: Optional[str] = None
    bios_version: Optional[str] = None
    bios_date: Optional[str] = None
    bios_release: Optional[str] = None

    firmware: Optional[str] = None          # "UEFI (64 bits)" o "BIOS heredada"
    secure_boot: Optional[bool] = None
    tpm_version: Optional[str] = None

    chipset: Optional[str] = None           # "Intel H510"
    chipset_full: Optional[str] = None      # el nombre completo de pci.ids
    host_bridge: Optional[str] = None

    system_vendor: Optional[str] = None
    system_name: Optional[str] = None
    system_version: Optional[str] = None
    system_family: Optional[str] = None
    system_sku: Optional[str] = None

    chassis_vendor: Optional[str] = None
    chassis: Optional[str] = None

    @property
    def display_name(self) -> str:
        """Cómo se llama esto en una frase: «MSI H510M PRO-E».

        En un portátil la placa no tiene nombre comercial —un IdeaPad 330
        lleva dentro una «LNVNB161216»— y quien mira no reconoce ese código
        por ninguna parte. Ahí manda el nombre del equipo, que es el que
        viene escrito en la pegatina.
        """
        if self.chassis_is_portable and self.system_version:
            marca = short_vendor(self.system_vendor) or ""
            nombre = self.system_version
            # Lenovo escribe «Lenovo ideapad 330-15ICH» ahí dentro, con la
            # marca incluida; anteponerla otra vez da «Lenovo Lenovo ideapad».
            equipo = (nombre if nombre.lower().startswith(marca.lower() or "\0")
                      else " ".join(p for p in (marca, nombre) if p))
            # Solo si aporta: algunos fabricantes repiten ahí el código de placa.
            if equipo and (self.name or "") not in equipo:
                return equipo
        parts = [short_vendor(self.vendor), self.name]
        joined = " ".join(p for p in parts if p)
        return joined or "Placa base"

    @property
    def chassis_is_portable(self) -> bool:
        """Si el DMI dice que esto se lleva encima."""
        return (self.chassis or "").lower() in (
            "notebook", "laptop", "portátil", "portable", "sub notebook",
            "hand held", "tablet", "convertible", "detachable")

    @property
    def bios_summary(self) -> str:
        parts = [short_vendor(self.bios_vendor), self.bios_version]
        joined = " ".join(p for p in parts if p)
        return f"{joined} ({self.bios_date})" if joined and self.bios_date else joined or "—"


# --------------------------------------------------------------------------
# Sensores
# --------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class GpuMemory:
    """La VRAM de la tarjeta, y la RAM del sistema que tiene prestada."""

    total_bytes: Optional[int] = None
    used_bytes: Optional[int] = None
    # El trozo de VRAM que la CPU puede direccionar. Con Resizable BAR es toda;
    # sin él son los 256 MB de siempre, y eso cuesta rendimiento.
    visible_bytes: Optional[int] = None
    visible_used_bytes: Optional[int] = None
    # GTT: memoria del sistema que el driver le presta a la GPU cuando la VRAM
    # se queda corta. No es memoria de la tarjeta y por eso va aparte.
    gtt_total_bytes: Optional[int] = None
    gtt_used_bytes: Optional[int] = None
    vendor: Optional[str] = None
    kind: Optional[str] = None          # GDDR6, HBM2e…
    bus_bits: Optional[int] = None
    # La tasa a la que viajan los datos, que no es el reloj: una GDDR6 a
    # 1258 MHz mueve 20 Gbps. Es el número que sale en las fichas técnicas.
    data_rate_hz: Optional[int] = None
    bandwidth_bytes: Optional[int] = None

    @property
    def used_percent(self) -> Optional[float]:
        if not self.total_bytes or self.used_bytes is None:
            return None
        return round(self.used_bytes / self.total_bytes * 100, 1)

    @property
    def resizable_bar(self) -> Optional[bool]:
        """Si la CPU ve toda la VRAM de golpe en vez de por una ventana."""
        if not self.total_bytes or not self.visible_bytes:
            return None
        # Un margen pequeño: el firmware reserva unos megas para sí mismo.
        return self.visible_bytes >= self.total_bytes * 0.95


@dataclass(frozen=True, slots=True)
class PcieLink:
    """Un enlace PCIe: a cuánto va ahora y a cuánto podría ir.

    Lo usan la gráfica y los discos NVMe por igual. Vale el eslabón más lento
    de la cadena hasta el puerto raíz, no lo que declare el aparato del final.
    """

    current_speed_gts: Optional[float] = None
    current_width: Optional[int] = None
    max_speed_gts: Optional[float] = None
    max_width: Optional[int] = None

    @staticmethod
    def _generation(gts: Optional[float]) -> Optional[int]:
        if not gts:
            return None
        # 2,5 · 5 · 8 · 16 · 32 · 64 GT/s son las seis generaciones de PCIe.
        for generation, velocidad in enumerate((2.5, 5.0, 8.0, 16.0, 32.0, 64.0), start=1):
            if abs(gts - velocidad) < 0.1:
                return generation
        return None

    @property
    def generation(self) -> Optional[int]:
        return self._generation(self.current_speed_gts)

    @property
    def max_generation(self) -> Optional[int]:
        return self._generation(self.max_speed_gts)

    @property
    def downgraded(self) -> bool:
        """La tarjeta va por debajo de lo que puede.

        En reposo es lo normal (los drivers bajan el enlace para gastar menos)
        así que esto se enseña como un apunte, no como un aviso.
        """
        if self.current_speed_gts and self.max_speed_gts:
            if self.current_speed_gts < self.max_speed_gts - 0.1:
                return True
        if self.current_width and self.max_width:
            return self.current_width < self.max_width
        return False


@dataclass(frozen=True, slots=True)
class GpuClockLevel:
    """Un escalón de la tabla DPM: la GPU solo corre a estas frecuencias."""

    index: int
    hz: int
    active: bool = False


@dataclass(frozen=True, slots=True)
class GpuClocks:
    core_hz: Optional[int] = None
    memory_hz: Optional[int] = None
    core_max_hz: Optional[int] = None
    memory_max_hz: Optional[int] = None
    # El reloj al que de verdad viaja la memoria, que es el de las fichas
    # técnicas: una GDDR6 con el reloj de comando a 1258 va a 2505 efectivos.
    memory_effective_hz: Optional[int] = None
    soc_hz: Optional[int] = None
    core_levels: tuple[GpuClockLevel, ...] = ()
    memory_levels: tuple[GpuClockLevel, ...] = ()
    performance_level: Optional[str] = None   # auto, low, high, manual…


@dataclass(frozen=True, slots=True)
class GpuApi:
    """Una API gráfica y hasta dónde llega en esta máquina."""

    name: str                       # OpenGL, Vulkan, OpenCL
    version: Optional[str] = None
    device: Optional[str] = None    # cómo se llama a sí misma la tarjeta ahí
    driver: Optional[str] = None
    extra: Optional[str] = None     # GLSL, unidades de cómputo…


@dataclass(frozen=True, slots=True)
class Display:
    """Una salida de vídeo de la tarjeta, esté enchufada o no."""

    connector: str                  # DP-1, HDMI-A-1…
    connected: bool = False
    # Cuidado con esto: es el modeset del kernel, no la sesión. Con un
    # compositor Wayland al mando vale False en pantallas encendidas, así que
    # sirve en consola y en X11 pero no para afirmar que algo está en uso.
    enabled: bool = False
    # El modo preferido que declara el monitor, que es el que casi siempre
    # acaba usándose. La resolución que el compositor tenga puesta ahora mismo
    # no está en sysfs.
    width: Optional[int] = None
    height: Optional[int] = None
    refresh_hz: Optional[float] = None
    monitor: Optional[Edid] = None

    @property
    def resolution(self) -> Optional[str]:
        if not (self.width and self.height):
            return None
        return f"{self.width} × {self.height}"


@dataclass(frozen=True, slots=True)
class Gpu:
    """Una tarjeta gráfica: lo que sabe el kernel y lo que dicen las APIs."""

    index: int = 0
    name: Optional[str] = None
    vendor: Optional[str] = None
    codename: Optional[str] = None
    driver: Optional[str] = None
    driver_version: Optional[str] = None
    drm_node: Optional[str] = None      # card0, card1… no tiene por qué ir en orden
    pci_slot: Optional[str] = None
    vendor_id: Optional[int] = None
    device_id: Optional[int] = None
    subsystem_vendor_id: Optional[int] = None
    subsystem_device_id: Optional[int] = None
    subsystem_name: Optional[str] = None
    revision: Optional[int] = None
    vbios: Optional[str] = None
    unique_id: Optional[str] = None
    # None cuando no se puede decidir. No es lo mismo que no serlo: con
    # nouveau no se lee la VRAM, y por ahí una GTX 1050 acababa de
    # integrada solo porque su memoria no se pudo contar.
    integrated: Optional[bool] = None
    primary: bool = False

    memory: GpuMemory = field(default_factory=GpuMemory)
    link: PcieLink = field(default_factory=PcieLink)
    clocks: GpuClocks = field(default_factory=GpuClocks)

    busy_percent: Optional[float] = None
    memory_busy_percent: Optional[float] = None
    video_busy_percent: Optional[float] = None
    temp_c: Optional[float] = None
    hotspot_c: Optional[float] = None
    memory_temp_c: Optional[float] = None
    power_w: Optional[float] = None
    power_cap_w: Optional[float] = None
    fan_rpm: Optional[int] = None
    fan_percent: Optional[float] = None
    voltage_v: Optional[float] = None
    voltage_soc_v: Optional[float] = None
    voltage_memory_v: Optional[float] = None
    # Los reguladores de voltaje de la propia tarjeta. No están en hwmon: los
    # cuenta el microcontrolador del firmware.
    vr_gfx_c: Optional[float] = None
    vr_soc_c: Optional[float] = None
    vr_memory_c: Optional[float] = None
    # Si la tarjeta se está frenando, y por qué. Es la pregunta que se hace
    # cualquiera cuando un juego rinde menos de lo que debería.
    throttled: Optional[bool] = None
    throttle_reasons: tuple[str, ...] = ()
    compute_units: Optional[int] = None
    rops: Optional[int] = None
    shader_engines: Optional[int] = None
    asic: Optional[str] = None

    displays: tuple[Display, ...] = ()
    apis: tuple[GpuApi, ...] = ()

    @property
    def display_name(self) -> str:
        return self.name or self.codename or f"Gráfica {self.index}"

    @property
    def pci_id(self) -> Optional[str]:
        if self.vendor_id is None or self.device_id is None:
            return None
        return f"{self.vendor_id:04X}:{self.device_id:04X}"

    @property
    def subsystem_id(self) -> Optional[str]:
        if self.subsystem_vendor_id is None or self.subsystem_device_id is None:
            return None
        return f"{self.subsystem_vendor_id:04X}:{self.subsystem_device_id:04X}"

    @property
    def connected_displays(self) -> tuple[Display, ...]:
        return tuple(d for d in self.displays if d.connected)


@dataclass(frozen=True, slots=True)
class NetworkTraffic:
    """Lo que ha pasado por una interfaz, y a qué ritmo pasa ahora."""

    rx_bytes: int = 0
    tx_bytes: int = 0
    rx_packets: int = 0
    tx_packets: int = 0
    rx_errors: int = 0
    tx_errors: int = 0
    rx_dropped: int = 0
    tx_dropped: int = 0
    # Ritmo instantáneo, calculado entre dos muestreos. En bytes por segundo:
    # el modelo guarda números, y ya decidirá el render si los enseña en bits.
    rx_rate_bps: Optional[float] = None
    tx_rate_bps: Optional[float] = None

    @property
    def total_bytes(self) -> int:
        return self.rx_bytes + self.tx_bytes

    @property
    def total_rate_bps(self) -> Optional[float]:
        if self.rx_rate_bps is None and self.tx_rate_bps is None:
            return None
        return (self.rx_rate_bps or 0.0) + (self.tx_rate_bps or 0.0)

    @property
    def problems(self) -> int:
        """Paquetes que no llegaron a su destino, por el motivo que sea."""
        return self.rx_errors + self.tx_errors + self.rx_dropped + self.tx_dropped


@dataclass(frozen=True, slots=True)
class NetworkInterface:
    """Una interfaz de red: qué es, cómo está conectada y cuánto mueve."""

    name: str
    kind: str = "ethernet"          # ethernet, wifi, loopback, virtual, puente
    up: bool = False
    carrier: Optional[bool] = None  # si hay cable enchufado / asociación wifi
    mac: Optional[str] = None
    ipv4: Optional[str] = None
    netmask: Optional[str] = None
    ipv6: tuple[str, ...] = ()
    gateway: Optional[str] = None
    default_route: bool = False
    speed_mbps: Optional[int] = None
    duplex: Optional[str] = None
    mtu: Optional[int] = None
    driver: Optional[str] = None
    model: Optional[str] = None
    vendor: Optional[str] = None
    pci_slot: Optional[str] = None
    traffic: NetworkTraffic = field(default_factory=NetworkTraffic)

    @property
    def display_name(self) -> str:
        return self.model or self.name

    @property
    def active(self) -> bool:
        """Enchufada y con dirección: la que de verdad está dando servicio."""
        return self.up and bool(self.ipv4 or self.ipv6)

    @property
    def link_summary(self) -> Optional[str]:
        """«2.5 Gb/s · full», que es como se lee la negociación del enlace."""
        if not self.speed_mbps:
            return None
        if self.speed_mbps >= 1000:
            velocidad = f"{self.speed_mbps / 1000:g} Gb/s"
        else:
            velocidad = f"{self.speed_mbps} Mb/s"
        return f"{velocidad} · {self.duplex}" if self.duplex else velocidad


@dataclass(frozen=True, slots=True)
class Partition:
    """Una partición, con lo que ocupa si está montada."""

    name: str                                  # nvme0n1p2
    size_bytes: Optional[int] = None
    filesystem: Optional[str] = None
    mountpoint: Optional[str] = None
    used_bytes: Optional[int] = None
    free_bytes: Optional[int] = None

    @property
    def used_percent(self) -> Optional[float]:
        if not self.size_bytes or self.used_bytes is None:
            return None
        return round(self.used_bytes / self.size_bytes * 100, 1)

    @property
    def mounted(self) -> bool:
        return bool(self.mountpoint)


@dataclass(frozen=True, slots=True)
class DiskIo:
    """Lo que ha pasado por el disco, y a qué ritmo pasa ahora."""

    read_bytes: int = 0
    write_bytes: int = 0
    read_ops: int = 0
    write_ops: int = 0
    read_rate_bps: Optional[float] = None
    write_rate_bps: Optional[float] = None

    @property
    def total_rate_bps(self) -> Optional[float]:
        if self.read_rate_bps is None and self.write_rate_bps is None:
            return None
        return (self.read_rate_bps or 0.0) + (self.write_rate_bps or 0.0)


@dataclass(frozen=True, slots=True)
class DiskHealth:
    """El estado del disco según sus propios contadores SMART.

    Casi nada de esto se puede leer sin permisos: el kernel reserva los
    comandos de diagnóstico al administrador porque son los mismos que borran
    un disco. Por eso viene aparte y puede estar entero vacío.
    """

    power_on_hours: Optional[int] = None
    power_cycles: Optional[int] = None
    written_bytes: Optional[int] = None        # el famoso TBW
    read_bytes: Optional[int] = None
    # Cuánta vida le queda al SSD según su propio contador de desgaste, de 0
    # a 100. Los discos mecánicos no lo tienen.
    percentage_used: Optional[int] = None
    spare_percent: Optional[int] = None
    unsafe_shutdowns: Optional[int] = None
    media_errors: Optional[int] = None
    critical_warning: Optional[int] = None

    @property
    def life_left_percent(self) -> Optional[int]:
        if self.percentage_used is None:
            return None
        return max(0, 100 - self.percentage_used)

    @property
    def healthy(self) -> Optional[bool]:
        if self.critical_warning is None:
            return None
        return self.critical_warning == 0


@dataclass(frozen=True, slots=True)
class Disk:
    """Una unidad de almacenamiento."""

    name: str                                  # sda, nvme0n1
    model: Optional[str] = None
    vendor: Optional[str] = None
    firmware: Optional[str] = None
    serial: Optional[str] = None
    size_bytes: Optional[int] = None
    # HDD, SSD o NVMe. Es lo primero que se quiere saber y no está en ningún
    # campo: hay que deducirlo de si el disco gira y de por dónde va conectado.
    kind: Optional[str] = None
    transport: Optional[str] = None            # sata, nvme, usb…
    rotational: Optional[bool] = None
    logical_sector: Optional[int] = None
    physical_sector: Optional[int] = None
    scheduler: Optional[str] = None
    removable: bool = False
    pci_slot: Optional[str] = None
    link: Optional[PcieLink] = None            # solo los NVMe
    temp_c: Optional[float] = None
    partitions: tuple[Partition, ...] = ()
    io: DiskIo = field(default_factory=DiskIo)
    health: DiskHealth = field(default_factory=DiskHealth)

    @property
    def display_name(self) -> str:
        return self.model or self.name

    @property
    def used_bytes(self) -> Optional[int]:
        """Lo ocupado sumando las particiones montadas."""
        usados = [p.used_bytes for p in self.partitions if p.used_bytes is not None]
        return sum(usados) if usados else None

    @property
    def mounted_partitions(self) -> tuple[Partition, ...]:
        return tuple(p for p in self.partitions if p.mounted)


class SensorKind(str, Enum):
    TEMPERATURE = "temperature"
    VOLTAGE = "voltage"
    FAN = "fan"
    POWER = "power"
    CURRENT = "current"
    ENERGY = "energy"
    CLOCK = "clock"
    USAGE = "usage"
    MEMORY = "memory"
    NETWORK = "network"
    OTHER = "other"


UNITS: dict[str, str] = {
    SensorKind.TEMPERATURE: "°C",
    SensorKind.VOLTAGE: "V",
    SensorKind.FAN: "RPM",
    SensorKind.POWER: "W",
    SensorKind.CURRENT: "A",
    SensorKind.ENERGY: "J",
    SensorKind.CLOCK: "MHz",
    SensorKind.USAGE: "%",
    SensorKind.MEMORY: "MB",
    SensorKind.NETWORK: "KB/s",
    SensorKind.OTHER: "",
}

# El nombre de la rama en la que cae cada tipo dentro del árbol de sensores.
CATEGORIES: dict[str, str] = {
    SensorKind.VOLTAGE: "Voltajes",
    SensorKind.TEMPERATURE: "Temperaturas",
    SensorKind.FAN: "Ventiladores",
    SensorKind.POWER: "Potencias",
    SensorKind.CURRENT: "Corrientes",
    SensorKind.ENERGY: "Energía",
    SensorKind.CLOCK: "Relojes",
    SensorKind.USAGE: "Uso",
    SensorKind.MEMORY: "Ocupación",
    SensorKind.NETWORK: "Tráfico",
    SensorKind.OTHER: "Otros",
}

# Orden en que se enseñan las ramas: el mismo que usan HWMonitor y HWiNFO,
# de lo que más se consulta a lo que menos.
CATEGORY_ORDER: tuple[str, ...] = (
    "Voltajes", "Temperaturas", "Ventiladores", "Potencias",
    "Relojes", "Uso", "Ocupación", "Tráfico", "Corrientes", "Energía", "Otros",
)


@dataclass(frozen=True, slots=True)
class Sensor:
    """Una lectura suelta de un chip de sensores.

    `key` tiene que ser estable entre muestreos: es lo que permite acumular
    mínimos y máximos por sensor a lo largo de la sesión, que es la gracia de
    un monitor de hardware frente a un simple visor de valores actuales.
    """

    key: str                        # "coretemp/temp2"
    chip: str                       # nombre crudo del chip: "coretemp"
    device: str                     # el aparato: "MSI H510M PRO-E", "Core i5-10400"
    label: str                      # "Core 0", "Vcore", "CPU Fan"
    kind: SensorKind
    value: float
    low: Optional[float] = None     # umbral bajo declarado por el chip
    high: Optional[float] = None    # umbral alto
    critical: Optional[float] = None
    order: int = 0                  # para mantener el orden natural dentro de la rama
    # True cuando los umbrales no los publica el sensor y los pone silux por
    # el chip que es. Se dice en la ventana: un límite estimado y uno que
    # declara el fabricante no merecen la misma confianza.
    estimated_limits: bool = False
    # Para lo que no encaja en ningún tipo con unidad fija, como un ritmo de
    # transferencia. Es la excepción, no la norma: si algo se repite, merece su
    # propio SensorKind.
    unit_override: Optional[str] = None

    @property
    def unit(self) -> str:
        return self.unit_override or UNITS.get(self.kind, "")

    @property
    def category(self) -> str:
        return CATEGORIES.get(self.kind, "Otros")

    @property
    def alarm(self) -> bool:
        """Si la lectura ha pasado un umbral que declara el propio hardware."""
        return self.alarm_level != "ok"

    @property
    def alarm_level(self) -> str:
        """«ok», «alto» o «crítico», según lo que diga el propio hardware.

        Dos niveles y no uno porque no es lo mismo: `max` es donde el
        fabricante empieza a incomodarse y `crit` donde el equipo se apaga
        solo. Pintar los dos del mismo color deja al que mira sin saber si
        tiene que hacer algo ahora o solo estar al tanto.
        """
        if self.value is None:
            return "ok"
        if self.critical is not None and self.value >= self.critical:
            return "crítico"
        if self.high is not None and self.value > self.high:
            return "alto"
        if self.low is not None and self.value < self.low:
            return "alto"
        return "ok"


@dataclass(frozen=True, slots=True)
class DriverHint:
    """Un módulo del kernel que daría más sensores y no está cargado.

    En Linux, un monitor de hardware no está limitado por lo que puede leer
    sino por los drivers que haya cargados. Detectarlo y decirlo vale más que
    cualquier sensor extra.
    """

    module: str
    provides: str
    command: str
    caution: str = ""


# --------------------------------------------------------------------------
# Snapshot
# --------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Snapshot:
    monotonic_ns: int
    cpu: CpuInfo
    board: Board = field(default_factory=Board)
    system: System = field(default_factory=System)
    modules: tuple[MemoryModule, ...] = ()
    spd: tuple[SpdInfo, ...] = ()
    memory_array: Optional[MemoryArray] = None
    gpus: tuple[Gpu, ...] = ()
    network: tuple[NetworkInterface, ...] = ()
    disks: tuple[Disk, ...] = ()
    privileged: PrivilegedState = field(default_factory=PrivilegedState)
    sensors: tuple[Sensor, ...] = ()
    driver_hints: tuple[DriverHint, ...] = ()
    capabilities: frozenset[str] = frozenset()
    notes: tuple[Note, ...] = ()

    def sensor_tree(self) -> dict[str, dict[str, tuple[Sensor, ...]]]:
        """Dispositivo → categoría → sensores, en el orden en que se dibujan.

        Es la forma en que presentan los datos HWMonitor y HWiNFO, y no es
        casualidad: agrupar por aparato y luego por magnitud es lo que permite
        mirar «qué hace la placa» o «qué temperaturas hay» sin leerlo todo.
        """
        tree: dict[str, dict[str, list[Sensor]]] = {}
        for sensor in self.sensors:
            tree.setdefault(sensor.device, {}).setdefault(sensor.category, []).append(sensor)

        ordered: dict[str, dict[str, tuple[Sensor, ...]]] = {}
        for device, categories in tree.items():
            ordered[device] = {
                name: tuple(sorted(categories[name], key=lambda s: (s.order, s.label)))
                for name in CATEGORY_ORDER
                if name in categories
            }
        return ordered

    def notes_for(self, prefix: str) -> tuple[Note, ...]:
        return tuple(n for n in self.notes if n.path.startswith(prefix))


def to_jsonable(obj: Any) -> Any:
    """Convierte el modelo a estructuras que `json` sabe serializar.

    Se escribe a mano en lugar de usar `dataclasses.asdict` porque hay que
    incluir las propiedades calculadas (multiplicadores, totales) y ordenar
    los conjuntos para que la salida sea estable entre ejecuciones.
    """
    if is_dataclass(obj) and not isinstance(obj, type):
        out: dict[str, Any] = {}
        for f in fields(obj):
            out[f.name] = to_jsonable(getattr(obj, f.name))
        for extra in _COMPUTED.get(type(obj).__name__, ()):
            out[extra] = to_jsonable(getattr(obj, extra))
        return out
    if isinstance(obj, Enum):
        return obj.value
    if isinstance(obj, (frozenset, set)):
        return sorted(obj)
    if isinstance(obj, (list, tuple)):
        return [to_jsonable(v) for v in obj]
    if isinstance(obj, dict):
        return {k: to_jsonable(v) for k, v in obj.items()}
    return obj


_COMPUTED: dict[str, tuple[str, ...]] = {
    "Cache": ("total_bytes",),
    "Clocks": ("multiplier", "base_multiplier", "min_multiplier",
               "max_multiplier", "max_turbo_multiplier", "turbo_headroom_hz"),
    "Power": ("load_percent",),
    "GpuMemory": ("used_percent", "resizable_bar"),
    "PcieLink": ("generation", "max_generation", "downgraded"),
    "Display": ("resolution",),
    "Edid": ("diagonal_inches", "made", "refresh_range", "best_mode"),
    "VideoMode": ("label",),
    "Gpu": ("display_name", "pci_id", "subsystem_id", "connected_displays"),
    "NetworkTraffic": ("total_bytes", "total_rate_bps", "problems"),
    "NetworkInterface": ("display_name", "active", "link_summary"),
    "Partition": ("used_percent", "mounted"),
    "DiskIo": ("total_rate_bps",),
    "DiskHealth": ("life_left_percent", "healthy"),
    "Disk": ("display_name", "used_bytes", "mounted_partitions"),
    "CpuInfo": ("total_cores", "total_threads", "package_power_w"),
    "Sensor": ("unit", "category", "alarm", "alarm_level"),
    "Board": ("display_name", "bios_summary"),
    "MemoryModule": ("has_ecc", "underclocked", "rated_mts"),
    "SpdInfo": ("rated_mts",),
    "Timings": ("summary",),
    "Memory": ("used_bytes", "used_percent", "cache_bytes", "apps_bytes",
               "swap_used_bytes", "swap_used_percent"),
}
