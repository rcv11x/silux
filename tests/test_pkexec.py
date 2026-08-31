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


class TestLaOrdenDeInstalar(ComprobadorDeOrdenes):
    """El botón de permisos permanentes, que era el peor de los tres.

    Copiaba el instalador y el ayudante a ~/.cache y le pasaba las dos rutas a
    pkexec. La ventana no era una carrera de microsegundos: iba desde la copia
    hasta que root abría los archivos, con el diálogo de la contraseña en
    medio. Y no se ganaba ejecutar una vez, se ganaba dejar instalado un
    binario de root con su acción de polkit apuntándole.
    """

    @classmethod
    def setUpClass(cls):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication

        cls.app = QApplication.instance() or QApplication([])

    def _orden(self):
        from silux.ui.app import MainWindow

        return MainWindow._orden_de_instalacion()

    def test_ninguna_ruta_escribible(self):
        orden, _entrada = self._orden()
        self.comprobar(orden, "instalador")

    def test_el_instalador_va_por_argv_y_el_ayudante_por_la_tuberia(self):
        from silux.privileged import instalar

        fuente = pathlib.Path(instalar.__file__).read_text(encoding="utf-8")
        orden, entrada = self._orden()
        self.assertIn(fuente, orden,
                      "el instalador tiene que viajar por argv")
        self.assertEqual(entrada, client.HELPER.read_text(encoding="utf-8"),
                         "el ayudante tiene que ir por stdin, no por una ruta")
        self.assertIn("--from-stdin", orden)

    def test_no_se_escribe_nada_en_la_cache(self):
        import tempfile

        with tempfile.TemporaryDirectory() as carpeta:
            with mock.patch.dict(os.environ, {"XDG_CACHE_HOME": carpeta}):
                self._orden()
            self.assertEqual(list(pathlib.Path(carpeta).rglob("*")), [])


class TestElInstaladorNoAceptaUnaRuta(unittest.TestCase):
    """Que no vuelva la bandera que hacía falta quitar.

    `--from RUTA` solo tenía un usuario —la interfaz desde el AppImage— y era
    justo el vulnerable. Aceptar una ruta es aceptar que otro proceso decida
    qué se instala como root, así que la bandera no existe.
    """

    def test_ya_no_hay_bandera_que_reciba_una_ruta(self):
        from silux.privileged import instalar

        fuente = pathlib.Path(instalar.__file__).read_text(encoding="utf-8")
        self.assertNotIn('"--from"', fuente)
        self.assertNotIn("dest=\"origen\"", fuente)
        self.assertIn('"--from-stdin"', fuente)

    def test_instala_lo_que_llega_por_stdin(self):
        import io
        import tempfile

        from silux.privileged import instalar

        cuerpo = "#!/usr/bin/env python3\nprint('el ayudante')\n"
        with tempfile.TemporaryDirectory() as tmp:
            raiz = pathlib.Path(tmp)
            destino = raiz / "libexec" / "silux" / "silux-helper"
            politica = raiz / "acciones" / "org.silux.helper.policy"
            politica.parent.mkdir(parents=True)
            with mock.patch.object(instalar, "DESTINO", destino), \
                 mock.patch.object(instalar, "POLITICA", politica), \
                 mock.patch.object(instalar.os, "geteuid", lambda: 0), \
                 mock.patch.object(instalar.os, "chown", lambda *a, **k: None), \
                 mock.patch.object(sys, "stdin", io.StringIO(cuerpo)), \
                 mock.patch.object(sys, "stdout", io.StringIO()):
                self.assertEqual(instalar.main(["--from-stdin"]), 0)

            self.assertIn("print('el ayudante')",
                          destino.read_text(encoding="utf-8"))
            self.assertEqual(destino.stat().st_mode & 0o777, 0o755)
            # La acción clava la ruta del binario: es lo que impide que la
            # autorización recordada valga para ejecutar otra cosa.
            self.assertIn(str(destino), politica.read_text(encoding="utf-8"))

    def test_sin_nada_por_stdin_no_instala_un_ayudante_vacio(self):
        import io

        from silux.privileged import instalar

        with mock.patch.object(instalar.os, "geteuid", lambda: 0), \
             mock.patch.object(sys, "stdin", io.StringIO("   \n")):
            with self.assertRaises(SystemExit):
                instalar.main(["--from-stdin"])


if __name__ == "__main__":
    unittest.main()
