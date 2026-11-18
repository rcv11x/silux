"""El aviso del SMBus que el firmware se reserva: si da el remedio, da el riesgo.

En el 5800X3D el SPD no se lee porque el firmware de la placa se queda con
el bus, y el aviso de Memoria mandaba añadir `acpi_enforce_resources=lax` al
arranque del kernel sin decir qué es. Es quitarle al kernel una protección:
deja que un driver toque hardware que el firmware también está usando, sin
coordinarse. Quien lo lee tiene que saberlo antes de copiarlo.
"""

import unittest

from silux import i18n
from silux.model import Need
from tests.test_equipos import EQUIPOS, foto

RIESGO = {"es": "riesgo", "en": "risk"}


class TestElAvisoDelSmbus(unittest.TestCase):

    def _nota(self, idioma):
        i18n.set_language(idioma)
        self.addCleanup(i18n.set_language, "es")
        f = foto(EQUIPOS / "5800x3d")[0]
        notas = [n for n in f.notes if n.path == "spd"]
        self.assertEqual(len(notas), 1)
        return notas[0]

    def test_el_volcado_tiene_el_caso(self):
        # Es la placa, no un permiso ni un driver que cargar: sin candado.
        nota = self._nota("es")
        self.assertIs(nota.need, Need.HARDWARE)
        self.assertIn("SMBus", nota.message)

    def test_si_nombra_el_parametro_dice_el_riesgo(self):
        for idioma, palabra in RIESGO.items():
            with self.subTest(idioma=idioma):
                pista = self._nota(idioma).hint
                if "acpi_enforce_resources" in pista:
                    self.assertIn(palabra, pista.lower())

    def test_y_no_lo_avala_con_que_otros_lo_hacen(self):
        # «Es lo que hacen lm-sensors y decode-dimms» era una recomendación
        # por autoridad, sin una palabra de lo que puede pasar.
        for idioma in RIESGO:
            with self.subTest(idioma=idioma):
                self.assertNotIn("lm-sensors", self._nota(idioma).hint)

    def test_cabe_en_dos_lineas(self):
        for idioma in RIESGO:
            with self.subTest(idioma=idioma):
                self.assertLess(len(self._nota(idioma).hint), 330)


if __name__ == "__main__":
    unittest.main()
