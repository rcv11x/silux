"""Lanzar el ayudante desde dentro de un AppImage.

Un probador con Hyprland no conseguía elevar permisos: el botón devolvía
«Autorización cancelada o denegada» sin llegar a pedirle la contraseña. No era
su agente de polkit. Era que ejecutaba el AppImage, y desde ahí el ayudante no
se puede lanzar por dos motivos:

* El punto de montaje va con `nosuid`, y pkexec se niega a ejecutar nada de un
  sistema de archivos así. Deniega antes de preguntar, que es exactamente lo
  que se veía.
* El montaje es de FUSE y pertenece al usuario, así que root ni siquiera puede
  leer dentro. Aunque pkexec arrancara, no encontraría el ayudante.

Se prueba con el entorno simulado porque montar un AppImage de verdad dentro de
los tests exige FUSE, y la máquina que los ejecute no tiene por qué tenerlo.
"""

import os
import pathlib
import tempfile
import unittest
from unittest import mock

from silux.privileged import client as mod
from silux.privileged.client import HelperUnavailable, PrivilegedClient


class TestDeteccion(unittest.TestCase):
    def test_fuera_de_un_appimage(self):
        with mock.patch.dict(os.environ, {}, clear=True), \
             mock.patch.object(mod.sys, "executable", "/usr/bin/python3"):
            self.assertFalse(PrivilegedClient().empaquetado())

    def test_por_la_variable_del_runtime(self):
        # El runtime de AppImage la exporta siempre.
        with mock.patch.dict(os.environ, {"APPIMAGE": "/home/x/silux.AppImage"}):
            self.assertTrue(PrivilegedClient().empaquetado())

    def test_por_la_ruta_del_interprete(self):
        # Por si alguien lo lanza de una forma que no exporte la variable.
        with mock.patch.dict(os.environ, {}, clear=True), \
             mock.patch.object(mod.sys, "executable",
                               "/tmp/.mount_siluxAbC/usr/bin/python3"):
            self.assertTrue(PrivilegedClient().empaquetado())


class TestPreparacion(unittest.TestCase):
    """Cómo se lanza el ayudante desde el AppImage ahora que no hay copia.

    Antes se dejaba una en `~/.cache/silux/helper.py` y se le pasaba esa ruta a
    pkexec. Esa carpeta la escribe el usuario, así que cualquier proceso suyo
    podía cambiar el archivo entre que silux lo escribía y que root lo abría, y
    quedarse con ejecución como root. Ahora el ayudante viaja entero por `argv`
    y no existe como archivo en ningún momento.
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.cache = pathlib.Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def _orden(self, empaquetado=True):
        with mock.patch.object(PrivilegedClient, "empaquetado",
                               staticmethod(lambda: empaquetado)), \
             mock.patch.object(PrivilegedClient, "instalado",
                               staticmethod(lambda: False)), \
             mock.patch.object(mod, "_cache_dir", lambda: self.cache):
            return PrivilegedClient()._orden()

    def test_no_se_copia_nada_a_ninguna_parte(self):
        for empaquetado in (True, False):
            with self.subTest(empaquetado=empaquetado):
                self._orden(empaquetado)
                self.assertEqual(list(self.cache.rglob("*")), [])

    def test_con_appimage_se_usa_el_python_del_sistema(self):
        with mock.patch.object(mod, "SYSTEM_PYTHON", ("/usr/bin/python3",)):
            orden = self._orden()
        self.assertEqual(orden[1], "/usr/bin/python3")

    def test_el_ayudante_sale_del_montaje_sin_pasar_por_el_disco(self):
        orden = self._orden()
        # Ninguna ruta del montaje, que es lo que root no puede leer.
        for pieza in orden:
            if pieza.startswith("/"):
                self.assertNotIn("/.mount_", pieza)
        # Y va entero, no recortado: el ayudante se lee y se manda tal cual.
        self.assertIn(mod.HELPER.read_text(encoding="utf-8"), orden)

    def test_una_actualizacion_no_deja_un_ayudante_viejo_detras(self):
        """Antes la copia se reescribía en cada conexión por esto mismo: una
        del AppImage anterior hablaría otro protocolo. Ahora se lee la fuente
        en el momento de lanzar, así que no hay nada que pueda quedarse atrás,
        pero sigue habiendo que comprobar que se lee y no se cachea."""
        falso = self.cache / "helper.py"
        falso.write_text("# el de antes\n", encoding="utf-8")
        with mock.patch.object(mod, "HELPER", falso):
            self.assertIn("# el de antes\n", self._orden())
            falso.write_text("# el de ahora\n", encoding="utf-8")
            self.assertIn("# el de ahora\n", self._orden())

    def test_sin_python_del_sistema_se_explica(self):
        with mock.patch.object(PrivilegedClient, "empaquetado", staticmethod(lambda: True)), \
             mock.patch.object(mod, "SYSTEM_PYTHON", ("/no/existe",)):
            with self.assertRaises(HelperUnavailable) as caso:
                mod.interprete()
        self.assertIn("Python del sistema", str(caso.exception))


if __name__ == "__main__":
    unittest.main()


class TestPuntoDeEntrada(unittest.TestCase):
    """Qué arranca el AppImage según con qué se le llame.

    Sin esto solo levantaba la interfaz, y `--report` es lo primero que se le
    pide a quien dice que algo no le sale: quien usa el AppImage no tenía
    ninguna forma de sacarlo.
    """

    def _apprun(self) -> str:
        import tools.build_appimage as build
        return build.APPRUN

    def test_por_omision_abre_la_interfaz(self):
        apprun = self._apprun()
        self.assertIn("silux.ui.app", apprun)
        # la última línea, la que se ejecuta si no casó ningún caso
        self.assertTrue(apprun.strip().splitlines()[-1].endswith('silux.ui.app "$@"'))

    def test_las_banderas_del_terminal_van_al_cli(self):
        apprun = self._apprun()
        for bandera in ("--report", "--json", "--sensors", "--cli"):
            self.assertIn(bandera, apprun, f"{bandera} no llega al CLI")
        self.assertIn("silux.cli", apprun)

    def test_no_se_deja_ninguna_bandera_del_cli(self):
        """Si el CLI gana una opción nueva, aquí hay que añadirla."""
        from silux import cli
        apprun = self._apprun()
        parser = cli.build_parser()
        propias = {a for accion in parser._actions for a in accion.option_strings
                   if a.startswith("--") and a not in ("--help", "--version")}
        # En el `case` van separadas por barras, no por espacios.
        faltan = {b for b in propias if b not in apprun}
        self.assertFalse(faltan, f"el AppRun no reparte: {sorted(faltan)}")


class TestQueSeMiraAlComprobar(unittest.TestCase):
    """A qué objetos del AppDir se les pregunta qué exigen.

    El comprobador decía «exige glibc 2.34» de un paquete que exigía 2.35, y
    esa equivocación solo cae hacia un lado: manda a alguien con RHEL 9 a
    descargar algo que no le arranca. El motivo era que miraba nada más
    `usr/lib/*.so*`, y encima las sesenta primeras, mientras que el intérprete
    cuelga de `usr/bin` y los módulos de extensión de la biblioteca estándar
    viven en `lib-dynload`. Justo `python3` era quien pedía el símbolo más
    alto, `hypot@GLIBC_2.35`.

    Es el mismo agujero por el que `_hashlib` se quedó sin `libcrypto`: dar por
    hecho que lo que hay que mirar está todo en un directorio.
    """

    def _appdir_de_mentira(self, raiz: pathlib.Path) -> None:
        (raiz / "usr" / "lib").mkdir(parents=True)
        (raiz / "usr" / "bin").mkdir(parents=True)
        (raiz / "usr" / "lib" / "python3.10" / "lib-dynload").mkdir(parents=True)
        (raiz / "usr" / "lib" / "libcualquiera.so.1").write_bytes(b"\x7fELF")
        interprete = raiz / "usr" / "bin" / "python3"
        interprete.write_bytes(b"\x7fELF")
        interprete.chmod(0o755)
        (raiz / "usr" / "lib" / "python3.10" / "lib-dynload"
         / "_bz2.cpython-310-x86_64-linux-gnu.so").write_bytes(b"\x7fELF")

    def test_se_miran_las_tres_familias(self):
        import tools.build_appimage as build

        with tempfile.TemporaryDirectory() as tmp:
            raiz = pathlib.Path(tmp) / "silux.AppDir"
            self._appdir_de_mentira(raiz)
            anterior = build.APPDIR
            try:
                build.APPDIR = raiz
                nombres = {p.name for p in build.objetos_del_appdir()}
            finally:
                build.APPDIR = anterior

        self.assertIn("libcualquiera.so.1", nombres, "no mira usr/lib")
        self.assertIn("python3", nombres,
                      "no mira el intérprete, que es quien pide más glibc")
        self.assertIn("_bz2.cpython-310-x86_64-linux-gnu.so", nombres,
                      "no mira lib-dynload, donde vive _bz2")

    def test_no_se_recorta_la_lista(self):
        """Un tope deja fuera justo al que más pide, y nadie se entera."""
        import tools.build_appimage as build

        with tempfile.TemporaryDirectory() as tmp:
            raiz = pathlib.Path(tmp) / "silux.AppDir"
            (raiz / "usr" / "lib").mkdir(parents=True)
            for numero in range(120):
                (raiz / "usr" / "lib" / f"lib{numero:03}.so.1").write_bytes(b"\x7fELF")
            anterior = build.APPDIR
            try:
                build.APPDIR = raiz
                cuantos = len(build.objetos_del_appdir())
            finally:
                build.APPDIR = anterior

        self.assertEqual(cuantos, 120, "el comprobador se deja objetos sin mirar")

    def test_las_dos_comprobaciones_recorren_lo_mismo(self):
        """Que no vuelvan a divergir: una lista, y las dos la usan.

        Cuando cada una recorría lo suyo, la del juego de instrucciones miraba
        el AppDir entero y la de glibc un solo directorio, y la diferencia no
        se veía hasta que alguien comparaba los dos avisos a mano.
        """
        import inspect

        import tools.build_appimage as build

        for funcion in (build._glibc_minima,
                        build.comprobar_juego_de_instrucciones):
            fuente = inspect.getsource(funcion)
            with self.subTest(funcion=funcion.__name__):
                self.assertIn("objetos_del_appdir()", fuente,
                              "recorre el AppDir por su cuenta en vez de "
                              "compartir la lista")


class TestElRegistroDeLaConstruccion(unittest.TestCase):
    """Que el registro cuente lo que pasó.

    Salía diciendo «las dos cosas» hubiera avisado de una o de dos, y
    recomendaba construir en un contenedor a quien acababa de construir en un
    contenedor. Y los pasos aparecían después de empaquetar, que ocurre al
    revés, porque dentro del contenedor la stdout de Python no es un terminal
    y se volcaba entera al final.
    """

    def _avisar(self, nivel=None, glibc=None, dentro=False):
        import io
        import os
        from contextlib import redirect_stdout

        import tools.build_appimage as build

        entorno = {build.EN_CONTENEDOR: "1"} if dentro else {}
        salida = io.StringIO()
        with mock.patch.dict(os.environ, entorno, clear=False), \
             mock.patch.object(build, "_nivel_isa", lambda: nivel), \
             mock.patch.object(build, "_glibc_minima", lambda: glibc), \
             redirect_stdout(salida):
            if not dentro:
                os.environ.pop(build.EN_CONTENEDOR, None)
            build.avisar_de_compatibilidad()
        return salida.getvalue()

    def test_con_un_aviso_no_dice_dos(self):
        texto = self._avisar(glibc="2.39")
        self.assertIn("Se resuelve construyendo", texto)
        self.assertNotIn("Las dos", texto)

    def test_con_dos_avisos_si(self):
        texto = self._avisar(nivel="x86-64-v3", glibc="2.39")
        self.assertIn("Las dos se resuelven", texto)

    def test_dentro_del_contenedor_el_glibc_no_es_un_aviso(self):
        """Ese suelo es el resultado que se buscaba, no un problema; y el
        consejo sería el que se acaba de seguir."""
        texto = self._avisar(glibc="2.35", dentro=True)
        self.assertIn("2.35", texto)
        self.assertNotIn("⚠", texto)
        self.assertNotIn("construyendo en un contenedor", texto)

    def test_dentro_del_contenedor_una_isa_alta_sigue_siendo_un_aviso(self):
        """Eso sí sorprende ahí dentro, y no lo arregla la imagen."""
        texto = self._avisar(nivel="x86-64-v3", glibc="2.35", dentro=True)
        self.assertIn("⚠", texto)
        self.assertIn("no lo", texto)
        self.assertNotIn("Se resuelve construyendo", texto)

    def test_sin_nada_que_decir_no_dice_nada(self):
        self.assertEqual(self._avisar(), "")

    def test_la_orden_del_contenedor_pide_salida_sin_buffer(self):
        """Es lo que pone los pasos en su orden. Sin esto el registro no sirve
        para saber en qué paso falló una construcción."""
        import tools.build_appimage as build

        with mock.patch.object(build.shutil, "which", lambda _: "/usr/bin/podman"), \
             mock.patch.object(build.subprocess, "run") as corrida:
            corrida.return_value = mock.Mock(returncode=0)
            build.construir_en_contenedor(build.IMAGEN_BASE)

        orden = corrida.call_args[0][0]
        self.assertIn("PYTHONUNBUFFERED=1", orden)
        self.assertIn(f"{build.EN_CONTENEDOR}=1", orden,
                      "la construcción de dentro no sabría que está dentro")
