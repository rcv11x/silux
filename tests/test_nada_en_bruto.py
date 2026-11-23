"""Ningún relleno ni texto en bruto del firmware llega a la pantalla.

Con permisos, la tarjeta de Memoria de Inicio decía «31.3 GB · Desconocido»
en el 5800X3D. La tabla del firmware trae una entrada por zócalo, y en los
vacíos el tipo es «Unknown»: Inicio tomaba el del primer zócalo que dijera
algo, y el primero estaba vacío. Lo que el firmware no sabe no es un dato:
no se enseña, y de un zócalo vacío no se saca cómo es la memoria.

De ahí la regla general, que vigila el último test recorriendo todas las
páginas con cada equipo volcado: lo que se lee en la ventana no lleva
rellenos del firmware («Unknown», «Default string»), ni un «None», ni la
razón social de un fabricante donde va su marca, ni el nombre de un chip con
su dirección pegada.
"""

import dataclasses
import re
import unittest

from silux import render
from silux.providers.base import Draft
from silux.providers.privileged_memory import PrivilegedMemory
from tests import pantalla, qt
from tests.per_dump import per_dump
from tests.test_equipos import EQUIPOS, foto, shared_snapshot, volcados
from tests.test_smbios import _empty_slot, _end, _memory_array, _memory_device

try:
    from PySide6.QtWidgets import QApplication
except ImportError:                                    # pragma: no cover
    QApplication = None


def _con_permisos(f, tabla: bytes):
    """La foto como queda al leer la tabla del firmware con permisos."""
    draft = Draft()
    PrivilegedMemory._parse(draft, tabla)
    return dataclasses.replace(
        f, modules=tuple(draft.modules), memory_array=draft.memory_array,
        notes=tuple(n for n in f.notes if n.path != "modules"))


# Como la de una placa de cuatro zócalos con dos módulos en el segundo y el
# cuarto: el primero que aparece está vacío.
DOS_DE_CUATRO = (_memory_array() + _empty_slot() + _memory_device()
                 + _empty_slot() + _memory_device() + _end())
# Y una en la que el firmware no dice el tipo de ninguno.
SIN_TIPO = (_memory_array() + _empty_slot()
            + _memory_device().replace(b"\x1a", b"\x02", 1) + _end())


class TestLoQueElFirmwareNoSabe(unittest.TestCase):

    def test_la_tabla_de_prueba_tiene_el_caso(self):
        from silux.privileged import smbios

        crudos = smbios.memory_devices(list(smbios.parse_table(DOS_DE_CUATRO)))
        self.assertEqual([m["populated"] for m in crudos], [False, True, False, True])
        # «Unknown» is no type: the empty slot says none, whatever the language.
        self.assertIsNone(crudos[0]["type"])

    def test_no_llega_al_modelo(self):
        draft = Draft()
        PrivilegedMemory._parse(draft, DOS_DE_CUATRO)
        self.assertEqual([m.type for m in draft.modules], [None, "DDR4", None, "DDR4"])
        self.assertEqual([m.form_factor for m in draft.modules], [None, 0x09, None, 0x09])
        for modulo in draft.modules:
            for campo in dataclasses.fields(modulo):
                valor = getattr(modulo, campo.name)
                if isinstance(valor, str):
                    self.assertNotRegex(valor, r"(?i)desconocid|unknown|^otr[oa]$", campo.name)

    def test_la_correccion_de_errores_tampoco(self):
        tabla = _memory_array().replace(b"\x03\x03\x03", b"\x03\x03\x02", 1) + _end()
        draft = Draft()
        PrivilegedMemory._parse(draft, tabla)
        self.assertIsNone(draft.memory_array.error_correction)


@unittest.skipIf(QApplication is None, "sin PySide6")
class TestLaTarjetaDeMemoriaDeInicio(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        qt.app()
        cls.amd = shared_snapshot(EQUIPOS / "5800x3d")

    def _tarjeta(self, f) -> str:
        with pantalla.Ventana(f) as ventana:
            return "\n".join(pantalla.textos_de(ventana.home_page.memoria))

    def test_con_permisos_dice_ddr4_y_no_desconocido(self):
        texto = self._tarjeta(_con_permisos(self.amd, DOS_DE_CUATRO))
        self.assertNotIn("Desconocido", texto)
        self.assertIn("DDR4-3200", texto)

    def test_si_no_se_sabe_no_dice_nada(self):
        texto = self._tarjeta(_con_permisos(self.amd, SIN_TIPO))
        self.assertNotIn("Desconocido", texto)
        self.assertNotIn("DDR", texto)
        self.assertIn(render.size(self.amd.system.memory.total_bytes), texto)


class TestLaMarcaYNoLaRazonSocial(unittest.TestCase):

    def test_cada_fabricante_por_su_marca(self):
        casos = {
            "Gigabyte Technology Co., Ltd.": "Gigabyte",
            "Micro-Star International Co., Ltd.": "MSI",
            "Micro-Star International Co., Ltd. [MSI]": "MSI",
            "Tul Corporation / PowerColor": "PowerColor",
            "ASUSTeK Computer Inc.": "ASUS",
            "Sapphire Technology Limited": "Sapphire Technology",
            "Advanced Micro Devices, Inc. [AMD]": "AMD",
            "Intel Corporation": "Intel",
            "XFX Limited": "XFX",
            "Framework Computer Inc": "Framework Computer",
            "Seagate": "Seagate",
        }
        for crudo, marca in casos.items():
            with self.subTest(fabricante=crudo):
                self.assertEqual(render.maker(crudo), marca)

    def test_lo_que_no_hay_sigue_sin_haberlo(self):
        self.assertIsNone(render.maker(None))
        self.assertIsNone(render.maker(""))


class TestElNombreDeUnChip(unittest.TestCase):

    def test_sin_la_direccion_que_le_pega_el_kernel(self):
        casos = {"it8688_40050607": "it8688", "r8169_0_600:00": "r8169",
                 "gigabyte_wmi": "gigabyte_wmi", "k10temp": "k10temp",
                 "nct6798": "nct6798", "acpitz": "acpitz", "nvme": "nvme",
                 "hidpp_battery_0": "hidpp_battery_0", "iwlwifi_1": "iwlwifi_1"}
        for crudo, limpio in casos.items():
            with self.subTest(chip=crudo):
                self.assertEqual(render.chip_name(crudo), limpio)


# Lo que no puede leerse en la ventana, con el porqué de cada cosa.
EN_BRUTO = {
    "un relleno del firmware": re.compile(
        r"(?i)\bdesconocid[oa]s?\b|\bunknown\b|default string|to be filled|o\.e\.m\."
        r"|not specified|not available|system product name|system manufacturer"),
    "un valor que no se convirtió en texto": re.compile(r"\bNone\b|\bnull\b|\bnan\b"),
    "una razón social": re.compile(
        r"Co\., ?Ltd|\bInc\.|\bCorporation\b|\bLimited\b|\bGmbH\b|\[[A-Z/]+\]$"
        r"|\bS\.A\.|\bInformatica SA\b"),
    # Not inside a path: a temporary folder's random name can look like one.
    # The address is eight hex digits: a Realtek driver is «rtw88_8821ce».
    "un chip con su dirección": re.compile(
        r"(?<!/)\b[a-z]+\d*_[0-9a-f]{8,}\b|(?<!/)\b\w+_\d+_[0-9a-f]+:\d+"),
    "una clave de idioma sin traducir": re.compile(r"^[a-z]+(\.[a-z0-9_]+){1,3}$"),
}


class TestTheChipPattern(unittest.TestCase):
    """A temporary folder's random name can look like a chip with its
    address («tmp4_a33fe4»), and Settings shows where it saves: the guard
    failed now and then in the CI."""

    def test_a_chip_is_caught(self):
        for texto in ("it8688_40050607", "Sensor de it8688_40050607", "r8169_0_600:00"):
            with self.subTest(texto=texto):
                self.assertTrue(EN_BRUTO["un chip con su dirección"].search(texto))

    def test_a_drivers_name_is_not(self):
        for texto in ("rtw88_8821ce", "rtw89_8852be"):
            with self.subTest(texto=texto):
                self.assertFalse(EN_BRUTO["un chip con su dirección"].search(texto))

    def test_a_folder_in_a_path_is_not(self):
        texto = "Los ajustes se guardan en /tmp/tmp4_a33fe4/silux/settings.json"
        self.assertFalse(EN_BRUTO["un chip con su dirección"].search(texto))


@unittest.skipIf(QApplication is None, "sin PySide6")
class TestNingunaPaginaDeNingunEquipo(unittest.TestCase):
    """La guarda: todas las páginas, con cada volcado, sin permisos y con
    la tabla del firmware leída."""

    @classmethod
    def setUpClass(cls):
        qt.app()

    def _consentido(self, f, texto: str) -> bool:
        # El campo «Especificación» de la página CPU es, a propósito, la
        # cadena que da el procesador de sí mismo, como en CPU-Z. Es el único
        # sitio donde va algo sin tocar, y se dice cuál.
        # And the kernel's own description of each vulnerability, which the
        # System page quotes on purpose: it is what one pastes in a search.
        return (any(texto == tipo.brand for tipo in f.cpu.types)
                or any(texto == v.status for v in f.system.vulnerabilities))

    def _hallazgos(self, f) -> list[str]:
        encontrados = []
        with pantalla.Ventana(f) as ventana:
            for seccion, pagina in pantalla.recorrer(ventana):
                for texto in pantalla.textos_de(pagina):
                    if self._consentido(f, texto):
                        continue
                    for que, patron in EN_BRUTO.items():
                        if patron.search(texto):
                            encontrados.append(f"{seccion}: {que}: {texto[:90]!r}")
        return encontrados

    def test_se_recorren_todas_las_paginas(self):
        from silux.ui.app import SECTIONS

        with pantalla.Ventana(shared_snapshot(EQUIPOS / "5800x3d")) as ventana:
            vistas = {seccion: len(pantalla.textos_de(pagina))
                      for seccion, pagina in pantalla.recorrer(ventana)}
        self.assertEqual(set(vistas), {clave for clave, _activa in SECTIONS})
        # Y de cada una se lee algo: una página vacía pasaría la guarda sola.
        sin_bateria = {s: n for s, n in vistas.items() if s != "nav.battery"}
        self.assertFalse([s for s, n in sin_bateria.items() if n < 5], vistas)

    def test_la_guarda_ve_lo_que_busca(self):
        # Si no cazara una foto estropeada a propósito, no vigilaría nada.
        f = shared_snapshot(EQUIPOS / "5800x3d")
        estropeada = dataclasses.replace(f, board=dataclasses.replace(
            f.board, name="Default string", bios_version="To be filled by O.E.M."))
        self.assertTrue(self._hallazgos(estropeada))

    def _without_permissions(self, carpeta):
        self.assertEqual(self._hallazgos(shared_snapshot(carpeta)), [])

    def _with_the_firmware_table(self, carpeta):
        for nombre, tabla in (("dos de cuatro", DOS_DE_CUATRO), ("sin tipo", SIN_TIPO)):
            with self.subTest(equipo=carpeta.name, tabla=nombre):
                self.assertEqual(
                    self._hallazgos(_con_permisos(shared_snapshot(carpeta), tabla)), [])


per_dump(TestNingunaPaginaDeNingunEquipo, "sin_permisos",
         TestNingunaPaginaDeNingunEquipo._without_permissions)
per_dump(TestNingunaPaginaDeNingunEquipo, "con_la_tabla_del_firmware_leida",
         TestNingunaPaginaDeNingunEquipo._with_the_firmware_table)


if __name__ == "__main__":
    unittest.main()
