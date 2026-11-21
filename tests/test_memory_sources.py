"""What the memory page says comes from the firmware's table, it says so.

Without the SPD (an SMBus the firmware keeps for itself), a module's rated
speed and voltage are only what the BIOS writes in SMBIOS, and many leave
the voltage at its stock value with an XMP profile on: 1.20 V for a kit
running its 1.35 V profile. And the SPD's reason appeared twice, in the
sentence under the modules and in a box below.
"""

import unittest

from silux.i18n import _
from tests import pantalla, qt
from tests.test_equipos import EQUIPOS, foto
from tests.test_nada_en_bruto import _con_permisos
from tests.test_smbios import _end, _memory_array, _memory_device


def _page_text(snapshot) -> str:
    qt.app()
    with pantalla.Ventana(snapshot) as ventana:
        ventana.select_section("Memoria")
        return "\n".join(pantalla.textos_de(ventana.stack.currentWidget()))


def _without_spd(configured_mts: int):
    # This machine's dump: its SMBus is reserved by the firmware, so no SPD.
    f = foto(EQUIPOS / "5800x3d")[0]
    assert not f.spd
    return _con_permisos(f, _memory_array() + _memory_device(configured_mts=configured_mts)
                         + _memory_device(configured_mts=configured_mts) + _end())


class TestFromTheFirmwareTable(unittest.TestCase):

    def test_rated_speed_and_voltage_say_where_they_come_from(self):
        texto = _page_text(_without_spd(3200))
        fuente = _("memory.source.bios")
        self.assertIn(f"3200 MT/s · {fuente}", texto)
        self.assertIn(f"1.20 V · {fuente}", texto)

    def test_above_jedec_the_voltage_may_be_another(self):
        f = _without_spd(3600)
        self.assertTrue(all(m.above_jedec for m in f.modules if m.populated))
        aviso = _("memory.na.voltage.profile").format(tipo="DDR4", jedec=3200)
        self.assertIn(aviso, _page_text(f))

    def test_at_the_jedec_top_nothing_is_guessed(self):
        # DDR4-3200 at 1.2 V is a JEDEC speed: no profile can be inferred.
        f = _without_spd(3200)
        self.assertFalse(any(m.above_jedec for m in f.modules if m.populated))
        self.assertNotIn(_("memory.na.voltage.profile").format(tipo="DDR4", jedec=3200),
                         _page_text(f))

    def test_with_the_spd_the_rated_speed_is_the_modules_own(self):
        # A dump whose SPD reads: the rated speed comes from the chip.
        f = foto(EQUIPOS / "i7-10700f")[0]
        self.assertTrue(f.spd)
        texto = _page_text(f)
        self.assertNotIn(_("memory.source.bios"), texto)


class TestTheSpdReasonOnce(unittest.TestCase):

    def test_said_once(self):
        f = _without_spd(3200)
        motivo = next(n for n in f.notes if n.path == "spd").message
        texto = _page_text(f)
        self.assertEqual(texto.lower().count(motivo[:40].lower()), 1, texto)


if __name__ == "__main__":
    unittest.main()


class TestTheJedecTops(unittest.TestCase):

    def test_each_is_the_fastest_named_speed_of_its_generation(self):
        from silux import spd
        from silux.model import JEDEC_TOP_MTS
        # The named speeds of each generation, as spd.py lists them.
        generaciones = {"DDR3": (1333, 2133), "DDR4": (2400, 3200), "DDR5": (3600, 8800)}
        for tipo, (desde, hasta) in generaciones.items():
            with self.subTest(tipo=tipo):
                propias = [v for v in spd.VELOCIDADES_JEDEC if desde <= v <= hasta]
                self.assertIn(JEDEC_TOP_MTS[tipo], spd.VELOCIDADES_JEDEC)
                self.assertEqual(JEDEC_TOP_MTS[tipo], max(propias))
