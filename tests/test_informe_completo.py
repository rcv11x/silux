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
from tests.per_dump import per_dump
from tests.test_equipos import EQUIPOS, shared_snapshot, volcados

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

    from silux.ui.widgets import StatTile

    # A padlocked tile's detail («with permissions») is the padlock's own,
    # which the report writes as «(needs permissions)».
    padlocked = {id(t.detail) for t in pagina.findChildren(StatTile) if t.is_locked()}
    textos = []
    for arbol in pagina.findChildren(QTreeWidget):
        if arbol.isVisibleTo(pagina):
            fila = QTreeWidgetItemIterator(arbol)
            while fila.value() is not None:
                if fila.value().text(0).strip():
                    textos.append(fila.value().text(0).strip())
                fila += 1
    for etiqueta in pagina.findChildren(QLabel):
        if etiqueta.isVisibleTo(pagina) and id(etiqueta) not in padlocked:
            # Line by line: a multi-line label keeps its lines in the report,
            # and inside a notice each one is quoted.
            textos += [line for line in _texto_de_etiqueta(etiqueta).splitlines()
                       if line.strip()]
    return textos


@unittest.skipIf(QApplication is None, "sin PySide6")
class TestElInformeDiceLoQueEnsenaLaVentana(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.app = qt.app()

    def _comparar(self, nombre, f):
        from silux import privacidad
        from silux.i18n import _
        from silux.ui import full_report
        from silux.ui.app import SECTIONS, seccion_que_falta

        informe = full_report.build(f)
        apartados = _apartados(informe)
        with pantalla.Ventana(privacidad.anonymize(f)) as ventana:
            ventana._on_sample(privacidad.anonymize(f))
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

    def _every_page(self, folder):
        self._comparar(folder.name, shared_snapshot(folder))

    def _anonymized(self, folder):
        from silux.ui import full_report

        f = shared_snapshot(folder)
        informe = full_report.build(f)
        if f.system.hostname and f.system.hostname not in ("equipo", "silux-pc"):
            self.assertNotIn(f.system.hostname, informe)
        # A dump whose annex lost the hostname has none to cover.
        if f.system.hostname:
            self.assertIn("silux-pc", informe)

    def test_las_secciones_se_eligen(self):
        from silux.i18n import _
        from silux.ui import full_report
        f = shared_snapshot(volcados()[0])
        apartados = _apartados(full_report.build(f, sections=["cpu", "placa"]))
        self.assertEqual(set(apartados) - {"Diagnóstico"},
                         {_("nav.cpu"), _("nav.board")})

    def test_lo_que_falta_por_permisos_lo_dice(self):
        from silux.i18n import _
        from silux.ui import full_report
        f = shared_snapshot(EQUIPOS / "5800x3d")
        informe = full_report.build(f)
        self.assertIn(f"Voltaje: ({_('report.locked')})", informe)


per_dump(TestElInformeDiceLoQueEnsenaLaVentana, "cada_pagina_de_cada_volcado",
         TestElInformeDiceLoQueEnsenaLaVentana._every_page)
per_dump(TestElInformeDiceLoQueEnsenaLaVentana, "va_anonimizado",
         TestElInformeDiceLoQueEnsenaLaVentana._anonymized)



class TestANarrowTableInTheReport(unittest.TestCase):
    """In a narrow card each name goes above its value; the report still says
    «name: value», whatever the width of the window it was taken from."""

    def test_a_name_above_its_value_is_one_line(self):
        from PySide6.QtWidgets import QApplication

        from silux.ui import full_report
        from silux.ui.widgets import InfoGrid

        qt.app()
        grid = InfoGrid()
        grid.add("Memoria del sistema (GTT)")
        grid.set("Memoria del sistema (GTT)", "hasta 11.6 GiB")
        grid.add("Driver")
        grid.set("Driver", "i915")
        grid.show()
        expected = ["- Memoria del sistema (GTT): hasta 11.6 GiB", "- Driver: i915"]
        for width, stacked in ((120, True), (900, False)):
            grid.resize(width, 200)
            QApplication.processEvents()
            self.assertEqual(grid._stacked, stacked, width)
            self.assertEqual(full_report._lineas(grid, grid), expected, width)
        grid.close()


if __name__ == "__main__":
    unittest.main()
