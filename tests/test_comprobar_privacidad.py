"""`tools/comprobar_privacidad.py`: lo que caza y lo que deja pasar.

Los valores son inventados. Los de documentación (192.0.2.x, 2001:db8::,
00:00:5e:00:53:xx) tienen que pasar; los demás están escogidos para que no
sean de ninguna máquina, que es justo lo que el comprobador vigila.

La auditoría del 19 de noviembre de 2026 encontró lo que el de antes no veía:
media IPv6 de enlace de la oficina dentro de un test, porque solo buscaba IPv4
privadas y las direcciones físicas completas; y que lanzado desde otra carpeta
daba su visto bueno sin haber mirado nada (F-M30).
"""

import importlib.util
import ipaddress
import pathlib
import subprocess
import sys
import tempfile
import unittest

RAIZ = pathlib.Path(__file__).resolve().parent.parent
RUTA = RAIZ / "tools" / "comprobar_privacidad.py"


def _comprobador():
    spec = importlib.util.spec_from_file_location("comprobar_privacidad", RUTA)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


# Los contraejemplos van por trozos: escritos enteros, el propio comprobador
# los encontraría en este archivo, y abrirle una excepción sería abrirle un
# hueco.
ENLACE = "fe80::" + "1a2b:3c4d:5e6f:7081"
ENLACE_HEXA = "fe80" + "000000000000" + "1a2b3c4d00000001"
GLOBAL = "2a01:4f8:" + "1c1c:abcd:1234:5678:9abc:def0"
MEDIA = "fe80::" + "1a2b:3c4d:0:1"
MAC = ":".join(("1c", "2b", "3a", "49", "58", "67"))
PRIVADA = "192.168." + "7.1"
PEM = "-----BEGIN OPENSSH " + "PRIVATE KEY-----"
CORREO = "alguien" + "@" + "correo-de-verdad.es"


def _que(texto: str) -> list[str]:
    return [q for _n, q in _comprobador()._en_el_texto(texto)]


class TestLoQueNoEsDeDocumentacion(unittest.TestCase):

    def test_ipv6_de_enlace_con_identificador(self):
        self.assertTrue(_que(f"inet6 {ENLACE}/64"))
        self.assertTrue(_que(f"{ENLACE_HEXA} 02 40 20 80 enp1s0"))

    def test_ipv6_global_que_no_es_de_documentacion(self):
        self.assertTrue(_que(GLOBAL))

    def test_la_mitad_de_un_identificador_tambien(self):
        """El caso real: dos grupos del identificador y el resto a ceros."""
        self.assertTrue(_que(MEDIA))

    def test_pasan_las_de_ejemplo(self):
        self.assertEqual(_que("2001:db8::11 2001:db8:1::7 fe80::1 ::1 "
                              "fe800000000000000000000000000001 "
                              "20010db8000000000000000000000011"), [])

    def test_las_horas_no_son_ipv6(self):
        self.assertEqual(_que("encendido a las 20:34:09, host 2:0:0:0"), [])

    def test_direccion_fisica(self):
        self.assertTrue(_que(f"link/ether {MAC}"))
        self.assertEqual(_que("00:00:5e:00:53:af ff:ff:ff:ff:ff:ff 00:00:00:00:00:00"), [])

    def test_ipv4_privada(self):
        self.assertTrue(_que(f"puerta {PRIVADA}"))
        self.assertEqual(_que("puerta 192.0.2.1 y 198.51.100.23"), [])

    def test_claves_y_correos(self):
        clave = "PrivateKey = " + "A" * 42 + "E="
        self.assertIn("una clave de WireGuard", _que(clave))
        self.assertIn("una clave privada", _que(PEM))
        self.assertIn("un correo", _que(f"escribe a {CORREO}"))
        self.assertEqual(_que("Co-Authored-By: Claude <noreply@anthropic.com>"), [])

    def test_no_imprime_el_dato(self):
        """Va al registro del CI, que es público."""
        hallazgos = _comprobador()._en_el_texto(f"uno\ndos {MAC}\n")
        self.assertEqual(hallazgos, [(2, "una dirección física")])
        self.assertNotIn(MAC, repr(hallazgos))


class TestLoDeEstaMaquina(unittest.TestCase):

    def test_se_busca_tambien_media_ipv6(self):
        trozos = _comprobador()._trozos_de_ipv6(ipaddress.IPv6Address(ENLACE))
        self.assertIn("1a2b:3c4d", trozos)
        self.assertIn("1a2b3c4d", trozos)

    def test_el_concentrador_raiz_no_tiene_serie(self):
        """Da su dirección PCI como serie, que está en cualquier ruta de sysfs."""
        self.assertTrue(_comprobador()._DIRECCION_PCI.match("0000:00:14.0"))
        self.assertFalse(_comprobador()._DIRECCION_PCI.match("S5GXNX0R123456"))

    def test_los_rellenos_del_firmware_no_se_buscan(self):
        relleno = _comprobador()._RELLENO
        for texto in ("To Be Filled By O.E.M.", "Default string", "Not Specified"):
            self.assertTrue(relleno.search(texto), texto)
        self.assertFalse(relleno.search("MON7Q2X91"))


class TestLosSustitutos(unittest.TestCase):

    def test_lo_que_pone_el_anonimizado_pasa(self):
        from silux import privacidad
        self.assertEqual(_que(f"{privacidad.IPV4} por {privacidad.PUERTA}"), [])
        # Y otra de la misma red no: sería de alguien.
        self.assertTrue(_que("192.168.1." + "77"))


class TestLosVolcados(unittest.TestCase):

    def _en(self, nombre: str, contenido: bytes, carpeta: str = "sys/x") -> list[str]:
        modulo = _comprobador()
        with tempfile.TemporaryDirectory() as tmp:
            ruta = pathlib.Path(tmp) / nombre
            ruta.write_bytes(contenido)
            return modulo._en_un_volcado(ruta, f"tests/fixtures/equipos/a/{carpeta}/{nombre}")

    def test_un_serie_sin_poner_a_cero(self):
        self.assertTrue(self._en("serial", b"S5GXNX0R123456\n"))
        self.assertEqual(self._en("serial", b"00000000000000\n"), [])

    def test_un_monitor_con_su_numero(self):
        edid = bytearray(128)
        edid[12:16] = (123456).to_bytes(4, "little")
        self.assertTrue(self._en("edid", bytes(edid)))
        self.assertEqual(self._en("edid", bytes(128)), [])

    def test_el_nombre_del_equipo(self):
        self.assertTrue(self._en("hostname", b"portatil-de-ana\n", "proc/sys/kernel"))
        self.assertEqual(self._en("hostname", b"equipo\n", "proc/sys/kernel"), [])


class TestMiraSiempreElRepositorio(unittest.TestCase):

    def test_lanzado_desde_otra_carpeta_mira_igual(self):
        """F-M30: con rutas relativas, desde otra carpeta no veía ningún archivo
        y daba su visto bueno."""
        with tempfile.TemporaryDirectory() as tmp:
            salida = subprocess.run([sys.executable, str(RUTA)], cwd=tmp,
                                    capture_output=True, text=True)
        self.assertNotIn("(0 archivos", salida.stdout)
        self.assertRegex(salida.stdout + salida.stderr, r"\d{3,} archivos|Esto se publicaría")


class TestElRepositorioEstaLimpio(unittest.TestCase):

    def test_nada_que_no_sea_de_documentacion(self):
        """La parte que no depende de quien ejecuta: la vigila el CI."""
        modulo = _comprobador()
        rutas = [r for r in modulo._versionados() if r.suffix.lower() != ".png"]
        self.assertGreater(len(rutas), 100)
        self.assertEqual(modulo.revisar(rutas, {}), [])


if __name__ == "__main__":
    unittest.main()
