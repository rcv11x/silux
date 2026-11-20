"""Boot and firmware lines from the first reports.

Gentoo with OpenRC read «Init: init» and «los da systemd, y no ha
contestado» on a system without systemd; a QEMU guest without a known boot
loader read «Gestor de arranque no lo publica», the generic word standing in
for a name; and SeaBIOS's «0.0» was shown as a «Revisión SMBIOS» that is
really the BIOS's release.
"""

import dataclasses
import os
import pathlib
import tempfile
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


class TestOpenRc(unittest.TestCase):

    def test_sysvinits_init_with_openrc_is_openrc(self):
        with tempfile.TemporaryDirectory() as raiz:
            (pathlib.Path(raiz) / "run" / "openrc").mkdir(parents=True)
            ruta = lambda p: pathlib.Path(raiz) / str(p).lstrip("/")  # noqa: E731
            with mock.patch.object(system_provider.sysroot, "ruta", ruta), \
                    mock.patch.object(os, "readlink", return_value="/sbin/init"):
                self.assertEqual(system_provider.SystemIdentity._init_system(), "openrc")
            with mock.patch.object(system_provider.sysroot, "ruta",
                                   lambda p: pathlib.Path(raiz) / "nada"), \
                    mock.patch.object(os, "readlink", return_value="/sbin/init"):
                self.assertEqual(system_provider.SystemIdentity._init_system(), "init")


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
