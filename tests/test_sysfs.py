"""Los proveedores de sysfs, contra un /sys falso.

Esto es lo que compra separar la lectura del formateo: se puede montar el
árbol de ficheros de una CPU que no se tiene delante —aquí una Intel híbrida
con núcleos P y E— y comprobar que el proveedor la interpreta bien. Sin esto,
soportar CPUs híbridas sería programar a ciegas y esperar informes de fallo.
"""

import pathlib
import tempfile
import unittest
from unittest import mock

from silux.providers import sysfs_cpu
from silux.providers.base import Draft, parse_cpu_list, parse_size


def _write(path: pathlib.Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"{value}\n", encoding="utf-8")


def build_hybrid_sysfs(root: pathlib.Path) -> None:
    """Un Core i7-12700K de mentira: 8 núcleos P con SMT y 4 E sin él."""
    p_cpus = list(range(0, 16))          # 8 núcleos P × 2 hilos
    e_cpus = list(range(16, 20))         # 4 núcleos E, un hilo cada uno

    _write(root / "online", "0-19")
    _write(root / "cpu_core" / "cpus", "0-15")
    _write(root / "cpu_atom" / "cpus", "16-19")

    for cpu in p_cpus + e_cpus:
        base = root / f"cpu{cpu}"
        is_p = cpu in p_cpus
        core_id = cpu // 2 if is_p else 8 + (cpu - 16)
        siblings = f"{core_id * 2},{core_id * 2 + 1}" if is_p else str(cpu)

        _write(base / "topology" / "physical_package_id", "0")
        _write(base / "topology" / "core_id", str(core_id))
        _write(base / "topology" / "thread_siblings_list", siblings)
        _write(base / "microcode" / "version", "0x2c")

        freq = base / "cpufreq"
        _write(freq / "cpuinfo_min_freq", "800000")
        _write(freq / "cpuinfo_max_freq", "5000000" if is_p else "3800000")
        _write(freq / "base_frequency", "3600000" if is_p else "2700000")
        _write(freq / "scaling_cur_freq", "4200000" if is_p else "3000000")
        _write(freq / "scaling_driver", "intel_pstate")
        _write(freq / "scaling_governor", "powersave")

        caches = [
            ("1", "Data", "48K", "12", "64", "64", siblings),
            ("1", "Instruction", "32K", "8", "64", "64", siblings),
            ("2", "Unified", "1280K" if is_p else "2048K", "10", "64", "2048", siblings),
            ("3", "Unified", "25600K", "10", "64", "40960", "0-19"),
        ]
        # La L2 de los núcleos E es una sola para los cuatro.
        if not is_p:
            caches[2] = ("2", "Unified", "2048K", "16", "64", "2048", "16-19")

        for index, (level, kind, size, ways, line, sets, shared) in enumerate(caches):
            entry = base / "cache" / f"index{index}"
            _write(entry / "level", level)
            _write(entry / "type", kind)
            _write(entry / "size", size)
            _write(entry / "ways_of_associativity", ways)
            _write(entry / "coherency_line_size", line)
            _write(entry / "number_of_sets", sets)
            _write(entry / "shared_cpu_list", shared)


class TestAyudasDeLectura(unittest.TestCase):
    def test_listas_de_cpu(self):
        self.assertEqual(parse_cpu_list("0-3,8,10-11"), (0, 1, 2, 3, 8, 10, 11))
        self.assertEqual(parse_cpu_list(""), ())
        self.assertEqual(parse_cpu_list("basura"), ())

    def test_tamanos(self):
        self.assertEqual(parse_size("32K"), 32768)
        self.assertEqual(parse_size("12288K"), 12582912)
        self.assertEqual(parse_size("8M"), 8388608)
        self.assertIsNone(parse_size(None))


class TestCpuHibrida(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self._tmp.name)
        build_hybrid_sysfs(self.root)

        self._patches = [
            mock.patch.object(sysfs_cpu, "SYS_CPU", str(self.root)),
            mock.patch.object(sysfs_cpu, "HYBRID_PMUS", (
                (str(self.root / "cpu_core"), "performance"),
                (str(self.root / "cpu_atom"), "efficiency"),
            )),
        ]
        for patch in self._patches:
            patch.start()
        self.addCleanup(self._tmp.cleanup)
        for patch in self._patches:
            self.addCleanup(patch.stop)

    def _recolectar(self) -> Draft:
        draft = Draft()
        sysfs_cpu.SysfsTopology().collect(draft)
        sysfs_cpu.SysfsClocks().collect(draft)
        return draft

    def test_separa_nucleos_p_y_e(self):
        snapshot = self._recolectar().freeze()
        self.assertTrue(snapshot.cpu.hybrid)
        self.assertEqual({t.key for t in snapshot.cpu.types}, {"performance", "efficiency"})

        by_key = {t.key: t for t in snapshot.cpu.types}
        self.assertEqual((by_key["performance"].cores, by_key["performance"].threads), (8, 16))
        self.assertEqual((by_key["efficiency"].cores, by_key["efficiency"].threads), (4, 4))
        self.assertTrue(by_key["performance"].smt)
        self.assertFalse(by_key["efficiency"].smt)

    def test_totales(self):
        cpu = self._recolectar().freeze().cpu
        self.assertEqual(cpu.total_cores, 12)
        self.assertEqual(cpu.total_threads, 20)
        self.assertEqual(cpu.sockets, 1)
        self.assertEqual(len(cpu.logical), 20)

    def test_cache_l2_distinta_por_tipo(self):
        by_key = {t.key: t for t in self._recolectar().freeze().cpu.types}
        l2_p = by_key["performance"].cache_at(2)
        l2_e = by_key["efficiency"].cache_at(2)
        self.assertEqual(l2_p.size_bytes, 1280 * 1024)
        self.assertEqual(l2_p.instances, 8)          # una por núcleo P
        self.assertEqual(l2_e.size_bytes, 2048 * 1024)
        self.assertEqual(l2_e.instances, 1)          # compartida por los cuatro E
        self.assertEqual(l2_e.shared_by, 4)

    def test_l3_es_unica_y_compartida(self):
        l3 = self._recolectar().freeze().cpu.types[0].cache_at(3)
        self.assertEqual(l3.instances, 1)
        self.assertEqual(l3.shared_by, 20)

    def test_frecuencias_por_tipo(self):
        by_key = {t.key: t for t in self._recolectar().freeze().cpu.types}
        self.assertEqual(by_key["performance"].clocks.current_hz, 4_200_000_000)
        self.assertEqual(by_key["performance"].clocks.max_hz, 5_000_000_000)
        self.assertEqual(by_key["efficiency"].clocks.current_hz, 3_000_000_000)
        self.assertEqual(by_key["efficiency"].clocks.max_hz, 3_800_000_000)

    def test_sysfs_vacio_no_revienta(self):
        with tempfile.TemporaryDirectory() as vacio:
            with mock.patch.object(sysfs_cpu, "SYS_CPU", vacio), \
                 mock.patch.object(sysfs_cpu, "HYBRID_PMUS", ()):
                draft = Draft()
                sysfs_cpu.SysfsTopology().collect(draft)
                snapshot = draft.freeze()
        self.assertEqual(len(snapshot.cpu.types), 1)   # cae a un único tipo genérico


if __name__ == "__main__":
    unittest.main()


class TestRyzenDeDosChiplets(unittest.TestCase):
    """Un 7950X3D: dos CCD, y el V-Cache apilado sobre uno solo.

    La mitad de los núcleos ve 96 MB de L3 y la otra mitad 32. No es un
    detalle de ficha técnica: es la razón de ser de la pieza, y de qué chiplet
    coja el planificador depende que un juego rinda como el modelo caro o como
    el barato. No hay ninguna de estas aquí, así que se monta su sysfs.
    """

    L3_GRANDE = 96 * 1024 * 1024
    L3_NORMAL = 32 * 1024 * 1024

    def setUp(self):
        import tempfile
        self._tmp = tempfile.TemporaryDirectory()
        self.raiz = pathlib.Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)
        self._montar()

    def _montar(self, asimetrica: bool = True) -> None:
        for cpu in range(32):
            ccd0 = cpu < 16
            base = self.raiz / f"cpu{cpu}" / "cache"
            pareja = f"{min(cpu, cpu ^ 1)},{max(cpu, cpu ^ 1)}"
            niveles = [(1, "Data", "32K", 8), (1, "Instruction", "32K", 8),
                       (2, "Unified", "1024K", 8)]
            for idx, (nivel, tipo, tam, vias) in enumerate(niveles):
                d = base / f"index{idx}"
                _write(d / "level", nivel)
                _write(d / "type", tipo)
                _write(d / "size", tam)
                _write(d / "ways_of_associativity", vias)
                _write(d / "coherency_line_size", 64)
                _write(d / "number_of_sets", 64)
                _write(d / "shared_cpu_list", pareja)
            d = base / "index3"
            grande = ccd0 or not asimetrica
            _write(d / "level", 3)
            _write(d / "type", "Unified")
            _write(d / "size", "98304K" if grande else "32768K")
            _write(d / "ways_of_associativity", 16)
            _write(d / "coherency_line_size", 64)
            _write(d / "number_of_sets", 16384 if grande else 8192)
            _write(d / "shared_cpu_list", "0-15" if ccd0 else "16-31")

    def _caches(self):
        from silux.providers import sysfs_cpu

        with mock.patch.object(sysfs_cpu, "SYS_CPU", str(self.raiz)):
            return sysfs_cpu.SysfsTopology._caches_for(list(range(32)))

    def test_las_dos_l3_salen_por_separado(self):
        """Deduplicar por nivel se quedaba con la primera que llegara."""
        ele3 = [c for c in self._caches() if c.level == 3]
        self.assertEqual(len(ele3), 2)
        self.assertEqual({c.size_bytes for c in ele3},
                         {self.L3_GRANDE, self.L3_NORMAL})

    def test_cada_l3_sabe_qué_nucleos_la_ven(self):
        ele3 = {c.size_bytes: c for c in self._caches() if c.level == 3}
        self.assertEqual(ele3[self.L3_GRANDE].instance_cpus, (tuple(range(16)),))
        self.assertEqual(ele3[self.L3_NORMAL].instance_cpus, (tuple(range(16, 32)),))

    def test_un_ryzen_simetrico_sigue_teniendo_una_sola_l3(self):
        """Un 7950X normal lleva 32 MB en cada chiplet: mismo tamaño, dos
        instancias, una sola fila."""
        self._montar(asimetrica=False)
        ele3 = [c for c in self._caches() if c.level == 3]
        self.assertEqual(len(ele3), 1)
        self.assertEqual(ele3[0].instances, 2)

    def _tipo(self, marca: str = "AMD Ryzen 9 7950X3D 16-Core Processor"):
        from silux.model import CpuType

        return CpuType(key="general", label="general", brand=marca,
                       caches=tuple(self._caches()))

    def test_se_dice_qué_nucleos_llevan_la_caché_grande(self):
        from silux import render

        frase = render.l3_asimetrica(self._tipo())
        self.assertIn("96 MB", frase)
        self.assertIn("0-15", frase)
        self.assertIn("32 MB", frase)
        self.assertIn("16-31", frase)

    def test_el_vcache_lo_confirma_el_nombre_y_no_el_tamaño(self):
        """La L3 crece por otros motivos según la familia: quien dice que es
        V-Cache es el fabricante en la cadena de marca."""
        from silux import render

        self.assertIn("V-Cache", render.l3_asimetrica(self._tipo()))
        sin_marca = render.l3_asimetrica(self._tipo("Procesador genérico"))
        self.assertIn("96 MB", sin_marca)
        self.assertNotIn("V-Cache", sin_marca)

    def test_un_ryzen_simetrico_no_tiene_nada_que_explicar(self):
        from silux import render

        self._montar(asimetrica=False)
        self.assertIsNone(render.l3_asimetrica(self._tipo("AMD Ryzen 9 7950X")))

    def test_la_etiqueta_de_vcache_sale_del_nombre(self):
        from silux import render

        self.assertEqual(render.vcache(self._tipo()), "3D V-Cache · 96 MB de L3")
        self.assertIsNone(render.vcache(self._tipo("AMD Ryzen 9 7950X")))
