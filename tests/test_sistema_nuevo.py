"""Sistema: vulnerabilidades, intercambio y arranque.

Los textos de los archivos son los que dio el 5800X3D (CachyOS, kernel 7.3.4,
Limine) el 17 de noviembre de 2026, sin permisos.
"""

import dataclasses
import json
import unittest

from silux import render
from silux.i18n import _
from silux.model import Boot, Swap
from silux.providers.base import Draft
from silux.providers.system import SystemSecurity, state_of, read_swaps
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


# Lo que da el i5-10400 de la oficina (MSI H510M, GRUB de Fedora) el 18 de
# noviembre de 2026, sin permisos.
FPDT_I5_10400 = {
    "/sys/firmware/acpi/fpdt/boot/firmware_start_ns": "182920179\n",
    "/sys/firmware/acpi/fpdt/boot/bootloader_load_ns": "5151336937\n",
    "/sys/firmware/acpi/fpdt/boot/bootloader_launch_ns": "5174902848\n",
    "/sys/firmware/acpi/fpdt/boot/exitbootservice_start_ns": "12319491606\n",
    "/sys/firmware/acpi/fpdt/boot/exitbootservice_end_ns": "12319794851\n",
}
SYSTEMD_I5_10400 = {"InitRDTimestampMonotonic": 859939,
                    "UserspaceTimestampMonotonic": 2606157,
                    "FinishTimestampMonotonic": 22060289}
# Como lo deja un volcado: lo que contestó `systemctl show`.
GRABADO_SYSTEMD = {"/grabado.json": json.dumps({"systemd": {"arranque": SYSTEMD_I5_10400}})}

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
            return dataclasses.replace(draft.system, swaps=read_swaps())

    def test_las_vulnerabilidades_con_el_texto_del_kernel_y_su_estado(self):
        sistema = self._sistema(EQUIPO)
        self.assertEqual([(v.name, v.state) for v in sistema.vulnerabilities],
                         [("meltdown", "unaffected"), ("spec_rstack_overflow", "mitigated"),
                          ("spectre_v2", "mitigated"), ("tsa", "mitigated")])
        self.assertTrue(sistema.vulnerabilities[2].status.endswith("BHI: Not affected"))

    def test_los_estados(self):
        self.assertEqual(state_of("Vulnerable: Clear CPU buffers attempted, no microcode"),
                         "vulnerable")
        self.assertEqual(state_of("KVM: Mitigation: VMX disabled"), "mitigated")
        # «Not affected» dentro de una mitigación no la convierte en no afectada.
        self.assertEqual(state_of("Mitigation: Retpolines; BHI: Not affected"), "mitigated")
        self.assertEqual(state_of("Unknown: Dependent on hypervisor status"), "unknown")

    def test_el_arranque_separa_el_firmware_del_cargador(self):
        arranque = self._sistema(EQUIPO).boot
        self.assertEqual(arranque, Boot(loader="Limine 12.10.0", entry="CachyOS.linux-cachyos",
                                        firmware_s=13.3, loader_s=5.3))
        self.assertEqual(arranque.total_s, 18.6)
        self.assertEqual(render.boot_phases(arranque),
                         [("sys.boot.phase.firmware", "13.3 s"),
                          ("sys.boot.phase.loader", "5.3 s"),
                          ("sys.boot.phase.total", "18.6 s")])

    def test_sin_gestor_ni_firmware_ni_systemd_no_hay_nada_y_no_se_inventa(self):
        sin = {k: v for k, v in EQUIPO.items() if "efivars" not in k}
        arranque = self._sistema(sin).boot
        self.assertEqual(arranque, Boot())
        self.assertEqual(render.boot_phases(arranque), [])

    def test_con_grub_el_firmware_y_el_cargador_salen_de_la_fpdt(self):
        """Revisión del autor: con GRUB no salía ningún tiempo. GRUB no
        publica LoaderTimeInitUSec, pero el firmware sí: su tabla FPDT, que
        el kernel deja en sysfs sin permisos y de la que systemd saca lo
        mismo. Los números son los del i5-10400 el 18 de noviembre, con su
        `systemd-analyze`: 5.174 s (firmware) + 7.144 s (loader) + 859 ms
        (kernel) + 1.746 s (initrd) + 19.454 s (userspace) = 34.380 s."""
        grub = {k: v for k, v in EQUIPO.items() if "efivars" not in k}
        grub[f"/sys/firmware/efi/efivars/LoaderInfo-{GUID}"] = efi("GRUB 2.12")
        grub.update(FPDT_I5_10400)
        grub.update(GRABADO_SYSTEMD)
        arranque = self._sistema(grub).boot
        self.assertEqual((arranque.firmware_s, arranque.loader_s, arranque.kernel_s,
                          arranque.initrd_s, arranque.userspace_s),
                         (5.2, 7.1, 0.9, 1.7, 19.5))
        self.assertEqual([texto for _clave, texto in render.boot_phases(arranque)],
                         ["5.2 s", "7.1 s", "0.9 s", "1.7 s", "19.5 s", "34.4 s"])

    def test_systemd_da_el_kernel_con_cualquier_gestor(self):
        """Sin FPDT y sin variables del gestor: lo del kernel en adelante sí."""
        sin = {k: v for k, v in EQUIPO.items() if "efivars" not in k}
        sin.update(GRABADO_SYSTEMD)
        arranque = self._sistema(sin).boot
        self.assertEqual((arranque.firmware_s, arranque.loader_s), (None, None))
        # Sin el firmware no hay total.
        self.assertEqual(render.boot_phases(arranque),
                         [("sys.boot.phase.kernel", "0.9 s"), ("sys.boot.phase.initrd", "1.7 s"),
                          ("sys.boot.phase.userspace", "19.5 s")])

    def test_lo_que_dice_systemctl(self):
        from silux.providers.system import _parse_systemctl

        self.assertEqual(_parse_systemctl("InitRDTimestampMonotonic=859939\n"
                                         "UserspaceTimestampMonotonic=2606157\n"
                                         "FinishTimestampMonotonic=22060289\n"),
                         SYSTEMD_I5_10400)
        self.assertIsNone(_parse_systemctl(""))

    def test_el_zram_es_una_sola_fila_con_como_comprime(self):
        (swap,) = self._sistema(EQUIPO).swaps
        self.assertEqual((swap.device, swap.zram, swap.algorithm), ("/dev/zram0", True, "zstd"))
        self.assertEqual(swap.size_bytes, 32776188 * 1024)
        self.assertEqual(swap.ratio, 3.4)
        self.assertEqual(render.swap_name(swap), "zram0 (en memoria)")
        self.assertEqual(render.swap_summary(swap),
                         "10.9 MiB de 31.3 GiB · zstd · comprime 3.4 a 1 · prioridad 100")

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
                boot=draft.system.boot, swaps=read_swaps()))
        cls.sin_nada = dataclasses.replace(base, system=dataclasses.replace(
            base.system, vulnerabilities=(), boot=Boot(), swaps=()))

    @staticmethod
    def _fases(pagina):
        """Las filas de tiempos que se ven, con su valor."""
        return {_(clave): pagina.boot._values[_(clave)].full_text()
                for clave, _campo in render.BOOT_PHASES
                if pagina.boot._values[_(clave)].isVisibleTo(pagina)}

    def _pagina(self, ventana):
        ventana.select_section("Sistema")
        for _vez in range(4):
            self.app.processEvents()
        return ventana.system_page

    def test_el_resumen_y_la_lista_entera(self):
        with pantalla.Ventana(self.foto) as ventana:
            pagina = self._pagina(ventana)
            # What shows: «Sin saber» hides when nothing is unknown.
            valores = {n: e.full_text() for n, e in pagina.security._values.items()
                       if e.isVisibleTo(pagina.security)}
            self.assertEqual(valores, {
                _("sys.vuln.known"): "4", _("sys.vuln.unaffected"): "1",
                _("sys.vuln.mitigated"): "3", _("sys.vuln.open"): _("sys.vuln.none")})
            # La lista lleva las que le afectan, y la larga sale entera, sin «…».
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
                              "10.9 MiB de 31.3 GiB · zstd · comprime 3.4 a 1 · prioridad 100"})
            self.assertEqual(self._fases(pagina),
                             {"Firmware": "13.3 s", "Cargador": "5.3 s", "Total": "18.6 s"})
            self.assertEqual(pagina.boot._values[_("sys.boot.loader")].full_text(),
                             "Limine 12.10.0")
            # Estos archivos no traen lo que contestó systemd: se dice eso, y nada
            # del firmware, que sí está.
            self.assertEqual(pagina.extra_pie.text(), _("sys.boot.nosystemd"))

    def test_lo_que_el_equipo_no_publica_se_esconde_y_se_dice(self):
        with pantalla.Ventana(self.sin_nada) as ventana:
            pagina = self._pagina(ventana)
            self.assertFalse(pagina.security_card.isVisible())
            self.assertFalse(pagina.boot_card.isVisible())
            self.assertTrue(pagina.extra_pie.isVisible())
            self.assertEqual(pagina.extra_pie.text(), _("sys.boot.unpublished"))
            self.assertEqual({n: e.full_text() for n, e in pagina.swap._values.items()},
                             {_("sys.swap.label"): _("sys.swap.none")})

    def test_con_grub_salen_todos_los_tiempos(self):
        """Revisión del autor: con el GRUB de Fedora la página decía que no
        había tiempos. El firmware los publica (FPDT) y systemd da el resto
        con cualquier gestor. Volcado del i5-10400, con su FPDT y lo que
        contestó systemd."""
        intel = foto(EQUIPOS / "i5-10400")[0]
        with pantalla.Ventana(intel) as ventana:
            pagina = self._pagina(ventana)
            self.assertEqual(pagina.boot._values[_("sys.boot.loader")].full_text(), "GRUB 2.12")
            self.assertEqual(self._fases(pagina),
                             {"Firmware": "5.2 s", "Cargador": "7.1 s", "Kernel": "0.9 s",
                              "Initrd": "1.7 s", "Espacio de usuario": "19.5 s",
                              "Total": "34.4 s"})
            # Una fila por fase, entera: en una sola línea se cortaba.
            for nombre in self._fases(pagina):
                valor = pagina.boot._values[nombre]
                self.assertEqual(valor.text(), valor.full_text(), nombre)
            # No falta nada: ningún pie.
            self.assertFalse(pagina.extra_pie.isVisible())

    def test_sin_firmware_se_dice_solo_eso(self):
        """El mismo GRUB en un equipo cuyo firmware no publica la FPDT (el
        volcado del 5800X3D, que no la grabó), con systemd."""
        intel = foto(EQUIPOS / "i5-10400")[0]
        sin = dataclasses.replace(intel, system=dataclasses.replace(
            intel.system, boot=dataclasses.replace(intel.system.boot,
                                                   firmware_s=None, loader_s=None)))
        with pantalla.Ventana(sin) as ventana:
            pagina = self._pagina(ventana)
            self.assertEqual(self._fases(pagina), {"Kernel": "0.9 s", "Initrd": "1.7 s",
                                                   "Espacio de usuario": "19.5 s"})
            self.assertEqual(pagina.extra_pie.text(),
                             _("sys.boot.nofirmware").format(gestor="GRUB 2.12"))

    def test_el_pie_no_dice_que_grub_no_publique_nada(self):
        """El de Fedora sí publica su nombre."""
        self.assertNotIn("GRUB no", _("sys.boot.unpublished"))

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
