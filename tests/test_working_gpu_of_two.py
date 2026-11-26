"""Two dedicated cards awake: the one this desktop draws on is the one that
works.

A desktop with a Radeon driving the monitor and a GeForce kept for a
virtual machine summarized the GeForce on Home: the first dedicated card
awake, in `cardN` order, won. The one with the monitor connected, or the
firmware's boot card, is the one in use.
"""

import dataclasses
import unittest

from tests import pantalla, qt
from tests.test_equipos import EQUIPOS, shared_snapshot


class TestTwoDedicatedCards(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.snapshot = shared_snapshot(EQUIPOS / "i7-6700k")

    def test_the_dump_has_two_awake_and_the_monitor_on_the_second(self):
        gpus = self.snapshot.gpus
        self.assertEqual([g.integrated for g in gpus], [False, False])
        self.assertEqual([g.resting for g in gpus], [False, False])
        self.assertEqual([g.vendor for g in gpus], ["NVIDIA", "AMD"])
        self.assertEqual([any(d.connected for d in g.displays) for g in gpus], [False, True])

    def test_the_one_with_the_monitor_works(self):
        self.assertEqual(self.snapshot.working_gpu, 1)

    def test_the_monitor_decides_without_a_boot_card(self):
        gpus = tuple(dataclasses.replace(g, primary=False) for g in self.snapshot.gpus)
        self.assertEqual(dataclasses.replace(self.snapshot, gpus=gpus).working_gpu, 1)

    def test_the_boot_card_without_a_monitor_works_too(self):
        """A monitor asleep or unplugged: the firmware's boot card decides."""
        gpus = tuple(dataclasses.replace(g, displays=tuple(
            dataclasses.replace(d, connected=False) for d in g.displays))
            for g in self.snapshot.gpus)
        self.assertEqual([g.primary for g in gpus], [False, True])
        self.assertEqual(dataclasses.replace(self.snapshot, gpus=gpus).working_gpu, 1)

    def test_home_shows_it(self):
        qt.app()
        radeon = self.snapshot.gpus[1].name
        geforce = self.snapshot.gpus[0].name
        with pantalla.Ventana(self.snapshot) as window:
            texts = pantalla.textos_de(window.home_page)
        joined = "\n".join(texts)
        self.assertIn(radeon, texts)
        self.assertIn(geforce, joined.split(radeon, 1)[1])
