"""The full report has to read well as plain text.

Reports come from people who were asked to send one, and the author reads
them as Markdown. Notices printed as loose lines looked like part of the
section above them, the sensor values had no column names, hidden columns
leaked duplicated text, multi-line notes were glued into one paragraph and
the value of a combo box went missing.
"""

import re
import unittest

from silux.i18n import _
from tests import qt
from tests.test_equipos import EQUIPOS, foto, shared_snapshot

try:
    from PySide6.QtWidgets import QApplication
except ImportError:                                    # pragma: no cover
    QApplication = None


@unittest.skipIf(QApplication is None, "no PySide6")
class TestReadability(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        from silux.ui import full_report
        qt.app()
        snapshot = shared_snapshot(EQUIPOS / "5800x3d")
        cls.text = full_report.build(snapshot)

    def section(self, title):
        start = self.text.index(f"\n## {title}\n")
        end = self.text.find("\n## ", start + 1)
        return self.text[start:end if end > 0 else None]

    def test_notices_are_quotes_with_a_bold_title(self):
        memory = self.section(_("nav.memory"))
        self.assertIn(f"> **{_('note.hardware')}**", memory)
        # Not a loose line that reads as part of the text above.
        self.assertNotRegex(memory, rf"(?m)^{re.escape(_('note.hardware'))}$")

    def test_tree_columns_are_named(self):
        sensors = self.section(_("nav.sensors"))
        header = next(line for line in sensors.splitlines() if line.startswith("*"))
        for column in ("sensors.col.current", "sensors.col.min", "sensors.col.max",
                       "sensors.col.avg"):
            with self.subTest(column=column):
                self.assertIn(_(column), header)

    def test_hidden_columns_do_not_leak(self):
        devices = self.section(_("nav.devices"))
        for line in devices.splitlines():
            cells = [c.strip().lower() for c in line.lstrip(" -").split(" · ")]
            with self.subTest(line=line):
                self.assertEqual(len(cells), len(set(cells)))

    def test_multi_line_notes_keep_their_lines(self):
        sensors = self.section(_("nav.sensors"))
        notes = [line for line in sensors.splitlines() if line.startswith("it8688:")]
        self.assertGreaterEqual(len(notes), 2)

    def test_combo_boxes_say_their_value(self):
        performance = self.section(_("nav.benchmark"))
        self.assertNotIn(": ·", performance)


@unittest.skipIf(QApplication is None, "no PySide6")
class TestALockedFigure(unittest.TestCase):

    def test_says_so_once(self):
        # On screen the tile's detail is «with permissions» under a padlock;
        # written out, the padlock already says it. The processor's and the
        # graphics card's power need permissions on this laptop.
        from silux.ui import full_report

        qt.app()
        text = full_report.build(shared_snapshot(EQUIPOS / "i3-1115g4"))
        locked = f"({_('report.locked')})"
        lines = [line for line in text.splitlines() if line.endswith(locked)]
        self.assertTrue(lines)
        self.assertNotIn(f"{locked} ({_('lock.detail')})", text)


if __name__ == "__main__":
    unittest.main()
