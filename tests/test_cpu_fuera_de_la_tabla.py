"""Un procesador que la tabla de esta versión no conoce.

La tabla de identificación es una foto de un día: un procesador que salga
después no está. Todo lo que da el propio CPUID tiene que salir igual, y el
nombre en clave, el nodo y el encapsulado no se inventan: se dice que no
están en la tabla de esta versión. Antes salían con un guion y una nota que
mandaba a regenerar la base con `tools/gen_cpu_db.py`, que no le sirve a
quien usa el AppImage.

Se simula con el volcado del 5800X3D quitándole su fila: sin las de AMD,
solo queda el comodín «Unknown AMD CPU», y sin los rangos de
`families.json`, nada lo rescata.
"""

import copy
import io
import unittest
from contextlib import redirect_stdout
from unittest import mock

from silux.i18n import _
from tests import pantalla, qt
from tests.test_equipos import EQUIPOS, foto

try:
    from PySide6.QtWidgets import QApplication
except ImportError:                                    # pragma: no cover
    QApplication = None

# Los tres datos que salen de la tabla y no del procesador.
DE_LA_TABLA = ("cpu.field.codename", "cpu.field.process", "cpu.field.package")


def _tabla_sin_amd():
    from silux import db
    tabla = copy.deepcopy(db.load())
    tabla["x86"]["AuthenticAMD"] = [e for e in tabla["x86"]["AuthenticAMD"]
                                    if e["name"].lower().startswith("unknown")]
    return tabla


def _foto_sin_su_fila():
    from silux import db
    with mock.patch.object(db, "load", return_value=_tabla_sin_amd()), \
         mock.patch.object(db, "_load_families", return_value=[]):
        return foto(EQUIPOS / "5800x3d")[0]


class TestLoDelCpuidSaleEntero(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.fuera = _foto_sin_su_fila()
        cls.dentro = foto(EQUIPOS / "5800x3d")[0]

    def test_nada_de_lo_que_da_el_procesador_cambia(self):
        a, b = self.fuera.cpu.types[0], self.dentro.cpu.types[0]
        for campo in ("brand", "cores", "threads", "caches", "features", "family",
                      "model", "stepping", "signature", "virtualization", "microcode"):
            with self.subTest(campo=campo):
                self.assertTrue(getattr(b, campo))
                self.assertEqual(getattr(a, campo), getattr(b, campo))
        self.assertTrue(b.clocks.max_hz)
        self.assertEqual(a.clocks, b.clocks)
        self.assertEqual(len(self.fuera.sensors), len(self.dentro.sensors))

    def test_no_se_inventa_nada(self):
        tipo = self.fuera.cpu.types[0]
        self.assertEqual((tipo.codename, tipo.technology, tipo.socket), (None, None, None))
        # Con la tabla, sí: es la misma foto con su fila.
        self.assertEqual(self.dentro.cpu.types[0].codename, "Ryzen 7 (Vermeer)")

    def test_la_nota_es_para_quien_usa_el_programa(self):
        notas = [n for n in self.fuera.notes if n.path == "cpu.codename"]
        self.assertEqual(len(notas), 1)
        texto = f"{notas[0].message} {notas[0].hint}"
        self.assertIn(_("cpu.notintable"), texto)
        self.assertNotIn("gen_cpu_db", texto)
        self.assertIn("--report", texto)


@unittest.skipIf(QApplication is None, "sin PySide6")
class TestEnLaPagina(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.app = qt.app()
        cls.fuera = _foto_sin_su_fila()

    def _seccion(self, ventana):
        from silux.ui.pages.cpu import TypeSection
        ventana.select_section("CPU")
        self.app.processEvents()
        return ventana.cpu_page.findChildren(TypeSection)[0]

    def test_las_tres_filas_lo_dicen_sin_guion(self):
        with pantalla.Ventana(self.fuera) as ventana:
            seccion = self._seccion(ventana)
            for clave in DE_LA_TABLA:
                with self.subTest(fila=clave):
                    etiqueta = seccion.processor._values[_(clave)]
                    self.assertTrue(etiqueta.isVisible())
                    self.assertEqual(etiqueta.full_text(), _("cpu.notintable"))
            # Lo que da el procesador, a su lado y entero.
            self.assertEqual(seccion.processor._values[_("cpu.field.cores")].full_text(), "8")

    def test_en_la_terminal_tambien(self):
        from silux import cli
        salida = io.StringIO()
        with redirect_stdout(salida):
            print(cli.dump(self.fuera, cli.Style(enabled=False)))
        # Solo el bloque del procesador: la gráfica también tiene nombre en clave.
        bloque = salida.getvalue().split("├─")[0]
        filas = {linea.split("  ")[1].strip(): linea for linea in bloque.splitlines()
                 if linea.startswith("  ") and len(linea.split("  ")) > 2}
        for fila in ("Nombre en clave", "Tecnología", "Encapsulado"):
            with self.subTest(fila=fila):
                self.assertIn(_("cpu.notintable"), filas[fila])


if __name__ == "__main__":
    unittest.main()
