"""La línea de órdenes: su ayuda y sus alias."""

import unittest


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
        anterior = i18n.actual()
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
        self.addCleanup(i18n.set_language, i18n.actual())
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


if __name__ == "__main__":
    unittest.main()
