"""A module's ranks: from the firmware's table, and else from its SPD.

An older SMBIOS has no rank field, and the row showed a dash beside an SPD
declaring two. The module is a DDR2 SODIMM as its report showed it with
permissions; its SPD is the dump's.
"""

import dataclasses
import unittest

from silux.i18n import _
from silux.model import MemoryModule
from tests import pantalla, qt
from tests.test_equipos import EQUIPOS, foto

try:
    from PySide6.QtWidgets import QApplication
except ImportError:                                    # pragma: no cover
    QApplication = None


def _with_permissions():
    snapshot = foto(EQUIPOS / "celeron-560")[0]
    module = MemoryModule(locator="DIMM_A", bank="CHANNEL A", populated=True,
                          size_bytes=1024 ** 3, type="DDR2", form_factor=0x0D,
                          speed_mts=667, configured_mts=667, spd=snapshot.spd[0])
    return dataclasses.replace(snapshot, modules=(module,))


class TestTheRanks(unittest.TestCase):

    def test_the_spd_when_the_table_has_none(self):
        module = _with_permissions().modules[0]
        self.assertIsNone(module.rank)
        self.assertEqual(module.ranks, 2)
        self.assertEqual(dataclasses.replace(module, rank=1).ranks, 1)

    @unittest.skipIf(QApplication is None, "no PySide6")
    def test_on_the_page(self):
        from silux.ui.widgets import InfoGrid

        app = qt.app()
        with pantalla.Ventana(_with_permissions()) as window:
            window.select_section("Memoria")
            for _turn in range(3):
                app.processEvents()
            ranks = [g._values[_("memory.field.ranks")].full_text()
                     for g in window.stack.currentWidget().findChildren(InfoGrid)
                     if _("memory.field.ranks") in g._values]
        self.assertEqual(ranks, ["2"])


if __name__ == "__main__":
    unittest.main()
