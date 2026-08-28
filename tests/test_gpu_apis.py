"""OpenGL, Vulkan y OpenCL colgados de la tarjeta que les toca.

Vulkan publica el identificador PCI y se casa sin ambigüedad. OpenGL y OpenCL
no dicen a qué nodo pertenecen, pero sí dicen quién contesta, y eso basta para
no colgárselas a la tarjeta equivocada.
"""

import json
import subprocess
import unittest
from unittest import mock

from silux import gpuapi
from silux.providers import gpu_apis
from silux.providers.base import Draft

VULKAN_AMD = {
    "name": "AMD Radeon RX 9070 XT (RADV GFX1201)",
    "api_version": "1.4.354", "instance_version": "1.4.357",
    "driver_version": 109060097, "vendor_id": 0x1002, "device_id": 0x7550,
    "kind": "dedicada",
}
OPENGL = {
    "version": "4.6 (Compatibility Profile) Mesa 26.2.1-arch3.1",
    "renderer": "AMD Radeon RX 9070 XT (radeonsi, gfx1201, ACO)",
    "vendor": "AMD", "glsl": "4.60", "egl_version": "1.5", "egl_vendor": "Mesa Project",
}
OPENCL = {
    "platform": "rusticl", "platform_version": "OpenCL 3.1",
    "name": "AMD Radeon RX 9070 XT", "vendor": "AMD", "version": "OpenCL 3.1",
    "driver_version": "26.2.1-arch3.1", "compute_units": 64,
    "max_clock_mhz": 2520, "global_memory_bytes": 17179869184,
}


def _recolectar(gpus, vulkan=(), opencl=(), opengl=None) -> Draft:
    draft = Draft()
    for indice, campos in enumerate(gpus):
        draft.gpu(indice).update(campos)
    respuesta = {"vulkan": list(vulkan), "opencl": list(opencl), "opengl": opengl}
    with mock.patch.object(gpu_apis.gpuapi, "consultar", lambda: respuesta):
        gpu_apis.GpuApis().collect(draft)
    return draft


class TestCasado(unittest.TestCase):
    def test_vulkan_se_casa_por_identificador_pci(self):
        draft = _recolectar(
            [{"vendor_id": 0x8086, "device_id": 0x9BC4},
             {"vendor_id": 0x1002, "device_id": 0x7550, "primary": True}],
            vulkan=[VULKAN_AMD])
        self.assertEqual(draft.gpus[0].get("apis", ()), ())
        self.assertEqual(draft.gpus[1]["apis"][0].name, "Vulkan")

    def test_opengl_y_opencl_van_a_la_principal(self):
        draft = _recolectar(
            [{"vendor_id": 0x8086, "device_id": 0x9BC4},
             {"vendor_id": 0x1002, "device_id": 0x7550, "primary": True}],
            opengl=OPENGL, opencl=[OPENCL])
        nombres = [a.name for a in draft.gpus[1]["apis"]]
        self.assertEqual(nombres, ["OpenGL", "OpenCL"])
        self.assertNotIn("apis", draft.gpus[0])

    def test_sin_ninguna_marcada_gana_la_primera(self):
        draft = _recolectar([{"vendor_id": 0x1002, "device_id": 0x7550}], opengl=OPENGL)
        self.assertEqual(draft.gpus[0]["apis"][0].name, "OpenGL")


class TestNombreDeLaTarjeta(unittest.TestCase):
    def test_vulkan_desambigua_un_nombre_con_barras(self):
        draft = _recolectar(
            [{"vendor_id": 0x1002, "device_id": 0x7550,
              "name": "Radeon RX 9070/9070 XT/9070 GRE"}],
            vulkan=[VULKAN_AMD])
        # Y de paso se le quita la coletilla del driver.
        self.assertEqual(draft.gpus[0]["name"], "AMD Radeon RX 9070 XT")

    def test_un_nombre_concreto_no_se_toca(self):
        # El de pci.ids incluye a quien montó la tarjeta, así que es mejor.
        draft = _recolectar(
            [{"vendor_id": 0x1002, "device_id": 0x7550, "name": "Radeon RX 9070 XT 16GB"}],
            vulkan=[VULKAN_AMD])
        self.assertEqual(draft.gpus[0]["name"], "Radeon RX 9070 XT 16GB")

    def test_sin_nombre_previo_vale_el_de_vulkan(self):
        draft = _recolectar([{"vendor_id": 0x1002, "device_id": 0x7550}], vulkan=[VULKAN_AMD])
        self.assertEqual(draft.gpus[0]["name"], "AMD Radeon RX 9070 XT")


class TestVersiones(unittest.TestCase):
    def test_la_version_del_driver_de_mesa(self):
        draft = _recolectar([{"vendor_id": 0x1002, "device_id": 0x7550}], vulkan=[VULKAN_AMD])
        self.assertEqual(draft.gpus[0]["apis"][0].driver, "26.2.1")

    def test_nvidia_empaqueta_la_suya_de_otra_forma(self):
        # Con el reparto de Vulkan, 0x23DFC0C0 daría un número sin sentido.
        nvidia = dict(VULKAN_AMD, vendor_id=0x10DE, device_id=0x2684,
                      driver_version=(580 << 22) | (65 << 14) | (6 << 6))
        draft = _recolectar([{"vendor_id": 0x10DE, "device_id": 0x2684}], vulkan=[nvidia])
        self.assertEqual(draft.gpus[0]["apis"][0].driver, "580.65.6")

    def test_las_versiones_se_quedan_en_el_numero(self):
        draft = _recolectar([{"vendor_id": 0x1002, "device_id": 0x7550, "primary": True}],
                            opengl=OPENGL, opencl=[OPENCL])
        versiones = {a.name: a.version for a in draft.gpus[0]["apis"]}
        self.assertEqual(versiones, {"OpenGL": "4.6", "OpenCL": "3.1"})

    def test_las_unidades_de_computo_salen_de_opencl(self):
        draft = _recolectar([{"vendor_id": 0x1002, "device_id": 0x7550, "primary": True}],
                            opencl=[OPENCL])
        self.assertEqual(draft.gpus[0]["compute_units"], 64)


class TestCuandoFalta(unittest.TestCase):
    def test_sin_bibliotecas_se_deja_dicho(self):
        draft = _recolectar([{"vendor_id": 0x1002, "device_id": 0x7550}])
        self.assertEqual([n.path for n in draft.notes], ["gpus.apis"])
        self.assertNotIn("gpu-apis", draft.capabilities)

    def test_una_api_que_falta_no_se_lleva_a_las_otras(self):
        draft = _recolectar([{"vendor_id": 0x1002, "device_id": 0x7550, "primary": True}],
                            opengl=OPENGL)
        self.assertEqual([a.name for a in draft.gpus[0]["apis"]], ["OpenGL"])

    def test_si_la_consulta_revienta_no_se_cae_el_muestreo(self):
        def revienta():
            raise OSError("el driver se ha caído")

        draft = Draft()
        draft.gpu(0).update({"vendor_id": 0x1002, "device_id": 0x7550})
        with mock.patch.object(gpu_apis.gpuapi, "consultar", revienta):
            gpu_apis.GpuApis().collect(draft)
        self.assertEqual([n.path for n in draft.notes], ["gpus.apis"])

    def test_sin_graficas_no_hace_nada(self):
        draft = _recolectar([], opengl=OPENGL)
        self.assertEqual(draft.notes, [])


class TestConsultaEnOtroProceso(unittest.TestCase):
    """Preguntar fuera es lo que mantiene el programa dentro de sus 100 MB.

    Los drivers de las tres APIs suman 118 MB de residente, y rusticl solo,
    83 de ellos. Cargándolos aquí el presupuesto se rompía y ya no había vuelta
    atrás, así que si el proceso hijo no sale adelante se prefiere quedarse sin
    el dato antes que pagar esa memoria para siempre.
    """

    # Cada API que se añada tiene que aparecer aquí vacía: si `consultar`
    # devolviera un diccionario al que le falta una clave, quien la lea se
    # llevaría un KeyError justo en el camino de «no se pudo preguntar».
    VACIO = {"vulkan": [], "opencl": [], "opengl": None, "vaapi": []}

    def _con_subproceso(self, **resultado):
        completado = mock.Mock(**resultado)
        return mock.patch.object(subprocess, "run", lambda *a, **k: completado)

    def test_lee_el_json_del_hijo(self):
        salida = json.dumps({"vulkan": [VULKAN_AMD], "opencl": [], "opengl": OPENGL})
        with self._con_subproceso(returncode=0, stdout=salida.encode()):
            leido = gpuapi.consultar()
        self.assertEqual(leido["vulkan"][0]["device_id"], 0x7550)
        self.assertEqual(leido["opengl"]["glsl"], "4.60")

    def test_un_hijo_que_muere_no_deja_basura(self):
        # Justo lo que pasa cuando un driver roto revienta: antes se llevaba
        # por delante el proceso entero.
        with self._con_subproceso(returncode=-11, stdout=b""):
            self.assertEqual(gpuapi.consultar(), self.VACIO)

    def test_una_salida_que_no_es_json(self):
        with self._con_subproceso(returncode=0, stdout=b"Segmentation fault"):
            self.assertEqual(gpuapi.consultar(), self.VACIO)

    def test_json_que_no_es_un_diccionario(self):
        with self._con_subproceso(returncode=0, stdout=b"[1, 2, 3]"):
            self.assertEqual(gpuapi.consultar(), self.VACIO)

    def test_un_driver_colgado_no_cuelga_el_muestreo(self):
        def se_atasca(*args, **kwargs):
            raise subprocess.TimeoutExpired(cmd="silux.gpuapi", timeout=gpuapi.TIEMPO_MAXIMO)

        with mock.patch.object(subprocess, "run", se_atasca):
            self.assertEqual(gpuapi.consultar(), self.VACIO)

    def test_sin_interprete_que_lanzar(self):
        def no_existe(*args, **kwargs):
            raise OSError("no such file")

        with mock.patch.object(subprocess, "run", no_existe):
            self.assertEqual(gpuapi.consultar(), self.VACIO)

    def test_el_hijo_encuentra_el_paquete(self):
        capturado = {}

        def espia(orden, **kwargs):
            capturado["orden"] = orden
            capturado["env"] = kwargs.get("env", {})
            return mock.Mock(returncode=0, stdout=b"{}")

        with mock.patch.object(subprocess, "run", espia):
            gpuapi.consultar()
        self.assertEqual(capturado["orden"][1:], ["-m", "silux.gpuapi"])
        self.assertIn("PYTHONPATH", capturado["env"])


if __name__ == "__main__":
    unittest.main()


# El portátil de un probador: Ryzen 7 7445HS con Radeon 740M integrada y una
# RTX 3050 Mobile dedicada. El kernel marca la integrada como principal porque
# es la que lleva la pantalla, pero quien contesta a OpenGL y OpenCL es la
# NVIDIA. Los datos son los que se vieron en su captura.
IGPU_AMD = {"vendor_id": 0x1002, "device_id": 0x1901, "vendor": "AMD",
            "name": "Radeon 740M", "primary": True}
DGPU_NVIDIA = {"vendor_id": 0x10DE, "device_id": 0x25A2, "vendor": "NVIDIA",
               "name": "GeForce RTX 3050 Mobile", "compute_units": 2048}
OPENGL_NVIDIA = {
    "version": "4.6.0 NVIDIA 610.57.04",
    "renderer": "NVIDIA GeForce RTX 3050 Laptop GPU/PCIe/SSE2",
    "vendor": "NVIDIA Corporation", "glsl": "4.60 NVIDIA",
}
OPENCL_NVIDIA = {
    "platform": "NVIDIA CUDA", "name": "NVIDIA GeForce RTX 3050 Laptop GPU",
    "vendor": "NVIDIA Corporation", "version": "OpenCL 3.0",
    "driver_version": "610.57.04", "compute_units": 16,
}


class TestPortatilHibrido(unittest.TestCase):
    """Dos tarjetas de fabricantes distintos y una sola que contesta."""

    def _hibrido(self):
        return _recolectar([dict(IGPU_AMD), dict(DGPU_NVIDIA)],
                           opengl=OPENGL_NVIDIA, opencl=[OPENCL_NVIDIA])

    def test_el_opengl_de_nvidia_no_va_a_la_radeon(self):
        draft = self._hibrido()
        self.assertNotIn("apis", draft.gpus[0])

    def test_va_a_la_nvidia_aunque_no_sea_la_principal(self):
        draft = self._hibrido()
        self.assertEqual([a.name for a in draft.gpus[1]["apis"]],
                         ["OpenGL", "OpenCL"])

    def test_y_no_le_pega_a_la_radeon_las_unidades_de_la_otra(self):
        """16 unidades de cómputo son los 16 SM de la RTX 3050, no de la 740M."""
        draft = self._hibrido()
        self.assertIsNone(draft.gpus[0].get("compute_units"))

    def test_ni_pisa_las_que_ya_se_sabian(self):
        """2048 núcleos CUDA los dio NVML; OpenCL cuenta otra cosa."""
        draft = self._hibrido()
        self.assertEqual(draft.gpus[1]["compute_units"], 2048)


class TestQuienContesta(unittest.TestCase):
    def test_reconoce_a_cada_fabricante(self):
        for texto, esperado in [
            ("NVIDIA GeForce RTX 3050 Laptop GPU/PCIe/SSE2", "NVIDIA"),
            ("AMD Radeon 740M (RADV PHOENIX)", "AMD"),
            ("Mesa Intel(R) Graphics (RPL-P)", "Intel"),
            ("AMD Radeon RX 9070 XT (radeonsi, gfx1201, ACO)", "AMD"),
        ]:
            self.assertEqual(gpu_apis._fabricante_de(texto), esperado, texto)

    def test_un_rasterizador_por_software_no_es_ninguna_tarjeta(self):
        """llvmpipe contesta cuando no hay driver, y no es la tarjeta puesta."""
        self.assertEqual(gpu_apis._fabricante_de("llvmpipe (LLVM 19.1.0, 256 bits)"),
                         "software")

    def test_y_no_se_le_cuelga_a_nadie(self):
        draft = _recolectar(
            [dict(IGPU_AMD), dict(DGPU_NVIDIA)],
            opengl={"version": "4.5 (Core Profile) Mesa 26.2.1",
                    "renderer": "llvmpipe (LLVM 19.1.0, 256 bits)",
                    "vendor": "Mesa", "glsl": "4.50"})
        self.assertNotIn("apis", draft.gpus[0])
        self.assertNotIn("apis", draft.gpus[1])

    def test_lo_que_no_dice_nada_sigue_yendo_a_la_principal(self):
        self.assertIsNone(gpu_apis._fabricante_de("Generic Renderer 1.0"))


class TestMemoriaPorVulkan(unittest.TestCase):
    """La VRAM de una tarjeta cuyo driver no la publica.

    Salió de una GeForce GTX 1050 Mobile con nouveau: amdgpu escribe la
    memoria en sysfs y NVML la da con el driver propietario, pero con nouveau
    no hay ninguna de las dos y la ficha entera se quedaba en blanco. Vulkan
    enumera los montones de memoria de la tarjeta y ahí está.
    """

    VULKAN_CON_MEMORIA = dict(VULKAN_AMD, device_memory_bytes=17_163_091_968)

    def test_rellena_la_que_falta(self):
        draft = _recolectar(
            [{"vendor_id": 0x1002, "device_id": 0x7550, "primary": True}],
            vulkan=[self.VULKAN_CON_MEMORIA])
        self.assertEqual(draft.gpus[0]["memory"].total_bytes, 17_163_091_968)

    def test_pero_no_pisa_la_que_dio_el_driver(self):
        """El driver mide su chip; Vulkan dice lo que puede repartir."""
        from silux.model import GpuMemory
        draft = _recolectar(
            [{"vendor_id": 0x1002, "device_id": 0x7550, "primary": True,
              "memory": GpuMemory(total_bytes=16_000_000_000)}],
            vulkan=[self.VULKAN_CON_MEMORIA])
        self.assertEqual(draft.gpus[0]["memory"].total_bytes, 16_000_000_000)

    def test_sin_el_dato_no_se_inventa_nada(self):
        draft = _recolectar(
            [{"vendor_id": 0x1002, "device_id": 0x7550, "primary": True}],
            vulkan=[VULKAN_AMD])
        memoria = draft.gpus[0].get("memory")
        self.assertTrue(memoria is None or memoria.total_bytes is None)

    def test_y_conserva_lo_demas_de_la_memoria(self):
        """El tipo y la anchura del bus los dio el ioctl y siguen ahí."""
        from silux.model import GpuMemory
        draft = _recolectar(
            [{"vendor_id": 0x1002, "device_id": 0x7550, "primary": True,
              "memory": GpuMemory(kind="GDDR6", bus_bits=256)}],
            vulkan=[self.VULKAN_CON_MEMORIA])
        memoria = draft.gpus[0]["memory"]
        self.assertEqual(memoria.kind, "GDDR6")
        self.assertEqual(memoria.bus_bits, 256)
        self.assertEqual(memoria.total_bytes, 17_163_091_968)
