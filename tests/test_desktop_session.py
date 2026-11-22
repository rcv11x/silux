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
from tests.test_equipos import foto, volcados


class TestTheFallbacks(unittest.TestCase):

    def test_desktop(self):
        self.assertEqual(desktop({"XDG_CURRENT_DESKTOP": "XFCE"}), "XFCE")
        self.assertEqual(desktop({"DESKTOP_SESSION": "icewm-session"}), "icewm-session")
        self.assertEqual(desktop({"GDMSESSION": "/usr/share/xsessions/plasma"}), "plasma")
        self.assertIsNone(desktop({"XDG_CURRENT_DESKTOP": "", "SHELL": "/bin/bash"}))

    def test_session(self):
        self.assertEqual(session_type({"XDG_SESSION_TYPE": "wayland"}), "wayland")
        self.assertEqual(session_type({"DISPLAY": ":0"}), "x11")
        self.assertEqual(session_type({"WAYLAND_DISPLAY": "wayland-0", "DISPLAY": ":0"}),
                         "wayland")
        self.assertIsNone(session_type({}))


class TestOnTheSystemPage(unittest.TestCase):

    def test_no_dash_and_the_foot_says_why(self):
        qt.app()
        for folder in volcados():
            snapshot = foto(folder)[0]
            with self.subTest(folder.name), pantalla.Ventana(snapshot) as window:
                window.select_section("Sistema")
                page = window.stack.currentWidget()
                self.assertEqual(_dashed(page.kernel, ("sys.kernel.desktop",
                                                       "sys.field.session")), [])
                unknown = not (snapshot.system.desktop and snapshot.system.session_type)
                self.assertEqual(not page.kernel_pie.isHidden(), unknown)


if __name__ == "__main__":
    unittest.main()
