"""A memory maker is one name however the firmware writes it: the module
read from its SPD and its twin read from the BIOS table can't show two."""

import unittest

from silux import render


class TestOneMaker(unittest.TestCase):

    def test_hynix_however_the_firmware_writes_it(self):
        for name in ("Hynix/Hyundai", "Hynix Semiconductor", "SK Hynix", "SK hynix",
                     "Hyundai Electronics"):
            with self.subTest(name=name):
                self.assertEqual(render.memory_maker(name), "SK Hynix")


if __name__ == "__main__":
    unittest.main()
