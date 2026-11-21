"""A battery right after the charger goes in or out, and its Wh.

On the author's T14 the embedded controller takes a few seconds to update
`power_now` after the charger is plugged or unplugged: charging or
discharging at 0 W. Potencia and Autonomía say «Calculando…» meanwhile, not
a dash (it could not be read) nor «0» (nothing flows). With the battery full
at 0 W, 0 W is the answer.

And its energy reads the same everywhere: the badge said «50 Wh» above a
«Diseño 50.5 Wh».
"""

import pathlib
import re
import unittest

from silux import render, volcado
from silux.collector import Collector
from silux.i18n import _
from tests import pantalla, qt

EQUIPOS = pathlib.Path(__file__).resolve().parent / "fixtures" / "equipos"
BAT = "sys/class/power_supply/BAT0"


def photo(status, power_uw):
    with volcado.montado(EQUIPOS / "i5-1135g7") as raiz:
        (raiz / BAT / "status").write_text(f"{status}\n")
        (raiz / BAT / "power_now").write_text(f"{power_uw}\n")
        collector = Collector()
        try:
            return collector.snapshot()
        finally:
            collector.close()


def tiles(snapshot):
    from silux.ui.widgets import StatTile
    qt.app()
    with pantalla.Ventana(snapshot) as ventana:
        ventana.select_section("Batería")
        pagina = ventana.stack.currentWidget()
        fichas = {t.caption.text(): t.figure_text() for t in pagina.findChildren(StatTile)}
        return fichas, pantalla.textos_de(pagina)


class TestRightAfterTheCharger(unittest.TestCase):

    def test_discharging_at_zero_is_still_coming(self):
        fichas, _textos = tiles(photo("Discharging", 0))
        self.assertEqual(fichas[_("bat.power")], _("bat.calculating"))
        self.assertEqual(fichas[_("bat.left")], _("bat.calculating"))

    def test_charging_at_zero_too(self):
        fichas, _textos = tiles(photo("Charging", 0))
        self.assertEqual(fichas[_("bat.power")], _("bat.calculating"))
        self.assertEqual(fichas[_("bat.tofull")], _("bat.calculating"))

    def test_once_it_comes_it_is_the_figure(self):
        fichas, _textos = tiles(photo("Discharging", 7620000))
        self.assertEqual(fichas[_("bat.power")], "7.6 W")
        self.assertNotEqual(fichas[_("bat.left")], _("bat.calculating"))

    def test_full_at_zero_is_zero(self):
        fichas, _textos = tiles(photo("Full", 0))
        self.assertEqual(fichas[_("bat.power")], "0.0 W")

    def test_the_report_says_it_too(self):
        from silux.report import build
        informe = build(photo("Discharging", 0))
        self.assertIn(_("bat.calculating").lower(), informe)


class TestTheSameWattHoursEverywhere(unittest.TestCase):

    def test_every_wh_on_the_page_has_one_decimal(self):
        foto = photo("Discharging", 7620000)
        _fichas, textos = tiles(foto)
        diseno = render.watt_hours(foto.batteries[0].design_wh)
        self.assertEqual(diseno, "50.5 Wh")
        cifras = [m for t in textos for m in re.findall(r"(\d+(?:\.\d+)?) Wh", t)]
        self.assertTrue(cifras)
        self.assertFalse([c for c in cifras if "." not in c], cifras)


if __name__ == "__main__":
    unittest.main()
