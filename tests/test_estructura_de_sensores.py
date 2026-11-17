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


@unittest.skipIf(QApplication is None, "sin PySide6")
class TestLoQueNoTieneActividadNacePlegado(unittest.TestCase):
    """Tres conectores de ventilador sin nada enchufado, a 0 RPM, iban delante
    de las tensiones; y cada interfaz de red sin tráfico (seis puentes de
    Docker en el 5800X3D, `interfaz1` en el i5-10400) ponía cuatro renglones
    de ceros al final de la página."""

    @classmethod
    def setUpClass(cls):
        cls.app = qt.app()

    def _pagina(self, equipo, plegadas=()):
        from silux.settings import Preferences
        from silux.tracking import Tracker
        from silux.ui import theme
        from silux.ui.pages.monitor import MonitorPage

        self.foto = foto(EQUIPOS / equipo)[0]
        prefs = Preferences(sensor_collapsed=tuple(plegadas)).normalized()
        pagina = MonitorPage(theme.palette_for(self.app, "dark"), prefs, Tracker())
        self.addCleanup(pagina.deleteLater)
        pagina.resize(1200, 900)
        pagina.show()
        pagina.apply(self.foto)
        self.app.processEvents()
        return pagina

    @staticmethod
    def _hojas(rama):
        return [rama.child(i).text(0) for i in range(rama.childCount())]

    def test_los_ventiladores_parados_van_aparte_y_cerrados(self):
        pagina = self._pagina("5800x3d")
        placa = self.foto.board.display_name
        todos = [s for s in self.foto.sensors
                 if s.device == placa and s.kind.value == "fan"]
        parados = [s.label for s in todos if s.value == 0]
        girando = [s.label for s in todos if s.value > 0]
        # El caso: en esa placa hay de los dos.
        self.assertTrue(parados and girando, (parados, girando))

        filas = pagina.tree._rows
        self.assertEqual(self._hojas(filas[f"::{placa}/cat.fan"]), girando)
        self.assertTrue(filas[f"::{placa}/cat.fan"].isExpanded())
        aparte = filas[f"::{placa}/cat.fan/idle"]
        self.assertEqual(self._hojas(aparte), parados)
        self.assertFalse(aparte.isExpanded())
        self.assertEqual(aparte.text(0),
                         _("sensors.fans.stopped").format(n=len(parados)))
        # Y siguen ahí: ninguno desaparece.
        for sensor in todos:
            self.assertIn(sensor.key, filas)

    def test_si_todos_estan_parados_se_cierra_la_categoria_sin_partirla(self):
        pagina = self._pagina("5800x3d")
        grafica = self.foto.gpus[0].name
        ventiladores = [s for s in self.foto.sensors
                        if s.device == grafica and s.kind.value == "fan"]
        self.assertTrue(ventiladores and all(s.value == 0 for s in ventiladores))
        filas = pagina.tree._rows
        self.assertFalse(filas[f"::{grafica}/cat.fan"].isExpanded())
        self.assertNotIn(f"::{grafica}/cat.fan/idle", filas)
        self.assertEqual(filas[f"::{grafica}/cat.fan"].text(0), _("cat.fan"))
        self.assertTrue(filas[f"::{grafica}"].isExpanded())

    def test_el_que_arranca_vuelve_con_los_demas(self):
        import dataclasses

        pagina = self._pagina("5800x3d")
        placa = self.foto.board.display_name
        parado = next(s for s in self.foto.sensors
                      if s.device == placa and s.kind.value == "fan" and s.value == 0)
        girando = dataclasses.replace(self.foto, sensors=tuple(
            dataclasses.replace(s, value=640.0) if s.key == parado.key else s
            for s in self.foto.sensors))
        pagina.apply(girando)
        self.app.processEvents()
        filas = pagina.tree._rows
        self.assertIn(parado.label, self._hojas(filas[f"::{placa}/cat.fan"]))
        self.assertNotIn(parado.label, self._hojas(filas[f"::{placa}/cat.fan/idle"]))

    def test_las_interfaces_sin_trafico_nacen_cerradas_y_la_principal_no(self):
        from silux.ui.pages.network import main_interface

        for equipo in ("i5-10400", "5800x3d"):
            with self.subTest(equipo=equipo):
                pagina = self._pagina(equipo)
                principal, todas = main_interface(self.foto.network)
                filas = pagina.tree._rows
                ramas = {i.name: filas[f"::Red ({i.name})"] for i in todas
                         if f"::Red ({i.name})" in filas}
                self.assertGreater(len(ramas), 1)
                self.assertTrue(ramas[principal.name].isExpanded())
                for nombre, rama in ramas.items():
                    if nombre != principal.name:
                        self.assertFalse(rama.isExpanded(), nombre)

    def test_la_que_resulta_tener_trafico_se_abre_al_rehacer_el_arbol(self):
        """En la primera muestra ninguna tiene ritmo todavía."""
        import dataclasses
        from silux.ui.pages.network import main_interface

        pagina = self._pagina("5800x3d")
        principal, todas = main_interface(self.foto.network)
        otra = next(i for i in todas if i is not principal
                    and f"::Red ({i.name})" in pagina.tree._rows)
        self.assertFalse(pagina.tree._rows[f"::Red ({otra.name})"].isExpanded())
        con_ritmo = dataclasses.replace(otra, traffic=dataclasses.replace(
            otra.traffic, rx_rate_bps=4096.0, tx_rate_bps=512.0))
        despues = dataclasses.replace(self.foto, network=tuple(
            con_ritmo if i is otra else i for i in self.foto.network))
        pagina.tree.rebuild(despues.sensor_tree(), pagina._inactivos(despues))
        self.assertTrue(pagina.tree._rows[f"::Red ({otra.name})"].isExpanded())

    def test_lo_que_el_usuario_dejo_manda_tambien_aqui(self):
        pagina = self._pagina("5800x3d", plegadas=("::Memoria",))
        placa = self.foto.board.display_name
        self.assertTrue(pagina.tree._rows[f"::{placa}/cat.fan/idle"].isExpanded())


if __name__ == "__main__":
    unittest.main()
