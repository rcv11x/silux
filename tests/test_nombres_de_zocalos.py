"""Cada zócalo de memoria tiene un nombre único y que se entiende.

En el 5800X3D (Gigabyte X570), con permisos, los dos módulos se llamaban
«DIMM 1» y los zócalos libres «DIMM 0, DIMM 0». Esa placa repite el
localizador en los dos canales y pone el canal en el banco: «P0 CHANNEL A»,
«P0 CHANNEL B». El nombre se sacaba solo del localizador, y por un
diccionario cuya clave era el propio localizador.

Cada fabricante reparte el dato a su manera; las parejas de aquí son las que
escriben sus firmwares. Lo que se exige es lo mismo para todas: ningún
nombre repetido, y el canal a la vista cuando el firmware lo dice.
"""

import dataclasses
import unittest

from silux import render
from silux.i18n import _
from silux.providers.base import Draft
from silux.providers.privileged_memory import PrivilegedMemory
from tests import pantalla, qt
from tests.test_equipos import EQUIPOS, foto, shared_snapshot
from tests.test_smbios import _empty_slot, _end, _memory_array, _memory_device

try:
    from PySide6.QtWidgets import QApplication
except ImportError:                                    # pragma: no cover
    QApplication = None

# (localizador, banco) de cada zócalo, en el orden de la tabla del firmware.
PLACAS = {
    "Gigabyte X570 (AM4)": (
        [("DIMM 0", "P0 CHANNEL A"), ("DIMM 1", "P0 CHANNEL A"),
         ("DIMM 0", "P0 CHANNEL B"), ("DIMM 1", "P0 CHANNEL B")],
        ["Canal A · DIMM 0", "Canal A · DIMM 1", "Canal B · DIMM 0", "Canal B · DIMM 1"]),
    "ASUS": (
        [("DIMM_A1", "BANK 0"), ("DIMM_A2", "BANK 1"),
         ("DIMM_B1", "BANK 2"), ("DIMM_B2", "BANK 3")],
        ["Canal A · DIMM 1", "Canal A · DIMM 2", "Canal B · DIMM 1", "Canal B · DIMM 2"]),
    "MSI, dos zócalos": (
        [("DIMM_A1", "BANK 0"), ("DIMM_B1", "BANK 1")],
        ["Canal A", "Canal B"]),
    "OEM, portátil": (
        [("ChannelA-DIMM0", "BANK 0"), ("ChannelB-DIMM0", "BANK 2")],
        ["Canal A", "Canal B"]),
    "Lenovo ThinkPad": (
        [("Controller0-ChannelA-DIMM0", "BANK 0"), ("Controller1-ChannelA-DIMM0", "BANK 0")],
        ["Controlador 0 · Canal A", "Controlador 1 · Canal A"]),
    "ASRock": (
        [("DIMM 0", "CHANNEL A"), ("DIMM 1", "CHANNEL A"),
         ("DIMM 0", "CHANNEL B"), ("DIMM 1", "CHANNEL B")],
        ["Canal A · DIMM 0", "Canal A · DIMM 1", "Canal B · DIMM 0", "Canal B · DIMM 1"]),
    "sin canal en ninguna parte": (
        [("DIMM 0", None), ("DIMM 1", None)],
        ["DIMM 0", "DIMM 1"]),
}


class TestElNombreDeCadaZocalo(unittest.TestCase):

    def test_cada_fabricante_a_su_manera(self):
        for placa, (zocalos, esperado) in PLACAS.items():
            with self.subTest(placa=placa):
                self.assertEqual(render.slot_names(zocalos), esperado)

    def test_nunca_hay_dos_iguales(self):
        raros = {
            "todo repetido y sin canal": [("DIMM", "BANK"), ("DIMM", "BANK"), ("DIMM", "BANK")],
            "sin nada": [(None, None), (None, None)],
            "no se entiende y se repite": [("RARO", "BANK 0"), ("RARO", "BANK 1")],
            "medio vacío": [("DIMM 0", "P0 CHANNEL A"), ("", "")],
        }
        for nombre, zocalos in {**{k: v[0] for k, v in PLACAS.items()}, **raros}.items():
            with self.subTest(caso=nombre):
                nombres = render.slot_names(zocalos)
                self.assertEqual(len(nombres), len(zocalos))
                self.assertEqual(len(set(nombres)), len(nombres), nombres)
                self.assertTrue(all(nombres))

    def test_lo_que_no_se_entiende_conserva_lo_del_firmware(self):
        self.assertEqual(render.slot_names([("A_RARO_1", None), ("B_RARO_2", None)]),
                         ["A_RARO_1", "B_RARO_2"])
        # Y si se repite, el banco es lo que lo distingue.
        self.assertEqual(render.slot_names([("RARO", "BANK 0"), ("RARO", "BANK 1")]),
                         ["RARO · 0", "RARO · 1"])

    def test_el_banco_completa_pero_no_corrige_al_localizador(self):
        self.assertEqual(render.slot_names([("DIMM_A1", "CHANNEL B"), ("DIMM_B1", "CHANNEL A")]),
                         ["Canal A", "Canal B"])


def _zocalo(localizador: str, banco: str, puesto: bool) -> bytes:
    """Una entrada de la tabla del firmware con esas dos cadenas."""
    if puesto:
        return (_memory_device().replace(b"DIMM 1\x00", localizador.encode() + b"\x00", 1)
                .replace(b"P0 CHANNEL A\x00", banco.encode() + b"\x00", 1))
    vacio = bytearray(_empty_slot())
    vacio[0x11] = 2                     # el banco es la segunda cadena
    return (bytes(vacio).replace(b"DIMM 2\x00", localizador.encode() + b"\x00", 1)
            .replace(b"Unknown\x00", banco.encode() + b"\x00", 1))


def _con_la_tabla(f, zocalos, puestos):
    """La foto como queda al leer con permisos una tabla con esos zócalos."""
    tabla = _memory_array(slots=len(zocalos)) + b"".join(
        _zocalo(localizador, banco or "Not Specified", i in puestos)
        for i, (localizador, banco) in enumerate(zocalos)) + _end()
    draft = Draft()
    PrivilegedMemory._parse(draft, tabla)
    return dataclasses.replace(
        f, modules=tuple(draft.modules), memory_array=draft.memory_array,
        notes=tuple(n for n in f.notes if n.path != "modules"))


@unittest.skipIf(QApplication is None, "sin PySide6")
class TestEnLaPaginaDeMemoria(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.app = qt.app()
        cls.fotos = {n: shared_snapshot(EQUIPOS / n) for n in ("5800x3d", "i5-10400")}

    def _titulos_y_libres(self, f):
        from silux.ui.widgets import Card

        with pantalla.Ventana(f) as ventana:
            ventana.select_section("Memoria")
            for _vez in range(4):
                self.app.processEvents()
            pagina = ventana.memory_page
            # El nombre del zócalo va en su campo; el título es «Módulo N».
            titulos = [g._values[_("memory.field.slot")].full_text()
                       for g in pagina._slot_grids if g._values[_("memory.field.slot")].full_text()]
            return titulos, pagina.subtitle.text(), pantalla.textos_de(pagina)

    def test_la_tabla_trae_el_caso(self):
        f = _con_la_tabla(self.fotos["5800x3d"], PLACAS["Gigabyte X570 (AM4)"][0], {1, 3})
        self.assertEqual([(m.locator, m.bank, m.populated) for m in f.modules],
                         [("DIMM 0", "P0 CHANNEL A", False), ("DIMM 1", "P0 CHANNEL A", True),
                          ("DIMM 0", "P0 CHANNEL B", False), ("DIMM 1", "P0 CHANNEL B", True)])

    def test_la_gigabyte_con_dos_modulos_de_cuatro(self):
        f = _con_la_tabla(self.fotos["5800x3d"], PLACAS["Gigabyte X570 (AM4)"][0], {1, 3})
        titulos, subtitulo, textos = self._titulos_y_libres(f)
        self.assertEqual(titulos, ["Canal A · DIMM 1", "Canal B · DIMM 1"])
        # Los vacíos no se cuentan ni se nombran: ver test_memory.
        self.assertIn("2 módulos", subtitulo)
        self.assertNotIn("Canal A · DIMM 0", " ".join(textos))

    def test_cada_placa_en_cada_volcado(self):
        for equipo, base in self.fotos.items():
            for placa, (zocalos, esperado) in PLACAS.items():
                with self.subTest(equipo=equipo, placa=placa):
                    puestos = set(range(len(zocalos))) - {0} if len(zocalos) > 2 \
                        else set(range(len(zocalos)))
                    f = _con_la_tabla(base, zocalos, puestos)
                    titulos, _subtitulo, _textos = self._titulos_y_libres(f)
                    self.assertEqual(titulos, [n for i, n in enumerate(esperado) if i in puestos])
                    self.assertEqual(len(set(titulos)), len(titulos))

    def test_la_tabla_de_temporizaciones_usa_los_mismos_nombres(self):
        """Sin permisos, con lo que da el SPD del volcado: no cambia nada."""
        for equipo, f in self.fotos.items():
            with self.subTest(equipo=equipo):
                titulos, _libres, _textos = self._titulos_y_libres(f)
                self.assertEqual(len(set(titulos)), len(titulos), titulos)


if __name__ == "__main__":
    unittest.main()
