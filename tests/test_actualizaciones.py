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

    def test_which_one_is_this_copy(self):
        release = updates.latest([_release("v0.4.0")])
        self.assertTrue(updates.is_current(release, "0.4.0"))
        self.assertFalse(updates.is_current(release, "0.4.0rc1"))
        self.assertFalse(updates.is_current(release, "0.4.1"))
        self.assertFalse(updates.is_current(None, "0.4.0"))


class TestLaVersionDePrueba(unittest.TestCase):
    """La 0.4-prueba1 es 0.4.0rc1 por debajo, y quien la instale tiene que
    recibir la 0.4.0 final con un clic. `parse_version` no entendía «rc»: la
    versión que corría salía None, y para `is_newer` nunca había nada más
    nuevo. La ventana lo enseñaba: «Buscar ahora» no ponía el aviso."""

    def test_la_final_va_por_delante_de_su_prueba(self):
        final = updates.latest([_release("v0.4.0")])
        self.assertTrue(updates.is_newer(final, "0.4.0rc1"))
        self.assertTrue(updates.is_newer(final, "0.4.0rc2"))
        self.assertFalse(updates.is_newer(final, "0.4.0"))
        self.assertTrue(updates.is_newer(updates.latest([_release("v0.4.1")]), "0.4.0rc1"))
        self.assertFalse(updates.is_newer(updates.latest([_release("v0.3.0")]), "0.4.0rc1"))

    def test_la_version_que_corre_se_entiende(self):
        # Contra la versión de verdad del paquete, no un caso escrito: si un
        # día cambia de forma, esto falla en vez de dejar de avisar callado.
        mas_nueva = updates.Release(version=(99, 0, 0), tag="v99.0.0", url="u")
        self.assertTrue(updates.is_newer(mas_nueva))

    def test_una_prueba_no_se_ofrece(self):
        lista = [_release("v0.3.0"), _release("0.4.0rc1", prerelease=True)]
        self.assertEqual(updates.latest(lista).version, (0, 3, 0))
        # Ni aunque alguien la publique sin marcarla como prerelease.
        lista = [_release("v0.3.0"), _release("0.4.0rc1")]
        self.assertEqual(updates.latest(lista).version, (0, 3, 0))


class TestNotThePagesOrder(unittest.TestCase):
    """GitHub lists releases by the day of their tag's commit and, within a
    day, by name as text: the 0.4-prueba10 came out under the 9 and the 8,
    published the same day. «Buscar ahora» goes by the version."""

    def test_the_highest_version_wherever_it_is_listed(self):
        page = [_release(f"0.4.0rc{n}", prerelease=True) for n in (9, 8, 10, 7, 6)]
        found = updates.latest(page, "testing")
        self.assertEqual(found.tag, "0.4.0rc10")
        self.assertTrue(updates.is_newer(found, "0.4.0rc9"))
        self.assertFalse(updates.is_newer(found, "0.4.0rc10"))


class TestTheChannel(unittest.TestCase):
    """«Estable» or «Pruebas» in Settings: the author wants whoever runs the
    0.4-prueba2 to get the prueba3 with «Buscar ahora»."""

    API = [_release("v0.3.0"), _release("0.4.0rc2", prerelease=True),
           _release("0.4.0rc3", prerelease=True)]
    API_CON_LA_FINAL = API + [_release("v0.4.0")]

    def test_stable_offers_only_finals(self):
        self.assertEqual(updates.latest(self.API, "stable").version, (0, 3, 0))
        self.assertEqual(updates.latest(self.API_CON_LA_FINAL, "stable").version, (0, 4, 0))

    def test_testing_offers_the_next_test_version(self):
        rc3 = updates.latest(self.API, "testing")
        self.assertEqual((rc3.version, rc3.prerelease), ((0, 4, 0), 3))
        self.assertTrue(updates.is_newer(rc3, "0.4.0rc2"))
        self.assertFalse(updates.is_newer(rc3, "0.4.0rc3"))
        self.assertTrue(updates.is_current(rc3, "0.4.0rc3"))
        self.assertEqual(rc3.version_text, "0.4.0rc3")

    def test_and_the_final_over_its_test_versions(self):
        final = updates.latest(self.API_CON_LA_FINAL, "testing")
        self.assertEqual((final.version, final.prerelease), ((0, 4, 0), None))

    def test_a_test_version_on_stable_gets_its_final(self):
        final = updates.latest(self.API_CON_LA_FINAL, "stable")
        self.assertTrue(updates.is_newer(final, "0.4.0rc2"))

    def test_without_a_choice_a_test_version_follows_the_tests(self):
        self.assertEqual(updates.channel_for("", "0.4.0rc2"), "testing")
        self.assertEqual(updates.channel_for("", "0.4.0"), "stable")
        self.assertEqual(updates.channel_for("stable", "0.4.0rc2"), "stable")
        self.assertEqual(updates.channel_for("testing", "0.4.0"), "testing")

    def test_check_asks_the_channel(self):
        red = Red({updates.API_URL: json.dumps(self.API).encode()})
        self.assertEqual(updates.check(red, channel="testing").prerelease, 3)
        self.assertEqual(updates.check(red, channel="stable").version, (0, 3, 0))


class TestQueCopiaEs(unittest.TestCase):
    def test_el_compatible_baja_el_compatible(self):
        self.assertEqual(updates.asset_name("20261118.c01944d-compat"), updates.COMPAT)

    def test_el_normal_y_el_codigo_bajan_el_normal(self):
        self.assertEqual(updates.asset_name("20261118.c01944d"), updates.NORMAL)
        self.assertEqual(updates.asset_name(""), updates.NORMAL)

    def test_the_compatible_one_says_when_the_normal_would_run(self):
        from silux.ui import guarda

        compat, normal = "20261123.a5b145b-compat", "20261123.a5b145b"
        for has_v2, build, said in ((True, compat, True), (False, compat, False),
                                    (None, compat, False), (True, normal, False)):
            with self.subTest(has_v2=has_v2, build=build), \
                    mock.patch.object(guarda, "has_x86_64_v2", return_value=has_v2):
                self.assertIs(updates.normal_would_run(build), said)

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

        falso = mock.Mock(open=abrir_falso)
        with mock.patch.object(updates, "_opener", return_value=falso):
            updates.check()
        peticion, espera = abiertas[0]
        self.assertEqual(peticion.get_header("User-agent"), f"silux/{__version__}")
        self.assertEqual(set(peticion.headers), {"User-agent", "Accept"})
        self.assertEqual(espera, updates.TIMEOUT_S)

    def test_nada_que_no_sea_https(self):
        # Con el abridor de verdad tapado: si la guarda faltara, el test no
        # puede acabar saliendo a la red.
        with mock.patch.object(updates, "_opener", side_effect=AssertionError("salió")), \
                self.assertRaises(updates.UpdateError) as caso:
            updates.open_url("http://api.github.com/repos/rcv11x/silux/releases", 1)
        self.assertEqual(caso.exception.code, "insecure")

    def test_una_redireccion_a_http_se_corta(self):
        with self.assertRaises(updates.UpdateError) as caso:
            updates._HttpsOnly().redirect_request(None, None, 302, "", {}, "http://ejemplo.org/x")
        self.assertEqual(caso.exception.code, "insecure")

    def test_y_se_dice_por_que_y_no_que_falta_red(self):
        """Con el GitHub falso de la prueba de punta a punta, una descarga
        redirigida a http:// salía «no hay conexión con GitHub»."""
        release = updates.Release((9, 0, 0), "v9.0.0", "u", {
            updates.NORMAL: "https://github.com/a", updates.SUMS: "https://github.com/s"})

        def abrir(url, espera):
            if url.endswith("/s"):
                return io.BytesIO(f"{'0' * 64}  {updates.NORMAL}\n".encode())
            return updates._HttpsOnly().redirect_request(None, None, 302, "", {}, "http://x/a")

        with tempfile.TemporaryDirectory() as carpeta:
            destino = pathlib.Path(carpeta, updates.NORMAL)
            destino.write_bytes(b"viejo")
            with self.assertRaises(updates.UpdateError) as caso:
                updates.install(release, destino, updates.NORMAL, opener=abrir)
            self.assertEqual(caso.exception.code, "insecure")
            self.assertEqual(destino.read_bytes(), b"viejo")

    def test_sin_red_es_un_error_con_su_motivo(self):
        red = Red({updates.API_URL: urllib.error.URLError("sin red")})
        with self.assertRaises(updates.UpdateError) as caso:
            updates.check(red)
        self.assertEqual(caso.exception.code, "network")

    def test_una_lista_enorme_no_se_lee_entera(self):
        red = Red({updates.API_URL: b"[" + b" " * updates.MAX_LIST_BYTES + b"]"})
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
        with mock.patch.object(updates, "MAX_APPIMAGE_BYTES", 1000):
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


class TestElCiPublicaLasSumas(unittest.TestCase):
    """Sin `SHA256SUMS` en la release, el programa no se actualiza: lo tiene
    que subir el CI, con los dos AppImage y con los nombres que se buscan."""

    def setUp(self):
        self.flujo = (pathlib.Path(__file__).resolve().parent.parent
                      / ".github" / "workflows" / "appimage.yml").read_text()

    def test_las_sumas_cubren_los_dos_appimage(self):
        orden = [linea for linea in self.flujo.splitlines()
                 if "sha256sum" in linea and not linea.lstrip().startswith("#")]
        self.assertEqual(len(orden), 1, orden)
        self.assertIn(updates.NORMAL, orden[0])
        self.assertIn(updates.COMPAT, orden[0])
        self.assertTrue(orden[0].rstrip().endswith("> " + updates.SUMS), orden[0])

    def test_se_publican_en_la_release(self):
        publicar = self.flujo[self.flujo.index("action-gh-release"):]
        self.assertIn(f"dist/{updates.SUMS}", publicar)
        for nombre in (updates.NORMAL, updates.COMPAT):
            self.assertIn(f"dist/{nombre}", publicar)


@unittest.skipUnless(HAS_SVG, "hace falta el complemento qsvg de Qt")
class TestElAccesoDirecto(_EnCasaFalsa):
    """La entrada de menú apunta a `$APPIMAGE`; el nuevo ocupa esa ruta."""

    def test_sigue_al_dia_despues_de_sustituir(self):
        destino = self.casa / "Aplicaciones" / "Silux x86_64.AppImage"
        destino.parent.mkdir()
        destino.write_bytes(b"el viejo")
        destino.chmod(0o755)
        lanzador = desktop.current_launcher({"APPIMAGE": str(destino)})
        desktop.set_shortcuts(True, True, lanzador)
        entrada = desktop.desktop_path().read_text()
        acceso = desktop.shortcut_path().read_text()
        self.assertEqual(desktop.status(lanzador).state, "current")

        nuevo = b"el nuevo" * 100
        red = Red({V + updates.SUMS: f"{hashlib.sha256(nuevo).hexdigest()}  "
                                     f"{updates.NORMAL}\n".encode(),
                   V + updates.NORMAL: nuevo})
        updates.install(updates.latest([_release()]), destino, updates.NORMAL, red)

        self.assertEqual(destino.read_bytes(), nuevo)
        self.assertTrue(os.access(destino, os.X_OK))
        self.assertEqual(desktop.desktop_path().read_text(), entrada)
        # The one on the desktop too: the new AppImage took the same path.
        self.assertEqual(desktop.shortcut_path().read_text(), acceso)
        self.assertEqual(desktop.status(lanzador).state, "current")


if __name__ == "__main__":
    unittest.main()


class TestLaConexionSegura(unittest.TestCase):
    """Lo que hace falta para hablar con GitHub por HTTPS, de verdad.

    Probado de punta a punta con el AppImage del CI y un GitHub falso
    (mitmproxy): el Python de dentro no traía `_ssl`, ninguna URL `https://`
    se podía abrir y la ventana decía «no hay conexión con GitHub». Y el
    OpenSSL de dentro busca los certificados en un solo sitio, que no todas
    las familias usan.
    """

    def setUp(self):
        # Back as it was: the suite's offline opener (tests/__init__.py).
        self.addCleanup(setattr, updates, "_opener_built", updates._opener_built)
        updates._opener_built = None

    def test_sin_ssl_se_dice_que_falta_tls_y_no_que_falta_red(self):
        import sys
        with mock.patch.dict(sys.modules, {"ssl": None}):
            with self.assertRaises(updates.UpdateError) as error:
                updates.open_url(updates.API_URL, 1.0)
        self.assertEqual(error.exception.code, "notls")

    def test_se_fia_de_los_certificados_del_sistema(self):
        import os
        import ssl
        sistema = next((r for r in updates.CA_BUNDLES if os.path.isfile(r)), None)
        if sistema is None:
            self.skipTest("este equipo no tiene almacén de certificados en un sitio conocido")
        vacio = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        with mock.patch.object(ssl, "create_default_context", return_value=vacio):
            abridor = updates._opener()
        manejador = next(h for h in abridor.handlers
                         if isinstance(h, __import__("urllib.request").request.HTTPSHandler))
        self.assertIs(manejador._context, vacio)
        self.assertGreater(vacio.cert_store_stats()["x509_ca"], 0)
