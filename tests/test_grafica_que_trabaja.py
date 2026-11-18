"""Inicio enseña la gráfica que trabaja, no la primera de la lista.

El orden de la lista es el de los nodos `cardN`, que el kernel numera según
cargan los drivers: en un portátil para jugar la integrada suele ser `card0`.
Y `boot_vga` dice con cuál arrancó el firmware, que en un portátil es la
integrada (drivers/pci/pci-sysfs.c, `boot_vga_show`). Se monta lo que el
kernel publica de las dos y se mira qué sale.
"""

import unittest

from silux.providers import drm
from silux.providers.base import Draft
from tests.test_gpu import BancoDrm, _write


class TestLaQueTrabaja(BancoDrm):
    def setUp(self):
        super().setUp()
        # La integrada de Intel, con la que arranca el firmware.
        self.tarjeta(0, ranura="0000:00:02.0", vendor="0x8086", device="0x9bc8",
                     boot_vga="1", **{"class": "0x030000"})
        _write(self.root / "pci0000:00" / "0000:00:02.0" / "power" / "runtime_status", "active")
        # La dedicada, una NVIDIA de portátil detrás de su puerto. Sin
        # `boot_vga`: el núcleo PCI solo lo crea para las de clase VGA, y la de
        # un Optimus es 3D (0x0302). Se sabe dedicada por el fabricante.
        self.dedicada = self.tarjeta(
            1, ranura="0000:01:00.0", vendor="0x10de", device="0x2520",
            **{"class": "0x030200"})

    def foto(self, estado: str):
        _write(self.dedicada / "power" / "runtime_status", estado)
        draft = Draft()
        drm.DrmGpus().collect(draft)
        drm.GpuState().collect(draft)
        return draft.freeze()

    def test_la_dedicada_despierta(self):
        foto = self.foto("active")
        self.assertEqual(foto.gpus[0].vendor_id, 0x8086)
        self.assertEqual(foto.working_gpu, 1)

    def test_si_la_dedicada_duerme_la_integrada(self):
        self.assertEqual(self.foto("suspended").working_gpu, 0)

    def test_inicio_la_enseña(self):
        from silux.settings import Preferences
        from silux.ui import theme
        from silux.ui.pages.home import HomePage
        from tests import qt
        theme.set_density("normal", "normal")
        pagina = HomePage(theme.palette_for(qt.app(), "dark"),
                          Preferences(font_scale="normal").normalized())
        foto = self.foto("active")
        pagina.apply(foto)
        self.assertEqual(pagina.gpu.nombre.text(), foto.gpus[1].display_name)
        self.assertNotEqual(foto.gpus[0].display_name, foto.gpus[1].display_name)


if __name__ == "__main__":
    unittest.main()
