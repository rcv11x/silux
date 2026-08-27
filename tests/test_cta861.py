"""Las extensiones CTA-861, que es donde el monitor dice lo que de verdad hace.

El bloque base del EDID es de 1994: tiene sitio para un modo preferido, unos
pocos estándar y poco más. Sin mirar los bloques que van detrás, un panel con
HDR10 y BT.2020 se describe igual que uno de hace veinte años.

Las muestras son los EDID de dos monitores reales, con el número de serie
borrado y la suma de control rehecha.
"""

import pathlib
import unittest

from silux import edid, render

FIXTURES = pathlib.Path(__file__).parent / "fixtures" / "edid"


def _leer(nombre: str):
    return edid.parse((FIXTURES / nombre).read_bytes())


class TestMonitoresReales(unittest.TestCase):
    def test_un_oled_de_240_hz(self):
        monitor = _leer("aorus-fo27q2-oled-240hz.bin")
        self.assertEqual(monitor.model, "AORUS FO27Q2")
        self.assertEqual(monitor.refresh_range, "48–240 Hz")

    def test_declara_hdr10_y_hlg(self):
        monitor = _leer("aorus-fo27q2-oled-240hz.bin")
        self.assertIn("HDR10 (PQ)", monitor.hdr)
        self.assertIn("HLG", monitor.hdr)

    def test_y_el_espacio_de_color_ancho(self):
        monitor = _leer("aorus-fo27q2-oled-240hz.bin")
        self.assertIn("BT.2020 RGB", monitor.color_spaces)

    def test_otro_monitor_declara_menos(self):
        """El LG trae HDR10 pero no HLG: son datos distintos, no un fallo."""
        monitor = _leer("lg-27gl850-144hz.bin")
        self.assertEqual(monitor.hdr, ("HDR10 (PQ)",))
        self.assertEqual(monitor.refresh_range, "48–144 Hz")

    def test_los_modos_salen_de_la_tabla_de_codigos(self):
        monitor = _leer("aorus-fo27q2-oled-240hz.bin")
        etiquetas = [m.label for m in monitor.modes]
        self.assertIn("1920 × 1080 @ 120 Hz", etiquetas)

    def test_no_llevan_numero_de_serie(self):
        """Estos archivos van al repositorio: el serie se borró a mano."""
        for nombre in ("aorus-fo27q2-oled-240hz.bin", "lg-27gl850-144hz.bin"):
            self.assertEqual(_leer(nombre).serial, "0000000000")


class TestDecodificador(unittest.TestCase):
    def _extension(self, bloques: bytes, fin: int) -> dict:
        cabecera = bytes([edid.ETIQUETA_CTA, 3, fin, 0x71])
        relleno = bytes(128 - len(cabecera) - len(bloques))
        return edid._extension_cta(cabecera + bloques + relleno)

    def test_un_bloque_de_video(self):
        # etiqueta 2 (vídeo), 2 bytes: VIC 97 nativo y VIC 16.
        salida = self._extension(bytes([(2 << 5) | 2, 97 | 0x80, 16]), 7)
        self.assertEqual(len(salida["modes"]), 2)
        self.assertEqual(salida["modes"][0].width, 3840)
        self.assertTrue(salida["modes"][0].native)

    def test_un_codigo_desconocido_se_salta(self):
        """No se le inventa una resolución a un código que no está en la tabla.

        Ojo con el byte: el bit 7 marca «nativo», así que 200 no es el código
        200 sino el 72, que sí existe. Aquí va el 127, que no está.
        """
        self.assertNotIn(127, edid.VIC)
        salida = self._extension(bytes([(2 << 5) | 2, 127, 16]), 7)
        self.assertEqual(len(salida["modes"]), 1)
        self.assertEqual(salida["modes"][0].width, 1920)

    def test_una_longitud_imposible_no_tumba_la_lectura(self):
        """Lee lo que haya y para; lo que no puede es lanzar una excepción."""
        salida = self._extension(bytes([(2 << 5) | 31, 97]), 6)
        self.assertIsInstance(salida["modes"], list)

    def test_un_bloque_que_no_es_cta_se_ignora(self):
        self.assertEqual(edid._extension_cta(bytes(128))["modes"], [])

    def test_un_bloque_corto_tampoco_revienta(self):
        self.assertEqual(edid._extension_cta(b"\x02")["modes"], [])

    def test_un_fin_de_datos_absurdo_se_descarta(self):
        salida = self._extension(bytes([(2 << 5) | 1, 16]), 200)
        self.assertEqual(salida["modes"], [])


class TestComoSePinta(unittest.TestCase):
    def test_junta_hdr_y_el_color_mas_ancho(self):
        monitor = _leer("aorus-fo27q2-oled-240hz.bin")
        texto = render.monitor_color(monitor)
        self.assertIn("HDR10", texto)
        self.assertIn("BT.2020", texto)

    def test_solo_un_espacio_de_color(self):
        """Enseñar los seis que declara llena la celda sin decir más."""
        monitor = _leer("aorus-fo27q2-oled-240hz.bin")
        self.assertEqual(render.monitor_color(monitor).count("BT.2020"), 1)

    def test_un_monitor_que_no_declara_nada_sale_con_su_guion(self):
        self.assertEqual(render.monitor_color(edid.Edid()), render.DASH)


if __name__ == "__main__":
    unittest.main()
