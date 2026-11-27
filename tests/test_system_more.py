"""What Sistema says besides the kernel: packages and the desktop's version
from each manager's own database, the access control module, time zone and
language, failed services and the kernel's errors since boot, grouped. The
anonymous report and a dump leave out the city, a unit's instance and any
MAC a kernel message names."""

import dataclasses
import os
import pathlib
import tempfile
import unittest
from unittest import mock

from silux import privacidad, render
from silux.i18n import _
from silux.providers import system
from tests import pantalla, qt
from tests.test_equipos import EQUIPOS, shared_snapshot

try:
    from PySide6.QtWidgets import QApplication
except ImportError:                                    # pragma: no cover
    QApplication = None

# As `journalctl --dmesg --boot --priority=err --output=cat` printed them on
# a Ryzen 7 5800X3D with a Radeon RX 9070 XT.
JOURNAL = [
    "virt/tdx: TDX not supported by the host platform",
    "usb 5-4.3: device descriptor read/64, error -32",
    "usb 1-5: 1:1: cannot get freq at ep 0x82",
    "usb 1-5: 1:2: cannot get freq at ep 0x82",
    "usb 1-5: 2:1: cannot get freq at ep 0x2",
    "logitech-djreceiver 0003:046D:C54D.000C: logi_dj_recv_query_paired_devices error:-32",
    "logitech-djreceiver 0003:046D:C54D.000C: logi_dj_recv_query_paired_devices error:-32",
]

# dpkg's status file, two installed and one removed.
DPKG = """Package: plasma-workspace
Status: install ok installed
Version: 4:5.27.5-2+deb12u2

Package: libfoo1
Status: install ok installed
Version: 1.2.3+dfsg-1

Package: oldthing
Status: deinstall ok config-files
Version: 0.9-1
"""


class TestTheSources(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = pathlib.Path(tmp.name)

    def paths(self, **changes):
        patcher = mock.patch.multiple(system, **changes)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_pacman_folders_and_the_plasma_version(self):
        local = self.root / "local"
        for entry in ("plasma-workspace-6.8.3-1.1", "linux-7.3.6-3", "lib32-glibc-2:2.42-1"):
            (local / entry).mkdir(parents=True)
        (local / "ALPM_DB_VERSION").write_text("9\n")
        flatpak = self.root / "flatpak"
        for app in ("org.mozilla.firefox", "com.valvesoftware.Steam"):
            (flatpak / app).mkdir(parents=True)
        self.paths(PACMAN_LOCAL=str(local), DPKG_STATUS=str(self.root / "none"),
                   FLATPAK_APPS=(str(flatpak),),
                   SNAPS=str(self.root / "none"))
        found = system.installed_software("KDE")
        self.assertEqual(found, {"packages": [["pacman", 3], ["flatpak", 2]],
                                 "desktop_version": "6.8.3"})

    def test_dpkg_counts_what_is_installed_and_strips_epoch_and_revision(self):
        status = self.root / "status"
        status.write_text(DPKG)
        snaps = self.root / "snaps"
        snaps.mkdir()
        for snap in ("core22_1663.snap", "core22_1722.snap", "firefox_5091.snap"):
            (snaps / snap).write_text("")
        self.paths(PACMAN_LOCAL=str(self.root / "none"), DPKG_STATUS=str(status),
                   FLATPAK_APPS=(),
                   SNAPS=str(snaps))
        found = system.installed_software("KDE")
        # Two revisions of one snap are one snap.
        self.assertEqual(found["packages"], [["dpkg", 2], ["snap", 2]])
        self.assertEqual(found["desktop_version"], "5.27.5")

    def test_access_control_from_the_active_modules(self):
        lsm = self.root / "lsm"
        enforce = self.root / "enforce"
        self.paths(LSM=str(lsm), SELINUX_ENFORCE=str(enforce))
        lsm.write_text("capability,landlock,lockdown,yama,bpf\n")
        self.assertEqual(system.access_control(), ["", None])
        lsm.write_text("lockdown,capability,landlock,yama,apparmor,bpf\n")
        self.assertEqual(system.access_control(), ["apparmor", None])
        lsm.write_text("lockdown,capability,yama,selinux,bpf\n")
        enforce.write_text("1")
        self.assertEqual(system.access_control(), ["selinux", "enforcing"])
        lsm.unlink()
        self.assertIsNone(system.access_control())

    def test_the_same_fault_repeated_is_one_line(self):
        groups = system.group_errors(JOURNAL)
        self.assertEqual([times for _text, times in groups], [1, 1, 3, 2])
        self.assertEqual(groups[2][0], "usb 1-5: 1:1: cannot get freq at ep 0x82")

    def test_journal_and_systemd_asked_every_half_minute(self):
        from silux.providers.base import Draft
        provider = system.SystemHealth()
        with mock.patch.object(system, "failed_units", return_value=["x.service"]) as units, \
             mock.patch.object(system, "kernel_error_lines", return_value=JOURNAL) as lines, \
             mock.patch.object(system.time, "monotonic", side_effect=[100.0, 110.0, 131.0]):
            for _sample in range(3):
                provider.collect(draft := Draft())
        self.assertEqual(units.call_count, 2)
        self.assertEqual(lines.call_count, 2)
        self.assertEqual(draft.system.failed_units, ("x.service",))
        self.assertEqual(len(draft.system.kernel_errors), 4)


class TestTheTexts(unittest.TestCase):
    def test_render(self):
        self.assertEqual(render.packages((("pacman", 1837), ("flatpak", 11))),
                         f"{render.thousands(1837)} (pacman) · 11 (Flatpak)")
        self.assertEqual(render.desktop("KDE", "6.8.3"), "KDE Plasma 6.8.3")
        self.assertEqual(render.desktop("GNOME", None), "GNOME")
        self.assertEqual(render.access_control(("", None)), _("sys.access.none"))
        self.assertEqual(render.access_control(("selinux", "enforcing")),
                         _("sys.access.enforcing").format(name="SELinux"))
        self.assertIsNone(render.failed_units(None))
        self.assertEqual(render.failed_units(()), _("sys.failed.none"))
        self.assertEqual(render.kernel_errors(system.group_errors(JOURNAL)),
                         _("sys.kerr.kinds").format(n=7, kinds=4))
        self.assertEqual(render.kernel_errors(((JOURNAL[0], 1),)),
                         render.counted("sys.kerr.count", 1))


def with_health(snapshot, **values):
    return dataclasses.replace(snapshot, system=dataclasses.replace(snapshot.system, **values))


class TestPrivacy(unittest.TestCase):
    # A router's address, from the documentation range like every MAC here.
    LINE = "wlp4s0: associated with 00:00:5e:00:53:42 (try 1/3)"
    # In two pieces: whole, the source would read as an email address.
    UNIT = "wg-quick@" + "casa.service"

    def test_the_anonymous_report_leaves_out_city_instance_and_router(self):
        snapshot = with_health(
            shared_snapshot(EQUIPOS / "5800x3d"), timezone="Europe/Madrid",
            failed_units=(self.UNIT, "cups.service"),
            kernel_errors=((self.LINE, 2),))
        system_ = privacidad.anonymize(snapshot).system
        self.assertIsNone(system_.timezone)
        self.assertEqual(system_.failed_units, ("wg-quick@….service", "cups.service"))
        self.assertEqual(system_.kernel_errors,
                         ((f"wlp4s0: associated with {privacidad.MAC} (try 1/3)", 2),))

    def test_and_so_does_a_dump(self):
        from silux import volcado
        with tempfile.TemporaryDirectory() as target:
            cleaner = volcado._Anonymizer(pathlib.Path(target), {
                "plataforma": {"zona_horaria": "Europe/Madrid"},
                "systemd": {"fallidos": [self.UNIT]},
                "kernel": {"errores": [self.LINE]}})
            clean = cleaner.clean_recording()
        self.assertNotIn("zona_horaria", clean["plataforma"])
        self.assertEqual(clean["systemd"]["fallidos"], ["wg-quick@….service"])
        self.assertNotIn("00:00:5e:00:53:42", clean["kernel"]["errores"][0])


@unittest.skipIf(QApplication is None, "no PySide6")
class TestOnThePage(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        qt.app()

    def page_of(self, snapshot):
        from silux.ui.pages.system import SystemPage
        window = pantalla.Ventana(snapshot)
        self.addCleanup(window.__exit__, None, None, None)
        window.__enter__().select_section("nav.system")
        QApplication.processEvents()
        page = window.ventana.stack.currentWidget()
        self.assertIsInstance(page, SystemPage)
        return page

    def test_every_new_row_shows(self):
        snapshot = with_health(
            shared_snapshot(EQUIPOS / "5800x3d"), desktop="KDE", desktop_version="6.8.3",
            packages=(("pacman", 1837), ("flatpak", 11)), access_control=("", None),
            timezone="Europe/Madrid", locale="es_ES.UTF-8", failed_units=(),
            kernel_errors=system.group_errors(JOURNAL))
        page = self.page_of(snapshot)
        values = {**{k: v.full_text() for k, v in page.os._values.items() if v.isVisible()},
                  **{k: v.full_text() for k, v in page.kernel._values.items() if v.isVisible()},
                  **{k: v.full_text() for k, v in page.activity._values.items()
                     if v.isVisible()}}
        self.assertEqual(values[_("sys.os.packages")], render.packages(snapshot.system.packages))
        self.assertEqual(values[_("sys.os.timezone")], "Europe/Madrid")
        self.assertEqual(values[_("sys.os.locale")], "es_ES.UTF-8")
        self.assertEqual(values[_("sys.kernel.desktop")], "KDE Plasma 6.8.3")
        self.assertEqual(values[_("sys.kernel.access")], _("sys.access.none"))
        self.assertEqual(values[_("sys.act.failed")], _("sys.failed.none"))
        self.assertIn(_("sys.act.load"), values)
        self.assertTrue(page.kernel_errors_card.isVisible())
        # The most repeated first.
        self.assertEqual(page.kernel_errors._cells[0][0].full_text(),
                         "usb 1-5: 1:1: cannot get freq at ep 0x82")

    def test_what_couldnt_be_read_is_not_a_row(self):
        page = self.page_of(shared_snapshot(EQUIPOS / "5800x3d"))
        for grid, key in ((page.os, "sys.os.packages"), (page.os, "sys.os.timezone"),
                          (page.kernel, "sys.kernel.access"), (page.activity, "sys.act.failed"),
                          (page.activity, "sys.act.kernelerrors")):
            with self.subTest(key=key):
                self.assertFalse(grid._values[_(key)].isVisible())
        self.assertFalse(page.kernel_errors_card.isVisible())

    def test_no_errors_is_said(self):
        page = self.page_of(with_health(shared_snapshot(EQUIPOS / "5800x3d"), kernel_errors=()))
        self.assertEqual(page.activity._values[_("sys.act.kernelerrors")].full_text(),
                         _("sys.kerr.none"))
        self.assertFalse(page.kernel_errors_card.isVisible())


if __name__ == "__main__":
    unittest.main()
