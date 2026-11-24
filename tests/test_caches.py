"""El eje del mapa de cachés y el agrupado por nivel."""

import unittest

from silux.model import Cache, CpuInfo, CpuType, LogicalCpu, Snapshot
from tests import qt
from tests.per_dump import per_dump


def _snapshot(hybrid: bool = False) -> Snapshot:
    if hybrid:
        # 2 núcleos P con SMT (CPUs 0-3) y 2 núcleos E (CPUs 4-5).
        logical = (
            LogicalCpu(0, core_id=0, package_id=0), LogicalCpu(1, core_id=0, package_id=0),
            LogicalCpu(2, core_id=1, package_id=0), LogicalCpu(3, core_id=1, package_id=0),
            LogicalCpu(4, core_id=2, package_id=0), LogicalCpu(5, core_id=3, package_id=0),
        )
        tipos = (
            CpuType(key="performance", label="P", cores=2, threads=4, caches=(
                Cache(2, "unified", 2 << 20, instances=2, shared_by=2,
                      instance_cpus=((0, 1), (2, 3))),
            )),
            CpuType(key="efficiency", label="E", cores=2, threads=2, caches=(
                Cache(2, "unified", 4 << 20, instances=1, shared_by=2,
                      instance_cpus=((4, 5),)),
            )),
        )
        return Snapshot(1, CpuInfo(hybrid=True, types=tipos, logical=logical))

    # 3 núcleos con SMT: las CPUs hermanas son 0/3, 1/4 y 2/5.
    logical = tuple(
        LogicalCpu(i, core_id=i % 3, package_id=0) for i in range(6)
    )
    tipo = CpuType(key="general", label="g", cores=3, threads=6, caches=(
        Cache(1, "data", 32 << 10, instances=3, shared_by=2,
              instance_cpus=((0, 3), (1, 4), (2, 5))),
        Cache(3, "unified", 8 << 20, instances=1, shared_by=6,
              instance_cpus=(tuple(range(6)),)),
    ))
    return Snapshot(1, CpuInfo(types=(tipo,), logical=logical))


class TestEje(unittest.TestCase):
    def setUp(self):
        try:
            from silux.ui.pages.caches import cache_axis
        except ImportError:                             # pragma: no cover
            self.skipTest("PySide6 no está instalado")
        self.axis = cache_axis

    def test_ordena_por_nucleo_para_juntar_hermanos_smt(self):
        # Con el orden natural (0..5) la L1 de las CPUs 0 y 3 saldría partida.
        self.assertEqual(self.axis(_snapshot()), [0, 3, 1, 4, 2, 5])

    def test_cada_instancia_queda_contigua_en_el_eje(self):
        from silux.ui.cachemap import _contiguous_runs

        eje = self.axis(_snapshot())
        posicion = {cpu: i for i, cpu in enumerate(eje)}
        cache = _snapshot().cpu.types[0].caches[0]
        for grupo in cache.instance_cpus:
            tramos = _contiguous_runs(sorted(posicion[c] for c in grupo))
            self.assertEqual(len(tramos), 1, f"{grupo} sale partida en {tramos}")


class TestAgrupado(unittest.TestCase):
    def setUp(self):
        try:
            from silux.ui.pages.caches import CachesPage
        except ImportError:                             # pragma: no cover
            self.skipTest("PySide6 no está instalado")
        self.page = CachesPage

    def test_cpu_homogenea_no_repite_filas(self):
        grupos = self.page._group(_snapshot())
        self.assertEqual(len(grupos), 2)
        self.assertEqual({k[2] for k in grupos}, {""})   # sin sufijo de tipo

    def test_cpu_hibrida_separa_por_tipo_de_nucleo(self):
        grupos = self.page._group(_snapshot(hybrid=True))
        self.assertEqual(len(grupos), 2)
        self.assertEqual({k[2] for k in grupos}, {"performance", "efficiency"})
        tamanos = {k[2]: c.size_bytes for k, c in grupos.items()}
        self.assertEqual(tamanos["performance"], 2 << 20)
        self.assertEqual(tamanos["efficiency"], 4 << 20)

    def test_the_l3_both_kinds_share_is_one(self):
        # A tester's i5-12450H: «31.7 MB de caché en total» and «8 cachés
        # distintas», with an «L3 P 12 MB» and an «L3 E 12 MB» that were the
        # same twelve threads' one L3. The topology is the one in that report.
        mib = 1 << 20
        pares = tuple((2 * i, 2 * i + 1) for i in range(4))
        sueltos = tuple((8 + i,) for i in range(4))
        l3 = Cache(3, "unified", 12 * mib, instances=1, shared_by=12,
                   instance_cpus=(tuple(range(12)),))
        tipos = (
            CpuType(key="performance", label="P", cores=4, threads=8, caches=(
                Cache(1, "data", 48 << 10, instances=4, shared_by=2, instance_cpus=pares),
                Cache(1, "instruction", 32 << 10, instances=4, shared_by=2, instance_cpus=pares),
                Cache(2, "unified", 1280 << 10, instances=4, shared_by=2, instance_cpus=pares),
                l3)),
            CpuType(key="efficiency", label="E", cores=4, threads=4, caches=(
                Cache(1, "data", 32 << 10, instances=4, shared_by=1, instance_cpus=sueltos),
                Cache(1, "instruction", 64 << 10, instances=4, shared_by=1, instance_cpus=sueltos),
                Cache(2, "unified", 2 * mib, instances=1, shared_by=4,
                      instance_cpus=(tuple(range(8, 12)),)),
                l3)),
        )
        grupos = self.page._group(Snapshot(1, CpuInfo(hybrid=True, types=tipos)))
        self.assertEqual(len(grupos), 7)
        terceras = [k for k in grupos if k[0] == 3]
        self.assertEqual(len(terceras), 1)
        self.assertEqual(terceras[0][2], "")              # no «P» or «E»: both
        total = sum(c.total_bytes for c in grupos.values())
        self.assertEqual(total, (192 + 128 + 128 + 256 + 5120 + 2048) * 1024 + 12 * mib)

    def test_etiquetas(self):
        self.assertEqual(self.page._label(1, "data", "", False), "L1 datos")
        self.assertEqual(self.page._label(3, "unified", "", False), "L3")
        self.assertEqual(self.page._label(2, "unified", "efficiency", True), "L2 E")


@unittest.skipUnless(__import__("importlib").util.find_spec("PySide6"), "sin PySide6")
class TestTabla(unittest.TestCase):
    """La tabla simple de la página de cachés."""

    @classmethod
    def setUpClass(cls):
        import os
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication
        cls.app = qt.app()

    def _table(self, filas: int):
        from silux.ui.widgets import Table

        tabla = Table(("Nivel", "Tamaño", "Total"), numeric=(False, True, True))
        tabla.set_rows([[f"L{i}", "32 KB", "192 KB"] for i in range(filas)])
        return tabla

    def test_el_alto_crece_con_las_filas(self):
        """Se calcula en vez de preguntar a Qt: su sizeHint se refresca en la
        pasada siguiente y la tabla se quedaba recortada a una línea."""
        una = self._table(1).height()
        seis = self._table(6).height()
        self.assertGreater(seis, una)
        self.assertGreater(seis - una, 60, "cinco filas tienen que notarse")

    def test_el_alto_no_depende_de_haberse_mostrado(self):
        tabla = self._table(4)
        antes = tabla.height()
        tabla.show()
        self.app.processEvents()
        self.assertEqual(tabla.height(), antes)

    def test_el_hueco_sobrante_va_detras_de_los_datos(self):
        # Si se estirase la primera columna, en pantalla completa las cifras
        # acabarían a un palmo del nombre.
        tabla = self._table(3)
        rejilla = tabla.widget().layout()
        self.assertEqual(rejilla.columnStretch(0), 0)
        self.assertEqual(rejilla.columnStretch(3), 1)


if __name__ == "__main__":
    unittest.main()


class TestEveryBlockSaysItsSize(unittest.TestCase):
    """A block of the cache map too narrow for its figure was left blank.
    The size goes in it, shorter, or once over its run of blocks («4 ×
    32K»), and every block has it in its tooltip."""

    @classmethod
    def setUpClass(cls):
        from silux.settings import Preferences
        from silux.ui import theme

        cls.app = qt.app()
        prefs = Preferences().normalized()
        theme.apply(cls.app, prefs.theme, prefs.density, prefs.font_scale)

    def _every_width(self, folder):
        from tests import pantalla
        from tests.test_equipos import shared_snapshot

        with pantalla.Ventana(shared_snapshot(folder)) as window:
            window.select_section("Cachés")
            cache_map = window.caches_page.map
            for width in (600, 760, 900):
                window.resize(width, 700)
                for _round in range(3):
                    self.app.processEvents()
                plan = cache_map.plan()
                for row, inner, instance in cache_map.blocks():
                    with self.subTest(width=width, row=row, cpus=instance[0]):
                        self.assertTrue(any(
                            index == row and area.left() <= inner.center().x() <= area.right()
                            for index, area, _text, _font, _pill in plan))
                        self.assertIn(instance[2].rstrip("KMB"), instance[3])


per_dump(TestEveryBlockSaysItsSize, "every_width", TestEveryBlockSaysItsSize._every_width)


class TestABlocksTooltip(unittest.TestCase):

    def test_hovering_a_narrow_block_says_its_size(self):
        from PySide6.QtCore import QEvent, QPoint
        from PySide6.QtGui import QHelpEvent
        from PySide6.QtWidgets import QToolTip

        from silux import render
        from tests import pantalla
        from tests.test_equipos import EQUIPOS, shared_snapshot

        app = qt.app()
        with pantalla.Ventana(shared_snapshot(EQUIPOS / "i7-12700kf")) as window:
            window.select_section("Cachés")
            window.resize(760, 700)
            for _round in range(3):
                app.processEvents()
            cache_map = window.caches_page.map
            _row, inner, instance = next(b for b in cache_map.blocks() if b[2][0] == (16,))
            point = inner.center().toPoint()
            cache_map.event(QHelpEvent(QEvent.Type.ToolTip, point, cache_map.mapToGlobal(point)))
            self.assertEqual(QToolTip.text(), instance[3])
            self.assertIn(render.cache_size(32 * 1024), QToolTip.text())
            QToolTip.hideText()
            cache_map.event(QHelpEvent(QEvent.Type.ToolTip, QPoint(1, 1), cache_map.mapToGlobal(QPoint(1, 1))))
