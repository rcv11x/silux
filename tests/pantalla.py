"""Lo que se lee en la ventana, página a página.

Para los tests que vigilan toda la interfaz y no una celda: que no llegue a
la pantalla un relleno del firmware, una clave sin traducir o un «None».
Recoge el texto de las etiquetas, los botones, las listas desplegables y las
filas de los árboles. Lo que un widget pinta a mano con `QPainter` —la cifra
de una gráfica, la leyenda de una barra— no sale de aquí.
"""

import os
import tempfile
from unittest import mock


def textos_de(widget) -> list[str]:
    from PySide6.QtWidgets import (QAbstractButton, QComboBox, QLabel, QLineEdit,
                                   QTreeWidget, QTreeWidgetItemIterator)
    from silux.ui.widgets import ElidingLabel

    vistos: list[str] = []
    for etiqueta in widget.findChildren(QLabel):
        # El texto entero, no el recortado con puntos suspensivos.
        vistos.append(etiqueta.full_text() if isinstance(etiqueta, ElidingLabel)
                      else etiqueta.text())
    for boton in widget.findChildren(QAbstractButton):
        vistos.append(boton.text())
    for campo in widget.findChildren(QLineEdit):
        vistos.append(campo.text())
    for lista in widget.findChildren(QComboBox):
        vistos.extend(lista.itemText(i) for i in range(lista.count()))
    for arbol in widget.findChildren(QTreeWidget):
        fila = QTreeWidgetItemIterator(arbol)
        while fila.value() is not None:
            vistos.extend(fila.value().text(c) for c in range(arbol.columnCount()))
            fila += 1
    return [t for t in vistos if t and t.strip()]


def recorrer(ventana):
    """Cada sección que este equipo enseña, abierta, con su página.

    Abierta de verdad: hay páginas que no se rellenan hasta que se visitan.
    """
    from PySide6.QtWidgets import QApplication
    from silux.ui.app import SECTIONS

    for clave, activa in SECTIONS:
        if not activa or not ventana.select_section(clave):
            continue
        QApplication.processEvents()
        yield clave, ventana.stack.currentWidget()


class Ventana:
    """La ventana de verdad con una foto puesta, para leer lo que enseña."""

    def __init__(self, foto):
        self._foto = foto

    def __enter__(self):
        from silux.settings import Preferences
        from silux.ui.app import MainWindow

        self._tmp = tempfile.TemporaryDirectory()
        self._entorno = mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": self._tmp.name})
        self._entorno.start()
        self.ventana = MainWindow(Preferences().normalized())
        self.ventana.show()
        self.ventana._on_sample(self._foto)
        return self.ventana

    def __exit__(self, *_exc):
        self.ventana.close()
        self._entorno.stop()
        self._tmp.cleanup()
