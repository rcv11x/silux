"""`sysroot.path` gives back what it gets: text for text, a Path for a Path.

A tester's Gentoo with OpenRC read «?» in Distribución, Kernel and the rest
of the system's identity: `sysroot.path("/run/openrc").is_dir()` called a
Path's method on text, the provider failed whole, and only on a machine
whose PID 1 is `init`. Its test had replaced `ruta` with one that always
gives a Path. Here every call to a Path method on `sysroot.path(...)` is
checked against what its argument really is.
"""

import ast
import pathlib
import unittest

RAIZ = pathlib.Path(__file__).resolve().parent.parent
METODOS_DE_PATH = {"is_dir", "is_file", "exists", "read_text", "read_bytes", "iterdir",
                   "glob", "rglob", "open", "stat", "resolve", "is_symlink", "readlink",
                   "parent", "name", "joinpath", "with_name", "relative_to"}


def _es_path(nodo, constantes: dict) -> bool | None:
    """Whether an expression is a Path (True), text (False), or unknown."""
    if isinstance(nodo, ast.Constant):
        return False if isinstance(nodo.value, str) else None
    if isinstance(nodo, ast.JoinedStr):
        return False
    if isinstance(nodo, ast.Call):
        nombre = ast.unparse(nodo.func)
        if nombre in ("pathlib.Path", "Path", "pathlib.PurePosixPath"):
            return True
        if nombre in ("str", "os.path.join", "os.fspath"):
            return False
        return None
    if isinstance(nodo, ast.BinOp) and isinstance(nodo.op, ast.Div):
        return True if _es_path(nodo.left, constantes) else None
    if isinstance(nodo, ast.Name):
        return constantes.get(nodo.id)
    return None


class TestPathMethodsOnRutaHaveAPath(unittest.TestCase):

    def test_everywhere_in_silux(self):
        malos = []
        for archivo in sorted((RAIZ / "silux").rglob("*.py")):
            arbol = ast.parse(archivo.read_text(encoding="utf-8"))
            constantes: dict[str, bool | None] = {}
            for nodo in arbol.body:
                if isinstance(nodo, ast.Assign) and len(nodo.targets) == 1 \
                        and isinstance(nodo.targets[0], ast.Name):
                    constantes[nodo.targets[0].id] = _es_path(nodo.value, constantes)
            for nodo in ast.walk(arbol):
                if not (isinstance(nodo, ast.Attribute) and nodo.attr in METODOS_DE_PATH
                        and isinstance(nodo.value, ast.Call)
                        and ast.unparse(nodo.value.func) == "sysroot.path"
                        and nodo.value.args):
                    continue
                if _es_path(nodo.value.args[0], constantes) is not True:
                    malos.append(f"{archivo.relative_to(RAIZ)}:{nodo.lineno} "
                                 f"{ast.unparse(nodo)}")
        self.assertEqual(malos, [])


if __name__ == "__main__":
    unittest.main()
