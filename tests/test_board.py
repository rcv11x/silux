"""Placa base: filtrado de rellenos, firmware, chipset y nombres."""

import os
import pathlib
import tempfile
import unittest
from unittest import mock

from silux import render
from silux.model import Board, clean_dmi
from silux.providers import dmi
from silux.providers.base import Draft

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


class TestRellenosDeLaBios(unittest.TestCase):
    """Las BIOS sin configurar dejan textos de fábrica en campos SMBIOS."""

    def test_descarta_los_rellenos_conocidos(self):
        for basura in ("Default string", "To be filled by O.E.M.", "System manufacturer",
                       "Not Specified", "None", "N/A", "  DEFAULT STRING  ",
                       # Templates for the version: Gigabyte's and ASUS's.
                       "x.x", "Rev X.0x", "X.XX", "...", "0x0000",
                       "Base Board Version", "Type2 - Board Product Name",
                       # Lenovo's board version on its IdeaPads.
                       "Not Defined"):
            with self.subTest(valor=basura):
                self.assertIsNone(clean_dmi(basura))

    def test_conserva_los_valores_de_verdad(self):
        self.assertEqual(clean_dmi("H510M PRO-E (MS-7D23)"), "H510M PRO-E (MS-7D23)")
        self.assertEqual(clean_dmi("  1.80  "), "1.80")
        # A real revision with a template's tail still says the revision.
        for real in ("Rev 1.xx", "Rev 1.02", "x570", "1.0", "0x1F", "X"):
            with self.subTest(valor=real):
                self.assertEqual(clean_dmi(real), real)

    def test_its_revision_on_the_board_page(self):
        from tests import pantalla, qt
        from tests.test_equipos import EQUIPOS, foto
        qt.app()
        snapshot = foto(EQUIPOS / "celeron-g3900")[0]
        self.assertIsNone(snapshot.board.version)
        with pantalla.Ventana(snapshot) as window:
            window.select_section("Placa base")
            texts = pantalla.textos_de(window.stack.currentWidget())
        self.assertFalse([t for t in texts if "X.0x" in t])

    def test_vacio_y_nulo(self):
        self.assertIsNone(clean_dmi(""))
        self.assertIsNone(clean_dmi(None))


class TestNombresDeLaPlaca(unittest.TestCase):
    def test_resumen_de_bios(self):
        board = Board(bios_vendor="American Megatrends International, LLC.",
                      bios_version="1.80", bios_date="06/08/2023")
        self.assertEqual(render.bios_summary(board), "AMI 1.80 (2023-06-08)")

    def test_resumen_sin_fecha(self):
        self.assertEqual(render.bios_summary(Board(bios_vendor="AMI", bios_version="1.2")),
                         "AMI 1.2")

    def test_resumen_vacio(self):
        self.assertEqual(render.bios_summary(Board()), "—")

    def test_la_fecha_de_la_bios_no_se_puede_leer_al_reves(self):
        # El firmware la da mes/día/año. «10/28/2025» delata el orden, pero
        # «06/08/2023» no: en España es el seis de agosto y es el ocho de junio.
        self.assertEqual(render.bios_date("10/28/2025"), "2025-10-28")
        self.assertEqual(render.bios_date("06/08/2023"), "2023-06-08")
        self.assertIsNone(render.bios_date(None))

    def test_una_fecha_con_otra_forma_se_deja_como_viene(self):
        for rara in ("2023.06.08", "13/45/2023", "Default string"):
            self.assertEqual(render.bios_date(rara), rara)

    def test_el_modelo_guarda_la_del_firmware(self):
        from tests.test_equipos import EQUIPOS, foto

        f = foto(EQUIPOS / "5800x3d")[0]
        self.assertEqual(f.board.bios_date, "10/28/2025")


class TestFirmware(unittest.TestCase):
    def test_sin_efi_es_bios_heredada(self):
        # Se apunta a una ruta inexistente en vez de parchear el objeto Path,
        # cuyos métodos son de solo lectura: así se ejerce el código real.
        with mock.patch.object(dmi, "EFI", pathlib.Path("/no/existe/efi")):
            self.assertEqual(dmi.DmiBoard._firmware(), (False, None))

    def test_con_efi_incluye_los_bits(self):
        with tempfile.TemporaryDirectory() as carpeta:
            efi = pathlib.Path(carpeta)
            (efi / "fw_platform_size").write_text("64\n", encoding="utf-8")
            with mock.patch.object(dmi, "EFI", efi):
                self.assertEqual(dmi.DmiBoard._firmware(), (True, 64))

    def test_con_efi_sin_el_fichero_de_bits(self):
        with tempfile.TemporaryDirectory() as carpeta:
            with mock.patch.object(dmi, "EFI", pathlib.Path(carpeta)):
                self.assertEqual(dmi.DmiBoard._firmware(), (True, None))

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


class TestTheModelLast(unittest.TestCase):
    """From a report: an older pci.ids calls an i7-12700's H670 bridge
    (8086:7a85) «LPC Controller/eSPI Controller (H670)», and the chipset went
    unrecognised, with a foot saying pci.ids gave only its codename."""

    BRIDGE = ("Intel Corporation", "LPC Controller/eSPI Controller (H670)")

    def test_it_is_found(self):
        self.assertEqual(dmi.chipset(self.BRIDGE, "H670 Steel Legend"), "Intel H670")
        # A laptop's PCH named by its codename still has no model (an
        # i5-12450H's, from our dumps).
        self.assertIsNone(dmi.chipset(("Intel Corporation", "Alder Lake PCH eSPI Controller"),
                                      None))

    def test_on_the_board_page(self):
        import dataclasses

        from silux.i18n import _
        from tests import pantalla, qt
        from tests.test_equipos import EQUIPOS, shared_snapshot

        qt.app()
        photo = shared_snapshot(EQUIPOS / "i5-10400")
        photo = dataclasses.replace(photo, board=dataclasses.replace(
            photo.board, chipset=dmi.chipset(self.BRIDGE, "H670 Steel Legend"),
            chipset_full=self.BRIDGE[1]))
        with pantalla.Ventana(photo) as window:
            window.select_section("Placa base")
            for _turn in range(4):
                qt.app().processEvents()
            page = window.board_page
            self.assertEqual(page.chipset._values[_("board.field.chipset")].full_text(),
                             "Intel H670")
            self.assertNotIn(_("board.na.chipset.codename"), page.chipset_pie.text())


class TestElChipsetDeUnaPlacaAmd(unittest.TestCase):
    """En AM4 y AM5 el puente LPC del bus 0 está dentro del procesador y se
    llama igual en todas las placas: «FCH LPC Bridge». El chipset de verdad
    lo dice el nombre de la placa."""

    def test_del_nombre_de_la_placa(self):
        casos = {
            "X570 AORUS ELITE": "X570",
            "B550M DS3H": "B550",
            "ROG STRIX B650E-F GAMING WIFI": "B650E",
            "X670E AORUS MASTER": "X670E",
            "PRIME A320M-K": "A320",
            "TUF GAMING X870-PLUS WIFI": "X870",
            "PRO B850M-A WIFI": "B850",
            "TRX40 AORUS MASTER": "TRX40",
        }
        for placa, esperado in casos.items():
            with self.subTest(placa=placa):
                self.assertEqual(dmi.chipset_from_board_name(placa), esperado)

    def test_un_nombre_que_no_lo_dice_no_se_adivina(self):
        for placa in ("LNVNB161216", "MS-7D23", "316C", "AX5700", "B5",
                      "Aspire A515-45", "VivoBook X513EA", None, ""):
            with self.subTest(placa=placa):
                self.assertIsNone(dmi.chipset_from_board_name(placa))

    def test_el_5800x3d_dice_x570_y_no_un_dispositivo_pci(self):
        from tests.test_equipos import EQUIPOS, foto

        f = foto(EQUIPOS / "5800x3d")[0]
        self.assertEqual(f.board.chipset, "AMD X570")
        # Lo que dice pci.ids sigue en su fila, que es de lo que habla.
        self.assertEqual(f.board.chipset_full, "FCH LPC Bridge")

    def test_el_intel_sigue_saliendo_del_bus_pci(self):
        from tests.test_equipos import EQUIPOS, foto

        f = foto(EQUIPOS / "i5-10400")[0]
        self.assertEqual(f.board.chipset, "Intel H510")

    def test_sin_modelo_en_ningun_sitio_no_hay_chipset(self):
        self.assertIsNone(dmi.chipset(("Advanced Micro Devices, Inc. [AMD]", "FCH LPC Bridge"),
                                      "LNVNB161216"))
        self.assertEqual(dmi.chipset(("Advanced Micro Devices, Inc. [AMD]", "FCH LPC Bridge"),
                                     "X570 AORUS ELITE"), "AMD X570")
        self.assertEqual(dmi.chipset(("Intel Corporation", "H510 Chipset eSPI Controller"),
                                     "H510M PRO-E (MS-7D23)"), "Intel H510")
        self.assertIsNone(dmi.chipset(None, "X570 AORUS ELITE"))
        # Un puente de Intel sin modelo no se completa con el nombre de la
        # placa: la lista es de chipsets de AMD.
        self.assertIsNone(dmi.chipset(("Intel Corporation", "LPC Controller"), "X570 Rara"))

    def test_la_pagina_y_el_informe_lo_dicen(self):
        from PySide6.QtWidgets import QLabel
        from silux import report
        from silux.settings import Preferences
        from silux.ui import theme
        from silux.ui.pages.board import BoardPage
        from tests import qt
        from tests.test_equipos import EQUIPOS, foto

        app = qt.app()
        f = foto(EQUIPOS / "5800x3d")[0]
        pagina = BoardPage(theme.palette_for(app, "dark"), Preferences().normalized())
        self.addCleanup(pagina.deleteLater)
        pagina.apply(f)
        textos = [e.text() for e in pagina.findChildren(QLabel)]
        self.assertIn("AMD X570", textos)
        self.assertFalse([t for t in textos if "FCH LPC Bridge" in t and "X570" in t])
        self.assertIn("- Chipset: AMD X570 (FCH LPC Bridge)", report.build(f))


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



class TestAChipsetPciIdsDoesNotKnow(unittest.TestCase):
    """A PCH newer than the system's pci.ids: no name and no identification,
    and the two rows came out as dashes. Hidden, and the foot says why."""

    def test_said_at_the_foot_not_dashed(self):
        import dataclasses

        from silux.i18n import _
        from tests import pantalla, qt
        from tests.test_equipos import EQUIPOS, shared_snapshot

        qt.app()
        photo = shared_snapshot(EQUIPOS / "i5-10400")
        photo = dataclasses.replace(photo, board=dataclasses.replace(
            photo.board, chipset=None, chipset_full=None))
        with pantalla.Ventana(photo) as window:
            window.select_section("Placa base")
            for _turn in range(4):
                qt.app().processEvents()
            page = window.board_page
            for row in ("board.field.chipset", "board.field.pciid"):
                self.assertFalse(page.chipset._values[_(row)].isVisibleTo(page), row)
            self.assertEqual(page.chipset_pie.text(), _("board.na.chipset.unknown"))
            self.assertTrue(page.chipset_pie.isVisibleTo(page))


if __name__ == "__main__":
    unittest.main()
