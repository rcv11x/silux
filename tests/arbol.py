"""Un sistema de mentira en una carpeta, para probar un proveedor suelto.

Los archivos llevan el contenido que dio un equipo de verdad: lo que se
fabrica aquí es la carpeta, no el estado. `SILUX_SYSROOT` apunta a ella
mientras dura el `with`.
"""

import contextlib
import os
import pathlib
import tempfile

from silux import sysroot


@contextlib.contextmanager
def arbol(archivos: dict, carpetas=()):
    """`archivos`: camino del sistema → texto o bytes. `carpetas`: vacías."""
    with tempfile.TemporaryDirectory(prefix="silux-arbol-") as tmp:
        raiz = pathlib.Path(tmp)
        for camino, contenido in archivos.items():
            destino = raiz / camino.lstrip("/")
            destino.parent.mkdir(parents=True, exist_ok=True)
            if isinstance(contenido, bytes):
                destino.write_bytes(contenido)
            else:
                destino.write_text(contenido)
        for camino in carpetas:
            (raiz / camino.lstrip("/")).mkdir(parents=True, exist_ok=True)
        anterior = os.environ.get(sysroot.VARIABLE)
        os.environ[sysroot.VARIABLE] = str(raiz)
        sysroot.forget()
        try:
            yield raiz
        finally:
            if anterior is None:
                os.environ.pop(sysroot.VARIABLE, None)
            else:
                os.environ[sysroot.VARIABLE] = anterior
            sysroot.forget()
