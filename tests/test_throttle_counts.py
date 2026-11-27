"""The T480s's thermal throttling (Felix's prueba13 report): «128753 on the
cores (0.0 s)». Thousands with their separator, and no time where the
kernel counted the events without one: 128 753 of them in 0 ms don't add
up."""

import unittest

from silux import render
from silux.i18n import _
from tests.test_equipos import EQUIPOS, shared_snapshot


class TestThrottleCounts(unittest.TestCase):
    def test_counted_without_their_time(self):
        throttle = shared_snapshot(EQUIPOS / "i5-8350u").cpu.thermal_throttle
        self.assertEqual(throttle.core_ms, 0)
        text = render.thermal_throttle(throttle)
        self.assertEqual(text, " · ".join((
            _("cpu.throttle.cores.untimed").format(n=render.thousands(throttle.core_count)),
            _("cpu.throttle.package.untimed").format(n=render.thousands(throttle.package_count)))))
        self.assertNotIn("0.0 s", text)


if __name__ == "__main__":
    unittest.main()
