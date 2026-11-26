"""El voltaje del núcleo leído del propio procesador.

Aquí no se lee ningún MSR de verdad: hace falta root y el módulo «msr», y un
test que dependa de eso no corre en el CI. Lo que se prueba es la
interpretación de los bits, que es donde está el error posible, y el reparto
de avisos.
"""

import unittest
from unittest import mock

from silux.i18n import _
from silux.model import Need
from silux.privileged import helper
from silux.privileged.client import HelperError, HelperMissingModule, PrivilegedClient
from silux.providers import msr_voltage
from silux.providers.base import Draft
from tests import qt


def _draft(vendor="AMD", voltaje=None, family=0x19):
    """`family`: CPUID's, which a real draft always has (Zen 3 by default)."""
    draft = Draft()
    entrada = draft.type_entry("general") if hasattr(draft, "type_entry") else None
    if entrada is None:                       # la API real, según la versión
        draft.types["general"] = {"vendor": vendor}
        entrada = draft.types["general"]
    entrada["vendor"] = vendor
    entrada["disp_family"] = family
    if voltaje is not None:
        entrada["voltage_v"] = voltaje
    return draft


class TestInterpretarLosBits(unittest.TestCase):
    """Un VID mal desplazado da un voltaje creíble y falso, que es lo peor."""

    @staticmethod
    def _pstate(vid):
        # Bit 63 marca el P-state como válido; el VID va en 21:14.
        return (1 << 63) | (vid << 14) | 0x30

    def test_un_vid_de_zen_en_carga(self):
        """VID 56 son 1,2 V, que es lo típico de un Ryzen trabajando."""
        valores = {msr_voltage.AMD_PSTATE_STATUS: 0,
                   msr_voltage.AMD_PSTATE_DEF: self._pstate(56)}
        self.assertAlmostEqual(msr_voltage._amd_voltage(valores), 1.2, places=3)

    def test_sigue_al_pstate_que_este_activo(self):
        """El registro de estado dice cuál manda; leer siempre el 0 daría el
        voltaje de otro punto de la curva."""
        valores = {msr_voltage.AMD_PSTATE_STATUS: 2,
                   msr_voltage.AMD_PSTATE_DEF: self._pstate(56),
                   msr_voltage.AMD_PSTATE_DEF + 2: self._pstate(96)}
        self.assertAlmostEqual(msr_voltage._amd_voltage(valores), 0.95, places=3)

    def test_un_pstate_sin_definir_no_da_voltaje(self):
        valores = {msr_voltage.AMD_PSTATE_STATUS: 1,
                   msr_voltage.AMD_PSTATE_DEF + 1: 0}
        self.assertIsNone(msr_voltage._amd_voltage(valores))

    def test_intel_lo_trae_ya_medido(self):
        """1,2 V en coma fija de 16 bits son 9830 en los bits 47:32."""
        valores = {msr_voltage.INTEL_PERF_STATUS: 9830 << 32}
        self.assertAlmostEqual(msr_voltage._intel_voltage(valores), 1.2, places=2)

    def test_un_registro_vacio_no_es_cero_voltios(self):
        self.assertIsNone(msr_voltage._intel_voltage({msr_voltage.INTEL_PERF_STATUS: 0}))


class TestElProveedor(unittest.TestCase):
    def _con(self, valores, vendor="AMD", voltaje=None):
        cliente = mock.Mock()
        cliente.connected.return_value = True
        cliente.read_msr.return_value = valores
        draft = _draft(vendor, voltaje)
        msr_voltage.MsrVoltage(cliente).collect(draft)
        return draft, cliente

    def test_rellena_el_voltaje_de_cada_tipo(self):
        draft, _c = self._con({msr_voltage.AMD_PSTATE_STATUS: 0,
                               msr_voltage.AMD_PSTATE_DEF: (1 << 63) | (56 << 14)})
        self.assertEqual(draft.types["general"]["voltage_v"], 1.2)

    def test_no_pisa_lo_que_midio_un_sensor_de_verdad(self):
        """El sensor de la placa mide lo que llega a los pines; esto solo dice
        lo que el procesador pide. Si están los dos, manda el medido."""
        draft, cliente = self._con({}, voltaje=1.35)
        self.assertEqual(draft.types["general"]["voltage_v"], 1.35)
        cliente.read_msr.assert_not_called()

    def test_una_cifra_imposible_se_descarta(self):
        """Un registro mal interpretado da un número creíble para el programa
        y absurdo para un procesador."""
        draft, _c = self._con({msr_voltage.AMD_PSTATE_STATUS: 0,
                               msr_voltage.AMD_PSTATE_DEF: (1 << 63) | (250 << 14)})
        self.assertIsNone(draft.types["general"].get("voltage_v"))

    def test_an_amd_before_zen_is_not_read_with_zens_layout(self):
        # An FX-8150 (family 15h) gave 1.550 V: its VID is in other bits.
        cliente = mock.Mock()
        cliente.connected.return_value = True
        draft = _draft(family=0x15)
        msr_voltage.MsrVoltage(cliente).collect(draft)
        cliente.read_msr.assert_not_called()
        self.assertIsNone(draft.types["general"].get("voltage_v"))
        self.assertEqual([(n.need, n.key) for n in draft.notes if n.path == "cpu.voltage_v"],
                         [(Need.DATABASE, "prov.msr.amdformat")])

    def test_nor_a_zen_5(self):
        """Family 1Ah changed the P-state registers again: left out on
        purpose, and said."""
        cliente = mock.Mock()
        cliente.connected.return_value = True
        draft = _draft(family=0x1A)
        msr_voltage.MsrVoltage(cliente).collect(draft)
        cliente.read_msr.assert_not_called()
        self.assertEqual([(n.need, n.key) for n in draft.notes if n.path == "cpu.voltage_v"],
                         [(Need.DATABASE, "prov.msr.amdformat")])

    def test_without_the_module_its_notice_offers_to_load_it(self):
        cliente = mock.Mock()
        cliente.connected.return_value = True
        cliente.read_msr.side_effect = HelperMissingModule("no_module")
        draft = _draft()
        msr_voltage.MsrVoltage(cliente).collect(draft)
        self.assertEqual([n for n in draft.notes if n.path == "cpu.voltage_v"], [])
        self.assertEqual([(h.module, h.provides, h.command) for h in draft.driver_hints],
                         [("msr", _("prov.hint.msr.voltage"), "sudo modprobe msr")])

    def test_the_helper_failing_otherwise_blames_no_module(self):
        cliente = mock.Mock()
        cliente.connected.return_value = True
        cliente.read_msr.side_effect = HelperError("el ayudante no respondió a tiempo")
        draft = _draft()
        msr_voltage.MsrVoltage(cliente).collect(draft)
        avisos = [n for n in draft.notes if n.path == "cpu.voltage_v"]
        self.assertEqual([(n.need, n.key) for n in avisos], [(Need.ERROR, "prov.msr.helperfail")])
        self.assertEqual(draft.driver_hints, [])

    def test_a_intel_se_le_pregunta_su_registro_y_no_los_de_amd(self):
        _draft_, cliente = self._con({}, vendor="Intel")
        cliente.read_msr.assert_called_once_with(0, [msr_voltage.INTEL_PERF_STATUS])

    def test_an_unexpected_failure_is_an_error_not_silence(self):
        # It returned without a word: the voltage was missing with no reason.
        from silux.collector import Collector
        cliente = mock.Mock()
        cliente.connected.return_value = True
        cliente.read_msr.side_effect = ValueError("bad register list")
        recolector = Collector(providers=[])
        draft = recolector._collect([msr_voltage.MsrVoltage(cliente)], into=_draft())
        avisos = [n for n in draft.notes if n.path == "cpu.voltage_v"]
        self.assertEqual([n.need for n in avisos], [Need.ERROR])
        self.assertEqual([f.where for f in recolector.failures.recent()], ["msr-voltage"])


class TestTheClientSaysWhichFailure(unittest.TestCase):
    """The helper's own answer without /dev/cpu/N/msr, read by the client."""

    def _client_reading(self, reply):
        cliente = PrivilegedClient.__new__(PrivilegedClient)
        cliente._last_error = None
        with mock.patch.object(PrivilegedClient, "request", return_value=reply):
            return cliente.read_msr(0, [msr_voltage.INTEL_PERF_STATUS])

    def test_no_device_is_a_missing_module(self):
        with mock.patch.object(helper.os, "open", side_effect=FileNotFoundError):
            reply = helper.read_msr(0, [msr_voltage.INTEL_PERF_STATUS])
        with self.assertRaises(HelperMissingModule):
            self._client_reading(reply)

    def test_any_other_failure_is_not(self):
        with mock.patch.object(helper.os, "open", side_effect=PermissionError):
            reply = helper.read_msr(0, [msr_voltage.INTEL_PERF_STATUS])
        with self.assertRaises(HelperError) as caught:
            self._client_reading(reply)
        self.assertNotIsInstance(caught.exception, HelperMissingModule)


class TestElAviso(unittest.TestCase):
    def test_sin_ayudante_pide_permisos_y_no_culpa_al_hardware(self):
        """Va con ROOT porque lleva botón: con DRIVER se leía como «tu equipo
        no lo tiene» cuando basta con dar permisos."""
        ruta, need, *_ = msr_voltage.MsrVoltage(None).unavailable_reason()
        self.assertEqual((ruta, need), ("cpu.voltage_v", Need.ROOT))

    def test_fuera_de_x86_no_promete_nada(self):
        with mock.patch("platform.machine",
                               return_value="aarch64"):
            _ruta, need, *_ = msr_voltage.MsrVoltage(None).unavailable_reason()
        self.assertEqual(need, Need.PLATFORM)

    def test_hwmon_ya_no_avisa_por_su_cuenta(self):
        """Salían dos avisos de lo mismo, y el de hwmon decía que no había
        nada que hacer cuando sí lo hay."""
        import inspect
        from silux.providers import hwmon
        fuente = inspect.getsource(hwmon.HwmonSensors._pick_voltage)
        self.assertNotIn("draft.note", fuente)


if __name__ == "__main__":
    unittest.main()


class TestQueLlegueALaPantalla(unittest.TestCase):
    """Que el dato tenga dónde pintarse, que es lo que faltaba.

    El proveedor se escribió, se probó y se dio por hecho, y la suite entera
    pasaba con el voltaje llegando al modelo y muriendo ahí: la ficha de
    procesador no tenía ninguna fila donde enseñarlo. Mil trescientos tests en
    verde y el dato invisible. Probar el proveedor no basta si nadie comprueba
    el camino hasta la ventana.
    """

    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app = qt.app()

    def _pagina(self, voltaje):
        import dataclasses
        from silux.collector import Collector
        from silux.settings import Preferences
        from silux.ui import theme
        from silux.ui.pages.cpu import CpuPage

        theme.set_density("normal", "normal")
        foto = Collector().sample()
        if not foto.cpu.types:
            self.skipTest("esta máquina no identifica ningún procesador")
        tipos = tuple(dataclasses.replace(t, voltage_v=voltaje)
                      for t in foto.cpu.types)
        pagina = CpuPage(theme.palette_for(self.app, "dark"),
                         Preferences(font_scale="normal").normalized())
        # Sin ayudante: lo que aquí se mira es el camino del dato hasta su
        # celda. Con ayudante y sin permisos, donde falta va un candado, y eso
        # lo prueba `test_candado` con los equipos volcados.
        from silux.model import PrivilegedState
        pagina.apply(dataclasses.replace(
            foto, cpu=dataclasses.replace(foto.cpu, types=tipos),
            privileged=PrivilegedState(supported=False)))
        # Se guarda en la instancia: sin una referencia viva, Python recolecta
        # la página al salir de aquí y Qt destruye los widgets por debajo. La
        # celda que se devolvía apuntaba entonces a un objeto ya borrado.
        self._viva = pagina
        return pagina

    @staticmethod
    def _celda(pagina, clave):
        from silux.i18n import _
        from silux.ui.widgets import InfoGrid
        for grid in pagina.findChildren(InfoGrid):
            if _(clave) in grid._values:
                return grid._values[_(clave)]
        return None

    def test_la_ficha_tiene_fila_de_voltaje(self):
        self.assertIsNotNone(self._celda(self._pagina(None), "cpu.field.voltage"),
                             "el voltaje no tiene dónde pintarse en la ficha")

    def test_un_voltaje_medido_se_ve(self):
        """1,1 V es lo que dio el 5800X3D del autor por MSR."""
        celda = self._celda(self._pagina(1.1), "cpu.field.voltage")
        self.assertIn("1.100", celda.text())

    def test_sin_medida_sale_su_guion(self):
        from silux import render
        celda = self._celda(self._pagina(None), "cpu.field.voltage")
        self.assertEqual(celda.text(), render.DASH)


class TestSeAnunciaEnLaBarra(unittest.TestCase):
    def test_al_leer_algo_se_apunta_en_las_fuentes(self):
        """La barra de estado lista las fuentes que dieron algo, y sin esto el
        proveedor leía el voltaje sin aparecer por ningún lado."""
        cliente = mock.Mock()
        cliente.connected.return_value = True
        cliente.read_msr.return_value = {
            msr_voltage.AMD_PSTATE_STATUS: 0,
            msr_voltage.AMD_PSTATE_DEF: (1 << 63) | (72 << 14)}
        draft = _draft()
        msr_voltage.MsrVoltage(cliente).collect(draft)
        self.assertIn("msr", draft.capabilities)

    def test_si_no_lee_nada_no_se_anuncia(self):
        cliente = mock.Mock()
        cliente.connected.return_value = True
        cliente.read_msr.return_value = {}
        draft = _draft()
        msr_voltage.MsrVoltage(cliente).collect(draft)
        self.assertNotIn("msr", draft.capabilities)


class TestBeforeSandyBridge(unittest.TestCase):
    """A Core 2 has no voltage in its MSR_PERF_STATUS: asking for permissions
    to read it promised what no permission brings."""

    def test_the_dumps_say_the_processor_does_not_publish_it(self):
        from silux.i18n import _
        from tests.test_equipos import EQUIPOS, foto

        for machine, need in (("core2-p8400", Need.HARDWARE), ("celeron-560", Need.HARDWARE),
                              ("i7-4710hq", Need.ROOT), ("i5-3330", Need.ROOT)):
            snapshot = foto(EQUIPOS / machine)[0]
            note = next(n for n in snapshot.notes if n.path == "cpu.voltage_v")
            with self.subTest(machine):
                self.assertEqual(note.need, need)
                if need is Need.HARDWARE:
                    self.assertEqual(note.message, _("prov.msr.oldintel"))

    def test_with_permissions_the_register_is_not_read(self):
        from silux import volcado
        from tests.test_equipos import EQUIPOS

        cliente = mock.Mock()
        cliente.connected.return_value = True
        draft = _draft("Intel")
        with volcado.mounted(EQUIPOS / "core2-p8400"):
            msr_voltage.MsrVoltage(cliente).collect(draft)
        cliente.read_msr.assert_not_called()
        self.assertEqual([n.need for n in draft.notes if n.path == "cpu.voltage_v"],
                         [Need.HARDWARE])

    def test_garbage_from_a_newer_one_is_said(self):
        from silux import volcado
        from tests.test_equipos import EQUIPOS

        cliente = mock.Mock()
        cliente.connected.return_value = True
        cliente.read_msr.return_value = {msr_voltage.INTEL_PERF_STATUS: 0xFFFF << 32}
        draft = _draft("Intel")
        with volcado.mounted(EQUIPOS / "i7-4710hq"):
            msr_voltage.MsrVoltage(cliente).collect(draft)
        self.assertIsNone(draft.types["general"].get("voltage_v"))
        self.assertEqual([n.key for n in draft.notes if n.path == "cpu.voltage_v"],
                         ["prov.msr.novalue"])

    def test_on_the_cpu_page_hidden_and_said_at_the_foot(self):
        from silux.i18n import _
        from tests import pantalla
        from tests.test_interface_language import visible_texts
        from tests.test_equipos import EQUIPOS, foto

        qt.app()
        for machine, shown in (("core2-p8400", False), ("i7-4710hq", True)):
            with self.subTest(machine), pantalla.Ventana(foto(EQUIPOS / machine)[0]) as window:
                window.select_section("CPU")
                text = visible_texts(window.stack.currentWidget())
                self.assertEqual(_("cpu.field.voltage") in text, shown)
                self.assertEqual(_("prov.msr.oldintel") in " ".join(text), not shown)
