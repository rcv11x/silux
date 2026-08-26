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
