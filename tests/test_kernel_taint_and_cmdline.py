"""System: whether the kernel is tainted, and its command line.

Two cheap readings without permissions. The command line names the
machine's disks (root=UUID=…), its encrypted volumes and sometimes its name
or address: that is hidden when it is read, so neither the window nor a
report nor a dump holds it.
"""

import re
import unittest

from silux import privacidad, render
from silux.i18n import _
from tests import pantalla, qt
from tests.test_equipos import EQUIPOS, foto, volcados

try:
    from PySide6.QtWidgets import QApplication
except ImportError:                                    # pragma: no cover
    QApplication = None

UUID = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")


class TestHidingTheCommandLine(unittest.TestCase):

    def test_what_names_the_machine_is_hidden(self):
        line = ("BOOT_IMAGE=/vmlinuz-linux rw quiet rootflags=subvol=/@ "
                "root=UUID=1234abcd-12ab-34cd-56ef-1234567890ab resume=PARTUUID=0a1b-02 "
                "cryptdevice=UUID=0a1b2c3d-1111-2222-3333-444455556666:root "
                "rd.luks.name=0a1b2c3d-1111-2222-3333-444455556666=cryptroot "
                "ip=192.0.2.5::192.0.2.1:255.255.255.0 systemd.hostname=casa "
                "foo=LABEL=MiDisco")
        hidden = privacidad.hide_cmdline_identifiers(line)
        self.assertEqual(hidden, (
            "BOOT_IMAGE=/vmlinuz-linux", "rw", "quiet", "rootflags=subvol=/@", "root=…",
            "resume=…", "cryptdevice=…", "rd.luks.name=…", "ip=…", "systemd.hostname=…",
            "foo=LABEL=…"))

    def test_no_dump_holds_a_uuid_in_its_command_line(self):
        for dump in volcados():
            path = dump / "proc" / "cmdline"
            if path.is_file():
                with self.subTest(dump=dump.name):
                    self.assertIsNone(UUID.search(path.read_text()))


class TestTaint(unittest.TestCase):

    def test_reasons(self):
        self.assertEqual(render.tainted(4096 + 8192),
                         f"{_('sys.taint.12')} · {_('sys.taint.13')}")
        self.assertEqual(render.tainted(0), _("sys.taint.no"))
        self.assertEqual(render.tainted(None), render.DASH)
        # A bit newer than the table is said, not dropped.
        self.assertIn("1048576", render.tainted(1 << 20))


@unittest.skipIf(QApplication is None, "no PySide6")
class TestOnTheSystemPage(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.app = qt.app()

    def page(self, window):
        window.select_section("Sistema")
        self.app.processEvents()
        return window.system_page

    def test_shown_when_the_machine_publishes_them(self):
        with pantalla.Ventana(foto(EQUIPOS / "5800x3d")[0]) as window:
            page = self.page(window)
            tainted = page.kernel._values[_("sys.kernel.tainted")]
            self.assertTrue(tainted.isVisible())
            self.assertEqual(tainted.full_text(), render.tainted(12288))
            line = page.boot._values[_("sys.boot.cmdline")]
            self.assertTrue(line.isVisible())
            self.assertIn("root=…", line.full_text())

    def test_hidden_when_the_dump_has_no_reading(self):
        with pantalla.Ventana(foto(EQUIPOS / "i5-10400")[0]) as window:
            page = self.page(window)
            self.assertFalse(page.kernel._values[_("sys.kernel.tainted")].isVisible())
            self.assertFalse(page.boot._values[_("sys.boot.cmdline")].isVisible())


if __name__ == "__main__":
    unittest.main()
