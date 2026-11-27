"""The mean of a sensor never falls outside its minimum and maximum.

An NVMe gives its temperature in whole kelvin: 349 K is 75.85 °C. Added
six times in floating point, the mean came out 75.85000000000001, which
rounds to «75.9» beside a maximum of «75.8».
"""

import unittest

from silux import render
from silux.tracking import Tracker


class TestTheMean(unittest.TestCase):
    def test_a_steady_reading_has_its_own_mean(self):
        tracker = Tracker()
        for _sample in range(6):
            # As hwmon gives it, in millidegrees.
            tracker.update("nvme", 75850 / 1000)
        entry = tracker.get("nvme")
        self.assertLessEqual(entry.average, entry.maximum)
        self.assertGreaterEqual(entry.average, entry.minimum)
        self.assertEqual(render.temperature(entry.average), render.temperature(entry.maximum))

    def test_it_stays_between_the_extremes_however_long(self):
        tracker = Tracker()
        for sample in range(5000):
            tracker.update("x", 75.85 if sample % 2 else 75.75)
            entry = tracker.get("x")
            self.assertTrue(entry.minimum <= entry.average <= entry.maximum, sample)


if __name__ == "__main__":
    unittest.main()
