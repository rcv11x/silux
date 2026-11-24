"""What Silux launches does not inherit what the AppImage adds.

In a Debian 13 with the compat AppImage, `systemctl` loaded the AppImage's
`libcrypto` and died («version `OPENSSL_3.4.0' not found»): the boot times
of two testers' reports were missing. The environment is the one the real
AppRun produces, run by `sh` from the packager's own template.
"""

import ast
import os
import pathlib
import subprocess
import tempfile
import unittest
from unittest import mock

from silux import system_env

ROOT = pathlib.Path(__file__).resolve().parent.parent

# Silux's own children run the AppImage's Python and need its environment.
OWN_PYTHON = {"silux/gpuapi.py", "silux/membench.py", "silux/memtest.py", "silux/annex.py"}
# The helper runs as root under pkexec, which cleans the environment, and
# gives modprobe a fixed one of its own (`MODPROBE_ENV`).
OWN_ENVIRONMENT = {"silux/privileged/helper.py"}
LAUNCHERS = {"run", "Popen", "call", "check_call", "check_output"}


def apprun_environment(user_library_path: str) -> tuple[str, dict[str, str]]:
    """The environment the AppRun's exports leave, and the AppDir they used."""
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "build_appimage", ROOT / "tools" / "build_appimage.py")
    builder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(builder)
    exports = builder.APPRUN.split("ARRANQUE=")[0]
    appdir = pathlib.Path(tempfile.mkdtemp(prefix=".mount_silux"))
    (appdir / "AppRun").write_text(exports + '\nenv -0\n')
    salida = subprocess.run(
        ["sh", str(appdir / "AppRun")], capture_output=True, check=True,
        env={"PATH": os.environ.get("PATH", "/usr/bin:/bin"),
             "LD_LIBRARY_PATH": user_library_path})
    pares = (linea.split("=", 1) for linea in salida.stdout.decode().split("\0") if "=" in linea)
    return str(appdir.resolve()), dict(pares)


class TestTheEnvironment(unittest.TestCase):

    def setUp(self):
        self.appdir, self.env = apprun_environment("/opt/mine/lib")
        self.addCleanup(lambda: __import__("shutil").rmtree(self.appdir, ignore_errors=True))

    def test_the_apprun_does_add_its_paths(self):
        self.assertTrue(self.env["LD_LIBRARY_PATH"].startswith(self.appdir))
        self.assertIn("PYTHONHOME", self.env)

    def test_a_system_program_gets_none_of_them(self):
        limpio = system_env.system_environment(self.env)
        self.assertEqual(limpio["LD_LIBRARY_PATH"], "/opt/mine/lib")
        for nombre in ("PYTHONHOME", "PYTHONPATH", "QT_PLUGIN_PATH",
                       "QT_QPA_PLATFORM_PLUGIN_PATH"):
            with self.subTest(variable=nombre):
                self.assertNotIn(nombre, limpio)
        self.assertEqual(limpio["PATH"], self.env["PATH"])

    def test_without_a_path_of_its_own_the_variable_goes(self):
        appdir, env = apprun_environment("")
        self.addCleanup(lambda: __import__("shutil").rmtree(appdir, ignore_errors=True))
        self.assertNotIn("LD_LIBRARY_PATH", system_env.system_environment(env))

    def test_outside_an_appimage_nothing_changes(self):
        env = {"LD_LIBRARY_PATH": "/opt/mine/lib", "PATH": "/usr/bin"}
        self.assertEqual(system_env.system_environment(env), env)


class TestSystemd(unittest.TestCase):

    def test_systemctl_runs_without_the_appimage(self):
        from silux.providers import system

        appdir, env = apprun_environment("")
        self.addCleanup(lambda: __import__("shutil").rmtree(appdir, ignore_errors=True))
        with mock.patch.dict(os.environ, env, clear=True), \
                mock.patch.object(system.subprocess, "run") as run:
            run.return_value = subprocess.CompletedProcess([], 0, "", "")
            system._systemd_times()
        usado = run.call_args.kwargs["env"]
        self.assertNotIn("LD_LIBRARY_PATH", usado)
        self.assertEqual(usado["LC_ALL"], "C")


class TestEveryLaunch(unittest.TestCase):
    """A launch that forgets it brings the problem back with no test failing."""

    @staticmethod
    def _launches():
        for ruta in sorted((ROOT / "silux").rglob("*.py")):
            relativa = str(ruta.relative_to(ROOT))
            for nodo in ast.walk(ast.parse(ruta.read_text(encoding="utf-8"))):
                if not isinstance(nodo, ast.Call) or not isinstance(nodo.func, ast.Attribute):
                    continue
                nombre = nodo.func.attr
                dueno = getattr(nodo.func.value, "id", None)
                if ((dueno == "subprocess" and nombre in LAUNCHERS)
                        or (dueno == "os" and nombre.startswith(("exec", "spawn", "system")))
                        or nombre == "openUrl"):
                    yield relativa, nodo.lineno, nombre, nodo

    def test_there_are_launches_to_look_at(self):
        self.assertGreater(len(list(self._launches())), 10)

    def test_each_one_gets_the_system_environment(self):
        sueltos = []
        for ruta, linea, nombre, nodo in self._launches():
            if ruta in OWN_PYTHON | OWN_ENVIRONMENT or ruta == "silux/system_env.py":
                continue
            entorno = next((k.value for k in nodo.keywords if k.arg == "env"), None)
            if nombre.startswith("exec"):
                # os.execve's third argument.
                entorno = nodo.args[2] if nombre == "execve" and len(nodo.args) > 2 else None
            texto = ast.unparse(entorno) if entorno is not None else ""
            if "system_environment(" not in texto:
                sueltos.append(f"{ruta}:{linea} {nombre}")
        self.assertEqual(sueltos, [])


if __name__ == "__main__":
    unittest.main()
