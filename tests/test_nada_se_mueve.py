"""Una muestra nueva con los mismos campos no mueve nada de la página.

En Gráficos, cada segundo la página parpadeaba y se movía todo: las filas
de las frecuencias del silicio se enseñaban y se volvían a esconder en la
misma muestra, y el área de desplazamiento medía la página en ese instante.
Una vez sí y otra no, la página quedaba 23 píxeles más alta, y con ella
desplazada hacia abajo saltaba entera. En Almacenamiento, cada candado se
quitaba y se volvía a poner. Ninguno cambiaba nada que se leyera: era la
página deshaciendo y rehaciendo su propio estado.

Aquí se monta cada página de cada equipo volcado, se le dan dos muestras
seguidas del mismo volcado —los mismos campos— y se mira, de cada widget a
la vista, su sitio y su tamaño, y si alguno se enseña o se esconde.
"""

import unittest

from tests import pantalla, qt
from tests.test_equipos import volcados

try:
    from PySide6.QtWidgets import QApplication
except ImportError:                                    # pragma: no cover
    QApplication = None


def dos_fotos(carpeta):
    """La segunda y la tercera muestra de un volcado: con los ritmos (que
    salen de dos lecturas) ya en las dos, así que con los mismos campos."""
    from silux.collector import Collector
    from tests.test_volcar_equipo import _herramienta

    with _herramienta().montado(carpeta):
        recolector = Collector()
        try:
            recolector.snapshot()
            return recolector.snapshot(), recolector.snapshot()
        finally:
            recolector.close()


def asentar() -> None:
    """Hasta que Qt haya recolocado todo lo que se le pidió."""
    for _vez in range(6):
        QApplication.processEvents()


def _nombre(widget, pagina) -> str:
    partes = []
    while widget is not None and widget is not pagina and len(partes) < 3:
        partes.append(type(widget).__name__ + (f"#{widget.objectName()}"
                                               if widget.objectName() else ""))
        widget = widget.parentWidget()
    return "<".join(partes)


def geometria(pagina) -> dict:
    """De cada widget a la vista: su sitio en la página y su tamaño."""
    import shiboken6
    from PySide6.QtCore import QPoint
    from PySide6.QtWidgets import QWidget

    vistos = {}
    for widget in pagina.findChildren(QWidget):
        if widget.isVisible():
            sitio = widget.mapTo(pagina, QPoint(0, 0))
            vistos[shiboken6.getCppPointer(widget)[0]] = (
                _nombre(widget, pagina),
                (sitio.x(), sitio.y(), widget.width(), widget.height()))
    return vistos


def diferencias(antes: dict, despues: dict) -> list[str]:
    salida = []
    for clave in sorted(set(antes) | set(despues), key=str):
        if clave not in despues:
            salida.append(f"se va {antes[clave][0]} {antes[clave][1]}")
        elif clave not in antes:
            salida.append(f"aparece {despues[clave][0]} {despues[clave][1]}")
        elif antes[clave][1] != despues[clave][1]:
            salida.append(f"se mueve {antes[clave][0]} {antes[clave][1]} → {despues[clave][1]}")
    return salida


class Visibilidad:
    """Los Show y Hide de los widgets de una página mientras dura el bloque.

    Aunque al final quede todo igual, enseñar y volver a esconder en la misma
    muestra recoloca la página entera: es lo que la hacía parpadear.
    """

    def __init__(self, pagina):
        from PySide6.QtCore import QObject

        espia = self

        class _Filtro(QObject):
            def eventFilter(self, objeto, evento):  # noqa: N802
                espia._mirar(objeto, evento)
                return False

        self._pagina = pagina
        self._filtro = _Filtro()
        self.cambios: list[str] = []

    def _mirar(self, objeto, evento) -> None:
        from PySide6.QtCore import QEvent
        from PySide6.QtWidgets import QWidget

        tipo = evento.type()
        if tipo not in (QEvent.Type.Show, QEvent.Type.Hide) or not isinstance(objeto, QWidget):
            return
        if objeto is self._pagina or not self._pagina.isAncestorOf(objeto):
            return
        texto = objeto.text() if hasattr(objeto, "text") and callable(objeto.text) else ""
        self.cambios.append(f"{'Show' if tipo == QEvent.Type.Show else 'Hide'} "
                            f"{_nombre(objeto, self._pagina)} {str(texto)[:30]!r}")

    def __enter__(self):
        QApplication.instance().installEventFilter(self._filtro)
        return self

    def __exit__(self, *_error):
        QApplication.instance().removeEventFilter(self._filtro)


@unittest.skipIf(QApplication is None, "sin PySide6")
class TestNadaSeMueve(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        qt.app()
        cls.fotos = {carpeta.name: dos_fotos(carpeta) for carpeta in volcados()}

    def _sin_moverse(self, nombre: str, fotos: dict, como: str) -> None:
        primera, segunda = fotos[nombre]
        with pantalla.Ventana(primera) as ventana:
            for seccion, pagina in pantalla.recorrer(ventana):
                with self.subTest(equipo=nombre, pagina=seccion, muestras=como):
                    ventana._on_sample(primera)
                    asentar()
                    antes = geometria(pagina)
                    with Visibilidad(pagina) as visibilidad:
                        ventana._on_sample(segunda)
                        asentar()
                    self.assertEqual(visibilidad.cambios, [])
                    self.assertEqual(diferencias(antes, geometria(pagina)), [])

    def test_cada_pagina_de_cada_equipo(self):
        self.assertTrue(self.fotos)
        for nombre in self.fotos:
            self._sin_moverse(nombre, self.fotos, "iguales")

    def test_la_guarda_ve_una_fila_que_se_enseña_y_se_esconde(self):
        # Si no cazara una página que se deshace y se rehace, no vigilaría
        # nada: una fila de Gráficos que se enseña y se vuelve a esconder en
        # cada muestra, como hacían las del silicio.
        from silux.i18n import _
        from silux.ui.pages.graphics import GpuSection

        nombre = next(n for n, (f, _s) in self.fotos.items() if f.gpus)
        primera, segunda = self.fotos[nombre]
        with pantalla.Ventana(primera) as ventana:
            ventana.select_section("nav.graphics")
            asentar()
            pagina = ventana.stack.currentWidget()
            seccion = pagina.findChildren(GpuSection)[0]
            original = seccion._apply_no_aplica

            def con_parpadeo(gpu):
                original(gpu)
                seccion.clocks.set_visible(_("gpu.clock.memory"), False)
                seccion.clocks.set_visible(_("gpu.clock.memory"), True)

            seccion._apply_no_aplica = con_parpadeo
            ventana._on_sample(primera)
            asentar()
            with Visibilidad(pagina) as visibilidad:
                ventana._on_sample(segunda)
                asentar()
        self.assertTrue(visibilidad.cambios)


if __name__ == "__main__":
    unittest.main()
