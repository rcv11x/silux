"""The process node from cpuid (Todd Allen), by family and model.

The kernel names Panther Lake but not its node, and libcpuid has neither.
cpuid's uarch tables give the node by family and model; Silux uses it only
when no other source gives one, and never invents it when cpuid has no row.
"""

import unittest

from silux import db


class TestCpuidNodes(unittest.TestCase):

    def test_it_comes_from_a_pinned_release(self):
        source = db.load()["sources"]["cpuid"]
        self.assertTrue(source["version"].isdigit())
        self.assertGreater(len(db.load()["cpuid_nodes"]), 100)

    def test_nodes_are_nodes(self):
        # The old AMD rows said «939-pin, 90nm»: only the node is kept.
        for row in db.load()["cpuid_nodes"]:
            with self.subTest(row=row):
                self.assertNotIn("pin", row["node"])
                self.assertNotIn(",", row["node"])

    def test_panther_lake_gets_its_node(self):
        self.assertEqual(db.cpuid_node("GenuineIntel", 6, 0xCC), "Intel 18A")
        ident = db.identify_x86(vendor_id="GenuineIntel", family=6, model=0xC, stepping=0,
                                ext_family=6, ext_model=0xCC, cores=0, brand="")
        self.assertEqual((ident.codename, ident.technology), ("Panther Lake", "Intel 18A"))

    def test_no_row_no_node(self):
        self.assertIsNone(db.cpuid_node("GenuineIntel", 99, 0x01))

    def test_a_known_node_is_not_replaced(self):
        ident = db.identify_x86(vendor_id="AuthenticAMD", family=15, model=1, stepping=2,
                                ext_family=25, ext_model=33, cores=8,
                                brand="AMD Ryzen 7 5800X3D 8-Core Processor")
        self.assertEqual(ident.technology, "TSMC N7FF")


if __name__ == "__main__":
    unittest.main()
