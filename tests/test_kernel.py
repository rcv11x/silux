"""Lo que falta porque el kernel es anterior al dato se dice así.

Los dos volcados se convierten en lo que daría un 5.15, el mínimo que silux
admite: la versión grabada pasa a 5.15.0 y se quita lo que ese kernel no
publica (según `docs/kernel.md`). Lo que en 5.15 vive en otro sitio —los
relojes de i915, en el nivel de la tarjeta en vez de en `gt/gt0/`— se pone
donde estaría, con el mismo contenido: nada que un 5.15 no dé.
"""

import json
import os
import pathlib
import re
import shutil
import tempfile
import unittest

from silux import kernel
from silux.i18n import _
from silux.model import Need
from tests import qt
from tests.test_equipos import EQUIPOS, foto

try:
    from PySide6.QtWidgets import QApplication
except ImportError:                                    # pragma: no cover
    QApplication = None

RAIZ = pathlib.Path(__file__).resolve().parent.parent
DOC = (RAIZ / "docs" / "kernel.md").read_text(encoding="utf-8")

# Las vulnerabilidades que un 5.15.0 no lista (las retroportaciones llegaron
# en 5.15.48 y siguientes; 5.15.0 no las tiene).
VULNERABILIDADES_NUEVAS = ("mmio_stale_data", "retbleed", "gather_data_sampling",
                           "spec_rstack_overflow", "reg_file_data_sampling", "ghostwrite",
                           "indirect_target_selection", "old_microcode", "tsa", "vmscape")


class TestElDocumentoYElCodigoDicenLoMismo(unittest.TestCase):

    def _filas(self):
        """{clave: (mayor, menor)} de las filas del documento que llevan clave."""
        filas = {}
        for linea in DOC.splitlines():
            celdas = [c.strip() for c in linea.strip().strip("|").split("|")]
            if len(celdas) < 6 or not re.fullmatch(r"`[a-z0-9_.]+`", celdas[3]):
                continue
            version = re.search(r"(\d+)\.(\d+)", celdas[2])
            filas[celdas[3].strip("`")] = (int(version.group(1)), int(version.group(2)))
        return filas

    def test_cada_clave_con_la_misma_version(self):
        self.assertEqual(self._filas(), kernel.DESDE)

    def test_todo_lo_de_la_tabla_es_posterior_al_minimo(self):
        self.assertTrue(all(v > kernel.MINIMO for v in kernel.DESDE.values()))

    def test_el_readme_dice_el_minimo(self):
        readme = (RAIZ / "README.md").read_text(encoding="utf-8")
        self.assertIn("Linux 5.15", readme)
        self.assertIn("docs/kernel.md", readme)


class TestLaFrase(unittest.TestCase):

    def test_con_un_kernel_anterior(self):
        self.assertEqual(kernel.too_old("amdgpu.vcn_busy_percent", (5, 15)),
                         _("kernel.tooold").format(tuyo="5.15", desde="6.10"))

    def test_con_uno_que_ya_lo_tiene_o_sin_saberlo(self):
        self.assertIsNone(kernel.too_old("amdgpu.vcn_busy_percent", (6, 10)))
        self.assertIsNone(kernel.too_old("amdgpu.vcn_busy_percent", (7, 3)))

    def test_la_version_de_lo_que_publica_cada_sitio(self):
        self.assertEqual(kernel.version("Linux 7.3.3-200.fc44.x86_64"), (7, 3))
        self.assertEqual(kernel.version("5.15.0-91-generic"), (5, 15))
        self.assertIsNone(kernel.version(""))


def _a_515(origen: pathlib.Path, destino: pathlib.Path) -> pathlib.Path:
    """Una copia del volcado como la daría un 5.15.0."""
    copia = destino / origen.name
    shutil.copytree(origen, copia, symlinks=True)
    grabado = copia / "grabado.json"
    datos = json.loads(grabado.read_text())
    datos["plataforma"]["uname"]["release"] = "5.15.0-91-generic"
    grabado.write_text(json.dumps(datos))

    cpu = copia / "sys/devices/system/cpu"
    for archivo in cpu.glob("cpufreq/policy*/cpuinfo_avg_freq"):
        archivo.unlink()
    for nombre in VULNERABILIDADES_NUEVAS:
        (cpu / "vulnerabilities" / nombre).unlink(missing_ok=True)

    # amd-pstate es de 5.17: un 5.15 va con acpi-cpufreq.
    for politica in cpu.glob("cpufreq/policy*"):
        for archivo in list(politica.glob("amd_pstate_*")) + list(
                politica.glob("energy_performance_*")):
            archivo.unlink()
        driver = politica / "scaling_driver"
        if driver.is_file() and driver.read_text().startswith("amd-pstate"):
            driver.write_text("acpi-cpufreq\n")

    for archivo in copia.rglob("vcn_busy_percent"):        # 6.10
        archivo.unlink()
    for archivo in copia.rglob("power1_input"):            # 6.6 en amdgpu
        if "hwmon" in str(archivo) and (archivo.parent / "power1_average").exists():
            archivo.unlink()

    # i915 por GT es de 5.19: antes, los mismos valores en la tarjeta.
    for gt0 in copia.rglob("gt/gt0"):
        tarjeta = gt0.parent.parent
        for archivo in gt0.glob("rps_*_freq_mhz"):
            (tarjeta / archivo.name.replace("rps_", "gt_", 1)).write_text(archivo.read_text())
        shutil.rmtree(gt0.parent)
    return copia


@unittest.skipIf(QApplication is None, "sin PySide6")
class TestLosVolcadosEnUn515(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.app = qt.app()
        cls._tmp = tempfile.TemporaryDirectory()
        tmp = pathlib.Path(cls._tmp.name)
        cls.intel = foto(_a_515(EQUIPOS / "i5-10400", tmp))[0]
        cls.amd = foto(_a_515(EQUIPOS / "5800x3d", tmp))[0]

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def _seccion(self, muestra):
        from silux.settings import Preferences
        from silux.ui import theme
        from silux.ui.pages.graphics import GraphicsPage

        pagina = GraphicsPage(theme.palette_for(self.app, "dark"), Preferences().normalized())
        self.addCleanup(pagina.deleteLater)
        pagina.resize(1200, 900)
        pagina.show()
        pagina.apply(muestra)
        self.app.processEvents()
        return pagina._sections[0]

    def test_sigue_leyendose_lo_que_existe(self):
        self.assertEqual(kernel.version(self.intel.system.kernel), (5, 15))
        # La frecuencia, de scaling_cur_freq; los relojes de la gráfica, de
        # la tarjeta; las vulnerabilidades, las nueve que conoce.
        self.assertTrue(all(h.freq_hz for h in self.intel.cpu.logical))
        self.assertEqual(self.intel.gpus[0].clocks.silicon_max_hz, 1_100_000_000)
        self.assertEqual(len(self.intel.system.vulnerabilities), 9)

    def test_lo_que_depende_del_hardware_no_se_atribuye_al_kernel(self):
        """El «Estado» de una Intel depende de la generación: este Comet Lake
        no lo tiene ni con 7.3. Y el uso del video de una AMD sale también
        de gpu_metrics (5.10): con 5.15 sigue saliendo. Decir «tu kernel no
        lo publica» sería falso en los dos casos."""
        seccion = self._seccion(self.intel)
        self.assertIn(_("gpu.na.intel.throttle"), seccion.sensors_outside.text())
        self.assertNotIn("5.19", seccion.sensors_outside.text())
        self.assertIsNotNone(self.amd.gpus[0].video_busy_percent)

    def test_la_ddr5_sin_spd_lo_atribuye_al_kernel(self):
        """spd5118 es de 6.11: con un kernel anterior no es la placa."""
        import dataclasses
        from silux.model import MemoryModule
        from silux.settings import Preferences
        from silux.ui import theme
        from silux.ui.pages.memory import MemoryPage

        modulos = tuple(MemoryModule(populated=True, locator=f"DIMM {n}", type="DDR5",
                                     size_bytes=16 << 30, speed_mts=5600, configured_mts=4800,
                                     manufacturer="Kingston") for n in (1, 2))
        for nucleo, culpa_al_kernel in (("Linux 5.15.0-91-generic", True),
                                        ("Linux 6.11.0", False)):
            with self.subTest(kernel=nucleo):
                muestra = dataclasses.replace(
                    self.intel, spd=(), modules=modulos,
                    system=dataclasses.replace(self.intel.system, kernel=nucleo))
                pagina = MemoryPage(theme.palette_for(self.app, "dark"), Preferences())
                self.addCleanup(pagina.deleteLater)
                pagina.apply(muestra)
                self.app.processEvents()
                texto = pagina.spd_missing.text()
                self.assertEqual(kernel.too_old("spd5118", (5, 15)) in texto, culpa_al_kernel)
                self.assertNotIn("esta placa no deja", texto)

    def test_amd_el_techo_lo_atribuye_al_kernel(self):
        nota = self.amd.note_for("cpu.clocks.max_turbo_hz") if hasattr(self.amd, "note_for") \
            else next((n for n in self.amd.notes if n.path == "cpu.clocks.max_turbo_hz"), None)
        self.assertIsNotNone(nota)
        self.assertIs(nota.need, Need.KERNEL)
        self.assertIn(kernel.too_old("amd_pstate", (5, 15)), nota.hint)

    def test_en_intel_el_techo_no_se_atribuye_a_amd_pstate(self):
        from silux.providers.base import Draft
        from silux.providers.cppc import CppcClocks
        from unittest import mock

        draft = Draft()
        draft.types["general"] = {"vendor": "Intel", "cpus": [0], "architecture": "x86_64"}
        with mock.patch("silux.providers.cppc._hay_ranking", return_value=True), \
             mock.patch("silux.providers.cppc._techo_de_amd_pstate", return_value=None), \
             mock.patch("silux.providers.cppc._leer_cppc", return_value={}), \
             mock.patch("silux.kernel.running", return_value=(5, 15)):
            CppcClocks().collect(draft)
        nota = next(n for n in draft.notes if n.path == "cpu.clocks.max_turbo_hz")
        self.assertIs(nota.need, Need.HARDWARE)

    def test_con_el_kernel_de_verdad_no_se_culpa_al_kernel(self):
        """Los mismos volcados, con su kernel (7.3), no dicen nada de esto."""
        intel = foto(EQUIPOS / "i5-10400")[0]
        seccion = self._seccion(intel)
        self.assertIn(_("gpu.na.intel.throttle"), seccion.sensors_outside.text())
        self.assertFalse([n for n in intel.notes if n.need is Need.KERNEL])


if __name__ == "__main__":
    unittest.main()
