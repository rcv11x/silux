"""Buscar una versión nueva y sustituir el AppImage, sin salir a la red.

Todo pasa por un transporte falso: un diccionario de URL a bytes. Si un test
pidiera algo que no está en él, falla en vez de ir a GitHub.
"""

import hashlib
import io
import json
import os
import pathlib
import stat
import tempfile
import unittest
import urllib.error
from unittest import mock

from silux import __version__, desktop, updates
from tests.test_desktop import HAS_SVG, _EnCasaFalsa

V = "https://github.com/rcv11x/silux/releases/download/v0.5.0/"


class Red:
    """El transporte falso: lo que hay, y lo que se pidió."""

    def __init__(self, respuestas: dict):
        self.respuestas = respuestas
        self.pedidas: list[str] = []

    def __call__(self, url, espera):
        self.pedidas.append(url)
        if url not in self.respuestas:
            raise AssertionError(f"el test no esperaba que se pidiera {url}")
        respuesta = self.respuestas[url]
        if isinstance(respuesta, Exception):
            raise respuesta
        if callable(respuesta):
            return respuesta()
        return io.BytesIO(respuesta)


def _release(tag="v0.5.0", draft=False, prerelease=False, adjuntos=(updates.NORMAL, updates.COMPAT,
                                                                     updates.SUMS)):
    return {"tag_name": tag, "draft": draft, "prerelease": prerelease,
            "html_url": f"https://github.com/rcv11x/silux/releases/tag/{tag}",
            "assets": [{"name": n, "browser_download_url": V + n} for n in adjuntos]}


class TestLasVersiones(unittest.TestCase):
    def test_tres_numeros_con_o_sin_v(self):
        self.assertEqual(updates.parse_version("v0.5.0"), (0, 5, 0))
        self.assertEqual(updates.parse_version("0.5.0"), (0, 5, 0))

    def test_lo_que_no_es_x_y_z_no_cuenta(self):
        for texto in ("v0.5.0-rc1", "0.5", "", "latest", "v0.5.0.1"):
            with self.subTest(texto=texto):
                self.assertIsNone(updates.parse_version(texto))

    def test_se_compara_como_numeros_y_no_como_texto(self):
        lista = [_release("v0.9.1"), _release("v0.10.0"), _release("v0.2.0")]
        self.assertEqual(updates.latest(lista).version, (0, 10, 0))

    def test_ni_borradores_ni_prereleases(self):
        lista = [_release("v0.4.1"), _release("v0.6.0", draft=True),
                 _release("v0.5.0", prerelease=True)]
        self.assertEqual(updates.latest(lista).version, (0, 4, 1))

    def test_una_respuesta_rara_no_revienta(self):
        for rara in (None, {}, "x", [1, None, {"tag_name": None}], [{"assets": "x", "tag_name": "v1.0.0"}]):
            with self.subTest(rara=rara):
                updates.latest(rara)

    def test_contra_la_version_completa(self):
        # Que la pantalla diga «0.4» no cambia nada: se compara 0.4.0.
        misma = updates.latest([_release("v" + __version__)])
        self.assertFalse(updates.is_newer(misma))
        self.assertTrue(updates.is_newer(updates.latest([_release("v0.4.1")]), "0.4.0"))
        self.assertFalse(updates.is_newer(updates.latest([_release("v0.4.0")]), "0.4.0"))
        self.assertFalse(updates.is_newer(None, "0.4.0"))


class TestQueCopiaEs(unittest.TestCase):
    def test_el_compatible_baja_el_compatible(self):
        self.assertEqual(updates.asset_name("20261118.c01944d-compat"), updates.COMPAT)

    def test_el_normal_y_el_codigo_bajan_el_normal(self):
        self.assertEqual(updates.asset_name("20261118.c01944d"), updates.NORMAL)
        self.assertEqual(updates.asset_name(""), updates.NORMAL)

    def test_desde_el_codigo_no_se_sustituye_nada(self):
        self.assertIsNone(updates.replaceable_path({}))

    def test_un_appimage_en_una_carpeta_propia_si(self):
        with tempfile.TemporaryDirectory() as carpeta:
            archivo = pathlib.Path(carpeta) / "silux.AppImage"
            archivo.write_bytes(b"x")
            self.assertEqual(updates.replaceable_path({"APPIMAGE": str(archivo)}), archivo)

    @unittest.skipIf(os.geteuid() == 0, "root escribe en cualquier carpeta")
    def test_una_carpeta_que_no_se_puede_escribir_solo_avisa(self):
        with tempfile.TemporaryDirectory() as carpeta:
            archivo = pathlib.Path(carpeta) / "silux.AppImage"
            archivo.write_bytes(b"x")
            os.chmod(carpeta, 0o555)
            try:
                self.assertIsNone(updates.replaceable_path({"APPIMAGE": str(archivo)}))
            finally:
                os.chmod(carpeta, 0o755)


class TestLaRed(unittest.TestCase):
    def test_busca_en_la_api_de_releases_del_repositorio(self):
        red = Red({updates.API_URL: json.dumps([_release("v0.5.0")]).encode()})
        self.assertEqual(updates.check(red).version, (0, 5, 0))
        self.assertEqual(red.pedidas, ["https://api.github.com/repos/rcv11x/silux/releases"])

    def test_el_user_agent_no_lleva_nada_del_equipo(self):
        self.assertEqual(updates.user_agent(), f"silux/{__version__}")

    def test_la_cabecera_que_sale_es_esa(self):
        abiertas = []

        def abrir_falso(peticion, timeout):
            abiertas.append((peticion, timeout))
            return io.BytesIO(b"[]")

        with mock.patch.object(updates._ABRIDOR, "open", abrir_falso):
            updates.check()
        peticion, espera = abiertas[0]
        self.assertEqual(peticion.get_header("User-agent"), f"silux/{__version__}")
        self.assertEqual(set(peticion.headers), {"User-agent", "Accept"})
        self.assertEqual(espera, updates.ESPERA)

    def test_nada_que_no_sea_https(self):
        # Con el abridor de verdad tapado: si la guarda faltara, el test no
        # puede acabar saliendo a la red.
        with mock.patch.object(updates._ABRIDOR, "open", side_effect=AssertionError("salió")), \
                self.assertRaises(updates.UpdateError) as caso:
            updates.abrir("http://api.github.com/repos/rcv11x/silux/releases", 1)
        self.assertEqual(caso.exception.code, "insecure")

    def test_una_redireccion_a_http_se_corta(self):
        with self.assertRaises(urllib.error.URLError):
            updates._SoloHttps().redirect_request(None, None, 302, "", {}, "http://ejemplo.org/x")

    def test_sin_red_es_un_error_con_su_motivo(self):
        red = Red({updates.API_URL: urllib.error.URLError("sin red")})
        with self.assertRaises(updates.UpdateError) as caso:
            updates.check(red)
        self.assertEqual(caso.exception.code, "network")

    def test_una_lista_enorme_no_se_lee_entera(self):
        red = Red({updates.API_URL: b"[" + b" " * updates.TOPE_DE_LA_LISTA + b"]"})
        with self.assertRaises(updates.UpdateError) as caso:
            updates.check(red)
        self.assertEqual(caso.exception.code, "toolarge")

    def test_una_respuesta_que_no_es_json(self):
        with self.assertRaises(updates.UpdateError) as caso:
            updates.check(Red({updates.API_URL: b"<html>"}))
        self.assertEqual(caso.exception.code, "badreply")


class TestSustituir(unittest.TestCase):
    NUEVO = b"\x7fELF el silux nuevo" * 1000

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.carpeta = pathlib.Path(self._tmp.name)
        self.destino = self.carpeta / "Silux.AppImage"
        self.destino.write_bytes(b"el viejo")
        self.destino.chmod(0o755)
        self.release = updates.latest([_release("v0.5.0")])

    def _red(self, suma=None, contenido=None):
        suma = suma or hashlib.sha256(self.NUEVO).hexdigest()
        sumas = f"{suma}  {updates.NORMAL}\n{'0' * 64}  {updates.COMPAT}\n".encode()
        return Red({V + updates.SUMS: sumas, V + updates.NORMAL: contenido or self.NUEVO})

    def _sin_restos(self):
        self.assertEqual(sorted(p.name for p in self.carpeta.iterdir()), ["Silux.AppImage"])

    def test_queda_el_nuevo_ejecutable_y_en_la_misma_ruta(self):
        updates.install(self.release, self.destino, updates.NORMAL, self._red())
        self.assertEqual(self.destino.read_bytes(), self.NUEVO)
        self.assertTrue(self.destino.stat().st_mode & stat.S_IXUSR)
        self._sin_restos()

    def test_baja_el_de_su_tipo(self):
        red = self._red()
        updates.install(self.release, self.destino, updates.NORMAL, red)
        self.assertNotIn(V + updates.COMPAT, red.pedidas)

    def test_si_la_suma_no_coincide_no_se_toca(self):
        with self.assertRaises(updates.UpdateError) as caso:
            updates.install(self.release, self.destino, updates.NORMAL, self._red(suma="1" * 64))
        self.assertEqual(caso.exception.code, "badhash")
        self.assertEqual(self.destino.read_bytes(), b"el viejo")
        self._sin_restos()

    def test_sin_sumas_publicadas_no_se_baja_nada(self):
        release = updates.latest([_release("v0.5.0", adjuntos=(updates.NORMAL, updates.COMPAT))])
        red = Red({})
        with self.assertRaises(updates.UpdateError) as caso:
            updates.install(release, self.destino, updates.NORMAL, red)
        self.assertEqual(caso.exception.code, "nosums")
        self.assertEqual(red.pedidas, [])
        self.assertEqual(self.destino.read_bytes(), b"el viejo")

    def test_las_sumas_no_listan_ese_appimage(self):
        red = Red({V + updates.SUMS: f"{'0' * 64}  otro.AppImage\n".encode()})
        with self.assertRaises(updates.UpdateError) as caso:
            updates.install(self.release, self.destino, updates.NORMAL, red)
        self.assertEqual(caso.exception.code, "nosums")
        self.assertNotIn(V + updates.NORMAL, red.pedidas)

    def test_mas_grande_que_el_tope_se_corta(self):
        with mock.patch.object(updates, "TOPE_DEL_APPIMAGE", 1000):
            with self.assertRaises(updates.UpdateError) as caso:
                updates.install(self.release, self.destino, updates.NORMAL, self._red())
        self.assertEqual(caso.exception.code, "toolarge")
        self.assertEqual(self.destino.read_bytes(), b"el viejo")
        self._sin_restos()

    def test_un_corte_a_mitad_deja_el_viejo(self):
        class Cortada(io.BytesIO):
            def read(self, n=-1):
                if self.tell() > 100:
                    raise ConnectionResetError("cortada")
                return super().read(n if n < 200 else 200)

        red = self._red()
        red.respuestas[V + updates.NORMAL] = lambda: Cortada(self.NUEVO)
        with self.assertRaises(updates.UpdateError) as caso:
            updates.install(self.release, self.destino, updates.NORMAL, red)
        self.assertEqual(caso.exception.code, "network")
        self.assertEqual(self.destino.read_bytes(), b"el viejo")
        self._sin_restos()

    def test_las_sumas_de_sha256sum(self):
        texto = f"{'a' * 64}  {updates.NORMAL}\n{'B' * 64} *{updates.COMPAT}\nbasura\n"
        self.assertEqual(updates.parse_sums(texto),
                         {updates.NORMAL: "a" * 64, updates.COMPAT: "b" * 64})


@unittest.skipUnless(HAS_SVG, "hace falta el complemento qsvg de Qt")
class TestElAccesoDirecto(_EnCasaFalsa):
    """La entrada de menú apunta a `$APPIMAGE`; el nuevo ocupa esa ruta."""

    def test_sigue_al_dia_despues_de_sustituir(self):
        destino = self.casa / "Aplicaciones" / "Silux x86_64.AppImage"
        destino.parent.mkdir()
        destino.write_bytes(b"el viejo")
        destino.chmod(0o755)
        lanzador = desktop.current_launcher({"APPIMAGE": str(destino)})
        desktop.install(lanzador)
        entrada = desktop.desktop_path().read_text()
        self.assertEqual(desktop.status(lanzador).state, "current")

        nuevo = b"el nuevo" * 100
        red = Red({V + updates.SUMS: f"{hashlib.sha256(nuevo).hexdigest()}  "
                                     f"{updates.NORMAL}\n".encode(),
                   V + updates.NORMAL: nuevo})
        updates.install(updates.latest([_release()]), destino, updates.NORMAL, red)

        self.assertEqual(destino.read_bytes(), nuevo)
        self.assertEqual(desktop.desktop_path().read_text(), entrada)
        self.assertEqual(desktop.status(lanzador).state, "current")


if __name__ == "__main__":
    unittest.main()
