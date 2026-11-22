"""A notice's heading says what happens, not only the kind of thing.

A kernel below the minimum came out under «Kernel older than the datum»,
the heading of a datum newer than the kernel. A note can carry its own,
and every page and the report use it.
"""

import unittest

from silux import render, report
from silux.i18n import _
from silux.model import Need, Note
from tests import pantalla, qt
from tests.test_equipos import EQUIPOS, foto

try:
    from PySide6.QtWidgets import QApplication, QLabel
except ImportError:                                    # pragma: no cover
    QApplication = None

OLD_KERNEL = EQUIPOS / "core2-p8400"               # 5.10


class TestTheHeading(unittest.TestCase):

    def test_its_own_before_its_kinds(self):
        titles = {Need.KERNEL: "note.kernel"}
        self.assertEqual(render.note_title(Note("x", Need.KERNEL, "m"), titles),
                         _("note.kernel"))
        self.assertEqual(render.note_title(Note("x", Need.KERNEL, "m", title="Own"), titles),
                         "Own")

    def test_the_old_kernel_has_its_own(self):
        note = next(n for n in foto(OLD_KERNEL)[0].notes if n.key == "kernel.belowminimum")
        self.assertEqual(note.title, _("kernel.belowminimum.title").format(minimo="5.15"))
        self.assertIn("5.15", note.title)

    def test_in_the_report(self):
        title = _("kernel.belowminimum.title").format(minimo="5.15")
        line = next(x for x in report.build(foto(OLD_KERNEL)[0]).splitlines()
                    if x.startswith("- `system.kernel`"))
        self.assertIn(f"({title[:1].lower()}{title[1:]})", line)


@unittest.skipIf(QApplication is None, "no PySide6")
class TestOnThePage(unittest.TestCase):

    def test_the_system_page(self):
        from silux.ui.widgets import Notice

        app = qt.app()
        with pantalla.Ventana(foto(OLD_KERNEL)[0]) as window:
            window.select_section("Sistema")
            for _turn in range(3):
                app.processEvents()
            texts = [n.findChild(QLabel, "NoticeTitle").text()
                     for n in window.system_page.findChildren(Notice)]
        self.assertIn(_("kernel.belowminimum.title").format(minimo="5.15"), texts)
        self.assertNotIn(_("note.kernel"), texts)


if __name__ == "__main__":
    unittest.main()
