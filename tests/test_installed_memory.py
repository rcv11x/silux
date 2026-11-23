"""Installed memory is never less than the usable.

Without permissions it is the sum of the SPD chips, and memory soldered on the
board has none: the author's T14 read «8 GB instalados · 15.3 GB utilizables».
Every dump, ours and the testers', is checked; the T14 says what it knows.
"""

import unittest

from silux.i18n import _
from tests.test_equipos import EQUIPOS, foto, shared_snapshot, volcados


class TestInstalledIsNeverLessThanUsable(unittest.TestCase):

    def test_in_every_dump(self):
        for carpeta in volcados():
            f = shared_snapshot(carpeta)
            with self.subTest(dump=carpeta.name):
                if f.installed_memory_bytes is not None:
                    self.assertGreaterEqual(f.installed_memory_bytes,
                                            f.system.memory.total_bytes)

    def test_the_t14_says_what_it_knows(self):
        f = shared_snapshot(EQUIPOS / "i5-1135g7")
        self.assertIsNone(f.installed_memory_bytes)
        self.assertFalse(f.spd_accounts_for_all_memory)

    def test_two_slots_full_still_say_it(self):
        f = shared_snapshot(EQUIPOS / "i7-10700f")
        self.assertEqual(f.installed_memory_bytes, 16 << 30)
        self.assertTrue(f.spd_accounts_for_all_memory)


if __name__ == "__main__":
    unittest.main()
