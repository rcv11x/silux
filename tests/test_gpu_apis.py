"""OpenGL, Vulkan y OpenCL colgados de la tarjeta que les toca.

Vulkan publica el identificador PCI y se casa sin ambigüedad. OpenGL y OpenCL
no dicen a qué tarjeta pertenecen, así que se le atribuyen a la que el sistema
usa por omisión, que es lo único honesto que se puede hacer sin adivinar.
"""

import json
import subprocess
import unittest
from unittest import mock

from cpuz import gpuapi
from cpuz.providers import gpu_apis
from cpuz.providers.base import Draft

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

    VACIO = {"vulkan": [], "opencl": [], "opengl": None}

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
            raise subprocess.TimeoutExpired(cmd="cpuz.gpuapi", timeout=gpuapi.TIEMPO_MAXIMO)

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
        self.assertEqual(capturado["orden"][1:], ["-m", "cpuz.gpuapi"])
        self.assertIn("PYTHONPATH", capturado["env"])


if __name__ == "__main__":
    unittest.main()
