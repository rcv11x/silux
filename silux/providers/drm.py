"""Tarjetas gráficas desde /sys/class/drm.

Es la parte ingrata que faltaba, y lo es porque aquí no hay un CPUID: cada
driver publica lo suyo donde le parece. Lo único común a todos es el nodo PCI
(fabricante, dispositivo, subsistema, enlace) y los conectores de vídeo. A
partir de ahí:

- **amdgpu** es el que más cuenta: VRAM, tabla DPM de frecuencias, uso, VBIOS
  y un hwmon completo. Casi todo lo que enseña GPU-Z sale de aquí.
- **i915 y xe** (Intel) dan las frecuencias del motor gráfico y poco más, que
  es razonable: una integrada no tiene VRAM propia ni VBIOS que enseñar.
- **nouveau** da el nodo PCI y para de contar; las NVIDIA con el driver
  propietario no publican nada en sysfs y piden NVML. Ahí se deja dicho en vez
  de enseñar una tarjeta vacía.

El nombre comercial sale de `pci.ids`, pero en las tarjetas recientes viene
ambiguo («Radeon RX 9070/9070 XT/9070 GRE» son tres modelos distintos) y quien
lo desambigua es el propio driver a través de Vulkan. Eso lo hace otro
proveedor; este deja el nombre que sabe.
"""

from __future__ import annotations

import dataclasses
import os
import pathlib
import re
from typing import Optional

from .. import amdgpu, edid, gpumetrics, pciids
from ..model import (Display, GpuClockLevel, GpuClocks, PcieLink, GpuMemory,
                      Need)
from .base import Draft, Provider, read_int, read_text

SYS_DRM = "/sys/class/drm"

# Quién fabrica el chip, que no siempre es quien vende la tarjeta.
VENDORS = {
    0x1002: "AMD",
    0x1022: "AMD",
    0x10DE: "NVIDIA",
    0x8086: "Intel",
    0x1AF4: "Red Hat",       # virtio-gpu
    0x15AD: "VMware",
    0x1234: "QEMU",
    0x1A03: "ASPEED",
    0x102B: "Matrox",
}

# Los que no publican casi nada y conviene explicar por qué.
DRIVERS_CIEGOS = {
    "nvidia": ("El driver propietario de NVIDIA no publica los datos de la tarjeta "
               "en sysfs.", "Se leen con NVML, la biblioteca que trae el propio driver."),
    "nouveau": ("nouveau no publica frecuencias ni memoria de la tarjeta sin depurar el "
                "kernel.", "Los datos completos de una NVIDIA piden el driver propietario "
                "y NVML."),
}

# «0: 500Mhz », «1: 1150Mhz *»: el asterisco marca la frecuencia en uso.
#
# Ojo con lo que hay aquí: en las tarjetas antiguas esto es una tabla DPM de
# verdad, con sus ocho escalones. En RDNA3 y RDNA4 son solo tres líneas (el
# mínimo, la frecuencia actual y el máximo), y la primera puede llegar con una
# «S:» en vez de un número: es la GPU en reposo profundo, a 0 MHz. Por eso el
# índice se acepta como texto y se descarta si no es un número.
_NIVEL_DPM = re.compile(r"^\s*(\w+)\s*:\s*([\d.]+)\s*([MG])hz\s*(\*?)", re.IGNORECASE)
# «32.0 GT/s PCIe»
_VELOCIDAD = re.compile(r"([\d.]+)\s*GT/s")
# «Navi 48 [Radeon RX 9070/9070 XT/9070 GRE]»
_NOMBRE_ENTRE_CORCHETES = re.compile(r"^(.*?)\s*\[(.+)\]\s*$")


# AMD escribe el nombre de la gráfica integrada dentro de la cadena de marca
# del procesador: «AMD Ryzen 7 7445HS w/ Radeon 740M Graphics». Hace falta
# porque pci.ids no siempre trae el comercial: al 1002:1901 lo llama
# «HawkPoint2» a secas, sin los corchetes donde suele ir.
_IGPU_EN_LA_MARCA = re.compile(r"\bw/\s+(Radeon\s+[\w\s]*?)\s*Graphics\b",
                               re.IGNORECASE)


def _igpu_de_la_cpu(draft) -> Optional[str]:
    """El nombre comercial de la integrada, si el procesador lo declara."""
    for entry in draft.types.values():
        if encaje := _IGPU_EN_LA_MARCA.search(entry.get("brand") or ""):
            return " ".join(encaje.group(1).split())
    return None


def _partir_nombre(texto: str) -> tuple[Optional[str], Optional[str]]:
    """pci.ids escribe «nombre en clave [nombre comercial]»; los separa."""
    if encaje := _NOMBRE_ENTRE_CORCHETES.match(texto):
        return encaje.group(1) or None, encaje.group(2)
    return None, texto or None


def tarjetas() -> list[pathlib.Path]:
    """Los nodos cardN, sin los conectores (que se llaman cardN-DP-1)."""
    raiz = pathlib.Path(SYS_DRM)
    if not raiz.is_dir():
        return []
    encontradas = [p for p in raiz.glob("card*") if re.fullmatch(r"card\d+", p.name)]
    return sorted(encontradas, key=lambda p: int(p.name[4:]))


class DrmGpus(Provider):
    """Identidad, memoria, enlace y salidas de vídeo. Todo lo que no cambia."""

    name = "drm-gpus"
    provides = "gpus"
    static = True

    def available(self) -> bool:
        return os.path.isdir(SYS_DRM)

    def unavailable_reason(self):
        if self.available():
            return None
        return ("gpus", Need.PLATFORM,
                "El kernel no expone /sys/class/drm.",
                "Sin el subsistema DRM no hay forma de enumerar las gráficas.")

    def collect(self, draft: Draft) -> None:
        nodos = tarjetas()
        if not nodos:
            draft.note(
                "gpus", Need.HARDWARE,
                "No hay ninguna tarjeta gráfica registrada en el kernel.",
                "Pasa en servidores sin salida de video y en máquinas virtuales "
                "sin gráfica emulada.",
            )
            return

        draft.capabilities.add("drm")
        for indice, nodo in enumerate(nodos):
            dispositivo = nodo / "device"
            gpu = draft.gpu(indice)
            gpu["drm_node"] = nodo.name
            gpu["pci_slot"] = _ranura(dispositivo)
            gpu["driver"] = _driver(dispositivo)
            gpu["primary"] = read_int(f"{dispositivo}/boot_vga") == 1

            self._identidad(gpu, dispositivo)
            gpu["link"] = _enlace(dispositivo)
            gpu["memory"] = _memoria_total(dispositivo)
            gpu["displays"] = _salidas(nodo.name)
            self._preguntar_al_driver(gpu, dispositivo)
            gpu["integrated"] = _es_integrada(gpu)

            aviso = DRIVERS_CIEGOS.get(gpu["driver"] or "")
            if aviso:
                draft.note(f"gpus.{indice}", Need.DRIVER, *aviso)

        _nombrar_monitores(draft.gpus)

    @staticmethod
    def _preguntar_al_driver(gpu: dict, dispositivo: pathlib.Path) -> None:
        """Lo que amdgpu solo suelta por ioctl: memoria, unidades y ROP."""
        if gpu.get("driver") != "amdgpu":
            return
        nodo = amdgpu.render_node(dispositivo)
        if not nodo:
            return
        info = amdgpu.query(nodo, expected_device_id=gpu.get("device_id"))
        if info is None:
            return

        gpu["memory"] = dataclasses.replace(
            gpu.get("memory") or GpuMemory(),
            kind=info.vram_type,
            bus_bits=info.vram_bits,
            data_rate_hz=info.memory_data_rate_hz,
            bandwidth_bytes=info.bandwidth_bytes,
        )
        gpu["compute_units"] = info.compute_units or gpu.get("compute_units")
        gpu["rops"] = info.rops
        gpu["shader_engines"] = info.shader_engines
        # Con guion bajo porque no es un campo del modelo: solo lo usa
        # _es_integrada y el congelado descarta lo que no reconoce.
        gpu["_is_apu"] = info.is_apu

    @staticmethod
    def _identidad(gpu: dict, dispositivo: pathlib.Path) -> None:
        vendor_id = _hex(dispositivo / "vendor")
        device_id = _hex(dispositivo / "device")
        gpu["vendor_id"] = vendor_id
        gpu["device_id"] = device_id
        gpu["subsystem_vendor_id"] = _hex(dispositivo / "subsystem_vendor")
        gpu["subsystem_device_id"] = _hex(dispositivo / "subsystem_device")
        gpu["revision"] = _hex(dispositivo / "revision")
        gpu["vbios"] = read_text(f"{dispositivo}/vbios_version")
        gpu["unique_id"] = read_text(f"{dispositivo}/unique_id")
        gpu["vendor"] = VENDORS.get(vendor_id or -1)

        if vendor_id is None or device_id is None:
            return
        sub = (gpu["subsystem_vendor_id"], gpu["subsystem_device_id"])
        subsistema = ()
        if all(v is not None for v in sub):
            subsistema = ((vendor_id, device_id, sub[0], sub[1]),)   # type: ignore[assignment]

        nombres = pciids.lookup([(vendor_id, device_id)], subsystems=subsistema)
        if encontrado := nombres.get((vendor_id, device_id)):
            marca, modelo = encontrado
            gpu["vendor"] = gpu["vendor"] or marca
            gpu["codename"], gpu["name"] = _partir_nombre(modelo)

        if subsistema and (encontrado := nombres.get(subsistema[0])):
            # Quien montó la tarjeta y cómo la llamó. Esto es lo que convierte
            # «Radeon RX 9070/9070 XT/9070 GRE» (tres modelos) en el que hay.
            fabricante, modelo = encontrado
            gpu["subsystem_name"] = fabricante or None
            clave, comercial = _partir_nombre(modelo)
            gpu["name"] = comercial or gpu.get("name")
            gpu["codename"] = gpu.get("codename") or clave

        # Lo que pci.ids dejó sin nombre comercial. Solo se toca lo que sigue
        # llamándose por su nombre en clave: si ya pone «Radeon» algo, ese
        # nombre salió de la base de datos y es más concreto que este.
        if (gpu.get("vendor") == "AMD"
                and "radeon" not in (gpu.get("name") or "").lower()
                and (integrada := _igpu_de_la_cpu(draft))):
            gpu["codename"] = gpu.get("codename") or gpu.get("name")
            gpu["name"] = integrada


def _es_integrada(gpu: dict) -> Optional[bool]:
    """Si la gráfica va pegada al procesador o es una tarjeta aparte.

    Antes se decidía por la VRAM: sin memoria propia, integrada. Pero no leer
    la memoria no significa que no la haya —con nouveau no se lee ninguna— y
    así una GeForce GTX 1050 Mobile, que es una tarjeta dedicada de las de
    verdad, aparecía como integrada. Y al revés: una APU reserva un trozo de
    la RAM del sistema, así que parece tener memoria propia y salía dedicada.

    Cada fabricante lo dice a su manera, y lo que no se pueda decidir se queda
    sin decidir en vez de contestar por descarte.
    """
    fabricante = gpu.get("vendor") or ""
    ranura = gpu.get("pci_slot") or ""

    # AMD lo publica en el ioctl: el bit FUSION dice que el chip está fusionado
    # con el procesador. No hay nada más fiable.
    if (apu := gpu.get("_is_apu")) is not None:
        return apu

    if fabricante == "Intel":
        # La integrada de Intel vive siempre en la función 0 del dispositivo 2
        # del bus 0. Una Arc dedicada va en otro bus, detrás de un puente.
        return ranura.endswith(":00:02.0")

    if fabricante == "NVIDIA":
        # En un PC no hay ninguna integrada de NVIDIA; las que van pegadas al
        # procesador son los Tegra, que no llevan este driver.
        return False

    return None


class GpuState(Provider):
    """Lo que cambia: uso, VRAM ocupada, frecuencias y sensores propios."""

    name = "gpu-state"
    provides = "gpus.load"

    def available(self) -> bool:
        return os.path.isdir(SYS_DRM)

    def collect(self, draft: Draft) -> None:
        for indice, gpu in enumerate(draft.gpus):
            nodo = gpu.get("drm_node")
            if not nodo:
                continue
            dispositivo = pathlib.Path(f"{SYS_DRM}/{nodo}/device")
            if not dispositivo.is_dir():
                continue

            gpu["busy_percent"] = _porcentaje(dispositivo / "gpu_busy_percent")
            gpu["memory_busy_percent"] = _porcentaje(dispositivo / "mem_busy_percent")
            gpu["video_busy_percent"] = _porcentaje(dispositivo / "vcn_busy_percent")
            gpu["memory"] = _memoria_usada(dispositivo, gpu.get("memory") or GpuMemory())
            gpu["link"] = _enlace(dispositivo, gpu.get("link") or PcieLink())
            gpu["clocks"] = _relojes(dispositivo)
            _sensores(gpu, dispositivo)
            _telemetria(gpu, dispositivo)


# -- lectura de campos -------------------------------------------------------

def _hex(ruta: pathlib.Path) -> Optional[int]:
    crudo = read_text(str(ruta))
    if not crudo:
        return None
    try:
        return int(crudo, 16)
    except ValueError:
        return None


def _porcentaje(ruta: pathlib.Path) -> Optional[float]:
    valor = read_int(str(ruta))
    return float(valor) if valor is not None else None


def _ranura(dispositivo: pathlib.Path) -> Optional[str]:
    try:
        return dispositivo.resolve().name          # 0000:0c:00.0
    except OSError:
        return None


def _driver(dispositivo: pathlib.Path) -> Optional[str]:
    enlace = dispositivo / "driver"
    try:
        return enlace.resolve().name if enlace.exists() else None
    except OSError:
        return None


def _cadena_pcie(dispositivo: pathlib.Path) -> list[pathlib.Path]:
    """El dispositivo y todos los puentes por los que pasa hasta la raíz.

    Hace falta la cadena entera porque el enlace que vale es el del eslabón más
    lento. Las tarjetas modernas traen un conmutador PCIe dentro, y su lado
    interno negocia a la velocidad del chip aunque el puerto de la placa no dé
    para tanto: una RX 9070 XT en una X570 dice 32 GT/s de puertas adentro
    mientras habla con el sistema a 16. Enseñar el número de dentro es decirle
    al usuario que tiene PCIe 5.0 en una placa que no lo tiene.
    """
    # El propio dispositivo entra siempre, tenga o no forma de dirección PCI:
    # una gráfica de un SoC cuelga del árbol de plataforma y no de un bus PCI,
    # y ahí lo único que hay es lo que publique ella misma.
    actual = dispositivo.resolve()
    eslabones = [actual]
    actual = actual.parent
    while re.fullmatch(r"[0-9a-f]{4}:[0-9a-f]{2}:[0-9a-f]{2}\.[0-9a-f]", actual.name):
        eslabones.append(actual)
        actual = actual.parent
    return eslabones


def _enlace(dispositivo: pathlib.Path, previo: Optional[PcieLink] = None) -> PcieLink:
    def velocidad(nodo: pathlib.Path, nombre: str) -> Optional[float]:
        crudo = read_text(f"{nodo}/{nombre}")
        if not crudo:
            return None
        encaje = _VELOCIDAD.search(crudo)
        return float(encaje.group(1)) if encaje else None

    def minimo(nombre: str, leer) -> Optional[float]:
        valores = [v for nodo in _cadena_pcie(dispositivo)
                   if (v := leer(nodo, nombre)) is not None]
        return min(valores) if valores else None

    ancho = lambda nodo, nombre: read_int(f"{nodo}/{nombre}")
    maxima = (previo.max_speed_gts if previo else None) or minimo("max_link_speed", velocidad)
    max_ancho = (previo.max_width if previo else None) or minimo("max_link_width", ancho)
    return PcieLink(
        current_speed_gts=minimo("current_link_speed", velocidad),
        current_width=(lambda v: int(v) if v is not None else None)(minimo("current_link_width", ancho)),
        # El techo no cambia; en el remuestreo se conserva el que ya se leyó.
        max_speed_gts=maxima,
        max_width=int(max_ancho) if max_ancho is not None else None,
    )


def _memoria_total(dispositivo: pathlib.Path) -> GpuMemory:
    return GpuMemory(
        total_bytes=read_int(f"{dispositivo}/mem_info_vram_total"),
        visible_bytes=read_int(f"{dispositivo}/mem_info_vis_vram_total"),
        gtt_total_bytes=read_int(f"{dispositivo}/mem_info_gtt_total"),
        vendor=read_text(f"{dispositivo}/mem_info_vram_vendor"),
    )


def _memoria_usada(dispositivo: pathlib.Path, previa: GpuMemory) -> GpuMemory:
    return dataclasses.replace(
        previa,
        used_bytes=read_int(f"{dispositivo}/mem_info_vram_used"),
        visible_used_bytes=read_int(f"{dispositivo}/mem_info_vis_vram_used"),
        gtt_used_bytes=read_int(f"{dispositivo}/mem_info_gtt_used"),
    )


def _niveles(ruta: pathlib.Path) -> tuple[GpuClockLevel, ...]:
    """La tabla DPM: la GPU no va a cualquier frecuencia, solo a estas."""
    crudo = read_text(str(ruta))
    if not crudo:
        return ()
    niveles = []
    for linea in crudo.splitlines():
        encaje = _NIVEL_DPM.match(linea)
        if not encaje or not encaje.group(1).isdigit():
            continue
        escala = 1_000_000_000 if encaje.group(3).upper() == "G" else 1_000_000
        niveles.append(GpuClockLevel(
            index=int(encaje.group(1)),
            hz=int(float(encaje.group(2)) * escala),
            active=bool(encaje.group(4)),
        ))
    return tuple(niveles)


def _primero(*candidatos: Optional[int]) -> Optional[int]:
    """El primero que exista, aunque valga cero.

    Con `or` se perdía la lectura más interesante que hay: una GPU parada de
    verdad marca 0 MHz, y eso no es un dato ausente, es la respuesta.
    """
    return next((c for c in candidatos if c is not None), None)


def _relojes(dispositivo: pathlib.Path) -> GpuClocks:
    nucleo = _niveles(dispositivo / "pp_dpm_sclk")
    memoria = _niveles(dispositivo / "pp_dpm_mclk")
    hwmon = _hwmon(dispositivo)
    frecuencias = _etiquetadas(hwmon, "freq")

    # La frecuencia instantánea la da hwmon; la línea marcada con asterisco es
    # más gruesa pero está cuando no hay hwmon, como en las Intel.
    activo = lambda niveles: next((n.hz for n in niveles if n.active), None)
    return GpuClocks(
        core_hz=_primero(frecuencias.get("sclk"), activo(nucleo),
                         _intel_hz(dispositivo, "cur")),
        memory_hz=_primero(frecuencias.get("mclk"), activo(memoria)),
        core_max_hz=_primero(max((n.hz for n in nucleo), default=None),
                             _intel_hz(dispositivo, "max")),
        memory_max_hz=max((n.hz for n in memoria), default=None),
        core_levels=nucleo,
        memory_levels=memoria,
        performance_level=read_text(f"{dispositivo}/power_dpm_force_performance_level"),
    )


def _intel_hz(dispositivo: pathlib.Path, cual: str) -> Optional[int]:
    """i915 publica las frecuencias del motor gráfico en megahercios sueltos."""
    mhz = read_int(f"{dispositivo}/gt_{cual}_freq_mhz")
    if mhz is None:
        # xe, el driver nuevo de Intel, las mueve dentro de la jerarquía de gt.
        mhz = read_int(f"{dispositivo}/tile0/gt0/freq0/{cual}_freq")
    return mhz * 1_000_000 if mhz else None


# -- hwmon de la propia tarjeta ---------------------------------------------

def _hwmon(dispositivo: pathlib.Path) -> Optional[pathlib.Path]:
    directorio = dispositivo / "hwmon"
    if not directorio.is_dir():
        return None
    return next(iter(sorted(directorio.glob("hwmon*"))), None)


def _etiquetadas(hwmon: Optional[pathlib.Path], prefijo: str) -> dict[str, int]:
    """Los canales de hwmon que traen etiqueta, indexados por ella.

    Las tarjetas no ponen las temperaturas en el mismo orden, así que buscarlas
    por número (`temp1`, `temp2`) es lotería; por etiqueta (`edge`, `junction`,
    `mem`) siempre cae donde toca.
    """
    if hwmon is None:
        return {}
    valores = {}
    for etiqueta in sorted(hwmon.glob(f"{prefijo}*_label")):
        nombre = read_text(str(etiqueta))
        entrada = read_int(str(etiqueta).replace("_label", "_input"))
        if nombre and entrada is not None:
            valores[nombre.lower()] = entrada
    return valores


def _sensores(gpu: dict, dispositivo: pathlib.Path) -> None:
    hwmon = _hwmon(dispositivo)
    if hwmon is None:
        return

    temperaturas = _etiquetadas(hwmon, "temp")
    mili = lambda v: round(v / 1000, 1) if v is not None else None
    gpu["temp_c"] = mili(temperaturas.get("edge"))
    gpu["hotspot_c"] = mili(_primero(temperaturas.get("junction"),
                                     temperaturas.get("hotspot")))
    gpu["memory_temp_c"] = mili(_primero(temperaturas.get("mem"),
                                         temperaturas.get("vram")))

    if gpu["temp_c"] is None:
        # Las Intel y las virtuales no etiquetan: ahí el primer canal es el bueno.
        gpu["temp_c"] = mili(read_int(f"{hwmon}/temp1_input"))

    micro = _primero(read_int(f"{hwmon}/power1_average"),
                     read_int(f"{hwmon}/power1_input"))
    gpu["power_w"] = round(micro / 1_000_000, 1) if micro is not None else None
    tope = read_int(f"{hwmon}/power1_cap")
    gpu["power_cap_w"] = round(tope / 1_000_000, 1) if tope is not None else None

    gpu["fan_rpm"] = read_int(f"{hwmon}/fan1_input")
    pwm = read_int(f"{hwmon}/pwm1")
    maximo = read_int(f"{hwmon}/pwm1_max") or 255
    gpu["fan_percent"] = round(pwm / maximo * 100, 1) if pwm is not None else None

    voltajes = _etiquetadas(hwmon, "in")
    milivoltios = _primero(voltajes.get("vddgfx"), voltajes.get("vddnb"))
    gpu["voltage_v"] = round(milivoltios / 1000, 3) if milivoltios is not None else None


def _telemetria(gpu: dict, dispositivo: pathlib.Path) -> None:
    """Lo que solo cuenta el firmware: por qué se frena y a cuánto va de verdad.

    Se aplica encima de lo leído en hwmon, no en lugar de ello: hwmon está en
    todas las tarjetas y esto solo en las AMD recientes, así que lo que hace es
    completar los huecos y añadir lo suyo.
    """
    medidas = gpumetrics.read(dispositivo)
    if medidas is None:
        return

    gpu["throttled"] = medidas.throttled
    gpu["throttle_reasons"] = medidas.throttle_reasons
    gpu["vr_gfx_c"] = medidas.temp_vr_gfx_c
    gpu["vr_soc_c"] = medidas.temp_vr_soc_c
    gpu["vr_memory_c"] = medidas.temp_vr_mem_c
    gpu["voltage_soc_v"] = medidas.voltage_soc_v
    gpu["voltage_memory_v"] = medidas.voltage_memory_v

    relojes: GpuClocks = gpu.get("clocks") or GpuClocks()
    gpu["clocks"] = dataclasses.replace(
        relojes,
        memory_effective_hz=medidas.memory_clock_effective_hz,
        soc_hz=medidas.soc_clock_hz,
        core_hz=_primero(relojes.core_hz, medidas.gfx_clock_hz),
        memory_hz=_primero(relojes.memory_hz, medidas.memory_clock_hz),
    )
    for campo, valor in (("busy_percent", medidas.gfx_activity_percent),
                         ("memory_busy_percent", medidas.memory_activity_percent),
                         ("video_busy_percent", medidas.video_activity_percent),
                         ("temp_c", medidas.temp_edge_c),
                         ("hotspot_c", medidas.temp_hotspot_c),
                         ("memory_temp_c", medidas.temp_memory_c),
                         ("power_w", medidas.socket_power_w),
                         ("voltage_v", medidas.voltage_gfx_v)):
        if gpu.get(campo) is None and valor is not None:
            gpu[campo] = valor


def _salidas(tarjeta: str) -> tuple[Display, ...]:
    """Los conectores de vídeo de esta tarjeta, enchufados o no."""
    raiz = pathlib.Path(SYS_DRM)
    salidas = []
    for conector in sorted(raiz.glob(f"{tarjeta}-*")):
        nombre = conector.name[len(tarjeta) + 1:]
        if nombre.startswith("Writeback"):
            continue                   # no es una salida, es un destino interno
        estado = (read_text(f"{conector}/status") or "").lower()
        chapa = edid.read(conector)
        ancho = alto = None
        if chapa and chapa.native_width:
            # El EDID manda sobre `modes`: dice la resolución nativa de verdad.
            ancho, alto = chapa.native_width, chapa.native_height
        elif modos := read_text(f"{conector}/modes"):
            # La primera línea es el modo preferido del monitor.
            primera = modos.splitlines()[0].strip()
            if encaje := re.fullmatch(r"(\d+)x(\d+)\D*", primera):
                ancho, alto = int(encaje.group(1)), int(encaje.group(2))
        salidas.append(Display(
            connector=nombre,
            connected=estado == "connected",
            enabled=(read_text(f"{conector}/enabled") or "").lower() == "enabled",
            width=ancho,
            height=alto,
            refresh_hz=chapa.native_refresh_hz if chapa else None,
            monitor=chapa,
        ))
    return tuple(salidas)


def _nombrar_monitores(gpus: list[dict]) -> None:
    """Traduce las tres letras del EDID a nombres, para todas las pantallas.

    Se hace al final y de una vez porque `pnp.ids` son 63 kB que no merece la
    pena recorrer una vez por monitor.
    """
    chapas = [d.monitor for gpu in gpus for d in gpu.get("displays", ()) if d.monitor]
    if not chapas:
        return
    nombres = edid.resolve_vendors(chapas)
    if not nombres:
        return
    for gpu in gpus:
        gpu["displays"] = tuple(
            dataclasses.replace(salida, monitor=dataclasses.replace(
                salida.monitor,
                manufacturer=nombres.get(salida.monitor.manufacturer_id)))
            if salida.monitor else salida
            for salida in gpu.get("displays", ())
        )
