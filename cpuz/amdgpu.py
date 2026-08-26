"""Lo que amdgpu solo cuenta si se le pregunta por ioctl.

Hay datos de una Radeon que no están en ningún fichero de sysfs: el tipo de
memoria, la anchura del bus, cuántas unidades de cómputo hay activas de verdad
y cuántos ROP monta el chip. El driver los tiene, pero solo los da por
`DRM_IOCTL_AMDGPU_INFO`, que es como los pide Mesa y como los saca LACT.

Se abre el nodo de render (`/dev/dri/renderD128`), que en cualquier
distribución de escritorio es legible por todo el mundo — está pensado para que
cualquier programa pueda dibujar. No hace falta root ni estar en el grupo
`video`, y no se escribe nada: la petición solo lee.

De aquí sale además el ancho de banda de la memoria, que no es un dato del
driver sino una multiplicación, pero es de los que la gente busca.
"""

from __future__ import annotations

import ctypes
import fcntl
import os
import pathlib
import struct
from dataclasses import dataclass
from typing import Optional

# DRM_IOCTL_AMDGPU_INFO = DRM_IOWR(DRM_COMMAND_BASE + DRM_AMDGPU_INFO, …)
DRM_COMMAND_BASE = 0x40
DRM_AMDGPU_INFO = 0x05
AMDGPU_INFO_DEV_INFO = 0x16
RESPUESTA = 1024                      # de sobra: la estructura ronda los 300 B

# Posiciones dentro de `struct drm_amdgpu_info_device`. Son ABI: el kernel solo
# puede añadir campos al final, nunca mover los que ya están, así que fijarlas
# aquí es seguro. `device_id` sirve de comprobación: si no coincide con el que
# dice sysfs, es que esta tabla no corresponde y se descarta todo.
CAMPOS = {
    "device_id": 0, "chip_rev": 4, "external_rev": 8, "pci_rev": 12, "family": 16,
    "num_shader_engines": 20, "num_shader_arrays_per_engine": 24,
    "cu_active_number": 48, "enabled_rb_pipes_mask": 120, "num_rb_pipes": 124,
    "num_hw_gfx_contexts": 128, "vram_type": 176, "vram_bit_width": 180,
}
CAMPOS_64 = {"max_engine_clock": 32, "max_memory_clock": 40}

TIPOS_DE_VRAM = {
    1: "GDDR1", 2: "DDR2", 3: "GDDR3", 4: "GDDR4", 5: "GDDR5", 6: "HBM",
    7: "DDR3", 8: "DDR4", 9: "GDDR6", 10: "DDR5", 11: "LPDDR4", 12: "LPDDR5",
}

# Cuántas transferencias hace cada tipo por ciclo del reloj que publica el
# driver. No es un dato que se pueda leer: sale de cómo funciona cada memoria,
# y se comprueba contra tarjetas conocidas —una RX 9070 XT da 20 Gbps con su
# reloj a 1258 MHz, una RX 580 daba 8 con 2000, una Vega 1,89 con 945—. Los
# tipos que no están aquí se quedan sin ancho de banda antes que enseñar uno
# inventado.
TRANSFERENCIAS = {
    "GDDR6": 16, "GDDR5": 4, "GDDR4": 4, "GDDR3": 4,
    "HBM": 2, "DDR3": 2, "DDR4": 2, "DDR5": 2, "LPDDR4": 2, "LPDDR5": 2,
}


class _Peticion(ctypes.Structure):
    """`struct drm_amdgpu_info`: dónde dejar la respuesta y qué se pregunta."""

    _fields_ = [
        ("return_pointer", ctypes.c_uint64),
        ("return_size", ctypes.c_uint32),
        ("query", ctypes.c_uint32),
        # La unión de parámetros de la consulta. DEV_INFO no usa ninguno, pero
        # el tamaño tiene que ser el de la estructura entera o el ioctl falla.
        ("_union", ctypes.c_uint32 * 4),
    ]


@dataclass(frozen=True, slots=True)
class DeviceInfo:
    """Lo que el driver sabe del chip y no publica por sysfs."""

    device_id: Optional[int] = None
    family: Optional[int] = None
    vram_type: Optional[str] = None
    vram_bits: Optional[int] = None
    compute_units: Optional[int] = None
    shader_engines: Optional[int] = None
    arrays_per_engine: Optional[int] = None
    render_backends: Optional[int] = None
    max_engine_hz: Optional[int] = None
    max_memory_hz: Optional[int] = None

    @property
    def rops(self) -> Optional[int]:
        """Las unidades que escriben píxeles. Van repartidas por cada array."""
        if not (self.render_backends and self.shader_engines
                and self.arrays_per_engine):
            return None
        return self.render_backends * self.shader_engines * self.arrays_per_engine

    @property
    def memory_data_rate_hz(self) -> Optional[int]:
        """La tasa real a la que viajan los datos, no el reloj de comando."""
        factor = TRANSFERENCIAS.get(self.vram_type or "")
        if not (factor and self.max_memory_hz):
            return None
        return self.max_memory_hz * factor

    @property
    def bandwidth_bytes(self) -> Optional[int]:
        """Ancho de banda de la memoria, en bytes por segundo."""
        if not (self.memory_data_rate_hz and self.vram_bits):
            return None
        return int(self.memory_data_rate_hz * self.vram_bits / 8)


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


def query(node: str, expected_device_id: Optional[int] = None) -> Optional[DeviceInfo]:
    """Pregunta al driver. Devuelve None ante cualquier duda, sin quejarse."""
    try:
        descriptor = os.open(node, os.O_RDWR | os.O_CLOEXEC)
    except OSError:
        return None

    try:
        buffer = ctypes.create_string_buffer(RESPUESTA)
        peticion = _Peticion(ctypes.addressof(buffer), RESPUESTA,
                             AMDGPU_INFO_DEV_INFO, (ctypes.c_uint32 * 4)())
        orden = _iowr("d", DRM_COMMAND_BASE + DRM_AMDGPU_INFO, ctypes.sizeof(_Peticion))
        if fcntl.ioctl(descriptor, orden, peticion) != 0:
            return None
    except (OSError, ValueError):
        return None
    finally:
        os.close(descriptor)

    leidos = {nombre: struct.unpack_from("<I", buffer, sitio)[0]
              for nombre, sitio in CAMPOS.items()}
    # Si el identificador no cuadra con el que dice sysfs, la estructura no es
    # la que se espera y todo lo demás estaría leído de sitios que no son.
    if expected_device_id is not None and leidos["device_id"] != expected_device_id:
        return None

    khz = {nombre: struct.unpack_from("<Q", buffer, sitio)[0]
           for nombre, sitio in CAMPOS_64.items()}
    return DeviceInfo(
        device_id=leidos["device_id"] or None,
        family=leidos["family"] or None,
        vram_type=TIPOS_DE_VRAM.get(leidos["vram_type"]),
        vram_bits=leidos["vram_bit_width"] or None,
        compute_units=leidos["cu_active_number"] or None,
        shader_engines=leidos["num_shader_engines"] or None,
        arrays_per_engine=leidos["num_shader_arrays_per_engine"] or None,
        render_backends=leidos["num_rb_pipes"] or None,
        max_engine_hz=khz["max_engine_clock"] * 1000 or None,
        max_memory_hz=khz["max_memory_clock"] * 1000 or None,
    )


def _iowr(letra: str, numero: int, tamano: int) -> int:
    """El mismo `_IOWR` de <asm/ioctl.h>, que Python no trae hecho."""
    LECTURA_Y_ESCRITURA = 3
    return (LECTURA_Y_ESCRITURA << 30) | (tamano << 16) | (ord(letra) << 8) | numero
