"""El EDID, la chapa de identificación que lleva dentro cada monitor.

Los bloques se construyen a mano en vez de guardar los de un monitor real: así
se pueden probar los casos que no se tienen delante —un panel de 240 Hz, uno
sin nombre, uno con el bloque corrupto— y de paso no se guardan en el
repositorio los números de serie del equipo de nadie.
"""

import unittest

from silux import edid


def construir(*, fabricante="GBT", producto=10025, serie=0x01010101,
              semana=16, anno=2024, ancho_cm=59, alto_cm=33,
              nombre="AORUS FO27Q2", serie_texto=None,
              nativo=(2560, 1440), refresco=(48, 240), cabecera=None) -> bytes:
    """Un EDID 1.4 de mentira, con su suma de comprobación al final."""
    bloque = bytearray(128)
    bloque[0:8] = cabecera if cabecera is not None else edid.CABECERA

    empaquetado = 0
    for indice, letra in enumerate(fabricante):
        empaquetado |= (ord(letra) - 0x40) << (10 - indice * 5)
    bloque[8:10] = empaquetado.to_bytes(2, "big")
    bloque[10:12] = producto.to_bytes(2, "little")
    bloque[12:16] = serie.to_bytes(4, "little")
    bloque[16] = semana
    bloque[17] = anno - 1990 if anno else 0
    bloque[18], bloque[19] = 1, 4
    bloque[21], bloque[22] = ancho_cm, alto_cm

    # Primer descriptor: el temporizador del modo preferido.
    if nativo:
        h, v = nativo
        hb, vb = 160, 40                      # márgenes cualesquiera
        reloj = int((h + hb) * (v + vb) * 60 / 10_000)
        d = bloque
        d[54:56] = reloj.to_bytes(2, "little")
        d[56] = h & 0xFF
        d[57] = hb & 0xFF
        d[58] = ((h >> 8) << 4) | (hb >> 8)
        d[59] = v & 0xFF
        d[60] = vb & 0xFF
        d[61] = ((v >> 8) << 4) | (vb >> 8)

    def descriptor(sitio: int, tipo: int, texto: str) -> None:
        bloque[sitio:sitio + 3] = b"\x00\x00\x00"
        bloque[sitio + 3] = tipo
        bloque[sitio + 4] = 0
        relleno = texto.encode("ascii")[:13].ljust(13, b" ")
        if len(texto) < 13:
            relleno = texto.encode("ascii") + b"\x0a" + b" " * (12 - len(texto))
        bloque[sitio + 5:sitio + 18] = relleno

    if refresco:
        minimo, maximo = refresco
        bloque[72:75] = b"\x00\x00\x00"
        bloque[75] = edid.TIPO_RANGOS
        # Los bits de acarreo para pasar de 255 Hz; aquí no hacen falta.
        bloque[76] = 0
        bloque[77], bloque[78] = minimo, maximo
    if nombre:
        descriptor(90, edid.TIPO_NOMBRE, nombre)
    if serie_texto:
        descriptor(108, edid.TIPO_SERIE, serie_texto)

    bloque[127] = (256 - sum(bloque[:127]) % 256) % 256
    return bytes(bloque)


class TestLecturaNormal(unittest.TestCase):
    def setUp(self):
        self.monitor = edid.parse(construir())

    def test_fabricante_empaquetado_en_cinco_bits(self):
        self.assertEqual(self.monitor.manufacturer_id, "GBT")

    def test_modelo_y_codigo(self):
        self.assertEqual(self.monitor.model, "AORUS FO27Q2")
        self.assertEqual(self.monitor.product_code, 10025)

    def test_fecha_de_fabricacion(self):
        self.assertEqual((self.monitor.week, self.monitor.year), (16, 2024))
        self.assertEqual(self.monitor.made, "semana 16 de 2024")

    def test_medidas_y_pulgadas(self):
        self.assertEqual((self.monitor.width_mm, self.monitor.height_mm), (590, 330))
        self.assertEqual(self.monitor.diagonal_inches, 26.6)

    def test_modo_nativo(self):
        self.assertEqual((self.monitor.native_width, self.monitor.native_height),
                         (2560, 1440))
        self.assertAlmostEqual(self.monitor.native_refresh_hz, 60, delta=1)

    def test_el_rango_de_refresco_no_es_el_modo_preferido(self):
        # Un OLED de 240 Hz puede pedir 60 como preferido. Enseñar solo el
        # preferido diría que un monitor de 240 va a 60.
        self.assertEqual(self.monitor.refresh_range, "48–240 Hz")

    def test_una_serie_de_relleno_no_cuenta(self):
        # 0x01010101 es lo que ponen los fabricantes cuando no hay número.
        self.assertIsNone(self.monitor.serial)

    def test_la_serie_de_texto_gana(self):
        monitor = edid.parse(construir(serie=12345, serie_texto="24160B000993"))
        self.assertEqual(monitor.serial, "24160B000993")


class TestCasosRaros(unittest.TestCase):
    def test_un_bloque_que_no_es_edid(self):
        self.assertIsNone(edid.parse(b"\x00" * 128))
        self.assertIsNone(edid.parse(b""))

    def test_un_bloque_a_medias(self):
        self.assertIsNone(edid.parse(construir()[:64]))

    def test_una_suma_que_no_cuadra(self):
        # Un cable malo o un adaptador que se inventa el EDID: sus datos no
        # valen, y es mejor no enseñar nada que enseñar ruido.
        roto = bytearray(construir())
        roto[127] = (roto[127] + 1) % 256
        self.assertIsNone(edid.parse(bytes(roto)))

    def test_un_monitor_sin_nombre(self):
        monitor = edid.parse(construir(nombre=None))
        self.assertIsNone(monitor.model)
        self.assertEqual(monitor.manufacturer_id, "GBT")

    def test_sin_rango_de_refresco(self):
        monitor = edid.parse(construir(refresco=None))
        self.assertIsNone(monitor.refresh_range)

    def test_sin_temporizador_preferido(self):
        monitor = edid.parse(construir(nativo=None))
        self.assertIsNone(monitor.native_width)

    def test_un_refresco_por_encima_de_255(self):
        # El estándar añadió bits de acarreo cuando aparecieron los paneles de
        # más de 255 Hz; sin sumarlos, un 360 Hz se lee como 105.
        crudo = bytearray(construir(refresco=(48, 105)))
        crudo[76] = 0x02                       # acarreo del máximo
        crudo[127] = (256 - sum(crudo[:127]) % 256) % 256
        self.assertEqual(edid.parse(bytes(crudo)).refresh_max_hz, 360)

    def test_un_monitor_sin_fecha(self):
        monitor = edid.parse(construir(anno=None, semana=0))
        self.assertIsNone(monitor.year)
        self.assertIsNone(monitor.made)


class TestNombresDeFabricante(unittest.TestCase):
    def test_traduce_las_tres_letras(self):
        # Contra la base del sistema; si no está, no se inventa nada.
        nombres = edid.resolve_vendors([edid.parse(construir(fabricante="GSM"))])
        self.assertIn(nombres.get("GSM", "LG"), ("LG Electronics", "LG"))

    def test_sin_nada_que_traducir(self):
        self.assertEqual(edid.resolve_vendors([]), {})


if __name__ == "__main__":
    unittest.main()
