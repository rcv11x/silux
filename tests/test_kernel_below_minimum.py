"""A kernel older than the minimum says so: below it a missing value may be
the kernel's, and the per-feature table only goes back to the minimum."""

import json
import unittest

from silux import kernel, sysroot, volcado
from silux.collector import Collector
from silux.i18n import _
from silux.model import Need
from tests import pantalla, qt
from tests.interval import second_snapshot
from tests.test_equipos import EQUIPOS


def _snapshot(release: str):
    with volcado.mounted(EQUIPOS / "qemu-kvm") as raiz:
        ruta = raiz / "grabado.json"
        grabado = json.loads(ruta.read_text())
        grabado["plataforma"]["uname"]["release"] = release
        ruta.write_text(json.dumps(grabado))
        sysroot.forget()
        recolector = Collector()
        try:
            return second_snapshot(recolector)
        finally:
            recolector.close()


class TestAKernelBelowTheMinimum(unittest.TestCase):

    def test_it_is_said_on_the_system_page(self):
        f = _snapshot("5.10.0-28-amd64")
        notas = [n for n in f.notes if n.key == "kernel.belowminimum"]
        self.assertEqual([(n.path, n.need) for n in notas], [("system.kernel", Need.KERNEL)])
        texto = _("kernel.belowminimum").format(
            tuyo="5.10", minimo="{}.{}".format(*kernel.MINIMUM))
        self.assertEqual(notas[0].message, texto)
        qt.app()
        with pantalla.Ventana(f) as ventana:
            ventana.select_section("Sistema")
            self.assertIn(texto, " ".join(pantalla.textos_de(ventana.stack.currentWidget())))

    def test_the_minimum_itself_says_nothing(self):
        f = _snapshot("5.15.0-130-generic")
        self.assertFalse([n for n in f.notes if n.key == "kernel.belowminimum"])


if __name__ == "__main__":
    unittest.main()
