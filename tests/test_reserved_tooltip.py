"""«Reservado» says what it is.

On the 5800X3D's storage bar it reads «Reservado 89.9 GB», which jars:
it is the space ext4 keeps for root and its own tables. On hover, the
segment and its legend say so, in Almacenamiento and in Inicio.
"""

import unittest

from silux.i18n import _
from tests import pantalla, qt
from tests.test_equipos import EQUIPOS, foto


class TestTheReservedSpaceExplainsItself(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.app = qt.app()
        cls.photo = foto(EQUIPOS / "5800x3d")[0]

    def _barra(self, ventana, seccion, barra):
        ventana.select_section(seccion)
        for _vez in range(4):
            self.app.processEvents()
        return barra(ventana)

    def _check(self, barra):
        insignias = {w.text().split("  ")[0]: w.toolTip() for w in barra._legend._widgets}
        self.assertEqual(insignias[_("storage.bar.reserved")], _("storage.bar.reserved.tip"))
        # The others have nothing to explain.
        self.assertEqual({k: v for k, v in insignias.items() if v},
                         {_("storage.bar.reserved"): _("storage.bar.reserved.tip")})
        # And over the bar, the segment under the pointer.
        x = next(x for x in range(barra.width())
                 if (tramo := barra._tramo_en(x)) and tramo.key == "reserved")
        self.assertEqual(barra._tramo_en(x).tooltip, _("storage.bar.reserved.tip"))

    def test_in_storage(self):
        with pantalla.Ventana(self.photo) as ventana:
            self._check(self._barra(ventana, "Almacenamiento", lambda v: v.storage_page.total_bar))

    def test_in_home(self):
        with pantalla.Ventana(self.photo) as ventana:
            self._check(self._barra(ventana, "Inicio", lambda v: v.home_page.discos.barra))


if __name__ == "__main__":
    unittest.main()
