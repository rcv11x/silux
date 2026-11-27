"""Los iconos de la barra lateral y la marca del programa.

Un icono de trazo por sección, todos del mismo grosor y dibujados en la misma
caja de 20 unidades: trece nombres seguidos se leen, no se reconocen, y un
icono delante de cada uno deja encontrar la sección sin leer la lista.

Van escritos aquí como trazados SVG y se pintan con el color del tema, en vez
de viajar como trece archivos por color. Se leen con `QImageReader`, que usa
el complemento `qsvg` de `imageformats`, y así no hace falta el módulo
`QtSvg`, que no se empaqueta (`tools/build_appimage.py`, `QT_MODULES`). El
empaquetador se para si ese complemento no entra en el AppImage.
"""

from __future__ import annotations

import pathlib

from PySide6.QtCore import QBuffer, QByteArray, QSize
from PySide6.QtGui import QIcon, QImage, QImageReader, QPixmap

ASSETS = pathlib.Path(__file__).parent / "assets"

# Cada uno en una caja de 20 × 20, con trazo de 1,5 y extremos redondos. La
# clave es la de la sección (`SECTIONS` en `ui/app.py`).
NAV = {
    "nav.home": '<path d="M3 9.5 L10 3.5 L17 9.5 V16.5 H12.5 V12 H7.5 V16.5 H3 Z"/>',
    "nav.cpu": ('<rect x="5.5" y="5.5" width="9" height="9" rx="1.5"/>'
                '<path d="M8 2.5V5 M12 2.5V5 M8 15V17.5 M12 15V17.5 '
                'M2.5 8H5 M2.5 12H5 M15 8H17.5 M15 12H17.5"/>'),
    "nav.caches": ('<path d="M10 3 L17 6.5 L10 10 L3 6.5 Z M3 10 L10 13.5 L17 10 '
                   'M3 13.5 L10 17 L17 13.5"/>'),
    "nav.board": ('<rect x="3" y="3" width="14" height="14" rx="2"/>'
                  '<rect x="6" y="6" width="4.5" height="4.5"/>'
                  '<path d="M13 6.5H14.5 M13 9.5H14.5 M6 13.5H14"/>'),
    "nav.memory": ('<rect x="2.5" y="6" width="15" height="7" rx="1"/>'
                   '<path d="M5.5 13V15.5 M8.5 13V15.5 M11.5 13V15.5 M14.5 13V15.5 '
                   'M6 8.5V10.5 M10 8.5V10.5 M14 8.5V10.5"/>'),
    "nav.graphics": ('<rect x="2.5" y="4" width="15" height="9.5" rx="1.5"/>'
                     '<path d="M7 16.5H13 M10 13.5V16.5"/>'),
    "nav.storage": ('<ellipse cx="10" cy="5.5" rx="6" ry="2.5"/>'
                    '<path d="M4 5.5V14.5 C4 16 7 17 10 17 C13 17 16 16 16 14.5 V5.5 '
                    'M4 10 C4 11.5 7 12.5 10 12.5 C13 12.5 16 11.5 16 10"/>'),
    "nav.network": ('<circle cx="10" cy="10" r="7"/>'
                    '<path d="M3 10H17 M10 3 C7 5.5 7 14.5 10 17 M10 3 C13 5.5 13 14.5 10 17"/>'),
    # Un conector USB visto de frente: lo que se enchufa.
    "nav.devices": ('<path d="M10 2.5 V12 M7 5.5 L10 2.5 L13 5.5"/>'
                    '<rect x="6.5" y="12" width="7" height="5.5" rx="1"/>'
                    '<path d="M8.6 14.5H8.7 M11.3 14.5H11.4"/>'),
    "nav.battery": ('<rect x="2.5" y="6.5" width="13" height="7" rx="1.5"/>'
                    '<path d="M17.5 9V11 M5 9V11 M7.5 9V11"/>'),
    "nav.system": ('<rect x="2.5" y="4" width="15" height="12" rx="2"/>'
                   '<path d="M6 8.5 L8.5 10.5 L6 12.5 M10.5 12.5H14"/>'),
    "nav.benchmark": ('<path d="M3.5 14 A7 7 0 1 1 16.5 14 M10 13 L13.5 8"/>'
                      '<circle cx="10" cy="13" r="0.9"/>'),
    "nav.sensors": '<path d="M2.5 10H6 L8 5 L11.5 15 L13.5 10 H17.5"/>',
    "nav.settings": ('<path d="M3 6H10.5 M15.5 6H17 M3 14H4.5 M9.5 14H17"/>'
                     '<circle cx="13" cy="6" r="2.2"/><circle cx="7" cy="14" r="2.2"/>'),
}


# The button that folds the sidebar: a window with its side column, and an
# arrow towards where the column goes.
SIDEBAR = {
    "fold": ('<rect x="2.5" y="3.5" width="15" height="13" rx="2"/>'
             '<path d="M7.5 3.5V16.5 M13.5 7.5 L11 10 L13.5 12.5"/>'),
    "unfold": ('<rect x="2.5" y="3.5" width="15" height="13" rx="2"/>'
               '<path d="M7.5 3.5V16.5 M11 7.5 L13.5 10 L11 12.5"/>'),
}


def _leer(svg: bytes, lado: int, escala: float = 2.0) -> QPixmap:
    """Un SVG pintado a `lado` píxeles, nítido también en pantallas densas."""
    bufer = QBuffer()
    bufer.setData(QByteArray(svg))
    bufer.open(QBuffer.OpenModeFlag.ReadOnly)
    lector = QImageReader(bufer, b"svg")
    real = max(1, round(lado * escala))
    lector.setScaledSize(QSize(real, real))
    imagen = lector.read()
    if imagen.isNull():
        # Sin el complemento de SVG no hay icono, y eso no puede tumbar la
        # ventana: se queda el hueco.
        imagen = QImage(real, real, QImage.Format.Format_ARGB32)
        imagen.fill(0)
    pixmap = QPixmap.fromImage(imagen)
    pixmap.setDevicePixelRatio(escala)
    return pixmap


def _de_trazo(cuerpo: str, color: str, lado: int) -> QPixmap:
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="none" '
           f'stroke="{color}" stroke-width="1.5" stroke-linecap="round" '
           f'stroke-linejoin="round">{cuerpo}</svg>')
    return _leer(svg.encode(), lado)


def nav_icon(seccion: str, color: str, color_abierta: str, lado: int) -> QIcon:
    """El icono de una sección: en `color`, y en `color_abierta` si es la
    que está abierta. Vacío si la sección no tiene uno dibujado."""
    cuerpo = NAV.get(seccion)
    icono = QIcon()
    if cuerpo is None:
        return icono
    icono.addPixmap(_de_trazo(cuerpo, color, lado), QIcon.Mode.Normal)
    icono.addPixmap(_de_trazo(cuerpo, color_abierta, lado), QIcon.Mode.Selected)
    return icono


def sidebar_icon(folded: bool, color: str, lado: int) -> QIcon:
    """The fold button's icon: to fold the bar, or to open it again."""
    return QIcon(_de_trazo(SIDEBAR["unfold" if folded else "fold"], color, lado))


def mark(oscuro: bool, lado: int) -> QPixmap:
    """La marca suelta, sin ficha, para ponerla junto al nombre."""
    archivo = ASSETS / ("silux-mark-dark.svg" if oscuro else "silux-mark-light.svg")
    try:
        return _leer(archivo.read_bytes(), lado)
    except OSError:
        return QPixmap()
