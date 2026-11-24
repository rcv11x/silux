"""Cómo está repartida la página CPU: lo que se busca arriba, lo demás a un clic.

«Procesador» eran quince filas seguidas: entre el encapsulado y el voltaje
había que pasar por familia, modelo, stepping, firma CPUID y microcódigo,
que hacen falta para un informe y casi nunca para otra cosa. Y la leyenda de
los mejores núcleos eran dos renglones de letra pequeña a todo el ancho.
"""

import unittest

from silux.i18n import _
from tests import pantalla, qt
from tests.test_equipos import EQUIPOS, foto, shared_snapshot

try:
    from PySide6.QtWidgets import QApplication, QLabel
except ImportError:                                    # pragma: no cover
    QApplication = None


@unittest.skipIf(QApplication is None, "sin PySide6")
class TestLaPaginaCpu(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.app = qt.app()
        cls.fotos = {n: shared_snapshot(EQUIPOS / n) for n in ("5800x3d", "i5-10400")}

    def _seccion(self, ventana):
        from silux.ui.pages.cpu import TypeSection

        ventana.select_section("CPU")
        self.app.processEvents()
        return ventana.cpu_page.findChildren(TypeSection)[0]

    def test_la_identificacion_va_plegada_y_no_se_pierde(self):
        for equipo, f in self.fotos.items():
            with self.subTest(equipo=equipo), pantalla.Ventana(f) as ventana:
                seccion = self._seccion(ventana)
                tipo = f.cpu.types[0]
                microcodigo = seccion.identity._values[_("cpu.field.microcode")]
                self.assertFalse(microcodigo.isVisible())
                self.assertNotIn(_("cpu.field.family"), seccion.processor._values)
                seccion.identity_fold.boton.click()
                self.app.processEvents()
                self.assertTrue(microcodigo.isVisible())
                self.assertEqual(microcodigo.full_text(), tipo.microcode)
                self.assertTrue(seccion.identity._values[_("cpu.field.signature")].full_text())

    def test_arriba_queda_lo_que_se_busca_con_el_voltaje(self):
        with pantalla.Ventana(self.fotos["5800x3d"]) as ventana:
            seccion = self._seccion(ventana)
            filas = seccion.processor._filas
            self.assertEqual(len(filas), 10)
            for clave in ("cpu.field.package", "cpu.field.cores", "cpu.field.threads",
                          "cpu.field.voltage"):
                self.assertIn(_(clave), filas)
            # Sin permisos el voltaje sigue llevando su candado, a la vista.
            self.assertTrue(seccion.processor.is_locked(_("cpu.field.voltage")))
            self.assertTrue(seccion.processor._candados[_("cpu.field.voltage")].isVisible())

    def test_la_leyenda_de_los_mejores_nucleos_es_una_frase(self):
        with pantalla.Ventana(self.fotos["5800x3d"]) as ventana:
            ventana.select_section("CPU")
            self.app.processEvents()
            leyenda = ventana.cpu_page.live.calidad
            self.assertTrue(leyenda.isVisible())
            self.assertIn("Núcleo 1", leyenda.text())
            self.assertNotIn("oblea", leyenda.text())
            # El porqué no se pierde: está al pasar el ratón.
            self.assertIn("oblea", leyenda.toolTip())
            self.assertIn("85 %", leyenda.toolTip())
            # Two lines at most, counted: the label's height carries its
            # margins too, and with a larger font they no longer fit under
            # exactly two line spacings.
            self.assertLessEqual(round(leyenda.height() / leyenda.fontMetrics().lineSpacing()), 2)


class TestLaEspecificacionEnCompacto(unittest.TestCase):
    """En compacto a 900 px «Intel(R) Core(TM) i5-10400 CPU @ 2.90GHz» salía
    cortada con puntos suspensivos; es una frase y pasa a dos líneas."""

    def test_sale_entera_en_dos_lineas(self):
        from silux.settings import Preferences
        from silux.ui import theme
        from silux.ui.app import MainWindow

        app = qt.app()
        normales = Preferences().normalized()
        self.addCleanup(theme.apply, app, normales.theme, normales.density,
                        normales.font_scale)
        # Con la letra por omisión, que es la «grande»: con la normal cabía.
        prefs = Preferences(density="compact", window_width=900,
                            window_height=680).normalized()
        theme.apply(app, prefs.theme, prefs.density, prefs.font_scale)
        for equipo in ("i5-10400", "5800x3d"):
            with self.subTest(equipo=equipo):
                f = shared_snapshot(EQUIPOS / equipo)
                ventana = MainWindow(prefs)
                self.addCleanup(ventana.close)
                ventana.resize(900, 680)
                ventana.show()
                for _vuelta in range(3):
                    ventana._on_sample(f)
                    for _vez in range(4):
                        app.processEvents()
                ventana.select_section("CPU")
                for _vez in range(6):
                    app.processEvents()
                pagina = ventana.stack.currentWidget()
                valor = next(e for e in pagina.findChildren(type(pagina.findChild(
                    __import__("silux.ui.widgets", fromlist=["ElidingLabel"]).ElidingLabel)))
                    if getattr(e, "full_text", lambda: "")() == f.cpu.types[0].brand)
                self.assertEqual(valor.text(), valor.full_text())
                self.assertGreaterEqual(valor.height(), valor.heightForWidth(valor.width()))
                una = valor.fontMetrics().horizontalAdvance(valor.full_text())
                if una > valor.width():                 # no cabe en una: son dos
                    self.assertGreater(valor.height(), valor.fontMetrics().lineSpacing() * 1.5)

    def test_y_si_ni_en_dos_cabe_se_recorta(self):
        from silux.ui.widgets import ElidingLabel

        app = qt.app()
        etiqueta = ElidingLabel("una especificación larguísima que no cabe ni en dos líneas "
                                "de una columna estrecha por mucho que se parta")
        self.addCleanup(etiqueta.deleteLater)
        etiqueta.permitir_lineas(2)
        etiqueta.resize(120, 60)
        etiqueta.show()
        app.processEvents()
        self.assertNotEqual(etiqueta.text(), etiqueta.full_text())
        self.assertTrue(etiqueta.text().endswith("…"))
        self.assertEqual(etiqueta.toolTip(), etiqueta.full_text())


if __name__ == "__main__":
    unittest.main()


@unittest.skipIf(QApplication is None, "sin PySide6")
class TestEachCoreTypeIsASection(unittest.TestCase):
    """On a hybrid, «Performance cores» and «Efficient cores» head their
    cards: they were a small grey line, read as loose text between cards."""

    @classmethod
    def setUpClass(cls):
        from silux.settings import Preferences
        from silux.ui import theme

        cls.app = qt.app()
        prefs = Preferences(font_scale="máximo").normalized()
        theme.apply(cls.app, prefs.theme, prefs.density, prefs.font_scale)
        cls.snapshot = shared_snapshot(EQUIPOS / "i7-12700kf")

    def test_each_heading_is_a_section_title_on_one_line(self):
        from silux.render import core_type_label
        from silux.ui.pages.cpu import TypeSection

        with pantalla.Ventana(self.snapshot) as ventana:
            ventana.resize(760, 900)
            ventana.select_section("CPU")
            self.app.processEvents()
            sections = ventana.cpu_page.findChildren(TypeSection)
            self.assertEqual(len(sections), 2)
            for section, cpu_type in zip(sections, self.snapshot.cpu.types):
                heading = section.report_title_label
                with self.subTest(type=cpu_type.key):
                    self.assertEqual(heading.text(), core_type_label(cpu_type, True))
                    self.assertEqual(heading.objectName(), "SectionTitle")
                    self.assertTrue(heading.isVisible())
                    self.assertLess(heading.height(), 1.5 * heading.fontMetrics().height())
                    self.assertGreater(heading.font().pixelSize(), heading.parentWidget()
                                       .findChildren(QLabel, "CardTitle")[0].font().pixelSize())


@unittest.skipIf(QApplication is None, "sin PySide6")
class TestABaseTheMachineDoesntPublish(unittest.TestCase):
    """«Base: —» sat above a notice saying the machine doesn't publish it.
    What the hardware lacks is hidden and named at the foot (rule 5); what
    needs permissions keeps its row, with its padlock."""

    def test_hidden_when_absent_kept_when_locked(self):
        from silux.ui.pages.cpu import TypeSection

        app = qt.app()
        base = _("cpu.clock.base")
        for dump, shown, locked in (("fx-8150", False, False), ("athlon-3000g", True, True),
                                    ("i5-10400", True, False)):
            with self.subTest(dump=dump), pantalla.Ventana(shared_snapshot(EQUIPOS / dump)) as window:
                window.select_section("CPU")
                app.processEvents()
                section = window.cpu_page.findChildren(TypeSection)[0]
                self.assertEqual(section.clocks._names[base].isVisible(), shown)
                self.assertEqual(section.clocks.is_locked(base), locked)
