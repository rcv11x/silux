"""El orden del árbol de sensores: lo que se mira primero, y cada chip junto.

La rama de la placa abría con nueve tensiones sin nombre; la del procesador
llevaba dieciséis relojes entre sus temperaturas y su consumo; y las sondas
que una Gigabyte publica por dos caminos salían intercaladas, «Temperatura 1»
de un chip, «Temperatura 1» del otro.
"""

import unittest

from silux.i18n import _
from tests import qt
from tests.test_equipos import EQUIPOS, foto

try:
    from PySide6.QtWidgets import QApplication
except ImportError:                                    # pragma: no cover
    QApplication = None


class TestElOrdenDelArbol(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.foto = foto(EQUIPOS / "5800x3d")[0]
        cls.arbol = cls.foto.sensor_tree()

    def test_las_temperaturas_van_antes_que_las_tensiones_y_los_relojes(self):
        for aparato, categorias in self.arbol.items():
            orden = list(categorias)
            with self.subTest(aparato=aparato):
                if "cat.temperature" in orden:
                    self.assertEqual(orden[0], "cat.temperature")
                for tarde in ("cat.voltage", "cat.clock"):
                    for pronto in ("cat.temperature", "cat.fan", "cat.power"):
                        if tarde in orden and pronto in orden:
                            self.assertLess(orden.index(pronto), orden.index(tarde))

    def test_cada_chip_va_junto_y_los_de_relleno_al_final(self):
        placa = self.arbol[self.foto.board.display_name]["cat.temperature"]
        chips = [s.chip for s in placa]
        self.assertGreater(len(set(chips)), 2)
        cambios = sum(1 for a, b in zip(chips, chips[1:]) if a != b)
        self.assertEqual(cambios, len(set(chips)) - 1, chips)
        self.assertTrue(placa[-1].placeholder)
        self.assertFalse(placa[0].placeholder)
        # Y dentro de un chip, en su orden.
        wmi = [s.label for s in placa if s.chip == "gigabyte_wmi"]
        self.assertEqual(wmi, sorted(wmi))


@unittest.skipIf(QApplication is None, "sin PySide6")
class TestLasRamasLargas(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.app = qt.app()
        cls.foto = foto(EQUIPOS / "5800x3d")[0]

    def _arbol(self, plegadas=None):
        from silux.ui import theme
        from silux.ui.sensortree import SensorTree

        arbol = SensorTree(theme.palette_for(self.app, "dark"))
        self.addCleanup(arbol.deleteLater)
        arbol.set_collapsed(plegadas)
        arbol.rebuild(self.foto.sensor_tree())
        return arbol

    def test_los_relojes_por_hilo_nacen_plegados_y_dicen_cuantos_son(self):
        arbol = self._arbol()
        cpu = "AMD Ryzen 7 5800X3D"
        relojes = arbol._rows[f"::{cpu}/cat.clock"]
        self.assertFalse(relojes.isExpanded())
        self.assertEqual(relojes.text(0), f"{_('cat.clock')} · 16")
        # Lo corto sigue abierto: es lo que se viene a mirar.
        temperaturas = arbol._rows[f"::{cpu}/cat.temperature"]
        self.assertTrue(temperaturas.isExpanded())
        self.assertEqual(temperaturas.text(0), _("cat.temperature"))
        self.assertTrue(arbol._rows[f"::{cpu}"].isExpanded())

    def test_lo_que_el_usuario_dejo_manda(self):
        cpu = "AMD Ryzen 7 5800X3D"
        arbol = self._arbol(plegadas=(f"::{cpu}/cat.temperature",))
        self.assertTrue(arbol._rows[f"::{cpu}/cat.clock"].isExpanded())
        self.assertFalse(arbol._rows[f"::{cpu}/cat.temperature"].isExpanded())


if __name__ == "__main__":
    unittest.main()
