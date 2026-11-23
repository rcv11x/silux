"""An Intel GPU inside the processor, and the temperature it does not have.

i915 and xe register hwmon only on dedicated cards (`xe_hwmon_register` and
`i915_hwmon_register` return early unless IS_DGFX). It shares the package
with the CPU: Gráficos shows the package's, said to be that, and it is never
taken for the GPU's own, neither in Sensores, nor as its `temp_c`, nor in the
report. Without a package sensor (coretemp not loaded) it is as before. The
author's T14 (Iris Xe, i915), mounted; its coretemp says 34 °C.

And what the screen says is said in plain words: no paths, no hwmon, no
sysfs. Those go to the report, in a note's `detail`.
"""

import pathlib
import re
import shutil
import unittest

from silux import volcado
from tests.per_dump import per_dump
from silux.collector import Collector
from silux.i18n import _
from silux.model import SensorKind
from tests import pantalla, qt
from tests.interval import second_snapshot

EQUIPOS = pathlib.Path(__file__).resolve().parent / "fixtures" / "equipos"
CORETEMP = "sys/devices/platform/coretemp.0"


def photo(dump="i5-1135g7", without_coretemp=False):
    with volcado.mounted(EQUIPOS / dump) as raiz:
        if without_coretemp:
            shutil.rmtree(raiz / CORETEMP)
            for enlace in (raiz / "sys/class/hwmon").iterdir():
                if "coretemp" in str(enlace.readlink()):
                    enlace.unlink()
        collector = Collector()
        try:
            return second_snapshot(collector)
        finally:
            collector.close()


def iris(snapshot):
    return next(g for g in snapshot.gpus if g.driver == "i915")


def textos(snapshot, seccion):
    qt.app()
    with pantalla.Ventana(snapshot) as ventana:
        ventana.select_section(seccion)
        return pantalla.textos_de(ventana.stack.currentWidget())


class TestThePackagesTemperature(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.foto = photo()

    def test_it_is_the_package_and_not_its_own(self):
        gpu = iris(self.foto)
        self.assertEqual(gpu.package_temp_c, 34.0)
        self.assertIsNone(gpu.temp_c)
        self.assertTrue(gpu.no_temperature_sensor)

    def test_graphics_shows_it_labelled(self):
        en_pantalla = textos(self.foto, "Gráficos")
        self.assertIn(_("gpu.tile.temp.package"), en_pantalla)
        self.assertIn(_("gpu.tile.package"), en_pantalla)
        self.assertNotIn(_("gpu.tile.temp"), en_pantalla)
        self.assertIn(_("gpu.temp.package.note"), en_pantalla)

    def test_sensores_does_not_give_it_to_the_gpu(self):
        temperaturas = [s for s in self.foto.sensors if s.kind is SensorKind.TEMPERATURE]
        self.assertFalse([s for s in temperaturas if "Iris" in (s.device or "")])

    def test_the_report_says_whose_it_is(self):
        from silux.ui import full_report
        qt.app()
        informe = full_report.build(self.foto)
        lineas = [l for l in informe.splitlines()
                  if l.startswith(f"- {_('gpu.tile.temp.package')}: 34") and _("gpu.tile.package") in l]
        self.assertTrue(lineas, "the report gives the package's temperature with its label")
        # The technical why, for whoever reads the report.
        self.assertIn(_("gpu.temp.detail.package"), informe)


class TestWithoutAPackageSensor(unittest.TestCase):

    def test_as_before_it_has_none(self):
        foto = photo(without_coretemp=True)
        gpu = iris(foto)
        self.assertIsNone(gpu.package_temp_c)
        en_pantalla = textos(foto, "Gráficos")
        self.assertIn(_("gpu.temp.none.note"), en_pantalla)
        self.assertNotIn(_("gpu.tile.package"), en_pantalla)


# What the screen never says: where something is read from. A device's name
# (/dev/sda2) and the card's DRM node (card1) are data, as its PCI slot.
TECNICO = re.compile(r"/sys/|/proc/|\bhwmon\b|\bsysfs\b|\bdebugfs\b", re.IGNORECASE)


class TestNoPathsOnScreen(unittest.TestCase):
    """Every page of every dump, open: a path or a kernel interface on screen
    is the report's, not the user's. The Intel notice said «el nodo DRM no
    trae hwmon y su contador de rendimiento no tiene evento térmico»."""

    def _every_page(self, carpeta):
        qt.app()
        foto = photo(carpeta.name)
        with pantalla.Ventana(foto) as ventana:
            for clave, pagina in pantalla.recorrer(ventana):
                for texto in pantalla.textos_de(pagina):
                    with self.subTest(equipo=carpeta.name, pagina=clave):
                        self.assertIsNone(TECNICO.search(texto), texto)


per_dump(TestNoPathsOnScreen, "every_page_of_every_dump", TestNoPathsOnScreen._every_page)


if __name__ == "__main__":
    unittest.main()
