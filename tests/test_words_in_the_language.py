"""Words a provider makes up go through the translation, joining words too.

The SPD notice joined the memory types with a Spanish «y», and the Vulkan
row's detail said «instancia» with the interface in English. The interface
test does not see them: they travel inside the model, as data.
"""

import types
import unittest
from unittest import mock

from silux import i18n
from silux.providers import spd_modules
from silux.providers.base import Draft
from tests.test_equipos import EQUIPOS, foto


class _InEnglish(unittest.TestCase):

    def setUp(self):
        i18n.set_language("en")
        self.addCleanup(i18n.set_language, "es")


class TestTheSpdNotice(_InEnglish):

    def test_two_types_are_joined_in_english(self):
        lecturas = [types.SimpleNamespace(decoded=False, dram_type=t, part_number=None)
                    for t in ("DDR3", "DDR2")]
        with mock.patch.object(spd_modules.spd_module, "read_all", return_value=lecturas):
            borrador = Draft()
            spd_modules.SpdModules().collect(borrador)
        mensaje = next(n.message for n in borrador.notes if n.path == "spd")
        self.assertIn("DDR2 and DDR3", mensaje)
        self.assertNotIn(" y ", mensaje)


class TestTheVulkanRow(_InEnglish):

    def test_its_instance_in_english(self):
        f = foto(EQUIPOS / "5800x3d")[0]
        detalles = [a.extra for g in f.gpus for a in g.apis if a.name == "Vulkan"]
        self.assertTrue(detalles)
        for detalle in detalles:
            self.assertTrue(detalle.startswith("instance "), detalle)


if __name__ == "__main__":
    unittest.main()
