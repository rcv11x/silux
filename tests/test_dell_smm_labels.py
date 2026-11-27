"""dell_smm labels its sensors in English, fixed in the driver
(dell-smm-hwmon.c): «Processor Fan» and «Other» showed as they came in a
Spanish Sensors page."""

import unittest

from silux.i18n import _
from tests import pantalla, qt
from tests.test_equipos import EQUIPOS, shared_snapshot
from tests.test_interface_language import visible_texts


class TestDellSmmLabels(unittest.TestCase):
    def test_in_the_interfaces_language(self):
        for dump, expected in (("celeron-560", ("sensor.dell.fan.cpu", "sensor.dell.other")),
                               ("core2-p8400", ("sensor.dell.fan.cpu", "sensor.dell.other",
                                                "sensor.dell.sodimm", "sensor.dell.gpu"))):
            with self.subTest(dump=dump):
                snapshot = shared_snapshot(EQUIPOS / dump)
                labels = {s.label for s in snapshot.sensors if s.chip == "dell_smm"}
                for key in expected:
                    self.assertIn(_(key), labels)
                self.assertFalse(labels & {"Processor Fan", "Other", "SODIMM", "GPU"})
                # What the driver wrote stays for the report.
                self.assertIn("Processor Fan",
                              {s.chip_label for s in snapshot.sensors if s.chip == "dell_smm"})

    def test_on_the_sensors_page(self):
        qt.app()
        with pantalla.Ventana(shared_snapshot(EQUIPOS / "celeron-560")) as window:
            window.select_section("Sensores")
            qt.app().processEvents()
            texts = visible_texts(window.stack.currentWidget())
        self.assertIn(_("sensor.dell.fan.cpu"), texts)
        self.assertNotIn("Processor Fan", texts)
        self.assertNotIn("Other", texts)


if __name__ == "__main__":
    unittest.main()
