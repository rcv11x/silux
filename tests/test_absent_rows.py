"""What a machine doesn't have hides and is named at the foot, not dashed.

Rule 5, on every dump: the clocks a processor doesn't publish, an energy
preference its frequency driver doesn't offer, what a virtual interface has
no card for, a disk that doesn't say its maker and a flash drive's wear.
"""

import unittest

from silux import render
from silux.i18n import _
from tests import pantalla, qt
from tests.test_equipos import foto, volcados

CLOCK_ROWS = ("cpu.clock.bus", "cpu.clock.multiplier", "cpu.clock.maxsilicon", "cpu.clock.epp")
INTERFACE_ROWS = ("net.field.mac", "gpu.field.driver", "storage.col.model", "net.field.slot")


def _dashed(grid, keys) -> list[str]:
    """The rows of `keys` not hidden and holding a dash. Not `isVisible`: a
    card folded away still shows its dash once unfolded."""
    return [key for key in keys
            if _(key) in grid._values
            and not grid._values[_(key)].isHidden()
            and grid._values[_(key)].full_text() == render.DASH]


class TestNoDashForWhatIsNotThere(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        qt.app()
        cls.snapshots = {d.name: foto(d)[0] for d in volcados()}

    def _page(self, window, section):
        window.select_section(section)
        return window.stack.currentWidget()

    def test_clocks(self):
        from silux.ui.pages.cpu import TypeSection

        for name, snapshot in self.snapshots.items():
            with self.subTest(name), pantalla.Ventana(snapshot) as window:
                page = self._page(window, "CPU")
                for section in page.findChildren(TypeSection):
                    if section.clocks_card.isHidden():
                        continue                # a hypervisor's: its notice says why
                    self.assertEqual(_dashed(section.clocks, CLOCK_ROWS), [])
                    clocks = snapshot.cpu.types[0].clocks
                    if render.without_energy_preference(clocks):
                        self.assertIn(_("cpu.clocks.noepp").format(driver=clocks.driver),
                                      section.clocks_foot.text())

    def test_interfaces(self):
        for name, snapshot in self.snapshots.items():
            with self.subTest(name), pantalla.Ventana(snapshot) as window:
                page = self._page(window, "Red")
                for interface in snapshot.network:
                    grid = page._grids.get(interface.name)
                    if grid is None:
                        continue
                    self.assertEqual(_dashed(grid, INTERFACE_ROWS), [], interface.name)
                    foot = page._feet[interface.name]
                    self.assertEqual(foot.isVisibleTo(page),
                                     bool(render.interface_missing(interface)), interface.name)

    def test_disks(self):
        for name, snapshot in self.snapshots.items():
            with self.subTest(name), pantalla.Ventana(snapshot) as window:
                page = self._page(window, "Almacenamiento")
                for disk in snapshot.disks:
                    grid = page._grids.get(disk.name)
                    if grid is None:
                        continue
                    self.assertEqual(
                        _dashed(grid, ("gpu.field.vendor", "storage.field.life")), [], disk.name)


if __name__ == "__main__":
    unittest.main()
