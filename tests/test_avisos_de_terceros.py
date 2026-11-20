"""Los avisos que piden las licencias de lo que Silux lleva de otros.

`silux/db/cpu_ids.json` sale de las tablas de libcpuid (BSD-2) y de la de
encapsulados de CPU-X (GPL-3.0 o posterior). BSD-2 pide conservar su
copyright, sus dos condiciones y su renuncia de garantía con el código, y
reproducirlos en lo que acompaña al binario. Solo se los nombraba en
Ajustes, `--db-info` y el generador; el AppImage no llevaba ni el `LICENSE`
de Silux.
"""

import os
import pathlib
import re
import tempfile
import unittest
from unittest import mock

from silux import db
from tests import qt

try:
    from PySide6.QtWidgets import QApplication, QLabel
except ImportError:                                    # pragma: no cover
    QApplication = None

RAIZ = pathlib.Path(__file__).resolve().parent.parent
AVISOS = RAIZ / "silux" / "db" / "THIRD_PARTY_NOTICES.md"


def _avisos() -> str:
    return AVISOS.read_text(encoding="utf-8")


class TestElArchivo(unittest.TestCase):

    def test_cada_fuente_de_la_tabla_tiene_su_aviso(self):
        """Se compara con lo que la tabla dice que lleva, no con una lista
        aparte: una fuente nueva sin su aviso no pasa."""
        fuentes = db.load()["sources"]
        self.assertTrue(fuentes)
        texto = _avisos()
        for nombre, datos in fuentes.items():
            with self.subTest(fuente=nombre):
                self.assertRegex(texto, rf"(?im)^## {re.escape(nombre)}\s*$")
                self.assertIn(datos["repo"].removesuffix(".git"), texto)

    def test_the_disk_table_too(self):
        """smart_units.json, from smartmontools' drivedb.h (GPL-2.0-or-later)."""
        import json

        tabla = json.loads((RAIZ / "silux" / "db" / "smart_units.json").read_text(encoding="utf-8"))
        texto = _avisos()
        for nombre, datos in tabla["sources"].items():
            with self.subTest(fuente=nombre):
                self.assertRegex(texto, rf"(?im)^## {re.escape(nombre)}\s*$")
                self.assertIn(datos["repo"], texto)
        self.assertIn("SPDX-License-Identifier: GPL-2.0-or-later", texto)

    def test_libcpuid_con_el_aviso_entero(self):
        texto = _avisos()
        for trozo in ("Copyright 2008  Veselin Georgiev",
                      "1. Redistributions of source code must retain the above copyright",
                      "2. Redistributions in binary form must reproduce the above copyright",
                      "THIS SOFTWARE IS PROVIDED BY THE AUTHOR ``AS IS''",
                      "EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE."):
            with self.subTest(trozo=trozo[:40]):
                self.assertIn(trozo, texto)

    def test_cpux_con_su_copyright(self):
        texto = _avisos()
        self.assertIn("Copyright © 2014-2025 The Tumultuous Unicorn Of Darkness", texto)
        self.assertIn("either version 3 of the License, or", texto)


class TestVaConElPrograma(unittest.TestCase):

    def test_en_el_paquete_de_pip(self):
        texto = (RAIZ / "pyproject.toml").read_text(encoding="utf-8")
        archivos = re.search(r"^license-files\s*=\s*\[(.*?)\]", texto, re.M | re.S)
        self.assertIsNotNone(archivos)
        self.assertIn('"silux/db/THIRD_PARTY_NOTICES.md"', archivos.group(1))
        self.assertIn('"LICENSE"', archivos.group(1))

    def test_dentro_del_appimage(self):
        import tools.build_appimage as build
        with tempfile.TemporaryDirectory() as tmp, \
             mock.patch.object(build, "APPDIR", pathlib.Path(tmp) / "silux.AppDir"):
            build.copiar_silux()
            doc = build.APPDIR / "usr" / "share" / "doc" / "silux"
            self.assertEqual((doc / "LICENSE").read_bytes(), (RAIZ / "LICENSE").read_bytes())
            self.assertEqual((doc / "THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8"),
                             _avisos())
            # Y junto a la tabla, que es lo que lee «Acerca de».
            self.assertTrue((build.APPDIR / "usr" / "lib" / "python" / "silux" / "db"
                             / "THIRD_PARTY_NOTICES.md").is_file())


@unittest.skipIf(QApplication is None, "sin PySide6")
class TestEnAcercaDe(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.app = qt.app()

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        parche = mock.patch.dict(os.environ, {"XDG_DATA_HOME": tmp.name})
        parche.start()
        self.addCleanup(parche.stop)
        from silux.settings import Preferences
        from silux.ui import theme
        from silux.ui.pages.settings import SettingsPage
        self.pagina = SettingsPage(Preferences().normalized(),
                                   theme.palette_for(self.app, "dark"))
        self.addCleanup(self.pagina.deleteLater)
        self.pagina.resize(1200, 900)
        self.pagina.show()
        self.app.processEvents()

    def test_dice_de_donde_salen_los_datos_y_de_quien_son(self):
        texto = " ".join(w.text() for w in self.pagina.findChildren(QLabel)
                         if w.isVisibleTo(self.pagina))
        for quien in ("libcpuid", "Veselin Georgiev", "CPU-X",
                      "The Tumultuous Unicorn Of Darkness"):
            with self.subTest(quien=quien):
                self.assertIn(quien, texto)

    def test_el_boton_enseña_los_avisos_enteros(self):
        self.pagina.notices_button.click()
        self.app.processEvents()
        dialogo = self.pagina._dialogo_avisos
        self.addCleanup(dialogo.close)
        self.assertTrue(dialogo.isVisible())
        self.assertIn("Redistribution and use in source and binary forms",
                      dialogo.texto.toPlainText())

    def test_los_enlaces_se_leen_sobre_el_fondo(self):
        """El azul de serie no se leía sobre el fondo oscuro; se vio en la
        captura. Van del color del acento."""
        self.pagina.notices_button.click()
        self.app.processEvents()
        documento = self.pagina._dialogo_avisos.texto.document()
        self.addCleanup(self.pagina._dialogo_avisos.close)
        colores = set()
        bloque = documento.begin()
        while bloque.isValid():
            trozo = bloque.begin()
            while not trozo.atEnd():
                formato = trozo.fragment().charFormat()
                if formato.isAnchor():
                    colores.add(formato.foreground().color().name().lower())
                trozo += 1
            bloque = bloque.next()
        self.assertEqual(colores, {self.pagina._p.accent.lower()})


if __name__ == "__main__":
    unittest.main()
