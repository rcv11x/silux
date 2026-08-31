"""Lo que se le pasa a pkexec, que es lo que corre como root.

`pkexec` no valida los argumentos del programa que ejecuta, y lo dice su
propio manual: «if an action is used for which the user can retain
authorization… this could be a security hole». Aquí eso se traduce en una
regla que no admite excepciones: **en una orden de pkexec no puede aparecer
ninguna ruta que el usuario pueda reescribir.**

Si aparece, cualquier proceso del propio usuario —un navegador comprometido,
un paquete de pip con sorpresa— puede sustituir ese archivo entre que el
programa lo escribe y que root lo abre, y conseguir ejecución como root. En
el instalador la ventana era el diálogo de la contraseña entero, segundos, y
lo que se ganaba no era ejecutar una vez: era dejar instalado un binario de
root con su acción de polkit apuntándole.

El test que importa es `test_ninguna_orden_lleva_una_ruta_escribible`. Está
escrito para fallar si alguien vuelve a meter una copia en una carpeta del
usuario, que es como se llegó aquí tres veces seguidas.
"""

import os
import pathlib
import subprocess
import sys
import unittest
from unittest import mock

from silux.privileged import client
from silux.privileged.client import PrivilegedClient

RAIZ = pathlib.Path(__file__).resolve().parent.parent


def _ancestros(camino: pathlib.Path):
    """El propio camino, si existe, y todas las carpetas de encima que existan."""
    if camino.exists():
        yield camino
    for padre in camino.parents:
        if padre.exists():
            yield padre


def por_que_es_sustituible(ruta: str) -> str:
    """Por qué un usuario que no sea root podría cambiar lo que hay ahí, o "".

    A propósito no usa `client.escribible_por_el_usuario`: comprobar el código
    con su propia función deja pasar el día que la función se equivoque. Y va
    por propietario y modo en vez de por `os.access`, para que siga midiendo
    algo cuando la suite la ejecuta root, que es como corre el CI.
    """
    camino = pathlib.Path(ruta).resolve()
    for parte in _ancestros(camino):
        info = parte.stat()
        que = "el archivo" if parte == camino else f"la carpeta {parte}"
        if info.st_uid != 0:
            return f"{que} es de uid {info.st_uid} y no de root"
        if info.st_mode & 0o022:
            return f"{que} la puede escribir su grupo o cualquiera ({info.st_mode & 0o777:o})"
    return ""


def rutas_de(orden: list[str]) -> list[str]:
    """Los elementos de una orden que son rutas de verdad.

    El resto son banderas y, desde que el guion viaja por `argv`, también su
    fuente entera. Nada de eso es una ruta y nada de eso lo puede cambiar
    nadie después del `exec()`.
    """
    rutas = []
    for pieza in orden:
        if pieza == "pkexec":
            import shutil

            encontrado = shutil.which("pkexec")
            if encontrado:
                rutas.append(encontrado)
            continue
        if not pieza.startswith("/") or "\n" in pieza:
            continue
        rutas.append(pieza)
    return rutas


class ComprobadorDeOrdenes(unittest.TestCase):
    """Base para los tests que examinan una orden de pkexec."""

    def comprobar(self, orden: list[str], contexto: str = "") -> None:
        self.assertEqual(orden[0], "pkexec", f"{contexto}: no empieza por pkexec")
        rutas = rutas_de(orden)
        self.assertTrue(rutas, f"{contexto}: no se ha reconocido ninguna ruta, "
                               "así que este test no está comprobando nada")
        for ruta in rutas:
            with self.subTest(contexto=contexto, ruta=ruta):
                motivo = por_que_es_sustituible(ruta)
                self.assertEqual(
                    motivo, "",
                    f"{contexto}: pkexec ejecutaría «{ruta}» y {motivo}. "
                    "Lo que corre como root no puede salir de una ruta que el "
                    "usuario pueda cambiar; si hace falta un guion suelto, va "
                    "por argv con `client.en_linea`.")


class TestNingunaRutaEscribible(ComprobadorDeOrdenes):
    def test_ninguna_orden_lleva_una_ruta_escribible(self):
        """El del ayudante, sin instalar: es el camino del AppImage."""
        with mock.patch.object(PrivilegedClient, "instalado", return_value=False):
            self.comprobar(PrivilegedClient()._orden(), "cliente sin instalar")

    def test_tampoco_con_el_ayudante_instalado(self):
        with mock.patch.object(PrivilegedClient, "instalado", return_value=True):
            orden = PrivilegedClient()._orden()
        self.assertEqual(orden, ["pkexec", str(client.HELPER_INSTALADO)])
        self.comprobar(orden, "cliente instalado")

    def test_no_se_escribe_nada_en_la_cache(self):
        """La copia era el agujero; que no vuelva por descuido."""
        import tempfile

        with tempfile.TemporaryDirectory() as carpeta:
            with mock.patch.dict(os.environ, {"XDG_CACHE_HOME": carpeta}), \
                 mock.patch.object(PrivilegedClient, "instalado", return_value=False), \
                 mock.patch.object(PrivilegedClient, "empaquetado", return_value=True):
                PrivilegedClient()._orden()
            dejado = list(pathlib.Path(carpeta).rglob("*"))
        self.assertEqual(dejado, [], f"dejó archivos en la caché: {dejado}")


class TestElAyudanteViajaPorArgv(unittest.TestCase):
    def test_la_fuente_es_la_del_ayudante_sin_tocar(self):
        with mock.patch.object(PrivilegedClient, "instalado", return_value=False):
            orden = PrivilegedClient()._orden()
        self.assertIn(client.HELPER.read_text(encoding="utf-8"), orden)

    def test_cabe_en_un_argumento(self):
        """El kernel corta en MAX_ARG_STRLEN, 32 páginas. Hoy va al 16 %, pero
        el ayudante crece y quedarse sin sitio sería un fallo raro de leer:
        `pkexec` devolvería E2BIG sin decir de qué argumento habla."""
        import mmap

        fuente = client.HELPER.read_text(encoding="utf-8")
        self.assertLess(len(fuente.encode()), 32 * mmap.PAGESIZE)

    def test_arranca_de_verdad_y_contesta(self):
        """Sin pkexec delante: lo que se prueba es que el ayudante funciona
        ejecutado así, no que polkit autorice."""
        import json

        with mock.patch.object(PrivilegedClient, "instalado", return_value=False):
            orden = PrivilegedClient()._orden()[1:]
        hecho = subprocess.run(orden, input='{"action": "ping"}\n',
                               capture_output=True, text=True, timeout=60)
        respuesta = json.loads(hecho.stdout.splitlines()[0])
        # Sin privilegios contesta que no es root, que es la respuesta correcta:
        # significa que se compiló, arrancó y despachó la petición.
        self.assertIn("ok", respuesta)
        self.assertEqual(respuesta.get("error"), "not_root")


class TestElTracebackSigueDiciendoDeDondeEs(unittest.TestCase):
    """Sin esto el arreglo se pagaría en el flujo de reportar fallos.

    `python3 -c` compila con el nombre «<string>», así que un fallo del
    ayudante llegaría sin archivo y —según la versión de Python del sistema—
    sin el texto de la línea. Es lo primero que se mira en un informe.
    """

    FUENTE = ('def leer(cual):\n'
              '    tabla = {"a": 1}\n'
              '    return tabla[cual]\n'
              '\n'
              '\n'
              'if __name__ == "__main__":\n'
              '    leer("no_existe")\n')

    def _traceback(self) -> str:
        hecho = subprocess.run(
            [sys.executable, "-c", client.ARRANQUE, "silux-helper.py", self.FUENTE],
            capture_output=True, text=True, timeout=60)
        return hecho.stderr

    def test_dice_el_nombre_del_archivo(self):
        self.assertIn('File "silux-helper.py"', self._traceback())

    def test_dice_la_linea_y_su_texto(self):
        salida = self._traceback()
        self.assertIn("line 3", salida)
        self.assertIn("return tabla[cual]", salida,
                      "sin cebar linecache el traceback se queda sin el código")

    def test_no_dice_string(self):
        # El marco del propio arranque sí sale como «<string>» y está bien que
        # salga: dice que el guion se lanzó en línea. Lo que no puede pasar es
        # que los marcos del guion salgan así.
        for linea in self._traceback().splitlines():
            if "line" in linea and "leer" in linea:
                self.assertNotIn("<string>", linea)


class TestElAyudanteInstaladoNecesitaSuPolitica(unittest.TestCase):
    """Las dos mitades o ninguna.

    El binario sin la política se ejecuta igual, pero por la acción genérica
    de pkexec: contraseña en cada arranque en vez de una por sesión, que es el
    motivo entero de instalarlo. Mirando solo el binario, el botón de permisos
    permanentes se escondía diciendo que ya estaba hecho.
    """

    def test_sin_la_politica_no_cuenta_como_instalado(self):
        import tempfile

        with tempfile.TemporaryDirectory() as carpeta:
            binario = pathlib.Path(carpeta) / "silux-helper"
            binario.write_text("#!/bin/true\n", encoding="utf-8")
            binario.chmod(0o755)
            politica = pathlib.Path(carpeta) / "org.silux.helper.policy"

            with mock.patch.object(client, "HELPER_INSTALADO", binario), \
                 mock.patch.object(client, "POLITICA_INSTALADA", politica):
                self.assertFalse(PrivilegedClient.instalado(),
                                 "sin política no está instalado del todo")
                politica.write_text("<policyconfig/>\n", encoding="utf-8")
                self.assertTrue(PrivilegedClient.instalado())

    def test_las_dos_rutas_son_las_que_escribe_el_instalador(self):
        """Una en el cliente y otra en el instalador: si se separan, el cliente
        buscaría en un sitio donde nadie pone nada."""
        from silux.privileged import instalar

        self.assertEqual(client.HELPER_INSTALADO, instalar.DESTINO)
        self.assertEqual(client.POLITICA_INSTALADA, instalar.POLITICA)


if __name__ == "__main__":
    unittest.main()
