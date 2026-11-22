"""Every graphics card on the PCI bus is listed, and a hybrid laptop's
second one is named on Home.

A laptop's dedicated GPU asleep by Optimus showed on Graphics but not on
Home, which sums up the working card. And a card with no driver (nouveau
blacklisted, NVIDIA's not installed) has no DRM node, and was missing
everywhere.
"""

import os
import pathlib
import shutil
import tempfile
import unittest

from silux.i18n import _
from tests import pantalla, qt
from tests.test_interface_language import visible_texts
from tests.test_equipos import EQUIPOS, foto, volcados

GTX = "sys/devices/pci0000:00/0000:00:01.0/0000:01:00.0"


def _asus_without_nouveau(base: pathlib.Path) -> pathlib.Path:
    """The ASUS as it boots with nouveau blacklisted and no NVIDIA driver:
    no `driver` link and no card node for the GTX 850M."""
    folder = base / "i7-4710hq"
    shutil.copytree(EQUIPOS / "i7-4710hq", folder, symlinks=True)
    os.unlink(folder / GTX / "driver")
    shutil.rmtree(folder / GTX / "drm")
    for node in ("card1", "renderD128"):
        os.unlink(folder / "sys/class/drm" / node)
    return folder


class TestOnHome(unittest.TestCase):

    def test_the_sleeping_one_is_named(self):
        qt.app()
        snapshot = foto(EQUIPOS / "i7-4710hq")[0]
        with pantalla.Ventana(snapshot) as window:
            window.select_section("Inicio")
            text = " ".join(visible_texts(window.stack.currentWidget()))
        self.assertIn("HD Graphics 4600", text)
        self.assertIn(f"GeForce GTX 850M ({_('gpu.asleep.short')})", text)

    def test_every_dump_names_all_its_cards_on_home(self):
        qt.app()
        from silux import render
        for folder in volcados():
            snapshot = foto(folder)[0]
            with self.subTest(folder.name), pantalla.Ventana(snapshot) as window:
                window.select_section("Inicio")
                text = " ".join(visible_texts(window.stack.currentWidget()))
                for gpu in snapshot.gpus:
                    self.assertIn(render.gpu_name(gpu), text)


class TestWithoutADriver(unittest.TestCase):

    def test_listed_with_its_reason(self):
        with tempfile.TemporaryDirectory() as base:
            snapshot = foto(_asus_without_nouveau(pathlib.Path(base)))[0]
        names = [g.name for g in snapshot.gpus]
        self.assertIn("GeForce GTX 850M", names)
        index = names.index("GeForce GTX 850M")
        gtx = snapshot.gpus[index]
        self.assertEqual((gtx.pci_slot, gtx.driver, gtx.integrated),
                         ("0000:01:00.0", None, False))
        note = next(n for n in snapshot.notes if n.path == f"gpus.{index}")
        self.assertEqual(note.key, "prov.drm.unbound")
        self.assertIn("GeForce GTX 850M", note.message)
        # The integrated one keeps working, and is still the one summed up.
        self.assertEqual(snapshot.gpus[snapshot.working_gpu].name, "HD Graphics 4600")

    def test_on_graphics_and_home(self):
        qt.app()
        with tempfile.TemporaryDirectory() as base:
            snapshot = foto(_asus_without_nouveau(pathlib.Path(base)))[0]
        message = _("prov.drm.unbound").format(tarjeta="GeForce GTX 850M")
        with pantalla.Ventana(snapshot) as window:
            window.select_section("Inicio")
            self.assertIn("GeForce GTX 850M",
                          " ".join(visible_texts(window.stack.currentWidget())))
            window.select_section("Gráficos")
            self.assertIn(message, " ".join(visible_texts(window.stack.currentWidget())))


if __name__ == "__main__":
    unittest.main()
