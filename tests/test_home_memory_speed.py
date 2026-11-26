"""Home says the speed the memory runs at, as Memory does.

A desktop with DDR5 on an EXPO profile read «DDR5-4800» on Home and «DDR5 ·
6000 MT/s» on Memory: Home took the speed the firmware lists for the
module, not the one the BIOS set. The modules here are the ones its report
showed with permissions; their SPD chips are the dump's.
"""

import dataclasses
import unittest

from silux.model import MemoryModule
from tests import pantalla, qt
from tests.test_equipos import EQUIPOS, shared_snapshot

GIB = 1024 ** 3
DIMM = 0x09


def _with_permissions():
    snapshot = shared_snapshot(EQUIPOS / "ryzen5-9600x")
    modules = tuple(
        MemoryModule(locator=f"DIMM {n}", bank=f"P0 CHANNEL {channel}", populated=True,
                     size_bytes=32 * GIB, type="DDR5", form_factor=DIMM,
                     speed_mts=4800, configured_mts=6000, manufacturer="Kingston",
                     part_number="KF560C30-32", spd=spd)
        for n, (channel, spd) in enumerate(zip("AB", snapshot.spd), start=1))
    return dataclasses.replace(snapshot, modules=modules)


class TestHome(unittest.TestCase):
    def test_says_the_speed_it_runs_at(self):
        qt.app()
        snapshot = _with_permissions()
        self.assertEqual(len(snapshot.modules), 2)
        with pantalla.Ventana(snapshot) as window:
            texts = "\n".join(pantalla.textos_de(window.home_page))
        self.assertIn("DDR5-6000", texts)
        self.assertNotIn("DDR5-4800", texts)
