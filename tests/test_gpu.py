"""Las gráficas, contra un /sys falso.

Aquí importa más que en ningún otro sitio poder inventarse el hardware: nadie
tiene delante a la vez una AMD dedicada, una Intel integrada y una NVIDIA con
el driver propietario, y los tres casos se comportan de forma distinta. Cada
uno se monta como un árbol de ficheros y se comprueba qué saca el proveedor.

Varias de estas pruebas nacieron de fallos reales encontrados con la tarjeta
delante, y están escritas para que no vuelvan.
"""

import pathlib
import tempfile
import unittest
from unittest import mock

from silux import i18n, render
from silux.i18n import _
from silux.model import (Display, Gpu, GpuClocks, GpuMemory, Need, Note,
                         PcieLink)
from silux.providers import drm
from silux.providers.base import Draft
from tests.test_edid import construir as construir_edid


def _write(path: pathlib.Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"{value}\n", encoding="utf-8")


def _write_bytes(path: pathlib.Path, value: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(value)


class BancoDrm(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self._tmp.name)
        patch = mock.patch.object(drm, "SYS_DRM", str(self.root))
        patch.start()
        self.addCleanup(patch.stop)
        self.addCleanup(self._tmp.cleanup)

    def tarjeta(self, numero: int, ranura: str = "0000:03:00.0",
                **campos: str) -> pathlib.Path:
        """Un nodo cardN con su nodo PCI detrás.

        `ranura` importa para distinguir una integrada de una dedicada: la de
        Intel vive siempre en 0000:00:02.0 y una tarjeta aparte va detrás de
        un puente, en otro bus.
        """
        real = self.root / "pci0000:00" / ranura
        real.mkdir(parents=True, exist_ok=True)
        for nombre, valor in campos.items():
            _write(real / nombre, valor)
        enlace = self.root / f"card{numero}" / "device"
        enlace.parent.mkdir(parents=True, exist_ok=True)
        if not enlace.exists():
            enlace.symlink_to(real)
        (real / "driver").parent.mkdir(parents=True, exist_ok=True)
        return enlace

    def cadena_pcie(self, numero: int, eslabones) -> None:
        """Monta la GPU al final de una cadena real de puentes PCI.

        `eslabones` va del puerto raíz hacia la tarjeta, con la velocidad y la
        anchura negociadas de cada uno.
        """
        ruta = self.root / "pci0000:00"
        for direccion, velocidad, ancho in eslabones:
            ruta = ruta / direccion
            _write(ruta / "current_link_speed", f"{velocidad} GT/s PCIe")
            _write(ruta / "max_link_speed", f"{velocidad} GT/s PCIe")
            _write(ruta / "current_link_width", str(ancho))
            _write(ruta / "max_link_width", str(ancho))
        enlace = self.root / f"card{numero}" / "device"
        enlace.parent.mkdir(parents=True, exist_ok=True)
        if enlace.is_symlink() or enlace.exists():
            for hijo in sorted(enlace.rglob("*"), reverse=True):
                hijo.unlink() if hijo.is_file() else None
        return ruta

    def conector(self, tarjeta: int, nombre: str, estado: str,
                 modos: str = "", habilitado: str = "disabled") -> None:
        base = self.root / f"card{tarjeta}-{nombre}"
        _write(base / "status", estado)
        _write(base / "enabled", habilitado)
        if modos:
            _write(base / "modes", modos)

    def recolectar(self) -> Draft:
        draft = Draft()
        drm.DrmGpus().collect(draft)
        drm.GpuState().collect(draft)
        return draft


class TestAmdCompleta(BancoDrm):
    """Una Radeon dedicada, que es la que más cosas publica."""

    def setUp(self):
        super().setUp()
        # A propósito es card1 y no card0: en una máquina con una sola gráfica
        # dedicada el kernel la numera así, y dar por hecho que el índice de la
        # lista es el número del nodo dejaba sin leer todo lo dinámico.
        dispositivo = self.tarjeta(
            1,
            vendor="0x1002", device="0x7550",
            subsystem_vendor="0x148c", subsystem_device="0x2435",
            revision="0xc0", boot_vga="1",
            vbios_version="113-EXT108779-100", unique_id="0000000000000000",
            current_link_speed="32.0 GT/s PCIe", current_link_width="16",
            max_link_speed="32.0 GT/s PCIe", max_link_width="16",
            mem_info_vram_total="17095983104", mem_info_vram_used="2108162048",
            mem_info_vis_vram_total="17095983104", mem_info_gtt_total="16782372864",
            mem_info_gtt_used="402334464", mem_info_vram_vendor="hynix",
            gpu_busy_percent="13", mem_busy_percent="4", vcn_busy_percent="0",
            pp_dpm_sclk="0: 500Mhz \n1: 1150Mhz *\n2: 2520Mhz ",
            pp_dpm_mclk="0: 96Mhz \n1: 1258Mhz *",
            power_dpm_force_performance_level="auto",
        )
        hwmon = dispositivo / "hwmon" / "hwmon3"
        for nombre, valor in (
            ("temp1_label", "edge"), ("temp1_input", "47000"),
            ("temp2_label", "junction"), ("temp2_input", "49000"),
            ("temp3_label", "mem"), ("temp3_input", "66000"),
            ("freq1_label", "sclk"), ("freq1_input", "1038000000"),
            ("freq2_label", "mclk"), ("freq2_input", "1258000000"),
            ("in0_label", "vddgfx"), ("in0_input", "695"),
            ("power1_average", "48000000"), ("power1_cap", "340000000"),
            ("fan1_input", "1200"), ("pwm1", "128"), ("pwm1_max", "255"),
        ):
            _write(hwmon / nombre, valor)

        self.conector(1, "DP-1", "connected", "2560x1440\n1920x1080")
        self.conector(1, "DP-2", "disconnected")
        self.conector(1, "Writeback-1", "unknown")

    def test_encuentra_la_tarjeta_aunque_el_nodo_no_sea_card0(self):
        gpus = self.recolectar().freeze().gpus
        self.assertEqual(len(gpus), 1)
        self.assertEqual(gpus[0].drm_node, "card1")

    def test_identidad(self):
        gpu = self.recolectar().freeze().gpus[0]
        self.assertEqual(gpu.vendor, "AMD")
        self.assertEqual(gpu.pci_id, "1002:7550")
        self.assertEqual(gpu.subsystem_id, "148C:2435")
        self.assertEqual(gpu.vbios, "113-EXT108779-100")
        self.assertTrue(gpu.primary)
        self.assertFalse(gpu.integrated)

    def test_memoria(self):
        gpu = self.recolectar().freeze().gpus[0]
        self.assertEqual(gpu.memory.total_bytes, 17095983104)
        self.assertEqual(gpu.memory.used_bytes, 2108162048)
        self.assertEqual(gpu.memory.vendor, "hynix")
        self.assertAlmostEqual(gpu.memory.used_percent, 12.3, places=1)
        # Toda la VRAM es visible: la BAR está redimensionada.
        self.assertTrue(gpu.memory.resizable_bar)

    def test_enlace_pcie(self):
        gpu = self.recolectar().freeze().gpus[0]
        self.assertEqual(gpu.link.generation, 5)
        self.assertEqual(gpu.link.current_width, 16)
        self.assertFalse(gpu.link.downgraded)
        self.assertEqual(render.pcie_link(gpu.link), "PCIe 5.0 × 16")

    def test_relojes_y_tabla_dpm(self):
        gpu = self.recolectar().freeze().gpus[0]
        # La instantánea la manda hwmon, no el escalón marcado.
        self.assertEqual(gpu.clocks.core_hz, 1_038_000_000)
        self.assertEqual(gpu.clocks.core_max_hz, 2_520_000_000)
        self.assertEqual([n.hz for n in gpu.clocks.core_levels],
                         [500_000_000, 1_150_000_000, 2_520_000_000])
        self.assertEqual([n.index for n in gpu.clocks.core_levels if n.active], [1])

    def test_sensores_por_etiqueta(self):
        gpu = self.recolectar().freeze().gpus[0]
        self.assertEqual((gpu.temp_c, gpu.hotspot_c, gpu.memory_temp_c), (47.0, 49.0, 66.0))
        self.assertEqual(gpu.power_w, 48.0)
        self.assertEqual(gpu.power_cap_w, 340.0)
        self.assertEqual(gpu.fan_rpm, 1200)
        self.assertAlmostEqual(gpu.fan_percent, 50.2, places=1)
        self.assertEqual(gpu.voltage_v, 0.695)

    def test_salidas_de_video(self):
        gpu = self.recolectar().freeze().gpus[0]
        # Writeback no es una salida: es un destino interno del compositor.
        self.assertEqual([d.connector for d in gpu.displays], ["DP-1", "DP-2"])
        self.assertEqual(gpu.connected_displays[0].resolution, "2560 × 1440")


class TestEnlacePcieReal(BancoDrm):
    """El enlace que vale es el del eslabón más lento, no el de la tarjeta."""

    def test_el_conmutador_interno_no_manda(self):
        # Una RX 9070 XT en una X570: por dentro negocia a 32 GT/s, pero con el
        # sistema habla a 16. Leyendo solo el nodo de la GPU salía «PCIe 5.0» en
        # una placa que no tiene PCIe 5.0.
        destino = self.cadena_pcie(1, [
            ("0000:00:03.1", "16.0", 16),   # puerto raíz de la CPU
            ("0000:0a:00.0", "16.0", 16),   # conmutador de la tarjeta, lado de fuera
            ("0000:0b:00.0", "32.0", 16),   # conmutador, lado de dentro
            ("0000:0c:00.0", "32.0", 16),   # la GPU
        ])
        _write(destino / "vendor", "0x1002")
        _write(destino / "device", "0x7550")
        (self.root / "card1" / "device").symlink_to(destino)

        gpu = self.recolectar().freeze().gpus[0]
        self.assertEqual(gpu.link.generation, 4)
        self.assertEqual(gpu.link.max_generation, 4)
        self.assertEqual(render.pcie_link(gpu.link), "PCIe 4.0 × 16")

    def test_un_ancho_recortado_se_nota(self):
        destino = self.cadena_pcie(1, [
            ("0000:00:03.1", "16.0", 4),    # ranura de solo cuatro carriles
            ("0000:0c:00.0", "16.0", 16),
        ])
        _write(destino / "vendor", "0x1002")
        _write(destino / "device", "0x7550")
        (self.root / "card1" / "device").symlink_to(destino)

        gpu = self.recolectar().freeze().gpus[0]
        self.assertEqual(gpu.link.current_width, 4)


class TestFormatosQueCambian(BancoDrm):
    """Lo que amdgpu escribe no siempre tiene la forma que uno espera."""

    def test_la_gpu_dormida_marca_su_escalon_con_una_letra(self):
        # RDNA3 y RDNA4 escriben «S:» —de sleep— en vez de un índice cuando la
        # tarjeta está en reposo profundo. Con el patrón anterior, esa línea se
        # colaba como escalón número cero y descuadraba la tabla entera.
        self.tarjeta(0, vendor="0x1002", device="0x7550",
                     pp_dpm_sclk="S: 0Mhz *\n1: 500Mhz \n2: 2520Mhz ")
        gpu = self.recolectar().freeze().gpus[0]
        self.assertEqual([n.index for n in gpu.clocks.core_levels], [1, 2])
        self.assertEqual(gpu.clocks.core_max_hz, 2_520_000_000)

    def test_cero_megahercios_es_una_respuesta_no_una_ausencia(self):
        # Una tarjeta parada del todo marca 0. Con `or` se descartaba y se
        # acababa enseñando un guion en lugar de la lectura más interesante.
        dispositivo = self.tarjeta(0, vendor="0x1002", device="0x7550")
        hwmon = dispositivo / "hwmon" / "hwmon0"
        _write(hwmon / "freq1_label", "sclk")
        _write(hwmon / "freq1_input", "0")
        gpu = self.recolectar().freeze().gpus[0]
        self.assertEqual(gpu.clocks.core_hz, 0)

    def test_gigahercios_en_la_tabla(self):
        self.tarjeta(0, vendor="0x1002", device="0x7550", pp_dpm_mclk="0: 1.25Ghz *")
        gpu = self.recolectar().freeze().gpus[0]
        self.assertEqual(gpu.clocks.memory_max_hz, 1_250_000_000)


class TestOtrosDrivers(BancoDrm):
    def test_una_intel_integrada(self):
        self.tarjeta(0, ranura="0000:00:02.0", vendor="0x8086", device="0x9bc4",
                     gt_cur_freq_mhz="350", gt_max_freq_mhz="1150")
        gpu = self.recolectar().freeze().gpus[0]
        self.assertEqual(gpu.vendor, "Intel")
        # La integrada de Intel vive en la función 0 del dispositivo 2 del
        # bus 0, siempre. Antes se decidía por no tener VRAM, y eso confundía
        # «no se pudo leer» con «no tiene».
        self.assertTrue(gpu.integrated)
        self.assertEqual(gpu.clocks.core_hz, 350_000_000)
        self.assertEqual(gpu.clocks.core_max_hz, 1_150_000_000)

    def test_una_nvidia_propietaria_se_explica(self):
        dispositivo = self.tarjeta(0, vendor="0x10de", device="0x2684")
        (dispositivo / "driver").symlink_to(self.root / "nvidia")
        (self.root / "nvidia").mkdir(parents=True, exist_ok=True)

        draft = self.recolectar()
        gpu = draft.freeze().gpus[0]
        self.assertEqual(gpu.vendor, "NVIDIA")
        # No se esconde la tarjeta: se dice por qué viene medio vacía.
        self.assertTrue(any(n.path.startswith("gpus.") for n in draft.notes))

    def test_sin_ninguna_grafica_lo_dice(self):
        draft = self.recolectar()
        self.assertEqual(draft.freeze().gpus, ())
        self.assertEqual([n.path for n in draft.notes], ["gpus"])


class TestMonitoresPorEdid(BancoDrm):
    """La chapa del monitor cuelga de la salida a la que está enchufado."""

    def setUp(self):
        super().setUp()
        self.tarjeta(0, vendor="0x1002", device="0x7550")
        self.conector(0, "DP-1", "connected", "1920x1080")
        # El EDID dice 2560×1440; `modes` dice otra cosa. Manda el EDID.
        _write_bytes(self.root / "card0-DP-1" / "edid",
                     construir_edid(nombre="AORUS FO27Q2", nativo=(2560, 1440),
                                    refresco=(48, 240)))
        self.conector(0, "HDMI-A-1", "disconnected")

    def test_identifica_el_monitor(self):
        salida = self.recolectar().freeze().gpus[0].displays[0]
        self.assertIsNotNone(salida.monitor)
        self.assertEqual(salida.monitor.model, "AORUS FO27Q2")
        self.assertEqual(salida.monitor.refresh_range, "48–240 Hz")

    def test_el_edid_manda_sobre_la_lista_de_modos(self):
        salida = self.recolectar().freeze().gpus[0].displays[0]
        self.assertEqual(salida.resolution, "2560 × 1440")

    def test_una_salida_libre_no_tiene_monitor(self):
        salidas = {d.connector: d for d in self.recolectar().freeze().gpus[0].displays}
        self.assertIsNone(salidas["HDMI-A-1"].monitor)

    def test_un_edid_corrupto_no_estropea_la_salida(self):
        _write_bytes(self.root / "card0-DP-1" / "edid", b"\x00" * 128)
        salida = self.recolectar().freeze().gpus[0].displays[0]
        self.assertIsNone(salida.monitor)
        self.assertTrue(salida.connected)     # sigue estando enchufada


class TestPantallasBajoWayland(BancoDrm):
    """El `enabled` de sysfs no dice lo que parece decir."""

    def test_una_pantalla_encendida_puede_figurar_como_deshabilitada(self):
        # Con un compositor Wayland al mando del modeset, sysfs marca
        # «disabled» en pantallas que están funcionando delante de uno. Por eso
        # el resumen habla de lo que hay enchufado y no de lo que está en uso.
        self.tarjeta(0, vendor="0x1002", device="0x7550")
        self.conector(0, "DP-1", "connected", "2560x1440", habilitado="disabled")
        gpu = self.recolectar().freeze().gpus[0]
        salida = gpu.displays[0]
        self.assertTrue(salida.connected)
        self.assertFalse(salida.enabled)
        self.assertEqual(render.display_summary(salida), "2560 × 1440")


class TestRenderDeGraficos(unittest.TestCase):
    def test_enlace_a_medio_gas(self):
        enlace = PcieLink(current_speed_gts=2.5, current_width=16,
                         max_speed_gts=32.0, max_width=16)
        self.assertTrue(enlace.downgraded)
        self.assertEqual(render.pcie_link(enlace), "PCIe 1.0 × 16")
        self.assertIn("PCIe 5.0 × 16", render.pcie_note(enlace))

    def test_una_velocidad_que_no_es_de_ninguna_generacion(self):
        enlace = PcieLink(current_speed_gts=7.0, current_width=8)
        self.assertIsNone(enlace.generation)
        self.assertEqual(render.pcie_link(enlace), "7 GT/s × 8")

    def test_sin_enlace_no_se_inventa_nada(self):
        self.assertEqual(render.pcie_link(PcieLink()), render.DASH)
        self.assertIsNone(render.pcie_note(PcieLink()))

    def test_resumen_de_memoria(self):
        memoria = GpuMemory(total_bytes=16 * 1024**3, used_bytes=4 * 1024**3)
        self.assertEqual(render.gpu_memory_summary(memoria), "4 GB de 16 GB   (25 %)")
        self.assertEqual(render.gpu_memory_summary(GpuMemory()), render.DASH)

    def test_ventana_fija_de_la_bar(self):
        # Sin Resizable BAR la CPU solo ve los 256 MB de siempre.
        estrecha = GpuMemory(total_bytes=16 * 1024**3, visible_bytes=256 * 1024**2)
        self.assertFalse(estrecha.resizable_bar)
        self.assertIsNone(GpuMemory().resizable_bar)

    def test_salida_sin_nada_enchufado(self):
        self.assertEqual(render.display_summary(Display(connector="HDMI-A-1")),
                         "sin conectar")


if __name__ == "__main__":
    unittest.main()


class TestUnidadesDeProceso(unittest.TestCase):
    """Cada fabricante cuenta las suyas y no son equivalentes.

    Una unidad de cómputo de AMD agrupa decenas de núcleos como los que NVIDIA
    cuenta de uno en uno. Enseñar «64 CU» y «2048 CU» con la misma etiqueta
    hacía creer que la segunda tarjeta tiene treinta veces más de lo mismo.
    """

    def test_amd_cuenta_unidades_de_computo(self):
        from silux.model import Gpu
        gpu = Gpu(vendor="AMD", compute_units=64)
        self.assertEqual(render.compute_units(gpu), "64 unidades de cómputo")
        self.assertEqual(render.compute_units_short(gpu), "64 CU")

    def test_nvidia_cuenta_nucleos_cuda(self):
        from silux.model import Gpu
        gpu = Gpu(vendor="NVIDIA", compute_units=2048)
        self.assertEqual(render.compute_units(gpu), "2048 núcleos CUDA")
        self.assertEqual(render.compute_units_short(gpu), "2048 CUDA")

    def test_intel_cuenta_unidades_de_ejecucion(self):
        from silux.model import Gpu
        gpu = Gpu(vendor="Intel", compute_units=96)
        self.assertEqual(render.compute_units_short(gpu), "96 EU")

    def test_un_fabricante_desconocido_no_se_inventa_la_unidad(self):
        from silux.model import Gpu
        gpu = Gpu(vendor="Matrox", compute_units=8)
        self.assertEqual(render.compute_units(gpu), "8 unidades de proceso")

    def test_sin_dato_no_hay_insignia(self):
        from silux.model import Gpu
        self.assertIsNone(render.compute_units_short(Gpu(vendor="AMD")))
        self.assertEqual(render.compute_units(Gpu(vendor="AMD")), render.DASH)


class TestTipoYBusDeMemoria(unittest.TestCase):
    def test_van_por_separado(self):
        # Juntarlos hacía que una tarjeta sin tipo conocido enseñara «128 bits»
        # en un campo llamado «Tipo».
        memoria = GpuMemory(kind="GDDR6", bus_bits=256)
        self.assertEqual(render.vram_kind(memoria), "GDDR6")
        self.assertEqual(render.vram_bus(memoria), "256 bits")

    def test_solo_el_bus(self):
        memoria = GpuMemory(bus_bits=128)
        self.assertEqual(render.vram_kind(memoria), render.DASH)
        self.assertEqual(render.vram_bus(memoria), "128 bits")

    def test_sin_nada(self):
        self.assertEqual(render.vram_kind(GpuMemory()), render.DASH)
        self.assertEqual(render.vram_bus(GpuMemory()), render.DASH)


class TestIntegradaODedicada(unittest.TestCase):
    """Una tarjeta dedicada cuya VRAM no se puede leer sigue siendo dedicada.

    El caso salió de una GeForce GTX 1050 Mobile con el driver nouveau, que
    no publica la memoria en sysfs. Como la clasificación miraba si había
    VRAM, la tarjeta aparecía marcada como integrada, que es lo contrario de
    lo que es. Y por el mismo motivo al revés: una APU reserva un trozo de la
    RAM del sistema y parecía tener memoria propia.
    """

    def _clasificar(self, **gpu):
        from silux.providers.drm import _es_integrada
        return _es_integrada(gpu)

    def test_una_nvidia_nunca_es_integrada(self):
        """Aunque no se le lea la memoria, como pasa con nouveau."""
        self.assertIs(self._clasificar(
            vendor="NVIDIA", pci_slot="0000:01:00.0", driver="nouveau"), False)

    def test_la_intel_del_bus_cero_si(self):
        self.assertIs(self._clasificar(
            vendor="Intel", pci_slot="0000:00:02.0"), True)

    def test_pero_una_intel_en_otro_bus_no(self):
        """Una Arc dedicada va detrás de un puente, como cualquier tarjeta."""
        self.assertIs(self._clasificar(
            vendor="Intel", pci_slot="0000:03:00.0"), False)

    def test_en_amd_manda_el_ioctl(self):
        """El bit FUSION lo pone el driver y no admite interpretación."""
        self.assertIs(self._clasificar(
            vendor="AMD", pci_slot="0000:05:00.0", _is_apu=True), True)
        self.assertIs(self._clasificar(
            vendor="AMD", pci_slot="0000:0c:00.0", _is_apu=False), False)

    def test_una_apu_con_su_trozo_de_ram_no_pasa_por_dedicada(self):
        """512 MB reservados de la RAM del sistema parecen memoria propia."""
        self.assertIs(self._clasificar(
            vendor="AMD", pci_slot="0000:05:00.0", _is_apu=True,
            memory_total=512 * 1024**2), True)

    def test_lo_que_no_se_sabe_se_queda_sin_saber(self):
        """Mejor no decirlo que decirlo por descarte."""
        self.assertIsNone(self._clasificar(vendor="Matrox", pci_slot="0000:04:00.0"))
        self.assertIsNone(self._clasificar(vendor="AMD", pci_slot="0000:05:00.0"))


class TestFrecuenciasIntel(BancoDrm):
    """Las frecuencias de una Intel integrada, se llamen como se llamen.

    Salieron de una captura de una UHD 630 con todos los relojes en blanco.
    No era que no se leyeran: se buscaban en `card0/device/`, que es el enlace
    al dispositivo PCI, y i915 las publica en el nodo DRM. Encima han cambiado
    de sitio con el kernel 6.2, que las metió en `gt/gt0/` con prefijo `rps_`
    para poder tener varios motores gráficos por tarjeta.
    """

    def _uhd(self, **ficheros):
        self.tarjeta(0, ranura="0000:00:02.0", vendor="0x8086", device="0x9bc8")
        for nombre, valor in ficheros.items():
            _write(self.root / "card0" / nombre.replace("__", "/"), valor)
        return self.recolectar().freeze().gpus[0]

    def test_el_sitio_clasico_de_i915(self):
        gpu = self._uhd(gt_act_freq_mhz="350", gt_max_freq_mhz="1150")
        self.assertEqual(gpu.clocks.core_hz, 350_000_000)
        self.assertEqual(gpu.clocks.core_max_hz, 1_150_000_000)

    def test_el_sitio_nuevo_desde_el_kernel_6_2(self):
        gpu = self._uhd(**{"gt__gt0__rps_act_freq_mhz": "450",
                           "gt__gt0__rps_max_freq_mhz": "1200"})
        self.assertEqual(gpu.clocks.core_hz, 450_000_000)
        self.assertEqual(gpu.clocks.core_max_hz, 1_200_000_000)

    def test_prefiere_la_que_va_de_verdad_a_la_que_se_pide(self):
        """`act` es lo que hace el chip; `cur` es lo que se le ha pedido."""
        gpu = self._uhd(**{"gt__gt0__rps_act_freq_mhz": "300",
                           "gt__gt0__rps_cur_freq_mhz": "1100"})
        self.assertEqual(gpu.clocks.core_hz, 300_000_000)

    def test_si_solo_esta_la_pedida_vale_esa(self):
        gpu = self._uhd(**{"gt__gt0__rps_cur_freq_mhz": "900"})
        self.assertEqual(gpu.clocks.core_hz, 900_000_000)

    def test_sin_ninguna_de_las_dos_no_se_inventa(self):
        gpu = self._uhd()
        self.assertIsNone(gpu.clocks.core_hz)
        self.assertIsNone(gpu.clocks.core_max_hz)

    def test_una_gpu_parada_a_cero_no_es_un_dato_ausente(self):
        """0 MHz es la respuesta de un motor gráfico en reposo profundo."""
        gpu = self._uhd(gt_act_freq_mhz="0", gt_max_freq_mhz="1150")
        self.assertEqual(gpu.clocks.core_max_hz, 1_150_000_000)


class TestMemoriaQueNoSeConoce(unittest.TestCase):
    """Un dato que falta se dice que falta.

    Cuando el driver no publica la memoria ocupada, el resumen devolvía el
    total y la página lo pintaba bajo el renglón «En uso»: una integrada de
    Intel declaraba tener sus 11,6 GB ocupados al completo.
    """

    def test_sin_lo_usado_no_se_inventa_el_total(self):
        memoria = GpuMemory(total_bytes=12_426_808_320)
        self.assertEqual(render.gpu_memory_summary(memoria), render.DASH)

    def test_con_los_dos_se_resume_como_siempre(self):
        memoria = GpuMemory(total_bytes=16 * 1024 ** 3, used_bytes=4 * 1024 ** 3)
        self.assertEqual(render.gpu_memory_summary(memoria), "4 GB de 16 GB   (25 %)")


class TestCentinelasDelEnlace(unittest.TestCase):
    """Un dispositivo que no cuelga de un bus PCIe publica los ficheros igual.

    La gráfica integrada dice ancho 0 y máximo 255 (0xFF): son centinelas de
    «no hay enlace» y «no se sabe», no anchos. Sin filtrarlos, declaraba un
    enlace de 255 carriles.
    """

    def test_los_anchos_validos_son_los_de_la_especificacion(self):
        from silux.providers.drm import ANCHOS_PCIE

        for carriles in (1, 2, 4, 8, 12, 16, 32):
            self.assertIn(carriles, ANCHOS_PCIE)

    def test_los_centinelas_no_lo_son(self):
        from silux.providers.drm import ANCHOS_PCIE

        for centinela in (0, 255, 3, 7, 100):
            self.assertNotIn(centinela, ANCHOS_PCIE)


class TestAvisoDeIntel(unittest.TestCase):
    def test_los_tres_avisos_dicen_lo_de_la_temperatura(self):
        # Es lo único que una Intel no da por ningún camino: el nodo DRM no
        # trae hwmon y su PMU no tiene evento térmico.
        from silux.providers.drm import INTEL_AVISOS

        # La tabla lleva claves, no frases: se traducen aquí, porque lo
        # que hay que vigilar es lo que acaba leyendo el usuario.
        for clave, (mensaje, pista) in INTEL_AVISOS.items():
            with self.subTest(clave=clave):
                self.assertIn("temperatura", _(mensaje))
                self.assertTrue(_(pista))

    def test_solo_el_de_permisos_promete_uso_y_consumo(self):
        # Los otros dos se enseñan cuando ya hay permisos: prometer ahí lo que
        # ya está en pantalla sobra, y prometerlo cuando el kernel no lo da
        # sería mentir.
        from silux.providers.drm import INTEL_AVISOS

        self.assertIn("consumo", _(INTEL_AVISOS["root"][0]))
        self.assertNotIn("consumo", _(INTEL_AVISOS["driver"][0]))

    def test_ninguno_manda_al_usuario_a_tocar_el_kernel(self):
        """Bajar perf_event_paranoid afloja el cerrojo de toda la máquina.

        A 0 —que es el único valor que sirve, comprobado: con 1 el contador
        sigue denegado— cualquier proceso sin privilegios puede perfilar el
        equipo entero. Eso no se le pide a nadie para ver un porcentaje, y
        menos cuando el ayudante privilegiado ya lo lee sin tocar nada.
        """
        from silux.providers.drm import INTEL_AVISOS

        # En los dos idiomas: el aviso se escribe dos veces y basta con
        # que se cuele en uno.
        for idioma in ("es", "en"):
            i18n.set_language(idioma)
            for clave, textos in INTEL_AVISOS.items():
                for texto in textos:
                    with self.subTest(clave=clave, idioma=idioma):
                        self.assertNotIn("paranoid", _(texto))
                        self.assertNotIn("CAP_PERFMON", _(texto))
                        self.assertNotIn("sysctl", _(texto))
        i18n.set_language("es")

    def test_i915_y_xe_ya_no_van_por_la_tabla_estatica(self):
        # Su aviso depende de si el usuario ha elevado permisos, y eso cambia
        # a mitad de sesión. La tabla la lee un proveedor que corre una vez.
        from silux.providers.drm import DRIVERS_CIEGOS

        self.assertNotIn("i915", DRIVERS_CIEGOS)
        self.assertNotIn("xe", DRIVERS_CIEGOS)

    def test_los_drivers_que_sí_publican_no_llevan_aviso(self):
        from silux.providers.drm import DRIVERS_CIEGOS

        self.assertNotIn("amdgpu", DRIVERS_CIEGOS)


class TestDondeSePintanLosAvisos(unittest.TestCase):
    """Un aviso vale de poco si está lejos del hueco que explica.

    En una UHD 630 sin CAP_PERFMON las cuatro fichas de arriba —uso,
    temperatura, consumo y VRAM— salen todas a «—», y la explicación se
    pintaba al final de la página, detrás de todas las tarjetas. Para leerla
    había que bajar del todo, así que en la práctica no se leía: la queja fue
    «no sale ningún dato abajo».
    """

    def _pagina_con(self, gpus, notes):
        from PySide6.QtWidgets import QApplication
        from silux.model import CpuInfo, Snapshot
        from silux.settings import Preferences
        from silux.ui import theme
        from silux.ui.pages.graphics import GraphicsPage

        app = QApplication.instance() or QApplication([])
        pagina = GraphicsPage(theme.palette_for(app, "dark"), Preferences())
        pagina.apply(Snapshot(monotonic_ns=0, cpu=CpuInfo(),
                              gpus=tuple(gpus), notes=tuple(notes)))
        return pagina

    def _cuantos_avisos(self, layout) -> int:
        return sum(1 for i in range(layout.count())
                   if layout.itemAt(i).widget() is not None)

    def test_el_aviso_de_una_grafica_va_en_su_tarjeta(self):
        nota = Note("gpus.0.utilization", Need.DRIVER, "Falta un driver.")
        pagina = self._pagina_con([Gpu(name="UHD 630")], [nota])
        self.assertEqual(self._cuantos_avisos(pagina._sections[0]._notices_host), 1)
        self.assertEqual(self._cuantos_avisos(pagina._notices_host), 0)

    def test_cada_grafica_recibe_el_suyo_y_no_el_de_al_lado(self):
        notas = [Note("gpus.1.utilization", Need.DRIVER, "Falta un driver.")]
        pagina = self._pagina_con(
            [Gpu(name="UHD 630"), Gpu(name="Radeon RX 9070 XT")], notas)
        self.assertEqual(self._cuantos_avisos(pagina._sections[0]._notices_host), 0)
        self.assertEqual(self._cuantos_avisos(pagina._sections[1]._notices_host), 1)

    def test_el_que_no_lleva_numero_se_queda_al_pie(self):
        notas = [Note("gpus", Need.DRIVER, "No se encontró ninguna gráfica.")]
        pagina = self._pagina_con([Gpu(name="UHD 630")], notas)
        self.assertEqual(self._cuantos_avisos(pagina._sections[0]._notices_host), 0)
        self.assertEqual(self._cuantos_avisos(pagina._notices_host), 1)

    def test_uno_con_un_numero_que_no_existe_tampoco_se_pierde(self):
        # Si el proveedor numera más gráficas de las que la página montó, el
        # aviso baja al pie en vez de desaparecer.
        notas = [Note("gpus.7.utilization", Need.DRIVER, "Falta un driver.")]
        pagina = self._pagina_con([Gpu(name="UHD 630")], notas)
        self.assertEqual(self._cuantos_avisos(pagina._notices_host), 1)


class ClienteFalso:
    """Un ayudante de mentira que devuelve los contadores que se le digan."""

    def __init__(self, respuestas, conectado=True):
        self._respuestas = list(respuestas)
        self._conectado = conectado
        self.llamadas = 0

    def connected(self):
        return self._conectado

    def gpu_pmu(self):
        self.llamadas += 1
        siguiente = self._respuestas.pop(0)
        if isinstance(siguiente, Exception):
            raise siguiente
        return siguiente


def _lectura(reloj_ns, ocupado_ns, energia=None):
    motores = {"i915": {"rcs0-busy": ocupado_ns}}
    escalas = {}
    if energia is not None:
        motores["power"] = {"energy-gpu": energia}
        escalas["power"] = {"energy-gpu": 2.3283064365386963e-10}
    return reloj_ns, motores, escalas


class TestContadoresDelKernel(unittest.TestCase):
    """El uso y el consumo de una Intel, que solo salen del PMU de perf.

    Contrastado contra intel_gpu_top en una UHD 630 con glxgears delante:
    la herramienta de referencia daba 40-43 % y 2.07-2.35 W, y esta cuenta
    sobre los mismos contadores dio 42 % y 2.25 W.
    """

    def _proveedor(self, respuestas, conectado=True):
        from silux.providers.drm import GpuState

        cliente = ClienteFalso(respuestas, conectado)
        return GpuState(client=cliente), cliente

    def test_la_primera_lectura_solo_fija_la_referencia(self):
        proveedor, _ = self._proveedor([_lectura(0, 0)])
        self.assertEqual(proveedor._contadores(), (None, None))

    def test_la_segunda_ya_da_el_porcentaje(self):
        # Medio segundo ocupado dentro de una ventana de un segundo.
        proveedor, _ = self._proveedor([
            _lectura(1_000_000_000, 0),
            _lectura(2_000_000_000, 500_000_000),
        ])
        proveedor._contadores()
        ocupacion, _ = proveedor._contadores()
        self.assertAlmostEqual(ocupacion["i915"]["rcs0-busy"], 50.0)

    def test_un_contador_reiniciado_se_salta_esa_vuelta(self):
        proveedor, _ = self._proveedor([
            _lectura(1_000_000_000, 900_000_000),
            _lectura(2_000_000_000, 10_000_000),
        ])
        proveedor._contadores()
        ocupacion, _ = proveedor._contadores()
        self.assertEqual(ocupacion, {})

    def test_no_se_pasa_del_cien_por_cien(self):
        # En ventanas cortas el contador y el reloj no arrancan alineados.
        proveedor, _ = self._proveedor([
            _lectura(1_000_000_000, 0),
            _lectura(1_000_050_000, 60_000),
        ])
        proveedor._contadores()
        ocupacion, _ = proveedor._contadores()
        self.assertEqual(ocupacion["i915"]["rcs0-busy"], 100.0)

    def test_los_vatios_salen_del_contador_de_energia(self):
        # 2^32 unidades de 2^-32 julios son un julio; en un segundo, un vatio.
        proveedor, _ = self._proveedor([
            _lectura(1_000_000_000, 0, energia=0),
            _lectura(2_000_000_000, 0, energia=2**32),
        ])
        proveedor._contadores()
        _, vatios = proveedor._contadores()
        self.assertAlmostEqual(vatios, 1.0, places=6)

    def test_la_energia_no_se_cuela_como_un_motor_mas(self):
        proveedor, _ = self._proveedor([
            _lectura(1_000_000_000, 0, energia=0),
            _lectura(2_000_000_000, 0, energia=2**32),
        ])
        proveedor._contadores()
        ocupacion, _ = proveedor._contadores()
        self.assertNotIn("power", ocupacion)

    def test_sin_permisos_no_se_le_pregunta_nada(self):
        proveedor, cliente = self._proveedor([], conectado=False)
        self.assertEqual(proveedor._contadores(), (None, None))
        self.assertEqual(cliente.llamadas, 0)

    def test_una_maquina_sin_contadores_deja_de_preguntarse(self):
        from silux.privileged.client import PmuUnsupported

        proveedor, cliente = self._proveedor([PmuUnsupported("no hay")])
        proveedor._contadores()
        proveedor._contadores()
        proveedor._contadores()
        self.assertEqual(cliente.llamadas, 1)

    def test_un_fallo_suelto_no_lo_da_por_perdido(self):
        # La tubería se puede cortar y el usuario volver a autorizar.
        from silux.privileged.client import HelperError

        proveedor, cliente = self._proveedor([
            HelperError("se cortó"),
            _lectura(1_000_000_000, 0),
            _lectura(2_000_000_000, 250_000_000),
        ])
        proveedor._contadores()
        proveedor._contadores()
        ocupacion, _ = proveedor._contadores()
        self.assertAlmostEqual(ocupacion["i915"]["rcs0-busy"], 25.0)
        self.assertEqual(cliente.llamadas, 3)

    def test_sin_cliente_no_revienta(self):
        from silux.providers.drm import GpuState

        self.assertEqual(GpuState()._contadores(), (None, None))


class TestRepartoDeMotores(unittest.TestCase):
    def test_el_pmu_de_i915_tiene_nombre_fijo(self):
        from silux.providers.drm import _pmu_de

        self.assertEqual(_pmu_de({"driver": "i915"}), "i915")

    def test_el_de_xe_lleva_la_ranura_pci_detras(self):
        from silux.providers.drm import _pmu_de

        self.assertEqual(_pmu_de({"driver": "xe", "pci_slot": "0000:03:00.0"}),
                         "xe_0000_03_00.0")

    def test_las_demas_no_tienen(self):
        from silux.providers.drm import _pmu_de

        for gpu in ({"driver": "amdgpu"}, {"driver": "nvidia"},
                    {"driver": "xe"}, {}):
            with self.subTest(gpu=gpu):
                self.assertIsNone(_pmu_de(gpu))

    def test_el_render_y_el_video_van_a_campos_distintos(self):
        from silux.providers.drm import _uso_intel

        gpu = {"driver": "i915"}
        _uso_intel(gpu, {"i915": {"rcs0-busy": 40.0, "vcs0-busy": 12.0,
                                  "vecs0-busy": 3.0}})
        self.assertEqual(gpu["busy_percent"], 40.0)
        self.assertEqual(gpu["video_busy_percent"], 12.0)

    def test_con_varios_motores_manda_el_mayor_y_no_la_suma(self):
        # Sumar pasaría del 100 % sin que la tarjeta esté a tope de nada.
        from silux.providers.drm import _uso_intel

        gpu = {"driver": "i915"}
        _uso_intel(gpu, {"i915": {"rcs0-busy": 60.0, "ccs0-busy": 70.0}})
        self.assertEqual(gpu["busy_percent"], 70.0)

    def test_sin_contadores_no_se_inventa_un_cero(self):
        from silux.providers.drm import _uso_intel

        gpu = {"driver": "i915"}
        _uso_intel(gpu, None)
        self.assertNotIn("busy_percent", gpu)


class TestElAvisoSigueAlEstado(unittest.TestCase):
    """El mismo hueco se explica distinto según lo que se pueda leer hoy."""

    def _aviso(self, proveedor):
        draft = Draft()
        proveedor._avisar_de_intel(draft, 0)
        return draft.notes[0]

    def test_sin_permisos_pide_permisos(self):
        from silux.model import Need
        from silux.providers.drm import GpuState

        self.assertEqual(self._aviso(GpuState()).need, Need.ROOT)

    def test_una_vez_leido_deja_de_pedirlos(self):
        from silux.model import Need
        from silux.providers.drm import GpuState

        proveedor = GpuState()
        proveedor._pmu_ok = True
        self.assertEqual(self._aviso(proveedor).need, Need.HARDWARE)

    def test_si_el_kernel_no_los_da_lo_dice(self):
        from silux.model import Need
        from silux.providers.drm import GpuState

        proveedor = GpuState()
        proveedor._pmu_mudo = True
        self.assertEqual(self._aviso(proveedor).need, Need.DRIVER)


class TestMotoresDeLaTarjeta(unittest.TestCase):
    """Una gráfica no es un bloque «al 40 %»: son varias unidades.

    Saber cuál va cargada distingue «la tarjeta no da más» de «solo está
    saturado el decodificador de video», que son dos problemas distintos con
    dos soluciones distintas.
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.raiz = pathlib.Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def _motor(self, nombre, capacidades=""):
        carpeta = self.raiz / "engine" / nombre
        carpeta.mkdir(parents=True)
        (carpeta / "capabilities").write_text(capacidades + "\n", encoding="utf-8")

    def test_cada_motor_sale_con_su_funcion(self):
        from silux.providers.drm import _motores_intel

        for nombre in ("rcs0", "bcs0", "vcs0", "vecs0"):
            self._motor(nombre)
        # El modelo guarda la clave; el nombre de la función lo pone la
        # interfaz al pintarla, para que salga en el idioma de quien mira.
        funciones = {m.name: _(m.kind) for m in _motores_intel(self.raiz)}
        self.assertEqual(funciones, {"rcs0": "render", "bcs0": "copia",
                                     "vcs0": "video",
                                     "vecs0": "mejora de video"})

    def test_las_capacidades_no_salen_por_ningun_otro_sitio(self):
        # «hevc» dice que decodifica H.265 por hardware y «sfc» que trae
        # escalador. Ni Vulkan ni OpenGL lo cuentan.
        from silux.providers.drm import _motores_intel

        self._motor("vcs0", "hevc sfc")
        motor = _motores_intel(self.raiz)[0]
        self.assertEqual(motor.capabilities, ("hevc", "sfc"))

    def test_un_motor_desconocido_no_se_inventa_una_funcion(self):
        from silux.providers.drm import _motores_intel

        self._motor("zzz0")
        self.assertIsNone(_motores_intel(self.raiz)[0].kind)

    def test_sin_carpeta_de_motores_no_hay_motores(self):
        from silux.providers.drm import _motores_intel

        self.assertEqual(_motores_intel(self.raiz), ())

    def test_el_uso_del_pmu_se_pega_a_cada_motor(self):
        from silux.model import GpuEngine
        from silux.providers.drm import _uso_intel

        gpu = {"driver": "i915",
               "engines": (GpuEngine(name="rcs0", kind="render"),
                           GpuEngine(name="vcs0", kind="video"))}
        _uso_intel(gpu, {"i915": {"rcs0-busy": 42.0, "vcs0-busy": 0.0}})
        self.assertEqual([m.busy_percent for m in gpu["engines"]], [42.0, 0.0])

    def test_un_motor_parado_marca_cero_y_no_un_hueco(self):
        # Un motor a 0 % no es un dato ausente: es la respuesta.
        from silux.model import GpuEngine
        from silux.providers.drm import _uso_intel

        gpu = {"driver": "i915", "engines": (GpuEngine(name="bcs0"),)}
        _uso_intel(gpu, {"i915": {"bcs0-busy": 0.0}})
        self.assertEqual(gpu["engines"][0].busy_percent, 0.0)


class TestReposoDeLaGrafica(unittest.TestCase):
    """El RC6, que sale de sysfs y no cuesta permisos.

    Es lo único de la telemetría de una Intel que se lee sin elevar nada, así
    que es lo que evita que la página esté del todo vacía antes de autorizar.
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.raiz = pathlib.Path(self._tmp.name)
        (self.raiz / "gt" / "gt0").mkdir(parents=True)
        self.addCleanup(self._tmp.cleanup)

    def _dormido(self, ms):
        (self.raiz / "gt" / "gt0" / "rc6_residency_ms").write_text(f"{ms}\n")

    def test_la_primera_lectura_solo_fija_la_referencia(self):
        from silux.providers.drm import GpuState

        self._dormido(1000)
        self.assertIsNone(GpuState()._reposo("card1", self.raiz))

    def test_la_segunda_da_el_porcentaje(self):
        from silux.providers.drm import GpuState

        proveedor = GpuState()
        with mock.patch("silux.providers.drm.time.monotonic", side_effect=[10.0, 11.0]):
            self._dormido(1000)
            proveedor._reposo("card1", self.raiz)
            self._dormido(1800)          # 800 ms dormida en 1000 de ventana
            self.assertAlmostEqual(proveedor._reposo("card1", self.raiz), 80.0)

    def test_no_se_pasa_del_cien(self):
        from silux.providers.drm import GpuState

        proveedor = GpuState()
        with mock.patch("silux.providers.drm.time.monotonic", side_effect=[10.0, 11.0]):
            self._dormido(0)
            proveedor._reposo("card1", self.raiz)
            self._dormido(1200)
            self.assertEqual(proveedor._reposo("card1", self.raiz), 100.0)

    def test_un_contador_reiniciado_se_salta(self):
        from silux.providers.drm import GpuState

        proveedor = GpuState()
        self._dormido(5000)
        proveedor._reposo("card1", self.raiz)
        self._dormido(10)
        self.assertIsNone(proveedor._reposo("card1", self.raiz))

    def test_sin_contador_no_se_inventa(self):
        from silux.providers.drm import GpuState

        self.assertIsNone(GpuState()._reposo("card1", self.raiz))

    def test_no_es_lo_contrario_del_uso(self):
        # Entre trabajar y dormir hay un término medio —encendida y sin
        # trabajo— que gasta y que no cuenta como reposo. Si esto se juntara,
        # el dato dejaría de significar nada.
        from silux.model import Gpu

        self.assertIn("sleep_percent", Gpu.__dataclass_fields__)
        self.assertIsNone(Gpu(name="x").sleep_percent)


class TestElBotonDePermisos(unittest.TestCase):
    """Sin botón aquí, había que ir a Memoria o Almacenamiento y volver.

    El uso y el consumo de una Intel piden permisos, pero la única forma de
    darlos estaba en otras dos páginas. Quien mira Gráficos leía «requiere
    permisos» sin nada que pulsar, y tenía que adivinar dónde estaba el botón.
    """

    def _pagina_con(self, notes, gpus=None):
        from PySide6.QtWidgets import QApplication
        from silux.model import CpuInfo, Snapshot
        from silux.settings import Preferences
        from silux.ui import theme
        from silux.ui.pages.graphics import GraphicsPage

        app = QApplication.instance() or QApplication([])
        pagina = GraphicsPage(theme.palette_for(app, "dark"), Preferences())
        pagina.apply(Snapshot(monotonic_ns=0, cpu=CpuInfo(),
                              gpus=tuple(gpus or [Gpu(name="UHD 630")]),
                              notes=tuple(notes)))
        return pagina

    def test_el_aviso_de_permisos_trae_su_boton(self):
        nota = Note("gpus.0", Need.ROOT, "Hace falta elevar.")
        self.assertEqual(len(self._pagina_con([nota]).elevation_buttons), 1)

    def test_los_demas_avisos_no(self):
        # Un botón que no arregla nada es peor que ninguno.
        for need in (Need.HARDWARE, Need.DRIVER, Need.PLATFORM, Need.DATABASE):
            with self.subTest(need=need):
                nota = Note("gpus.0", need, "No lo expone.")
                self.assertEqual(self._pagina_con([nota]).elevation_buttons, [])

    def test_pulsarlo_pide_los_permisos(self):
        nota = Note("gpus.0", Need.ROOT, "Hace falta elevar.")
        pagina = self._pagina_con([nota])
        recibido = []
        pagina.elevation_requested.connect(lambda: recibido.append(True))
        pagina.elevation_buttons[0].click()
        self.assertEqual(recibido, [True])

    def test_cuando_ya_hay_permisos_el_boton_desaparece(self):
        pagina = self._pagina_con([Note("gpus.0", Need.ROOT, "Hace falta elevar.")])
        self.assertEqual(len(pagina.elevation_buttons), 1)
        # La nota cambia sola en cuanto el contador contesta.
        pagina.apply(__import__("silux.model", fromlist=["Snapshot"]).Snapshot(
            monotonic_ns=1,
            cpu=__import__("silux.model", fromlist=["CpuInfo"]).CpuInfo(),
            gpus=(Gpu(name="UHD 630"),),
            notes=(Note("gpus.0", Need.HARDWARE, "No lo expone."),)))
        self.assertEqual(pagina.elevation_buttons, [])


class TestElColorDelAviso(unittest.TestCase):
    """Un hecho del hardware no es una avería, y no debe pintarse igual.

    Con la misma banda ámbar para todo, «esta gráfica no trae sensor de
    temperatura» —que no va a cambiar nunca— se lee como una alarma
    permanente, igual de urgente que algo que sí se puede arreglar.
    """

    def test_lo_que_se_arregla_va_en_ambar(self):
        from silux.ui.pages.graphics import NEED_TONES

        for need in (Need.ROOT, Need.DRIVER, Need.DATABASE):
            with self.subTest(need=need):
                self.assertEqual(NEED_TONES[need], "warn")

    def test_lo_que_es_asi_y_ya_esta_va_en_gris(self):
        from silux.ui.pages.graphics import NEED_TONES

        for need in (Need.HARDWARE, Need.PLATFORM):
            with self.subTest(need=need):
                self.assertEqual(NEED_TONES[need], "idle")

    def test_un_fallo_nuestro_se_nota(self):
        from silux.ui.pages.graphics import NEED_TONES

        self.assertEqual(NEED_TONES[Need.ERROR], "bad")

    def test_el_tono_llega_al_widget(self):
        from PySide6.QtWidgets import QApplication
        from silux.ui.widgets import Notice

        QApplication.instance() or QApplication([])
        self.assertEqual(Notice("t", "b", tone="idle").property("tone"), "idle")
        self.assertEqual(Notice("t", "b").property("tone"), "warn")

    def test_la_hoja_de_estilo_define_los_tres(self):
        from PySide6.QtWidgets import QApplication
        from silux.ui import theme

        app = QApplication.instance() or QApplication([])
        hoja = theme.stylesheet(theme.palette_for(app, "dark"))
        self.assertIn('QFrame#Notice[tone="idle"]', hoja)
        self.assertIn('QFrame#Notice[tone="bad"]', hoja)


class TestCodecsDeVideo(unittest.TestCase):
    """Lo que decide si un video se ve gastando dos vatios o quemando la CPU.

    Contrastado contra `vainfo` en una UHD 630: HEVC hasta 10 bits en los dos
    sentidos, H.264 en los dos, VP9 solo de lectura y ningún AV1, que esta
    generación no lo trae.
    """

    def _codecs(self, perfiles):
        """Monta la respuesta de VA-API a mano y la agrupa como el módulo."""
        from silux import gpuapi

        lib = mock.Mock()
        lib.vaMaxNumProfiles.return_value = len(perfiles)
        lib.vaMaxNumEntrypoints.return_value = 8
        lib.vaQueryConfigProfiles.side_effect = self._perfiles(perfiles)
        lib.vaQueryConfigEntrypoints.side_effect = self._entradas(perfiles)
        return gpuapi._va_codecs(lib, 1)

    @staticmethod
    def _perfiles(perfiles):
        def relleno(display, lista, cuantos):
            for i, (perfil, _) in enumerate(perfiles):
                lista[i] = perfil
            cuantos._obj.value = len(perfiles)
            return 0
        return relleno

    @staticmethod
    def _entradas(perfiles):
        def relleno(display, perfil, lista, cuantos):
            puntos = dict(perfiles)[perfil]
            for i, punto in enumerate(puntos):
                lista[i] = punto
            cuantos._obj.value = len(puntos)
            return 0
        return relleno

    def test_decodificar_y_codificar_no_son_lo_mismo(self):
        # 7 = H.264 High; 1 = VLD (decodifica), 6 = EncSlice (codifica).
        solo_lee = self._codecs([(7, [1])])
        self.assertTrue(solo_lee[0]["decode"])
        self.assertFalse(solo_lee[0]["encode"])
        los_dos = self._codecs([(7, [1, 6])])
        self.assertTrue(los_dos[0]["encode"])

    def test_los_perfiles_de_un_mismo_codec_se_juntan(self):
        # 17 = HEVC Main y 18 = HEVC Main 10: un solo códec, no dos.
        codecs = self._codecs([(17, [1]), (18, [1, 6])])
        self.assertEqual(len(codecs), 1)
        self.assertEqual(codecs[0]["name"], "HEVC")
        self.assertEqual(codecs[0]["profiles"], ["Main", "Main 10"])

    def test_la_profundidad_es_la_mayor_que_admita(self):
        codecs = self._codecs([(17, [1]), (18, [1])])
        self.assertEqual(codecs[0]["bits"], 10)

    def test_un_punto_de_entrada_que_no_es_ni_leer_ni_escribir_no_cuenta(self):
        # 10 = VideoProc, 12 = Stats: postproceso y estadísticas.
        self.assertEqual(self._codecs([(7, [10, 12])]), [])

    def test_un_perfil_que_no_esta_en_la_tabla_se_ignora(self):
        # Antes que inventarse un nombre, no enseñarlo.
        self.assertEqual(self._codecs([(999, [1])]), [])

    def test_se_ordenan_por_lo_que_la_gente_busca(self):
        from silux.gpuapi import VA_ORDEN

        # 0 = MPEG-2 Simple, 32 = AV1 Profile 0, 7 = H.264 High.
        nombres = [c["name"] for c in self._codecs([(0, [1]), (32, [1]), (7, [1])])]
        self.assertEqual(nombres, ["AV1", "H.264", "MPEG-2"])
        self.assertLess(VA_ORDEN.index("AV1"), VA_ORDEN.index("JPEG"))

    def test_cada_familia_conocida_tiene_su_nombre(self):
        from silux.gpuapi import VA_PERFILES

        familias = {familia for familia, _, _ in VA_PERFILES.values()}
        for esperada in ("H.264", "HEVC", "AV1", "VP9", "VP8", "MPEG-2"):
            with self.subTest(codec=esperada):
                self.assertIn(esperada, familias)


class TestRepartoDeCodecs(unittest.TestCase):
    """VA-API se abre sobre un nodo concreto, así que no hay que adivinar.

    Es lo contrario de lo que pasa con OpenGL, que no dice de qué tarjeta
    habla y obligó a casar por el nombre del fabricante.
    """

    def test_cada_tarjeta_recibe_los_de_su_nodo(self):
        from silux.providers.gpu_apis import _codecs_de

        respuesta = [{"node": "renderD129",
                      "codecs": [{"name": "AV1", "decode": True, "encode": False,
                                  "bits": 10, "profiles": ["Profile 0"]}]}]
        with mock.patch("silux.providers.gpu_apis.amdgpu.render_node",
                        return_value="/dev/dri/renderD129"):
            codecs = _codecs_de({"pci_slot": "0000:03:00.0"}, respuesta)
        self.assertEqual(len(codecs), 1)
        self.assertEqual(codecs[0].name, "AV1")
        self.assertTrue(codecs[0].decode)
        self.assertFalse(codecs[0].encode)

    def test_los_de_otra_tarjeta_no_se_le_cuelgan(self):
        from silux.providers.gpu_apis import _codecs_de

        respuesta = [{"node": "renderD128", "codecs": [{"name": "AV1"}]}]
        with mock.patch("silux.providers.gpu_apis.amdgpu.render_node",
                        return_value="/dev/dri/renderD129"):
            self.assertEqual(_codecs_de({"pci_slot": "0000:03:00.0"}, respuesta), ())

    def test_sin_ranura_no_se_atribuye_nada(self):
        from silux.providers.gpu_apis import _codecs_de

        self.assertEqual(_codecs_de({}, [{"node": "renderD128"}]), ())


class TestAnchoDeLasColumnas(unittest.TestCase):
    """La columna se mide al montarla, cuando aún no hay nada que medir.

    «Uso» se quedaba con el ancho de su cabecera —tres letras— y enseñaba
    «12…» en vez de «12.4 %». El mismo fallo que ya tenía el árbol de
    sensores, y se arregla igual: al llegar un valor la columna se ensancha;
    nunca se encoge, o la tabla bailaría a cada muestreo.
    """

    def _tabla(self):
        from PySide6.QtWidgets import QApplication
        from silux.ui.widgets import Table

        QApplication.instance() or QApplication([])
        return Table(("Motor", "Uso"), numeric=(False, True))

    def test_la_columna_se_ensancha_con_el_valor(self):
        tabla = self._tabla()
        tabla.set_rows([("rcs0", "0 %")])
        estrecha = tabla._anchos[1]
        tabla.set_rows([("rcs0", "100.0 %")])
        self.assertGreater(tabla._anchos[1], estrecha)

    def test_pero_no_se_encoge_cuando_el_valor_baja(self):
        tabla = self._tabla()
        tabla.set_rows([("rcs0", "100.0 %")])
        ancha = tabla._anchos[1]
        tabla.set_rows([("rcs0", "0 %")])
        self.assertEqual(tabla._anchos[1], ancha)

    def test_un_valor_desmesurado_no_estira_la_tabla_sin_fin(self):
        tabla = self._tabla()
        tabla.set_rows([("rcs0", "x" * 4000)])
        self.assertLess(tabla._anchos[1], 1000)


class TestCuadrosDeLaGrafica(unittest.TestCase):
    """Las seis cifras vivas de arriba de la página de Gráficos."""

    def _seccion(self, gpu):
        from PySide6.QtWidgets import QApplication
        from silux.model import CpuInfo, Snapshot
        from silux.settings import Preferences
        from silux.ui import theme
        from silux.ui.pages.graphics import GraphicsPage

        app = QApplication.instance() or QApplication([])
        # La página se guarda en la prueba: sin una referencia viva, el
        # recolector se lleva los QLabel de dentro antes de mirarlos.
        self.pagina = GraphicsPage(theme.palette_for(app, "dark"), Preferences())
        self.pagina.apply(Snapshot(monotonic_ns=0, cpu=CpuInfo(), gpus=(gpu,)))
        return self.pagina._sections[0]

    def test_la_frecuencia_del_nucleo_sale_en_megahercios(self):
        seccion = self._seccion(Gpu(
            name="RX 9070 XT",
            clocks=GpuClocks(core_hz=2_609_000_000, core_max_hz=3_000_000_000),
        ))
        self.assertEqual(seccion.tile_clock.value.text(), "2609")

    def test_el_reloj_de_memoria_y_su_tasa_de_datos_no_son_lo_mismo(self):
        """Una GDDR6 a 1258 MHz mueve 20 Gbps: dieciséis transferencias por
        ciclo. En el detalle va la efectiva, que es la que se compara con lo
        que anuncia el fabricante."""
        seccion = self._seccion(Gpu(
            name="RX 9070 XT",
            clocks=GpuClocks(core_hz=2_609_000_000,
                             memory_hz=1_258_000_000,
                             memory_effective_hz=2_517_000_000),
        ))
        self.assertIn("2.52 GHz", seccion.tile_clock.detail.full_text())

    def test_el_bus_de_memoria_no_es_la_vram_ocupada(self):
        """Una tarjeta con la VRAM llena y el bus parado tiene datos cargados
        y no los está tocando: son dos preguntas distintas."""
        seccion = self._seccion(Gpu(
            name="RX 9070 XT",
            memory_busy_percent=21.0,
            memory=GpuMemory(total_bytes=17_095_983_104,
                             used_bytes=15_000_000_000,
                             bandwidth_bytes=644_096_000_000),
        ))
        self.assertEqual(seccion.tile_membus.value.text(), "21")
        self.assertEqual(seccion.tile_vram.value.text(), "88")

    def test_el_porcentaje_del_bus_dice_contra_que_se_compara(self):
        """Un 21 % a secas no dice si son megas o gigas por segundo."""
        seccion = self._seccion(Gpu(
            name="RX 9070 XT", memory_busy_percent=21.0,
            memory=GpuMemory(bandwidth_bytes=644_096_000_000),
        ))
        self.assertIn("644", seccion.tile_membus.detail.full_text())

    def test_una_grafica_que_no_publica_nada_no_inventa_ceros(self):
        """Una Intel sin permisos deja los cuadros a «—», no a cero: no leer
        un dato no es que valga cero."""
        seccion = self._seccion(Gpu(name="UHD 630"))
        for nombre in ("tile_clock", "tile_membus"):
            with self.subTest(cuadro=nombre):
                cuadro = getattr(seccion, nombre)
                self.assertEqual(cuadro.value.text(), render.DASH)
                self.assertFalse(cuadro.detail.isVisible())


class TestGraficaSinDriver(unittest.TestCase):
    """Cuando el kernel se queda en el framebuffer de respaldo.

    Salió de la captura de un usuario: una ficha titulada «Gráfica 0» con
    driver `simple-framebuffer` y absolutamente todos los campos a un guion,
    que se lee como que el programa está roto. No lo estaba: ese driver es el
    respaldo que pone el kernel para tener imagen, no sabe nada del chip que
    hay debajo, y la ficha no tenía de dónde sacar ni el nombre.

    El bus PCI sí enumera la tarjeta aunque nadie sepa hablarle, y de ahí sale
    al menos quién es.
    """

    def test_el_framebuffer_generico_no_se_confunde_con_un_driver(self):
        from silux.providers.drm import FRAMEBUFFER_GENERICO

        for falso in ("simple-framebuffer", "simpledrm", "efifb", "vesafb"):
            self.assertIn(falso, FRAMEBUFFER_GENERICO)
        for real in ("amdgpu", "i915", "nouveau", "nvidia", "xe", "radeon"):
            self.assertNotIn(real, FRAMEBUFFER_GENERICO)

    def test_una_grafica_del_bus_se_identifica_sin_driver(self):
        """El bus da vendor y device; `pciids` los convierte en un nombre."""
        from silux import pciids

        # Los de una RTX 3050 Mobile, que es de las que llegaron en capturas.
        nombres = pciids.lookup([(0x10DE, 0x25A2)])
        marca, modelo = nombres[(0x10DE, 0x25A2)]
        self.assertIn("NVIDIA", marca)
        self.assertIn("3050", modelo)

    def test_se_reconocen_las_dos_clases_pci_de_una_grafica(self):
        """La 3D controller es la dedicada de un portátil, sin salida propia."""
        from silux.providers.drm import CLASES_GRAFICAS

        self.assertIn(0x030000, CLASES_GRAFICAS)
        self.assertIn(0x030200, CLASES_GRAFICAS)


class TestNucleosCudaDeNvidia(unittest.TestCase):
    """NVML no contesta lo mismo en todas las tarjetas.

    Dos capturas de dos usuarios, el mismo día: una GTX 1660 Ti diciendo
    «1536 núcleos CUDA», que son los suyos, y una RTX 4060 diciendo «24», que
    son sus multiprocesadores —lleva 3072—. La función es la misma en las dos,
    `nvmlDeviceGetNumGpuCores`, y lo que devuelve depende de la generación.
    """

    def test_lo_que_ya_son_nucleos_se_deja_como_esta(self):
        from silux.providers.nvidia import _nucleos_cuda

        self.assertEqual(_nucleos_cuda({"codename": "TU116"}, 1536), 1536)

    def test_los_multiprocesadores_se_convierten_a_nucleos(self):
        from silux.providers.nvidia import _nucleos_cuda

        # RTX 4060: 24 multiprocesadores de Ada, 128 núcleos cada uno.
        self.assertEqual(_nucleos_cuda({"codename": "AD107"}, 24), 3072)
        # RTX 3050 Mobile: 16 de Ampere.
        self.assertEqual(_nucleos_cuda({"codename": "GA107M"}, 16), 2048)

    def test_una_arquitectura_desconocida_no_se_inventa(self):
        """Antes que un número creíble y falso, ninguno."""
        from silux.providers.nvidia import _nucleos_cuda

        self.assertIsNone(_nucleos_cuda({"codename": "XX999"}, 24))
        self.assertIsNone(_nucleos_cuda({}, 24))

    def test_sin_dato_sigue_sin_haber_dato(self):
        from silux.providers.nvidia import _nucleos_cuda

        self.assertIsNone(_nucleos_cuda({"codename": "AD107"}, None))


class TestSalidasLibres(unittest.TestCase):
    """Los conectores sin nada enchufado no ocupan una fila cada uno.

    Un MacBook Air de 11 pulgadas enseñaba cuatro filas seguidas —DP-1, DP-2,
    HDMI-A-1, HDMI-A-2— con los seis campos a guiones, y solo la quinta, su
    propia pantalla, con datos. Cuatro quintas partes de la tabla eran salidas
    que el chip expone y esa carcasa no trae.
    """

    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication

        cls.app = QApplication.instance() or QApplication([])

    def _pagina(self, salidas):
        import dataclasses

        from silux.collector import Collector
        from silux.settings import Preferences
        from silux.ui import theme
        from silux.ui.pages.graphics import GraphicsPage

        theme.set_density("normal", "normal")
        foto = Collector().sample()
        if not foto.gpus:
            self.skipTest("esta máquina no tiene ninguna gráfica")
        gpu = dataclasses.replace(foto.gpus[0], displays=tuple(salidas))
        pagina = GraphicsPage(theme.palette_for(self.app, "dark"),
                              Preferences(font_scale="normal").normalized())
        pagina.apply(dataclasses.replace(foto, gpus=(gpu,)))
        return pagina

    @staticmethod
    def _linea_de_libres(pagina):
        """La etiqueta vive en la tarjeta de cada gráfica, no en la página."""
        from silux.ui.pages.graphics import GpuSection

        bloque = pagina.findChildren(GpuSection)[0]
        return bloque.displays_free

    def test_las_libres_se_juntan_en_una_linea(self):
        from silux.model import Display
        from silux.ui.widgets import Table

        pagina = self._pagina([
            Display(connector="DP-1", connected=False),
            Display(connector="DP-2", connected=False),
            Display(connector="HDMI-A-1", connected=False),
            Display(connector="eDP-1", connected=True, width=1366, height=768),
        ])
        tabla = pagina.findChildren(Table)[-1]
        self.assertEqual(len(tabla._cells), 1, "solo la conectada va en la tabla")
        self.assertEqual(tabla._cells[0][0].full_text(), "eDP-1")

        etiqueta = self._linea_de_libres(pagina)
        texto = etiqueta.text()
        for suelta in ("DP-1", "DP-2", "HDMI-A-1"):
            self.assertIn(suelta, texto)
        self.assertNotIn("eDP-1", texto)

    def test_sin_ninguna_libre_no_sobra_una_linea_vacia(self):
        from silux.model import Display

        pagina = self._pagina([Display(connector="DP-1", connected=True)])
        self.assertEqual(self._linea_de_libres(pagina).text(), "")


class TestLaIntegradaDeUnaApu(unittest.TestCase):
    """«HawkPoint2» es un nombre en clave, no el nombre de una gráfica.

    Lo trajo la captura de un usuario con un Ryzen 7 7445HS: su Radeon 740M
    salía titulada «HawkPoint2» y con el nombre en clave vacío. `pci.ids` llama
    así al 1002:1901, sin los corchetes donde suele poner el nombre comercial,
    y de ahí no se puede sacar otra cosa.

    Quien sí lo sabe es el procesador, que se llama «AMD Ryzen 7 7445HS w/
    Radeon 740M Graphics». El código que lo aprovecha estaba escrito desde
    hacía tiempo y no se ejecutó nunca: usaba `draft` sin recibirlo, o sea un
    NameError, y como la condición de delante corta cuando el nombre lleva
    «Radeon» dentro, en las máquinas con tarjeta dedicada no saltaba jamás.
    Solo reventaba en las APU, que son justo las que ese código venía a
    arreglar. No había test que recorriera ese camino; este es ese test.
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.raiz = pathlib.Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def _dispositivo(self, vendor=0x1002, device=0x1901):
        """Un nodo PCI con lo justo para que `_identidad` lo lea."""
        for nombre, valor in (("vendor", vendor), ("device", device),
                              ("subsystem_vendor", 0x1043),
                              ("subsystem_device", 0x1504),
                              ("revision", 0xC1)):
            (self.raiz / nombre).write_text(f"0x{valor:04x}\n", encoding="utf-8")
        return self.raiz

    def _draft(self, marca):
        from silux.providers.base import Draft

        draft = Draft()
        draft.types["general"] = {"brand": marca}
        return draft

    def _con_pciids(self, nombre):
        """Fija lo que responde la base de datos de PCI.

        Sin esto el test depende de qué `pci.ids` tenga puesto quien lo
        ejecuta: el de Ubuntu 22.04 todavía no conoce el 1002:1901 y devuelve
        nada, así que el nombre en clave salía vacío y el test fallaba en el
        CI por lo mismo que este archivo está arreglando en otros sitios.
        """
        from unittest import mock

        from silux.providers import drm

        return mock.patch.object(drm.pciids, "lookup",
                                 return_value={(0x1002, 0x1901): ("AMD", nombre)})

    def test_el_nombre_comercial_sale_de_la_marca_del_procesador(self):
        from silux.providers.drm import DrmGpus

        gpu = {}
        draft = self._draft("AMD Ryzen 7 7445HS w/ Radeon 740M Graphics")
        with self._con_pciids("HawkPoint2"):
            DrmGpus._identidad(gpu, self._dispositivo(), draft)

        self.assertEqual(gpu["name"], "Radeon 740M")
        self.assertEqual(gpu["codename"], "HawkPoint2")

    def test_una_dedicada_conserva_el_nombre_que_ya_tenia(self):
        """Si ya pone «Radeon» algo, ese nombre salió de pci.ids y es más
        concreto que el de la cadena del procesador.

        El caso de verdad: un portátil con integrada y tarjeta aparte, donde
        la marca del procesador nombra la suya y la dedicada no es esa.
        """
        from silux.providers.drm import DrmGpus

        gpu = {}
        draft = self._draft("AMD Ryzen 7 7445HS w/ Radeon 740M Graphics")
        with self._con_pciids("Radeon RX 7600M XT"):
            DrmGpus._identidad(gpu, self._dispositivo(), draft)

        self.assertEqual(gpu["name"], "Radeon RX 7600M XT")

    def test_un_procesador_sin_integrada_no_inventa_ninguna(self):
        """Sin «w/ Radeon ... Graphics» en la marca no hay de dónde sacarlo,
        y el nombre en clave se queda como está en vez de rellenarse."""
        from silux.providers.drm import DrmGpus

        gpu = {}
        draft = self._draft("AMD Ryzen 7 5800X3D 8-Core Processor")
        with self._con_pciids("HawkPoint2"):
            DrmGpus._identidad(gpu, self._dispositivo(), draft)

        self.assertEqual(gpu["name"], "HawkPoint2")

    def test_identidad_recibe_el_draft_que_necesita(self):
        """La firma es lo que faltaba, así que se vigila la firma.

        Con `draft` fuera de ella el fallo no es un dato mal puesto: es un
        NameError en mitad de la detección, y solo en los equipos que no
        están aquí.
        """
        import inspect

        from silux.providers.drm import DrmGpus

        parametros = inspect.signature(DrmGpus._identidad).parameters
        self.assertIn("draft", parametros,
                      "_identidad usa draft; tiene que recibirlo")
