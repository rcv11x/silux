"""Two notices that permissions are needed, one after the other, each with
its button, on a ThinkPad T480s's CPU page: RAPL's energy counter and the
core voltage. One notice says both, with one button."""

import unittest

from silux import render
from silux.model import Need
from tests import geometry, pantalla, qt
from tests.test_equipos import EQUIPOS, shared_snapshot


class TestOnePermissionNotice(unittest.TestCase):
    def test_the_t480s_cpu_page(self):
        from PySide6.QtWidgets import QLabel

        from silux.ui.widgets import Notice

        snapshot = shared_snapshot(EQUIPOS / "i5-8350u")
        root = [n for n in snapshot.notes_for("cpu") if n.need is Need.ROOT]
        self.assertGreaterEqual(len(root), 2)
        app = qt.app()
        with pantalla.Ventana(snapshot) as window:
            window.select_section("CPU")
            geometry.settle(app)
            page = window.stack.currentWidget()
            with_button = [n for n in page.findChildren(Notice)
                           if n.action_button is not None and n.isVisibleTo(page)]
            self.assertEqual(len(with_button), 1)
            texts = " ".join(label.text() for label in with_button[0].findChildren(QLabel))
        for note in root:
            self.assertIn(note.message, texts)
            self.assertIn(note.hint, texts)

    def test_one_alone_stays_as_it_was(self):
        notes = [n for n in shared_snapshot(EQUIPOS / "i5-8350u").notes_for("cpu")
                 if n.need is Need.ROOT][:1]
        self.assertEqual(render.one_permission_notice(notes), notes)


if __name__ == "__main__":
    unittest.main()
