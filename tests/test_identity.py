"""Cómo se presenta la identidad del procesador.

La primera versión enseñaba cuatro filas de familia y modelo, dos de ellas
con los bits en crudo de CPUID. Un "modelo 5" en un procesador que Intel
llama 165 no informa de nada; estos tests fijan la presentación buena.
"""

import unittest

from silux import render
from silux.model import CpuType, Power


class TestFirmaCpuid(unittest.TestCase):
    def _tipo(self) -> CpuType:
        # i5-10400: EAX de la hoja 1 = 0x000A0653.
        return CpuType(
            key="general", label="g",
            family=6, model=5, stepping=3,
            disp_family=6, disp_model=165, signature=0x000A0653,
        )

    def test_formato_de_la_firma(self):
        self.assertEqual(render.signature(0x000A0653), "0x000A0653")
        self.assertEqual(render.signature(None), "—")

    def test_el_tooltip_explica_la_composicion(self):
        texto = render.signature_tooltip(self._tipo())
        self.assertIn("0x000A0653", texto)
        self.assertIn("familia base 6", texto)
        self.assertIn("modelo base 5", texto)
        self.assertIn("modelo extendido 10", texto)
        self.assertIn("modelo 165", texto)

    def test_sin_firma_no_hay_tooltip(self):
        self.assertEqual(render.signature_tooltip(CpuType(key="g", label="g")), "")

    def test_la_interfaz_enseña_los_valores_compuestos(self):
        try:
            from silux.ui.pages.cpu import PROCESSOR_FIELDS
        except ImportError:                                # pragma: no cover
            self.skipTest("PySide6 no está instalado")
        # Los campos son claves de idioma; el texto lo pone `_()` al montar.
        self.assertIn("cpu.field.family", PROCESSOR_FIELDS)
        self.assertIn("cpu.field.model", PROCESSOR_FIELDS)
        self.assertIn("cpu.field.signature", PROCESSOR_FIELDS)
        # Las filas con los bits en crudo ya no existen: confundían más de lo
        # que aportaban, y su contenido vive ahora en el tooltip de la firma.
        self.assertNotIn("cpu.field.dispmodel", PROCESSOR_FIELDS)
        self.assertNotIn("cpu.field.dispfamily", PROCESSOR_FIELDS)


class TestCargaMedia(unittest.TestCase):
    def test_formato(self):
        self.assertEqual(render.load_average((0.55, 0.72, 0.75)), "0.55 · 0.72 · 0.75")
        self.assertEqual(
            render.load_average((1.0, 2.0, 3.0), threads=12),
            "1.00 · 2.00 · 3.00  (de 12 hilos)",
        )

    def test_sin_datos(self):
        self.assertEqual(render.load_average(()), "—")


class TestPotencia(unittest.TestCase):
    def test_titular_con_limite(self):
        power = Power(package_w=7.9, limit_long_w=65.0)
        self.assertEqual(render.power_headline(power), "12 % de 65 W")

    def test_titular_sin_limite(self):
        self.assertEqual(render.power_headline(Power(package_w=7.9)), "")

    def test_desglose_omite_lo_que_no_hay(self):
        power = Power(package_w=7.9, core_w=6.9, dram_w=0.8)
        desglose = render.power_breakdown(power)
        self.assertIn("núcleos", desglose)
        self.assertIn("DRAM", desglose)
        self.assertNotIn("uncore", desglose)

    def test_el_tooltip_lleva_los_limites(self):
        power = Power(package_w=7.9, core_w=6.9, limit_long_w=65.0, limit_short_w=115.0)
        texto = render.power_tooltip(power)
        self.assertIn("PL1", texto)
        self.assertIn("PL2", texto)
        self.assertIn("115.0 W", texto)


class TestVirtualizacion(unittest.TestCase):
    def setUp(self):
        try:
            from silux.ui.pages.cpu import TypeSection
        except ImportError:                                # pragma: no cover
            self.skipTest("PySide6 no está instalado")
        self.describe = TypeSection._virtualization

    def test_soportada(self):
        tipo = CpuType(key="g", label="g", virtualization="VT-x")
        self.assertEqual(self.describe(tipo), "VT-x (soportada)")

    def test_no_soportada(self):
        self.assertEqual(self.describe(CpuType(key="g", label="g")), "no soportada")

    def test_dentro_de_una_maquina_virtual(self):
        tipo = CpuType(key="g", label="g", virtualization="VT-x", in_virtual_machine=True)
        self.assertIn("máquina virtual", self.describe(tipo))


if __name__ == "__main__":
    unittest.main()
