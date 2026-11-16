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

_app = None


def app():
    global _app
    from PySide6.QtWidgets import QApplication

    if _app is None:
        actual = QApplication.instance()
        if actual is not None and not isinstance(actual, QApplication):
            raise RuntimeError(
                f"ya hay una {type(actual).__name__} en este proceso y con ella no "
                "se puede crear un widget: quien la crea tiene que pedir antes "
                "tests.qt.app()")
        _app = actual or QApplication([])
    return _app
