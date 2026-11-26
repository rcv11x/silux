"""A page stays in its view, sample after sample.

The Performance page grew without end after a CPU test: content wider than
its readable column fed the column's margins, the page grew with them, and
every sample pushed it further right until it was blank. What a scroll area
holds has to be as wide as its view, and stay so as samples come in.
"""

SAMPLES = 4


def settle(application, turns: int = 4) -> None:
    for _turn in range(turns):
        application.processEvents()


def scroll_areas(page):
    """The page, or each tab of Performance, as the scroll area it is."""
    tabs = getattr(page, "_tabs", None)
    if tabs:
        for key, tab in tabs.items():
            page.select_tab(key)
            yield key, tab
    elif hasattr(page, "widget") and hasattr(page, "viewport"):
        yield "", page


def stays_in_view(test, window, area, snapshot, samples: int = SAMPLES) -> None:
    """`area`, a scroll area of `window`, as wide as its view however many
    samples of `snapshot` come."""
    from PySide6.QtWidgets import QApplication

    root = area.widget()
    if root is None:
        return
    widths = []
    for _sample in range(samples):
        window._on_sample(snapshot)
        settle(QApplication.instance())
        widths.append(root.width())
    test.assertEqual(len(set(widths)), 1, f"it grows with each sample: {widths}")
    test.assertLessEqual(root.width(), area.viewport().width())
