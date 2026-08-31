"""El voltaje del núcleo leído del propio procesador.

Aquí no se lee ningún MSR de verdad: hace falta root y el módulo «msr», y un
test que dependa de eso no corre en el CI. Lo que se prueba es la
interpretación de los bits, que es donde está el error posible, y el reparto
de avisos.
"""

import unittest
from unittest import mock

from silux.model import Need
from silux.providers import msr_voltage
from silux.providers.base import Draft
from silux.privileged.client import HelperError


def _draft(vendor="AMD", voltaje=None):
    draft = Draft()
    entrada = draft.type_entry("general") if hasattr(draft, "type_entry") else None
    if entrada is None:                       # la API real, según la versión
        draft.types["general"] = {"vendor": vendor}
        entrada = draft.types["general"]
    entrada["vendor"] = vendor
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
        self.assertAlmostEqual(msr_voltage._voltaje_amd(valores), 1.2, places=3)

    def test_sigue_al_pstate_que_este_activo(self):
        """El registro de estado dice cuál manda; leer siempre el 0 daría el
        voltaje de otro punto de la curva."""
        valores = {msr_voltage.AMD_PSTATE_STATUS: 2,
                   msr_voltage.AMD_PSTATE_DEF: self._pstate(56),
                   msr_voltage.AMD_PSTATE_DEF + 2: self._pstate(96)}
        self.assertAlmostEqual(msr_voltage._voltaje_amd(valores), 0.95, places=3)

    def test_un_pstate_sin_definir_no_da_voltaje(self):
        valores = {msr_voltage.AMD_PSTATE_STATUS: 1,
                   msr_voltage.AMD_PSTATE_DEF + 1: 0}
        self.assertIsNone(msr_voltage._voltaje_amd(valores))

    def test_intel_lo_trae_ya_medido(self):
        """1,2 V en coma fija de 16 bits son 9830 en los bits 47:32."""
        valores = {msr_voltage.INTEL_PERF_STATUS: 9830 << 32}
        self.assertAlmostEqual(msr_voltage._voltaje_intel(valores), 1.2, places=2)

    def test_un_registro_vacio_no_es_cero_voltios(self):
        self.assertIsNone(msr_voltage._voltaje_intel({msr_voltage.INTEL_PERF_STATUS: 0}))


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

    def test_si_falta_el_modulo_se_dice_con_su_orden(self):
        cliente = mock.Mock()
        cliente.connected.return_value = True
        cliente.read_msr.side_effect = HelperError("no_module")
        draft = _draft()
        msr_voltage.MsrVoltage(cliente).collect(draft)
        avisos = [n for n in draft.notes if n.path == "cpu.voltage_v"]
        self.assertEqual(len(avisos), 1)
        self.assertIn("modprobe", avisos[0].hint)

    def test_a_intel_se_le_pregunta_su_registro_y_no_los_de_amd(self):
        _draft_, cliente = self._con({}, vendor="Intel")
        cliente.read_msr.assert_called_once_with(0, [msr_voltage.INTEL_PERF_STATUS])


class TestElAviso(unittest.TestCase):
    def test_sin_ayudante_pide_permisos_y_no_culpa_al_hardware(self):
        """Va con ROOT porque lleva botón: con DRIVER se leía como «tu equipo
        no lo tiene» cuando basta con dar permisos."""
        ruta, need, *_ = msr_voltage.MsrVoltage(None).unavailable_reason()
        self.assertEqual((ruta, need), ("cpu.voltage_v", Need.ROOT))

    def test_fuera_de_x86_no_promete_nada(self):
        with mock.patch.object(msr_voltage.platform, "machine",
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
