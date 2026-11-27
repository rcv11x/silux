"""A module whose SPD chip the kernel never looked for.

`i2c_register_spd` looks at 0x50 + n for each slot the firmware declares:
0x50 and 0x51 with two. Two laptops with two modules had the second one's
chip elsewhere, and only the first was read. The page says why and gives
the order that registers it at 0x52, as text to copy: Silux writes nothing.

The modules are what each machine's firmware table gave, as its report
showed with permissions; the chips are the dumps'.
"""

import errno
import unittest
from unittest import mock

from silux import spd, volcado
from silux.collector import Collector
from silux.i18n import _
from silux.model import MemoryModule
from silux.providers.base import Draft
from silux.providers.privileged_memory import PrivilegedMemory
from silux.providers.spd_modules import SpdModules
from tests import pantalla, qt
from tests.interval import fake_clock, next_snapshot
from tests.test_equipos import EQUIPOS

try:
    from PySide6.QtWidgets import QApplication, QLabel
except ImportError:                                    # pragma: no cover
    QApplication = None

GIB = 1024 ** 3


def _slots(*types):
    return [MemoryModule(locator=f"DIMM_{'AB'[n]}", populated=True, size_bytes=GIB,
                         type=kind, form_factor=0x0D) for n, kind in enumerate(types)]


def _collect(dump, modules):
    with volcado.mounted(EQUIPOS / dump):
        draft = Draft()
        draft.modules = list(modules)
        SpdModules().collect(draft)
    return draft


class TestTheOrder(unittest.TestCase):

    def test_with_the_bus_and_the_name_of_each_machine(self):
        for dump, types, order in (
                ("celeron-560", ("DDR2", "DDR"),
                 "echo spd 0x52 | sudo tee /sys/bus/i2c/devices/i2c-0/new_device"),
                ("i5-5200u", ("DDR3", "DDR3"),
                 "echo spd 0x52 | sudo tee /sys/bus/i2c/devices/i2c-2/new_device")):
            with self.subTest(dump=dump):
                note = next(n for n in _collect(dump, _slots(*types)).notes
                            if n.key == "prov.spd.unregistered")
                self.assertIn(order, note.hint)
                self.assertEqual(note.title, _("prov.spd.unregistered.title"))

    def test_every_module_read_has_nothing_to_register(self):
        draft = _collect("celeron-560", _slots("DDR2"))
        self.assertFalse([n for n in draft.notes if n.key == "prov.spd.unregistered"])

    def test_without_the_firmware_table_it_isnt_known(self):
        # Memory soldered on the board has no chip either.
        draft = _collect("celeron-560", [])
        self.assertFalse([n for n in draft.notes if n.key == "prov.spd.unregistered"])

    def test_a_chip_at_0x52_is_not_this(self):
        with volcado.mounted(EQUIPOS / "celeron-560") as root:
            source = root / "sys/devices/pci0000:00/0000:00:1f.3/i2c-0/0-0050"
            (source.parent / "0-0052").mkdir()
            (root / "sys/bus/i2c/devices/0-0052").symlink_to(
                "../../../devices/pci0000:00/0000:00:1f.3/i2c-0/0-0052")
            readings = spd.read_all()
            self.assertIsNone(spd.register_by_hand(readings))

    def test_memory_soldered_as_the_first_slot_is_not_this(self):
        # Its firmware calls the soldered memory a SODIMM in «ChannelA-DIMM0»,
        # and the slot's chip answers at 0x51.
        draft = _collect("i5-8350u", _slots("DDR4", "DDR4"))
        self.assertFalse([n for n in draft.notes if n.key == "prov.spd.unregistered"])

    def test_the_kernels_names(self):
        self.assertEqual({spd.KERNEL_NAMES[t] for t in ("DDR2", "DDR3")}, {"spd"})
        self.assertEqual(spd.KERNEL_NAMES["DDR4"], "ee1004")
        self.assertEqual(spd.KERNEL_NAMES["DDR5"], "spd5118")


def _with_permissions(_self, draft):
    draft.modules = _slots("DDR2", "DDR")


def _snapshot(prepare=None):
    """The Vostro's dump with its firmware's table, as the app collects it."""
    with mock.patch.object(PrivilegedMemory, "collect", _with_permissions), \
            volcado.mounted(EQUIPOS / "celeron-560") as root, fake_clock() as clock:
        if prepare is not None:
            prepare(root)
        collector = Collector()
        try:
            collector.snapshot()
            return next_snapshot(collector, clock)
        finally:
            collector.close()


def _foot(snapshot) -> str:
    app = qt.app()
    with pantalla.Ventana(snapshot) as window:
        window.select_section("Memoria")
        for _turn in range(3):
            app.processEvents()
        page = window.stack.currentWidget()
        # The foot, and why the SPD isn't read in its notice under the modules.
        return "\n\n".join([page.spd_missing.text()] + [
            label.text() for label in page.spd_reason.findChildren(QLabel)
            if label.isVisibleTo(page)])


def _sentence(key: str, **fields) -> str:
    """The sentence without the list of fields it starts with."""
    return _(key).format(campos="", **fields).strip()


@unittest.skipIf(QApplication is None, "no PySide6")
class TestOnThePage(unittest.TestCase):

    def test_said_with_the_order_to_copy(self):
        from PySide6.QtCore import Qt

        from silux.ui.widgets import Notice

        app = qt.app()
        snapshot = _snapshot()
        order = "echo spd 0x52 | sudo tee /sys/bus/i2c/devices/i2c-0/new_device"
        with pantalla.Ventana(snapshot) as window:
            window.select_section("Memoria")
            for _turn in range(3):
                app.processEvents()
            notices = window.stack.currentWidget().findChildren(Notice)
            found = [n for n in notices
                     if n.findChild(QLabel, "NoticeTitle").text()
                     == _("prov.spd.unregistered.title")]
            self.assertEqual(len(found), 1)
            hint = found[0].findChild(QLabel, "NoticeHint")
            self.assertTrue(hint.isVisible())
            self.assertIn(order, hint.text())
            self.assertTrue(hint.textInteractionFlags()
                            & Qt.TextInteractionFlag.TextSelectableByMouse)

    def test_the_foot_says_whose_chip_was_not_read(self):
        # The first module's chip was read and is on its card.
        foot = _foot(_snapshot())
        self.assertIn(_sentence("memory.na.nospd.one", n="2"), foot)
        self.assertNotIn(_sentence("memory.na.nospd"), foot)

    def test_a_chip_that_fails_to_read_says_whose_too(self):
        def a_second_chip_that_fails(root):
            device = root / "sys/devices/pci0000:00/0000:00:1f.3/i2c-0/0-0052"
            device.mkdir()
            (device / "eeprom").write_bytes(b"")
            (root / "sys/bus/i2c/devices/0-0052").symlink_to(
                "../../../devices/pci0000:00/0000:00:1f.3/i2c-0/0-0052")

        read_pages = spd.read_pages

        def failing(path):
            if path.parent.name == "0-0052":
                raise OSError(errno.ENXIO, "No such device or address")
            return read_pages(path)

        with mock.patch.object(spd, "read_pages", failing):
            snapshot = _snapshot(a_second_chip_that_fails)
        self.assertEqual([n.key for n in snapshot.notes if n.path == "spd"],
                         ["prov.spd.readfailed"])
        foot = _foot(snapshot)
        self.assertIn(_sentence("memory.na.nospd.why.one", n="2",
                                motivo="").rstrip(":"), foot)
        self.assertNotIn(_sentence("memory.na.nospd.why", motivo="").rstrip(":"), foot)


if __name__ == "__main__":
    unittest.main()
