"""The «copied» toast leaves the value it confirms in view and the next
click alone."""

import unittest

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QLabel

from silux.ui import theme
from silux.ui.widgets import Table
from tests import qt


class TestCopiedToast(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = qt.app()
        theme.apply(cls.app, "dark", "normal")

    def setUp(self):
        self.table = Table(("Fecha", "RAM", "Lectura"), numeric=(False, True, True))
        self.addCleanup(self.table.deleteLater)
        self.table.set_rows([("24/11/2026 15:08", "77.4 ns", "43.9 GB/s")])
        self.table.resize(700, 200)
        self.table.show()
        for _turn in range(3):
            self.app.processEvents()

    def click(self, label):
        label.mouseReleaseEvent(QMouseEvent(
            QMouseEvent.Type.MouseButtonRelease, QPoint(2, 2), Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier))
        toasts = [w for w in self.table.window().findChildren(QLabel)
                  if w.objectName() == "Toast"]
        self.assertTrue(toasts)
        return toasts[-1]

    def text_rect(self, label):
        window = label.window()
        corner = label.mapTo(window, QPoint(0, 0))
        width = label.fontMetrics().horizontalAdvance(label.text())
        left = corner.x() + (label.width() - width
                             if label.alignment() & Qt.AlignmentFlag.AlignRight else 0)
        return left, left + width, corner.y(), corner.y() + label.height()

    def overlaps(self, toast, label) -> bool:
        left, right, top, bottom = self.text_rect(label)
        return (toast.x() < right and left < toast.x() + toast.width()
                and toast.y() < bottom and top < toast.y() + toast.height())

    def test_it_never_covers_a_figure_in_a_right_aligned_column(self):
        """It went to the right of where a left-aligned text would end: in
        a column of figures, on top of the figure."""
        cell = self.table._cells[0][1]
        self.assertFalse(self.overlaps(self.click(cell), cell))

    def test_nor_a_text_on_the_left(self):
        cell = self.table._cells[0][0]
        self.assertFalse(self.overlaps(self.click(cell), cell))

    def test_clicks_go_through_it(self):
        """For its 1.4 s it swallowed the click meant for what was under it."""
        toast = self.click(self.table._cells[0][2])
        self.assertTrue(toast.testAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents))

    def test_smaller_than_the_text_it_confirms(self):
        cell = self.table._cells[0][1]
        toast = self.click(cell)
        self.assertLess(toast.font().pointSizeF(), cell.font().pointSizeF())


if __name__ == "__main__":
    unittest.main()
