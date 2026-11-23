"""Red: las interfaces virtuales, agrupadas y plegadas debajo de las físicas.

En un equipo con Docker la página de Red eran veinte tarjetas de puentes
antes de llegar a la de la tarjeta de red. Los puentes, los `veth`, el túnel
de Tailscale y el bucle local los crea un programa: no son hardware. Van
debajo, en un renglón que dice cuántas son y que se abre al pulsarlo.

Con los volcados de los dos equipos: el 5800X3D con dos tarjetas y seis
virtuales, el i5-10400 con una y veintitrés.
"""

import dataclasses
import unittest

from tests import qt
from tests.test_equipos import EQUIPOS, foto, shared_snapshot

try:
    from PySide6.QtWidgets import QApplication
except ImportError:                                    # pragma: no cover
    QApplication = None

FISICAS = {"5800x3d": ["enp6s0", "enp5s0"], "i5-10400": ["enp1s0"]}


@unittest.skipIf(QApplication is None, "sin PySide6")
class TestLasVirtualesVanAparte(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.app = qt.app()
        cls.fotos = {n: shared_snapshot(EQUIPOS / n) for n in FISICAS}

    def _pagina(self, f):
        from silux.settings import Preferences
        from silux.ui import theme
        from silux.ui.pages.network import NetworkPage

        theme.set_density("normal", "normal")
        self.pagina = NetworkPage(theme.palette_for(self.app, "dark"),
                                  Preferences().normalized())
        self.pagina.resize(1200, 800)
        self.pagina.show()
        self.addCleanup(self.pagina.close)
        self.pagina.apply(f)
        self.pagina.apply(f)
        self.app.processEvents()
        return self.pagina

    @staticmethod
    def _nombres(tabla):
        return [fila[0].full_text() for fila in tabla._cells]

    def test_arriba_solo_las_fisicas_y_la_activa_primero(self):
        for nombre, fisicas in FISICAS.items():
            with self.subTest(equipo=nombre):
                pagina = self._pagina(self.fotos[nombre])
                self.assertEqual(self._nombres(pagina.traffic), fisicas)
                self.assertEqual(list(pagina._montadas["fisicas"]), fisicas)

    def test_las_virtuales_salen_plegadas_en_un_renglon(self):
        for nombre, fisicas in FISICAS.items():
            with self.subTest(equipo=nombre):
                f = self.fotos[nombre]
                pagina = self._pagina(f)
                virtuales = len(f.network) - len(fisicas)
                self.assertTrue(pagina.virtual_toggle.isVisible())
                self.assertIn(str(virtuales), pagina.virtual_toggle.text())
                self.assertFalse(pagina.virtual_box.isVisible())
                # Plegadas no se montan: ninguna tarjeta de un puente.
                self.assertNotIn("docker0", pagina._grids)
                self.assertNotIn("virtuales", pagina._montadas)

    def test_al_pulsar_se_abren_y_al_volver_a_pulsar_se_pliegan(self):
        f = self.fotos["5800x3d"]
        pagina = self._pagina(f)
        pagina.virtual_toggle.click()
        self.app.processEvents()
        self.assertTrue(pagina.virtual_box.isVisible())
        en_la_tabla = set(self._nombres(pagina.virtual_traffic))
        self.assertEqual(en_la_tabla, {i.name for i in f.network} - set(FISICAS["5800x3d"]))
        for una in ("docker0", "tailscale0", "virbr0", "lo"):
            self.assertIn(una, en_la_tabla)
            self.assertIn(una, pagina._grids)
        # Abiertas, siguen abiertas con la muestra siguiente.
        pagina.apply(f)
        self.assertTrue(pagina.virtual_box.isVisible())
        pagina.virtual_toggle.click()
        self.assertFalse(pagina.virtual_box.isVisible())

    def test_van_debajo_de_las_fisicas(self):
        from PySide6.QtCore import QPoint

        pagina = self._pagina(self.fotos["5800x3d"])
        raiz = pagina.widget()
        tarjeta = pagina._cards["enp6s0"]
        self.assertGreater(pagina.virtual_toggle.mapTo(raiz, QPoint(0, 0)).y(),
                           tarjeta.mapTo(raiz, QPoint(0, 0)).y() + tarjeta.height() - 1)

    def test_sin_virtuales_no_hay_renglon(self):
        from silux.ui.pages.network import is_physical

        f = self.fotos["5800x3d"]
        solo = dataclasses.replace(f, network=tuple(i for i in f.network if is_physical(i)))
        pagina = self._pagina(solo)
        self.assertFalse(pagina.virtual_toggle.isVisible())
        self.assertFalse(pagina.virtual_box.isVisible())

    def test_la_cabecera_cuenta_las_fisicas(self):
        pagina = self._pagina(self.fotos["i5-10400"])
        insignias = " ".join(pagina._chip_signature)
        self.assertIn("1 de 1", insignias)
        self.assertNotIn("24", insignias)


if __name__ == "__main__":
    unittest.main()
