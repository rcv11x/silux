"""«Accesos directos» in Settings: one switch each, and an AppImage that stays put.

It was a badge, a switch for the desktop and a separate «Añadir» button, with
the AppImage's path in the main text. Now each shortcut has its switch and is
applied at once; the path goes small. And a shortcut to an AppImage in
Downloads breaks the day that folder is emptied, so turning one on offers to
move Silux to ~/AppImages first and open it again from there.
"""

import errno
import os
import pathlib
import subprocess
import tempfile
import unittest
from typing import Optional
from unittest import mock

from silux import desktop
from silux.i18n import _
from tests import qt

try:
    from PySide6.QtWidgets import QApplication
except ImportError:                                    # pragma: no cover
    QApplication = None


class _FakeHome(unittest.TestCase):
    """HOME, the data folder and the desktop folder, all in a temporary one."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.home = pathlib.Path(tmp.name)
        (self.home / "config").mkdir()
        (self.home / "config" / "user-dirs.dirs").write_text(
            f'XDG_DESKTOP_DIR="{self.home}/Escritorio"\n')
        for patch in (mock.patch.dict(os.environ, {"HOME": str(self.home),
                                                   "XDG_DATA_HOME": str(self.home / "data"),
                                                   "XDG_CONFIG_HOME": str(self.home / "config")}),
                      mock.patch.object(desktop, "refresh_caches")):
            patch.start()
            self.addCleanup(patch.stop)

    def appimage(self, folder="Descargas", name="silux-x86_64.AppImage", content=b"silux"):
        path = self.home / folder / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        path.chmod(0o755)
        return path


@unittest.skipIf(QApplication is None, "no PySide6")
class TestEachShortcutOnItsOwn(_FakeHome):

    def setUp(self):
        super().setUp()
        qt.app()
        self.launcher = desktop.current_launcher({"APPIMAGE": str(self.appimage())})

    def _there(self):
        return (desktop.desktop_path().exists(), desktop.shortcut_path().exists(),
                desktop.scalable_path().exists())

    def test_menu_desktop_both_and_none(self):
        for menu, on_desktop in ((True, False), (False, True), (True, True), (False, False)):
            with self.subTest(menu=menu, desktop=on_desktop):
                desktop.set_shortcuts(menu, on_desktop, self.launcher)
                self.assertEqual(self._there(), (menu, on_desktop, menu or on_desktop))


class TestMovingToAppImages(_FakeHome):

    def test_moved_when_it_can_be(self):
        old = self.appimage()
        moved = desktop.move_to_appimages(old)
        self.assertEqual(moved.path, self.home / "AppImages" / old.name)
        self.assertFalse(moved.copied)
        self.assertFalse(old.exists())
        self.assertTrue(os.access(moved.path, os.X_OK))

    def test_never_over_another_file(self):
        other = self.appimage("AppImages", content=b"another one")
        moved = desktop.move_to_appimages(self.appimage())
        self.assertEqual(moved.path.name, "silux-x86_64-2.AppImage")
        self.assertEqual(other.read_bytes(), b"another one")

    def test_copied_across_file_systems(self):
        old = self.appimage()
        with mock.patch.object(desktop.os, "link", side_effect=OSError(errno.EXDEV, "cross-device")):
            moved = desktop.move_to_appimages(old)
        self.assertTrue(moved.copied)
        self.assertTrue(old.exists())
        self.assertEqual(moved.path.read_bytes(), b"silux")
        self.assertTrue(os.access(moved.path, os.X_OK))

    def test_a_link_in_appimages_is_in_appimages(self):
        target = self.appimage()
        (self.home / "AppImages").mkdir()
        link = self.home / "AppImages" / "silux.AppImage"
        link.symlink_to(target)
        self.assertTrue(desktop.in_appimages(link))
        self.assertFalse(desktop.in_appimages(target))

    def test_copied_when_the_old_one_cannot_be_removed(self):
        old = self.appimage()
        with mock.patch.object(pathlib.Path, "unlink", side_effect=PermissionError):
            moved = desktop.move_to_appimages(old)
        self.assertTrue(moved.copied)
        self.assertTrue(old.exists())


class TestOpeningItAgain(unittest.TestCase):

    def test_without_what_this_mount_added(self):
        env = {"APPDIR": "/tmp/.mount_abc", "APPIMAGE": "/home/u/Descargas/s.AppImage",
               "ARGV0": "s", "OWD": "/home/u", "PYTHONHOME": "/tmp/.mount_abc/usr",
               "PYTHONPATH": "/tmp/.mount_abc/usr/lib/python:/home/u/mine",
               "LD_LIBRARY_PATH": "/tmp/.mount_abc/usr/lib", "LANG": "es_ES.UTF-8"}
        clean = desktop.relaunch_environment(env)
        self.assertEqual(clean, {"PYTHONPATH": "/home/u/mine", "LANG": "es_ES.UTF-8"})


@unittest.skipIf(QApplication is None, "no PySide6")
class TestInSettings(_FakeHome):

    def setUp(self):
        super().setUp()
        self.app = qt.app()
        from tests.test_ajustes import _pagina
        self.page = _pagina(self.app)
        self.addCleanup(self.page.deleteLater)

    def _wait(self):
        if self.page._tarea is not None:
            self.page._tarea.wait()
        for _turn in range(5):
            self.app.processEvents()

    def test_two_switches_applied_at_once_and_no_add_button(self):
        self.assertEqual(self.page.desktop_state, "missing")
        self.assertFalse(hasattr(self.page, "desktop_add"))
        self.page.menu_switch.setChecked(True)
        self._wait()
        self.assertTrue(desktop.desktop_path("silux-dev").is_file())
        self.page.desktop_shortcut.setChecked(True)
        self._wait()
        self.assertTrue(desktop.shortcut_path("silux-dev").is_file())
        self.page.menu_switch.setChecked(False)
        self._wait()
        self.assertFalse(desktop.desktop_path("silux-dev").exists())
        self.assertTrue(desktop.shortcut_path("silux-dev").is_file())
        self.assertTrue(desktop.scalable_path("silux-dev").is_file())

    def _as_appimage(self):
        path = self.appimage()
        patch = mock.patch.dict(os.environ, {"APPIMAGE": str(path)})
        patch.start()
        self.addCleanup(patch.stop)
        self.page.refresh_desktop()
        return path

    def test_the_path_goes_small_not_in_the_main_text(self):
        path = self._as_appimage()
        self.assertEqual(self.page.desktop_path.text(),
                         _("settings.shortcut.path").format(ruta="~/Descargas/" + path.name))
        self.assertEqual(self.page.desktop_path.toolTip(), str(path))
        self.assertNotIn("Descargas", self.page.menu_row.explicacion.text())

    def test_move_and_add_moves_points_there_and_opens_it_again(self):
        old = self._as_appimage()
        opened = []
        self.page.relaunch_requested.connect(opened.append)
        with mock.patch.object(type(self.page), "_preguntar_mover", return_value=True):
            self.page.menu_switch.setChecked(True)
            self._wait()
        new = self.home / "AppImages" / old.name
        self.assertTrue(new.is_file())
        self.assertFalse(old.exists())
        self.assertIn(f"Exec={new}", desktop.desktop_path().read_text())
        self.assertEqual(opened, [str(new)])

    def test_left_where_it_is_it_says_the_shortcut_is_fragile(self):
        old = self._as_appimage()
        with mock.patch.object(type(self.page), "_preguntar_mover", return_value=False):
            self.page.menu_switch.setChecked(True)
            self._wait()
        self.assertIn(f"Exec={old}", desktop.desktop_path().read_text())
        self.assertTrue(self.page.desktop_fragile.isVisibleTo(self.page))

    def test_no_fragile_warning_when_they_open_another_copy(self):
        self._as_appimage()
        other = self.appimage("AppImages")
        desktop.set_shortcuts(True, False, desktop.current_launcher({"APPIMAGE": str(other)}))
        self.page.refresh_desktop()
        self.assertEqual(self.page.desktop_state, "elsewhere")
        self.assertFalse(self.page.desktop_fragile.isVisibleTo(self.page))

    def test_closing_the_question_changes_nothing(self):
        self._as_appimage()
        with mock.patch.object(type(self.page), "_preguntar_mover", return_value=None):
            self.page.menu_switch.setChecked(True)
            self._wait()
        self.assertFalse(desktop.desktop_path().exists())
        self.assertFalse(self.page.menu_switch.isChecked())

    def test_moved_it_opens_again_even_if_a_shortcut_failed(self):
        old = self._as_appimage()
        opened = []
        self.page.relaunch_requested.connect(opened.append)
        with mock.patch.object(type(self.page), "_preguntar_mover", return_value=True), \
             mock.patch.object(desktop, "set_shortcuts", side_effect=OSError("disk full")):
            self.page.menu_switch.setChecked(True)
            self._wait()
        self.assertEqual(opened, [str(self.home / "AppImages" / old.name)])

    def test_pointing_them_here_asks_too(self):
        old = self._as_appimage()
        other = desktop.current_launcher({"APPIMAGE": str(self.appimage("Otra"))})
        desktop.set_shortcuts(True, False, other)
        self.page.refresh_desktop()
        self.assertEqual(self.page.desktop_state, "elsewhere")
        with mock.patch.object(type(self.page), "_preguntar_mover", return_value=False) as ask:
            self.page.desktop_fix.click()
            self._wait()
        ask.assert_called_once()
        self.assertIn(f"Exec={old}", desktop.desktop_path().read_text())

    def test_already_in_appimages_it_does_not_ask(self):
        path = self.appimage("AppImages")
        with mock.patch.dict(os.environ, {"APPIMAGE": str(path)}), \
             mock.patch.object(type(self.page), "_preguntar_mover") as ask:
            self.page.refresh_desktop()
            self.page.menu_switch.setChecked(True)
            self._wait()
            ask.assert_not_called()
            self.assertFalse(self.page.desktop_fragile.isVisibleTo(self.page))


# What Plasma's menu editor writes when an entry is deleted: the .desktop
# stays, and its name goes into an <Exclude> of its submenu.
KMENUEDIT = """<!DOCTYPE Menu PUBLIC '-//freedesktop//DTD Menu 1.0//EN' 'http://www.freedesktop.org/standards/menu-spec/1.0/menu.dtd'>
<Menu>
 <Menu>
  <Name>System</Name>
  <Layout>
   <Merge type="menus"/>
   <Merge type="files"/>
  </Layout>
  <Exclude>
   <Filename>silux.desktop</Filename>
   <Filename>other.desktop</Filename>
  </Exclude>
 </Menu>
 <Menu>
  <Name>Utilities</Name>
  <Exclude>
   <Filename>silux.desktop</Filename>
  </Exclude>
 </Menu>
</Menu>
"""


def _glib_try_exec(entry: pathlib.Path) -> Optional[str]:
    """TryExec as GLib reads it (GNOME's menus), or what went wrong reading
    it. None only when GLib cannot be imported here."""
    python = "/usr/bin/python3"
    probe = "import gi; gi.require_version('Gio', '2.0'); from gi.repository import Gio"
    if not os.path.exists(python) or subprocess.run(
            [python, "-I", "-c", probe], capture_output=True, timeout=30).returncode != 0:
        return None
    code = (probe + "\nimport sys\napp = Gio.DesktopAppInfo.new_from_filename(sys.argv[1])\n"
            "try:\n    print(app.get_string('TryExec') if app else 'not loaded')\n"
            "except Exception as error:\n    print('error:', error)")
    result = subprocess.run([python, "-I", "-c", code, str(entry)],
                            capture_output=True, text=True, timeout=30)
    return result.stdout.rstrip("\n") or result.stderr


@unittest.skipIf(QApplication is None, "no PySide6")
class TestTryExec(_FakeHome):

    def setUp(self):
        super().setUp()
        qt.app()
        # A space and a backslash: the value is read back with its escapes.
        self.path = self.appimage(folder="Mis cosas/a\\b", name="Silux x86_64.AppImage")
        desktop.set_shortcuts(True, False, desktop.current_launcher({"APPIMAGE": str(self.path)}))

    def test_it_names_the_appimage(self):
        escaped = str(self.path).replace("\\", "\\\\")
        self.assertIn(f"TryExec={escaped}\n", desktop.desktop_path().read_text())

    def test_a_real_reader_gets_the_appimage_back(self):
        read = _glib_try_exec(desktop.desktop_path())
        if read is None:
            self.skipTest("no GLib from Python here")
        self.assertEqual(read, str(self.path))


@unittest.skipIf(QApplication is None, "no PySide6")
class TestDeletedByHand(_FakeHome):
    """Deleted from a terminal or the menu: not added, and nothing else said."""

    def setUp(self):
        super().setUp()
        self.app = qt.app()
        self.path = self.appimage("AppImages")
        patch = mock.patch.dict(os.environ, {"APPIMAGE": str(self.path)})
        patch.start()
        self.addCleanup(patch.stop)
        desktop.set_shortcuts(True, True)
        from tests.test_ajustes import _pagina
        self.page = _pagina(self.app)
        self.addCleanup(self.page.deleteLater)

    def _quietly_off(self, switch):
        self.page.refresh_desktop()
        self.assertFalse(switch.isChecked())
        self.assertEqual(self.page._error_del_escritorio, "")
        self.assertFalse(self.page._arreglo.isVisibleTo(self.page))
        self.assertFalse(self.page.desktop_fragile.isVisibleTo(self.page))

    def test_from_a_terminal(self):
        desktop.desktop_path().unlink()
        self._quietly_off(self.page.menu_switch)
        self.assertEqual(self.page.menu_row.explicacion.text(), _("settings.shortcut.menu.help"))
        desktop.shortcut_path().unlink()
        self._quietly_off(self.page.desktop_shortcut)

    def test_hidden_with_nodisplay(self):
        entry = desktop.desktop_path()
        entry.write_text(entry.read_text() + "NoDisplay=true\n")
        self._quietly_off(self.page.menu_switch)

    def _wait(self):
        self.page.wait_for_tasks()
        for _turn in range(5):
            self.app.processEvents()

    def test_from_the_kde_menu_and_back(self):
        menu = desktop.kde_menu_file()
        menu.parent.mkdir(parents=True)
        menu.write_text(KMENUEDIT)
        self._quietly_off(self.page.menu_switch)
        self.page.menu_switch.setChecked(True)
        self._wait()
        self.assertTrue(self.page.menu_switch.isChecked())
        self.assertTrue(desktop.in_menu())
        text = menu.read_text()
        self.assertNotIn("<Filename>silux.desktop</Filename>", text)
        self.assertIn("<Filename>other.desktop</Filename>", text)
        self.assertNotIn("<Name>Utilities</Name>\n  <Exclude>", text)
        self.assertTrue(text.startswith("<!DOCTYPE Menu"))

    def test_moved_to_another_kde_submenu_is_still_there(self):
        menu = desktop.kde_menu_file()
        menu.parent.mkdir(parents=True)
        menu.write_text(KMENUEDIT.replace(" <Menu>\n  <Name>Utilities</Name>\n  <Exclude>",
                                          " <Menu>\n  <Name>Utilities</Name>\n  <Include>")
                        .replace("</Filename>\n  </Exclude>\n </Menu>\n</Menu>",
                                 "</Filename>\n  </Include>\n </Menu>\n</Menu>"))
        self.assertTrue(desktop.in_menu())


@unittest.skipIf(QApplication is None, "no PySide6")
class TestTheQuestion(unittest.TestCase):

    def test_two_answers_in_spanish_and_closing_is_neither(self):
        from PySide6.QtCore import Qt
        from PySide6.QtTest import QTest
        from PySide6.QtWidgets import QPushButton

        from silux.ui.dialogs import MoveAppImageDialog

        qt.app()
        dialog = MoveAppImageDialog(str(pathlib.Path.home() / "Descargas" / "s.AppImage"))
        self.addCleanup(dialog.deleteLater)
        texts = [b.text() for b in dialog.findChildren(QPushButton)]
        self.assertEqual(sorted(texts), sorted([_("settings.shortcut.move.yes"),
                                                _("settings.shortcut.move.no")]))
        self.assertTrue(dialog.move_button.isDefault())
        self.assertIn("<nobr>~/AppImages</nobr>", dialog.paragraphs[0].text())
        dialog.show()
        QTest.keyClick(dialog, Qt.Key.Key_Escape)
        self.assertIsNone(dialog.choice)
        dialog.leave_button.click()
        self.assertEqual(dialog.choice, "leave")


@unittest.skipIf(QApplication is None, "no PySide6")
class TestTheWindowOpensItAgain(_FakeHome):

    def test_saved_and_closed_before_the_new_one_opens(self):
        from silux import settings
        from silux.ui.app import MainWindow

        app = qt.app()
        window = MainWindow(settings.Preferences().normalized())
        window.show()
        app.processEvents()
        saved = settings.config_path()
        seen = {}

        def popen(args, **kwargs):
            seen["visible"] = window.isVisible()
            seen["saved"] = saved.is_file()
            seen["args"], seen["env"] = args, kwargs["env"]
            seen["session"] = kwargs.get("start_new_session")
            return mock.Mock()

        env = {**os.environ, "APPIMAGE": "/old/silux.AppImage", "APPDIR": "/tmp/.mount_x",
               "PYTHONHOME": "/tmp/.mount_x/usr"}
        with mock.patch.dict(os.environ, env, clear=True), \
             mock.patch("silux.ui.app.subprocess.Popen", side_effect=popen):
            window.settings_page.relaunch_requested.emit(str(self.home / "AppImages" / "s"))
        self.assertFalse(seen["visible"])
        self.assertTrue(seen["saved"])
        self.assertEqual(seen["args"], [str(self.home / "AppImages" / "s")])
        self.assertTrue(seen["session"])
        for variable in ("APPIMAGE", "APPDIR", "PYTHONHOME"):
            self.assertNotIn(variable, seen["env"])


if __name__ == "__main__":
    unittest.main()
