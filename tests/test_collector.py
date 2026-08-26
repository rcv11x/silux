"""Qué hace el recolector cuando un proveedor se cae.

El motivo que se le pone a un dato ausente no es decoración: es lo que el
usuario lee para saber si puede hacer algo al respecto. Marcar un permiso
denegado como «no aplica a esta plataforma» le dice que se rinda cuando lo
que le pasa tiene arreglo.
"""

import unittest

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
        self.assertIn("/sys/class/net", nota.message)

    def test_y_no_dice_que_la_plataforma_no_aplique(self):
        """Salía así en un aarch64 enjaulado: hasta la red «no aplicaba»."""
        nota = _nota_de(PermissionError(13, "Permission denied", "/sys/class/net"))
        self.assertNotEqual(nota.need, Need.PLATFORM)

    def test_un_fichero_que_no_esta_es_hardware_que_no_lo_publica(self):
        nota = _nota_de(FileNotFoundError(2, "No such file", "/sys/class/hwmon"))
        self.assertEqual(nota.need, Need.HARDWARE)
        self.assertIn("/sys/class/hwmon", nota.message)

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


if __name__ == "__main__":
    unittest.main()
