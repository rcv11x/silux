"""Lo que enseñaron las capturas de equipos que no son el del autor.

Un Xeon E5-2650 v2 con una GTX 1660 Ti, y un portátil Ryzen 7445HS con una
Radeon 740M integrada y una RTX 3050 dedicada. Cada caso de aquí es un dato
que salía mal en una de las dos máquinas y que desde la del autor no se
podía ver, porque su equipo no tiene ni dos gráficas, ni DDR3, ni Gentoo.
"""

import unittest
from unittest import mock

from silux import render
from silux.providers import drm, system
from silux.providers.base import Draft


class TestOsRelease(unittest.TestCase):
    """Gentoo entrecomilla con comillas simples y es igual de válido."""

    def test_quita_las_comillas_simples(self):
        self.assertEqual(system._desentrecomillar("'Gentoo Linux'"), "Gentoo Linux")

    def test_y_las_dobles_de_siempre(self):
        self.assertEqual(system._desentrecomillar('"Debian GNU/Linux"'),
                         "Debian GNU/Linux")

    def test_sin_comillas_no_toca_nada(self):
        self.assertEqual(system._desentrecomillar("CachyOS"), "CachyOS")

    def test_una_comilla_suelta_dentro_se_respeta(self):
        self.assertEqual(system._desentrecomillar('"L\'Autre"'), "L'Autre")

    def test_lee_un_fichero_de_gentoo_entero(self):
        contenido = ("NAME='Gentoo Linux'\n"
                     "ID='gentoo'\n"
                     "PRETTY_NAME='Gentoo Linux'\n"
                     "VERSION='2.18'\n"
                     "# un comentario\n"
                     "ANSI_COLOR='1;32'\n")
        with mock.patch("builtins.open", mock.mock_open(read_data=contenido)):
            valores = system._os_release()
        self.assertEqual(valores["NAME"], "Gentoo Linux")
        self.assertEqual(valores["VERSION"], "2.18")
        self.assertNotIn("#", "".join(valores))


class TestCompilacionDelKernel(unittest.TestCase):
    """El renglón repetía el kernel cuando no lo había compilado gcc."""

    def _build(self, texto):
        with mock.patch.object(system, "read_text", return_value=texto):
            return system.SystemIdentity._kernel_build()

    def test_no_repite_el_kernel(self):
        salida = self._build(
            "Linux version 6.18.35-gentoo-dist-bin (root@gentoo) "
            "(gcc (Gentoo 14.3.0 p2) 14.3.0, GNU ld (Gentoo 2.44) 2.44) "
            "#1 SMP PREEMPT_DYNAMIC Tue Aug 26 20:11:03 CEST 2026")
        self.assertNotIn("Linux version", salida)
        self.assertIn("#1 SMP", salida)

    def test_reconoce_clang(self):
        salida = self._build(
            "Linux version 7.2.0-1-cachyos (linux-cachyos@cachyos) "
            "(clang version 22.1.8, LLD 22.1.8) #1 SMP PREEMPT_DYNAMIC Thu, "
            "20 Aug 2026 16:18:38 +0000")
        self.assertIn("clang 22.1.8", salida)

    def test_y_gcc_con_parentesis_dentro(self):
        salida = self._build(
            "Linux version 6.8.0-31-generic (buildd@lcy02) "
            "(x86_64-linux-gnu-gcc-13 (Ubuntu 13.2.0) 13.2.0, GNU ld 2.42) "
            "#31-Ubuntu SMP PREEMPT_DYNAMIC Sat Apr 20 00:40:06 UTC 2024")
        self.assertIn("gcc 13.2.0", salida)

    def test_sin_numero_de_compilacion_no_se_inventa(self):
        self.assertIsNone(self._build("Linux version 5.4.0-custom"))


class TestVentilador(unittest.TestCase):
    """Salía «—   (0.0 %)»: un dato ausente al lado de otro que decía cero."""

    def test_parado_se_dice_parado(self):
        self.assertEqual(render.fan(None, 0.0), "parado")
        self.assertEqual(render.fan(0, None), "parado")

    def test_con_las_dos_cifras_van_las_dos(self):
        self.assertEqual(render.fan(1200, 45.0), "1200 RPM   (45.0 %)")

    def test_con_una_sola_va_esa(self):
        self.assertEqual(render.fan(1200, None), "1200 RPM")
        self.assertEqual(render.fan(None, 45.0), "45.0 %")

    def test_sin_ninguna_es_un_dato_que_falta(self):
        self.assertEqual(render.fan(None, None), render.DASH)


class TestNombreDeLaIntegrada(unittest.TestCase):
    """pci.ids llama «HawkPoint2» al 1002:1901, sin nombre comercial."""

    def test_lo_saca_de_la_marca_del_procesador(self):
        self.assertEqual(
            drm._IGPU_EN_LA_MARCA.search(
                "AMD Ryzen 7 7445HS w/ Radeon 740M Graphics").group(1).strip(),
            "Radeon 740M")

    def test_un_procesador_sin_grafica_no_dice_nada(self):
        self.assertIsNone(drm._IGPU_EN_LA_MARCA.search(
            "AMD Ryzen 7 5800X3D 8-Core Processor"))

    def test_una_radeon_generica_no_aporta_modelo(self):
        """«with Radeon Graphics» no dice cuál es, así que no se usa."""
        self.assertIsNone(drm._IGPU_EN_LA_MARCA.search(
            "AMD Ryzen 5 5600G with Radeon Graphics"))

    def test_busca_en_los_tipos_de_nucleo_del_borrador(self):
        draft = Draft()
        draft.type_for("general")["brand"] = "AMD Ryzen 7 7445HS w/ Radeon 740M Graphics"
        self.assertEqual(drm._igpu_de_la_cpu(draft), "Radeon 740M")


class TestConsejoDelSpd(unittest.TestCase):
    def test_menciona_las_tres_generaciones(self):
        """A una placa X79 se le proponían solo los módulos de DDR4 y DDR5."""
        from silux import spd
        with mock.patch.object(spd, "_hay_controlador_smbus", return_value=True), \
             mock.patch.object(spd, "_hay_bus_de_memoria", return_value=True):
            _, consejo = spd.diagnostico()
        for modulo in ("spd5118", "ee1004", "at24"):
            self.assertIn(modulo, consejo)


if __name__ == "__main__":
    unittest.main()
