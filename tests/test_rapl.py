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

import json
import pathlib
import tempfile
import unittest
from unittest import mock

from silux.model import Need
from silux.privileged.client import HelperError, PrivilegedClient
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

        for bueno in ("intel-rapl:0", "amd-rapl:1", "intel-rapl:0:0", "intel-rapl:0:2"):
            self.assertRegex(bueno, helper.RAPL_ZONE)
        for malo in ("../../etc/shadow", "rapl", "", "intel-rapl:0:0:0", "intel-rapl-mmio:0",
                     "intel-rapl:0\n", "intel-rapl:0/energy_uj"):
            self.assertNotRegex(malo, helper.RAPL_ZONE)

    def test_la_accion_está_declarada_en_el_protocolo(self):
        from silux.privileged import protocol

        self.assertIn(protocol.ACTION_RAPL, protocol.ACTIONS)


class _InProcessClient(PrivilegedClient):
    """The real client talking to the real helper, in this process: what
    `handle` answers, through JSON as the pipe carries it."""

    def connected(self) -> bool:
        return True

    def request(self, payload, timeout=None):
        from silux.privileged import helper
        return json.loads(json.dumps(helper.handle(json.loads(json.dumps(payload)))))


class TestAnIntelsSubzonesThroughTheHelper(unittest.TestCase):
    """The author's T14 with permissions: «Consumo 3 W» and nothing else. The
    helper took one level of zones, and its test listed `intel-rapl:0:0` as a
    bad name; the provider's test used a fake that gave the sub-zone anyway.

    Two trees, because the user running the tests can read what the kernel
    keeps for root: the helper's, flat as /sys/class/powercap lists every
    zone, with `energy_uj`; the provider's, nested as the kernel has them,
    without it.
    """

    ZONES = {"intel-rapl:0": "package-0", "intel-rapl:0:0": "core",
             "intel-rapl:0:1": "uncore", "intel-rapl:1": "psys",
             "intel-rapl-mmio:0": "package-0"}

    def setUp(self):
        from silux.privileged import helper
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.del_ayudante = pathlib.Path(tmp.name) / "helper"
        self.del_proveedor = pathlib.Path(tmp.name) / "provider"
        for zone, name in self.ZONES.items():
            (self.del_ayudante / zone).mkdir(parents=True)
            (self.del_ayudante / zone / "name").write_text(name + "\n")
            padre = zone.rsplit(":", 1)[0] if zone.count(":") == 2 else None
            sitio = (self.del_proveedor / padre / zone) if padre else self.del_proveedor / zone
            sitio.mkdir(parents=True, exist_ok=True)
            (sitio / "name").write_text(name + "\n")
        for parche in (mock.patch.object(helper, "POWERCAP", str(self.del_ayudante)),
                       mock.patch.object(rapl, "POWERCAP", self.del_proveedor),
                       mock.patch.dict(helper._LAST_READ, clear=True)):
            parche.start()
            self.addCleanup(parche.stop)

    def _energia(self, **julios):
        for zone, value in julios.items():
            (self.del_ayudante / zone / "energy_uj").write_text(f"{int(value * 1e6)}\n")

    def test_the_helper_gives_core_and_uncore(self):
        from silux.privileged import helper
        self._energia(**{"intel-rapl:0": 1, "intel-rapl:0:0": 1, "intel-rapl:0:1": 1,
                         "intel-rapl:1": 1, "intel-rapl-mmio:0": 1})
        zonas = helper.read_rapl()["zones"]
        self.assertEqual(set(zonas), {"intel-rapl:0", "intel-rapl:0:0", "intel-rapl:0:1",
                                      "intel-rapl:1"})

    def test_and_the_page_gets_their_watts(self):
        proveedor = rapl.RaplPower(client=_InProcessClient())
        draft = Draft()
        self._energia(**{"intel-rapl:0": 10, "intel-rapl:0:0": 5, "intel-rapl:0:1": 1,
                         "intel-rapl:1": 20})
        with mock.patch.object(rapl.time, "monotonic", return_value=100.0):
            proveedor.collect(draft)
        self._energia(**{"intel-rapl:0": 12, "intel-rapl:0:0": 6, "intel-rapl:0:1": 1.25,
                         "intel-rapl:1": 23})
        with mock.patch.object(rapl.time, "monotonic", return_value=101.0):
            proveedor.collect(draft)
        potencia = draft.cpu_extra["power"]
        self.assertAlmostEqual(potencia.package_w, 2.0)
        self.assertAlmostEqual(potencia.core_w, 1.0)
        self.assertAlmostEqual(potencia.uncore_w, 0.25)


class TestTheHelperPacesItsCounters(unittest.TestCase):
    """Energy and busy counters at most every 100 ms, whatever the client
    asks: read at their own rate they are the Platypus side channel."""

    class Clock:
        def __init__(self):
            self.now = 10.0
            self.slept = []

        def monotonic(self):
            return self.now

        def sleep(self, seconds):
            self.slept.append(seconds)
            self.now += seconds

    def setUp(self):
        from silux.privileged import helper
        self.helper = helper
        self.clock = self.Clock()
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        zona = pathlib.Path(tmp.name) / "intel-rapl:0"
        zona.mkdir()
        (zona / "energy_uj").write_text("1\n")
        # No counters of this machine's are opened: the PMU families answer
        # «unsupported», after the wait.
        for parche in (mock.patch.object(helper, "POWERCAP", tmp.name),
                       mock.patch.object(helper, "_abrir_pmu", lambda familia: None),
                       mock.patch.dict(helper._PMU_FDS, clear=True),
                       mock.patch.dict(helper._LAST_READ, clear=True),
                       mock.patch.object(helper.time, "monotonic", self.clock.monotonic),
                       mock.patch.object(helper.time, "sleep", self.clock.sleep)):
            parche.start()
            self.addCleanup(parche.stop)

    def test_each_reading_waits_for_the_rest_of_100_ms(self):
        for action in ("rapl", "gpu_pmu", "imc"):
            with self.subTest(action=action):
                self.clock.slept.clear()
                self.helper.handle({"action": action})
                self.assertEqual(self.clock.slept, [])
                self.clock.now += 0.03
                self.helper.handle({"action": action})
                self.assertEqual(len(self.clock.slept), 1)
                self.assertAlmostEqual(self.clock.slept[0], 0.07)
                self.clock.now += 0.5
                self.helper.handle({"action": action})
                self.assertEqual(len(self.clock.slept), 1)

    def test_one_family_does_not_hold_up_another(self):
        self.helper.handle({"action": "rapl"})
        self.helper.handle({"action": "gpu_pmu"})
        self.helper.handle({"action": "imc"})
        self.assertEqual(self.clock.slept, [])
