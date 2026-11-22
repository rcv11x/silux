"""El orden del árbol de sensores: lo que se mira primero, y cada chip junto.

La rama de la placa abría con nueve tensiones sin nombre; la del procesador
llevaba dieciséis relojes entre sus temperaturas y su consumo; y las sondas
que una Gigabyte publica por dos caminos salían intercaladas, «Temperatura 1»
de un chip, «Temperatura 1» del otro.
"""

import unittest

from silux.model import Snapshot

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
        placa = self.arbol["board"]["cat.temperature"]
        chips = [s.chip for s in placa]
        # El Super I/O y las zonas de ACPI; lo que `gigabyte_wmi` repite del
        # primero ya no entra en el árbol (tests/test_sensores_repetidos.py).
        self.assertGreater(len(set(chips)), 1)
        cambios = sum(1 for a, b in zip(chips, chips[1:]) if a != b)
        self.assertEqual(cambios, len(set(chips)) - 1, chips)
        self.assertTrue(placa[-1].placeholder)
        self.assertFalse(placa[0].placeholder)
        # Y dentro de un chip, en su orden.
        del_chip = [s.label for s in placa if s.chip.startswith("it8688")]
        self.assertEqual(len(del_chip), 6)
        self.assertEqual(del_chip, sorted(del_chip))


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
        cpu = "cpu"                 # its raw key: «AMD Ryzen 7 5800X3D»
        relojes = arbol._rows[f"::{cpu}/cat.clock"]
        self.assertFalse(relojes.isExpanded())
        self.assertEqual(relojes.text(0), f"{_('cat.clock')} · 16")
        # Lo corto sigue abierto: es lo que se viene a mirar.
        temperaturas = arbol._rows[f"::{cpu}/cat.temperature"]
        self.assertTrue(temperaturas.isExpanded())
        self.assertEqual(temperaturas.text(0), _("cat.temperature"))
        self.assertTrue(arbol._rows[f"::{cpu}"].isExpanded())

    def test_lo_que_el_usuario_dejo_manda(self):
        from silux.ui import theme
        from silux.ui.sensortree import SensorTree

        cpu = "cpu"                 # its raw key: «AMD Ryzen 7 5800X3D»
        arbol = SensorTree(theme.palette_for(self.app, "dark"))
        self.addCleanup(arbol.deleteLater)
        arbol.set_collapsed((f"::{cpu}/cat.temperature",), (f"::{cpu}/cat.clock",))
        arbol.rebuild(self.foto.sensor_tree())
        self.assertFalse(arbol._rows[f"::{cpu}/cat.temperature"].isExpanded())
        self.assertTrue(arbol._rows[f"::{cpu}/cat.clock"].isExpanded())

    def test_lo_que_no_eligio_sigue_la_regla_aunque_tenga_algo_guardado(self):
        """Se guardaba el estado entero, y con una sola rama cerrada a mano
        todas las demás quedaban «elegidas abiertas»: las largas incluidas, y
        cualquier regla nueva no llegaba a quien ya tenía preferencias."""
        cpu = "cpu"                 # its raw key: «AMD Ryzen 7 5800X3D»
        arbol = self._arbol(plegadas=(f"::{cpu}/cat.temperature",))
        self.assertFalse(arbol._rows[f"::{cpu}/cat.clock"].isExpanded())
        self.assertTrue(arbol._rows[f"::{cpu}"].isExpanded())

    def test_montar_el_arbol_no_es_una_eleccion_del_usuario(self):
        arbol = self._arbol()
        avisos = []
        arbol.branchesChanged.connect(lambda c, a: avisos.append((c, a)))
        arbol.rebuild(self.foto.sensor_tree())
        arbol.set_filter("tctl")
        arbol.set_filter("")
        self.assertEqual(avisos, [])
        self.assertEqual((arbol.collapsed(), arbol.expanded()), ((), ()))

    def test_solo_se_apunta_lo_que_se_aparta_de_la_regla(self):
        cpu = "cpu"                 # its raw key: «AMD Ryzen 7 5800X3D»
        arbol = self._arbol()
        avisos = []
        arbol.branchesChanged.connect(lambda c, a: avisos.append((c, a)))
        temperaturas = arbol._rows[f"::{cpu}/cat.temperature"]
        relojes = arbol._rows[f"::{cpu}/cat.clock"]

        temperaturas.setExpanded(False)             # como un clic del usuario
        self.assertEqual(avisos[-1], ((f"::{cpu}/cat.temperature",), ()))
        temperaturas.setExpanded(True)              # y se arrepiente
        self.assertEqual(avisos[-1], ((), ()))
        relojes.setExpanded(True)                   # abre una de las largas
        self.assertEqual(avisos[-1], ((), (f"::{cpu}/cat.clock",)))
        relojes.setExpanded(False)
        self.assertEqual(avisos[-1], ((), ()))


@unittest.skipIf(QApplication is None, "sin PySide6")
class TestLoQueNoTieneActividadNacePlegado(unittest.TestCase):
    """Tres conectores de ventilador sin nada enchufado, a 0 RPM, iban delante
    de las tensiones; y cada interfaz de red sin tráfico (seis puentes de
    Docker en el 5800X3D, `interfaz1` en el i5-10400) ponía cuatro renglones
    de ceros al final de la página."""

    @classmethod
    def setUpClass(cls):
        cls.app = qt.app()

    @staticmethod
    def _first_sample(folder):
        """What the collector reads first: no rates yet, as on opening."""
        from silux import volcado
        from silux.collector import Collector

        with volcado.mounted(folder):
            collector = Collector()
            try:
                return collector.snapshot()
            finally:
                collector.close()

    def _pagina(self, equipo, plegadas=(), abiertas=(), first=False):
        from silux.settings import Preferences
        from silux.tracking import Tracker
        from silux.ui import theme
        from silux.ui.pages.monitor import MonitorPage

        self.foto = (self._first_sample(EQUIPOS / equipo) if first
                     else foto(EQUIPOS / equipo)[0])
        prefs = Preferences(sensor_collapsed=tuple(plegadas),
                            sensor_expanded=tuple(abiertas)).normalized()
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
        placa = "board"
        todos = [s for s in self.foto.sensors
                 if s.group == placa and s.kind.value == "fan"]
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
        grafica = f"gpu:{self.foto.gpus[0].pci_slot}"
        ventiladores = [s for s in self.foto.sensors
                        if s.group == grafica and s.kind.value == "fan"]
        self.assertTrue(ventiladores and all(s.value == 0 for s in ventiladores))
        filas = pagina.tree._rows
        self.assertFalse(filas[f"::{grafica}/cat.fan"].isExpanded())
        self.assertNotIn(f"::{grafica}/cat.fan/idle", filas)
        self.assertEqual(filas[f"::{grafica}/cat.fan"].text(0), _("cat.fan"))
        self.assertTrue(filas[f"::{grafica}"].isExpanded())

    def test_el_que_arranca_vuelve_con_los_demas(self):
        import dataclasses

        pagina = self._pagina("5800x3d")
        placa = "board"
        parado = next(s for s in self.foto.sensors
                      if s.group == placa and s.kind.value == "fan" and s.value == 0)
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

        folded = 0
        for equipo, first in (("i5-10400", False), ("5800x3d", False), ("5800x3d", True)):
            with self.subTest(equipo=equipo, primera=first):
                pagina = self._pagina(equipo, first=first)
                principal, todas = main_interface(self.foto.network)
                filas = pagina.tree._rows
                ramas = {i.name: (i, filas[f"::net:{i.name}"]) for i in todas
                         if f"::net:{i.name}" in filas}
                self.assertGreater(len(ramas), 1)
                self.assertTrue(ramas[principal.name][1].isExpanded())
                for nombre, (interfaz, rama) in ramas.items():
                    if nombre != principal.name:
                        traffic = bool(interfaz.traffic.rx_rate_bps or interfaz.traffic.tx_rate_bps)
                        self.assertEqual(rama.isExpanded(), traffic, nombre)
                        folded += not traffic
        self.assertGreater(folded, 1)

    def test_la_que_resulta_tener_trafico_se_abre_al_rehacer_el_arbol(self):
        """En la primera muestra ninguna tiene ritmo todavía."""
        import dataclasses
        from silux.ui.pages.network import main_interface

        pagina = self._pagina("5800x3d", first=True)
        principal, todas = main_interface(self.foto.network)
        otra = next(i for i in todas if i is not principal
                    and f"::net:{i.name}" in pagina.tree._rows)
        self.assertFalse(pagina.tree._rows[f"::net:{otra.name}"].isExpanded())
        con_ritmo = dataclasses.replace(otra, traffic=dataclasses.replace(
            otra.traffic, rx_rate_bps=4096.0, tx_rate_bps=512.0))
        despues = dataclasses.replace(self.foto, network=tuple(
            con_ritmo if i is otra else i for i in self.foto.network))
        pagina.tree.rebuild(despues.sensor_tree(), pagina._inactivos(despues))
        self.assertTrue(pagina.tree._rows[f"::net:{otra.name}"].isExpanded())

    def test_lo_que_el_usuario_dejo_manda_tambien_aqui(self):
        placa = "board"             # «Gigabyte X570 AORUS ELITE»
        pagina = self._pagina("5800x3d", abiertas=(f"::{placa}/cat.fan/idle",))
        self.assertEqual(Snapshot.device_name(self.foto.sensor_tree()[placa]),
                         self.foto.board.display_name)
        self.assertTrue(pagina.tree._rows[f"::{placa}/cat.fan/idle"].isExpanded())

    def test_con_las_preferencias_de_antes_lo_inactivo_tambien_se_pliega(self):
        """Las del autor: tres ramas cerradas a mano, guardadas cuando se
        guardaba el estado entero. Lo nuevo le tiene que llegar igual."""
        cpu = "cpu"                 # its raw key: «AMD Ryzen 7 5800X3D»
        # (El consumo del procesador no está en el volcado: sale de restar
        # dos lecturas. Que su rama esté guardada y no exista no rompe nada.)
        pagina = self._pagina("5800x3d", first=True, plegadas=(
            f"::{cpu}/cat.power", f"::{cpu}/cat.temperature", "::net:enp6s0/cat.network"))
        placa = "board"
        filas = pagina.tree._rows
        self.assertFalse(filas[f"::{placa}/cat.fan/idle"].isExpanded())
        self.assertFalse(filas[f"::{cpu}/cat.temperature"].isExpanded())
        self.assertFalse(filas["::net:enp6s0/cat.network"].isExpanded())
        self.assertTrue(filas["::net:enp6s0"].isExpanded())
        cerradas = [c for c in filas if c.startswith("::net:") and c.count("/") == 0
                    and not filas[c].isExpanded()]
        self.assertTrue(cerradas)

    def test_la_pagina_no_guarda_nada_por_montarse(self):
        guardado = []
        pagina = self._pagina("5800x3d")
        pagina.branches_changed.connect(lambda c, a: guardado.append((c, a)))
        pagina.apply(self.foto)
        self.app.processEvents()
        self.assertEqual(guardado, [])


if __name__ == "__main__":
    unittest.main()
