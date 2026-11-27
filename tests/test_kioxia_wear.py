"""The office's KIOXIA-EXCERIA S, as `smartctl -A` reads it: 9=4181,
12=1503, 167=0, 168=0, 169=0, 173 at 141 normalized and 0 raw, 192=134,
194 packed, 241=915316. 192, the shutdowns it wasn't let finish, by its
name; and it publishes no wear the standard way (173 at 141 % says
nothing): the card says so instead of «Vida restante —».
"""

import dataclasses
import unittest

from silux import render
from silux.i18n import _
from silux.model import DiskHealth
from tests import geometry, pantalla, qt
from tests.test_equipos import EQUIPOS, shared_snapshot
from tests.test_smart_packed_temperature import KIOXIA_194

KIOXIA = DiskHealth(
    power_on_hours=4181, power_cycles=1503,
    attributes=((9, 100, 4181), (12, 100, 1503), (167, 100, 0), (168, 100, 0), (169, 100, 0),
                (173, 141, 0), (192, 100, 134), (194, 72, KIOXIA_194), (241, 100, 915_316)))


class TestTheKioxiaCard(unittest.TestCase):
    def test_its_card_and_its_diagnosis(self):
        app = qt.app()
        snapshot = shared_snapshot(EQUIPOS / "i5-10400")
        snapshot = dataclasses.replace(snapshot, disks=tuple(
            dataclasses.replace(d, health=KIOXIA) for d in snapshot.disks))
        rows = dict(render.smart_rows(KIOXIA))
        self.assertEqual(rows[f"194 · {_('smart.attr.194')}"], "28 °C, mín 14, máx 41")
        self.assertIn(f"192 · {_('smart.attr.192')}", rows)
        with pantalla.Ventana(snapshot) as window:
            window.select_section("Almacenamiento")
            geometry.settle(app)
            page = window.storage_page
            disk = snapshot.disks[0].name
            grid = page._grids[disk]
            self.assertFalse(grid.value_label(_("storage.field.life")).isVisibleTo(page))
            self.assertIn(_("storage.na.life"), page._pies[disk].text())


if __name__ == "__main__":
    unittest.main()
