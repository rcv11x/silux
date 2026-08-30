"""El consumo del procesador cuando el kernel no deja leerlo.

Desde el 5.10, `energy_uj` no se lee sin privilegios: se restringió porque
muestrearlo a mucha frecuencia deja ver el patrón de consumo de otro proceso.
En las máquinas donde eso pasa —AMD sobre todo— el consumo salía en blanco.

Lo que lo convirtió en un fallo y no en una carencia lo reportó un usuario con
un Ryzen 7 7445HS: «le di permisos pero aún dice que 1 dato requiere permisos,
y al tocarlo no abre el polkit». El aviso lo ponía este proveedor, el usuario
daba los permisos, el ayudante arrancaba… y nadie leía RAPL, así que la nota no
se iba nunca y el botón no tenía nada que hacer.
"""

import pathlib
import tempfile
import unittest
from unittest import mock

from silux.model import Need
from silux.privileged.client import HelperError
from silux.providers import rapl
from silux.providers.base import Draft


class _ClienteFalso:
    """Un ayudante que contesta lo que se le diga."""

    def __init__(self, zonas=None, conectado=True, falla=False):
        self._zonas = zonas or {}
        self._conectado = conectado
        self._falla = falla
        self.veces = 0

    def connected(self) -> bool:
        return self._conectado

    def rapl(self) -> dict:
        self.veces += 1
        if self._falla:
            raise HelperError("no se pudo leer RAPL")
        return dict(self._zonas)


class TestCuandoElKernelLoNiega(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.raiz = pathlib.Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)
        zona = self.raiz / "amd-rapl:0"
        zona.mkdir()
        (zona / "name").write_text("package-0\n", encoding="utf-8")
        # Sin `energy_uj`: es justo lo que el kernel esconde.
        self.zona = zona
        parche = mock.patch.object(rapl, "POWERCAP", self.raiz)
        parche.start()
        self.addCleanup(parche.stop)

    def test_sin_ayudante_se_pide_permiso_en_vez_de_callar(self):
        proveedor = rapl.RaplPower()
        self.assertFalse(proveedor.available())
        camino, necesidad, *_ = proveedor.unavailable_reason()
        self.assertEqual(camino, "cpu.power")
        self.assertEqual(necesidad, Need.ROOT)

    def test_con_el_ayudante_conectado_ya_se_puede(self):
        """Y por tanto la nota de permisos desaparece, que es lo que fallaba."""
        proveedor = rapl.RaplPower(client=_ClienteFalso({"amd-rapl:0": 1}))
        self.assertTrue(proveedor.available())
        self.assertIsNone(proveedor.unavailable_reason())

    def test_un_ayudante_sin_conectar_no_cuenta(self):
        proveedor = rapl.RaplPower(client=_ClienteFalso(conectado=False))
        self.assertFalse(proveedor.available())

    def test_los_vatios_salen_de_dos_lecturas_del_ayudante(self):
        cliente = _ClienteFalso({"amd-rapl:0": 0})
        proveedor = rapl.RaplPower(client=cliente)

        draft = Draft()
        with mock.patch.object(rapl.time, "monotonic", return_value=100.0):
            proveedor.collect(draft)        # primera pasada: solo referencia
        self.assertNotIn("power", draft.cpu_extra)

        # Un julio en un segundo es un vatio.
        cliente._zonas = {"amd-rapl:0": 1_000_000}
        with mock.patch.object(rapl.time, "monotonic", return_value=101.0):
            proveedor.collect(draft)
        self.assertAlmostEqual(draft.cpu_extra["power"].package_w, 1.0)

    def test_se_pregunta_una_vez_por_muestreo_y_no_una_por_zona(self):
        """Con paquete, núcleos y DRAM serían cuatro viajes por segundo."""
        hijo = self.zona / "amd-rapl:0:0"
        hijo.mkdir()
        (hijo / "name").write_text("core\n", encoding="utf-8")

        cliente = _ClienteFalso({"amd-rapl:0": 0, "amd-rapl:0:0": 0})
        proveedor = rapl.RaplPower(client=cliente)
        with mock.patch.object(rapl.time, "monotonic", return_value=1.0):
            proveedor.collect(Draft())
        self.assertEqual(cliente.veces, 1)

    def test_si_el_ayudante_falla_no_se_inventa_un_consumo(self):
        proveedor = rapl.RaplPower(client=_ClienteFalso(falla=True))
        draft = Draft()
        proveedor.collect(draft)
        self.assertNotIn("power", draft.cpu_extra)


class TestSinPowercapNoEsCuestionDePermisos(unittest.TestCase):
    """Un equipo que no trae el contador no lo va a traer con permisos."""

    def test_se_dice_que_es_del_hardware(self):
        with tempfile.TemporaryDirectory() as vacio:
            with mock.patch.object(rapl, "POWERCAP", pathlib.Path(vacio)):
                proveedor = rapl.RaplPower(client=_ClienteFalso())
                camino, necesidad, *_ = proveedor.unavailable_reason()
                self.assertEqual(camino, "cpu.power")
                self.assertEqual(necesidad, Need.HARDWARE)


class TestLoQueLeeElAyudante(unittest.TestCase):
    """La acción nueva del proceso con privilegios."""

    def test_solo_se_admiten_nombres_de_zona(self):
        from silux.privileged import helper

        for bueno in ("intel-rapl:0", "amd-rapl:1"):
            self.assertRegex(bueno, helper.RAPL_ZONE)
        for malo in ("../../etc/shadow", "intel-rapl:0:0", "rapl", ""):
            self.assertNotRegex(malo, helper.RAPL_ZONE)

    def test_la_accion_está_declarada_en_el_protocolo(self):
        from silux.privileged import protocol

        self.assertIn(protocol.ACTION_RAPL, protocol.ACTIONS)
