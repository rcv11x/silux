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


class TestAnImpossibleReading(unittest.TestCase):
    """A laptop RTX 4050 read 588.21 W on waking, with 95 W as its highest
    limit. Over 1.5 times that, a reading is thrown away, and the next way
    is not tried: the card answered, with something impossible."""

    def test_thrown_away_and_the_next_one_kept(self):
        session, _fake, first = read_once(fake_nvml.rtx_4050_laptop())
        self.assertIsNone(first.power_w)
        self.assertEqual((first.power_discarded_w, first.power_discarded_source),
                         (588.21, "nvmlDeviceGetPowerUsage"))
        answers = dict(first.power_answers)
        self.assertEqual(answers["field 185"], "not asked")
        self.assertIsNone(first.power_estimate_w)
        self.assertEqual(answers["ceiling"], "142.5 W, 1.5 x 95.0 W")
        self.assertEqual(session.devices()[0].power_w, 1.3)

    def test_a_card_on_its_limit_is_not(self):
        # A card at full load passes its limit by a little: an RTX 3060's
        # maximum is its factory 170 W.
        card = fake_nvml.Card(name="NVIDIA GeForce RTX 3060", power_mw=171000,
                              enforced_mw=170000, default_mw=170000,
                              constraints_mw=(100000, 170000))
        self.assertEqual(read_once(card)[2].power_w, 171.0)

    def test_without_a_declared_limit_only_the_general_ceiling(self):
        card = read_once(fake_nvml.Card(name="NVIDIA", power_mw=588210))[2]
        self.assertEqual(card.power_w, 588.2)
        self.assertEqual(dict(card.power_answers)["ceiling"], "5000 W, no declared limit")

    def test_impossible_samples_are_left_out_of_the_estimate(self):
        card = fake_nvml.Card(name="NVIDIA", samples=[588210] + [12000] * 48,
                              constraints_mw=(5000, 95000), architecture=nvml.ARCH_ADA)
        read = read_once(card)[2]
        self.assertEqual((read.power_estimate_w, read.power_estimate_samples), (12.0, 48))
        self.assertIn("1 over the ceiling left out",
                      dict(read.power_answers)["nvmlDeviceGetSamples"])

    def _woken(self, asleep_first):
        fake = fake_nvml.FakeNvml(fake_nvml.rtx_4050_laptop())
        provider = nvidia.NvidiaGpus()
        if asleep_first:
            collect(fake, "suspended", provider=provider)
        return collect(fake, provider=provider)[0]

    def test_its_note_gives_the_sleep_as_the_probable_cause(self):
        note = next(n for n in self._woken(True).notes if n.path == "gpus.0.power_w")
        self.assertEqual((note.key, note.message, note.hint),
                         ("nvml.discarded", _("prov.nvml.discarded"),
                          _("prov.nvml.discarded.woke")))
        self.assertEqual(note.detail, "588.21 W from nvmlDeviceGetPowerUsage, over the "
                                      "ceiling of 142.5 W, 1.5 x 95.0 W; suspended before "
                                      "this reading")

    def test_not_if_it_was_not_asleep(self):
        note = next(n for n in self._woken(False).notes if n.path == "gpus.0.power_w")
        self.assertEqual((note.key, note.hint), ("nvml.discarded", ""))

    def test_once_read_it_is_no_longer_just_awake(self):
        # Woken by a program that keeps using it: read every sample.
        fake = fake_nvml.FakeNvml(dataclasses.replace(fake_nvml.rtx_4050_laptop(),
                                                      power_mw=[588210], busy=37))
        provider = nvidia.NvidiaGpus()
        collect(fake, "suspended", provider=provider)
        collect(fake, provider=provider)
        later = collect(fake, provider=provider)[0]
        note = next(n for n in later.notes if n.path == "gpus.0.power_w")
        self.assertEqual((note.key, note.hint), ("nvml.discarded", ""))

    def test_its_numbers_in_the_report(self):
        text = report.build(snapshot_of(self._woken(True)), anonymous=True)
        self.assertIn("588.21 W from nvmlDeviceGetPowerUsage", text)


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


def collect_1050_ti(card):
    draft = Draft()
    # As DRM leaves it from pci.ids: the name, and the chip as its codename.
    draft.gpu(0).update(pci_slot=fake_nvml.SLOT, vendor="NVIDIA", driver="nvidia",
                        name="GeForce GTX 1050 Ti", codename="GP107", drm_node="card1",
                        integrated=False)
    return collect(fake_nvml.FakeNvml(card), draft=draft)[0]


class TestACardWithNoSensor(unittest.TestCase):
    """A GTX 1050 Ti on driver 535: `nvidia-smi` gives «N/A / 75W», and
    Silux showed 36 W. Whichever way it came from, NOT_SUPPORTED is the
    driver saying the card reads no power: no figure, and no estimate before
    Ada."""

    def test_not_from_the_instant_field(self):
        card = read_once(fake_nvml.gtx_1050_ti_instant())[2]
        self.assertEqual((card.power_w, card.power_sensor, card.power_estimate_w),
                         (None, False, None))
        self.assertIn("not taken", dict(card.power_answers)["field 186"])

    def test_not_from_its_samples_buffer(self):
        card = read_once(fake_nvml.gtx_1050_ti_samples())[2]
        self.assertEqual((card.power_w, card.power_sensor, card.power_estimate_w),
                         (None, False, None))
        answers = dict(card.power_answers)
        self.assertIn("119 samples", answers["nvmlDeviceGetSamples"])
        self.assertEqual(answers["nvmlDeviceGetArchitecture"], str(fake_nvml.PASCAL))

    def test_no_notice_repeats_its_tile(self):
        # «Sin sensor» and the limit are on the power tile: a notice saying
        # the same above the cards was said twice.
        draft = collect_1050_ti(fake_nvml.gtx_1050_ti_instant())
        self.assertFalse([n for n in draft.notes if n.path == "gpus.0.power_w"])
        self.assertIs(draft.gpus[0]["power_sensor"], False)
        self.assertEqual(draft.gpus[0]["power_cap_w"], 75.0)

    @unittest.skipIf(QApplication is None, "sin PySide6")
    def test_what_nvidia_smi_showed_is_on_its_page(self):
        # The tester's nvidia-smi: 4096 MiB, fan at 45 %, P8. A capture with
        # a fake card that answered none of it read «nvidia no publica total,
        # ventilador ni relojes».
        qt.app()
        snapshot = snapshot_of(collect_1050_ti(fake_nvml.gtx_1050_ti_instant()))
        with pantalla.Ventana(snapshot) as window:
            window.select_section("nav.graphics")
            section = window.stack.currentWidget()._sections[0]
            self.assertEqual(section.title.text(), "GeForce GTX 1050 Ti")
            self.assertEqual(section.memory._values[_("gpu.vram.total")].full_text(), "4 GiB")
            self.assertEqual(section.sensors._values[_("gpu.sensor.fan")].full_text(),
                             render.fan(None, 45.0))
            self.assertEqual(section.clocks._values[_("gpu.clock.pstate")].full_text(), "P8")

    @unittest.skipIf(QApplication is None, "sin PySide6")
    def test_on_screen_no_sensor_and_its_limit_apart(self):
        from tests.test_interface_language import visible_texts
        qt.app()
        for card in (fake_nvml.gtx_1050_ti_instant(), fake_nvml.gtx_1050_ti_samples()):
            snapshot = snapshot_of(collect_1050_ti(card))
            with pantalla.Ventana(snapshot) as window, self.subTest(card=card.fields or "samples"):
                texts = {key: visible_texts(page) for key, page in pantalla.recorrer(window)}
                window.select_section("nav.graphics")
                tile = window.stack.currentWidget()._sections[0].tile_power
                self.assertEqual(tile.value.text(), _("gpu.tile.nosensor"))
                self.assertEqual(tile.detail.full_text(),
                                 _("gpu.tile.limit").format(limit=render.limit_watts(75.0)))
                for key, page_texts in texts.items():
                    self.assertFalse([t for t in page_texts if "36" in t and "W" in t], key)


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
            # It has no sensor: said so, with no figure nor a dash.
            self.assertEqual(tile.value.text(), _("gpu.tile.nosensor"))

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
