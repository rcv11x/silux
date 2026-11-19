"""AMD's own specifications table, from amd.com, by model.

libcpuid's tables are frozen; amd.com lists every AMD chip it sells, with
its codename, socket and node. The table uses it when libcpuid doesn't know
the chip, and to fill in the node or socket libcpuid lacks. libcpuid still
wins when it knows the chip, so none of the 411 reference CPUs changes.
"""

import unittest

from silux import db


def identify(brand, ext_family, ext_model, family=15, model=0):
    return db.identify_x86(vendor_id="AuthenticAMD", family=family, model=model,
                           stepping=0, ext_family=ext_family, ext_model=ext_model,
                           cores=0, brand=brand)


class TestTheTable(unittest.TestCase):

    def test_it_comes_from_amd_com(self):
        data = db.load()
        self.assertIn("amd.com", data["sources"])
        self.assertGreater(len(data["amd_models"]), 600)
        row = db.amd_model("AMD Ryzen 7 5800X3D 8-Core Processor")
        self.assertEqual((row["codename"], row["socket"]), ("Vermeer", "AM4"))
        self.assertTrue(row["source"].startswith("https://www.amd.com/"))

    def test_family_names_are_not_codenames(self):
        codenames = {row["codename"] for row in db.load()["amd_models"]}
        for generic in ("FX Legacy", "Athlon Legacy", "Threadripper", "Phenom", "Sempron"):
            with self.subTest(generic=generic):
                self.assertNotIn(generic, codenames)
        # The socket goes in its own field, not glued to the name.
        self.assertFalse({c for c in codenames if c and c.endswith((" AM4", " AM5"))})


class TestTheModelKey(unittest.TestCase):

    def test_brand_strings_and_amd_names_meet(self):
        for brand, name in (
                ("AMD Ryzen 7 5800X3D 8-Core Processor", "AMD Ryzen™ 7 5800X3D"),
                ("AMD Ryzen Threadripper PRO 9985WX 64-Cores", "AMD Ryzen™ Threadripper™ PRO 9985WX"),
                ("AMD FX(tm)-8350 Eight-Core Processor", "AMD FX-8350"),
                ("AMD A10-7850K Radeon R7, 12 Compute Cores 4C+8G", "AMD A10-7850K"),
                ("AMD Ryzen 7 7445HS w/ Radeon 740M Graphics", "AMD Ryzen™ 7 7445HS")):
            with self.subTest(brand=brand):
                self.assertEqual(db.amd_model_key(brand), db.amd_model_key(name))


class TestIdentification(unittest.TestCase):

    def test_a_chip_libcpuid_lacks_gets_amd_com(self):
        # Ryzen 7 7445HS (Phoenix, 0x7C) isn't in libcpuid.
        ident = identify("AMD Ryzen 7 7445HS w/ Radeon 740M Graphics", 25, 0x7C, model=12)
        self.assertEqual(ident.codename, "Phoenix")
        self.assertEqual(ident.technology, db.amd_model("AMD Ryzen 7 7445HS")["node"])

    def test_libcpuid_still_wins_when_it_knows_the_chip(self):
        ident = identify("AMD Ryzen 7 5800X3D 8-Core Processor", 25, 33, model=1)
        self.assertEqual(ident.codename, "Ryzen 7 (Vermeer)")
        self.assertEqual(ident.technology, "TSMC N7FF")

    def test_the_socket_amd_lists_when_nothing_else_has_it(self):
        brand = "AMD Ryzen 7 7445HS w/ Radeon 740M Graphics"
        ident = identify(brand, 25, 0x7C, model=12)
        socket = db.find_socket("AuthenticAMD", ident.codename, brand)
        self.assertEqual(socket, db.amd_model(brand)["socket"])
        self.assertTrue(socket)


if __name__ == "__main__":
    unittest.main()
