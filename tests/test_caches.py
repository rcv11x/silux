"""El eje del mapa de cachés y el agrupado por nivel."""

import unittest

from silux.model import Cache, CpuInfo, CpuType, LogicalCpu, Snapshot


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
        from silux.ui.widgets import _contiguous_runs

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
        cls.app = QApplication.instance() or QApplication([])

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
