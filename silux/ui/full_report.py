"""El informe completo: lo que enseña cada página, tal y como lo enseña.

`report.py` escribía el informe a mano, sección a sección, desde la foto, y
se quedaba atrás de la ventana: cada dato nuevo había que acordarse de
llevarlo también allí, y la mitad no estaba. Este no tiene una lista propia
de qué contar. Monta la ventana de verdad sin pantalla, le da la foto ya
anonimizada, abre cada página y la recorre en el orden de sus layouts: las
tarjetas salen como títulos, las rejillas como «campo: valor» o como tablas,
las fichas grandes con su cifra y su unidad, y lo que falta por permisos con
su candado dicho en palabras. Lo que se formatea es lo que formatea
`render.py` para la ventana, porque es la ventana.

`tests/test_informe_completo.py` lo comprueba con cada volcado: todo texto
que se ve en una página está en su apartado del informe.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Iterable, Optional

from ..i18n import _

# Un título de Markdown: almohadillas y un espacio. «#1 SMP PREEMPT…», la
# compilación del kernel, no lo es.
_TITULO = re.compile(r"#{1,6} ")

# Lo que no se cuenta: Ajustes son preferencias, no hardware.
FUERA = ("nav.settings",)


def section_ids() -> list[str]:
    """Los nombres con que se eligen secciones en `--sections`: los de la
    clave (`cpu`, `board`, `memory`…)."""
    from .app import SECTIONS

    return [clave.split(".", 1)[1] for clave, _activa in SECTIONS if clave not in FUERA]


def _normal(texto: str) -> str:
    sin_tildes = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in sin_tildes if not unicodedata.combining(c)).lower().strip()


def wanted(clave: str, sections: Optional[Iterable[str]]) -> bool:
    """Si la sección `clave` (`nav.cpu`) está entre las pedidas, por su
    identificador (`cpu`) o por su nombre en la barra lateral («Placa base»,
    «placa base»)."""
    if not sections:
        return True
    pedidas = {_normal(s) for s in sections}
    nombre = _normal(_(clave))
    return (_normal(clave.split(".", 1)[1]) in pedidas or nombre in pedidas
            or nombre.split()[0] in pedidas)


def unknown_sections(sections: Optional[Iterable[str]]) -> list[str]:
    """The requested names that match no section, in the order given."""
    from .app import SECTIONS

    keys = [clave for clave, _activa in SECTIONS if clave not in FUERA]
    return [name for name in sections or ()
            if not any(wanted(key, [name]) for key in keys)]


def build(snapshot, sections: Optional[Iterable[str]] = None,
          anonymous: bool = True, inside_app: bool = False) -> str:
    """El informe en Markdown, anonimizado salvo que se pida lo contrario.
    `sections` limita las páginas.

    Hace falta una `QApplication`; si no la hay, se crea una sin pantalla.
    """
    import os

    from PySide6.QtCore import QCoreApplication, QEvent
    from PySide6.QtWidgets import QApplication

    if QApplication.instance() is None:
        # Sin pantalla aunque la haya: no se enseña ninguna ventana.
        os.environ["QT_QPA_PLATFORM"] = "offscreen"

    from .. import privacidad, report
    from ..settings import Preferences
    from . import theme
    from .app import SECTIONS, MainWindow, seccion_que_falta

    aplicacion = QApplication.instance() or QApplication(["silux"])
    preferencias = Preferences(window_width=1400, window_height=1000).normalized()
    # From the open window (`inside_app`), the user's theme stays: applying
    # one would restyle the whole application.
    if not inside_app:
        theme.apply(aplicacion, "dark", preferencias.density, "normal")
    foto = privacidad.anonymize(snapshot) if anonymous else snapshot
    ventana = MainWindow(preferencias)
    if inside_app:
        # Laid out and painted, but never on screen.
        from PySide6.QtCore import Qt
        ventana.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
    try:
        ventana.resize(1400, 1000)
        ventana.show()
        # Dos veces: lo que se deriva de dos muestras (los ritmos, las
        # medias) solo sale con la segunda.
        ventana._on_sample(foto)
        ventana._on_sample(foto)
        partes = [report._header(foto, anonymous=anonymous)]
        for clave, activa in SECTIONS:
            if not activa or clave in FUERA or not wanted(clave, sections):
                continue
            if not ventana.select_section(clave) or seccion_que_falta(ventana, clave):
                continue
            aplicacion.processEvents()
            pagina = ventana.stack.currentWidget()
            abrir_plegables(pagina)
            aplicacion.processEvents()
            cuerpo = page_text(pagina)
            if cuerpo.strip():
                partes.append(f"\n## {_(clave)}\n\n{cuerpo}")
        partes.append(report._diagnosis(foto))
    finally:
        ventana.hide()
        ventana.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    return "\n".join(partes).strip() + "\n"


def abrir_plegables(pagina) -> None:
    """Abre lo plegado: en el informe va todo, también lo que en la ventana
    hay que desplegar (los identificadores de una gráfica, el desglose de la
    memoria)."""
    from .widgets import Plegable

    for plegable in pagina.findChildren(Plegable):
        if not plegable.abierto():
            plegable.set_abierto(True)
    # What a page folds its own way (Red, its virtual interfaces).
    if hasattr(pagina, "open_for_report"):
        pagina.open_for_report()


def _de_lista(linea: str) -> bool:
    """A list item or a table row, at any depth."""
    return linea.lstrip().startswith(("- ", "|"))


def page_text(pagina) -> str:
    """Lo que enseña una página, en Markdown."""
    lineas = _lineas(pagina, pagina)
    # Sin líneas en blanco repetidas.
    salida: list[str] = []
    for linea in lineas:
        if linea == "" and (not salida or salida[-1] == ""):
            continue
        # A paragraph right after a list is part of its last item in
        # Markdown: «Iris Xe Graphics: no publica su temperatura.» read as
        # one more sensor. A blank line between them.
        if (salida and linea and _de_lista(salida[-1]) and not _de_lista(linea)
                and not linea.startswith(("#", ">"))):
            salida.append("")
        salida.append(linea)
    return "\n".join(salida).strip()


def _visible(widget, raiz) -> bool:
    return widget is raiz or widget.isVisibleTo(raiz)


def _texto_de_etiqueta(etiqueta) -> str:
    """El texto de una etiqueta, entero y sin marcas: el de una
    `ElidingLabel` sin recortar, y el de una con texto enriquecido sin el
    HTML."""
    from PySide6.QtCore import Qt
    from PySide6.QtGui import Qt as QtGui
    from PySide6.QtGui import QTextDocument

    from .widgets import ElidingLabel

    texto = etiqueta.full_text() if isinstance(etiqueta, ElidingLabel) else etiqueta.text()
    if etiqueta.textFormat() == Qt.TextFormat.RichText or (
            etiqueta.textFormat() == Qt.TextFormat.AutoText and QtGui.mightBeRichText(texto)):
        documento = QTextDocument()
        documento.setHtml(texto)
        texto = documento.toPlainText()
    return "\n".join(" ".join(line.split()) for line in texto.splitlines() if line.strip())


def _es_hoja(widget) -> bool:
    """Una pieza que dice una sola cosa: una etiqueta, un candado, una barra
    pintada. Lo que lleva dentro tarjetas, rejillas de datos o tablas no lo
    es."""
    from PySide6.QtWidgets import QAbstractButton, QLabel, QScrollArea, QTreeWidget

    from .corematrix import CoreMatrix
    from .widgets import Card, ChipRow, InfoGrid, LockMark, Sparkline, Table

    if isinstance(widget, (QLabel, LockMark, QAbstractButton, ChipRow, Sparkline)):
        return True
    if isinstance(widget, (Card, InfoGrid, Table, QTreeWidget, QScrollArea, CoreMatrix)):
        return False
    return widget.layout() is None or _todo_hojas(widget.layout())


def _items(disposicion) -> list:
    """Los widgets y sublayouts de un layout, en su orden; en una rejilla, por
    filas."""
    from PySide6.QtWidgets import QGridLayout

    if isinstance(disposicion, QGridLayout):
        posiciones = []
        for i in range(disposicion.count()):
            fila, columna, _alto, _ancho = disposicion.getItemPosition(i)
            posiciones.append((fila, columna, disposicion.itemAt(i)))
        return [item for _f, _c, item in sorted(posiciones, key=lambda x: (x[0], x[1]))]
    return [disposicion.itemAt(i) for i in range(disposicion.count())]


def _todo_hojas(disposicion) -> bool:
    for item in _items(disposicion):
        if item.widget() is not None and not _es_hoja(item.widget()):
            return False
        if item.layout() is not None and not _todo_hojas(item.layout()):
            return False
    return True


def _celda(item, raiz) -> str:
    """Lo que dice una celda o un renglón, en una línea."""
    if item.widget() is not None:
        lineas = _lineas(item.widget(), raiz)
    elif item.layout() is not None:
        lineas = _de_layout(item.layout(), raiz)
    else:
        return ""
    return " ".join(l.strip() for l in lineas if l.strip() and not _TITULO.match(l))


def _filas(rejilla, raiz, columnas: bool = False) -> list[list[str]]:
    """Las celdas con algo que decir de una rejilla, fila a fila.

    Con `columnas`, cada celda en su columna aunque esté vacía: en una tabla,
    quitar un hueco corre las de la derecha bajo otra cabecera."""
    filas: dict[int, dict[int, str]] = {}
    for i in range(rejilla.count()):
        fila, columna, _alto, _ancho = rejilla.getItemPosition(i)
        texto = _celda(rejilla.itemAt(i), raiz)
        if texto:
            filas.setdefault(fila, {})[columna] = texto
    if columnas:
        ancho = max((c for celdas in filas.values() for c in celdas), default=-1) + 1
        return [[celdas.get(c, "") for c in range(ancho)]
                for _f, celdas in sorted(filas.items()) if celdas]
    return [[celdas[c] for c in sorted(celdas)] for _f, celdas in sorted(filas.items())
            if celdas]


def _tabla(filas: list[list[str]]) -> list[str]:
    if not filas:
        return []
    ancho = max(len(f) for f in filas)
    salida = [""]
    for n, fila in enumerate(filas):
        fila = fila + [""] * (ancho - len(fila))
        salida.append("| " + " | ".join(c.replace("|", "\\|") for c in fila) + " |")
        if n == 0:
            salida.append("|" + "---|" * ancho)
    return salida + [""]


def _lineas(widget, raiz) -> list[str]:
    from PySide6.QtWidgets import QAbstractButton, QComboBox, QLabel, QScrollArea, QTreeWidget

    from .. import render
    from .corematrix import CoreMatrix
    from .widgets import Card, ChipRow, InfoGrid, LockMark, Plegable, Sparkline, StatTile, Table

    if not _visible(widget, raiz):
        return []
    if isinstance(widget, LockMark):
        return [f"({_('report.locked')})"]
    if isinstance(widget, (QAbstractButton, Sparkline)):
        return []
    if isinstance(widget, CoreMatrix):
        # Pintada a mano: lo que dice cada hilo sale de sus datos, con el
        # mismo `render` que usa al pintar.
        return [f"- {c['name']}: " + " · ".join(
            x for x in (c.get("detail", ""), render.percent(c.get("usage")))
            if x and x != render.DASH)
            for c in widget._cores]
    if isinstance(widget, StatTile):
        if widget.is_locked():
            valor = f"({_('report.locked')})"
        else:
            valor = widget.figure_text()
        detalle = (_texto_de_etiqueta(widget.detail)
                   if widget.detail.isVisibleTo(raiz) else "")
        return [f"- {widget.caption.text()}: {valor}" + (f" ({detalle})" if detalle else "")]
    if isinstance(widget, ChipRow):
        chips = [_texto_de_etiqueta(c) for c in widget.findChildren(QLabel)
                 if c.isVisibleTo(raiz) and c.text().strip()]
        return [" · ".join(chips)] if chips else []
    if isinstance(widget, InfoGrid):
        return [("- " + ": ".join(f)) if len(f) == 2 else "- " + " · ".join(f)
                for f in _filas(widget._grid, raiz)]
    if isinstance(widget, Table):
        return _tabla(_filas(widget._grid, raiz, columnas=True))
    if isinstance(widget, QTreeWidget):
        return _arbol(widget)
    if isinstance(widget, QLabel):
        texto = _texto_de_etiqueta(widget)
        return texto.splitlines() if texto else []
    if isinstance(widget, QComboBox):
        return [widget.currentText()] if widget.currentText() else []
    if widget.objectName() == "Notice":
        return _notice(widget, raiz)

    lineas: list[str] = []
    if isinstance(widget, Card):
        titulo = getattr(widget, "_title_label", None)
        if titulo is not None and titulo.isVisibleTo(raiz) and titulo.text().strip():
            lineas += ["", f"### {_texto_de_etiqueta(titulo)}", ""]
    if isinstance(widget, Plegable):
        lineas += ["", f"#### {widget._titulo}", ""]
    if isinstance(widget, QScrollArea) and widget.widget() is not None:
        return lineas + _lineas(widget.widget(), raiz)

    disposicion = widget.layout()
    if disposicion is not None:
        lineas += _de_layout(disposicion, raiz, saltar=getattr(widget, "_title_label", None))
    return lineas


def _notice(notice, root) -> list[str]:
    """A notice as a quote with its title in bold, so it doesn't read as part
    of the text above it."""
    from PySide6.QtWidgets import QLabel

    texts = [_texto_de_etiqueta(label) for label in notice.findChildren(QLabel)
             if label.isVisibleTo(root) and label.text().strip()]
    if not texts:
        return []
    title, *rest = texts
    return ["", f"> **{title}**", *(f"> {line}" for text in rest
                                     for line in text.splitlines()), ""]


def _arbol(arbol) -> list[str]:
    from PySide6.QtWidgets import QTreeWidgetItemIterator

    # What the window hides doesn't go in, and columns with nothing in them
    # (the trend line, the stretch) don't either.
    columns = [c for c in range(arbol.columnCount()) if not arbol.isColumnHidden(c)]
    rows = []
    iterador = QTreeWidgetItemIterator(arbol)
    while iterador.value() is not None:
        fila = iterador.value()
        nivel, padre = 0, fila.parent()
        while padre is not None:
            nivel, padre = nivel + 1, padre.parent()
        rows.append((nivel, {c: fila.text(c).strip() for c in columns}))
        iterador += 1
    used = [c for c in columns if any(cells[c] for _level, cells in rows)]
    lines = []
    if not arbol.isHeaderHidden():
        names = [arbol.headerItem().text(c).strip() for c in used]
        if any(names):
            lines.append("*" + " · ".join(n for n in names if n) + "*")
    for level, cells in rows:
        texts = [cells[c] for c in used if cells[c]]
        if texts:
            lines.append("  " * level + "- " + " · ".join(texts))
    return lines


def _solo_hijos():
    from PySide6.QtCore import Qt
    return Qt.FindChildOption.FindDirectChildrenOnly


def _de_layout(disposicion, raiz, saltar=None) -> list[str]:
    """Un layout: si todo lo que lleva son hojas, en una línea (una fila de
    una rejilla, una por fila); si lleva tarjetas o rejillas, recorrido."""
    from PySide6.QtWidgets import QBoxLayout, QGridLayout

    items = [i for i in _items(disposicion) if i.widget() is None or i.widget() is not saltar]
    if isinstance(disposicion, QGridLayout) and _todo_hojas(disposicion):
        return [("- " + f[0] + ": " + " · ".join(f[1:])) if len(f) > 1 else f[0]
                for f in _filas(disposicion, raiz)]
    horizontal = (isinstance(disposicion, QBoxLayout) and disposicion.direction() in (
        QBoxLayout.Direction.LeftToRight, QBoxLayout.Direction.RightToLeft))
    if horizontal and _todo_hojas(disposicion):
        texto = " ".join(c for c in (_celda(i, raiz) for i in items) if c)
        return [texto] if texto else []
    lineas: list[str] = []
    for item in items:
        if item.widget() is not None:
            lineas += _lineas(item.widget(), raiz)
        elif item.layout() is not None:
            lineas += _de_layout(item.layout(), raiz)
    return lineas
