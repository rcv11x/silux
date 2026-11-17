"""Sistema: vulnerabilidades, intercambio y arranque.

Los textos de los archivos son los que dio el 5800X3D (CachyOS, kernel 7.3.4,
Limine) el 17 de noviembre de 2026, sin permisos.
"""

import dataclasses
import unittest

from silux import render
from silux.i18n import _
from silux.model import Boot, Swap
from silux.providers.base import Draft
from silux.providers.system import SystemSecurity, estado_de, leer_intercambio
from tests import pantalla, qt
from tests.arbol import arbol
from tests.test_equipos import EQUIPOS, foto

try:
    from PySide6.QtWidgets import QApplication
except ImportError:                                    # pragma: no cover
    QApplication = None

VULN = "/sys/devices/system/cpu/vulnerabilities/"
GUID = "4a67b082-0a4c-41cf-b6c7-440b29bb8c4f"


def efi(texto: str) -> bytes:
    return b"\x06\x00\x00\x00" + texto.encode("utf-16-le") + b"\x00\x00"


EQUIPO = {
    VULN + "meltdown": "Not affected\n",
    VULN + "spec_rstack_overflow": "Mitigation: Safe RET\n",
    VULN + "spectre_v2": "Mitigation: Retpolines; IBPB: conditional; IBRS_FW; STIBP: always-on; "
                         "RSB filling; PBRSB-eIBRS: Not affected; BHI: Not affected\n",
    VULN + "tsa": "Mitigation: Clear CPU buffers\n",
    "/proc/swaps": "Filename\t\t\t\tType\t\tSize\t\tUsed\t\tPriority\n"
                   "/dev/zram0                              partition\t32776188\t11172\t\t100\n",
    "/sys/block/zram0/comp_algorithm": "lzo-rle lzo lz4 lz4hc [zstd] deflate 842\n",
    "/sys/block/zram0/mm_stat": " 6365184  1858709  3268608        0  3268608        0"
                                "        0        0        0\n",
    f"/sys/firmware/efi/efivars/LoaderInfo-{GUID}": efi("Limine 12.10.0"),
    f"/sys/firmware/efi/efivars/LoaderEntrySelected-{GUID}": efi("CachyOS.linux-cachyos"),
    f"/sys/firmware/efi/efivars/LoaderTimeInitUSec-{GUID}": efi("13319778"),
    f"/sys/firmware/efi/efivars/LoaderTimeExecUSec-{GUID}": efi("18585953"),
    f"/sys/firmware/efi/efivars/LoaderDevicePartUUID-{GUID}": efi("no-se-lee"),
}


class TestElProveedor(unittest.TestCase):

    def _sistema(self, archivos):
        with arbol(archivos):
            draft = Draft()
            SystemSecurity().collect(draft)
            return dataclasses.replace(draft.system, swaps=leer_intercambio())

    def test_las_vulnerabilidades_con_el_texto_del_kernel_y_su_estado(self):
        sistema = self._sistema(EQUIPO)
        self.assertEqual([(v.name, v.state) for v in sistema.vulnerabilities],
                         [("meltdown", "unaffected"), ("spec_rstack_overflow", "mitigated"),
                          ("spectre_v2", "mitigated"), ("tsa", "mitigated")])
        self.assertTrue(sistema.vulnerabilities[2].status.endswith("BHI: Not affected"))

    def test_los_estados(self):
        self.assertEqual(estado_de("Vulnerable: Clear CPU buffers attempted, no microcode"),
                         "vulnerable")
        self.assertEqual(estado_de("KVM: Mitigation: VMX disabled"), "mitigated")
        # «Not affected» dentro de una mitigación no la convierte en no afectada.
        self.assertEqual(estado_de("Mitigation: Retpolines; BHI: Not affected"), "mitigated")
        self.assertEqual(estado_de("Unknown: Dependent on hypervisor status"), "unknown")

    def test_el_arranque_separa_el_firmware_del_cargador(self):
        arranque = self._sistema(EQUIPO).boot
        self.assertEqual(arranque, Boot(loader="Limine 12.10.0", entry="CachyOS.linux-cachyos",
                                        firmware_s=13.3, loader_s=5.3))
        self.assertEqual(arranque.total_s, 18.6)
        self.assertEqual(render.boot_times(arranque),
                         "Firmware 13.3 s · cargador 5.3 s · total 18.6 s")

    def test_con_grub_no_hay_nada_y_no_se_inventa(self):
        sin = {k: v for k, v in EQUIPO.items() if "efivars" not in k}
        arranque = self._sistema(sin).boot
        self.assertEqual(arranque, Boot())
        self.assertIsNone(render.boot_times(arranque))

    def test_el_zram_es_una_sola_fila_con_como_comprime(self):
        (swap,) = self._sistema(EQUIPO).swaps
        self.assertEqual((swap.device, swap.zram, swap.algorithm), ("/dev/zram0", True, "zstd"))
        self.assertEqual(swap.size_bytes, 32776188 * 1024)
        self.assertEqual(swap.ratio, 3.4)
        self.assertEqual(render.swap_name(swap), "zram0 (en memoria)")
        self.assertEqual(render.swap_summary(swap),
                         "10.9 MB de 31.3 GB · zstd · comprime 3.4 a 1 · prioridad 100")

    def test_un_archivo_de_intercambio(self):
        archivos = dict(EQUIPO)
        archivos["/proc/swaps"] = ("Filename\t\t\t\tType\t\tSize\t\tUsed\t\tPriority\n"
                                   "/swapfile                               file\t\t8388604\t\t0\t\t-2\n")
        (swap,) = self._sistema(archivos).swaps
        self.assertEqual((swap.kind, swap.zram, swap.priority), ("file", False, -2))
        self.assertEqual(render.swap_name(swap), "/swapfile (archivo)")

    def test_sin_intercambio(self):
        archivos = dict(EQUIPO)
        archivos["/proc/swaps"] = "Filename\t\t\t\tType\t\tSize\t\tUsed\t\tPriority\n"
        self.assertEqual(self._sistema(archivos).swaps, ())


@unittest.skipIf(QApplication is None, "sin PySide6")
class TestEnLaPagina(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.app = qt.app()
        base = foto(EQUIPOS / "5800x3d")[0]
        with arbol(EQUIPO):
            draft = Draft()
            SystemSecurity().collect(draft)
            cls.foto = dataclasses.replace(base, system=dataclasses.replace(
                base.system, vulnerabilities=draft.system.vulnerabilities,
                boot=draft.system.boot, swaps=leer_intercambio()))
        cls.sin_nada = dataclasses.replace(base, system=dataclasses.replace(
            base.system, vulnerabilities=(), boot=Boot(), swaps=()))

    def _pagina(self, ventana):
        ventana.select_section("Sistema")
        for _vez in range(4):
            self.app.processEvents()
        return ventana.system_page

    def test_el_resumen_y_la_lista_entera(self):
        with pantalla.Ventana(self.foto) as ventana:
            pagina = self._pagina(ventana)
            valores = {n: e.full_text() for n, e in pagina.security._values.items()}
            self.assertEqual(valores, {
                _("sys.vuln.known"): "4", _("sys.vuln.unaffected"): "1",
                _("sys.vuln.mitigated"): "3", _("sys.vuln.open"): _("sys.vuln.none")})
            # La lista lleva las mitigadas, y la larga sale entera, sin «…».
            self.assertEqual(list(pagina.vulns._values),
                             ["spec_rstack_overflow", "spectre_v2", "tsa"])
            pagina.vuln_fold.boton.click()
            for _vez in range(4):
                self.app.processEvents()
            larga = pagina.vulns._values["spectre_v2"]
            self.assertTrue(larga.isVisible())
            self.assertEqual(larga.text(), larga.full_text())
            self.assertGreaterEqual(larga.height(), larga.heightForWidth(larga.width()))

    def test_intercambio_y_arranque(self):
        with pantalla.Ventana(self.foto) as ventana:
            pagina = self._pagina(ventana)
            self.assertEqual({n: e.full_text() for n, e in pagina.swap._values.items()},
                             {"zram0 (en memoria)":
                              "10.9 MB de 31.3 GB · zstd · comprime 3.4 a 1 · prioridad 100"})
            self.assertEqual(pagina.boot._values[_("sys.boot.time")].full_text(),
                             "Firmware 13.3 s · cargador 5.3 s · total 18.6 s")
            self.assertEqual(pagina.boot._values[_("sys.boot.loader")].full_text(),
                             "Limine 12.10.0")
            self.assertFalse(pagina.extra_pie.isVisible())

    def test_lo_que_el_equipo_no_publica_se_esconde_y_se_dice(self):
        with pantalla.Ventana(self.sin_nada) as ventana:
            pagina = self._pagina(ventana)
            self.assertFalse(pagina.security_card.isVisible())
            self.assertFalse(pagina.boot_card.isVisible())
            self.assertTrue(pagina.extra_pie.isVisible())
            self.assertEqual(pagina.extra_pie.text(), _("sys.boot.unpublished"))
            self.assertEqual({n: e.full_text() for n, e in pagina.swap._values.items()},
                             {_("sys.swap.label"): _("sys.swap.none")})

    def test_un_intercambio_que_aparece_con_la_pagina_abierta(self):
        with pantalla.Ventana(self.sin_nada) as ventana:
            pagina = self._pagina(ventana)
            ventana._on_sample(self.foto)
            for _vez in range(4):
                self.app.processEvents()
            self.assertEqual(list(pagina.swap._values), ["zram0 (en memoria)"])
            self.assertTrue(pagina.swap._values["zram0 (en memoria)"].isVisible())
            self.assertTrue(pagina.boot_card.isVisible())

    def test_la_version_de_mesa_sale_de_lo_que_ya_dice_opengl(self):
        base = foto(EQUIPOS / "5800x3d")[0]
        self.assertRegex(render.graphics_stack(base) or "", r"^Mesa \d+\.\d+")
        with pantalla.Ventana(base) as ventana:
            pagina = self._pagina(ventana)
            self.assertEqual(pagina.kernel._values[_("sys.kernel.graphics")].full_text(),
                             render.graphics_stack(base))


if __name__ == "__main__":
    unittest.main()
