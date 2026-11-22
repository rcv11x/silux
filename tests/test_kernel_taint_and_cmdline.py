"""System: whether the kernel is tainted, and its command line.

Two cheap readings without permissions. The command line names the
machine's disks (root=UUID=…), its encrypted volumes and sometimes its name
or address: that is hidden when it is read, so neither the window nor a
report nor a dump holds it.
"""

import glob
import re
import unittest
from unittest import mock

from silux import privacidad, render
from silux.i18n import _
from tests import pantalla, qt
from tests.arbol import arbol
from tests.test_equipos import EQUIPOS, foto, volcados

try:
    from PySide6.QtWidgets import QApplication
except ImportError:                                    # pragma: no cover
    QApplication = None

def _load(language):
    import json
    import pathlib
    from silux import i18n
    return json.loads((pathlib.Path(i18n.__file__).parent / "db" / "lang"
                       / f"{language}.json").read_text(encoding="utf-8"))


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

    def test_p_is_the_license_not_proprietary(self):
        # The kernel sets P for any module whose license isn't GPL-compatible:
        # ZFS, under the CDDL, is free software.
        snapshot = foto(EQUIPOS / "celeron-g3900")[0]
        self.assertIn(("zfs", "PO"), snapshot.system.tainting_modules)
        text = render.tainted(snapshot.system.tainted, snapshot.system.tainting_modules)
        self.assertIn(_("sys.taint.0") + " (zfs)", text)
        for language in ("es", "en"):
            with self.subTest(language):
                reason = _load(language)["sys.taint.0"].lower()
                self.assertNotIn("propietario", reason)
                self.assertNotIn("proprietary", reason)
                self.assertIn("gpl", reason)


MODULES = {"/proc/meminfo": "MemTotal: 1 kB\n",
           "/proc/sys/kernel/tainted": "12288\n",
           "/sys/module/nvidia/taint": "POE\n",
           "/sys/module/vboxdrv/taint": "OE\n",
           "/sys/module/ext4/taint": "\n"}


def _state(files=MODULES):
    from silux.providers.base import Draft
    from silux.providers.system import SystemState
    with arbol(files):
        draft = Draft()
        SystemState().collect(draft)
    return draft.system


class TestWhichModuleTaintsIt(unittest.TestCase):

    def test_the_modules_are_read_with_their_letters(self):
        self.assertEqual(_state().tainting_modules, (("nvidia", "POE"), ("vboxdrv", "OE")))

    def test_each_reason_names_its_modules(self):
        system = _state()
        self.assertEqual(render.tainted(system.tainted, system.tainting_modules),
                         f"{_('sys.taint.12')} (nvidia, vboxdrv) · {_('sys.taint.13')} (nvidia, vboxdrv)")

    def test_a_warning_is_no_module_and_nothing_is_read(self):
        files = {**MODULES, "/proc/sys/kernel/tainted": "512\n"}
        with mock.patch("glob.glob", wraps=glob.glob) as listed:
            system = _state(files)
        self.assertEqual(system.tainting_modules, ())
        self.assertFalse([c for c in listed.call_args_list if "module" in str(c)])

    def test_read_again_only_when_something_changes(self):
        from silux.providers.base import Draft
        from silux.providers.system import SystemState
        provider = SystemState()
        with arbol(MODULES), mock.patch("glob.glob", wraps=glob.glob) as listed:
            for _sample in range(3):
                provider.collect(Draft())
            self.assertEqual(len([c for c in listed.call_args_list if "module" in str(c)]), 1)


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

    def test_the_modules_are_named_on_the_page(self):
        import dataclasses
        photo = foto(EQUIPOS / "5800x3d")[0]
        photo = dataclasses.replace(photo, system=dataclasses.replace(
            photo.system, tainting_modules=_state().tainting_modules))
        with pantalla.Ventana(photo) as window:
            tainted = self.page(window).kernel._values[_("sys.kernel.tainted")]
            self.assertIn("(nvidia, vboxdrv)", tainted.full_text())

    def test_hidden_when_the_dump_has_no_reading(self):
        with pantalla.Ventana(foto(EQUIPOS / "i5-10400")[0]) as window:
            page = self.page(window)
            self.assertFalse(page.kernel._values[_("sys.kernel.tainted")].isVisible())
            self.assertFalse(page.boot._values[_("sys.boot.cmdline")].isVisible())


if __name__ == "__main__":
    unittest.main()
