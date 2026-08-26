"""Placa base: filtrado de rellenos, firmware, chipset y nombres."""

import os
import pathlib
import tempfile
import unittest
from unittest import mock

from silux.model import Board, clean_dmi
from silux.providers import dmi
from silux.providers.base import Draft

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


class TestRellenosDeLaBios(unittest.TestCase):
    """Las BIOS sin configurar dejan textos de fábrica en campos SMBIOS."""

    def test_descarta_los_rellenos_conocidos(self):
        for basura in ("Default string", "To be filled by O.E.M.", "System manufacturer",
                       "Not Specified", "None", "N/A", "  DEFAULT STRING  "):
            with self.subTest(valor=basura):
                self.assertIsNone(clean_dmi(basura))

    def test_conserva_los_valores_de_verdad(self):
        self.assertEqual(clean_dmi("H510M PRO-E (MS-7D23)"), "H510M PRO-E (MS-7D23)")
        self.assertEqual(clean_dmi("  1.80  "), "1.80")

    def test_vacio_y_nulo(self):
        self.assertIsNone(clean_dmi(""))
        self.assertIsNone(clean_dmi(None))


class TestNombresDeLaPlaca(unittest.TestCase):
    def test_resumen_de_bios(self):
        board = Board(bios_vendor="American Megatrends International, LLC.",
                      bios_version="1.80", bios_date="06/08/2023")
        self.assertEqual(board.bios_summary, "AMI 1.80 (06/08/2023)")

    def test_resumen_sin_fecha(self):
        self.assertEqual(Board(bios_vendor="AMI", bios_version="1.2").bios_summary, "AMI 1.2")

    def test_resumen_vacio(self):
        self.assertEqual(Board().bios_summary, "—")


class TestFirmware(unittest.TestCase):
    def test_sin_efi_es_bios_heredada(self):
        # Se apunta a una ruta inexistente en vez de parchear el objeto Path,
        # cuyos métodos son de solo lectura: así se ejerce el código real.
        with mock.patch.object(dmi, "EFI", pathlib.Path("/no/existe/efi")):
            self.assertEqual(dmi.DmiBoard._firmware(), "BIOS heredada")

    def test_con_efi_incluye_los_bits(self):
        with tempfile.TemporaryDirectory() as carpeta:
            efi = pathlib.Path(carpeta)
            (efi / "fw_platform_size").write_text("64\n", encoding="utf-8")
            with mock.patch.object(dmi, "EFI", efi):
                self.assertEqual(dmi.DmiBoard._firmware(), "UEFI (64 bits)")

    def test_con_efi_sin_el_fichero_de_bits(self):
        with tempfile.TemporaryDirectory() as carpeta:
            with mock.patch.object(dmi, "EFI", pathlib.Path(carpeta)):
                self.assertEqual(dmi.DmiBoard._firmware(), "UEFI")

    def test_arranque_seguro_desde_la_variable_efi(self):
        with tempfile.TemporaryDirectory() as carpeta:
            ruta = pathlib.Path(carpeta) / "SecureBoot"
            # Cuatro bytes de atributos y luego el valor.
            ruta.write_bytes(b"\x06\x00\x00\x00\x01")
            with mock.patch.object(dmi, "SECURE_BOOT", ruta):
                self.assertIs(dmi.DmiBoard._secure_boot(), True)
            ruta.write_bytes(b"\x06\x00\x00\x00\x00")
            with mock.patch.object(dmi, "SECURE_BOOT", ruta):
                self.assertIs(dmi.DmiBoard._secure_boot(), False)

    def test_sin_variable_efi_no_se_sabe(self):
        with mock.patch.object(dmi, "SECURE_BOOT", pathlib.Path("/no/existe")):
            self.assertIsNone(dmi.DmiBoard._secure_boot())


class TestChipset(unittest.TestCase):
    def test_extrae_el_modelo_del_nombre_pci(self):
        casos = {
            "H510 Chipset eSPI Controller": "H510",
            "B550 LPC Bridge": "B550",
            "Z790 LPC/eSPI Controller": "Z790",
        }
        for completo, esperado in casos.items():
            with self.subTest(nombre=completo):
                encontrado = dmi._CHIPSET_MODEL.search(completo)
                self.assertIsNotNone(encontrado, completo)
                self.assertEqual(encontrado.group(1), esperado)

    def test_un_nombre_sin_modelo_no_casa(self):
        self.assertIsNone(dmi._CHIPSET_MODEL.search("Ethernet Controller"))


class TestRecoleccionReal(unittest.TestCase):
    @unittest.skipUnless(os.path.isdir(dmi.SYS_DMI), "este sistema no expone DMI")
    def test_recoge_sin_reventar_y_sin_rellenos(self):
        draft = Draft()
        dmi.DmiBoard().collect(draft)
        board = draft.board

        self.assertIn("dmi", draft.capabilities)
        self.assertTrue(board.display_name)
        # Ningún campo debe contener un relleno de fábrica.
        for campo in ("name", "version", "system_family", "system_sku", "chassis_vendor"):
            valor = getattr(board, campo)
            if valor:
                self.assertIsNotNone(clean_dmi(valor), f"{campo} trae un relleno: {valor!r}")


if __name__ == "__main__":
    unittest.main()
