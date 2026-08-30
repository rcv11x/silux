"""Cuántas unidades de ejecución tiene de verdad una gráfica Intel.

El número no está en sysfs por ningún lado. Lo único que contestaba era
OpenCL, y contesta otra cosa: sus «unidades de cómputo» son los subslices, que
en Xe-LP agrupan dieciséis EU cada uno. Por eso una Iris Xe G7 de 80 EU salía
con un 5 en la ficha, etiquetado como EU, sin que el número fuera falso ni la
etiqueta cierta.

Quien sabe el dato es el driver, y lo da por `DRM_IOCTL_I915_GETPARAM` con
`I915_PARAM_EU_TOTAL`, que es de donde lo sacan Mesa e `intel_gpu_top`.

Se abre el nodo de render, legible por cualquiera igual que en `amdgpu.py`, y
solo se lee. El identificador del chip sirve de comprobación: si no coincide
con el que dice sysfs, es que se está hablando con otra tarjeta y se descarta.

Esto es solo para `i915`. El driver `xe` de las generaciones nuevas tiene su
propia interfaz y no atiende a estos números.
"""

from __future__ import annotations

import ctypes
import fcntl
import os
import pathlib
from dataclasses import dataclass
from typing import Optional

# DRM_IOCTL_I915_GETPARAM = DRM_IOWR(DRM_COMMAND_BASE + DRM_I915_GETPARAM, …)
DRM_COMMAND_BASE = 0x40
DRM_I915_GETPARAM = 0x06

# De <drm/i915_drm.h>. Son ABI: los números no se reutilizan nunca.
I915_PARAM_CHIPSET_ID = 4
I915_PARAM_SUBSLICE_TOTAL = 33
I915_PARAM_EU_TOTAL = 34


@dataclass(frozen=True)
class DeviceInfo:
    """None en cada campo que el driver no haya querido contestar."""

    chipset_id: Optional[int] = None
    eu_total: Optional[int] = None
    subslices: Optional[int] = None


class _Peticion(ctypes.Structure):
    """`struct drm_i915_getparam`: qué se pregunta y dónde dejar la respuesta.

    El puntero va alineado a ocho, así que entre los dos campos hay cuatro
    bytes de relleno que ctypes pone solo. El tamaño tiene que salir 16 o el
    ioctl no es el que el kernel espera.
    """

    _fields_ = [("param", ctypes.c_int32),
                ("value", ctypes.POINTER(ctypes.c_int32))]


def query(node: str, expected_device_id: Optional[int] = None) -> Optional[DeviceInfo]:
    """Pregunta al driver. Devuelve None ante cualquier duda, sin quejarse."""
    try:
        descriptor = os.open(node, os.O_RDWR | os.O_CLOEXEC)
    except OSError:
        return None

    try:
        chipset = _parametro(descriptor, I915_PARAM_CHIPSET_ID)
        # Si el chip no es el que dice sysfs, este nodo es de otra tarjeta y
        # todo lo que conteste estaría atribuido a quien no es.
        if expected_device_id is not None and chipset != expected_device_id:
            return None
        return DeviceInfo(
            chipset_id=chipset,
            eu_total=_parametro(descriptor, I915_PARAM_EU_TOTAL),
            subslices=_parametro(descriptor, I915_PARAM_SUBSLICE_TOTAL),
        )
    finally:
        os.close(descriptor)


def render_node(device: pathlib.Path | str) -> Optional[str]:
    """El `/dev/dri/renderD*` de una tarjeta, a partir de su nodo PCI."""
    directorio = pathlib.Path(device, "drm")
    if not directorio.is_dir():
        return None
    for entrada in sorted(directorio.glob("renderD*")):
        camino = f"/dev/dri/{entrada.name}"
        if os.path.exists(camino):
            return camino
    return None


def _parametro(descriptor: int, cual: int) -> Optional[int]:
    """Un `GETPARAM` suelto. Los que no existan contestan con un error."""
    valor = ctypes.c_int32(0)
    peticion = _Peticion(cual, ctypes.pointer(valor))
    try:
        if fcntl.ioctl(descriptor, _ORDEN, peticion) != 0:
            return None
    except (OSError, ValueError):
        return None
    # Cero no es una respuesta: ninguna gráfica tiene cero unidades. El driver
    # lo devuelve así cuando conoce el parámetro pero no tiene qué contestar.
    return valor.value or None


def _iowr(letra: str, numero: int, tamano: int) -> int:
    """El mismo `_IOWR` de <asm/ioctl.h>, que Python no trae hecho."""
    LECTURA_Y_ESCRITURA = 3
    return (LECTURA_Y_ESCRITURA << 30) | (tamano << 16) | (ord(letra) << 8) | numero


_ORDEN = _iowr("d", DRM_COMMAND_BASE + DRM_I915_GETPARAM, ctypes.sizeof(_Peticion))
