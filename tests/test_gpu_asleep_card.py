"""A card asleep, and the card beside it while the libraries wait.

A GeForce asleep under Optimus showed 35 rows of dashes under the heading
«This machine doesn't expose it»; the integrated one beside it said
«Neither Vulkan nor OpenGL use this card» when they hadn't been asked, so
as not to wake the other. Asleep, the card keeps what is known without
waking it and says why the rest waits; and what wasn't asked isn't said
to be absent.
"""

import unittest

from silux import render
from silux.i18n import _
from tests import pantalla, qt
from tests.test_equipos import foto, shared_snapshot, volcados

try:
    from PySide6.QtWidgets import QApplication, QLabel
except ImportError:                                    # pragma: no cover
    QApplication = None


def _sections(window):
    from silux.ui.pages.graphics import GpuSection
    from tests.test_interface_language import visible_texts

    window.select_section("Gráficos")
    for _turn in range(3):
        QApplication.processEvents()
    page = window.stack.currentWidget()
    return [(section, visible_texts(section))
            for section in page.findChildren(GpuSection) if section.isVisible()]


@unittest.skipIf(QApplication is None, "no PySide6")
class TestEveryDump(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        qt.app()
        cls.snapshots = {folder.name: shared_snapshot(folder) for folder in volcados()}

    def test_some_dump_has_a_card_asleep(self):
        self.assertTrue([name for name, s in self.snapshots.items()
                         if any(g.suspended for g in s.gpus)])

    def test_asleep_without_dashes_and_saying_so(self):
        from silux.ui.widgets import Notice

        for name, snapshot in self.snapshots.items():
            asleep = [g for g in snapshot.gpus if g.suspended]
            if not asleep:
                continue
            with self.subTest(dump=name), pantalla.Ventana(snapshot) as window:
                sections = _sections(window)
                for gpu in asleep:
                    section, texts = next((s, t) for s, t in sections
                                          if render.gpu_name(gpu) in t)
                    self.assertNotIn(render.DASH, texts)
                    headings = [n.findChild(QLabel, "NoticeTitle").text()
                                for n in section.findChildren(Notice) if n.isVisible()]
                    self.assertIn(_("prov.drm.asleep.title"), headings)
                    self.assertNotIn(_("note.hardware"), headings)
                    # What is known without waking it stays, and the cards
                    # that would only hold dashes wait for it to wake.
                    self.assertIn(gpu.driver, texts)
                    for card in ("gpu.card.vram", "gpu.card.clocks", "gpu.card.sensors",
                                 "gpu.card.apis"):
                        self.assertNotIn(_(card), texts)

    def test_libraries_not_asked_are_not_said_absent(self):
        for name, snapshot in self.snapshots.items():
            if not any(n.key == "prov.apis.asleep" for n in snapshot.notes):
                continue
            with self.subTest(dump=name), pantalla.Ventana(snapshot) as window:
                for section, texts in _sections(window):
                    joined = " ".join(texts)
                    self.assertNotIn(_("gpu.apis.none"), texts)
                    self.assertNotIn(_("gpu.na.noapi").split("{")[0], joined)
                awake = [t for s, t in _sections(window)
                         if _("gpu.apis.notasked") in t]
                self.assertTrue(awake)


if __name__ == "__main__":
    unittest.main()
