"""Where a dump's recording held something identifying, as a path of keys:
each one from its own parent, not from the sibling before it."""

import unittest

from silux.volcado import _json_without


class TestThePathOfEachRemovedValue(unittest.TestCase):

    def test_siblings_and_nesting(self):
        data = {"a": {"x": "host-1", "y": "fine"}, "b": "host-1", "c": ["ok", "host-1"]}
        clean, removed = _json_without(data, b"host-1")
        self.assertEqual(removed, ["a.x", "b", "c[1]"])
        self.assertEqual(clean, {"a": {"x": None, "y": "fine"}, "b": None, "c": ["ok"]})


if __name__ == "__main__":
    unittest.main()
