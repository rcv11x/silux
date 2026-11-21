"""Qué hace el recolector cuando un proveedor se cae.

El motivo que se le pone a un dato ausente no es decoración: es lo que el
usuario lee para saber si puede hacer algo al respecto. Marcar un permiso
denegado como «no aplica a esta plataforma» le dice que se rinda cuando lo
que le pasa tiene arreglo.
"""

import os
import pathlib
import unittest
from unittest import mock

from silux.collector import Collector
from silux.model import Need
from silux.providers.base import Provider


class _Rompe(Provider):
    name = "prueba"
    provides = "cosa"

    def __init__(self, excepcion):
        self._excepcion = excepcion

    def available(self) -> bool:
        return True

    def collect(self, draft) -> None:
        raise self._excepcion


def _nota_de(excepcion):
    draft = Collector()._collect([_Rompe(excepcion)])
    notas = [n for n in draft.notes if n.path == "cosa"]
    assert len(notas) == 1, notas
    return notas[0]


class TestExcepciones(unittest.TestCase):
    def test_un_permiso_denegado_pide_permisos(self):
        nota = _nota_de(PermissionError(13, "Permission denied", "/sys/class/net"))
        self.assertEqual(nota.need, Need.ROOT)
        # The path, for the report; on screen, plain words.
        self.assertIn("/sys/class/net", nota.detail)
        self.assertNotIn("/sys", nota.message)

    def test_y_no_dice_que_la_plataforma_no_aplique(self):
        """Salía así en un aarch64 enjaulado: hasta la red «no aplicaba»."""
        nota = _nota_de(PermissionError(13, "Permission denied", "/sys/class/net"))
        self.assertNotEqual(nota.need, Need.PLATFORM)

    def test_un_fichero_que_no_esta_es_hardware_que_no_lo_publica(self):
        nota = _nota_de(FileNotFoundError(2, "No such file", "/sys/class/hwmon"))
        self.assertEqual(nota.need, Need.HARDWARE)
        self.assertIn("/sys/class/hwmon", nota.detail)
        self.assertNotIn("/sys", nota.message)

    def test_lo_demas_es_un_fallo_nuestro_y_se_dice(self):
        nota = _nota_de(ValueError("me he liado"))
        self.assertEqual(nota.need, Need.ERROR)
        self.assertIn("me he liado", nota.message)
        self.assertIn("informe", nota.hint)

    def test_un_proveedor_roto_no_se_lleva_a_los_demas(self):
        class _Va(Provider):
            name, provides = "va", "otra"
            def available(self): return True
            def collect(self, draft): draft.system = "llegué"

        draft = Collector()._collect([_Rompe(ValueError("x")), _Va()])
        self.assertEqual(draft.system, "llegué")


class TestOurOwnFailures(unittest.TestCase):
    """A file missing outside what the system publishes is our failure: it
    said «this machine does not publish it», which breaks rule 5. It is an
    error, and the report carries its traceback."""

    def test_a_missing_file_of_ours_is_an_error(self):
        nota = _nota_de(FileNotFoundError(2, "No such file", "/opt/silux/db/cpu_ids.json"))
        self.assertEqual(nota.need, Need.ERROR)

    def test_inside_a_dump_a_system_file_is_still_the_hardwares(self):
        with mock.patch.dict(os.environ, {"SILUX_SYSROOT": "/tmp/volcado"}):
            nota = _nota_de(FileNotFoundError(2, "No such file", "/tmp/volcado/sys/class/hwmon"))
        self.assertEqual(nota.need, Need.HARDWARE)

    def test_the_report_carries_its_traceback_without_the_home_folder(self):
        from silux import report
        casa = str(pathlib.Path.home())
        recolector = Collector(providers=[
            _Rompe(FileNotFoundError(2, "No such file", f"{casa}/silux/db/scores.json"))])
        foto = recolector.snapshot()
        self.assertEqual([f.where for f in foto.failures], ["prueba"])
        texto = report.build(foto)
        self.assertIn("Traceback (most recent call last)", texto)
        self.assertIn("test_collector.py", texto)
        self.assertNotIn(casa + "/", texto)

    def test_the_same_failure_again_only_counts(self):
        recolector = Collector(providers=[_Rompe(ValueError("otra vez"))])
        recolector.snapshot()
        foto = recolector.snapshot()
        self.assertEqual([(f.where, f.count) for f in foto.failures], [("prueba", 2)])

    def test_a_failure_between_samples_is_not_swallowed(self):
        class _Entre(Provider):
            name, provides = "entre", "algo"
            def available(self): return True
            def collect(self, draft): pass
            def wants_between_samples(self): return True
            def between_samples(self): raise KeyError("temp1")

        recolector = Collector(providers=[_Entre()])
        recolector.between_samples()
        foto = recolector.snapshot()
        self.assertEqual([f.where for f in foto.failures], ["entre.between_samples"])
        self.assertFalse(foto.notes)          # the page loses nothing


if __name__ == "__main__":
    unittest.main()
