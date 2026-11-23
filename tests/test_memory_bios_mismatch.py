"""What the BIOS says of a module whose SPD chip wasn't read, against the
module whose chip was.

On a laptop with two DDR2 SODIMMs the kernel registered only the first
chip. With permissions, the firmware's table gave the second as «DDR»,
«DIMM» and running at 800 MT/s, beside a DDR2 SODIMM running at 667: a
board mixes neither generations nor slot sizes, and its modules share one
clock. The modules here are the ones its report showed with permissions;
the first one's SPD is the dump's.
"""

import dataclasses
import unittest

from silux import render
from silux.i18n import _
from silux.model import MemoryModule, firmware_contradicted
from tests import pantalla, qt
from tests.test_equipos import EQUIPOS, foto

try:
    from PySide6.QtWidgets import QApplication
except ImportError:                                    # pragma: no cover
    QApplication = None

SODIMM, DIMM = 0x0D, 0x09
GIB = 1024 ** 3


def _vostro():
    snapshot = foto(EQUIPOS / "celeron-560")[0]
    read = MemoryModule(locator="DIMM_A", bank="CHANNEL A", populated=True,
                        size_bytes=GIB, type="DDR2", form_factor=SODIMM,
                        speed_mts=667, configured_mts=667, manufacturer="Samsung",
                        spd=snapshot.spd[0])
    unread = MemoryModule(locator="DIMM_B", bank="CHANNEL B", populated=True,
                          size_bytes=GIB, type="DDR", form_factor=DIMM,
                          speed_mts=800, configured_mts=800, manufacturer="Samsung",
                          part_number="M4 70T2864EH3-CF7")
    return dataclasses.replace(snapshot, modules=(read, unread))


class TestTheRule(unittest.TestCase):

    def test_what_the_others_chip_contradicts(self):
        read, unread = _vostro().modules
        self.assertEqual(firmware_contradicted(unread, (read, unread)),
                         {"type", "form", "running"})
        self.assertEqual(firmware_contradicted(read, (read, unread)), set())

    def test_the_same_generation_is_no_contradiction(self):
        # DDR3 from the BIOS beside a DDR3L from its SPD: SMBIOS has no code
        # for DDR3L, and the two mix.
        spd = foto(EQUIPOS / "i5-5200u")[0].spd[0]
        read = MemoryModule(locator="ChannelA-DIMM0", populated=True, type="DDR3",
                            form_factor=SODIMM, speed_mts=1600, configured_mts=1600, spd=spd)
        unread = dataclasses.replace(read, locator="ChannelB-DIMM0", spd=None)
        self.assertEqual(render.module_type(read), "DDR3L")
        self.assertEqual(firmware_contradicted(unread, (read, unread)), set())

    def test_with_no_chip_read_nothing_is_judged(self):
        _read, unread = _vostro().modules
        other = dataclasses.replace(unread, locator="DIMM_A", type="DDR2")
        self.assertEqual(firmware_contradicted(unread, (other, unread)), set())


@unittest.skipIf(QApplication is None, "no PySide6")
class TestOnThePage(unittest.TestCase):

    def test_marked_and_left_out_of_the_header(self):
        from silux.ui.widgets import InfoGrid
        from tests.test_interface_language import visible_texts

        app = qt.app()
        with pantalla.Ventana(_vostro()) as window:
            window.select_section("Memoria")
            for _turn in range(3):
                app.processEvents()
            page = window.stack.currentWidget()
            texts = visible_texts(page)
            badges = [text for text, _loud in page.badges._chips]
            ranks = [g._values[_("memory.field.ranks")].full_text()
                     for g in page.findChildren(InfoGrid)
                     if _("memory.field.ranks") in g._values]
        mark = _("memory.source.bios.mismatch")
        for value in ("DDR", "DIMM", "800 MT/s"):
            self.assertIn(f"{value} · {mark}", texts)
        for value in ("DDR2", "SODIMM", "667 MT/s"):
            self.assertNotIn(f"{value} · {mark}", texts)
        self.assertIn("DDR2", badges)
        self.assertIn("667 MT/s", badges)
        self.assertEqual([b for b in badges if b in ("DDR", "800 MT/s")], [])
        # The first module's SPD declares two ranks; the second's is unknown.
        self.assertEqual(ranks, ["2", render.DASH])


def _collected_with_its_report():
    """The Vostro's dump, and its firmware's table as its report gave it."""
    from unittest import mock

    from silux import volcado
    from silux.collector import Collector
    from silux.providers.privileged_memory import PrivilegedMemory
    from tests.interval import fake_clock, next_snapshot

    def with_permissions(_self, draft):
        draft.modules = [
            MemoryModule(locator="DIMM_A", bank="CHANNEL A", populated=True, size_bytes=GIB,
                         type="DDR", form_factor=SODIMM, speed_mts=667, configured_mts=667,
                         manufacturer="Samsung", part_number="M4 70T2953EZ3-CE6"),
            MemoryModule(locator="DIMM_B", bank="CHANNEL B", populated=True, size_bytes=GIB,
                         type="DDR", form_factor=DIMM, speed_mts=800, configured_mts=800,
                         manufacturer="Samsung", part_number="M4 70T2864EH3-CF7")]

    with mock.patch.object(PrivilegedMemory, "collect", with_permissions), \
            volcado.mounted(EQUIPOS / "celeron-560"), fake_clock() as clock:
        collector = Collector()
        try:
            collector.snapshot()
            return next_snapshot(collector, clock)
        finally:
            collector.close()


@unittest.skipIf(QApplication is None, "no PySide6")
class TestTheMarkIsRead(unittest.TestCase):
    """A value marked with where it comes from is read whole: the mark is the
    point, and «DDR · según la BIOS, no…» hid it."""

    def test_no_marked_value_is_cut(self):
        from silux.settings import Preferences
        from silux.ui import theme
        from silux.ui.widgets import InfoGrid

        app = qt.app()
        # With the app's own theme and its fonts, as the window is seen.
        prefs = Preferences().normalized()
        self.addCleanup(theme.apply, app, prefs.theme, prefs.density, prefs.font_scale)
        theme.apply(app, prefs.theme, prefs.density, prefs.font_scale)
        marks = (_("memory.source.bios"), _("memory.source.spd.nominal"))
        with pantalla.Ventana(_collected_with_its_report()) as window:
            window.resize(1000, 900)
            window.select_section("Memoria")
            for _turn in range(4):
                app.processEvents()
            page = window.stack.currentWidget()
            marked = [label for grid in page.findChildren(InfoGrid)
                      for label in grid._values.values()
                      if label.isVisible() and any(m in label.full_text() for m in marks)]
            # Type, form, running and rated of the second; the first's voltage.
            self.assertGreaterEqual(len(marked), 5)
            for label in marked:
                self.assertEqual(label.text(), label.full_text())


if __name__ == "__main__":
    unittest.main()
