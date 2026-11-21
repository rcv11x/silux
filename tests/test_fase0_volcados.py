"""La fase 0 de la revisión de gráficas: lo que los volcados tienen que traer.

- NVML se graba por `sysroot.recorded`, como los ioctl, y sin el número de
  serie; un volcado con NVIDIA se reproduce sin la NVML de quien lo lee.
- De cada gráfica despierta se copian los archivos de `xe` del nodo PCI
  (`tile*/gt*/freq0`, `gtidle`; Documentation/ABI/testing/sysfs-driver-xe),
  su hwmon entero, el enlace de cada puente de su cadena y el tipo, formato
  y eventos de cada PMU de `/sys/bus/event_source/devices`
  (Documentation/ABI/testing/sysfs-bus-event_source-devices-*).
"""

import json
import os
import pathlib
import sys
import unittest
from unittest import mock

from silux import nvml, sysroot
from silux.providers import nvidia
from silux.providers.base import Draft
from tests.arbol import arbol

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from silux import volcado as volcar_equipo  # noqa: E402

RTX = nvml.NvidiaGpu(pci_slot="0000:01:00.0", name="GeForce RTX 3060",
                     serial="1324021234567", uuid="GPU-1b2c3d4e-0000-1111-2222-333344445555",
                     temp_c=41.0, throttle_reasons=("inactiva",))


class TestNvmlSeGraba(unittest.TestCase):
    def proveedor(self, cliente):
        p = nvidia.NvidiaGpus.__new__(nvidia.NvidiaGpus)
        p.client = cliente
        return p

    def test_se_graba_sin_numero_de_serie_y_se_reproduce(self):
        sysroot.start_recording()
        try:
            vivo = self.proveedor(mock.Mock(open=lambda: True, devices=lambda: [RTX]))
            with mock.patch.object(nvidia, "sleeping_nvidias", return_value=[]):
                self.assertTrue(vivo.available())
            vivo.collect(Draft())
        finally:
            grabado = sysroot.recorded_data()
        self.assertTrue(grabado["nvml"]["abierta"])
        self.assertIsNone(grabado["nvml"]["tarjetas"][0]["serial"])

        with arbol({"/grabado.json": json.dumps(grabado)}):
            def no(*_a):
                raise AssertionError("se ha preguntado a la NVML de este equipo")
            leido = self.proveedor(mock.Mock(open=no, devices=no))
            self.assertTrue(leido.available())
            draft = Draft()
            draft.gpu(0)["pci_slot"] = "0000:01:00.0"
            leido.collect(draft)
        self.assertEqual(draft.gpus[0]["name"], "GeForce RTX 3060")
        self.assertEqual(draft.gpus[0]["temp_c"], 41.0)

    def test_un_volcado_sin_nvidia_no_la_tiene(self):
        with arbol({"/proc/version": "Linux"}):
            p = self.proveedor(mock.Mock(open=lambda: True))
            self.assertFalse(p.available())


class TestLoQueSeCopiaDeMas(unittest.TestCase):
    RAMA = "/sys/devices/pci0000:00/0000:00:01.0/0000:01:00.0/0000:02:01.0/0000:03:00.0"

    def test_xe_los_puentes_y_event_source(self):
        archivos = {
            f"{self.RAMA}/vendor": "0x8086", f"{self.RAMA}/class": "0x030000",
            f"{self.RAMA}/power/runtime_status": "active",
            f"{self.RAMA}/tile0/gt0/freq0/act_freq": "2850",
            f"{self.RAMA}/tile0/gt0/freq0/throttle/reasons": "",
            f"{self.RAMA}/tile0/gt0/gtidle/idle_residency_ms": "1234",
            f"{self.RAMA}/hwmon/hwmon6/temp2_label": "pkg",
            "/sys/devices/pci0000:00/0000:00:01.0/current_link_speed": "16.0 GT/s PCIe",
            "/sys/devices/pci0000:00/0000:00:01.0/0000:01:00.0/current_link_width": "16",
            "/sys/bus/event_source/devices/xe_0000_03_00.0/type": "42",
            "/sys/bus/event_source/devices/xe_0000_03_00.0/format/gt": "config:60-63",
            "/sys/bus/event_source/devices/xe_0000_03_00.0/events/engine-active-ticks": "event=0x02",
        }
        with arbol(archivos) as raiz:
            enlace = raiz / "sys/bus/pci/devices/0000:03:00.0"
            enlace.parent.mkdir(parents=True, exist_ok=True)
            enlace.symlink_to(raiz / self.RAMA.lstrip("/"))
            extras = volcar_equipo._gpu_extras()
        for camino in (f"{self.RAMA}/tile0/gt0/freq0/act_freq",
                       f"{self.RAMA}/tile0/gt0/freq0/throttle/reasons",
                       f"{self.RAMA}/tile0/gt0/gtidle/idle_residency_ms",
                       f"{self.RAMA}/hwmon/hwmon6/temp2_label",
                       "/sys/devices/pci0000:00/0000:00:01.0/current_link_speed",
                       "/sys/devices/pci0000:00/0000:00:01.0/0000:01:00.0/current_link_width",
                       "/sys/bus/event_source/devices/xe_0000_03_00.0/format/gt",
                       "/sys/bus/event_source/devices/xe_0000_03_00.0/events/engine-active-ticks"):
            with self.subTest(camino):
                self.assertIn(camino, extras)

    def test_de_una_dormida_nada(self):
        archivos = {f"{self.RAMA}/vendor": "0x10de", f"{self.RAMA}/class": "0x030200",
                    f"{self.RAMA}/power/runtime_status": "suspended",
                    f"{self.RAMA}/hwmon/hwmon6/temp1_input": "41000",
                    "/sys/devices/pci0000:00/0000:00:01.0/current_link_speed": "16.0 GT/s PCIe"}
        with arbol(archivos) as raiz:
            enlace = raiz / "sys/bus/pci/devices/0000:03:00.0"
            enlace.parent.mkdir(parents=True, exist_ok=True)
            enlace.symlink_to(raiz / self.RAMA.lstrip("/"))
            extras = volcar_equipo._gpu_extras()
        self.assertFalse(any(c.startswith("/sys/devices") for c in extras), extras)


if __name__ == "__main__":
    unittest.main()


class TestUnEnlaceQueNoSeDejaLeer(unittest.TestCase):
    def test_no_tumba_el_volcado(self):
        """`/proc/1/exe`: con Python 3.10, realpath deja escapar el
        PermissionError de leer el enlace; el volcado entero se caía."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            copia = volcar_equipo._Copy(pathlib.Path(tmp))
            with mock.patch.object(volcar_equipo.os.path, "realpath",
                                   side_effect=PermissionError(13, "Permission denied")):
                copia._from_outside("/proc/1/exe")
