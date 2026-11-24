"""La QApplication de la suite: una por proceso, y guardada.

`QApplication.instance() or QApplication([])` sin guardar el resultado crea
una que se destruye en el acto, y el siguiente widget aborta el proceso
(«Fatal Python error: Aborted»). En serie no se veía porque algún módulo
anterior dejaba otra viva; en paralelo el orden cambia y salta. Todos la
piden aquí, y aquí se queda viva hasta que acaba el proceso.

Tiene que ser una `QApplication`. Si en el proceso ya hay otra que no lo es
—`tools/install_desktop.py` dibuja los iconos con una `QGuiApplication`—,
`instance()` la devuelve igual y el primer widget aborta. Solo cabe una por
proceso, así que no se puede cambiar por la buena: se dice aquí, y quien usa
algo que crea la suya pide antes esta (`test_desktop`).
"""

import atexit
import pathlib

_app = None


def _cerrar():
    """Borra las ventanas que quedaron vivas, mientras Python sigue entero.

    Con la aplicación guardada, la suite terminaba en verde y el proceso
    salía con una violación de segmento (código 139, a veces «corrupted
    double-linked list»): al desmontarse el intérprete, PySide recorre los
    objetos que le quedan para destruirlos, y entre las ventanas que los tests
    sueltan sin cerrar encuentra alguno ya liberado. La traza acaba en
    `PySide::destroyQCoreApplication`. Borradas aquí, una a una y con todo en
    su sitio, no queda nada que recorrer.

    `QApplication.shutdown()` no sirve para esto: hace ese mismo recorrido.
    """
    global _app
    if _app is None:
        return
    import gc

    import shiboken6
    from PySide6.QtWidgets import QApplication

    gc.collect()
    for ventana in QApplication.topLevelWidgets():
        if shiboken6.isValid(ventana):
            shiboken6.delete(ventana)
    _app = None


def app():
    global _app
    from PySide6.QtWidgets import QApplication

    if _app is None:
        atexit.register(_cerrar)
        actual = QApplication.instance()
        if actual is not None and not isinstance(actual, QApplication):
            raise RuntimeError(
                f"ya hay una {type(actual).__name__} en este proceso y con ella no "
                "se puede crear un widget: quien la crea tiene que pedir antes "
                "tests.qt.app()")
        _app = actual or QApplication([])
        _load_ci_font()
        reset_font()
        reset_theme()
    return _app


# The CI runner draws with DejaVu Sans, wider than the Noto Sans or Cantarell
# of many desktops: pages that fit here ran off the edge there, and figures
# that fit in one line wrapped. The suite uses it wherever it's installed, so
# a run here measures what the CI measures; and at Qt's size on a desktop
# that says none, the CI's, rather than this desktop's.
CI_FONT = "DejaVu Sans"
CI_FONT_POINTS = 9
# The same font, for the desktops that don't have it installed: without it
# the suite fell back to whatever they draw with, and what fit here broke
# the CI.
FONTS = pathlib.Path(__file__).parent / "fixtures" / "fonts"


def _load_ci_font() -> None:
    """Give Qt the suite's font where the system has none. Before any widget
    exists: one already built keeps the font it was laid out with."""
    from PySide6.QtGui import QFontDatabase

    if CI_FONT in QFontDatabase.families():
        return
    for font in sorted(FONTS.glob("*.ttf")):
        QFontDatabase.addApplicationFont(str(font))

# What a test finds when it starts: this font, and before each class what a
# new application has, no theme. A window doesn't apply the theme (the
# program's `main` does), so a test used to get whatever the test before it
# in the same process had left: a fault that showed alone hid in the suite.
# With both put back, a test sees in the suite what it sees alone; one that
# measures the theme applies the one it wants. `conftest.py` does it before
# every class and every test.
_default_family = None


def reset_font() -> None:
    """The application's font back to the suite's, if Qt is running."""
    global _default_family
    if _app is None:
        return
    from PySide6.QtGui import QFont, QFontDatabase

    if _default_family is None:
        _default_family = _app.font().family()
    family = CI_FONT if CI_FONT in QFontDatabase.families() else _default_family
    wanted = QFont(family, CI_FONT_POINTS)
    if _app.font() != wanted:
        _app.setFont(wanted)


def reset_theme() -> None:
    """No style sheet, Qt's own palette and the theme's default sizes, as a
    new application starts, if Qt is running."""
    if _app is None:
        return
    from silux.ui import theme

    theme.set_density("normal", "normal")
    # Only what differs: the windows the tests close stay alive until the
    # process ends, and a new style sheet or palette reaches every one.
    if _app.styleSheet():
        _app.setStyleSheet("")
    standard = _app.style().standardPalette()
    if _app.palette() != standard:
        _app.setPalette(standard)
