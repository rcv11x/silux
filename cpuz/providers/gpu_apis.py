"""Lo que las APIs gráficas cuentan de cada tarjeta.

Preguntar cuesta caro —los drivers de las tres suman 118 MB de residente— así
que `cpuz.gpuapi` lo hace en un proceso aparte y aquí solo llega el resultado.

El kernel dice qué hay puesto; OpenGL, Vulkan y OpenCL dicen qué se puede hacer
con ello. Son datos de otra naturaleza —versiones de API, no registros— y por
eso van en un proveedor aparte que se apoya en `cpuz.gpuapi`.

Además resuelve una ambigüedad que sysfs no puede: `pci.ids` puede dar un
nombre para tres modelos («Radeon RX 9070/9070 XT/9070 GRE») y es el driver
quien sabe cuál es. Cuando el nombre que ya hay lleva barras, el de Vulkan lo
sustituye; si no, se respeta el de la base de datos, que suele ser más
completo porque incluye a quien montó la tarjeta.
"""

from __future__ import annotations

import re
from typing import Optional

from .. import gpuapi
from ..model import GpuApi, Need
from .base import Draft, Provider

# «AMD Radeon RX 9070 XT (RADV GFX1201)» → el paréntesis es del driver, no del
# nombre de la tarjeta.
_COLA_DEL_DRIVER = re.compile(r"\s*\((?:RADV|LLVM|ACO|radeonsi|llvmpipe)[^)]*\)\s*$",
                              re.IGNORECASE)
# «4.6 (Compatibility Profile) Mesa 26.2.1-arch3.1» → 26.2.1-arch3.1
_VERSION_DE_MESA = re.compile(r"Mesa\s+([\w.\-]+)")


class GpuApis(Provider):
    """OpenGL, Vulkan y OpenCL, preguntados una sola vez."""

    name = "gpu-apis"
    provides = "gpus.apis"
    # Las versiones de API no cambian mientras el programa esté abierto, y
    # crear un contexto de OpenGL en cada muestreo sería absurdo.
    static = True

    def available(self) -> bool:
        return True

    def collect(self, draft: Draft) -> None:
        if not draft.gpus:
            return

        # Una sola llamada: por dentro lanza un proceso aparte que carga los
        # drivers, contesta y muere. Ver el porqué en `cpuz.gpuapi`.
        datos = _sin_reventar(gpuapi.consultar) or {}
        vulkan = datos.get("vulkan") or []
        opencl = datos.get("opencl") or []
        opengl = datos.get("opengl")

        if not (vulkan or opencl or opengl):
            draft.note(
                "gpus.apis", Need.DRIVER,
                "No hay ninguna biblioteca de OpenGL, Vulkan ni OpenCL que preguntar.",
                "Suele ser una máquina sin entorno gráfico instalado. Las trae el "
                "driver: mesa, vulkan-radeon, vulkan-intel o el paquete de NVIDIA.",
            )
            return

        draft.capabilities.add("gpu-apis")
        principal = _principal(draft.gpus)

        for indice, gpu in enumerate(draft.gpus):
            apis: list[GpuApi] = []

            if dispositivo := _vulkan_de(gpu, vulkan):
                apis.append(GpuApi(
                    name="Vulkan",
                    version=dispositivo["api_version"],
                    device=dispositivo["name"],
                    driver=_version_del_driver(dispositivo),
                    extra=f"instancia {dispositivo['instance_version']}",
                ))
                _afinar_nombre(gpu, dispositivo["name"])

            # OpenGL y OpenCL no dicen a qué nodo PCI pertenecen, así que solo
            # se le atribuyen a la tarjeta que el sistema usa por omisión.
            if indice == principal:
                if opengl and opengl.get("version"):
                    apis.append(GpuApi(
                        name="OpenGL",
                        version=_solo_version(opengl["version"]),
                        device=opengl.get("renderer"),
                        driver=_mesa(opengl["version"]),
                        extra=f"GLSL {opengl['glsl']}" if opengl.get("glsl") else None,
                    ))
                for dispositivo in opencl:
                    apis.append(GpuApi(
                        name="OpenCL",
                        version=_solo_version(dispositivo.get("version") or ""),
                        device=dispositivo.get("name"),
                        driver=dispositivo.get("driver_version"),
                        extra=_unidades(dispositivo),
                    ))
                    if dispositivo.get("compute_units"):
                        gpu["compute_units"] = dispositivo["compute_units"]

            if apis:
                gpu["apis"] = tuple(apis)
                gpu["driver_version"] = gpu.get("driver_version") or next(
                    (a.driver for a in apis if a.driver), None
                )


# -- casado y limpieza -------------------------------------------------------

def _sin_reventar(funcion):
    """Una API rota no puede llevarse por delante a las otras dos."""
    try:
        return funcion()
    except Exception:                                  # noqa: BLE001
        return None


def _principal(gpus: list[dict]) -> int:
    """La tarjeta que el sistema usa por omisión, que es la que arrancó."""
    for indice, gpu in enumerate(gpus):
        if gpu.get("primary"):
            return indice
    return 0


def _vulkan_de(gpu: dict, dispositivos: list[dict]) -> Optional[dict]:
    """Vulkan sí publica el identificador PCI, así que aquí no hay que adivinar."""
    for dispositivo in dispositivos:
        if (dispositivo.get("vendor_id") == gpu.get("vendor_id")
                and dispositivo.get("device_id") == gpu.get("device_id")):
            return dispositivo
    return None


def _afinar_nombre(gpu: dict, nombre: Optional[str]) -> None:
    """Sustituye un nombre que vale para varios modelos por el del driver."""
    if not nombre:
        return
    actual = gpu.get("name")
    # Una barra en el nombre es la marca de pci.ids para «una de estas».
    if actual and "/" not in actual:
        return
    gpu["name"] = _COLA_DEL_DRIVER.sub("", nombre).strip() or actual


def _solo_version(texto: str) -> Optional[str]:
    """«OpenCL 3.1» y «4.6 (Compatibility Profile) Mesa…» → «3.1» y «4.6»."""
    encaje = re.search(r"(\d+\.\d+(?:\.\d+)?)", texto)
    return encaje.group(1) if encaje else (texto.strip() or None)


def _mesa(texto: str) -> Optional[str]:
    encaje = _VERSION_DE_MESA.search(texto)
    return encaje.group(1) if encaje else None


def _unidades(dispositivo: dict) -> Optional[str]:
    unidades = dispositivo.get("compute_units")
    return f"{unidades} unidades de cómputo" if unidades else None


def _version_del_driver(dispositivo: dict) -> Optional[str]:
    """Vulkan da la versión del driver en 32 bits, y no todos la empaquetan igual.

    Casi todos siguen el reparto de la propia API —10, 10 y 12 bits—, con lo que
    Mesa sale como 26.2.1. NVIDIA usa el suyo, y leerlo con el reparto estándar
    da un número que no se parece a nada.
    """
    crudo = dispositivo.get("driver_version")
    if not crudo:
        return None
    if dispositivo.get("vendor_id") == 0x10DE:
        return f"{(crudo >> 22) & 0x3FF}.{(crudo >> 14) & 0xFF}.{(crudo >> 6) & 0xFF}"
    return f"{(crudo >> 22) & 0x7F}.{(crudo >> 12) & 0x3FF}.{crudo & 0xFFF}"
