"""A card handed to a virtual machine is not a sleeping card.

A desktop kept its integrated GPU on vfio-pci for a virtual machine, in
D3hot. The dump took it for a laptop's card asleep and, not to wake it, left
out what OpenGL, Vulkan, OpenCL and VA-API answer for the other two. Bound
to vfio-pci it has no node here, and nothing enumerating the others wakes
it. The manifest says it is a virtual machine's.
"""

import unittest

from silux import volcado
from tests.test_equipos import EQUIPOS

SLOT = "0000:00:02.0"


class TestAPassedThroughCard(unittest.TestCase):
    def test_the_dump_has_it_on_vfio_in_d3(self):
        with volcado.mounted(EQUIPOS / "i7-6700k"):
            self.assertEqual(volcado.power_state(f"{volcado.SYS_PCI}/{SLOT}")["power_state"],
                             "D3hot")
            self.assertTrue(volcado.passed_through(f"{volcado.SYS_PCI}/{SLOT}"))

    def test_is_not_asleep_and_is_named(self):
        with volcado.mounted(EQUIPOS / "i7-6700k"):
            cards = volcado._SleepingCards()
        self.assertEqual(cards.asleep, [])
        self.assertFalse(cards)
        self.assertEqual(cards.passed_through, [SLOT])

    def test_a_sleeping_laptop_card_still_is(self):
        with volcado.mounted(EQUIPOS / "i7-4710hq"):
            cards = volcado._SleepingCards()
        self.assertTrue(cards.asleep)
        self.assertEqual(cards.passed_through, [])
