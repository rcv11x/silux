"""A table a little too wide narrows the air between its columns before it
hides any behind a scroll bar, and takes the air back when there is room."""

import unittest

from tests.qt import app


class TestTheGapsGiveWayFirst(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from silux.ui import theme

        cls.app = app()
        theme.apply(cls.app, "dark", "normal")

    def table(self):
        from silux.ui.widgets import Table

        table = Table(["Fecha", "Uno", "Dos", "Tres", "Cuatro"],
                      numeric=(False, True, True, True, True))
        self.addCleanup(table.deleteLater)
        table.set_rows([["25/11/2026 10:41", "6 592", "3 946", "63.3", "62.9 °C"]])
        table.show()
        return table

    def settle(self, table, width: int) -> None:
        table.resize(width, 200)
        for _turn in range(4):
            self.app.processEvents()

    def test_a_few_pixels_short_and_nothing_is_hidden(self):
        from silux.ui import theme
        from silux.ui.widgets import Table

        table = self.table()
        self.settle(table, 2000)
        wide = theme.METRICS.grid_hspace
        self.assertEqual(table._grid.horizontalSpacing(), wide)
        needed = sum(max(width, table._ancho_de_cabecera(column))
                     for column, width in enumerate(table._anchos))
        # Room for the columns and the narrowest gaps, not for the usual ones.
        self.settle(table, needed + 4 * Table.MIN_COLUMN_GAP + 4)
        self.assertEqual(table.horizontalScrollBar().maximum(), 0)
        self.assertLess(table._grid.horizontalSpacing(), wide)
        self.assertGreaterEqual(table._grid.horizontalSpacing(), Table.MIN_COLUMN_GAP)
        self.settle(table, 2000)
        self.assertEqual(table._grid.horizontalSpacing(), wide)


if __name__ == "__main__":
    unittest.main()
