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
        _use_ci_font(_app)
    return _app


# The CI runner draws with DejaVu Sans, wider than the Noto Sans or Cantarell
# of many desktops: pages that fit here ran off the edge there, and figures
# that fit in one line wrapped. The suite uses it wherever it's installed, so
# a run here measures what the CI measures.
CI_FONT = "DejaVu Sans"


def _use_ci_font(application) -> None:
    from PySide6.QtGui import QFont, QFontDatabase

    if CI_FONT in QFontDatabase.families():
        font = QFont(application.font())
        font.setFamily(CI_FONT)
        application.setFont(font)
