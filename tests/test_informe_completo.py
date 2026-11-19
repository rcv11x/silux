"""El informe completo dice todo lo que enseña la ventana.

Se escribe recorriendo las páginas de verdad (`silux/ui/full_report.py`), y
aquí se comprueba lo que promete: con cada volcado, todo texto que se ve en
una página está en su apartado del informe. El informe de antes se escribía
a mano desde la foto y se quedaba atrás de la ventana: no decía la memoria
instalada, ni los dispositivos, ni la mitad de Gráficos.
"""

import re
import unittest

from tests import pantalla, qt
from tests.test_equipos import foto, volcados

try:
    from PySide6.QtWidgets import QApplication
except ImportError:                                    # pragma: no cover
    QApplication = None


def _apartados(informe: str) -> dict[str, str]:
    trozos = re.split(r"^## ", informe, flags=re.M)
    return {t.split("\n", 1)[0].strip(): t for t in trozos[1:]}


def _visibles(pagina) -> list[str]:
    """Lo que se lee en una página: el texto de sus etiquetas a la vista."""
    from PySide6.QtWidgets import QLabel
    from silux.ui.full_report import _texto_de_etiqueta

    from PySide6.QtWidgets import QTreeWidget, QTreeWidgetItemIterator

    textos = []
    for arbol in pagina.findChildren(QTreeWidget):
        if arbol.isVisibleTo(pagina):
            fila = QTreeWidgetItemIterator(arbol)
            while fila.value() is not None:
                if fila.value().text(0).strip():
                    textos.append(fila.value().text(0).strip())
                fila += 1
    for etiqueta in pagina.findChildren(QLabel):
        if etiqueta.isVisibleTo(pagina):
            texto = _texto_de_etiqueta(etiqueta)
            if texto and texto.strip():
                textos.append(texto)
    return textos


@unittest.skipIf(QApplication is None, "sin PySide6")
class TestElInformeDiceLoQueEnsenaLaVentana(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.app = qt.app()
        cls.fotos = {c.name: foto(c)[0] for c in volcados()}

    def _comparar(self, nombre, f):
        from silux import privacidad
        from silux.i18n import _
        from silux.ui import full_report
        from silux.ui.app import SECTIONS, seccion_que_falta

        informe = full_report.build(f)
        apartados = _apartados(informe)
        with pantalla.Ventana(privacidad.anonimizar(f)) as ventana:
            ventana._on_sample(privacidad.anonimizar(f))
            for clave, pagina in pantalla.recorrer(ventana):
                if clave in full_report.FUERA or seccion_que_falta(ventana, clave):
                    continue
                full_report.abrir_plegables(pagina)
                self.app.processEvents()
                titulo = _(clave)
                with self.subTest(equipo=nombre, pagina=titulo):
                    self.assertIn(titulo, apartados, "la página no tiene apartado")
                    apartado = apartados[titulo]
                    faltan = [t for t in _visibles(pagina) if t not in apartado]
                    self.assertEqual(faltan, [])

    def test_cada_pagina_de_cada_volcado(self):
        self.assertTrue(self.fotos)
        for nombre, f in self.fotos.items():
            self._comparar(nombre, f)

    def test_va_anonimizado(self):
        from silux.ui import full_report
        for nombre, f in self.fotos.items():
            with self.subTest(equipo=nombre):
                informe = full_report.build(f)
                if f.system.hostname and f.system.hostname not in ("equipo", "silux-pc"):
                    self.assertNotIn(f.system.hostname, informe)
                self.assertIn("silux-pc", informe)

    def test_las_secciones_se_eligen(self):
        from silux.i18n import _
        from silux.ui import full_report
        f = next(iter(self.fotos.values()))
        apartados = _apartados(full_report.build(f, sections=["cpu", "placa"]))
        self.assertEqual(set(apartados) - {"Diagnóstico"},
                         {_("nav.cpu"), _("nav.board")})

    def test_lo_que_falta_por_permisos_lo_dice(self):
        from silux.i18n import _
        from silux.ui import full_report
        f = self.fotos["5800x3d"]
        informe = full_report.build(f)
        self.assertIn(f"Voltaje: ({_('report.locked')})", informe)


if __name__ == "__main__":
    unittest.main()
