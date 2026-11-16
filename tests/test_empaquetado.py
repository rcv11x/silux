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


if __name__ == "__main__":
    unittest.main()
