"""Rellena las tarjetas NVIDIA con lo que solo sabe NVML.

`DrmGpus` ya las ha enumerado (el nodo PCI está ahí para todos los drivers)
pero con el driver propietario esa ficha viene casi vacía. Este proveedor la
completa preguntando a NVML y casando por la dirección PCI, que es el único
identificador que ambos lados publican.

No sustituye a nada: si algún dato ya venía de sysfs (una tarjeta con nouveau,
por ejemplo) se respeta, y NVML solo tapa huecos.

La sesión se abre una vez y se queda abierta; el colector la cierra al salir
por el mismo camino que usa para el ayudante de permisos.
"""

from __future__ import annotations

import dataclasses

from typing import Optional
from .. import nvml
from ..model import GpuClocks, PcieLink, GpuMemory, Need
from .base import Draft, Provider

# La velocidad de cada generación de PCIe, para traducir el número que da NVML.
VELOCIDADES = {1: 2.5, 2: 5.0, 3: 8.0, 4: 16.0, 5: 32.0, 6: 64.0}


class NvidiaGpus(Provider):
    """Memoria, relojes, sensores y recorte de rendimiento de las GeForce."""

    name = "nvml"
    provides = "gpus.nvidia"

    def __init__(self) -> None:
        # Se llama `client` a propósito: el colector cierra por ese nombre.
        self.client = nvml.Nvml()

    def available(self) -> bool:
        return self.client.open()

    def unavailable_reason(self):
        return None       # sin NVIDIA no falta nada; no hay nada que explicar

    def collect(self, draft: Draft) -> None:
        tarjetas = self.client.devices()
        if not tarjetas:
            return
        draft.capabilities.add("nvml")

        por_ranura = {gpu.get("pci_slot"): gpu for gpu in draft.gpus if gpu.get("pci_slot")}
        for tarjeta in tarjetas:
            destino = por_ranura.get(tarjeta.pci_slot)
            if destino is None:
                # NVML ve una tarjeta que DRM no enumeró. Pasa con las Tesla en
                # modo de solo cómputo, que no registran nodo de gráficos.
                destino = draft.gpu(len(draft.gpus))
                destino["pci_slot"] = tarjeta.pci_slot
                destino["vendor"] = "NVIDIA"
            _rellenar(destino, tarjeta)

        # Ya no hace falta el aviso de que una NVIDIA viene vacía: no lo viene.
        draft.notes = [n for n in draft.notes
                       if not (n.need is Need.DRIVER and n.path.startswith("gpus.")
                               and "NVIDIA" in n.message)]


# Cuántos núcleos CUDA lleva cada multiprocesador, por generación. Las dos
# primeras letras del nombre en clave dicen cuál es —AD107 es Ada, TU116 es
# Turing— y es un dato de la arquitectura, igual para toda la familia.
NUCLEOS_POR_SM = {
    "GP": 128,   # Pascal
    "GV": 64,    # Volta
    "TU": 64,    # Turing
    "GA": 128,   # Ampere
    "AD": 128,   # Ada Lovelace
    "GB": 128,   # Blackwell
}

# Por debajo de esto no son núcleos. La tarjeta más modesta que habla NVML
# ronda los 256 y ninguna GPU pasa de 200 multiprocesadores, así que entre las
# dos magnitudes hay un hueco que no deja lugar a dudas.
MINIMO_NUCLEOS = 200


def _nucleos_cuda(gpu: dict, crudo: Optional[int]) -> Optional[int]:
    """Los núcleos CUDA de verdad, que no siempre es lo que contesta NVML.

    `nvmlDeviceGetNumGpuCores` devuelve una cosa distinta según la tarjeta: una
    GTX 1660 Ti contesta 1536, que son sus núcleos, y una RTX 4060 contesta 24,
    que son sus multiprocesadores —lleva 3072 núcleos—. Salían las dos juntas
    en capturas de dos usuarios, «1536 CUDA» y «24 CUDA», y la segunda parece
    un fallo del programa porque lo es.

    Cuando el número es demasiado bajo para ser núcleos se multiplica por lo
    que da cada multiprocesador en esa arquitectura. Si no se reconoce la
    arquitectura no se inventa: se deja sin dato, que es preferible a una
    cifra creíble y falsa.
    """
    if crudo is None or crudo >= MINIMO_NUCLEOS:
        return crudo
    clave = (gpu.get("codename") or "")[:2].upper()
    factor = NUCLEOS_POR_SM.get(clave)
    return crudo * factor if factor else None


def _rellenar(gpu: dict, tarjeta: nvml.NvidiaGpu) -> None:
    directos = {
        "name": tarjeta.name,
        "vbios": tarjeta.vbios,
        "driver_version": tarjeta.driver_version,
        "unique_id": tarjeta.uuid,
        "compute_units": _nucleos_cuda(gpu, tarjeta.cuda_cores),
        "busy_percent": tarjeta.busy_percent,
        "memory_busy_percent": tarjeta.memory_busy_percent,
        "temp_c": tarjeta.temp_c,
        "power_w": tarjeta.power_w,
        "power_cap_w": tarjeta.power_cap_w,
        "fan_percent": tarjeta.fan_percent,
        "throttled": tarjeta.throttled,
    }
    for campo, valor in directos.items():
        if valor is not None and gpu.get(campo) is None:
            gpu[campo] = valor
    if tarjeta.throttle_reasons and not gpu.get("throttle_reasons"):
        gpu["throttle_reasons"] = tarjeta.throttle_reasons

    memoria: GpuMemory = gpu.get("memory") or GpuMemory()
    gpu["memory"] = dataclasses.replace(
        memoria,
        total_bytes=memoria.total_bytes or tarjeta.memory_total_bytes,
        used_bytes=memoria.used_bytes if memoria.used_bytes is not None
        else tarjeta.memory_used_bytes,
        bus_bits=memoria.bus_bits or tarjeta.memory_bus_bits,
    )
    # Las GeForce y las Quadro son tarjetas aparte. Lo que NVIDIA fusiona
    # con el procesador son los Tegra, que no hablan por NVML en un PC.
    gpu["integrated"] = False

    relojes: GpuClocks = gpu.get("clocks") or GpuClocks()
    gpu["clocks"] = dataclasses.replace(
        relojes,
        core_hz=relojes.core_hz if relojes.core_hz is not None else tarjeta.core_hz,
        core_max_hz=relojes.core_max_hz or tarjeta.core_max_hz,
        memory_hz=relojes.memory_hz if relojes.memory_hz is not None else tarjeta.memory_hz,
        memory_max_hz=relojes.memory_max_hz or tarjeta.memory_max_hz,
    )

    # NVML da la generación de PCIe; el modelo guarda gigatransferencias, que es
    # lo que publica sysfs para todas las demás tarjetas.
    enlace: PcieLink = gpu.get("link") or PcieLink()
    gpu["link"] = dataclasses.replace(
        enlace,
        current_speed_gts=(enlace.current_speed_gts
                           or VELOCIDADES.get(tarjeta.link_generation or 0)),
        current_width=enlace.current_width or tarjeta.link_width,
        max_speed_gts=(enlace.max_speed_gts
                       or VELOCIDADES.get(tarjeta.max_link_generation or 0)),
        max_width=enlace.max_width or tarjeta.max_link_width,
    )
