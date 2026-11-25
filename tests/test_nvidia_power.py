"""An NVIDIA's power by each of NVML's ways, against a fake libnvidia-ml.

A card with a power sensor answers nvmlDeviceGetPowerUsage and shows as it
always did. One without a sensor (a desktop RTX 4060) answers only through
the power samples buffer, which is the driver's estimate: it goes in its own
field and row, named as an estimate, never as the power (docs/nvml.md).
"""

import dataclasses
import json
import unittest

from silux import nvml, render, report
from silux.i18n import _
from silux.model import to_jsonable
from silux.providers import nvidia
from silux.providers.base import Draft
from tests import fake_nvml, pantalla, qt
from tests.arbol import arbol
from tests.test_equipos import EQUIPOS, shared_snapshot

try:
    from PySide6.QtWidgets import QApplication
except ImportError:                                    # pragma: no cover
    QApplication = None


def collect(fake, runtime_status="active", d3=None, draft=None, provider=None):
    """One sample of the NVIDIA provider over a card DRM already listed."""
    if draft is None:
        draft = Draft()
        draft.gpu(0).update(pci_slot=fake_nvml.SLOT, vendor="NVIDIA", driver="nvidia",
                            name="AD107 [GeForce RTX 4060]", drm_node="card1",
                            integrated=False)
    provider = provider or nvidia.NvidiaGpus()
    with arbol(fake_nvml.bus(runtime_status, d3)), fake_nvml.loaded(fake):
        if provider.available():
            provider.collect(draft)
    return draft, provider


def snapshot_of(draft):
    """A dump's snapshot with these cards in place of its own."""
    frozen = draft.freeze()
    return dataclasses.replace(shared_snapshot(EQUIPOS / "5800x3d"),
                               gpus=frozen.gpus, notes=frozen.notes)


def read_once(card):
    session = nvml.Nvml()
    fake = fake_nvml.FakeNvml(card)
    session._lib, session._active = fake, True
    return session, fake, session.devices()[0]


class TestTheDriversEstimate(unittest.TestCase):
    """The desktop RTX 4060: the three ways nvidia-smi gives the power answer
    NOT_SUPPORTED, and the samples buffer holds the driver's 53 W."""

    def test_its_own_field_and_never_the_power(self):
        card = read_once(fake_nvml.rtx_4060_desktop())[2]
        self.assertIsNone(card.power_w)
        self.assertIsNone(card.power_source)
        self.assertEqual((card.power_estimate_w, card.power_estimate_window_s,
                          card.power_estimate_samples), (53.1, 2.44, 119))

    def test_the_next_reading_takes_only_the_new_samples(self):
        session, fake, first = read_once(fake_nvml.rtx_4060_desktop())
        fake.advance(1.0, 54000)
        second = session.devices()[0]
        newest = fake_nvml.FIRST_SAMPLE_US + 118 * fake_nvml.SAMPLE_PERIOD_US
        self.assertEqual(fake.since, [0, newest])
        self.assertEqual((second.power_estimate_w, second.power_estimate_samples), (54.0, 48))
        self.assertAlmostEqual(second.power_estimate_window_s, 1.0, places=1)

    def test_what_each_way_answered(self):
        answers = dict(read_once(fake_nvml.rtx_4060_desktop())[2].power_answers)
        self.assertEqual(answers["nvmlDeviceGetPowerUsage"], "NVML_ERROR_NOT_SUPPORTED (3)")
        self.assertEqual(answers["field 185"], "NVML_ERROR_NOT_SUPPORTED (3)")
        self.assertEqual(answers["field 186"], "NVML_ERROR_NOT_SUPPORTED (3)")
        self.assertEqual(answers["nvmlDeviceGetSamples"],
                         "119 samples over 2.44 s, 52.59-55.37 W, mean 53.11 W")
        self.assertEqual(answers["nvmlDeviceGetTotalEnergyConsumption"],
                         "NVML_ERROR_NOT_SUPPORTED (3)")

    def test_its_note_says_the_driver_calculates_it(self):
        draft, _provider = collect(fake_nvml.FakeNvml(fake_nvml.rtx_4060_desktop()))
        notes = [n for n in draft.notes if n.path == "gpus.0.power_w"]
        self.assertEqual([n.key for n in notes], ["nvml.estimate"])
        self.assertEqual(notes[0].message, _("prov.nvml.estimate"))
        self.assertIn("NOT_SUPPORTED", notes[0].detail)


class TestACardWithASensor(unittest.TestCase):
    """An RTX 4070 answers nvmlDeviceGetPowerUsage: its power, as always."""

    def test_its_power_and_no_estimate(self):
        card = read_once(fake_nvml.rtx_4070())[2]
        self.assertEqual((card.power_w, card.power_source), (110.5, "nvmlDeviceGetPowerUsage"))
        self.assertIsNone(card.power_estimate_w)
        answers = dict(card.power_answers)
        self.assertEqual(answers["field 185"], "not asked")
        self.assertEqual(answers["nvmlDeviceGetTotalEnergyConsumption"], "812345678 mJ")

    def test_no_note_on_its_power(self):
        draft, _provider = collect(fake_nvml.FakeNvml(fake_nvml.rtx_4070()))
        self.assertEqual(draft.gpus[0]["power_w"], 110.5)
        self.assertFalse([n for n in draft.notes if n.path == "gpus.0.power_w"])


@unittest.skipIf(QApplication is None, "sin PySide6")
class TestOnScreen(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        qt.app()

    def _window_texts(self, card):
        # A hidden row's label is still a widget: only what is seen counts.
        from tests.test_interface_language import visible_texts
        draft, _provider = collect(fake_nvml.FakeNvml(card))
        snapshot = snapshot_of(draft)
        with pantalla.Ventana(snapshot) as window:
            texts = {key: visible_texts(page) for key, page in pantalla.recorrer(window)}
        return snapshot, texts

    def test_the_estimate_only_in_the_graphics_page(self):
        snapshot, texts = self._window_texts(fake_nvml.rtx_4060_desktop())
        estimate = render.gpu_power_estimate(snapshot.gpus[0])
        self.assertEqual(estimate, "53 W · " + _("gpu.power.estimate.detail").format(
            window="2.4 s"))
        self.assertIn(estimate, texts["nav.graphics"])
        self.assertIn(_("gpu.sensor.powerestimate"), texts["nav.graphics"])
        self.assertIn(_("prov.nvml.estimate"), " ".join(texts["nav.graphics"]))
        for key in ("nav.home", "nav.sensors"):
            with self.subTest(page=key):
                self.assertFalse([t for t in texts[key] if "53" in t and "W" in t])

    def test_the_estimate_is_no_tile_figure(self):
        from silux.ui.pages.graphics import GraphicsPage
        draft, _provider = collect(fake_nvml.FakeNvml(fake_nvml.rtx_4060_desktop()))
        snapshot = snapshot_of(draft)
        with pantalla.Ventana(snapshot) as window:
            window.select_section("nav.graphics")
            page = window.stack.currentWidget()
            self.assertIsInstance(page, GraphicsPage)
            tile = page._sections[0].tile_power
            self.assertEqual(tile.value.text(), render.DASH)

    def test_a_card_with_a_sensor_says_estimate_nowhere(self):
        snapshot, texts = self._window_texts(fake_nvml.rtx_4070())
        words = (_("gpu.sensor.powerestimate").lower(), "estimad", "estimate")
        for key, page_texts in texts.items():
            with self.subTest(page=key):
                self.assertFalse([t for t in page_texts if any(w in t.lower() for w in words)])
        self.assertNotIn("estimad", report.build(snapshot, anonymous=True).lower())


class TestTheReportAndTheJson(unittest.TestCase):

    def test_the_json_has_the_estimate_and_not_the_answers(self):
        draft, _provider = collect(fake_nvml.FakeNvml(fake_nvml.rtx_4060_desktop()))
        gpu = json.loads(json.dumps(to_jsonable(draft.freeze())))["gpus"][0]
        self.assertIsNone(gpu["power_w"])
        self.assertEqual((gpu["power_estimate_w"], gpu["power_estimate_window_s"],
                          gpu["power_estimate_samples"]), (53.1, 2.44, 119))
        self.assertNotIn("power_answers", gpu)
        self.assertNotIn("runtime_status", gpu)

    def test_the_json_says_which_way_gave_the_power(self):
        draft, _provider = collect(fake_nvml.FakeNvml(fake_nvml.rtx_4070()))
        gpu = to_jsonable(draft.freeze())["gpus"][0]
        self.assertEqual(gpu["power_source"], "nvmlDeviceGetPowerUsage")

    def test_the_report_has_each_answer_and_the_runtime_state(self):
        draft, _provider = collect(fake_nvml.FakeNvml(fake_nvml.rtx_4060_desktop()))
        text = report.build(snapshot_of(draft), anonymous=True)
        self.assertIn("  - runtime_status: active", text)
        self.assertIn("  - nvmlDeviceGetSamples: 119 samples over 2.44 s", text)
        self.assertIn("  - nvmlDeviceGetTotalEnergyConsumption: NVML_ERROR_NOT_SUPPORTED (3)",
                      text)


if __name__ == "__main__":
    unittest.main()
