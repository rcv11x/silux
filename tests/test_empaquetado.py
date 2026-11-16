"""Lo que el empaquetador promete del paquete que se reparte.

Estas pruebas no construyen nada: miran las decisiones que toma
`tools/build_appimage.py` antes de construir, que es donde se cuelan los
fallos que luego solo se ven en la máquina de otro.
"""

import re
import unittest


def _version(texto: str) -> tuple[int, ...]:
    return tuple(int(parte) for parte in texto.split("."))


def _admite(rango: str, version: str) -> bool:
    """Si `version` cumple un rango de pip como «PySide6>=6.6,<6.12».

    Escrito a mano y no con `packaging` porque el Python del CI no lo trae
    como módulo importable, y aquí solo hacen falta las cinco comparaciones
    que se usan en un rango.
    """
    especificacion = re.sub(r"^[A-Za-z0-9_.-]+", "", rango.strip())
    v = _version(version)
    for condicion in filter(None, (c.strip() for c in especificacion.split(","))):
        operador, numero = re.fullmatch(r"(>=|<=|==|!=|<|>)\s*([\d.]+)", condicion).groups()
        n = _version(numero)
        largo = max(len(v), len(n))
        a = v + (0,) * (largo - len(v))
        b = n + (0,) * (largo - len(n))
        cumple = {">=": a >= b, "<=": a <= b, "==": a == b,
                  "!=": a != b, "<": a < b, ">": a > b}[operador]
        if not cumple:
            return False
    return True


class TestElQtQueSeEmpaqueta(unittest.TestCase):
    """PySide6 6.12.0 deja de llevar bien la cuenta de las referencias a `None`.

    Cada llamada a un método que devuelve `void` —`lineTo`, `setY`,
    `cubicTo`…— le quita una. Desde Python 3.12 `None` es inmortal y no se
    nota; en 3.10 y 3.11 la cuenta llega a cero y el proceso muere con
    «Fatal Python error: none_dealloc». El AppImage normal lleva el Python
    3.10 de Ubuntu 22.04, así que con un rango sin techo el próximo que se
    construyera abortaría al pintar la primera gráfica. Con 6.11.3 el
    balance es cero y la suite entera pasa en 3.10.

    El CI pregunta el rango a `--pyside-range`, así que este mismo techo
    alcanza a los tests en 3.10 y a la construcción, dentro o fuera del
    contenedor.
    """

    def _rangos(self):
        import tools.build_appimage as build
        return build.RANGO_PYSIDE

    def test_ningun_paquete_se_lleva_el_pyside_que_rompe_python_3_10(self):
        for compat, rango in self._rangos().items():
            with self.subTest(compat=compat, rango=rango):
                self.assertFalse(_admite(rango, "6.12.0"),
                                 "este rango deja entrar PySide6 6.12.0, que "
                                 "aborta en el Python 3.10 del AppImage")

    def test_pero_el_normal_sigue_llevandose_la_ultima_que_funciona(self):
        # El techo es por un fallo concreto, no un cambio de criterio: el
        # paquete normal sigue llevándose la serie más nueva que arranca.
        rangos = self._rangos()
        self.assertTrue(_admite(rangos[False], "6.11.3"))
        self.assertTrue(_admite(rangos[True], "6.9.3"))
        self.assertFalse(_admite(rangos[True], "6.10.0"),
                         "el compat no puede llevar un Qt de x86-64-v2")

    def test_el_comparador_de_rangos_sabe_decir_que_no(self):
        # Sin esto, un `_admite` que contestara siempre False daría por
        # buenos los dos tests de arriba sin haber leído nada.
        self.assertTrue(_admite("PySide6>=6.6", "6.12.0"))
        self.assertFalse(_admite("PySide6>=6.6,<6.12", "6.12.0"))
        self.assertTrue(_admite("PySide6>=6.6,<6.12", "6.11.3"))
        self.assertFalse(_admite("PySide6>=6.6,!=6.12.0", "6.12.0"))


class TestQuienInstalaDesdeElCodigo(unittest.TestCase):
    """El extra `gui` del `pyproject` no deja entrar la 6.12.0 donde se cae.

    La regla es que `pyproject.toml` no pone techos a PySide6: no le toca
    decidir qué Qt corre en la máquina de otro. Esta es la excepción, y solo
    para Python 3.10 y 3.11, que es donde el fallo de `None` de la 6.12.0
    tumba el proceso. Desde 3.12 `None` es inmortal y la 6.12 funciona, así
    que ahí no se le quita a nadie.
    """

    def _requisitos(self) -> list[str]:
        import pathlib
        texto = (pathlib.Path(__file__).resolve().parent.parent
                 / "pyproject.toml").read_text()
        bloque = re.search(r"^gui\s*=\s*\[(.*?)\]", texto, re.S | re.M).group(1)
        lineas = [l.split("#", 1)[0] for l in bloque.splitlines()]
        return re.findall(r'"([^"]+)"', "\n".join(lineas))

    def _rangos_para(self, python: str) -> list[str]:
        """Los rangos de PySide6 que aplican en esa versión de Python."""
        rangos = []
        for requisito in self._requisitos():
            rango, _, marcador = requisito.partition(";")
            if marcador.strip():
                operador, version = re.fullmatch(
                    r"\s*python_version\s*(<|>=)\s*['\"]([\d.]+)['\"]\s*",
                    marcador).groups()
                if not _admite(f"x{operador}{version}", python):
                    continue
            rangos.append(rango.strip())
        return rangos

    def test_en_3_10_y_3_11_no_entra_la_6_12_0(self):
        for python in ("3.10", "3.11"):
            with self.subTest(python=python):
                rangos = self._rangos_para(python)
                self.assertTrue(rangos, f"en {python} no se pide ningún PySide6")
                for rango in rangos:
                    self.assertFalse(_admite(rango, "6.12.0"), rango)
                    self.assertTrue(_admite(rango, "6.11.3"), rango)

    def test_desde_3_12_no_se_le_pone_techo(self):
        for python in ("3.12", "3.14"):
            with self.subTest(python=python):
                rangos = self._rangos_para(python)
                self.assertEqual(len(rangos), 1, rangos)
                self.assertTrue(_admite(rangos[0], "6.12.0"), rangos[0])


class TestElCiConstruyeComoSeReparte(unittest.TestCase):
    """El AppImage que se publica tiene que salir del contenedor.

    El de la v0.2.0 se construyó en el runner, con el Python y las
    bibliotecas que trajera ese día, y no con la receta del contenedor.
    Salió sin siete `libxcb-*` —`cursor`, `icccm`, `image`, `keysyms`,
    `render-util`, `shape` y `util`— que `libqxcb.so` declara en su
    `NEEDED` y que el mismo paquete construido con `--container` sí lleva:
    la receta las instala antes de empaquetar porque `ldd` solo informa de
    lo que puede resolver. En un X11 sin `libxcb-cursor0` eso es un
    programa que no abre.
    """

    def _construcciones(self) -> list[str]:
        import pathlib
        flujo = (pathlib.Path(__file__).resolve().parent.parent
                 / ".github" / "workflows" / "appimage.yml").read_text()
        ordenes = [linea.strip() for linea in flujo.splitlines()
                   if "build_appimage.py" in linea
                   and not linea.lstrip().startswith("#")]
        return [o for o in ordenes if "--pyside-range" not in o]

    def test_hay_algo_que_mirar(self):
        # Que el flujo construya los dos paquetes; si se renombra el
        # empaquetador, el test de abajo no puede quedarse en verde sin
        # haber encontrado ninguna orden.
        construcciones = self._construcciones()
        self.assertEqual(len(construcciones), 2, construcciones)
        self.assertEqual(sum("--compat" in o for o in construcciones), 1)

    def test_las_dos_construcciones_van_dentro_del_contenedor(self):
        for orden in self._construcciones():
            with self.subTest(orden=orden):
                self.assertIn("--container", orden)


class TestLasAccionesDelCiCorrenEnNode24(unittest.TestCase):
    """GitHub retira Node 20 de los runners y avisa en cada ejecución.

    Las versiones de abajo son la primera de cada acción que declara
    `using: node24` en su `action.yml`, preguntado a GitHub y no supuesto:
    upload-artifact todavía iba en Node 20 en su v5. La de publicar la
    release solo corre al etiquetar, así que su aviso no salía en las
    ejecuciones normales, y es la que no puede fallar el día que toca.
    """

    PRIMERA_CON_NODE24 = {
        "actions/checkout": 5,
        "actions/setup-python": 6,
        "actions/upload-artifact": 6,
        "softprops/action-gh-release": 3,
    }

    def test_ninguna_se_queda_en_node_20(self):
        import pathlib
        flujo = (pathlib.Path(__file__).resolve().parent.parent
                 / ".github" / "workflows" / "appimage.yml").read_text()
        usadas = re.findall(r"^\s*-?\s*uses:\s*([\w.-]+/[\w.-]+)@v(\d+)",
                            flujo, re.M)
        self.assertEqual({a for a, _v in usadas}, set(self.PRIMERA_CON_NODE24),
                         "el flujo usa una acción que este test no conoce")
        for accion, version in usadas:
            with self.subTest(accion=accion):
                self.assertGreaterEqual(int(version),
                                        self.PRIMERA_CON_NODE24[accion])


class TestUnPaqueteIncompletoNoSeEmpaqueta(unittest.TestCase):
    """Si al AppDir le falta una biblioteca, la construcción falla.

    `comprobar_autocontenido` lo veía y lo escribía en stderr, y la
    construcción seguía y devolvía cero. Así se publicó la v0.2.0 sin siete
    `libxcb-*`. Aquí se monta un AppDir de mentira y se le hace decir a `ldd`
    lo que dijo en el runner: que `libqxcb.so` pide una `libxcb-cursor` que no
    encuentra en ninguna parte.
    """

    def setUp(self):
        import pathlib
        import tempfile
        from unittest import mock

        import tools.build_appimage as build
        self.build = build
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.appdir = pathlib.Path(self._tmp.name) / "silux.AppDir"
        plataformas = self.appdir / "usr" / "plugins" / "platforms"
        plataformas.mkdir(parents=True)
        (plataformas / "libqxcb.so").write_bytes(b"\x7fELF")
        (self.appdir / "usr" / "bin").mkdir(parents=True)
        interprete = self.appdir / "usr" / "bin" / "python3"
        interprete.write_bytes(b"\x7fELF")
        interprete.chmod(0o755)

        self.preguntados = []

        def ldd(objeto, extra=None, ausentes=False):
            self.preguntados.append(objeto.name)
            if objeto.name == "libqxcb.so" and self.falta_cursor:
                return [], ["libxcb-cursor.so.0"]
            return [], []

        self.falta_cursor = True
        for nombre, valor in (("APPDIR", self.appdir), ("dependencias", ldd)):
            parche = mock.patch.object(build, nombre, valor)
            parche.start()
            self.addCleanup(parche.stop)

    def _construir(self):
        """`main` entero, con los pasos que copian y empaquetan sustituidos."""
        import contextlib
        import io
        import sys
        from unittest import mock

        build = self.build
        vacio = mock.Mock(return_value=set())
        pasos = {nombre: vacio for nombre in (
            "copiar_python", "copiar_silux", "copiar_pyside",
            "copiar_plugins", "copiar_bibliotecas", "quitar_simbolos",
            "escribir_metadatos", "sellar_build", "avisar_de_compatibilidad")}
        pasos["comprobar_juego_de_instrucciones"] = mock.Mock(return_value=[])
        self.empaquetar = mock.Mock(return_value=None)
        pasos["empaquetar"] = self.empaquetar
        # `main` empieza borrando el AppDir y creando uno vacío; el de mentira
        # se vuelve a montar justo después, cuando ya no lo va a tocar.
        montado = self.appdir.parent / "montado"
        import shutil
        shutil.copytree(self.appdir, montado)

        def copiar_python():
            shutil.rmtree(self.appdir)
            shutil.copytree(montado, self.appdir)
            return set()
        pasos["copiar_python"] = copiar_python
        with mock.patch.multiple(build, **pasos), \
             mock.patch.object(sys, "argv", ["build_appimage.py"]), \
             contextlib.redirect_stdout(io.StringIO()), \
             contextlib.redirect_stderr(io.StringIO()) as errores:
            codigo = build.main()
        return codigo, errores.getvalue()

    def test_si_falta_una_biblioteca_sale_con_error_y_no_empaqueta(self):
        codigo, errores = self._construir()
        self.assertNotEqual(codigo, 0)
        self.empaquetar.assert_not_called()
        self.assertIn("libxcb-cursor.so.0", errores)

    def test_si_no_falta_nada_empaqueta(self):
        # La otra mitad: que la comprobación no lo pare todo por sistema.
        self.falta_cursor = False
        self._construir()
        self.empaquetar.assert_called_once()

    def test_se_pregunta_tambien_por_el_interprete(self):
        import contextlib
        import io

        self.falta_cursor = False
        with contextlib.redirect_stdout(io.StringIO()):
            self.build.comprobar_autocontenido()
        self.assertIn("python3", self.preguntados)
        self.assertIn("libqxcb.so", self.preguntados)


class TestLaGuardaDelAppRun(unittest.TestCase):
    """Lo que hace el AppRun en un procesador al que le faltan instrucciones.

    Se ejecuta el AppRun que escribe el empaquetador, con `sh`, contra un
    `/proc/cpuinfo` sin SSE4.1 y con un `python3` de mentira que solo dice qué
    módulo le pidieron arrancar. La guarda corría antes de mirar los
    argumentos, así que bloqueaba también el `--report` que su propio mensaje
    recomienda como salida: el CLI no importa Qt y correría en ese procesador,
    y es justo el archivo que se le pide a esa persona. El mensaje mandaba
    además a `$0`, que dentro de un AppImage es el punto de montaje temporal,
    y elegía idioma solo por `LANG`.
    """

    def setUp(self):
        import os
        import pathlib
        import tempfile
        from unittest import mock

        import tools.build_appimage as build
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        raiz = pathlib.Path(self._tmp.name)
        appdir = raiz / "silux.AppDir"
        (appdir / "usr" / "bin").mkdir(parents=True)
        (appdir / "usr" / "lib").mkdir(parents=True)
        python = appdir / "usr" / "bin" / "python3"
        # `-c ARRANQUE MODULO argumentos…`: el módulo es el tercero.
        python.write_text('#!/bin/sh\necho "arranca $3"\n')
        python.chmod(0o755)
        sin_sse = raiz / "cpuinfo"
        sin_sse.write_text("processor\t: 0\nflags\t\t: fpu sse sse2\n")

        with mock.patch.object(build, "APPDIR", appdir):
            build.escribir_metadatos({"sse4_1"})
        self.apprun = appdir / "AppRun"
        guion = self.apprun.read_text()
        self.assertIn("/proc/cpuinfo", guion)
        self.apprun.write_text(guion.replace("/proc/cpuinfo", str(sin_sse)))
        self.entorno_base = {"PATH": os.environ.get("PATH", "/usr/bin:/bin")}

    def _lanzar(self, *argumentos, **entorno):
        import subprocess
        return subprocess.run(["sh", str(self.apprun), *argumentos],
                              env={**self.entorno_base, **entorno},
                              capture_output=True, text=True, timeout=30)

    def test_la_interfaz_no_arranca_y_lo_explica(self):
        hecho = self._lanzar()
        self.assertEqual(hecho.returncode, 1)
        self.assertNotIn("arranca", hecho.stdout)
        self.assertIn("sse4_1", hecho.stderr)

    def test_las_ordenes_del_cli_pasan(self):
        for argumentos in (("--report", "informe.md"), ("--report=informe.md",),
                           ("--json",), ("--sensors",), ("--version",),
                           ("--cli", "--watch")):
            with self.subTest(argumentos=argumentos):
                hecho = self._lanzar(*argumentos)
                self.assertEqual(hecho.returncode, 0, hecho.stderr)
                self.assertIn("arranca silux.cli", hecho.stdout)

    def test_recomienda_el_appimage_y_no_el_punto_de_montaje(self):
        hecho = self._lanzar(APPIMAGE="/home/ana/Descargas/silux-x86_64.AppImage")
        self.assertIn("/home/ana/Descargas/silux-x86_64.AppImage --report",
                      hecho.stderr)
        self.assertNotIn(str(self.apprun), hecho.stderr)

    def test_el_idioma_sigue_el_orden_de_posix(self):
        casos = (
            ({"LANG": "es_ES.UTF-8"}, "A este procesador"),
            ({"LC_ALL": "es_ES.UTF-8"}, "A este procesador"),
            ({"LC_MESSAGES": "es_MX.UTF-8", "LANG": "C"}, "A este procesador"),
            ({"LC_ALL": "C", "LANG": "es_ES.UTF-8"}, "This processor"),
            ({}, "This processor"),
        )
        for entorno, espera in casos:
            with self.subTest(entorno=entorno):
                self.assertIn(espera, self._lanzar(**entorno).stderr)


if __name__ == "__main__":
    unittest.main()
