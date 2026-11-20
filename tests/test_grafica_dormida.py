"""Una gráfica suspendida no se despierta para leerla.

La dedicada de un portátil duerme (D3) cuando nadie la usa, y el kernel lo
publica en `power/runtime_status` sin tocarla: `runtime_status_show`
(drivers/base/power/sysfs.c) devuelve el estado guardado
(Documentation/ABI/testing/sysfs-devices-power). Casi todo lo demás la
despierta: el enlace PCIe desde Linux 6.18 (`current_link_speed` pasa por
`pci_config_pm_runtime_get`), el hwmon y los ioctl de amdgpu
(`amdgpu_pm_get_access_if_active`), abrir el nodo de render, NVML.

Aquí no se monta ningún equipo: solo los archivos que el kernel garantiza en
un dispositivo PCI con runtime PM, y se mira qué se abre.
"""

import builtins
import pathlib
import unittest
from unittest import mock

from silux import collector as collector_mod
from silux import render
from silux.model import Gpu
from silux.providers import drm, nvidia
from silux.providers.base import Draft
from tests.arbol import arbol
from tests.test_gpu import BancoDrm, _write

# Lo que el núcleo PCI guarda al enumerar y publica sin tocar el dispositivo
# (drivers/pci/pci-sysfs.c: vendor, device, subsystem_*, revision, class y
# boot_vga leen de `struct pci_dev`), más el estado de runtime PM.
SIN_DESPERTAR = {"vendor", "device", "subsystem_vendor", "subsystem_device",
                 "revision", "class", "boot_vga", "runtime_status"}


class Espia:
    """Qué archivos de debajo del dispositivo se abren."""

    def __init__(self, dispositivo: pathlib.Path):
        self.dispositivo = str(dispositivo.resolve())
        self.abiertos: list[str] = []
        self._open = builtins.open

    def __call__(self, ruta, *args, **kwargs):
        texto = str(pathlib.Path(str(ruta)).resolve()) if isinstance(ruta, (str, pathlib.Path)) else ""
        if texto.startswith(self.dispositivo + "/"):
            self.abiertos.append(texto[len(self.dispositivo) + 1:])
        return self._open(ruta, *args, **kwargs)

    def prohibidos(self) -> list[str]:
        return [r for r in self.abiertos if r.rsplit("/", 1)[-1] not in SIN_DESPERTAR]


class TestUnaDedicadaDormida(BancoDrm):
    def setUp(self):
        super().setUp()
        self.dispositivo = self.tarjeta(
            1, ranura="0000:01:00.0",
            vendor="0x1002", device="0x73ff", subsystem_vendor="0x1043",
            subsystem_device="0x1e12", revision="0xc7", **{"class": "0x030000"},
            vbios_version="113-D53201-100", unique_id="00000000",
            current_link_speed="16.0 GT/s PCIe", current_link_width="8",
            max_link_speed="16.0 GT/s PCIe", max_link_width="8",
            mem_info_vram_total="8573157376", mem_info_vram_used="0",
            gpu_busy_percent="0",
        )
        _write(self.dispositivo / "power" / "runtime_status", "suspended")
        _write(self.dispositivo / "hwmon" / "hwmon5" / "temp1_input", "41000")
        _write(self.dispositivo / "hwmon" / "hwmon5" / "temp1_label", "edge")

    def _recolectar_espiando(self):
        espia = Espia(self.dispositivo)
        with mock.patch.object(builtins, "open", espia):
            draft = self.recolectar()
        return draft, espia

    def test_no_se_abre_nada_que_la_despierte(self):
        _draft, espia = self._recolectar_espiando()
        self.assertEqual(espia.prohibidos(), [])
        self.assertIn("power/runtime_status", espia.abiertos)

    def test_se_sabe_quien_es_y_que_duerme(self):
        draft, _espia = self._recolectar_espiando()
        gpu = draft.gpus[0]
        self.assertTrue(gpu["suspended"])
        self.assertEqual(gpu["device_id"], 0x73FF)
        self.assertNotIn("busy_percent", {k for k, v in gpu.items() if v is not None})
        self.assertIsNone(gpu.get("temp_c"))
        self.assertTrue(any(n.path == "gpus.0" and "reposo" in n.message for n in draft.notes))

    def test_al_despertar_se_vuelve_a_por_lo_estatico(self):
        draft = Draft()
        drm.DrmGpus().collect(draft)
        _write(self.dispositivo / "power" / "runtime_status", "active")
        estado = drm.GpuState()
        estado.collect(draft)
        self.assertTrue(draft.static_stale)
        self.assertFalse(draft.gpus[0]["suspended"])
        self.assertEqual(draft.gpus[0]["busy_percent"], 0.0)

    def test_si_se_duerme_se_dice_lo_ultimo_y_de_cuando(self):
        _write(self.dispositivo / "power" / "runtime_status", "active")
        estado = drm.GpuState()
        draft = Draft()
        drm.DrmGpus().collect(draft)
        estado.collect(draft)
        self.assertEqual(draft.gpus[0]["temp_c"], 41.0)

        _write(self.dispositivo / "power" / "runtime_status", "suspended")
        dormida = Draft()
        drm.DrmGpus().collect(dormida)
        espia = Espia(self.dispositivo)
        with mock.patch.object(builtins, "open", espia):
            estado.collect(dormida)
        self.assertEqual(espia.prohibidos(), [])
        gpu = dormida.gpus[0]
        self.assertEqual(gpu["last_temp_c"], 41.0)
        self.assertIsNotNone(gpu["last_awake_s"])
        self.assertIsNone(gpu["link"].current_speed_gts)


class TestElColectorRelee(unittest.TestCase):
    def test_lo_estatico_se_relee_cuando_algo_despierta(self):
        class Estatico:
            name, provides, static = "e", "e", True
            veces = 0

            def available(self):
                return True

            def collect(self, draft):
                Estatico.veces += 1

        class Despierta:
            name, provides, static = "d", "d", False

            def available(self):
                return True

            def collect(self, draft):
                draft.static_stale = Estatico.veces == 1

        colector = collector_mod.Collector([Estatico(), Despierta()])
        colector.snapshot()
        colector.snapshot()
        colector.snapshot()
        self.assertEqual(Estatico.veces, 2)


class TestNvmlNoLaDespierta(unittest.TestCase):
    ARBOL = {
        "/sys/bus/pci/devices/0000:00:02.0/vendor": "0x8086",
        "/sys/bus/pci/devices/0000:00:02.0/class": "0x030000",
        "/sys/bus/pci/devices/0000:00:02.0/power/runtime_status": "active",
        "/sys/bus/pci/devices/0000:01:00.0/vendor": "0x10de",
        "/sys/bus/pci/devices/0000:01:00.0/class": "0x030200",
        "/sys/bus/pci/devices/0000:01:00.0/power/runtime_status": "suspended",
        # Su función de sonido duerme igual y no es una gráfica.
        "/sys/bus/pci/devices/0000:01:00.1/vendor": "0x10de",
        "/sys/bus/pci/devices/0000:01:00.1/class": "0x040300",
        "/sys/bus/pci/devices/0000:01:00.1/power/runtime_status": "suspended",
    }

    def test_encuentra_la_nvidia_dormida(self):
        with arbol(self.ARBOL):
            self.assertEqual(nvidia.nvidias_dormidas(), ["0000:01:00.0"])

    def test_no_se_abre_nvml_y_se_suelta_si_estaba_abierta(self):
        proveedor = nvidia.NvidiaGpus.__new__(nvidia.NvidiaGpus)
        proveedor.client = mock.Mock()
        with mock.patch.object(nvidia.sysroot, "activo", return_value=False), \
                mock.patch.object(nvidia, "nvidias_dormidas", return_value=["0000:01:00.0"]):
            self.assertFalse(proveedor.available())
        proveedor.client.open.assert_not_called()
        proveedor.client.close.assert_called_once()


class TestSeDiceEnPantalla(unittest.TestCase):
    def test_en_reposo_con_lo_ultimo_que_se_supo(self):
        gpu = Gpu(suspended=True, last_awake_s=0.0, last_temp_c=41.0)
        texto = render.gpu_asleep(gpu)
        self.assertIn("reposo", texto)
        self.assertIn("41.0 °C", texto)

    def test_despierta_no_dice_nada(self):
        self.assertEqual(render.gpu_asleep(Gpu()), "")

    def test_la_pagina_lo_pone_arriba(self):
        from tests import qt
        from silux.ui import theme
        from silux.ui.pages.graphics import GraphicsPage
        from silux.settings import Preferences
        app = qt.app()
        pagina = GraphicsPage(theme.palette_for(app, "dark"), Preferences().normalized())
        borrador = Draft()
        borrador.gpu(0).update(name="RX 6600M", integrated=False, suspended=True)
        pagina.apply(borrador.freeze())
        seccion = pagina._sections[0]
        self.assertIn("reposo", seccion.recorte.text())
        self.assertFalse(seccion.recorte.isHidden())


if __name__ == "__main__":
    unittest.main()


class TestANvidiaThatFallsAsleep(BancoDrm):
    """A tester's laptop: its RTX 4050 was awake when the static pass read it,
    and asleep afterwards. The page said «Falta un driver» and the report
    «falta un módulo del kernel»: NVML is closed on purpose so as not to wake
    it, and the driver was there all along."""

    def setUp(self):
        super().setUp()
        self.dispositivo = self.tarjeta(
            1, ranura="0000:01:00.0", vendor="0x10de", device="0x28e1",
            subsystem_vendor="0x17aa", subsystem_device="0x3c90",
            **{"class": "0x030000"}, max_link_speed="16.0 GT/s PCIe",
            max_link_width="8")
        controlador = self.root / "drivers" / "nvidia"
        controlador.mkdir(parents=True)
        (self.dispositivo.resolve() / "driver").symlink_to(controlador)
        _write(self.dispositivo / "power" / "runtime_status", "active")

    def test_asleep_it_is_said_so_and_not_that_a_driver_is_missing(self):
        draft = Draft()
        drm.DrmGpus().collect(draft)
        self.assertTrue([n for n in draft.notes if n.need.value == "driver"])
        _write(self.dispositivo / "power" / "runtime_status", "suspended")
        drm.GpuState().collect(draft)
        notas = [n for n in draft.notes if n.path == "gpus.0"]
        self.assertEqual([n.need.value for n in notas], ["hardware"])
        self.assertIn("reposo", notas[0].message)


class TestTheBoardPageDoesNotPutItInTheProcessor(unittest.TestCase):

    def test_a_sleeping_card_is_asleep_not_integrated(self):
        import dataclasses

        from silux.i18n import _
        from silux.settings import Preferences
        from silux.ui import theme
        from silux.ui.pages.board import BoardPage
        from tests import qt
        from tests.test_equipos import EQUIPOS, foto

        app = qt.app()
        f = foto(EQUIPOS / "5800x3d")[0]
        # Asleep: no link read for it, on the PCI table or on its card.
        gpu = dataclasses.replace(f.gpus[0], suspended=True)
        pci = tuple(dataclasses.replace(d, link=None) if d.slot == gpu.pci_slot else d
                    for d in f.pci_devices)
        pagina = BoardPage(theme.palette_for(app, "dark"), Preferences())
        self.addCleanup(pagina.deleteLater)
        pagina.apply(dataclasses.replace(f, gpus=(gpu,), pci_devices=pci))
        fila = next(i for i, d in enumerate(sorted(pci, key=lambda d: d.kind != "gpu"))
                    if d.slot == gpu.pci_slot)
        self.assertEqual(pagina.pci._cells[fila][2].full_text(), _("board.pci.asleep"))
