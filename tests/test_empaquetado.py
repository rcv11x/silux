"""Lo que el empaquetador promete del paquete que se reparte.

Estas pruebas no construyen nada: miran las decisiones que toma
`tools/build_appimage.py` antes de construir, que es donde se cuelan los
fallos que luego solo se ven en la máquina de otro.
"""

import pathlib
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
    """Cada paquete lleva un PySide6 que funciona con el Python que va dentro.

    PySide6 6.12.0 le quita una referencia a `None` en cada método que
    devuelve `void` —`lineTo`, `setY`, `cubicTo`…—. Desde Python 3.12 `None`
    es inmortal y no se nota; en 3.10 y 3.11 la cuenta llega a cero y el
    proceso muere con «Fatal Python error: none_dealloc» al pintar la
    primera gráfica. El normal lleva 3.14 y se lleva la última; el compat
    lleva el 3.10 y no puede llevarla.

    El CI pregunta el rango a `--pyside-range`, así que lo mismo alcanza a
    los tests de cada pareja y a la construcción.
    """

    def _build(self):
        import tools.build_appimage as build
        return build

    def test_ningun_paquete_con_python_viejo_se_lleva_la_6_12(self):
        build = self._build()
        for compat, rango in build.RANGO_PYSIDE.items():
            python = build.PYTHON[compat]
            if _version(python) >= (3, 12):
                continue
            with self.subTest(compat=compat, python=python, rango=rango):
                self.assertFalse(_admite(rango, "6.12.0"),
                                 f"este rango deja entrar PySide6 6.12.0, que "
                                 f"aborta en el Python {python} del paquete")

    def test_el_normal_se_lleva_la_ultima_y_el_compat_la_6_9(self):
        build = self._build()
        self.assertEqual(_version(build.PYTHON[False])[:2], (3, 14))
        self.assertTrue(_admite(build.RANGO_PYSIDE[False], "6.12.0"))
        self.assertTrue(_admite(build.RANGO_PYSIDE[True], "6.9.3"))
        self.assertFalse(_admite(build.RANGO_PYSIDE[True], "6.10.0"),
                         "el compat no puede llevar un Qt de x86-64-v2")

    def test_el_comparador_de_rangos_sabe_decir_que_no(self):
        # Sin esto, un `_admite` que contestara siempre False daría por
        # buenos los dos tests de arriba sin haber leído nada.
        self.assertTrue(_admite("PySide6>=6.6", "6.12.0"))
        self.assertFalse(_admite("PySide6>=6.6,<6.12", "6.12.0"))
        self.assertTrue(_admite("PySide6>=6.6,<6.12", "6.11.3"))
        self.assertFalse(_admite("PySide6>=6.6,!=6.12.0", "6.12.0"))


class TestElCiPruebaLoQueSeReparte(unittest.TestCase):
    """Los tests del CI corren con el Python y el PySide6 de cada paquete.

    Si la matriz dijera 3.12 y el paquete llevara 3.14, el verde del CI no
    diría nada del programa que se descarga. Se lee la matriz del flujo y se
    compara con la tabla del empaquetador, sin que nadie tenga que acordarse
    de cambiar los dos sitios.
    """

    def _matriz(self) -> list[dict[str, str]]:
        import pathlib
        flujo = (pathlib.Path(__file__).resolve().parent.parent
                 / ".github" / "workflows" / "appimage.yml").read_text()
        inicio = flujo.index("include:")
        bloque = flujo[inicio:flujo.index("steps:", inicio)]
        entradas = []
        for trozo in re.split(r"\n\s*- ", bloque)[1:]:
            campos = dict(re.findall(r'(\w+):\s*"?([^"\n]*)"?', trozo))
            entradas.append(campos)
        return entradas

    def test_each_package_with_its_python_and_the_module_both_ways(self):
        import tools.build_appimage as build
        matriz = self._matriz()
        self.assertEqual(sorted({e["paquete"] for e in matriz}), ["compat", "normal"], matriz)
        for entrada in matriz:
            compat = entrada["paquete"] == "compat"
            with self.subTest(paquete=entrada["paquete"], modulo=entrada.get("modulo")):
                self.assertEqual(entrada["python"], build.PYTHON[compat])
        # The suite with the native module, as both packages ship, and
        # without it, as a pip install may run.
        self.assertEqual({e.get("modulo") for e in matriz}, {"con", "sin"})

    def test_cada_pareja_instala_el_pyside_de_su_paquete(self):
        import pathlib
        flujo = (pathlib.Path(__file__).resolve().parent.parent
                 / ".github" / "workflows" / "appimage.yml").read_text()
        instala = [l for l in flujo.splitlines()
                   if "--pyside-range" in l and not l.lstrip().startswith("#")]
        self.assertEqual(len(instala), 1, instala)
        self.assertIn("matrix.paquete == 'compat' && '--compat'", instala[0])


class TestElPaqueteTraeTls(unittest.TestCase):
    """Sin `_ssl`, el AppImage no abre ninguna URL `https://`.

    El empaquetador lo quitaba por no usarse, y el actualizador decía que no
    había red. Ahora no se quita, y la construcción arranca el Python del
    AppDir y le pide un contexto TLS antes de empaquetar.
    """

    def setUp(self):
        import pathlib
        import tempfile
        from unittest import mock

        import tools.build_appimage as build
        self.build = build
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.appdir = pathlib.Path(tmp.name) / "silux.AppDir"
        (self.appdir / "usr" / "bin").mkdir(parents=True)
        parche = mock.patch.object(build, "APPDIR", self.appdir)
        parche.start()
        self.addCleanup(parche.stop)

    def _python(self, guion: str) -> None:
        python = self.appdir / "usr" / "bin" / "python3"
        python.write_text("#!/bin/sh\n" + guion)
        python.chmod(0o755)

    def _comprobar(self):
        import contextlib
        import io
        with contextlib.redirect_stdout(io.StringIO()) as salida, \
             contextlib.redirect_stderr(io.StringIO()) as errores:
            hecho = self.build.comprobar_tls()
        return hecho, salida.getvalue() + errores.getvalue()

    def test_no_se_quita_ssl(self):
        self.assertFalse(any(m.startswith(("_ssl", "_hashlib"))
                             for m in self.build.DYNLOAD_FUERA))

    def test_sin_ssl_la_construccion_se_para(self):
        # Lo que dice el Python de Ubuntu 22.04 con `_ssl` quitado.
        self._python('echo "ModuleNotFoundError: No module named \'_ssl\'" >&2\n'
                     "exit 1\n")
        hecho, texto = self._comprobar()
        self.assertFalse(hecho)
        self.assertIn("_ssl", texto)

    def test_con_ssl_sigue_y_dice_cual(self):
        self._python('echo "OpenSSL 3.5.9 29 Sep 2026"\n')
        hecho, texto = self._comprobar()
        self.assertTrue(hecho)
        self.assertIn("OpenSSL 3.5.9", texto)

    def test_arranca_con_su_propia_biblioteca(self):
        # Como el AppRun: PYTHONHOME dentro del AppDir, no el de quien construye.
        self._python('echo "$PYTHONHOME"\n')
        _hecho, texto = self._comprobar()
        self.assertIn(str(self.appdir / "usr"), texto)


class TestQuienInstalaDesdeElCodigo(unittest.TestCase):
    """El extra `gui` del `pyproject` no deja entrar la 6.11 ni la 6.12 donde
    se caen.

    La regla es que `pyproject.toml` no pone techos a PySide6: no le toca
    decidir qué Qt corre en la máquina de otro. Esta es la excepción, y solo
    para Python 3.10 y 3.11: ahí la 6.12.0 muere con «none_dealloc» y la 6.11
    revienta cuando la ventana cambia de forma (`tools/agitar_ventana.py`).
    Desde 3.12 las dos funcionan, así que ahí no se le quita a nadie.
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

    def test_en_3_10_y_3_11_no_entran_la_6_11_ni_la_6_12(self):
        for python in ("3.10", "3.11"):
            with self.subTest(python=python):
                rangos = self._rangos_para(python)
                self.assertTrue(rangos, f"en {python} no se pide ningún PySide6")
                for rango in rangos:
                    self.assertFalse(_admite(rango, "6.12.0"), rango)
                    self.assertFalse(_admite(rango, "6.11.3"), rango)
                    self.assertFalse(_admite(rango, "6.11.0"), rango)
                    self.assertTrue(_admite(rango, "6.10.3"), rango)

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


class TestTheCompatAsksForNoNewerGlibc(unittest.TestCase):
    """The build for old machines can't need a newer system than the normal
    one. It carried Ubuntu 22.04's own Python 3.10, which needs glibc 2.35
    where the normal one needs 2.34, and that image's libraries ask for 2.34
    on their own: PySide6 6.9 alone asks for 2.28.
    """

    def _container_command(self, compat: bool) -> list[str]:
        from unittest import mock

        import tools.build_appimage as build

        with mock.patch.object(build.shutil, "which", lambda _: "/usr/bin/podman"), \
             mock.patch.object(build.subprocess, "run") as run:
            run.return_value = mock.Mock(returncode=0)
            build.construir_en_contenedor(build.IMAGEN_BASE, compat)
        return run.call_args[0][0]

    def _image_chosen(self, *options: str) -> str:
        from unittest import mock

        import tools.build_appimage as build

        argv = ["build_appimage.py", "--container", *options]
        with mock.patch.object(build.sys, "argv", argv), \
             mock.patch.object(build, "construir_en_contenedor", return_value=0) as build_in:
            build.main()
        return build_in.call_args[0][0]

    def test_both_builds_carry_python_build_standalone(self):
        import tools.build_appimage as build

        for compat in (False, True):
            with self.subTest(compat=compat):
                wanted = build.PYTHON_STANDALONE.format(version=build.PYTHON[compat])
                self.assertIn(f"SILUX_PYTHON={wanted}", self._container_command(compat))

    def test_the_recipe_never_uses_the_image_python(self):
        import tools.build_appimage as build

        self.assertNotIn("break-system-packages", build.RECETA)
        self.assertIn('--python "$SILUX_PYTHON"', build.RECETA)

    def test_the_compat_is_built_on_an_older_base(self):
        import tools.build_appimage as build

        def release(image: str) -> tuple[int, ...]:
            return _version(image.rsplit(":", 1)[1])

        normal, compat = self._image_chosen(), self._image_chosen("--compat")
        self.assertEqual(normal, build.IMAGEN_BASE)
        self.assertEqual(compat, build.COMPAT_BASE_IMAGE)
        self.assertEqual(normal.rsplit(":", 1)[0], compat.rsplit(":", 1)[0])
        self.assertLess(release(compat), release(normal))

    def test_an_image_given_by_hand_is_kept(self):
        self.assertEqual(self._image_chosen("debian:11", "--compat"), "debian:11")

    def test_the_ci_opens_its_window_on_that_base(self):
        import tools.build_appimage as build

        workflow = (pathlib.Path(__file__).resolve().parent.parent
                    / ".github" / "workflows" / "appimage.yml").read_text()
        step = workflow.split("- name: Arrancar el compatible en el sistema de su suelo", 1)
        self.assertEqual(len(step), 2, "the CI step is gone")
        step = step[1].split("- name:", 1)[0]
        self.assertIn(build.COMPAT_BASE_IMAGE, step)
        self.assertIn("silux-x86_64-compat.AppImage --screenshot", step)


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


class TestLaEtiquetaNoPisaLasNotas(unittest.TestCase):
    """Las notas de una release son solo la entrada de su versión.

    El autor las pone en el borrador. Publicarlo crea la etiqueta, la
    etiqueta lanza el CI, y su paso de softprops/action-gh-release, con
    `body_path: CHANGELOG.md`, las sustituía por el CHANGELOG entero, todas
    las versiones: pasó con la 0.3.0. Sin body ni body_path, la acción deja
    las de la release que ya existe.
    """

    def test_el_paso_de_la_release_no_lleva_cuerpo(self):
        import re
        flujo = (pathlib.Path(__file__).resolve().parent.parent
                 / ".github" / "workflows" / "appimage.yml").read_text()
        paso = flujo[flujo.index("softprops/action-gh-release"):]
        paso = re.split(r"\n      - ", paso, maxsplit=1)[0]
        self.assertNotRegex(paso, r"\n\s+body(_path)?:")


class TestElBytecodeVaDentro(unittest.TestCase):
    """Los `.pyc` van compilados dentro del paquete y no se miran al importar.

    El punto de montaje del AppImage es de solo lectura: sin ellos, cada
    arranque compilaba silux entero y la parte de la biblioteca estándar que
    usa. Con ellos, `--version` pasó de 270 a 92 ms y la ventana ganó 330.
    Se compila con un Python de verdad, el de quien ejecuta los tests, puesto
    donde el empaquetador busca el de dentro.
    """

    def setUp(self):
        import pathlib
        import sys
        import tempfile
        from unittest import mock

        import tools.build_appimage as build
        self.build = build
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.appdir = pathlib.Path(tmp.name) / "silux.AppDir"
        (self.appdir / "usr" / "bin").mkdir(parents=True)
        self.paquete = self.appdir / "usr" / "lib" / "python" / "silux"
        self.paquete.mkdir(parents=True)
        (self.paquete / "modulo.py").write_text("VALOR = 1\n")
        python = self.appdir / "usr" / "bin" / "python3"
        # El AppDir de mentira no trae biblioteca estándar: el de quien
        # ejecuta usa la suya y no el PYTHONHOME que le pone el empaquetador.
        python.write_text(f'#!/bin/sh\nunset PYTHONHOME\nexec "{sys.executable}" "$@"\n')
        python.chmod(0o755)
        parche = mock.patch.object(build, "APPDIR", self.appdir)
        parche.start()
        self.addCleanup(parche.stop)

    def _compilar(self):
        import contextlib
        import io
        with contextlib.redirect_stdout(io.StringIO()), \
             contextlib.redirect_stderr(io.StringIO()) as errores:
            return self.build.compilar_bytecode(), errores.getvalue()

    def test_compila_sin_mirar_la_fuente(self):
        hecho, errores = self._compilar()
        self.assertTrue(hecho, errores)
        compilados = list((self.paquete / "__pycache__").glob("modulo.*.pyc"))
        self.assertEqual(len(compilados), 1)
        cabecera = compilados[0].read_bytes()[:16]
        # PEP 552: banderas 0b01 = por hash y sin comprobar la fuente.
        self.assertEqual(int.from_bytes(cabecera[4:8], "little"), 0b01)

    def test_un_archivo_que_no_compila_para_la_construccion(self):
        (self.paquete / "roto.py").write_text("def (:\n")
        hecho, errores = self._compilar()
        self.assertFalse(hecho)
        self.assertIn("roto.py", errores)


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
            "copiar_python", "copiar_silux", "copy_native_module", "copiar_pyside",
            "copiar_plugins", "copiar_bibliotecas", "quitar_simbolos",
            "escribir_metadatos", "sellar_build", "avisar_de_compatibilidad")}
        pasos["comprobar_juego_de_instrucciones"] = mock.Mock(return_value=[])
        pasos["comprobar_tls"] = mock.Mock(return_value=True)
        pasos["compilar_bytecode"] = mock.Mock(return_value=True)
        pasos["draw_file_icon"] = mock.Mock(return_value=True)
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


class TestLosComplementosDeImagen(unittest.TestCase):
    """El AppImage lleva `libqsvg.so`, que es con lo que se leen los iconos.

    El empaquetador buscaba `qsvg.so` y el archivo se llama `libqsvg.so`: la
    carpeta `imageformats` salía vacía y nadie se quejaba. Mientras el único
    SVG fue el icono de la ventana no se notó; con la barra lateral nueva, el
    AppImage arrancaba sin ningún icono ni la marca. Se vio abriendo el que
    construyó el CI, que solo comprobaba que arrancase.
    """

    def setUp(self):
        import pathlib
        import tempfile
        from unittest import mock

        import tools.build_appimage as build
        self.build = build
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        raiz = pathlib.Path(tmp.name)
        self.plugins = raiz / "plugins"
        self.appdir = raiz / "silux.AppDir"
        # Como los trae PySide6: con `lib` delante y con más de los que hacen falta.
        for carpeta, nombres in (
                ("imageformats", ("libqsvg.so", "libqico.so", "libqjpeg.so",
                                  "libqgif.so", "libqwebp.so", "libqtiff.so")),
                ("iconengines", ("libqsvgicon.so",)),
                ("platforms", ("libqxcb.so",))):
            (self.plugins / carpeta).mkdir(parents=True)
            for nombre in nombres:
                (self.plugins / carpeta / nombre).write_bytes(b"\x7fELF")
        for nombre, valor in (("APPDIR", self.appdir),
                              ("plugins_de_qt", lambda: self.plugins),
                              ("dependencias", lambda so, extra=None: []),
                              ("qt_propio", lambda: None)):
            parche = mock.patch.object(build, nombre, valor)
            parche.start()
            self.addCleanup(parche.stop)

    def _copiados(self):
        destino = self.appdir / "usr" / "lib" / "qt" / "plugins" / "imageformats"
        return sorted(p.name for p in destino.iterdir())

    def test_se_lleva_los_cuatro_y_ninguno_mas(self):
        self.build.copiar_plugins()
        self.assertEqual(self._copiados(),
                         sorted(f"lib{base}.so" for base in self.build.IMAGEFORMATS))
        self.assertIn("libqsvg.so", self._copiados())

    def test_si_falta_uno_la_construccion_se_para(self):
        (self.plugins / "imageformats" / "libqsvg.so").unlink()
        with self.assertRaises(SystemExit) as salida:
            self.build.copiar_plugins()
        self.assertIn("libqsvg.so", str(salida.exception))


class TestNiVncNiLibresolv(unittest.TestCase):
    """El AppImage llevaba `libresolv.so.2`, que es de glibc.

    Llegaba por `libqvnc.so`, el plugin de Qt para servir la ventana por VNC:
    es el único de `platforms` que pide QtNetwork, y QtNetwork arrastra
    Kerberos y `libresolv`. Silux no se usa por VNC, y una pieza de glibc
    dentro del paquete es lo mismo que llevarse `libc.so`: choca con la del
    sistema. Se vio con `ldd` sobre cada plugin de PySide6 6.12.
    """

    def setUp(self):
        import pathlib
        import tempfile
        from unittest import mock

        import tools.build_appimage as build
        self.build = build
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        raiz = pathlib.Path(tmp.name)
        self.plugins = raiz / "plugins"
        self.appdir = raiz / "silux.AppDir"
        for carpeta, nombres in (
                ("imageformats", tuple(f"lib{b}.so" for b in build.IMAGEFORMATS)),
                ("platforms", ("libqxcb.so", "libqwayland.so", "libqoffscreen.so",
                               "libqvnc.so"))):
            (self.plugins / carpeta).mkdir(parents=True)
            for nombre in nombres:
                (self.plugins / carpeta / nombre).write_bytes(b"\x7fELF")
        self.pedidas = []
        for nombre, valor in (("APPDIR", self.appdir),
                              ("plugins_de_qt", lambda: self.plugins),
                              ("dependencias",
                               lambda so, extra=None: self.pedidas.append(so.name) or []),
                              ("qt_propio", lambda: None)):
            parche = mock.patch.object(build, nombre, valor)
            parche.start()
            self.addCleanup(parche.stop)

    def test_el_plugin_de_vnc_no_entra(self):
        self.build.copiar_plugins()
        destino = self.appdir / "usr" / "lib" / "qt" / "plugins" / "platforms"
        self.assertEqual(sorted(p.name for p in destino.iterdir()),
                         ["libqoffscreen.so", "libqwayland.so", "libqxcb.so"])
        # Ni se le preguntan sus dependencias, que es por donde entraba lo demás.
        self.assertNotIn("libqvnc.so", self.pedidas)

    def test_libresolv_la_pone_el_sistema(self):
        self.assertTrue("libresolv.so.2".startswith(self.build.DEL_SISTEMA))


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

    def test_the_first_line_says_what_to_download_and_from_where(self):
        # Before anything else, in one line: which file and where.
        for language, words in (("es_ES.UTF-8", "descarga"), ("C", "download")):
            with self.subTest(language=language):
                first = self._lanzar(LANG=language).stderr.splitlines()[0]
                self.assertIn(words, first)
                self.assertIn("silux-x86_64-compat.AppImage", first)
                self.assertIn("https://github.com/rcv11x/silux/releases/latest", first)

    def test_recomienda_el_appimage_y_no_el_punto_de_montaje(self):
        hecho = self._lanzar(APPIMAGE="/home/ana/Descargas/silux-x86_64.AppImage")
        self.assertIn("/home/ana/Descargas/silux-x86_64.AppImage --report",
                      hecho.stderr)
        self.assertNotIn(str(self.apprun), hecho.stderr)

    def test_el_idioma_sigue_el_orden_de_posix(self):
        casos = (
            ({"LANG": "es_ES.UTF-8"}, "Este procesador necesita"),
            ({"LC_ALL": "es_ES.UTF-8"}, "Este procesador necesita"),
            ({"LC_MESSAGES": "es_MX.UTF-8", "LANG": "C"}, "Este procesador necesita"),
            ({"LC_ALL": "C", "LANG": "es_ES.UTF-8"}, "This processor needs"),
            ({}, "This processor needs"),
        )
        for entorno, espera in casos:
            with self.subTest(entorno=entorno):
                self.assertIn(espera, self._lanzar(**entorno).stderr)



class TestLosDatosEntranEnElPaquete(unittest.TestCase):
    """Lo que el programa lee de su propia carpeta va en lo que se instala.

    `pip install` solo copia los archivos que no son Python si
    `[tool.setuptools.package-data]` los nombra, carpeta a carpeta. Los de
    idioma están en `silux/db/lang/` y la regla solo nombraba `silux.db`: la
    rueda salía sin `es.json` ni `en.json`, y un silux instalado así enseña
    las claves —`cpu.card.clocks`— en vez de las frases. El AppImage no lo
    sufre porque copia la carpeta entera, y por eso no se vio.
    """

    RAIZ = __import__("pathlib").Path(__file__).resolve().parent.parent

    def _reglas(self) -> dict:
        texto = (self.RAIZ / "pyproject.toml").read_text(encoding="utf-8")
        bloque = re.search(r"^\[tool\.setuptools\.package-data\]\n(.*?)(?=^\[|\Z)",
                           texto, re.S | re.M).group(1)
        return {paquete: re.findall(r'"([^"]+)"', patrones)
                for paquete, patrones in re.findall(r'^"([^"]+)"\s*=\s*\[(.*?)\]',
                                                    bloque, re.S | re.M)}

    def test_cada_archivo_de_datos_tiene_su_regla(self):
        import fnmatch

        reglas = self._reglas()
        self.assertTrue(reglas)
        datos = [f for f in (self.RAIZ / "silux").rglob("*")
                 if f.is_file() and f.suffix not in (".py", ".pyc")
                 and "__pycache__" not in f.parts]
        self.assertTrue(datos)
        fuera = []
        for archivo in datos:
            paquete = ".".join(archivo.parent.relative_to(self.RAIZ).parts)
            if not any(fnmatch.fnmatch(archivo.name, patron)
                       for patron in reglas.get(paquete, ())):
                fuera.append(str(archivo.relative_to(self.RAIZ)))
        self.assertEqual(fuera, [], "no entrarían en el paquete instalado")


if __name__ == "__main__":
    unittest.main()


class TestLoQueUsaSiluxNoSeQuita(unittest.TestCase):
    """Un módulo de la biblioteca estándar que silux importa no puede estar en
    `DYNLOAD_FUERA`: el AppImage arrancaría y fallaría al usarlo, lejos de
    aquí. Le pasó a `_ssl`, fuera desde que el programa no salía a la red:
    con el actualizador, ninguna URL `https://` se podía abrir."""

    def test_ningun_import_de_silux_cae_en_lo_que_se_quita(self):
        import ast
        import pathlib

        import tools.build_appimage as build_appimage
        raiz = pathlib.Path(__file__).resolve().parent.parent
        importados = set()
        for archivo in (raiz / "silux").rglob("*.py"):
            for nodo in ast.walk(ast.parse(archivo.read_text(encoding="utf-8"))):
                if isinstance(nodo, ast.Import):
                    importados |= {a.name.split(".")[0] for a in nodo.names}
                elif isinstance(nodo, ast.ImportFrom) and nodo.module and not nodo.level:
                    importados.add(nodo.module.split(".")[0])
        # urllib.request solo abre https:// si puede importar ssl.
        if "urllib" in importados:
            importados.add("ssl")
        quitados = {m.lstrip("_") for m in build_appimage.DYNLOAD_FUERA}
        self.assertEqual(sorted(importados & quitados), [])
