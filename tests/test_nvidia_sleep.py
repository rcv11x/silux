"""A laptop's NVIDIA is not kept awake by Silux.

The driver does not switch a card off while any process holds its node
open, and an open NVML session does (docs/nvml.md, «Las portátiles
dormidas»). On a card the driver can switch off, Silux reads it, closes NVML
when nothing else uses it and leaves it alone long enough to fall asleep.
Asleep, NVML is not even loaded. A desktop card goes on as always.
"""

import dataclasses
import unittest
from unittest import mock

from silux import render
from silux.i18n import _
from silux.providers import nvidia
from silux.providers.base import Draft
from tests import fake_nvml, pantalla, qt
from tests.arbol import arbol
from tests.test_equipos import EQUIPOS, shared_snapshot

try:
    from PySide6.QtWidgets import QApplication
except ImportError:                                    # pragma: no cover
    QApplication = None

FINE = "Enabled (fine-grained)"


def fresh_draft() -> Draft:
    """What DRM listed of the card this sample, before NVML."""
    draft = Draft()
    draft.gpu(0).update(pci_slot=fake_nvml.SLOT, vendor="NVIDIA", driver="nvidia",
                        name="AD107M [GeForce RTX 4050 Max-Q / Mobile]", drm_node="card1",
                        integrated=False)
    return draft


class Laptop:
    """One provider sampling one card, with the clock in the test's hands."""

    def __init__(self, card, d3=FINE):
        self.fake = fake_nvml.FakeNvml(card)
        self.provider = nvidia.NvidiaGpus()
        self.now = 1000.0
        self.provider._clock = lambda: self.now
        self.d3 = d3

    def sample(self, runtime_status="active", after_s=1.0) -> Draft:
        self.now += after_s
        draft = fresh_draft()
        with arbol(fake_nvml.bus(runtime_status, self.d3)), fake_nvml.loaded(self.fake):
            if self.provider.available():
                self.provider.collect(draft)
        return draft


def idle_laptop_card():
    return dataclasses.replace(fake_nvml.rtx_4050_laptop(), power_mw=12800)


class TestAsleep(unittest.TestCase):

    def test_nvml_is_not_even_loaded(self):
        laptop = Laptop(idle_laptop_card())
        draft = laptop.sample("suspended")
        self.assertEqual(laptop.fake.inits, 0)
        self.assertTrue(draft.gpus[0]["suspended"])
        self.assertEqual([n.key for n in draft.notes if n.path == "gpus.0"],
                         ["prov.drm.asleep"])

    def test_nor_while_it_sleeps(self):
        laptop = Laptop(idle_laptop_card())
        for _sample in range(5):
            laptop.sample("suspended")
        self.assertEqual(laptop.fake.inits, 0)


class TestAwakeWithNothingOnIt(unittest.TestCase):

    def test_read_once_and_let_go(self):
        laptop = Laptop(idle_laptop_card())
        first = laptop.sample()
        self.assertEqual(first.gpus[0]["temp_c"], 44.0)
        self.assertEqual((laptop.fake.inits, laptop.fake.shutdowns), (1, 1))

    def test_then_left_alone_while_it_falls_asleep(self):
        laptop = Laptop(idle_laptop_card())
        laptop.sample()
        draft = laptop.sample()
        self.assertEqual(laptop.fake.inits, 1)
        gpu = draft.gpus[0]
        self.assertTrue(gpu["left_to_sleep"])
        self.assertIsNone(gpu.get("temp_c"))
        self.assertEqual([n.key for n in draft.notes if n.path == "gpus.0"],
                         ["nvml.lefttosleep"])

    def test_and_asleep_once_the_driver_switches_it_off(self):
        laptop = Laptop(idle_laptop_card())
        laptop.sample()
        draft = laptop.sample("suspended", after_s=9.0)
        self.assertTrue(draft.gpus[0]["suspended"])
        self.assertFalse(draft.gpus[0].get("left_to_sleep"))
        self.assertEqual(laptop.fake.inits, 1)

    def test_still_awake_later_it_is_read_again(self):
        # Something else keeps it awake: Silux's session is not the reason.
        laptop = Laptop(idle_laptop_card())
        laptop.sample()
        draft = laptop.sample(after_s=nvidia.LET_IT_SLEEP_S + 1)
        self.assertEqual(laptop.fake.inits, 2)
        self.assertEqual(draft.gpus[0]["temp_c"], 44.0)


class TestTheDisplayServerOnIt(unittest.TestCase):
    """On a hybrid laptop Xorg, or the Wayland compositor, shows up as a
    graphics process of a few MiB on the NVIDIA while nothing uses it, and
    the driver switches the card off all the same."""

    def test_does_not_keep_it_awake(self):
        laptop = Laptop(dataclasses.replace(idle_laptop_card(),
                                            graphics_processes=fake_nvml.IDLE_XORG))
        laptop.sample()
        self.assertEqual(laptop.fake.shutdowns, 1)
        self.assertTrue(laptop.sample().gpus[0]["left_to_sleep"])
        self.assertTrue(laptop.sample("suspended", after_s=9.0).gpus[0]["suspended"])
        self.assertEqual(laptop.fake.inits, 1)


class TestAwakeAndInUse(unittest.TestCase):

    def test_a_game_on_it_keeps_the_session(self):
        laptop = Laptop(dataclasses.replace(idle_laptop_card(), busy=37, memory_busy=12,
                                            graphics_processes=fake_nvml.IDLE_XORG
                                            + [("game", 1800)]))
        for _sample in range(3):
            draft = laptop.sample()
            self.assertEqual(draft.gpus[0]["temp_c"], 44.0)
        self.assertEqual((laptop.fake.inits, laptop.fake.shutdowns), (1, 0))

    def test_so_does_a_compute_program_while_it_waits(self):
        # The driver keeps the card on while a CUDA program runs.
        laptop = Laptop(dataclasses.replace(idle_laptop_card(), compute_processes=1))
        for _sample in range(3):
            laptop.sample()
        self.assertEqual((laptop.fake.inits, laptop.fake.shutdowns), (1, 0))

    def test_once_it_stops_working_the_session_is_let_go(self):
        laptop = Laptop(dataclasses.replace(idle_laptop_card(), busy=37,
                                            graphics_processes=fake_nvml.IDLE_XORG))
        laptop.sample()
        laptop.fake.card.busy = 0
        laptop.sample()
        self.assertEqual(laptop.fake.shutdowns, 1)


class TestADesktopCard(unittest.TestCase):
    """Its driver never switches it off: the session stays open and every
    sample reads it, as before."""

    def test_as_always(self):
        for d3 in (None, "Disabled by default", "Not Supported"):
            with self.subTest(d3=d3):
                laptop = Laptop(fake_nvml.rtx_4070(), d3=d3)
                for _sample in range(4):
                    draft = laptop.sample()
                    self.assertEqual(draft.gpus[0]["power_w"], 110.5)
                    self.assertFalse(draft.gpus[0].get("left_to_sleep"))
                self.assertEqual((laptop.fake.inits, laptop.fake.shutdowns), (1, 0))

    def test_its_power_file_is_read_once(self):
        laptop = Laptop(fake_nvml.rtx_4070(), d3="Disabled by default")
        reads = []
        original = nvidia.driver_lets_it_sleep
        with mock.patch.object(
                nvidia, "driver_lets_it_sleep",
                side_effect=lambda slot: reads.append(slot) or original(slot)):
            for _sample in range(3):
                laptop.sample()
        self.assertEqual(reads, [fake_nvml.SLOT])


class TestTheWorkingCard(unittest.TestCase):

    def test_is_not_the_one_left_alone(self):
        # Home sums up the card that works: on a hybrid laptop, the integrated.
        from silux.model import Gpu
        snapshot = dataclasses.replace(
            shared_snapshot(EQUIPOS / "5800x3d"),
            gpus=(Gpu(index=0, driver="i915", vendor="Intel", integrated=True),
                  Gpu(index=1, driver="nvidia", vendor="NVIDIA", integrated=False,
                      left_to_sleep=True)))
        self.assertEqual(snapshot.working_gpu, 0)


@unittest.skipIf(QApplication is None, "sin PySide6")
class TestOnScreen(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        qt.app()

    def _snapshot(self, draft):
        frozen = draft.freeze()
        return dataclasses.replace(shared_snapshot(EQUIPOS / "5800x3d"),
                                   gpus=frozen.gpus, notes=frozen.notes)

    def test_left_alone_it_says_so_without_dashes(self):
        from tests.test_interface_language import visible_texts
        laptop = Laptop(idle_laptop_card())
        laptop.sample()
        snapshot = self._snapshot(laptop.sample())
        with pantalla.Ventana(snapshot) as window:
            window.select_section("nav.graphics")
            QApplication.processEvents()
            texts = visible_texts(window.stack.currentWidget())
        self.assertIn(render.gpu_asleep(snapshot.gpus[0]), texts)
        self.assertIn(_("prov.nvml.lefttosleep.title"), texts)
        self.assertNotIn(render.DASH, texts)

    def test_the_open_page_follows_it(self):
        # Rule 9: open with the card read, then left alone, as if mounted so.
        from tests.test_al_momento import retrato
        laptop = Laptop(idle_laptop_card())
        read = self._snapshot(laptop.sample())
        left = self._snapshot(laptop.sample())
        with pantalla.Ventana(read) as window:
            window.select_section("nav.graphics")
            QApplication.processEvents()
            window._on_sample(left)
            QApplication.processEvents()
            followed = retrato(window)
        with pantalla.Ventana(left) as window:
            window.select_section("nav.graphics")
            QApplication.processEvents()
            mounted = retrato(window)
        self.assertEqual(sorted(followed), sorted(mounted))
