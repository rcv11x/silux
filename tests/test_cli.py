"""La línea de órdenes: su ayuda y sus alias."""

import pathlib
import tempfile
import unittest

from silux.i18n import _


class TestLaAyuda(unittest.TestCase):
    """`--help` en el idioma de la interfaz, opciones en inglés y alias en
    español que funcionan sin salir en la ayuda.

    Salía mitad en inglés («usage:», «options:», «show this help message and
    exit») y mitad en español, y las opciones de la ventana eran una mezcla
    (`--anonimo` al lado de `--screenshot`).
    """

    def _ayuda(self, idioma: str, construir) -> str:
        import contextlib
        import io
        from silux import i18n
        anterior = i18n.current()
        self.addCleanup(i18n.set_language, anterior)
        i18n.set_language(idioma)
        salida = io.StringIO()
        with contextlib.redirect_stdout(salida), self.assertRaises(SystemExit):
            construir().parse_args(["--help"])
        return salida.getvalue()

    def test_en_espanol_no_queda_nada_de_argparse_en_ingles(self):
        from silux import cli
        texto = self._ayuda("es", cli.build_parser)
        for ingles in ("usage:", "options:", "show this help", "show program"):
            self.assertNotIn(ingles, texto)
        self.assertIn("uso:", texto)
        self.assertIn("--report", texto)

    def test_en_ingles_tampoco_queda_espanol(self):
        from silux import cli
        texto = self._ayuda("en", cli.build_parser)
        self.assertIn("usage:", texto)
        for espanol in ("informe", "sensores", "opciones", "enseña"):
            self.assertNotIn(espanol, texto)

    def test_los_alias_en_espanol_funcionan_y_no_salen(self):
        from silux import cli
        parser = cli.build_parser()
        for espanol, campo, valor in (("--informe", "report", "x.md"),
                                      ("--sensores", "sensors", True),
                                      ("--sin-color", "no_color", True),
                                      ("--con-identificadores", "with_identifiers", True)):
            with self.subTest(alias=espanol):
                argumentos = [espanol, valor] if isinstance(valor, str) else [espanol]
                self.assertEqual(getattr(parser.parse_args(argumentos), campo), valor)
        texto = self._ayuda("es", cli.build_parser)
        self.assertNotIn("--informe", texto)
        self.assertNotIn("--sensores", texto)


class TestLaAyudaDeLaVentana(unittest.TestCase):
    """La de la ventana, que es la que sale con `--help` en el AppImage:
    cuenta cómo usar la terminal y el informe, con el nombre del archivo."""

    def test_desde_el_appimage_explica_la_terminal_y_el_informe(self):
        import os
        from unittest import mock
        from silux import i18n, options
        self.addCleanup(i18n.set_language, i18n.current())
        i18n.set_language("es")
        with mock.patch.dict(os.environ, {"APPIMAGE": "/home/x/silux-x86_64.AppImage"}):
            texto = options.epilog_for_terminal()
        self.assertIn("./silux-x86_64.AppImage --report informe.md", texto)
        self.assertIn("./silux-x86_64.AppImage --cli --help", texto)
        self.assertIn("issues", texto)

    def test_opciones_en_ingles_y_sus_alias(self):
        try:
            from silux.ui import app
        except ImportError:                              # pragma: no cover
            self.skipTest("sin PySide6")
        parser = app.build_parser()
        ingles = parser.parse_args(["--anonymous", "--font-scale", "large", "--page", "CPU"])
        espanol = parser.parse_args(["--anonimo", "--letra", "grande", "--pagina", "CPU"])
        self.assertTrue(ingles.anonymous and espanol.anonymous)
        self.assertEqual(app.TAMANOS_DE_LETRA[ingles.font_scale], "grande")
        self.assertEqual(espanol.font_scale, "grande")
        self.assertEqual(ingles.page, espanol.page)


class TestElInformePidePermisosAlEmpezar(unittest.TestCase):
    """`--report` pide los permisos antes de leer: lo que solo ve el
    administrador (la memoria, la salud de los discos) es a menudo lo que
    hace falta para entender un fallo."""

    def _lanzar(self, *argumentos):
        import contextlib
        import io
        import tempfile
        from unittest import mock
        from silux import cli
        recolector = mock.MagicMock()
        with tempfile.TemporaryDirectory() as carpeta, \
             mock.patch.object(cli, "Collector", return_value=recolector), \
             mock.patch.object(cli.report, "build", return_value="informe\n"), \
             mock.patch.object(cli, "qt_can_start", return_value=False), \
             mock.patch("silux.privileged.client.already_root", return_value=False), \
             contextlib.redirect_stdout(io.StringIO()), \
             contextlib.redirect_stderr(io.StringIO()):
            cli.main(["--report", f"{carpeta}/informe.md", *argumentos])
        return recolector

    def test_los_pide(self):
        self._lanzar().request_elevation.assert_called_once()

    def test_no_los_pide_si_se_dice(self):
        self._lanzar("--without-permissions").request_elevation.assert_not_called()
        self._lanzar("--sin-permisos").request_elevation.assert_not_called()
        self._lanzar("--short").request_elevation.assert_not_called()


class TestVigilarLosSensores(unittest.TestCase):
    """`--sensors --watch` repite el árbol de sensores, no el volcado entero:
    es el ejemplo que da la ayuda («los sensores, cada segundo»)."""

    class _Basta(Exception):
        """Corta el bucle tras una vuelta. No `KeyboardInterrupt`: pytest
        lo toma como que se ha interrumpido la suite entera."""

    def _una_vuelta(self, *argumentos):
        import contextlib
        import io
        import types
        from unittest import mock
        from silux import cli
        salida = io.StringIO()
        # Only the `time` cli sees. `cli.time` is the time module itself, and
        # patching its `sleep` stopped whoever else slept first: the
        # `Popen.wait` of the `git log` behind `build_id()`, which waits with
        # sleeps when git has closed its pipes but cannot be reaped yet. The
        # output came back empty (1 run in 100, CI run 44753317786).
        reloj = types.SimpleNamespace(sleep=mock.Mock(side_effect=self._Basta))
        with mock.patch.object(cli, "time", reloj), \
             contextlib.redirect_stdout(salida), self.assertRaises(self._Basta):
            cli.main([*argumentos, "--watch", "1", "--no-color"])
        reloj.sleep.assert_called_once_with(1.0)
        return salida.getvalue()

    def test_con_sensors_solo_los_sensores(self):
        from silux import cli
        from silux.collector import Collector
        texto = self._una_vuelta("--sensors")
        foto = Collector().snapshot()
        volcado = cli.dump(foto, cli.Style(enabled=False))
        primera_del_volcado = volcado.strip().splitlines()[0]
        self.assertNotIn(primera_del_volcado, texto)
        # And what it does print: with nothing printed, the line above held.
        arbol = cli.sensors_text(foto, cli.Style(enabled=False))
        self.assertIn(arbol.strip().splitlines()[0], texto)

    def test_sin_sensors_el_volcado(self):
        from silux import cli
        from silux.collector import Collector
        texto = self._una_vuelta()
        foto = Collector().snapshot()
        primera = cli.dump(foto, cli.Style(enabled=False)).strip().splitlines()[0]
        self.assertIn(primera, texto)


class TestElArbolDeSensoresEnLaTerminal(unittest.TestCase):
    """`--sensors` decía «cat.temperature» y «Núcleo {n}» en la gráfica."""

    def test_sin_claves_ni_huecos_sin_rellenar(self):
        from silux import cli
        from silux.collector import Collector
        from tests.test_equipos import EQUIPOS, foto
        for f in (foto(EQUIPOS / "5800x3d")[0], Collector().snapshot()):
            texto = cli.sensors_text(f, cli.Style(enabled=False))
            self.assertNotIn("cat.", texto)
            self.assertNotIn("{", texto)

    def test_the_plain_dump_neither(self):
        """The plain dump's Sensors said «cat.temperature» too (Felix's
        prueba13 5800X), and «Micro-Star International Co., Ltd. [MSI]» for
        who built the card."""
        from silux import cli
        from tests.test_equipos import EQUIPOS, shared_snapshot
        texto = cli.dump(shared_snapshot(EQUIPOS / "ryzen7-5800x"), cli.Style(enabled=False))
        self.assertNotIn("cat.", texto)
        self.assertNotIn("Co., Ltd.", texto)
        self.assertIn("MSI", texto)


if __name__ == "__main__":
    unittest.main()


class TestReportArguments(unittest.TestCase):
    """Mistakes in the report options are said, not silently ignored: an
    unknown section was dropped and `--report ''` printed the plain dump."""

    def run_cli(self, *args):
        import contextlib
        import io
        from silux import cli
        out, err = io.StringIO(), io.StringIO()
        code = 0
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            try:
                code = cli.main(list(args))
            except SystemExit as exit_:
                code = exit_.code
        return code, out.getvalue(), err.getvalue()

    def test_an_empty_report_name_is_an_error(self):
        code, out, err = self.run_cli("--report", "", "--without-permissions")
        self.assertEqual(code, 2)
        self.assertEqual(out, "")
        self.assertIn("«-»", err)

    def test_an_unknown_section_is_an_error_that_lists_the_real_ones(self):
        code, out, err = self.run_cli("--report", "-", "--without-permissions",
                                      "--sections", "cpu,made-up")
        self.assertEqual(code, 2)
        self.assertEqual(out, "")
        self.assertIn("made-up", err)
        self.assertIn("memory", err)

    def test_known_sections_still_work(self):
        code, out, _err = self.run_cli("--report", "-", "--without-permissions",
                                       "--sections", "cpu,Placa base")
        self.assertEqual(code, 0)
        self.assertIn("## CPU", out)
        # A chosen part of the report is not for reproducing the machine.
        self.assertNotIn("silux-annex", out)

    def test_the_full_report_ends_with_this_machines_raw_data(self):
        from silux import annex
        from silux.collector import Collector
        code, out, _err = self.run_cli("--report", "-", "--without-permissions")
        self.assertEqual(code, 0)
        last = out.rsplit("\n## ", 1)[-1]
        self.assertTrue(last.startswith(_("report.annex.title")), last[:80])
        with tempfile.TemporaryDirectory() as tmp:
            annex.to_folder(annex.find(out), pathlib.Path(tmp) / "back")
            from silux import volcado
            photo = volcado.snapshot_of(pathlib.Path(tmp) / "back")
        self.assertEqual([t.brand for t in photo.cpu.types],
                         [t.brand for t in Collector().snapshot().cpu.types])

    def test_the_short_one_does_not(self):
        code, out, _err = self.run_cli("--report", "-", "--short", "--without-permissions")
        self.assertEqual(code, 0)
        self.assertNotIn("silux-annex", out)


class TestTheReportWithoutGraphicsLibraries(unittest.TestCase):
    """On a system without libGL (a server, a minimal container) the full
    report, built from the window's pages, died with a traceback. It writes
    the short one and says why."""

    def test_the_short_one_and_why(self):
        import contextlib
        import io
        import sys
        import tempfile
        from unittest import mock

        from silux import cli
        from silux.i18n import _

        errors = io.StringIO()
        with tempfile.TemporaryDirectory() as folder, \
             mock.patch.object(cli, "Collector", return_value=mock.MagicMock()), \
             mock.patch.object(cli.report, "build", return_value="informe corto\n"), \
             mock.patch.object(cli, "qt_can_start", return_value=True), \
             mock.patch.dict(sys.modules, {"PySide6.QtWidgets": None}), \
             contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(errors):
            cli.main(["--report", f"{folder}/informe.md", "--without-permissions"])
            written = open(f"{folder}/informe.md", encoding="utf-8").read()
        self.assertEqual(written, "informe corto\n")
        self.assertIn(_("cli.report.nolibs").split("(")[0], errors.getvalue())
