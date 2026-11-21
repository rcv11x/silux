"""Las NVIDIA con el driver propietario.

Aquí hay una limitación honesta: no hay ninguna NVIDIA en la máquina donde se
escribió esto, así que lo que se prueba es todo lo que rodea a la llamada —el
casado con la tarjeta que ya enumeró DRM, la traducción de la dirección PCI,
los motivos de recorte, el respeto por lo que ya venía de sysfs— y no la
llamada en sí. El día que alguien ejecute esto con una tarjeta puesta, conviene
contrastar las cifras con `nvidia-smi -q`.
"""

import dataclasses
import unittest
from unittest import mock

from silux import nvml
from silux.model import GpuClocks, PcieLink, GpuMemory
from silux.providers import nvidia
from silux.providers.base import Draft
from tests import pantalla, qt

UNA_4070 = nvml.NvidiaGpu(
    index=0, pci_slot="0000:01:00.0", name="NVIDIA GeForce RTX 4070",
    vbios="95.04.3a.40.71", driver_version="580.65.06",
    uuid="GPU-1234abcd", cuda_cores=5888,
    memory_total_bytes=12 * 1024**3, memory_used_bytes=2 * 1024**3,
    memory_bus_bits=192, busy_percent=31.0, memory_busy_percent=12.0,
    temp_c=54.0, power_w=110.5, power_cap_w=200.0, fan_percent=42.0,
    core_hz=2_505_000_000, core_max_hz=2_610_000_000,
    memory_hz=1_313_000_000, memory_max_hz=1_313_000_000,
    link_generation=4, link_width=16, max_link_generation=4, max_link_width=16,
    throttled=False,
)


def recolectar(gpus, tarjetas=(UNA_4070,)) -> Draft:
    draft = Draft()
    for indice, campos in enumerate(gpus):
        draft.gpu(indice).update(campos)
    proveedor = nvidia.NvidiaGpus()
    with mock.patch.object(proveedor.client, "devices", lambda: list(tarjetas)):
        proveedor.collect(draft)
    return draft


class TestDireccionPci(unittest.TestCase):
    """NVML y sysfs escriben la misma dirección de dos formas distintas."""

    def test_normaliza_el_formato_de_nvml(self):
        self.assertEqual(nvml._ranura("00000000:0C:00.0"), "0000:0c:00.0")
        self.assertEqual(nvml._ranura("00000000:01:00.0"), "0000:01:00.0")

    def test_un_dominio_que_no_es_cero(self):
        # El dominio va en ocho dígitos hexadecimales; sysfs lo escribe en
        # cuatro salvo que no quepa, como en las máquinas con muchos buses.
        self.assertEqual(nvml._ranura("00000001:01:00.0"), "0001:01:00.0")
        self.assertEqual(nvml._ranura("00010000:01:00.0"), "10000:01:00.0")

    def test_algo_que_no_es_una_direccion(self):
        self.assertIsNone(nvml._ranura("no soy una dirección"))
        self.assertIsNone(nvml._ranura(""))


class TestMotivosDeRecorte(unittest.TestCase):
    def test_el_reposo_no_es_un_recorte(self):
        # El bit 0 significa «la tarjeta está parada», que es lo normal y no
        # tiene nada que ver con que la estén frenando.
        self.assertEqual(nvml._motivos(0x01), ())

    def test_temperatura_y_potencia(self):
        motivos = nvml._motivos(0x04 | 0x40)
        self.assertIn("límite de potencia del driver", motivos)
        self.assertIn("temperatura (hardware)", motivos)


class TestCasado(unittest.TestCase):
    def test_completa_la_tarjeta_que_drm_dejo_vacia(self):
        draft = recolectar([{"pci_slot": "0000:01:00.0", "vendor": "NVIDIA",
                             "driver": "nvidia", "name": "AD104 [GeForce RTX 4070]"}])
        gpu = draft.gpus[0]
        self.assertEqual(gpu["vbios"], "95.04.3a.40.71")
        self.assertEqual(gpu["compute_units"], 5888)
        self.assertEqual(gpu["temp_c"], 54.0)
        self.assertEqual(gpu["memory"].total_bytes, 12 * 1024**3)
        self.assertEqual(gpu["memory"].bus_bits, 192)

    def test_no_pisa_lo_que_ya_sabia_sysfs(self):
        # Con nouveau algunos datos sí están, y son los del kernel.
        draft = recolectar([{"pci_slot": "0000:01:00.0", "temp_c": 49.0,
                             "name": "GeForce RTX 4070 de sysfs"}])
        gpu = draft.gpus[0]
        self.assertEqual(gpu["temp_c"], 49.0)
        self.assertEqual(gpu["name"], "GeForce RTX 4070 de sysfs")

    def test_the_vram_is_nvmls_and_not_vulkans_sum(self):
        # A tester's RTX 4060 read «8.2 GB»: Vulkan, asked before NVML, adds
        # NVIDIA's BAR window (a host-visible heap inside the same memory) to
        # the 8188 MiB, and that sum stayed. NVML's figure is the card's.
        vulkan = GpuMemory(total_bytes=(8188 + 228) * 1024 ** 2)
        tarjeta = dataclasses.replace(UNA_4070, memory_total_bytes=8188 * 1024 ** 2)
        draft = recolectar([{"pci_slot": "0000:01:00.0", "memory": vulkan}], (tarjeta,))
        self.assertEqual(draft.gpus[0]["memory"].total_bytes, 8188 * 1024 ** 2)

    def test_traduce_la_generacion_de_pcie_a_gigatransferencias(self):
        draft = recolectar([{"pci_slot": "0000:01:00.0"}])
        enlace = draft.gpus[0]["link"]
        self.assertEqual(enlace.current_speed_gts, 16.0)
        self.assertEqual(enlace.generation, 4)

    def test_no_toca_una_tarjeta_de_otro_fabricante(self):
        draft = recolectar([{"pci_slot": "0000:0c:00.0", "vendor": "AMD"},
                            {"pci_slot": "0000:01:00.0", "vendor": "NVIDIA"}])
        self.assertIsNone(draft.gpus[0].get("vbios"))
        self.assertEqual(draft.gpus[1]["vbios"], "95.04.3a.40.71")

    def test_una_tarjeta_que_nvml_ve_y_drm_no(self):
        # Las Tesla en modo de solo cómputo no registran nodo de gráficos.
        draft = recolectar([])
        self.assertEqual(len(draft.gpus), 1)
        self.assertEqual(draft.gpus[0]["vendor"], "NVIDIA")
        self.assertEqual(draft.gpus[0]["pci_slot"], "0000:01:00.0")

    def test_se_anuncia_como_fuente(self):
        self.assertIn("nvml", recolectar([{"pci_slot": "0000:01:00.0"}]).capabilities)

    def test_una_tarjeta_con_memoria_es_dedicada(self):
        draft = recolectar([{"pci_slot": "0000:01:00.0"}])
        self.assertFalse(draft.gpus[0]["integrated"])


class TestNucleosCuda(unittest.TestCase):
    """Las tres cifras vienen de capturas de tres equipos ajenos.

    NVML contesta a `nvmlDeviceGetNumGpuCores` una cosa distinta según la
    tarjeta: unas veces los núcleos y otras los multiprocesadores. Entre las
    dos magnitudes hay un hueco enorme, que es lo que permite distinguirlas.
    """

    def test_una_3050_mobile_da_multiprocesadores(self):
        gpu = {"codename": "GA107M"}
        self.assertEqual(nvidia._nucleos_cuda(gpu, 16), 2048)

    def test_una_4080_laptop_tambien(self):
        gpu = {"codename": "AD104M"}
        self.assertEqual(nvidia._nucleos_cuda(gpu, 58), 7424)

    def test_una_1660_ti_da_los_nucleos_de_verdad(self):
        """1536 ya son núcleos: no hay nada que multiplicar."""
        gpu = {"codename": "TU116"}
        self.assertEqual(nvidia._nucleos_cuda(gpu, 1536), 1536)

    def test_una_arquitectura_que_no_se_reconoce_no_se_inventa(self):
        gpu = {"codename": "XX999"}
        self.assertIsNone(nvidia._nucleos_cuda(gpu, 16))

    def test_sin_nombre_en_clave_tampoco(self):
        self.assertIsNone(nvidia._nucleos_cuda({}, 16))


class TestSinNvidia(unittest.TestCase):
    def test_sin_tarjetas_no_toca_nada(self):
        draft = recolectar([{"pci_slot": "0000:0c:00.0", "vendor": "AMD"}], tarjetas=())
        self.assertNotIn("nvml", draft.capabilities)
        self.assertEqual(draft.gpus[0], {"index": 0, "pci_slot": "0000:0c:00.0",
                                         "vendor": "AMD"})

    def test_sin_la_biblioteca_el_proveedor_se_declara_no_disponible(self):
        proveedor = nvidia.NvidiaGpus()
        with mock.patch.object(nvml.ctypes, "CDLL", side_effect=OSError("no está")):
            self.assertFalse(proveedor.available())
        # Y no deja nota: sin una NVIDIA delante no falta nada que explicar.
        self.assertIsNone(proveedor.unavailable_reason())


class TestSesion(unittest.TestCase):
    def test_cerrar_sin_haber_abierto_no_revienta(self):
        nvml.Nvml().close()

    def test_pedir_dispositivos_sin_abrir_devuelve_vacio(self):
        self.assertEqual(nvml.Nvml().devices(), [])


class _Nvml:
    """libnvidia-ml as nvml.h (NVML 13.4.92) describes these two calls:
    the power usage call answers NOT_SUPPORTED (3) where power management
    mode is not, and each field value carries its own return code."""

    def __init__(self, uso=None, campos=None):
        self.uso, self.campos, self.pedidos = uso, campos or {}, []

    def nvmlDeviceGetPowerUsage(self, asa, valor):
        if self.uso is None:
            return 3
        valor._obj.value = self.uso
        return 0

    def nvmlDeviceGetFieldValues(self, asa, cuantos, campos):
        for campo in campos[:cuantos.value]:
            self.pedidos.append(campo.fieldId)
            if campo.fieldId in self.campos:
                campo.nvmlReturn, campo.valueType = 0, 1
                campo.value.uiVal = self.campos[campo.fieldId]
            else:
                campo.nvmlReturn = 3
        return 0


class _NvmlWithSamples(_Nvml):
    """A desktop RTX 4060 with driver 595, as `nvidia-smi -q -d POWER` showed
    it: no power usage, no power fields, and the power samples buffer (119
    samples between 52.59 and 55.37 W, 53.11 on average)."""

    SAMPLES = [52590] * 60 + [53000] * 50 + [55370] * 9

    def __init__(self, **kw):
        super().__init__(**kw)
        self.since = []

    def nvmlDeviceGetSamples(self, asa, kind, last_seen, value_type, count, samples):
        self.since.append(last_seen.value)
        value_type._obj.value = 1                    # unsigned int
        if samples is None:
            count._obj.value = len(self.SAMPLES)
            return 0
        for i, mw in enumerate(self.SAMPLES[:count._obj.value]):
            samples[i].timeStamp = 1000 + i
            samples[i].sampleValue.uiVal = mw
        return 0


class TestThePowerSamples(unittest.TestCase):
    """Neither the power usage nor the fields answer: the mean of the power
    samples since the last reading, as nvidia-smi does."""

    def _session(self, lib):
        sesion = nvml.Nvml()
        sesion._lib = lib
        return sesion

    def test_the_mean_of_its_samples(self):
        lib = _NvmlWithSamples()
        watts, reason = self._session(lib)._potencia(nvml.ctypes.c_void_p(1), 0)
        media = sum(_NvmlWithSamples.SAMPLES) / len(_NvmlWithSamples.SAMPLES) / 1000
        self.assertEqual(watts, round(media, 1))
        self.assertIsNone(reason)

    def test_the_next_reading_asks_only_for_new_samples(self):
        lib = _NvmlWithSamples()
        sesion = self._session(lib)
        sesion._potencia(nvml.ctypes.c_void_p(1), 0)
        sesion._potencia(nvml.ctypes.c_void_p(1), 0)
        self.assertEqual(lib.since[0], 0)
        self.assertEqual(lib.since[-1], 1000 + len(_NvmlWithSamples.SAMPLES) - 1)


class _OldDriver:
    """A driver from before most calls: only these exist, and the rest are
    missing symbols. Nothing may break; what is missing stays empty."""

    def nvmlInit_v2(self):
        return 0

    def nvmlShutdown(self):
        return 0

    def nvmlDeviceGetCount_v2(self, count):
        count._obj.value = 1
        return 0

    def nvmlDeviceGetHandleByIndex_v2(self, index, handle):
        handle._obj.value = 1
        return 0

    def nvmlDeviceGetName(self, handle, buffer, size):
        buffer.value = b"GeForce GTX 680"
        return 0

    def nvmlDeviceGetTemperature(self, handle, sensor, value):
        value._obj.value = 40
        return 0


class TestAnOldDriver(unittest.TestCase):

    def test_missing_calls_leave_their_value_empty(self):
        sesion = nvml.Nvml()
        sesion._lib = _OldDriver()
        sesion._activa = True
        tarjetas = sesion.devices()
        self.assertEqual(len(tarjetas), 1)
        self.assertEqual(tarjetas[0].temp_c, 40.0)
        self.assertIsNone(tarjetas[0].power_w)
        self.assertIsNone(tarjetas[0].power_cap_max_w)
        self.assertIn("not in the library", tarjetas[0].power_error)


class TestItsPowerLimits(unittest.TestCase):

    def test_current_default_minimum_and_maximum(self):
        class _Limits(_NvmlWithSamples):
            def nvmlDeviceGetPowerManagementLimitConstraints(self, asa, low, high):
                low._obj.value, high._obj.value = 90000, 115000
                return 0

            def nvmlDeviceGetPowerManagementDefaultLimit(self, asa, value):
                value._obj.value = 115000
                return 0

        sesion = nvml.Nvml()
        sesion._lib = _Limits()
        limites = sesion._limits(nvml.ctypes.c_void_p(1))
        self.assertEqual(limites, {"power_cap_default_w": 115.0, "power_cap_min_w": 90.0,
                                   "power_cap_max_w": 115.0})


class TestThePowerOfANewDriver(unittest.TestCase):
    """A desktop RTX 4060 with driver 595: temperature, clocks and limit, and
    «Consumo: —». nvmlDeviceGetPowerUsage only answers where power
    management mode is supported; the header points to the power fields."""

    def _leer(self, lib):
        sesion = nvml.Nvml()
        sesion._lib = lib
        return sesion._potencia(nvml.ctypes.c_void_p(1), 0)

    def _potencia(self, lib):
        return self._leer(lib)[0]

    def test_the_seconds_average_where_the_old_call_does_not_answer(self):
        self.assertEqual(self._potencia(_Nvml(campos={185: 15234, 186: 17000})), 15.2)

    def test_or_the_current_one(self):
        self.assertEqual(self._potencia(_Nvml(campos={186: 9800})), 9.8)

    def test_without_either_there_is_none(self):
        self.assertIsNone(self._potencia(_Nvml()))

    def test_without_either_it_keeps_what_nvml_answered(self):
        # The same card in prueba5: neither way gave it, and nothing said why.
        _vatios, motivo = self._leer(_Nvml())
        self.assertEqual(motivo, "nvmlDeviceGetPowerUsage: NVML_ERROR_NOT_SUPPORTED (3); "
                                 "field 185: NVML_ERROR_NOT_SUPPORTED (3); "
                                 "field 186: NVML_ERROR_NOT_SUPPORTED (3); "
                                 "nvmlDeviceGetSamples: not in the library")
        self.assertIsNone(self._leer(_Nvml(uso=12000))[1])

    def test_its_page_says_the_driver_does_not_give_it(self):
        from silux.i18n import _
        from tests.test_equipos import EQUIPOS, foto
        f = foto(EQUIPOS / "i7-10700f")[0]
        nota = next(n for n in f.notes if n.path == "gpus.0.power_w")
        self.assertEqual(nota.message, _("prov.nvml.nopower"))
        qt.app()
        with pantalla.Ventana(f) as ventana:
            ventana.select_section("Gráficos")
            self.assertIn(_("prov.nvml.nopower"),
                          " ".join(pantalla.textos_de(ventana.stack.currentWidget())))

    def test_where_the_old_call_answers_the_fields_are_not_asked(self):
        lib = _Nvml(uso=12000, campos={185: 99000})
        self.assertEqual(self._potencia(lib), 12.0)
        self.assertEqual(lib.pedidos, [])


class TestTheDesktopRtx4060WithItsSamples(unittest.TestCase):
    """What the new code records on that desktop: the power from the
    samples, and the limits nvidia-smi showed (115 W, from 90 to 115)."""

    def test_its_power_and_limits_on_the_page(self):
        import json
        from silux import render, sysroot, volcado
        from silux.collector import Collector
        from silux.i18n import _
        from tests.interval import second_snapshot
        from tests.test_equipos import EQUIPOS

        with volcado.montado(EQUIPOS / "i7-10700f") as raiz:
            ruta = raiz / "grabado.json"
            grabado = json.loads(ruta.read_text())
            grabado["nvml"]["tarjetas"][0].update(
                power_w=53.0, power_error=None, power_cap_default_w=115.0,
                power_cap_min_w=90.0, power_cap_max_w=115.0)
            ruta.write_text(json.dumps(grabado))
            sysroot.olvidar()
            recolector = Collector()
            try:
                f = second_snapshot(recolector)
            finally:
                recolector.close()
        gpu = f.gpus[0]
        self.assertEqual((gpu.power_w, gpu.power_cap_default_w, gpu.power_cap_min_w,
                          gpu.power_cap_max_w), (53.0, 115.0, 90.0, 115.0))
        self.assertFalse([n for n in f.notes if n.path == "gpus.0.power_w"])
        qt.app()
        with pantalla.Ventana(f) as ventana:
            ventana.select_section("Gráficos")
            textos = pantalla.textos_de(ventana.stack.currentWidget())
        self.assertIn(render.gpu_factory_power_limit(gpu), textos)
        self.assertIn(_("gpu.sensor.powercap"), textos)
        self.assertNotIn(_("prov.nvml.nopower"), " ".join(textos))


class TestAProprietaryNvidiaInSensors(unittest.TestCase):
    """Its driver has no hwmon: temperature and clocks come from NVML, and
    the sensor tree had none of them (a desktop RTX 4060)."""

    def test_its_temperature_and_clocks_are_there(self):
        import pathlib
        from silux.model import SensorKind
        from tests.test_equipos import EQUIPOS, foto
        f = foto(EQUIPOS / "i7-10700f")[0]
        nvidia_ = {(s.kind, s.label): s.value for s in f.sensors if s.device == "GeForce RTX 4060"}
        self.assertEqual(nvidia_[(SensorKind.TEMPERATURE, "Núcleo")], 37.0)
        self.assertEqual(nvidia_[(SensorKind.CLOCK, "Núcleo")], 2505.0)

    def test_an_amd_card_does_not_get_them_twice(self):
        # Its hwmon already gives them.
        from tests.test_equipos import EQUIPOS, foto
        f = foto(EQUIPOS / "5800x3d")[0]
        self.assertFalse([s.key for s in f.sensors if s.chip == "drm" and
                          s.key.split("/")[-1] in ("temp", "power", "clk_core", "clk_mem")])


if __name__ == "__main__":
    unittest.main()
