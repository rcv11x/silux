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

from silux import render
from silux.model import Display, PcieLink, GpuMemory
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
