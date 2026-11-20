"""Boot and firmware lines from the first reports.

Gentoo with OpenRC read «Init: init» and «los da systemd, y no ha
contestado» on a system without systemd; a QEMU guest without a known boot
loader read «Gestor de arranque no lo publica», the generic word standing in
for a name; and SeaBIOS's «0.0» was shown as a «Revisión SMBIOS» that is
really the BIOS's release.
"""

import dataclasses
import unittest
from unittest import mock

from silux.i18n import _
from silux.providers import system as system_provider
from tests import qt
from tests.test_equipos import EQUIPOS, foto

try:
    from PySide6.QtWidgets import QApplication
except ImportError:                                    # pragma: no cover
    QApplication = None


class TestWithoutSystemd(unittest.TestCase):
    """A machine whose PID 1 is not systemd, as the kernel shows it.

    The first OpenRC test replaced `sysroot.ruta` with one that always gave
    a Path; the real one gives text for text, `.is_dir()` failed and a
    tester's Gentoo lost its distribution, kernel and desktop («?»). Here
    the machine is a dump mounted for real, without a systemd: no readable
    /proc/1/exe (it is root's), and PID 1's name in /proc/1/comm.
    """

    def _system(self, pid1, runlevels=False):
        from silux import volcado
        from silux.collector import Collector
        with volcado.montado(EQUIPOS / "qemu-kvm") as raiz:
            exe = raiz / "proc/1/exe"
            if exe.is_symlink() or exe.exists():
                exe.unlink()
            (raiz / "proc/1").mkdir(parents=True, exist_ok=True)
            (raiz / "proc/1/comm").write_text(pid1 + "\n")
            if runlevels:
                (raiz / "etc/runlevels/default").mkdir(parents=True)
            recolector = Collector()
            try:
                return recolector.snapshot()
            finally:
                recolector.close()

    def test_each_init_and_the_rest_of_the_system(self):
        for pid1, runlevels, init in (("init", True, "openrc"), ("openrc-init", False, "openrc"),
                                      ("init", False, "init"), ("runit", False, "runit"),
                                      ("s6-svscan", False, "s6-svscan")):
            with self.subTest(pid1=pid1, runlevels=runlevels):
                foto = self._system(pid1, runlevels)
                self.assertEqual(foto.system.init, init)
                self.assertTrue(foto.system.distribution)
                self.assertTrue(foto.system.kernel)
                self.assertEqual([n for n in foto.notes if n.path.startswith("system")], [])

    def test_a_datum_that_fails_takes_nothing_else(self):
        from silux.model import Need
        with mock.patch.object(system_provider.SystemIdentity, "_init_system",
                               side_effect=AttributeError("'str' object has no attribute 'is_dir'")):
            foto = self._system("init")
        self.assertIsNone(foto.system.init)
        self.assertTrue(foto.system.distribution)
        self.assertEqual([(n.path, n.need) for n in foto.notes if n.path.startswith("system")],
                         [("system.init", Need.ERROR)])


@unittest.skipIf(QApplication is None, "sin PySide6")
class TestThePages(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.app = qt.app()

    def _system(self, f):
        from silux.settings import Preferences
        from silux.ui import theme
        from silux.ui.pages.system import SystemPage

        pagina = SystemPage(theme.palette_for(self.app, "dark"), Preferences().normalized())
        self.addCleanup(pagina.deleteLater)
        pagina.apply(f)
        return pagina.extra_pie.text()

    def test_without_a_loaders_name_no_generic_word_stands_for_one(self):
        f = foto(EQUIPOS / "qemu-kvm")[0]
        self.assertIsNone(f.system.boot.loader)
        pie = self._system(f)
        self.assertNotIn(_("sys.boot.loader") + " no lo publica", pie)
        self.assertIn(_("sys.boot.nofirmware.unknown"), pie)

    def test_on_openrc_systemd_did_not_fail_to_answer(self):
        f = foto(EQUIPOS / "qemu-kvm")[0]
        sin_systemd = dataclasses.replace(f, system=dataclasses.replace(
            f.system, init="openrc", boot=dataclasses.replace(
                f.system.boot, kernel_s=None, initrd_s=None, userspace_s=None)))
        pie = self._system(sin_systemd)
        self.assertNotIn(_("sys.boot.nosystemd"), pie)
        self.assertIn("openrc", pie)

    def test_seabios_zero_release_is_not_shown(self):
        from silux.settings import Preferences
        from silux.ui import theme
        from silux.ui.pages.board import BoardPage

        f = foto(EQUIPOS / "qemu-kvm")[0]
        self.assertEqual(f.board.bios_release, "0.0")
        pagina = BoardPage(theme.palette_for(self.app, "dark"), Preferences())
        self.addCleanup(pagina.deleteLater)
        pagina.apply(f)
        grid = pagina.firmware
        self.assertFalse(grid._values[_("board.field.smbios")].isVisibleTo(grid))
