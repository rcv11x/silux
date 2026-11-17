"""Los datos nuevos, leídos del volcado del 5800X3D por los proveedores.

`tests/test_placa_nueva.py`, `test_sistema_nuevo.py` y los demás prueban las
páginas con datos puestos a mano o con archivos sueltos. Aquí es el Collector
entero leyendo el equipo volcado: lo que comprueba es que lo que cada
proveedor abre está en el volcado, y que el volcado no lleva lo que no debe.

El del i5-10400 es de antes de estos proveedores y no trae nada de esto: se
rehace en la oficina. Hasta entonces solo se le exige que no reviente.
"""

import pathlib
import unittest

from silux import privacidad, render
from tests.test_equipos import EQUIPOS, foto


class TestElVolcadoNuevo(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.foto = foto(EQUIPOS / "5800x3d")[0]

    def test_los_dispositivos_pci_con_el_nombre_de_su_pagina(self):
        por_tipo = {}
        for d in self.foto.pci_devices:
            por_tipo.setdefault(d.kind, []).append(d)
        self.assertEqual([d.name for d in por_tipo["gpu"]], [self.foto.gpus[0].name])
        self.assertEqual(sorted(d.name for d in por_tipo["nvme"]),
                         sorted(x.model for x in self.foto.disks if x.transport == "nvme"))
        for clase in ("ethernet", "sata", "usb", "audio"):
            self.assertTrue(por_tipo.get(clase), clase)
        # Cada dirección, una vez.
        self.assertEqual(len({d.slot for d in self.foto.pci_devices}),
                         len(self.foto.pci_devices))

    def test_el_enlace_de_la_grafica_es_el_de_graficos(self):
        gpu = next(d for d in self.foto.pci_devices if d.kind == "gpu")
        self.assertEqual(render.pcie_link(gpu.link), render.pcie_link(self.foto.gpus[0].link))
        self.assertEqual(render.pcie_link(gpu.link), "PCIe 4.0 × 16")
        # Lo que no va en una ranura no trae enlace.
        self.assertTrue(all(d.link is None for d in self.foto.pci_devices
                            if d.kind in ("sata", "usb", "audio")))

    def test_la_plataforma(self):
        p = self.foto.platform
        self.assertEqual((p.virtualization, p.virtualization_kind), ("active", "AMD-V"))
        self.assertGreater(p.iommu_groups, 0)
        self.assertGreater(p.above_4g_devices, 0)
        self.assertEqual(render.chip_name(p.sensor_chip), "it8688")
        self.assertEqual(p.audio_codec, "Realtek ALCS1200A")

    def test_el_sistema(self):
        s = self.foto.system
        self.assertGreater(s.processes, 100)            # y no «1»: va grabado
        self.assertGreater(len(s.vulnerabilities), 10)
        self.assertFalse([v for v in s.vulnerabilities if v.state == "vulnerable"])
        self.assertEqual(s.boot.loader.split()[0], "Limine")
        self.assertAlmostEqual(s.boot.total_s, s.boot.firmware_s + s.boot.loader_s, places=1)
        self.assertEqual([(x.zram, x.algorithm) for x in s.swaps], [(True, "zstd")])
        self.assertRegex(render.graphics_stack(self.foto), r"^Mesa \d+")

    def test_lo_enchufado_sin_marcas_ni_modelos(self):
        usb = self.foto.usb_devices
        self.assertGreater(len(usb), 5)
        self.assertEqual({(u.vendor, u.product, u.usb_id) for u in usb}, {(None, None, None)})
        self.assertIn("hub", {u.kind for u in usb})
        self.assertNotIn("other", {u.kind for u in usb if not u.is_hub})
        self.assertTrue(any(u.parent for u in usb))
        self.assertTrue(all(s.name is None for s in self.foto.sound_cards))
        self.assertTrue(all(c.name is None for c in self.foto.cameras))
        self.assertTrue(all(b.product is None for b in self.foto.bluetooth))
        # Anonimizar ya no encuentra nada que quitar ahí.
        anonima = privacidad.anonimizar(self.foto)
        self.assertEqual(anonima.usb_devices, usb)
        self.assertEqual(anonima.sound_cards, self.foto.sound_cards)

    def test_en_el_volcado_no_hay_archivos_que_digan_de_quien_es_cada_cosa(self):
        raiz = EQUIPOS / "5800x3d"
        delatores = [str(p.relative_to(raiz)) for p in raiz.rglob("*")
                     if p.name in ("product", "manufacturer", "idVendor", "idProduct")
                     and "/usb" in str(p)]
        self.assertEqual(delatores, [])
        self.assertFalse(list(raiz.rglob("LoaderDevicePartUUID*")))
        self.assertFalse(list(raiz.rglob("LoaderSystemToken*")))
        # Ningún número de serie USB ni dirección de Bluetooth se llegó a abrir.
        usb = [p for p in raiz.rglob("serial") if "/usb" in str(p)]
        self.assertEqual(usb, [])
        self.assertFalse([p for p in raiz.rglob("address") if "bluetooth" in str(p)])

    def test_el_trim_de_cada_disco(self):
        por_nombre = {d.name: d for d in self.foto.disks}
        self.assertTrue(por_nombre["nvme0n1"].discard and por_nombre["nvme0n1"].discard_mounted)
        self.assertIs(por_nombre["sdb"].discard, False)
        self.assertTrue(all(d.fstrim_timer for d in self.foto.disks))

    def test_el_reposo_no_sale_de_una_sola_lectura(self):
        self.assertEqual(self.foto.cpu.idle_states, ())


class TestElVolcadoDeAntes(unittest.TestCase):
    """El i5-10400, volcado antes de que existieran estos proveedores."""

    def test_no_revienta_y_lo_que_no_trae_queda_vacio(self):
        f = foto(EQUIPOS / "i5-10400")[0]
        self.assertEqual(f.usb_devices, ())
        self.assertEqual(f.system.vulnerabilities, ())
        self.assertEqual((f.cpu.power.limit_long_w, f.cpu.power.limit_short_w), (65.0, 115.0))


if __name__ == "__main__":
    unittest.main()
