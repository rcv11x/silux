"""A mounted dump does not have this machine's helper.

The installed helper and its polkit rule are files of the machine. Read
straight, one installed here and older than the code made every dump's
photo say «outdated», and five tests that open the window with a dump failed
on the author's machines only: the CI has no helper installed.
"""

import os
import pathlib
import tempfile
import unittest
from unittest import mock

from silux import volcado
from silux.collector import Collector
from silux.privileged import client

EQUIPOS = pathlib.Path(__file__).resolve().parent / "fixtures" / "equipos"


class TestTheHelperInstalledHere(unittest.TestCase):

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        # An old helper and its rule, installed on this machine.
        ayudante = pathlib.Path(tmp.name) / "silux-helper"
        ayudante.write_text("#!/usr/bin/python3\n# an older helper\n")
        os.chmod(ayudante, 0o755)
        politica = pathlib.Path(tmp.name) / "org.silux.helper.policy"
        politica.write_text("<policyconfig/>\n")
        for parche in (mock.patch.object(client, "INSTALLED_HELPER", ayudante),
                       mock.patch.object(client, "INSTALLED_POLICY", politica)):
            parche.start()
            self.addCleanup(parche.stop)

    def test_here_it_needs_replacing(self):
        self.assertTrue(client.PrivilegedClient.needs_reinstall())

    def test_a_dumps_photo_does_not_carry_it(self):
        with volcado.mounted(EQUIPOS / "i5-10400"):
            self.assertFalse(client.PrivilegedClient.installed())
            collector = Collector()
            try:
                photo = collector.snapshot()
            finally:
                collector.close()
        self.assertFalse(photo.privileged.outdated)


if __name__ == "__main__":
    unittest.main()
