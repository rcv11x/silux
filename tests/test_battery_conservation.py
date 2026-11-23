"""«Not charging» below full is not «held at the top».

A Lenovo LOQ on its charger at 76 %: the kernel said «Not charging» and the
page said «Retenida en el tope». Its conservation mode holds the charge low;
`ideapad_laptop` publishes it as `conservation_mode` (the kernel's generic
`charge_types` calls it Long_Life). The dump was taken before Silux read
that file, so the tests that need it write it where the driver puts it.
"""

import unittest

from silux import volcado
from silux.collector import Collector
from silux.i18n import _
from tests import pantalla, qt
from tests.test_equipos import EQUIPOS, shared_snapshot

LOQ = EQUIPOS / "i5-12450h"
CONSERVATION = "sys/bus/platform/drivers/ideapad_acpi/VPC2004:00/conservation_mode"
BATTERY = "sys/class/power_supply/BAT1"


def _collected(files: dict[str, str]):
    with volcado.mounted(LOQ) as root:
        for path, value in files.items():
            target = root / path
            if target.is_symlink():
                target = target.resolve()
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(value + "\n")
        collector = Collector()
        try:
            return collector.snapshot()
        finally:
            collector.close()


def _page(snapshot) -> tuple[str, bool]:
    """The page's text, and whether the limits card is shown."""
    from silux.ui.pages.battery import _SeccionBateria

    qt.app()
    with pantalla.Ventana(snapshot) as window:
        window.select_section("Batería")
        page = window.stack.currentWidget()
        section = page.findChildren(_SeccionBateria)[0]
        return (" ".join(pantalla.textos_de(page)),
                section.limites_card.isVisibleTo(page))


class TestTheStatus(unittest.TestCase):

    def test_below_full_without_a_mode_it_is_not_the_top(self):
        battery = shared_snapshot(LOQ).batteries[0]
        self.assertLess(battery.percent, 99)
        self.assertIsNone(battery.conservation_mode)
        self.assertEqual(battery.status, "bat.status.notcharging")

    def test_lenovos_conservation_mode(self):
        on = _collected({CONSERVATION: "1"}).batteries[0]
        self.assertEqual((on.conservation_mode, on.status),
                         (True, "bat.status.conservation"))
        off = _collected({CONSERVATION: "0"}).batteries[0]
        self.assertEqual((off.conservation_mode, off.status),
                         (False, "bat.status.notcharging"))

    def test_the_kernels_long_life_charge_type(self):
        battery = _collected({f"{BATTERY}/charge_types": "Standard [Long_Life] Bypass"}).batteries[0]
        self.assertEqual((battery.conservation_mode, battery.status),
                         (True, "bat.status.conservation"))

    def test_full_is_held_at_the_top(self):
        battery = _collected({f"{BATTERY}/capacity": "100"}).batteries[0]
        self.assertEqual(battery.status, "bat.status.held")


class TestOnThePage(unittest.TestCase):

    def test_without_the_mode(self):
        text, limits_shown = _page(shared_snapshot(LOQ))
        self.assertIn(_("bat.status.notcharging"), text)
        self.assertNotIn(_("bat.status.held"), text)
        self.assertFalse(limits_shown)

    def test_with_the_mode_on(self):
        text, limits_shown = _page(_collected({CONSERVATION: "1"}))
        self.assertIn(_("bat.status.conservation"), text)
        self.assertTrue(limits_shown)
        self.assertIn(f"{_('bat.limit.conservation')} {_('bat.conservation.on')}", text)
        self.assertNotIn(_("bat.status.held"), text)


if __name__ == "__main__":
    unittest.main()
