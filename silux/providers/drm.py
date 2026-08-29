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
import time
from typing import Optional

from .. import amdgpu, edid, gpumetrics, pciids
from ..model import (Display, GpuClockLevel, GpuClocks, GpuEngine, PcieLink, GpuMemory,
                      Need)
from ..privileged.client import HelperError, PmuUnsupported, PrivilegedClient
from .base import Draft, Provider, read_int, read_text
from ..i18n import _

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
    "nvidia": ("prov.drm.nvidia", "prov.drm.nvidia.hint"),
    "nouveau": ("prov.drm.nouveau", "prov.drm.nouveau.hint"),
    # i915 y xe no están aquí a propósito: su aviso lo pone GpuState, porque
    # depende de si el usuario ha elevado permisos y eso cambia a mitad de
    # sesión. Esta tabla la lee un proveedor estático, que corre una sola vez.
}

# Lo que una gráfica Intel no da por ningún camino. Comprobado contra una UHD
# 630 con i915: el nodo DRM no tiene hwmon, y su PMU no publica ningún evento
# de energía, así que ni temperatura ni vatios.
#
# Se probó además el atajo que parecía obvio —el dominio «uncore» de RAPL, que
# en los Intel de sobremesa parecía ser el plano de la gráfica— y no lo es: se
# queda clavado en 3,2 W mientras el reloj del motor gráfico va de 350 a
# 1050 MHz. Habría sido un dato creíble y falso.
INTEL_SIN_TEMPERATURA = "prov.drm.inteltemp"

# El uso y el consumo sí existen, pero solo como contadores del kernel. Los lee
# el ayudante privilegiado, el mismo que ya pide permisos una vez para los
# discos.
#
# Aquí NO se le dice al usuario que baje /proc/sys/kernel/perf_event_paranoid.
# Es un cerrojo de todo el sistema —a 0 cualquier proceso sin privilegios puede
# perfilar la máquina entera—, y bajarlo para ver un porcentaje no compensa.
# Comprobado además que el valor intermedio, 1, tampoco sirve.
INTEL_AVISOS = {
    "root": ("prov.drm.intelroot", "prov.drm.intelroot.hint"),
    "driver": (INTEL_SIN_TEMPERATURA, "prov.drm.inteldriver.hint"),
    "hardware": (INTEL_SIN_TEMPERATURA, "prov.drm.intelhw.hint"),
}

# Cómo llama el kernel a cada motor y qué hace. El prefijo del nombre basta:
# rcs0 es el de dibujo, vcs1 el segundo decodificador de video.
MOTORES_INTEL = {
    "rcs": "engine.render",
    "ccs": "engine.compute",
    "bcs": "engine.copy",
    "vcs": "engine.video",
    "vecs": "engine.videoenhance",
}

# El plano de energía de la gráfica en RAPL. Es el de la integrada del
# procesador, así que no se le cuelga a una dedicada aunque sea Intel.
PMU_ENERGIA = ("power", "energy-gpu")

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
                _("prov.drm.nosysfs"), _("prov.drm.nosysfs.hint"))

    def collect(self, draft: Draft) -> None:
        nodos = tarjetas()
        if not nodos:
            draft.note(
                "gpus", Need.HARDWARE,
                _("prov.drm.nogpu"), _("prov.drm.nogpu.hint"),
            )
            return

        draft.capabilities.add("drm")
        # Se enumera una vez y se van repartiendo: con dos tarjetas y ningún
        # driver, la primera ficha se queda con la primera del bus.
        sin_driver = _graficas_del_bus()
        for indice, nodo in enumerate(nodos):
            dispositivo = nodo / "device"
            gpu = draft.gpu(indice)
            gpu["drm_node"] = nodo.name
            gpu["pci_slot"] = _ranura(dispositivo)
            gpu["driver"] = _driver(dispositivo)
            gpu["primary"] = read_int(f"{dispositivo}/boot_vga") == 1

            self._identidad(gpu, dispositivo)
            if gpu["driver"] in FRAMEBUFFER_GENERICO or not gpu.get("vendor_id"):
                self._identidad_del_bus(gpu, draft, indice, sin_driver)
            if gpu["driver"] in ("i915", "xe"):
                gpu["engines"] = _motores_intel(nodo)
            gpu["link"] = _enlace(dispositivo)
            gpu["memory"] = _memoria_total(dispositivo)
            gpu["displays"] = _salidas(nodo.name)
            self._preguntar_al_driver(gpu, dispositivo)
            gpu["integrated"] = _es_integrada(gpu)

            aviso = DRIVERS_CIEGOS.get(gpu["driver"] or "")
            if aviso:
                draft.note(f"gpus.{indice}", Need.DRIVER,
                           *(_(clave) for clave in aviso))

        _nombrar_monitores(draft.gpus)

    def _identidad_del_bus(self, gpu: dict, draft: Draft, indice: int,
                           candidatas: list) -> None:
        """Quién es la tarjeta cuando el nodo DRM no lo sabe.

        El framebuffer de respaldo cuelga de un dispositivo de plataforma, no
        del PCI, así que no hay `vendor` ni `device` que leer y la ficha salía
        entera a guiones: ni el nombre de la tarjeta, que es lo primero que uno
        mira. El bus sí la enumera, con driver o sin él.
        """
        if not candidatas:
            return
        dispositivo = candidatas.pop(0)
        self._identidad(gpu, dispositivo)
        gpu["pci_slot"] = dispositivo.name
        # El nodo DRM sigue siendo el del framebuffer; el enlace y la memoria
        # se leen del dispositivo de verdad, que es quien los tiene.
        gpu["link"] = _enlace(dispositivo)
        gpu["integrated"] = _es_integrada(gpu)
        draft.note(f"gpus.{indice}", Need.DRIVER,
                   _("prov.drm.nodriver").format(
                       tarjeta=gpu.get("name") or _("prov.drm.thiscard")),
                   _("prov.drm.nodriver.hint"))

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

        # pci.ids solo trae la línea del subsistema completo para las
        # combinaciones que alguien se ha molestado en añadir, y una placa
        # reciente rara vez está. El fabricante suelto sí: decir quién montó
        # la tarjeta vale más que un guion.
        if not gpu.get("subsystem_name") and sub and sub[0] is not None:
            gpu["subsystem_name"] = pciids.vendor_name(sub[0])

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

    def __init__(self, client: Optional[PrivilegedClient] = None) -> None:
        # El colector reparte un único cliente entre todos los que lo piden:
        # dos serían dos diálogos de polkit para la misma contraseña. Si no
        # llega ninguno, sencillamente no hay contadores que leer.
        self.client = client
        # (reloj, contadores) de la vuelta anterior, para restar. Los del PMU
        # son acumulativos: un valor suelto no dice nada.
        self._pmu_previo: Optional[tuple[int, dict]] = None
        self._pmu_ok = False
        self._pmu_mudo = False
        # El contador de reposo es acumulativo, igual que los del PMU, pero
        # este sale de sysfs y no cuesta permisos.
        self._rc6: dict[str, tuple[float, int]] = {}

    def available(self) -> bool:
        return os.path.isdir(SYS_DRM)

    def collect(self, draft: Draft) -> None:
        ocupacion, vatios = self._contadores()
        for indice, gpu in enumerate(draft.gpus):
            nodo = gpu.get("drm_node")
            if not nodo:
                continue
            raiz = pathlib.Path(f"{SYS_DRM}/{nodo}")
            dispositivo = raiz / "device"
            if not dispositivo.is_dir():
                continue

            gpu["busy_percent"] = _porcentaje(dispositivo / "gpu_busy_percent")
            gpu["memory_busy_percent"] = _porcentaje(dispositivo / "mem_busy_percent")
            gpu["video_busy_percent"] = _porcentaje(dispositivo / "vcn_busy_percent")
            gpu["memory"] = _memoria_usada(dispositivo, gpu.get("memory") or GpuMemory())
            gpu["link"] = _enlace(dispositivo, gpu.get("link") or PcieLink())
            gpu["clocks"] = _relojes(dispositivo, raiz)
            _sensores(gpu, dispositivo)
            _telemetria(gpu, dispositivo)

            if gpu.get("driver") in ("i915", "xe"):
                gpu["sleep_percent"] = self._reposo(nodo, raiz)
                _uso_intel(gpu, ocupacion)
                # Solo a la integrada: el plano de energía es el que el
                # procesador reserva para su gráfica, y colgárselo a una
                # dedicada sería atribuirle el consumo de otra.
                if vatios is not None and gpu.get("integrated"):
                    gpu["power_w"] = vatios
                self._avisar_de_intel(draft, indice)

    # -- el contador de ocupación del kernel --------------------------------

    def _contadores(self) -> tuple[Optional[dict[str, dict[str, float]]],
                                   Optional[float]]:
        """La ocupación de cada motor en tanto por ciento, y los vatios.

        El ayudante devuelve contadores acumulados desde que los abrió; lo que
        interesa sale de restar contra la vuelta anterior y dividir por lo que
        ha durado la ventana. La primera lectura solo fija la referencia y
        todavía no da número, igual que el uso de CPU.
        """
        cliente = self.client
        if self._pmu_mudo or cliente is None or not cliente.connected():
            return None, None

        try:
            reloj, crudo, escalas = cliente.gpu_pmu()
        except PmuUnsupported:
            # Esta máquina no tiene contadores de gráfica: no se vuelve a
            # preguntar en cada muestreo por algo que no va a aparecer.
            self._pmu_mudo = True
            return None, None
        except HelperError:
            # Un fallo suelto no lo da por perdido: la tubería puede haberse
            # cortado y el usuario volver a autorizar.
            return None, None

        self._pmu_ok = True
        previo, self._pmu_previo = self._pmu_previo, (reloj, crudo)
        if previo is None:
            return None, None
        reloj_previo, crudo_previo = previo
        ventana = reloj - reloj_previo
        if ventana <= 0:
            return None, None

        salida: dict[str, dict[str, float]] = {}
        vatios = None
        for pmu, eventos in crudo.items():
            anteriores = crudo_previo.get(pmu, {})
            for evento, valor in eventos.items():
                antes = anteriores.get(evento)
                if antes is None or valor < antes:
                    continue                  # contador nuevo o reiniciado
                if (pmu, evento) == PMU_ENERGIA:
                    escala = escalas.get(pmu, {}).get(evento)
                    if escala:
                        # El contador va en julios una vez escalado, y un
                        # vatio es un julio por segundo.
                        vatios = (valor - antes) * escala * 1e9 / ventana
                    continue
                # Se recorta a 100: en ventanas muy cortas el contador y el
                # reloj no arrancan alineados y sale algo más.
                porcentaje = (valor - antes) * 100.0 / ventana
                salida.setdefault(pmu, {})[evento] = min(100.0, max(0.0, porcentaje))
        return salida, vatios

    def _reposo(self, nodo: str, raiz: pathlib.Path) -> Optional[float]:
        """Cuánto del intervalo ha estado la gráfica dormida del todo.

        Es el RC6 de Intel, y sale de sysfs sin pedir permisos: un contador de
        milisegundos acumulados que hay que restar contra la vuelta anterior.
        No es «cien menos el uso»: entre trabajar y dormir hay un término
        medio —encendida y esperando— que gasta y que aquí no cuenta.
        """
        acumulado = _primero(read_int(f"{raiz}/gt/gt0/rc6_residency_ms"),
                             read_int(f"{raiz}/power/rc6_residency_ms"))
        if acumulado is None:
            return None
        ahora = time.monotonic()
        previo, self._rc6[nodo] = self._rc6.get(nodo), (ahora, acumulado)
        if previo is None:
            return None
        antes, dormido = previo
        ventana = (ahora - antes) * 1000.0
        if ventana <= 0 or acumulado < dormido:
            return None
        return min(100.0, max(0.0, (acumulado - dormido) * 100.0 / ventana))

    def _avisar_de_intel(self, draft: Draft, indice: int) -> None:
        """Por qué esa tarjeta tiene huecos, según lo que se pueda leer hoy."""
        if self._pmu_mudo:
            clave = "driver"
        elif self._pmu_ok:
            clave = "hardware"
        else:
            clave = "root"
        draft.note(f"gpus.{indice}", NEED_INTEL[clave],
                   *(_(k) for k in INTEL_AVISOS[clave]))


NEED_INTEL = {"root": Need.ROOT, "driver": Need.DRIVER, "hardware": Need.HARDWARE}


def _motores_intel(raiz: pathlib.Path) -> tuple[GpuEngine, ...]:
    """Qué motores tiene la tarjeta y qué sabe hacer cada uno.

    Sale de `engine/` en el nodo DRM y no cuesta permisos: es identidad, no
    telemetría. Las capacidades importan —`hevc` dice que decodifica H.265 por
    hardware y `sfc` que trae escalador—, y no salen por ningún otro sitio.
    """
    carpeta = raiz / "engine"
    if not carpeta.is_dir():
        return ()
    motores = []
    for nodo in sorted(carpeta.iterdir()):
        nombre = nodo.name
        familia = re.match(r"^([a-z]+)\d+$", nombre)
        capacidades = (read_text(f"{nodo}/capabilities") or "").split()
        motores.append(GpuEngine(
            name=nombre,
            kind=MOTORES_INTEL.get(familia.group(1)) if familia else None,
            capabilities=tuple(capacidades),
        ))
    return tuple(motores)


def _pmu_de(gpu: dict) -> Optional[str]:
    """Con qué nombre publica el kernel el PMU de esta gráfica.

    i915 solo admite una tarjeta y la registra con un nombre fijo. xe le pega
    la ranura PCI detrás, con los dos puntos cambiados por guiones bajos.
    """
    driver = gpu.get("driver")
    if driver == "i915":
        return "i915"
    if driver == "xe":
        ranura = gpu.get("pci_slot")
        return f"xe_{ranura.replace(':', '_')}" if ranura else None
    return None


def _uso_intel(gpu: dict, ocupacion: Optional[dict]) -> None:
    """Reparte los motores del PMU en los porcentajes del modelo.

    Para el resumen de arriba se coge el máximo y no la suma: con varios
    motores del mismo tipo, sumar pasaría del 100 % sin que la tarjeta esté a
    tope de nada. El detalle por motor se guarda aparte, que es donde se ve la
    diferencia entre «la gráfica no da más» y «solo va cargado el vídeo».
    """
    motores = (ocupacion or {}).get(_pmu_de(gpu) or "")
    if not motores:
        return
    render = [v for e, v in motores.items() if e.startswith(("rcs", "ccs"))]
    video = [v for e, v in motores.items() if e.startswith(("vcs", "vecs"))]
    if render:
        gpu["busy_percent"] = max(render)
    if video:
        gpu["video_busy_percent"] = max(video)

    gpu["engines"] = tuple(
        dataclasses.replace(motor, busy_percent=motores.get(f"{motor.name}-busy"))
        for motor in gpu.get("engines") or ()
    )


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


# Los drivers que no son de ninguna tarjeta: el respaldo que pone el kernel
# para tener imagen cuando el driver de verdad no está. No leen sensores, no
# dan relojes y no saben qué chip hay debajo, así que una ficha suya sale
# entera a guiones y parece que el programa esté roto.
#
# Aparecen al arrancar con `nomodeset`, con el driver sin instalar (lo típico
# con una NVIDIA recién comprada) o con una tarjeta más nueva que el kernel.
FRAMEBUFFER_GENERICO = frozenset({
    "simple-framebuffer", "simpledrm", "vesafb", "efifb", "offb", "vga16fb",
})

# Clases PCI de una tarjeta gráfica: controlador VGA y controlador 3D. La
# segunda es la de las dedicadas de portátil, que no llevan salida de video.
CLASES_GRAFICAS = (0x030000, 0x030200)


def _graficas_del_bus() -> list[pathlib.Path]:
    """Las tarjetas que hay en el bus PCI, tenga o no driver cargado.

    Es lo que permite decir «tienes una GeForce RTX 3050» en un equipo donde
    el kernel se ha quedado en el framebuffer de respaldo: el bus enumera el
    hardware aunque no haya nadie que sepa hablarle.
    """
    raiz = pathlib.Path("/sys/bus/pci/devices")
    encontradas = []
    for dispositivo in sorted(raiz.glob("*")) if raiz.is_dir() else ():
        clase = _hex(dispositivo / "class")
        if clase is not None and (clase & 0xFFFF00) in (
                c & 0xFFFF00 for c in CLASES_GRAFICAS):
            encontradas.append(dispositivo)
    return encontradas


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


# Los únicos anchos de enlace que existen en PCIe. Cualquier otra cifra que
# aparezca en sysfs es un centinela, no un dato.
ANCHOS_PCIE = frozenset({1, 2, 4, 8, 12, 16, 32})


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

    def ancho(nodo: pathlib.Path, nombre: str) -> Optional[int]:
        """El número de carriles, descartando lo que no es un número de carriles.

        Un dispositivo que no cuelga de un bus PCIe de verdad —la gráfica
        integrada, sin ir más lejos— publica los ficheros igualmente pero con
        centinelas: 0 cuando no hay enlace y 255 (0xFF) cuando no se sabe. Sin
        filtrarlos, una integrada declaraba un enlace de 255 carriles.
        """
        valor = read_int(f"{nodo}/{nombre}")
        return valor if valor in ANCHOS_PCIE else None
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


def _relojes(dispositivo: pathlib.Path,
             nodo: Optional[pathlib.Path] = None) -> GpuClocks:
    nucleo = _niveles(dispositivo / "pp_dpm_sclk")
    memoria = _niveles(dispositivo / "pp_dpm_mclk")
    hwmon = _hwmon(dispositivo)
    frecuencias = _etiquetadas(hwmon, "freq")

    # La frecuencia instantánea la da hwmon; la línea marcada con asterisco es
    # más gruesa pero está cuando no hay hwmon, como en las Intel.
    activo = lambda niveles: next((n.hz for n in niveles if n.active), None)
    return GpuClocks(
        core_hz=_primero(frecuencias.get("sclk"), activo(nucleo),
                         _intel_hz(dispositivo, nodo, "cur")),
        memory_hz=_primero(frecuencias.get("mclk"), activo(memoria)),
        core_max_hz=_primero(max((n.hz for n in nucleo), default=None),
                             _intel_hz(dispositivo, nodo, "max")),
        memory_max_hz=max((n.hz for n in memoria), default=None),
        core_levels=nucleo,
        memory_levels=memoria,
        performance_level=read_text(f"{dispositivo}/power_dpm_force_performance_level"),
    )


def _intel_hz(dispositivo: pathlib.Path, nodo: Optional[pathlib.Path],
              cual: str) -> Optional[int]:
    """Las frecuencias del motor gráfico de una Intel, se llamen como se llamen.

    Han cambiado de sitio dos veces y ninguna de las dos rutas viejas se ha
    borrado del todo, así que hay que mirar en las cuatro:

    - i915 clásico las pone sueltas en el nodo DRM, no en el nodo PCI. Eso es
      lo que las dejaba sin leer: se buscaban en `device/`, que es el enlace
      al dispositivo PCI, y ahí no están.
    - i915 desde el kernel 6.2 las mete en `gt/gt0/` con el prefijo `rps_`,
      para poder tener más de un motor gráfico por tarjeta.
    - xe, el driver nuevo, usa otra jerarquía distinta.

    Un cero se devuelve tal cual cuando es la frecuencia de ahora mismo: una
    integrada en reposo profundo apaga el motor gráfico y marca 0, y eso es la
    respuesta, no la falta de ella. Descartarlo dejaba «Núcleo —» en la ficha
    de un ThinkPad mientras la curva de al lado sí tenía historial, que es la
    contradicción por la que se vio. En un máximo o un mínimo sí es un campo
    sin rellenar: nadie tiene un techo de 0 MHz.
    """
    actual = cual in ("cur", "act")

    def escalar(mhz: Optional[int]) -> Optional[int]:
        if mhz is None or (mhz == 0 and not actual):
            return None
        return mhz * 1_000_000

    if nodo is not None:
        # `act` es la que va de verdad; `cur` es la que se ha pedido. Para el
        # máximo no hay tal distinción.
        medida = "act" if cual == "cur" else cual
        for ruta in (f"{nodo}/gt/gt0/rps_{medida}_freq_mhz",
                     f"{nodo}/gt/gt0/rps_{cual}_freq_mhz",
                     f"{nodo}/gt_{medida}_freq_mhz",
                     f"{nodo}/gt_{cual}_freq_mhz"):
            if (mhz := read_int(ruta)) is not None:
                return escalar(mhz)

    mhz = read_int(f"{dispositivo}/gt_{cual}_freq_mhz")
    if mhz is None:
        # xe, el driver nuevo de Intel, las mueve dentro de la jerarquía de gt.
        mhz = read_int(f"{dispositivo}/tile0/gt0/freq0/{cual}_freq")
    return escalar(mhz)


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
