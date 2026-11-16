"""La QApplication de la suite: una por proceso, y guardada.

`QApplication.instance() or QApplication([])` sin guardar el resultado crea
una que se destruye en el acto, y el siguiente widget aborta el proceso
(«Fatal Python error: Aborted»). En serie no se veía porque algún módulo
anterior dejaba otra viva; en paralelo el orden cambia y salta. Todos la
piden aquí, y aquí se queda viva hasta que acaba el proceso.
"""

_app = None


def app():
    global _app
    from PySide6.QtWidgets import QApplication

    if _app is None:
        _app = QApplication.instance() or QApplication([])
    return _app
