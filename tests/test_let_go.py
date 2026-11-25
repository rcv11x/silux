"""A widget taken out of a window on screen never comes up as a window of
its own.

One added to a window on screen has its showing queued for the next turn
of the event loop. Taken out before that turn, without a parent, it showed
as a window: the Disk tab left «It is a hard disk» floating, one per time
the notes were said twice in a row.
"""

import unittest

from tests.qt import app

try:
    from PySide6.QtWidgets import QApplication, QLabel, QVBoxLayout, QWidget
except ImportError:                                    # pragma: no cover
    QApplication = None


def loose(kind: str) -> list:
    """The windows of their own of that kind on screen."""
    QApplication.processEvents()
    return [w for w in QApplication.topLevelWidgets()
            if w.isVisible() and w.metaObject().className() == kind]


@unittest.skipIf(QApplication is None, "sin PySide6")
class TestLetGo(unittest.TestCase):
    def setUp(self):
        app()
        self.window = QWidget()
        self.addCleanup(self.window.close)
        self.layout = QVBoxLayout(self.window)
        self.window.show()
        QApplication.processEvents()

    def test_a_layout_emptied_in_the_same_turn_leaves_nothing_on_screen(self):
        from silux.ui.widgets import clear_layout

        for _turn in range(3):
            self.layout.addWidget(QLabel("added"))
            clear_layout(self.layout)
        self.assertEqual([w.text() for w in loose("QLabel")], [])

    def test_a_table_whose_rows_change_twice_leaves_no_cell_on_screen(self):
        from silux.ui.widgets import Table

        table = Table(["A", "B"])
        self.layout.addWidget(table)
        QApplication.processEvents()
        table.set_rows([("1", "2")])
        table.set_rows([("1", "2"), ("3", "4")])
        self.assertEqual(loose("ElidingLabel"), [])


class TestTheDiskTabsNotes(unittest.TestCase):
    def test_notes_said_twice_in_a_row_leave_none_floating(self):
        from tests.test_disktest_page import TabCase

        class Case(TabCase):
            DUMP = "athlon-3000g"

            def runTest(self):
                pass

        Case.setUpClass()
        case = Case()
        case.setUp()
        self.addCleanup(case.doCleanups)
        tab = case.tab()
        tab._describe()
        tab._describe()
        self.assertEqual(loose("Notice"), [])
