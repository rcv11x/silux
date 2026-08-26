"""Las NVIDIA con el driver propietario.

Aquí hay una limitación honesta: no hay ninguna NVIDIA en la máquina donde se
escribió esto, así que lo que se prueba es todo lo que rodea a la llamada —el
casado con la tarjeta que ya enumeró DRM, la traducción de la dirección PCI,
los motivos de recorte, el respeto por lo que ya venía de sysfs— y no la
llamada en sí. El día que alguien ejecute esto con una tarjeta puesta, conviene
contrastar las cifras con `nvidia-smi -q`.
"""

import unittest
from unittest import mock

from cpuz import nvml
from cpuz.model import GpuClocks, GpuLink, GpuMemory
from cpuz.providers import nvidia
from cpuz.providers.base import Draft

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


if __name__ == "__main__":
    unittest.main()
