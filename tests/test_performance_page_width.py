"""The Performance page stays inside its window after a CPU test.

A text wider than the readable column used to start a loop: the column's
side margins counted towards the page's minimum width, so the page grew, the
margins grew with it, and every sample pushed the content further right
until the tab was blank. The CPU test's score note was such a text.
"""

import unittest
from unittest import mock

from silux import benchmark, history, score
from tests import pantalla
from tests.qt import app
from tests.test_equipos import EQUIPOS, shared_snapshot


def settle(application, turns: int = 6) -> None:
    for _turn in range(turns):
        application.processEvents()


class TestAfterTheQuickTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from silux.ui import theme

        cls.app = app()
        theme.apply(cls.app, "dark", "normal")
        cls.snapshot = shared_snapshot(EQUIPOS / "i5-10400")

    def setUp(self):
        # The run is saved: the next test of this process would find it.
        history.clear()
        self.addCleanup(history.clear)

    def test_the_page_never_grows_past_its_view(self):
        from silux import render

        # A processor the score table does not know, as almost all are.
        cpu = render.cpu_short_name(self.snapshot.cpu.types[0].brand)
        self.assertIsNone(score.compare(cpu, 1000))
        with pantalla.Ventana(self.snapshot) as window:
            window.resize(1100, 720)
            window.select_section("Rendimiento")
            page = window.benchmarks_page
            tab = page.cpu_tab
            settle(self.app)
            # The real run, shortened: each measurement is the same work for
            # less time.
            with mock.patch.object(benchmark, "QUICK_SECONDS", 0.05):
                tab.quick_button.click()
                while tab.running:
                    self.app.processEvents()
            settle(self.app)
            self.assertTrue(tab.score_card.isVisibleTo(tab))
            self.assertTrue(tab.score_range.text())
            for _sample in range(4):
                window._on_sample(self.snapshot)
                settle(self.app)
            root = tab.widget()
            self.assertLessEqual(root.width(), tab.viewport().width())
            self.assertLessEqual(root.side(), root.content_width())
            # The tab buttons follow the column, inside the window too.
            self.assertLessEqual(page.buttons["cpu"].mapTo(window, page.buttons["cpu"].rect()
                                                           .topLeft()).x(), window.width())


class TestReadableRoot(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from silux.ui import theme

        cls.app = app()
        theme.apply(cls.app, "dark", "normal")

    def area(self, text: str):
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import QLabel, QScrollArea

        from silux.ui.widgets import ReadableRoot

        area = QScrollArea()
        area.setWidgetResizable(True)
        area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        root = ReadableRoot()
        area.setWidget(root)
        label = QLabel(text)
        root.column.addWidget(label)
        area.resize(800, 400)
        area.show()
        self.addCleanup(area.deleteLater)
        return area, root, label

    def test_content_wider_than_the_column_does_not_feed_the_margins(self):
        area, root, label = self.area("")
        label.setText("x " * (root.content_width() // 4))
        widths = []
        for _turn in range(5):
            # Another layout pass with nothing changed, as a sample brings.
            label.updateGeometry()
            settle(self.app)
            widths.append(root.width())
        self.assertEqual(len(set(widths)), 1, widths)
        self.assertLessEqual(root.width(), label.minimumSizeHint().width()
                             + 2 * root.column.contentsMargins().left() + 2)

    def test_a_wide_window_still_centres_the_column(self):
        area, root, _label = self.area("short")
        area.resize(root.content_width() + 600, 400)
        settle(self.app)
        self.assertGreaterEqual(root.side(), 290)
