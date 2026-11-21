"""Con una raíz alternativa, el Collector no toca el equipo de verdad.

Es lo que permite probar un arreglo contra el volcado de otro equipo: si un
proveedor leyera un solo archivo de `/sys` de la máquina que ejecuta la
suite, o preguntara a su procesador, el test mezclaría dos equipos y podría
decir que todo cuadra mezclando el i5 de la oficina con el 5800X3D de casa.
"""

import builtins
import contextlib
import io
import os
import pathlib
import tempfile
import unittest
from unittest import mock

from silux import sysroot

SISTEMA = ("/sys", "/proc", "/etc", "/dev")


@contextlib.contextmanager
def _vigilando(raiz: str):
    """Apunta cada camino del sistema que se toca fuera de `raiz`."""
    tocados: list[str] = []

    def mira(camino):
        try:
            texto = os.fspath(camino)
        except TypeError:
            return
        if isinstance(texto, bytes):
            texto = texto.decode(errors="replace")
        if texto.startswith(SISTEMA) and not texto.startswith(raiz):
            tocados.append(texto)

    def envolver(funcion):
        def envuelta(camino, *args, **kwargs):
            mira(camino)
            return funcion(camino, *args, **kwargs)
        return envuelta

    parches = [mock.patch.object(builtins, "open", envolver(builtins.open)),
               mock.patch.object(io, "open", envolver(io.open))]
    for nombre in ("stat", "lstat", "listdir", "scandir", "readlink", "statvfs"):
        parches.append(mock.patch.object(os, nombre, envolver(getattr(os, nombre))))
    with contextlib.ExitStack() as pila:
        for parche in parches:
            pila.enter_context(parche)
        yield tocados


class TestLaRaizAlternativaNoSeSaleDeElla(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.raiz = self._tmp.name
        for carpeta in ("sys", "proc", "etc"):
            (pathlib.Path(self.raiz) / carpeta).mkdir()
        parche = mock.patch.dict(os.environ, {sysroot.VARIABLE: self.raiz})
        parche.start()
        self.addCleanup(parche.stop)
        sysroot.forget()

    def test_ningun_proveedor_lee_el_sistema_de_verdad(self):
        from silux.collector import Collector

        with _vigilando(self.raiz) as tocados:
            recolector = Collector()
            try:
                recolector.snapshot()
            finally:
                recolector.close()
        self.assertEqual(sorted(set(tocados))[:15], [],
                         f"{len(set(tocados))} caminos del sistema de verdad")

    def test_ni_pregunta_a_la_cpu_ni_lanza_el_proceso_de_las_apis(self):
        from silux import gpuapi, rawcpuid
        from silux.collector import Collector

        preguntas = []
        with mock.patch.object(rawcpuid.CpuidReader, "__call__",
                               lambda self, *a: preguntas.append(a) or (0, 0, 0, 0)), \
             mock.patch.object(gpuapi, "consultar",
                               lambda: preguntas.append("gpuapi") or {}):
            recolector = Collector()
            try:
                recolector.snapshot()
            finally:
                recolector.close()
        self.assertEqual(preguntas, [])


class TestRutas(unittest.TestCase):
    def test_sin_raiz_no_cambia_nada(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop(sysroot.VARIABLE, None)
            self.assertEqual(sysroot.path("/sys/class/hwmon"), "/sys/class/hwmon")

    def test_con_raiz_traduce_y_no_traduce_dos_veces(self):
        with mock.patch.dict(os.environ, {sysroot.VARIABLE: "/tmp/v"}):
            una = sysroot.path("/sys/class/hwmon")
            self.assertEqual(una, "/tmp/v/sys/class/hwmon")
            self.assertEqual(sysroot.path(una), una)
            self.assertEqual(sysroot.path(pathlib.Path("/proc/stat")),
                             pathlib.Path("/tmp/v/proc/stat"))
            self.assertEqual(sysroot.path("/usr/share/hwdata/pci.ids"),
                             "/usr/share/hwdata/pci.ids")
            self.assertEqual(sysroot.unrooted("/tmp/v/sys/class/net"), "/sys/class/net")


if __name__ == "__main__":
    unittest.main()
