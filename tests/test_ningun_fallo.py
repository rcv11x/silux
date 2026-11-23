"""No dump makes a provider fail.

A failure of Silux's own code is not something the machine lacks (rule 5):
the page says «Falló al leerse», and a dump reproducing it is a bug to fix,
not a reference to keep. The i7-12700KF's network page said so in its
screen reference, and nothing stopped it.
"""

import unittest

from tests.per_dump import per_dump
from tests.test_equipos import shared_snapshot


class TestNoProviderFails(unittest.TestCase):

    def _every_dump(self, folder):
        photo = shared_snapshot(folder)
        self.assertEqual([(f.where, f.error) for f in photo.failures], [])


per_dump(TestNoProviderFails, "no_provider_fails", TestNoProviderFails._every_dump)


if __name__ == "__main__":
    unittest.main()
