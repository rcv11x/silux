"""«Cargar el módulo» in Sensors asks first, with its own warning.

It went straight to the password window. It is not the warning for giving
permissions, which says that Silux only reads: this changes the system, so it
says which module, that it stays for every boot, and how to undo it.
"""

import unittest
from unittest import mock

from silux.i18n import _
from silux.privileged import cargar_modulo
from tests import pantalla, qt
from tests.test_equipos import EQUIPOS, foto

try:
    from PySide6.QtWidgets import QApplication
except ImportError:                                    # pragma: no cover
    QApplication = None


class TestTheFileItNames(unittest.TestCase):

    def test_is_the_one_root_writes(self):
        from silux.ui.dialogs import MODULES_FILE
        self.assertEqual(MODULES_FILE, str(cargar_modulo.TARGET))


@unittest.skipIf(QApplication is None, "no PySide6")
class TestOnTheSensorsPage(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.app = qt.app()
        cls.photo = foto(EQUIPOS / "5800x3d")[0]

    def _button(self, window):
        from silux.ui.widgets import Notice
        window.select_section("Sensores")
        for _turn in range(4):
            self.app.processEvents()
        page = window.stack.currentWidget()
        buttons = [n.action_button for n in page.findChildren(Notice)
                   if n.action_button is not None
                   and n.action_button.text() == _("sensors.driver.button")]
        self.assertTrue(buttons, "the dump has no module to load")
        return page, buttons[0]

    def test_it_asks_first_and_says_what_changes(self):
        from silux.ui.dialogs import MODULES_FILE
        with pantalla.Ventana(self.photo) as window:
            page, button = self._button(window)
            module = next(h.module for h in self.photo.driver_hints
                          if cargar_modulo.is_allowed(h.module))
            with mock.patch.object(page, "_cargar_driver") as load:
                button.click()
                self.app.processEvents()
                dialog = page._module_dialog
                self.assertTrue(dialog.isVisible())
                text = " ".join(p.text() for p in dialog.paragraphs)
                for piece in (module, MODULES_FILE, f"modprobe -r {module}"):
                    with self.subTest(piece=piece):
                        self.assertIn(piece, text)
                self.assertTrue(dialog.cancel_button.isDefault())
                load.assert_not_called()
                dialog.cancel_button.click()
                load.assert_not_called()
                button.click()
                page._module_dialog.load_button.click()
                load.assert_called_once()
                self.assertEqual(load.call_args.args[0], module)


if __name__ == "__main__":
    unittest.main()
