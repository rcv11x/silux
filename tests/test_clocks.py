"""El reloj base, el techo del silicio y el BCLK fuera del Intel moderno.

CPUID 0x16 solo responde en Intel de Skylake en adelante. El resto del parque
—todo AMD, los Intel anteriores, los Core 2— tiene que salir de ACPI CPPC o de
la cadena de marca. Aquí se montan esos árboles de /sys a mano para comprobar
que cada máquina saca lo que puede y calla lo que no.
"""

import pathlib
import tempfile
import unittest
from unittest import mock

from cpuz.model import Clocks
from cpuz.providers import cppc
from cpuz.providers.base import Draft


def _write(path: pathlib.Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"{value}\n", encoding="utf-8")


class BancoDeRelojes(unittest.TestCase):
    """Monta un /sys de mentira y pasa el proveedor por encima."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self._tmp.name)
        patch = mock.patch.object(cppc, "SYS_CPU", str(self.root))
        patch.start()
        self.addCleanup(patch.stop)
        self.addCleanup(self._tmp.cleanup)

    def cppc(self, cpu: int = 0, **campos: int) -> None:
        for nombre, valor in campos.items():
            _write(self.root / f"cpu{cpu}" / "acpi_cppc" / nombre, str(valor))

    def cpufreq(self, cpu: int = 0, **campos: int) -> None:
        for nombre, valor in campos.items():
            _write(self.root / f"cpu{cpu}" / "cpufreq" / nombre, str(valor))

    def recolectar(self, clocks: Clocks | None = None, brand: str | None = None,
                   cpus=(0,), architecture: str | None = "x86_64") -> tuple[Clocks, Draft]:
        draft = Draft()
        entry = draft.type_for("general")
        entry["cpus"] = list(cpus)
        entry["architecture"] = architecture
        if clocks is not None:
            entry["clocks"] = clocks
        if brand is not None:
            entry["brand"] = brand
        cppc.CppcClocks().collect(draft)
        return draft.types["general"].get("clocks") or Clocks(), draft


class TestAmdConCppc(BancoDeRelojes):
    """Un Ryzen 7 5800X3D: 3,4 GHz de base y 4,55 de boost, sin hoja 0x16."""

    def setUp(self):
        super().setUp()
        self.cppc(nominal_freq=3401, lowest_freq=550, nominal_perf=124, highest_perf=181)
        self.cpufreq(amd_pstate_max_freq=4552952)

    def test_base_sale_del_reloj_nominal(self):
        clocks, _ = self.recolectar(Clocks(min_hz=575_976_000, max_hz=4_552_952_000))
        self.assertEqual(clocks.base_hz, 3_401_000_000)

    def test_el_bclk_se_deduce_en_cien_megahercios(self):
        clocks, _ = self.recolectar()
        # 3401 / 34 = 100,03 MHz: el multiplicador base sale redondo.
        self.assertAlmostEqual(clocks.bus_hz / 1_000_000, 100, delta=0.1)
        self.assertEqual(clocks.base_multiplier, 34.0)

    def test_el_techo_del_silicio_lo_da_amd_pstate(self):
        clocks, _ = self.recolectar()
        self.assertEqual(clocks.max_turbo_hz, 4_552_952_000)
        self.assertEqual(clocks.max_turbo_multiplier, 45.5)

    def test_con_prefcore_no_se_usa_la_escala_inflada(self):
        # highest_perf/nominal_perf da 181/124 = 4,96 GHz, que no existe: con
        # núcleos preferentes ese campo lleva el ranking, no el rendimiento.
        clocks, _ = self.recolectar()
        self.assertLess(clocks.max_turbo_hz, 4_600_000_000)

    def test_no_deja_notas_cuando_lo_rellena_todo(self):
        _, draft = self.recolectar()
        self.assertEqual(draft.notes, [])


class TestCppcSinAmdPstate(BancoDeRelojes):
    """Sin amd-pstate el techo sale de la escala de rendimiento de CPPC."""

    def test_el_techo_sale_de_la_escala_de_perf(self):
        self.cppc(nominal_freq=3400, nominal_perf=100, highest_perf=130)
        clocks, _ = self.recolectar()
        self.assertEqual(clocks.max_turbo_hz, 4_420_000_000)

    def test_un_techo_por_debajo_de_la_base_se_descarta(self):
        self.cppc(nominal_freq=3400, nominal_perf=200, highest_perf=100)
        clocks, _ = self.recolectar()
        self.assertIsNone(clocks.max_turbo_hz)
        self.assertEqual(clocks.base_hz, 3_400_000_000)

    def test_un_firmware_que_deja_los_campos_a_cero_no_cuenta(self):
        self.cppc(nominal_freq=0, nominal_perf=0, highest_perf=0)
        clocks, draft = self.recolectar()
        self.assertIsNone(clocks.base_hz)
        self.assertIsNone(clocks.bus_hz)
        self.assertTrue(draft.notes)


class TestNoPisaLoQueYaHay(BancoDeRelojes):
    """En un Intel con hoja 0x16, CPUID va primero y esto no toca nada."""

    def test_respeta_los_valores_de_cpuid(self):
        self.cppc(nominal_freq=2900, nominal_perf=100, highest_perf=148)
        ya = Clocks(base_hz=2_900_000_000, max_turbo_hz=4_300_000_000,
                    bus_hz=100_000_000)
        clocks, draft = self.recolectar(ya)
        self.assertEqual(clocks.base_hz, 2_900_000_000)
        self.assertEqual(clocks.max_turbo_hz, 4_300_000_000)
        self.assertEqual(clocks.bus_hz, 100_000_000)
        self.assertEqual(draft.notes, [])

    def test_completa_solo_el_hueco_que_falta(self):
        self.cppc(nominal_freq=2900, nominal_perf=100, highest_perf=148)
        clocks, _ = self.recolectar(Clocks(base_hz=2_900_000_000))
        self.assertEqual(clocks.base_hz, 2_900_000_000)
        self.assertEqual(clocks.max_turbo_hz, 4_292_000_000)


class TestSinCppc(BancoDeRelojes):
    """Un Core 2 o un Phenom: ni 0x16 ni CPPC, solo la cadena de marca."""

    def test_la_base_sale_del_nombre_del_procesador(self):
        clocks, _ = self.recolectar(brand="Intel(R) Core(TM)2 Duo CPU E8400 @ 3.00GHz")
        self.assertEqual(clocks.base_hz, 3_000_000_000)

    def test_el_bclk_no_se_inventa_sin_cppc(self):
        # El E8400 corre a 333 MHz de FSB por 9. Suponer 100 MHz porque 3000
        # divide bien sería dar un multiplicador de 30 que no existe.
        clocks, draft = self.recolectar(brand="Intel(R) Core(TM)2 Duo CPU E8400 @ 3.00GHz")
        self.assertIsNone(clocks.bus_hz)
        self.assertEqual([n.path for n in draft.notes], ["cpu.clocks.bus_hz"])

    def test_una_marca_en_megahercios(self):
        clocks, _ = self.recolectar(brand="Intel(R) Pentium(R) 4 CPU 2800MHz")
        self.assertIsNone(clocks.base_hz)   # sin «@» no hay nada que leer
        clocks, _ = self.recolectar(brand="Intel(R) Pentium(R) 4 CPU @ 2800MHz")
        self.assertEqual(clocks.base_hz, 2_800_000_000)

    def test_un_ryzen_no_lleva_la_frecuencia_en_el_nombre(self):
        clocks, draft = self.recolectar(brand="AMD Ryzen 7 5800X3D 8-Core Processor")
        self.assertIsNone(clocks.base_hz)
        self.assertEqual({n.path for n in draft.notes},
                         {"cpu.clocks.base_hz", "cpu.clocks.bus_hz"})


class TestFueraDeX86(BancoDeRelojes):
    """En un ARM con CPPC hay reloj nominal, pero no hay BCLK que deducir."""

    def test_el_reloj_base_si_se_aprovecha(self):
        self.cppc(nominal_freq=2400, nominal_perf=100, highest_perf=120)
        clocks, _ = self.recolectar(architecture="aarch64")
        self.assertEqual(clocks.base_hz, 2_400_000_000)

    def test_no_se_inventa_un_multiplicador_de_cien_megahercios(self):
        self.cppc(nominal_freq=2400, nominal_perf=100, highest_perf=120)
        clocks, draft = self.recolectar(architecture="aarch64")
        self.assertIsNone(clocks.bus_hz)
        # Tampoco se deja nota: allí el dato no es que falte, es que no existe.
        self.assertEqual(draft.notes, [])


class TestRelojDeReferencia(unittest.TestCase):
    """El BCLK deducido, en aislado."""

    def test_multiplicadores_de_cuarto_en_cuarto(self):
        self.assertAlmostEqual(cppc._reloj_de_referencia(3_401_000_000) / 1e6, 100.03, places=1)
        self.assertEqual(cppc._reloj_de_referencia(2_900_000_000), 100_000_000)
        self.assertAlmostEqual(cppc._reloj_de_referencia(3_333_000_000) / 1e6, 100.24, places=1)

    def test_lo_que_no_cuadra_se_deja_vacio(self):
        # Un reloj tan bajo que el multiplicador no llega a 1.
        self.assertIsNone(cppc._reloj_de_referencia(50_000_000))


class TestVariosTiposDeNucleo(BancoDeRelojes):
    """En una híbrida cada tipo pregunta por su propio núcleo."""

    def test_cada_tipo_lee_su_lider(self):
        self.cppc(cpu=0, nominal_freq=3600, nominal_perf=100, highest_perf=140)
        self.cppc(cpu=16, nominal_freq=2700, nominal_perf=100, highest_perf=141)

        draft = Draft()
        for clave, cpus in (("performance", list(range(16))), ("efficiency", [16, 17, 18, 19])):
            draft.type_for(clave).update(cpus=cpus, architecture="x86_64")
        cppc.CppcClocks().collect(draft)

        self.assertEqual(draft.types["performance"]["clocks"].base_hz, 3_600_000_000)
        self.assertEqual(draft.types["efficiency"]["clocks"].base_hz, 2_700_000_000)


if __name__ == "__main__":
    unittest.main()
