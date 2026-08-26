"""Identidad del procesador donde no hay CPUID.

Un aarch64 no tiene cadena de marca grabada en el silicio ni familia ni
modelo al modo de x86. Tiene otra cosa: dos números en MIDR_EL1 que dicen
quién hizo el núcleo y cuál es. Lo que se prueba aquí es que de esos dos
números sale un nombre, y que cuando no salga se diga el número en vez de
inventarse uno.

Las muestras son /proc/cpuinfo de máquinas reales. En esta máquina no hay
ningún ARM, así que la llamada al sistema es lo único que no se ejerce.
"""

import pathlib
import unittest
from unittest import mock

from silux import db
from silux.providers import armcpu
from silux.providers.base import Draft
from silux.providers.sysfs_cpu import _por_nucleo_arm

FIXTURES = pathlib.Path(__file__).parent / "fixtures" / "arm"


def _con(nombre, arm=True):
    """Pone un /proc/cpuinfo de mentira y dice que la máquina es aarch64."""
    texto = (FIXTURES / nombre).read_text(encoding="utf-8")
    return (mock.patch.object(pathlib.Path, "read_text", return_value=texto),
            mock.patch.object(armcpu.platform, "machine",
                              return_value="aarch64" if arm else "x86_64"))


class TestLectura(unittest.TestCase):
    def test_separa_los_bloques_por_cpu(self):
        con_fichero, con_arch = _con("unisoc-t606.txt")
        with con_fichero, con_arch:
            self.assertEqual(len(armcpu._cpuinfo()), 4)

    def test_saca_el_midr_de_cada_una(self):
        con_fichero, con_arch = _con("unisoc-t606.txt")
        with con_fichero, con_arch:
            midr = armcpu.midr_por_cpu()
        self.assertEqual(midr[0], (0x41, 0xd05))
        self.assertEqual(midr[7], (0x41, 0xd0b))

    def test_respeta_la_numeracion_del_kernel(self):
        """Los índices son los del kernel, no la posición en el fichero."""
        con_fichero, con_arch = _con("unisoc-t606.txt")
        with con_fichero, con_arch:
            midr = armcpu.midr_por_cpu()
        self.assertEqual(sorted(midr), [0, 1, 6, 7])


class TestIdentidad(unittest.TestCase):
    def _identidad(self, nombre, cpus=(0,)):
        con_fichero, con_arch = _con(nombre)
        draft = Draft()
        draft.type_for("general")["cpus"] = list(cpus)
        with con_fichero, con_arch:
            armcpu.ArmIdentity().collect(draft)
        return draft.types["general"]

    def test_pone_el_nombre_del_nucleo(self):
        entry = self._identidad("raspberry-pi-4.txt")
        self.assertEqual(entry["brand"], "ARM Cortex-A72 r0p3")
        self.assertEqual(entry["codename"], "Cortex-A72")
        self.assertEqual(entry["vendor"], "ARM")

    def test_la_revision_va_como_la_nombra_arm(self):
        """rXpY: es como ARM numera sus revisiones y sus erratas."""
        self.assertIn("r0p3", self._identidad("raspberry-pi-4.txt")["brand"])

    def test_un_nucleo_que_no_esta_en_la_tabla_sale_por_su_numero(self):
        entry = self._identidad("desconocido.txt")
        self.assertEqual(entry["brand"], "ARM núcleo 0xfab r1p2")
        self.assertIsNone(entry["codename"])

    def test_las_banderas_salen_como_las_nombra_el_kernel(self):
        """Crudas en el modelo. Ponerles nombre es cosa de render."""
        entry = self._identidad("raspberry-pi-4.txt")
        self.assertIn("crc32", entry["features"])
        self.assertIn("asimd", entry["features"])

    def test_no_se_inventa_una_familia_ni_un_modelo(self):
        """En ARM no existen, y un None es más honesto que un cero."""
        entry = self._identidad("raspberry-pi-4.txt")
        self.assertIsNone(entry.get("disp_family"))
        self.assertIsNone(entry.get("disp_model"))

    def test_retira_la_nota_de_que_falta_cpuid(self):
        con_fichero, con_arch = _con("raspberry-pi-4.txt")
        draft = Draft()
        draft.type_for("general")["cpus"] = [0]
        from silux.model import Need
        draft.note("cpu.identity", Need.PLATFORM, "CPUID es una instrucción de x86")
        with con_fichero, con_arch:
            armcpu.ArmIdentity().collect(draft)
        self.assertEqual([n for n in draft.notes if n.path == "cpu.identity"], [])


class TestBigLittle(unittest.TestCase):
    """Un big.LITTLE es tan híbrido como un Intel de 12ª generación."""

    def test_separa_los_grandes_de_los_pequenos(self):
        con_fichero, con_arch = _con("unisoc-t606.txt")
        with con_fichero, con_arch:
            reparto = _por_nucleo_arm((0, 1, 6, 7))
        self.assertEqual(reparto, {"performance": [6, 7], "efficiency": [0, 1]})

    def test_un_solo_tipo_no_se_toca(self):
        """Con todos los núcleos iguales manda el reparto de siempre."""
        con_fichero, con_arch = _con("raspberry-pi-4.txt")
        with con_fichero, con_arch:
            self.assertEqual(_por_nucleo_arm((0, 1)), {})

    def test_en_x86_no_se_mete(self):
        con_fichero, con_arch = _con("unisoc-t606.txt", arm=False)
        with con_fichero, con_arch:
            self.assertEqual(_por_nucleo_arm((0, 1, 6, 7)), {})


class TestTabla(unittest.TestCase):
    def test_el_numero_de_pieza_solo_vale_dentro_de_su_fabricante(self):
        """0xd01 es un Cortex-A32 en ARM y un TaiShan en HiSilicon."""
        self.assertEqual(db.arm_part(0x41, 0xd01), "Cortex-A32")
        self.assertEqual(db.arm_part(0x48, 0xd01), "TaiShan v110")

    def test_lo_que_no_conoce_no_se_lo_inventa(self):
        self.assertIsNone(db.arm_part(0x41, 0xfff))
        self.assertIsNone(db.arm_implementer(0x99))

    def test_cubre_los_de_uso_corriente(self):
        for impl, part, esperado in [
            (0x41, 0xd03, "Cortex-A53"), (0x41, 0xd08, "Cortex-A72"),
            (0x41, 0xd0c, "Neoverse-N1"), (0x41, 0xd82, "Cortex-X4"),
            (0x51, 0x804, "Kryo 4xx Gold"), (0x61, 0x023, "Firestorm"),
            (0xc0, 0xac3, "Ampere-1"), (0x4e, 0x004, "Carmel"),
        ]:
            self.assertEqual(db.arm_part(impl, part), esperado)


class TestInstrucciones(unittest.TestCase):
    """La misma bandera no es la misma instrucción en las dos arquitecturas."""

    def _tipo(self, arquitectura, *banderas):
        from silux.model import Clocks, CpuType
        return CpuType(key="general", label="general", cores=4, threads=4,
                       architecture=arquitectura, features=banderas,
                       clocks=Clocks())

    def test_el_aes_de_un_arm_no_es_aes_ni(self):
        """AES-NI es de Intel. Un aarch64 trae las extensiones de ARMv8."""
        from silux import render
        texto = render.instructions(self._tipo("aarch64", "aes", "asimd"))
        self.assertIn("AES", texto)
        self.assertNotIn("AES-NI", texto)

    def test_y_en_x86_sigue_siendo_aes_ni(self):
        from silux import render
        self.assertIn("AES-NI", render.instructions(self._tipo("x86_64", "aes")))

    def test_las_de_arm_salen_con_su_nombre(self):
        from silux import render
        texto = render.instructions(self._tipo("aarch64", "asimd", "sve2",
                                               "atomics", "asimddp"))
        for esperado in ("NEON", "SVE2", "LSE", "DotProd"):
            self.assertIn(esperado, texto)

    def test_no_se_cuela_ninguna_de_x86_en_un_arm(self):
        from silux import render
        texto = render.instructions(self._tipo("aarch64", "aes", "sha2", "crc32",
                                               "asimd", "fphp", "atomics"))
        for x86 in ("AVX", "SSE", "MMX", "AES-NI", "VT-x"):
            self.assertNotIn(x86, texto)


class TestEtiquetas(unittest.TestCase):
    def test_en_arm_los_nucleos_se_llaman_como_los_llama_arm(self):
        """«Núcleo E» es de Intel; en un teléfono nadie lo reconoce."""
        from silux import render
        from silux.model import Clocks, CpuType
        grande = CpuType(key="performance", label="", cores=4, threads=4,
                         architecture="aarch64", clocks=Clocks())
        self.assertIn("big", render.core_type_label(grande, hybrid=True))
        self.assertNotIn("Núcleos P", render.core_type_label(grande, hybrid=True))

    def test_y_en_x86_siguen_siendo_P_y_E(self):
        from silux import render
        from silux.model import Clocks, CpuType
        grande = CpuType(key="performance", label="", cores=8, threads=16,
                         architecture="x86_64", clocks=Clocks())
        self.assertIn("Núcleos P", render.core_type_label(grande, hybrid=True))


if __name__ == "__main__":
    unittest.main()
