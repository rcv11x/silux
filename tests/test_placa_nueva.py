"""Placa base: los dispositivos PCIe y lo que la plataforma tiene activado.

Los dispositivos son los del 5800X3D (Gigabyte X570) tal y como los dio el
proveedor en esa máquina el 18 de noviembre de 2026, sin permisos. Lo que el
proveedor lee del bus se comprueba además contra el volcado, en
`tests/test_equipos_nuevo.py`.
"""

import dataclasses
import struct
import unittest

from silux import render
from silux.i18n import _
from silux.model import PciDevice, PcieLink, Platform
from silux.privileged import smbios
from tests import pantalla, qt
from tests.test_equipos import EQUIPOS, foto
from tests.test_smbios import _end, _structure

try:
    from PySide6.QtWidgets import QApplication
except ImportError:                                    # pragma: no cover
    QApplication = None


def _enlace(gts, ancho, max_gts=None, max_ancho=None):
    return PcieLink(current_speed_gts=gts, current_width=ancho,
                    max_speed_gts=max_gts or gts, max_width=max_ancho or ancho)


DISPOSITIVOS = (
    PciDevice("0000:0c:00.0", "gpu", "Radeon RX 9070 XT 16GB", "AMD", "amdgpu", _enlace(16.0, 16)),
    PciDevice("0000:01:00.0", "nvme", "WD_BLACK SN850X HS 1000GB", "Sandisk", "nvme", _enlace(16.0, 4)),
    PciDevice("0000:04:00.0", "nvme", "Samsung SSD 970 EVO Plus 2TB", "Samsung", "nvme", _enlace(8.0, 4)),
    PciDevice("0000:06:00.0", "ethernet", "RTL8125 2.5GbE Controller", "Realtek", "r8169", _enlace(5.0, 1)),
    PciDevice("0000:08:00.0", "sata", "FCH SATA Controller [AHCI mode]", "AMD", "ahci"),
    PciDevice("0000:07:00.1", "usb", "Matisse USB 3.0 Host Controller", "AMD", "xhci_hcd"),
    PciDevice("0000:0c:00.1", "audio", "Navi 48 HDMI/DP Audio Controller", "AMD", "snd_hda_intel"),
    PciDevice("0000:0e:00.4", "audio", "Starship/Matisse HD Audio Controller", "AMD", "snd_hda_intel"),
)
PLATAFORMA = Platform(iommu_groups=34, virtualization="active", virtualization_kind="AMD-V",
                      above_4g_devices=4, sensor_chip="it8688_40050607",
                      audio_codec="Realtek ALCS1200A")


def _ranura(nombre: str, bus: int, dispositivo: int, funcion: int = 0, segmento: int = 0) -> bytes:
    """Una estructura de tipo 9 con esa dirección."""
    campos = bytearray(0x11 - 4)
    campos[0x04 - 4] = 1                                   # cadena 1: el nombre
    campos[0x05 - 4] = 0xA5                                # PCI Express x16
    campos[0x07 - 4] = 0x04                                # en uso
    struct.pack_into("<H", campos, 0x0D - 4, segmento)
    campos[0x0F - 4] = bus
    campos[0x10 - 4] = (dispositivo << 3) | funcion
    return _structure(9, bytes(campos), [nombre])


class TestLasRanurasDelFirmware(unittest.TestCase):

    def test_la_direccion_y_el_nombre(self):
        tabla = _ranura("PCIEX16", 0x0A, 0) + _ranura("M2A_CPU", 0x01, 0) + _end()
        self.assertEqual(smbios.system_slots(list(smbios.parse_table(tabla))),
                         {"0000:0a:00.0": "PCIEX16", "0000:01:00.0": "M2A_CPU"})

    def test_las_que_el_firmware_marca_como_desconocidas_no_entran(self):
        tabla = (_ranura("PCIEX1_1", 0xFF, 0x1F, 7) + _ranura("PCIEX4", 0x05, 0, segmento=0xFFFF)
                 + _end())
        self.assertEqual(smbios.system_slots(list(smbios.parse_table(tabla))), {})

    def test_una_grafica_casa_por_el_puente_de_su_tarjeta(self):
        """La ranura apunta al puente de entrada de la tarjeta, y la gráfica
        cuelga dos más abajo."""
        import pathlib
        import tempfile

        from silux.providers.pci import PciDevices

        with tempfile.TemporaryDirectory() as tmp:
            nodo = pathlib.Path(tmp, "pci0000:00", "0000:00:03.1", "0000:0a:00.0",
                                "0000:0b:00.0", "0000:0c:00.0")
            nodo.mkdir(parents=True)
            self.assertEqual(PciDevices._ranura(nodo, {"0000:0a:00.0": "PCIEX16"}), "PCIEX16")
            self.assertIsNone(PciDevices._ranura(nodo, {"0000:01:00.0": "M2A_CPU"}))
            self.assertIsNone(PciDevices._ranura(nodo, {}))


class TestLoQueDiceLaPlataforma(unittest.TestCase):

    def test_las_frases(self):
        self.assertEqual(render.iommu(PLATAFORMA), "activa · 34 grupos")
        self.assertEqual(render.virtualization(PLATAFORMA), "activa (AMD-V), en uso por KVM")
        self.assertEqual(render.above_4g(PLATAFORMA), "activo · 4 dispositivos lo usan")

    def test_lo_que_no_se_puede_afirmar_no_se_afirma(self):
        nada = Platform()
        self.assertEqual(render.iommu(nada), _("plat.iommu.off"))
        self.assertIsNone(render.virtualization(nada))
        # Ninguna dirección por encima de 4 GB no demuestra que esté apagado.
        self.assertIsNone(render.above_4g(nada))
        sin_usar = Platform(virtualization="present", virtualization_kind="VT-x")
        self.assertEqual(render.virtualization(sin_usar),
                         "el procesador la tiene (VT-x); no está en uso")


@unittest.skipIf(QApplication is None, "sin PySide6")
class TestEnLaPagina(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.app = qt.app()
        cls.base = foto(EQUIPOS / "5800x3d")[0]
        cls.foto = dataclasses.replace(cls.base, pci_devices=DISPOSITIVOS, platform=PLATAFORMA)

    def _pagina(self, ventana):
        ventana.select_section("Placa base")
        for _vez in range(4):
            self.app.processEvents()
        return ventana.board_page

    def _filas(self, pagina):
        return [[c.full_text() for c in fila] for fila in pagina.pci._cells]

    def test_una_sola_tabla_con_los_nombres_de_silux_y_el_enlace_bueno(self):
        with pantalla.Ventana(self.foto) as ventana:
            pagina = self._pagina(ventana)
            filas = self._filas(pagina)
            self.assertEqual(len(filas), len(DISPOSITIVOS))
            self.assertEqual(filas[0], ["Gráfica", "Radeon RX 9070 XT 16GB", "PCIe 4.0 × 16",
                                        "PCIe 4.0 × 16", "amdgpu"])
            self.assertEqual(filas[2][:4], ["NVMe", "Samsung SSD 970 EVO Plus 2TB",
                                            "PCIe 3.0 × 4", "PCIe 3.0 × 4"])
            # Cada dispositivo, una vez.
            self.assertEqual(len({f[1] + f[4] + f[0] for f in filas} | {"x"}) - 1,
                             len({(d.name, d.driver, d.kind) for d in DISPOSITIVOS}))
            # La dirección PCI no es una columna: va al pasar el ratón.
            self.assertFalse([c for fila in filas for c in fila if c.startswith("0000:")])
            self.assertIn("0000:0c:00.0", pagina.pci._cells[0][1].toolTip())

    def test_lo_que_no_va_en_una_ranura_no_ensena_un_enlace(self):
        with pantalla.Ventana(self.foto) as ventana:
            filas = {f[1]: f for f in self._filas(self._pagina(ventana))}
            self.assertEqual(filas["FCH SATA Controller [AHCI mode]"][2:4],
                             [_("board.pci.onboard"), ""])
            self.assertEqual(filas["Navi 48 HDMI/DP Audio Controller"][2], _("board.pci.ongpu"))
            self.assertEqual(filas["Starship/Matisse HD Audio Controller"][2],
                             _("board.pci.onboard"))

    def test_la_columna_ranura_solo_existe_con_permisos(self):
        with pantalla.Ventana(self.foto) as ventana:
            pagina = self._pagina(ventana)
            self.assertEqual(len(pagina.pci._headers), 5)
            self.assertNotIn(_("board.pci.slot"), pagina.pci._headers)
            self.assertTrue(pagina.pci_pie.isVisible())
            self.assertEqual(pagina.pci_pie.text(), _("board.pci.slots.locked"))
            # Llegan los permisos con la página abierta: sale la columna.
            con = dataclasses.replace(self.foto, pci_devices=tuple(
                dataclasses.replace(d, slot_name="PCIEX16") if d.kind == "gpu" else d
                for d in DISPOSITIVOS))
            ventana._on_sample(con)
            for _vez in range(4):
                self.app.processEvents()
            self.assertEqual(pagina.pci._headers[-1], _("board.pci.slot"))
            self.assertEqual(self._filas(pagina)[0][-1], "PCIEX16")
            self.assertEqual(self._filas(pagina)[1][-1], "")
            self.assertFalse(pagina.pci_pie.isVisible())
            self.assertTrue(pagina.pci.isVisible())

    def test_la_plataforma(self):
        with pantalla.Ventana(self.foto) as ventana:
            pagina = self._pagina(ventana)
            valores = {n: e.full_text() for n, e in pagina.platform._values.items()
                       if e.isVisible()}
            self.assertEqual(valores, {
                _("board.plat.iommu"): "activa · 34 grupos",
                _("board.plat.virt"): "activa (AMD-V), en uso por KVM",
                _("board.plat.above4g"): "activo · 4 dispositivos lo usan",
                _("board.plat.sensors"): "IT8688",
                _("board.plat.codec"): "Realtek ALCS1200A"})
            self.assertIn("Above 4G Decoding", _("board.plat.above4g"))

    def test_sin_dispositivos_la_tarjeta_no_sale(self):
        vacia = dataclasses.replace(self.base, pci_devices=(), platform=Platform())
        with pantalla.Ventana(vacia) as ventana:
            pagina = self._pagina(ventana)
            self.assertFalse(pagina.pci_card.isVisible())
            visibles = [n for n, e in pagina.platform._values.items() if e.isVisible()]
            self.assertEqual(visibles, [_("board.plat.iommu")])


if __name__ == "__main__":
    unittest.main()
