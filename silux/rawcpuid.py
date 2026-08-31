"""Ejecuta la instrucción CPUID desde Python, sin root y sin compilar nada.

El truco: se reservan unas pocas páginas anónimas con `mmap`, se escriben en
ellas los 20 bytes de código máquina de una función que hace `cpuid`, se les
quita permiso de escritura y se les da permiso de ejecución (W^X), y se llama
al resultado con `ctypes` como si fuera cualquier otra función de C.

CPUID responde por el núcleo donde se ejecuta, así que para leer los datos de
un núcleo concreto hay que fijar el hilo a él. En Linux
`sched_setaffinity(0, …)` afecta al *hilo* que llama, no al proceso entero:
por eso `pinned()` es seguro siempre que se use dentro del hilo trabajador y
nunca en el hilo de la interfaz.
"""

from __future__ import annotations

import contextlib
import ctypes
import mmap
import os
import platform
import struct
from typing import Iterator

__all__ = ["CpuidError", "CpuidReader", "pinned", "is_supported",
           "pagina_ejecutable"]

# System V AMD64: rdi = puntero de salida, esi = hoja, edx = subhoja.
_CODE_X86_64 = bytes(
    (
        0x53,                    # push rbx        (rbx es callee-saved)
        0x89, 0xF0,              # mov  eax, esi   -> hoja
        0x89, 0xD1,              # mov  ecx, edx   -> subhoja
        0x0F, 0xA2,              # cpuid
        0x89, 0x07,              # mov  [rdi+0],  eax
        0x89, 0x5F, 0x04,        # mov  [rdi+4],  ebx
        0x89, 0x4F, 0x08,        # mov  [rdi+8],  ecx
        0x89, 0x57, 0x0C,        # mov  [rdi+12], edx
        0x5B,                    # pop  rbx
        0xC3,                    # ret
    )
)

_PROT_READ_EXEC = 0x1 | 0x4


def pagina_ejecutable(codigo: bytes, error=RuntimeError):
    """Una página con `codigo` dentro, lista para llamarse con ctypes.

    Devuelve el `mmap` y la dirección. El `mmap` hay que guardarlo mientras se
    use la función: si se recolecta, la dirección deja de ser válida y la
    llamada siguiente se lleva el proceso por delante.

    Vive aquí porque este módulo fue el primero que lo necesitó, para CPUID, y
    ahora lo usa también el kernel que persigue punteros de `membench`. Los
    detalles que tiene dentro se aprendieron una vez y no conviene repetirlos
    en dos sitios para que se desincronicen.
    """
    mm = mmap.mmap(-1, mmap.PAGESIZE, prot=mmap.PROT_READ | mmap.PROT_WRITE)
    mm.write(codigo)

    # `CDLL(None)` es el propio proceso, que ya trae la libc cargada, y es
    # lo que hacen los otros dos módulos que la piden. Buscarla con
    # `find_library` no la encuentra mejor y sí lanza `ldconfig -p` para
    # preguntar por algo que ya está abierto: un fork y un exec dentro del
    # hilo de muestreo, y un fallo donde no haya ldconfig puesto.
    libc = ctypes.CDLL(None, use_errno=True)
    # La vista se crea y se descarta en la misma expresión: si se guardara,
    # el mmap quedaría "exportado" y no se podría cerrar nunca. La dirección
    # sigue siendo válida mientras viva `mm`.
    address = ctypes.addressof(ctypes.c_char.from_buffer(mm))

    if libc.mprotect(ctypes.c_void_p(address), mmap.PAGESIZE, _PROT_READ_EXEC) != 0:
        errno = ctypes.get_errno()
        mm.close()
        raise error(
            f"mprotect falló (errno {errno}). El entorno prohíbe ejecutar memoria "
            "anónima; suele pasar bajo políticas SELinux estrictas o en sandboxes."
        )
    return mm, address


class CpuidError(RuntimeError):
    """CPUID no se puede usar en esta máquina o en este entorno."""


def is_supported() -> bool:
    return platform.machine() in ("x86_64", "AMD64")


@contextlib.contextmanager
def pinned(cpu_index: int) -> Iterator[None]:
    """Fija el hilo actual a una CPU lógica y restaura la máscara al salir."""
    previous = os.sched_getaffinity(0)
    try:
        os.sched_setaffinity(0, {cpu_index})
    except OSError as exc:                      # cpu apagada, cgroup restrictivo…
        raise CpuidError(f"no se pudo fijar el hilo a la CPU {cpu_index}: {exc}") from exc
    try:
        yield
    finally:
        os.sched_setaffinity(0, previous)


class CpuidReader:
    """Lector de hojas CPUID. Construirlo una vez y reutilizarlo."""

    def __init__(self) -> None:
        if not is_supported():
            raise CpuidError(f"CPUID solo está implementado para x86-64, no para {platform.machine()}")

        self._mm, address = pagina_ejecutable(_CODE_X86_64, CpuidError)

        prototype = ctypes.CFUNCTYPE(None, ctypes.POINTER(ctypes.c_uint32), ctypes.c_uint32, ctypes.c_uint32)
        self._call = prototype(address)
        self._regs = (ctypes.c_uint32 * 4)()

        # Comprobación de cordura: la hoja 0 siempre devuelve un identificador
        # de fabricante con caracteres imprimibles.
        try:
            self.max_leaf, ebx, ecx, edx = self(0)
            self.vendor_id = struct.pack("<III", ebx, edx, ecx).decode("ascii")
        except Exception as exc:
            self.close()
            raise CpuidError(f"CPUID devolvió basura: {exc}") from exc

        self.max_extended_leaf = self(0x8000_0000)[0]

    def __call__(self, leaf: int, subleaf: int = 0) -> tuple[int, int, int, int]:
        """Devuelve (eax, ebx, ecx, edx) para una hoja y subhoja."""
        self._call(self._regs, leaf, subleaf)
        return tuple(self._regs)  # type: ignore[return-value]

    def supports(self, leaf: int) -> bool:
        if leaf >= 0x8000_0000:
            return leaf <= self.max_extended_leaf
        return leaf <= self.max_leaf

    def brand_string(self) -> str:
        """La cadena de marca del fabricante, en las hojas 0x80000002-4."""
        if not self.supports(0x8000_0004):
            return ""
        raw = b"".join(struct.pack("<IIII", *self(leaf)) for leaf in (0x8000_0002, 0x8000_0003, 0x8000_0004))
        return " ".join(raw.split(b"\x00")[0].decode("ascii", "replace").split())

    def close(self) -> None:
        self._call = None  # type: ignore[assignment]
        mm = getattr(self, "_mm", None)
        if mm is not None and not mm.closed:
            mm.close()

    def __enter__(self) -> "CpuidReader":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def __del__(self) -> None:
        with contextlib.suppress(Exception):
            self.close()
