"""Una APU de AMD no enseña como de la gráfica lo que es del procesador.

- `power1` de hwmon en una APU es el PPT del encapsulado: amdgpu_pm.c lo
  etiqueta «PPT» y lo lee de AMDGPU_PP_SENSOR_GPU_INPUT_POWER, que en las APU
  devuelve `SocketPower` del SMU (smu_v13_0_4_ppt.c, yellow_carp_ppt.c).
- En `gpu_metrics_v2_1` (kgd_pp_interface.h), `temperature_soc` es la del
  SoC y `average_socket_power` la del encapsulado.
- Que es una APU lo dice el ioctl: amdgpu_kms.c pone AMDGPU_IDS_FLAGS_FUSION
  cuando `adev->flags & AMD_IS_APU`.
"""

import struct
import unittest
from unittest import mock

from silux import amdgpu, gpumetrics
from silux.providers import drm
from silux.providers.base import Draft
from tests.test_gpu import BancoDrm, _write


def tabla_v2_1(**campos) -> bytes:
    datos = bytearray(120)
    struct.pack_into("<HBB", datos, 0, 120, 2, 1)
    sitios = {"temperature_gfx": 4, "temperature_soc": 6, "socket_power": 40}
    for nombre, valor in campos.items():
        struct.pack_into("<H", datos, sitios[nombre], valor)
    return bytes(datos)


class TestLaTelemetria(unittest.TestCase):
    def test_la_del_soc_no_es_un_punto_caliente(self):
        medidas = gpumetrics.parse(tabla_v2_1(temperature_gfx=4210, temperature_soc=5530))
        self.assertAlmostEqual(medidas.temp_edge_c, 42.1)
        self.assertIsNone(medidas.temp_hotspot_c)

    def test_el_encapsulado_no_es_el_consumo_de_la_grafica(self):
        self.assertIsNone(gpumetrics.parse(tabla_v2_1(socket_power=28)).socket_power_w)


class TestElHwmonDeUnaApu(BancoDrm):
    def setUp(self):
        super().setUp()
        self.dispositivo = self.tarjeta(
            0, ranura="0000:c4:00.0", vendor="0x1002", device="0x15bf",
            **{"class": "0x030000"}, gpu_busy_percent="3")
        (self.root / "amdgpu").mkdir()
        (self.dispositivo / "driver").symlink_to(self.root / "amdgpu")
        _write(self.dispositivo / "drm" / "renderD128" / "dev", "226:128")
        hwmon = self.dispositivo / "hwmon" / "hwmon4"
        for nombre, valor in (("temp1_label", "edge"), ("temp1_input", "42000"),
                              ("power1_label", "PPT"), ("power1_input", "28000000"),
                              ("power1_cap", "54000000")):
            _write(hwmon / nombre, valor)

    def recolectar_apu(self, es_apu: bool):
        respuesta = amdgpu.DeviceInfo(device_id=0x15BF, is_apu=es_apu)
        real = drm.sysroot.a_traves

        def ioctl(espacio, clave, fn, *args, **kwargs):
            if espacio == "amdgpu":
                return respuesta
            return real(espacio, clave, fn, *args, **kwargs)
        with mock.patch.object(drm.sysroot, "a_traves", ioctl), \
                mock.patch.object(drm.amdgpu, "render_node", return_value="/dev/dri/renderD128"):
            draft = Draft()
            drm.DrmGpus().collect(draft)
        drm.GpuState().collect(draft)
        return draft.gpus[0]

    def test_sin_consumo_ni_tope(self):
        gpu = self.recolectar_apu(True)
        self.assertTrue(gpu["integrated"])
        self.assertIsNone(gpu["power_w"])
        self.assertIsNone(gpu["power_cap_w"])
        self.assertEqual(gpu["temp_c"], 42.0)

    def test_una_dedicada_lo_sigue_teniendo(self):
        gpu = self.recolectar_apu(False)
        self.assertEqual(gpu["power_w"], 28.0)


class TestLaPagina(unittest.TestCase):
    def test_se_esconde_y_se_dice_al_pie(self):
        from silux.settings import Preferences
        from silux.ui import theme
        from silux.ui.pages.graphics import GraphicsPage
        from silux.i18n import _
        from tests import qt
        app = qt.app()
        pagina = GraphicsPage(theme.palette_for(app, "dark"), Preferences().normalized())
        borrador = Draft()
        borrador.gpu(0).update(name="Radeon 780M", vendor="AMD", driver="amdgpu",
                               integrated=True, temp_c=42.0)
        pagina.apply(borrador.freeze())
        seccion = pagina._sections[0]
        self.assertTrue(seccion.tile_power.isHidden())
        self.assertFalse(seccion.tile_temp.isHidden())
        self.assertIn(_("gpu.na.apu"), seccion.sensors_pie.text() + seccion.sensors_outside.toolTip())


if __name__ == "__main__":
    unittest.main()
