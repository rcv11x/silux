"""A notice whose text changes is repainted on the open page.

A real case: Graphics says which graphics libraries are missing
(«deps.graphics»). Install one and the same notice, with the same path and
the same cause, lists one fewer, with a shorter command to install the rest.
Most pages compared only the path and the cause to know whether to repaint,
so the old text stayed until leaving the page and coming back.
"""

import dataclasses
import unittest

from silux.i18n import _
from silux.model import Need, Note
from tests import pantalla, qt
from tests.test_equipos import EQUIPOS, shared_snapshot
from tests.test_interface_language import visible_texts

# Each page, and a path its notices are taken from.
PAGES = (
    ("Placa base", "board.packages.pciids"),
    ("Memoria", "spd.packages"),
    ("Red", "network.packages.usbids"),
    ("CPU", "cpu.packages"),
    ("Sistema", "system.packages"),
    ("Gráficos", "gpus.packages.apis"),     # the page's own
    ("Gráficos", "gpus.0.packages"),        # its card's
)


def _note(path: str, missing: str, command: str) -> Note:
    return Note(path=path, need=Need.PACKAGE,
                message=_("deps.graphics").format(cuales=missing), hint=command)


class TestANoticeThatChangesItsText(unittest.TestCase):

    def _shown(self, section: str, before: Note, after: Note) -> list[str]:
        app = qt.app()
        snapshot = shared_snapshot(EQUIPOS / "i5-10400")
        with_note = lambda note: dataclasses.replace(snapshot, notes=snapshot.notes + (note,))
        with pantalla.Ventana(with_note(before)) as window:
            window.select_section(section)
            app.processEvents()
            window._on_sample(with_note(after))
            app.processEvents()
            return visible_texts(window.stack.currentWidget())

    def test_its_message(self):
        for section, path in PAGES:
            with self.subTest(section=section, path=path):
                before = _note(path, "Vulkan, OpenCL", "sudo dnf install vulkan-loader ocl-icd")
                after = _note(path, "OpenCL", "sudo dnf install vulkan-loader ocl-icd")
                shown = self._shown(section, before, after)
                self.assertIn(after.message, shown)
                self.assertNotIn(before.message, shown)

    def test_its_hint(self):
        for section, path in PAGES:
            with self.subTest(section=section, path=path):
                before = _note(path, "OpenCL", "sudo dnf install vulkan-loader ocl-icd")
                after = _note(path, "OpenCL", "sudo dnf install ocl-icd")
                shown = " ".join(self._shown(section, before, after))
                self.assertIn(after.hint, shown)
                self.assertNotIn(before.hint, shown)


if __name__ == "__main__":
    unittest.main()
