"""The desktop and the graphical session, also without logind.

Under runit or sysvinit nobody sets XDG's variables; what the display
manager sets and the display itself still say it. What stays unknown hides
and is said, never «?» nor a dash.
"""

import unittest

from silux.i18n import _
from silux.providers.system import desktop, session_type
from tests import pantalla, qt
from tests.test_absent_rows import _dashed
from tests.test_equipos import EQUIPOS, foto, shared_snapshot, volcados


class TestTheFallbacks(unittest.TestCase):

    def test_desktop(self):
        self.assertEqual(desktop({"XDG_CURRENT_DESKTOP": "XFCE"}), "XFCE")
        self.assertEqual(desktop({"DESKTOP_SESSION": "icewm-session"}), "icewm-session")
        self.assertEqual(desktop({"GDMSESSION": "/usr/share/xsessions/plasma"}), "plasma")
        self.assertIsNone(desktop({"XDG_CURRENT_DESKTOP": "", "SHELL": "/bin/bash"}))

    def test_the_desktop_in_xdgs_list(self):
        # From two reports: Debian's Cinnamon and Ubuntu's GNOME, as they set
        # the variable.
        self.assertEqual(desktop({"XDG_CURRENT_DESKTOP": "X-Cinnamon",
                                  "DESKTOP_SESSION": "cinnamon"}), "Cinnamon")
        self.assertEqual(desktop({"XDG_CURRENT_DESKTOP": "ubuntu:GNOME"}), "GNOME")
        # A desktop built on another goes by its own name.
        self.assertEqual(desktop({"XDG_CURRENT_DESKTOP": "Budgie:GNOME"}), "Budgie")
        self.assertEqual(desktop({"XDG_CURRENT_DESKTOP": "sway"}), "sway")

    def test_session(self):
        self.assertEqual(session_type({"XDG_SESSION_TYPE": "wayland"}), "wayland")
        self.assertEqual(session_type({"DISPLAY": ":0"}), "x11")
        self.assertEqual(session_type({"WAYLAND_DISPLAY": "wayland-0", "DISPLAY": ":0"}),
                         "wayland")
        self.assertIsNone(session_type({}))

    def test_a_tty_with_a_display(self):
        # From a report: Debian 13's Cinnamon, with the session «tty» while
        # Silux ran on display :0.
        self.assertEqual(session_type({"XDG_SESSION_TYPE": "tty", "DISPLAY": ":0",
                                       "WAYLAND_DISPLAY": None}), "x11")
        self.assertEqual(session_type({"XDG_SESSION_TYPE": "tty", "DISPLAY": ":0",
                                       "WAYLAND_DISPLAY": "wayland-0"}), "wayland")
        # Without one, it is a console (our QEMU dump).
        self.assertEqual(session_type({"XDG_SESSION_TYPE": "tty"}), "tty")


class TestOnTheSystemPage(unittest.TestCase):

    def test_no_dash_and_the_foot_says_why(self):
        qt.app()
        for folder in volcados():
            snapshot = shared_snapshot(folder)
            with self.subTest(folder.name), pantalla.Ventana(snapshot) as window:
                window.select_section("Sistema")
                page = window.stack.currentWidget()
                self.assertEqual(_dashed(page.kernel, ("sys.kernel.desktop",
                                                       "sys.field.session")), [])
                unknown = not (snapshot.system.desktop and snapshot.system.session_type)
                self.assertEqual(not page.kernel_pie.isHidden(), unknown)

    def test_cinnamon_without_its_prefix(self):
        qt.app()
        snapshot = shared_snapshot(EQUIPOS / "celeron-g3900")
        with pantalla.Ventana(snapshot) as window:
            window.select_section("Sistema")
            page = window.stack.currentWidget()
            self.assertEqual(page.kernel.value_label(_("sys.kernel.desktop")).full_text(),
                             "Cinnamon")


if __name__ == "__main__":
    unittest.main()
