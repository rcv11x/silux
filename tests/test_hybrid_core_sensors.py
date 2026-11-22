"""On a hybrid processor, Sensors says which cores are P and which are E.

coretemp numbers its cores by core id: an i5-12450H read «Núcleo 0, 4, 8,
12, 20, 21, 22, 23», and nothing said that the last four are E-cores.
"""

import unittest

from silux import render
from silux.i18n import _
from tests import pantalla, qt
from tests.test_equipos import EQUIPOS, foto, volcados

TYPE_KEYS = {"performance": "sensor.core.p", "efficiency": "sensor.core.e"}


class TestTheCoreSensors(unittest.TestCase):

    def test_named_by_the_type_of_their_core_in_every_dump(self):
        for folder in volcados():
            snapshot = foto(folder)[0]
            types = {cpu.core_id: cpu.type_key for cpu in snapshot.cpu.logical}
            hybrid = len(set(types.values())) > 1
            for sensor in snapshot.sensors:
                if sensor.chip != "coretemp" or not (sensor.chip_label or "").startswith("Core "):
                    continue
                core = int(sensor.chip_label.split()[1])
                key = TYPE_KEYS[types[core]] if hybrid else "sensor.core"
                with self.subTest(folder.name, sensor=sensor.chip_label):
                    self.assertEqual(render.sensor_label(sensor), _(key).format(n=core))

    def test_on_the_sensors_page(self):
        qt.app()
        with pantalla.Ventana(foto(EQUIPOS / "i5-12450h")[0]) as window:
            window.select_section("Sensores")
            texts = pantalla.textos_de(window.stack.currentWidget())
        joined = " | ".join(texts)
        for n in (0, 4, 8, 12):
            self.assertIn(_("sensor.core.p").format(n=n), joined)
        for n in (20, 21, 22, 23):
            self.assertIn(_("sensor.core.e").format(n=n), joined)


if __name__ == "__main__":
    unittest.main()
