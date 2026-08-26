"""La base pci.ids, incluidas las líneas de subsistema.

El tercer nivel del fichero es el que convierte «Radeon RX 9070/9070 XT/9070
GRE» —un nombre para tres tarjetas distintas— en la que de verdad hay puesta,
junto con quien la montó. Se lee en la misma pasada que el resto.
"""

import pathlib
import tempfile
import unittest
from unittest import mock

from silux import pciids

FICHERO = """\
# Un pci.ids recortado
1002  Advanced Micro Devices, Inc. [AMD/ATI]
\t7550  Navi 48 [Radeon RX 9070/9070 XT/9070 GRE]
\t\t1458 2437  Navi 48 XTX [Radeon RX 9070 XT Gaming OC ICE 16G]
\t\t148c 2435  Radeon RX 9070 XT 16GB
\t73df  Navi 22 [Radeon RX 6700/6700 XT]
8086  Intel Corporation
\t9bc4  CometLake-H GT2 [UHD Graphics]
148c  Tul Corporation / PowerColor
"""


class BancoPciIds(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        ruta = pathlib.Path(self._tmp.name) / "pci.ids"
        ruta.write_text(FICHERO, encoding="utf-8")
        patch = mock.patch.object(pciids, "database_path", lambda: ruta)
        patch.start()
        self.addCleanup(patch.stop)
        self.addCleanup(self._tmp.cleanup)


class TestDispositivos(BancoPciIds):
    def test_nombra_fabricante_y_modelo(self):
        resultado = pciids.lookup([(0x1002, 0x7550)])
        self.assertEqual(resultado[(0x1002, 0x7550)],
                         ("Advanced Micro Devices, Inc. [AMD/ATI]",
                          "Navi 48 [Radeon RX 9070/9070 XT/9070 GRE]"))

    def test_varios_fabricantes_de_una_vez(self):
        resultado = pciids.lookup([(0x1002, 0x73DF), (0x8086, 0x9BC4)])
        self.assertEqual(len(resultado), 2)
        self.assertIn("UHD Graphics", resultado[(0x8086, 0x9BC4)][1])

    def test_lo_que_no_esta_simplemente_no_sale(self):
        self.assertEqual(pciids.lookup([(0x1002, 0xFFFF)]), {})

    def test_sin_nada_que_buscar(self):
        self.assertEqual(pciids.lookup([]), {})


class TestSubsistemas(BancoPciIds):
    def test_resuelve_la_tarjeta_concreta(self):
        clave = (0x1002, 0x7550, 0x148C, 0x2435)
        resultado = pciids.lookup([(0x1002, 0x7550)], subsystems=[clave])
        self.assertEqual(resultado[clave],
                         ("Tul Corporation / PowerColor", "Radeon RX 9070 XT 16GB"))

    def test_no_confunde_subsistemas_del_mismo_dispositivo(self):
        claves = [(0x1002, 0x7550, 0x1458, 0x2437), (0x1002, 0x7550, 0x148C, 0x2435)]
        resultado = pciids.lookup([(0x1002, 0x7550)], subsystems=claves)
        self.assertIn("Gaming OC ICE", resultado[claves[0]][1])
        self.assertIn("9070 XT 16GB", resultado[claves[1]][1])

    def test_un_subsistema_que_no_existe(self):
        resultado = pciids.lookup([(0x1002, 0x7550)],
                                  subsystems=[(0x1002, 0x7550, 0xDEAD, 0xBEEF)])
        self.assertNotIn((0x1002, 0x7550, 0xDEAD, 0xBEEF), resultado)
        # El dispositivo sí se resuelve aunque su subsistema no esté.
        self.assertIn((0x1002, 0x7550), resultado)

    def test_no_para_de_leer_antes_de_nombrar_al_fabricante(self):
        # La sección de PowerColor va después de la de AMD en el fichero. La
        # búsqueda salía en cuanto tenía todos los dispositivos, y el nombre
        # del fabricante de la tarjeta se quedaba sin resolver.
        clave = (0x1002, 0x7550, 0x148C, 0x2435)
        resultado = pciids.lookup([(0x1002, 0x7550)], subsystems=[clave])
        self.assertEqual(resultado[clave][0], "Tul Corporation / PowerColor")

    def test_las_lineas_de_subsistema_no_se_toman_por_dispositivos(self):
        # «1458 2437» dentro de 7550 no es el dispositivo 0x1458.
        resultado = pciids.lookup([(0x1002, 0x1458)], subsystems=[])
        self.assertEqual(resultado, {})


class TestSinBaseDeDatos(unittest.TestCase):
    def test_devuelve_vacio_en_vez_de_fallar(self):
        with mock.patch.object(pciids, "database_path", lambda: None):
            self.assertEqual(pciids.lookup([(0x1002, 0x7550)]), {})


if __name__ == "__main__":
    unittest.main()
