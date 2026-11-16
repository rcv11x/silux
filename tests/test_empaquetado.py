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


if __name__ == "__main__":
    unittest.main()
