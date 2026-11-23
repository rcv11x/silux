"""Every page in the interface's language, and only in it.

The Network page showed its headers and tiles in Spanish with the interface
in English («Bajando», «Recibido»), a stopped fan read «parado», a monitor
«semana 16 de 2024», a CPU at a fixed clock «fija en 4.20 GHz». Every page
of every dump is opened in English and in Spanish, and what can be seen
(labels, tiles, headers, notices, buttons, the sidebar) must not hold words
of the other language.

A word of the other language is one that only its interface file uses, one
of its function words («de», «con» / «the», «with») in lowercase, or, in
English, an accented letter. Data does not count: a word the snapshot itself
carries (a model, a maker, a driver), a path, and each language's own name in
the language selector.
"""

import dataclasses
import json
import pathlib
import re
import unittest

from silux import i18n
from tests import pantalla, qt
from tests.per_dump import per_dump
from tests.test_equipos import foto, shared_snapshot, volcados

LANG = pathlib.Path(__file__).resolve().parent.parent / "silux" / "db" / "lang"
# Letters with neither a letter nor a digit next to them: a commit hash such
# as «f92b2be3» in the build id holds no word.
WORD = re.compile(r"(?<![\dA-Za-zÁÉÍÓÚÜÑáéíóúüñ])[A-Za-zÁÉÍÓÚÜÑáéíóúüñ]{2,}"
                  r"(?![\dA-Za-zÁÉÍÓÚÜÑáéíóúüñ])")
HTML = re.compile(r"<[^>]+>|&[#\w]+;")
PATH = re.compile(r"(?:~|\.)?(?:/[\w.@:+\-]+)+/?")
ACCENT = re.compile(r"[áéíóúñ¿¡]")
FUNCTION_WORDS = {
    "en": {"de", "del", "la", "las", "los", "el", "con", "sin", "por", "para", "que",
           "una", "uno", "entre", "desde", "hasta", "cada", "sobre", "según", "como",
           "pero", "más", "menos", "este", "esta", "sus", "son", "está", "se", "lo",
           "al", "ni", "ya", "su", "es", "y"},
    "es": {"the", "and", "with", "without", "for", "from", "this", "that", "not", "are",
           "is", "of", "to", "in", "on", "by", "at", "an", "or", "it", "its", "be", "was",
           "has", "have", "will", "can", "than", "when", "which", "only"},
}
LANGUAGE_NAMES = {"español", "english"}


def _clean(texto: str) -> str:
    return PATH.sub(" ", HTML.sub(" ", texto))


def _words(texto: str) -> set:
    return set(WORD.findall(_clean(texto)))


def _vocabulary(idioma: str) -> set:
    valores = json.loads((LANG / f"{idioma}.json").read_text(encoding="utf-8")).values()
    return {w.lower() for v in valores for w in _words(v)}


def _foreign_words(idioma: str) -> set:
    """What must not be seen with the interface in `idioma`, lowercase."""
    propio, ajeno = _vocabulary(idioma), _vocabulary("en" if idioma == "es" else "es")
    return ajeno - propio


def _data(snapshot) -> set:
    palabras = set()

    def recorrer(valor):
        if dataclasses.is_dataclass(valor) and not isinstance(valor, type):
            for campo in dataclasses.fields(valor):
                recorrer(getattr(valor, campo.name))
        elif isinstance(valor, dict):
            for clave, dentro in valor.items():
                recorrer(clave)
                recorrer(dentro)
        elif isinstance(valor, (list, tuple, set, frozenset)):
            for dentro in valor:
                recorrer(dentro)
        elif isinstance(valor, str):
            palabras.update(w.lower() for w in _words(valor))

    recorrer(snapshot)
    return palabras


def visible_texts(ventana) -> list:
    """What the person sees: hidden widgets do not count."""
    from PySide6.QtWidgets import (QAbstractButton, QComboBox, QLabel, QLineEdit,
                                   QTreeWidget, QTreeWidgetItemIterator)
    from silux.ui.widgets import ElidingLabel

    textos = []
    for etiqueta in ventana.findChildren(QLabel):
        if etiqueta.isVisibleTo(ventana):
            textos.append(etiqueta.full_text() if isinstance(etiqueta, ElidingLabel)
                          else etiqueta.text())
    for boton in ventana.findChildren(QAbstractButton):
        if boton.isVisibleTo(ventana):
            textos.append(boton.text())
    for campo in ventana.findChildren(QLineEdit):
        if campo.isVisibleTo(ventana):
            textos += [campo.text(), campo.placeholderText()]
    for lista in ventana.findChildren(QComboBox):
        if lista.isVisibleTo(ventana):
            textos += [lista.itemText(i) for i in range(lista.count())]
    for arbol in ventana.findChildren(QTreeWidget):
        if not arbol.isVisibleTo(ventana):
            continue
        textos += [arbol.headerItem().text(c) for c in range(arbol.columnCount())]
        fila = QTreeWidgetItemIterator(arbol)
        while fila.value() is not None:
            textos += [fila.value().text(c) for c in range(arbol.columnCount())]
            fila += 1
    return [t for t in textos if t and t.strip()]


def foreign(texto: str, idioma: str, ajenas: set, datos: set) -> set:
    """The words of `texto` that belong to the other language."""
    palabras = {w for w in _words(texto) if w.lower() not in datos | LANGUAGE_NAMES}
    # Function words count in lowercase only: «The Tumultuous Unicorn Of
    # Darkness» is a name, and «AES-NI» an acronym.
    malas = {w for w in palabras if w.lower() in ajenas and not w.isupper()}
    malas |= {w for w in palabras if w in FUNCTION_WORDS[idioma]}
    if idioma == "en" and ACCENT.search(_clean(texto)):
        malas |= {w for w in palabras if ACCENT.search(w)}
    return malas


class TestEveryPageInOneLanguage(unittest.TestCase):

    def _no_word_of_the_other_language(self, carpeta):
        qt.app()
        for idioma in ("en", "es"):
            ajenas = _foreign_words(idioma)
            i18n.set_language(idioma)
            try:
                snapshot = shared_snapshot(carpeta)
                datos = _data(snapshot)
                with pantalla.Ventana(snapshot) as ventana:
                    for clave, _pagina in pantalla.recorrer(ventana):
                        for texto in visible_texts(ventana):
                            malas = foreign(texto, idioma, ajenas, datos)
                            with self.subTest(idioma=idioma, equipo=carpeta.name, pagina=clave):
                                self.assertFalse(malas, f"{sorted(malas)} :: {texto[:120]}")
            finally:
                i18n.set_language("es")

    def test_it_sees_a_word_of_the_other_language(self):
        ajenas = _foreign_words("en")
        self.assertTrue(foreign("parado", "en", ajenas, set()))
        self.assertTrue(foreign("semana 16 de 2024", "en", ajenas, set()))
        self.assertTrue(foreign("Bajando", "en", ajenas, set()))
        self.assertFalse(foreign("AES-NI", "en", ajenas, set()))
        self.assertTrue(foreign("fixed at 4.2 GHz", "es", _foreign_words("es"), set()))


per_dump(TestEveryPageInOneLanguage, "no_word_of_the_other_language",
         TestEveryPageInOneLanguage._no_word_of_the_other_language)


if __name__ == "__main__":
    unittest.main()
