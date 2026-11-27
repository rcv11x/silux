"""«Show all instructions» redoes CPU's instruction list and nothing else:
rebuilding every page took a while and sent Settings back to its top."""

import unittest

from tests import qt
from tests.test_settings_feedback import _window

class TestAllInstructions(unittest.TestCase):
    def test_only_the_cpu_list_is_redone(self):
        from tests.test_equipos import EQUIPOS, shared_snapshot

        window = _window()
        self.addCleanup(window.close)
        window._on_sample(shared_snapshot(EQUIPOS / "5800x3d"))
        window.select_section("Ajustes")
        qt.app().processEvents()
        pages = (window.settings_page, window.cpu_page, window.home_page)
        scroll = window.settings_page.verticalScrollBar()
        scroll.setValue(scroll.maximum() // 2)
        position = scroll.value()
        section = next(iter(window.cpu_page._sections.values()))
        shown = len(section.chips._chips)

        window.settings_page.all_features.click()
        qt.app().processEvents()
        self.assertEqual((window.settings_page, window.cpu_page, window.home_page), pages)
        self.assertEqual(scroll.value(), position)
        window.select_section("CPU")
        qt.app().processEvents()
        self.assertGreater(len(section.chips._chips), shown)


if __name__ == "__main__":
    unittest.main()
