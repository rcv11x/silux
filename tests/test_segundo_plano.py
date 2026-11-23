"""`pkexec` no se espera en el hilo de la interfaz (F-M4).

Instalar el ayudante y cargar un módulo abren el diálogo de la contraseña, y
los dos lo esperaban con `subprocess.run` dentro del manejador del botón: con
el diálogo abierto la ventana no repintaba. Aquí la orden se cambia por una
que tarda lo que se le diga, que es lo que hace `pkexec` mientras alguien
escribe, y se mira que el botón vuelva enseguida y que el resultado llegue
después.

Lo que se ejecuta de verdad —la orden, sin ninguna ruta que no sea de root—
lo vigila `test_pkexec`, y aquí no se toca.
"""

import os
import sys
import tempfile
import time
import unittest
from unittest import mock

from tests import qt

try:
    from PySide6.QtWidgets import QApplication, QMessageBox
except ImportError:                                    # pragma: no cover
    QApplication = None

LENTA = 0.6


def orden(segundos: float = LENTA, codigo: int = 0, queja: str = "") -> list:
    """Una orden que lee su entrada, espera y sale con el código pedido."""
    return [sys.executable, "-c",
            "import sys, time; sys.stdin.read(); time.sleep(%r); "
            "sys.stderr.write(%r); sys.exit(%d)" % (segundos, queja, codigo)]


def esperar(app, condicion, tope: float = 8.0) -> bool:
    fin = time.monotonic() + tope
    while time.monotonic() < fin:
        app.processEvents()
        if condicion():
            return True
        time.sleep(0.01)
    return False


@unittest.skipIf(QApplication is None, "sin PySide6")
class TestLaOrden(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.app = qt.app()

    def _lanzar(self, *args, **kwargs):
        from silux.ui.background import BackgroundCommand

        resultados = []
        tarea = BackgroundCommand(*args, **kwargs)
        tarea.done.connect(resultados.append)
        tarea.start()
        return tarea, resultados

    def test_devuelve_el_codigo_y_lo_que_escribio(self):
        tarea, resultados = self._lanzar(orden(0.0, 3, "no se pudo"), stdin="x")
        self.assertTrue(esperar(self.app, lambda: resultados))
        tarea.wait()
        self.assertEqual(resultados[0].returncode, 3)
        self.assertEqual(resultados[0].stderr, "no se pudo")
        self.assertIsNone(resultados[0].error)

    def test_una_orden_que_no_existe_no_revienta(self):
        tarea, resultados = self._lanzar(["/no/existe/silux-nada"])
        self.assertTrue(esperar(self.app, lambda: resultados))
        tarea.wait()
        self.assertIsNone(resultados[0].returncode)
        self.assertTrue(resultados[0].error)

    def test_la_que_no_acaba_se_corta_a_su_hora(self):
        tarea, resultados = self._lanzar(orden(30.0), timeout=0.3)
        self.assertTrue(esperar(self.app, lambda: resultados))
        tarea.wait()
        self.assertTrue(resultados[0].error)

    def test_cancelarla_la_mata_y_no_avisa(self):
        tarea, resultados = self._lanzar(orden(30.0))
        time.sleep(0.2)
        antes = time.monotonic()
        tarea.cancel()
        self.assertLess(time.monotonic() - antes, 3.0)
        self.assertFalse(tarea.isRunning())
        self.app.processEvents()
        self.assertEqual(resultados, [])


@unittest.skipIf(QApplication is None, "sin PySide6")
class TestInstalarElAyudante(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.app = qt.app()

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        parche = mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": tmp.name})
        parche.start()
        self.addCleanup(parche.stop)

    def _ventana(self, la_orden):
        from silux.settings import Preferences
        from silux.ui.app import MainWindow

        ventana = MainWindow(Preferences().normalized())
        self.addCleanup(ventana.close)
        parche = mock.patch.object(MainWindow, "_orden_de_instalacion",
                                   staticmethod(lambda: (la_orden, "el ayudante")))
        parche.start()
        self.addCleanup(parche.stop)
        return ventana

    def test_el_boton_vuelve_antes_de_que_acabe_pkexec(self):
        ventana = self._ventana(orden(LENTA))
        antes = time.monotonic()
        ventana._on_permanent_requested()
        self.assertLess(time.monotonic() - antes, LENTA / 2,
                        "el manejador del botón esperó a la orden")
        # Y mientras tanto la ventana atiende: los botones dicen que se está
        # instalando, que antes no llegaba a pintarse.
        self.app.processEvents()
        self.assertFalse(ventana.memory_page.permanent_button.isEnabled())
        self.assertTrue(esperar(self.app, lambda: ventana._instalacion is None))

    def test_al_acabar_bien_lo_dice(self):
        from silux.i18n import _

        ventana = self._ventana(orden(0.0))
        ventana._on_permanent_requested()
        self.assertTrue(esperar(self.app, lambda: ventana._instalacion is None))
        self.assertEqual(ventana._status.full_text(), _("perm.installed"))

    def test_cancelar_la_contrasena_no_es_un_fallo(self):
        ventana = self._ventana(orden(0.0, 126))
        with mock.patch.object(QMessageBox, "warning") as aviso:
            ventana._on_permanent_requested()
            self.assertTrue(esperar(self.app, lambda: ventana._instalacion is None))
        aviso.assert_not_called()
        self.assertTrue(ventana.memory_page.permanent_button.isEnabled())

    def test_un_fallo_de_verdad_se_ensena(self):
        ventana = self._ventana(orden(0.0, 1, "no hay sitio en /usr/local"))
        with mock.patch.object(QMessageBox, "warning") as aviso:
            ventana._on_permanent_requested()
            self.assertTrue(esperar(self.app, lambda: ventana._instalacion is None))
        aviso.assert_called_once()
        self.assertIn("no hay sitio", aviso.call_args.args[2])

    def test_pulsar_dos_veces_no_abre_dos_dialogos(self):
        ventana = self._ventana(orden(LENTA))
        ventana._on_permanent_requested()
        primera = ventana._instalacion
        ventana._on_permanent_requested()
        self.assertIs(ventana._instalacion, primera)
        self.assertTrue(esperar(self.app, lambda: ventana._instalacion is None))

    def test_cerrar_con_el_dialogo_abierto_no_espera_ni_aborta(self):
        ventana = self._ventana(orden(30.0))
        ventana._on_permanent_requested()
        time.sleep(0.2)
        antes = time.monotonic()
        ventana.close()
        self.assertLess(time.monotonic() - antes, 5.0)
        self.assertIsNone(ventana._instalacion)


class TestLoadingAModule(unittest.TestCase):
    """Loading a module goes through the sampling thread, where the password
    window may block: the button only sets a flag."""

    def test_what_each_outcome_says(self):
        from silux.privileged.client import HelperDenied, HelperError
        from silux.ui.sampler import Sampler

        collector = mock.Mock()
        self.assertEqual(Sampler._load(collector, "drivetemp"), "")
        collector.load_module.side_effect = HelperDenied("cancelled")
        self.assertIsNone(Sampler._load(collector, "drivetemp"))
        collector.load_module.side_effect = HelperError("modprobe: not found")
        self.assertEqual(Sampler._load(collector, "drivetemp"), "modprobe: not found")

    def test_asking_does_not_wait(self):
        from silux.ui.sampler import Sampler

        sampler = Sampler()
        before = time.monotonic()
        sampler.request_module_load("drivetemp")
        self.assertLess(time.monotonic() - before, 0.1)
        self.assertEqual(sampler._module_to_load, "drivetemp")


class TestTheCollectorLoadsAModule(unittest.TestCase):

    def _collector(self, connected: bool):
        from silux.collector import Collector
        from silux.privileged.client import PrivilegedClient

        client = mock.Mock(spec=PrivilegedClient)
        client.connected.return_value = connected
        provider = mock.Mock(client=client, static=True)
        collector = Collector(providers=[provider])
        collector._static = object()
        return collector, client

    def test_a_helper_started_for_it_is_closed(self):
        collector, client = self._collector(connected=False)
        collector.load_module("drivetemp")
        client.load_module.assert_called_once_with("drivetemp")
        client.close.assert_called_once()
        self.assertIsNone(collector._static)

    def test_one_already_running_stays(self):
        collector, client = self._collector(connected=True)
        collector.load_module("drivetemp")
        client.close.assert_not_called()

    def test_closed_even_when_it_fails(self):
        from silux.privileged.client import HelperError

        collector, client = self._collector(connected=False)
        client.load_module.side_effect = HelperError("no")
        with self.assertRaises(HelperError):
            collector.load_module("drivetemp")
        client.close.assert_called_once()

if __name__ == "__main__":
    unittest.main()
