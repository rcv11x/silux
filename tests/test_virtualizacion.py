"""Que un equipo virtual se presente como lo que es.

Llegó la captura de un i5-10500T con «2 núcleos · 2 hilos · 2 sockets» y la
L3 de 12 MB contada dos veces, de alguien convencido de que el programa
contaba mal los núcleos. No contaba mal: era una VM de VMware con dos vCPU, y
esa es la topología que le había dado el hipervisor —la pieza de abajo trae
seis núcleos, doce hilos y un solo socket—. El dato que lo explica estaba
detectado desde el primer día, el bit «hypervisor» de CPUID, y no salía ni en
la cabecera de la ficha ni en el informe, que es justamente el archivo que se
pide para diagnosticar.
"""

import dataclasses
import pathlib
import struct
import tempfile
import unittest
from unittest import mock

from silux import render, report
from silux.model import (Clocks, CpuInfo, CpuType, Need, Note, Snapshot, System)
from silux.providers import sysfs_cpu
from silux.providers.base import Draft
from silux.providers.cpuid_x86 import CpuidIdentity
from silux.rawcpuid import CpuidReader


def _registros(firma: bytes) -> tuple[int, int, int, int]:
    """Los cuatro registros tal y como los deja la hoja 0x40000000."""
    ebx, ecx, edx = struct.unpack("<III", firma.ljust(12, b"\x00"))
    return (0x4000_0001, ebx, ecx, edx)


class ReaderFalso:
    """Lo justo que `hypervisor_id` necesita: contestar a una hoja.

    El método es el de verdad, así que lo que se prueba es el desempaquetado
    real de los registros y no una copia suya escrita en el test.
    """

    def __init__(self, regs):
        self._regs = regs

    def __call__(self, leaf, subleaf=0):
        return self._regs

    hypervisor_id = CpuidReader.hypervisor_id


def _tipo(**cambios) -> CpuType:
    base = dict(key="general", label="general",
                brand="Intel(R) Core(TM) i5-10500T CPU @ 2.30GHz",
                codename="Core i5 (Comet Lake-S)", socket="LGA 1200",
                technology="14++ nm", architecture="x86_64",
                cores=2, threads=2, clocks=Clocks(base_hz=2_300_000_000))
    base.update(cambios)
    return CpuType(**base)


def _foto(tipo: CpuType) -> Snapshot:
    return Snapshot(monotonic_ns=0,
                    cpu=CpuInfo(types=(tipo,), sockets=2),
                    system=System(distribution="Debian GNU/Linux 13",
                                  kernel="Linux 6.12.101+deb13-amd64"))


class TestFirmaDelHipervisor(unittest.TestCase):
    """La hoja 0x40000000 y su tabla."""

    @staticmethod
    def _quien(firma: bytes):
        return CpuidIdentity._hipervisor(ReaderFalso(_registros(firma)))

    def test_vmware(self):
        self.assertEqual(self._quien(b"VMwareVMware"), "VMware")

    def test_kvm_lleva_relleno_de_ceros(self):
        self.assertEqual(self._quien(b"KVMKVMKVM"), "KVM")

    def test_hyperv_lleva_un_espacio_dentro(self):
        self.assertEqual(self._quien(b"Microsoft Hv"), "Hyper-V")

    def test_uno_que_no_esta_en_la_tabla_se_devuelve_tal_cual(self):
        # Vale como identificación aunque no tenga nombre bonito, y llega al
        # informe, que es de donde puede salir la entrada que falta.
        self.assertEqual(self._quien(b"AcmeHypervis"), "AcmeHypervis")

    def test_lo_que_no_es_texto_no_es_una_firma(self):
        # Sin hipervisor debajo, CPUID contesta a una hoja que no conoce con
        # el contenido de la más alta que tenga: números, no letras.
        self.assertIsNone(CpuidIdentity._hipervisor(ReaderFalso((0x16, 0, 0, 0))))
        self.assertIsNone(
            CpuidIdentity._hipervisor(ReaderFalso((0x16, 0x0001_0002, 0x03, 0x04))))


class TestElTextoDeLaInsignia(unittest.TestCase):
    def test_con_hipervisor_conocido_se_nombra(self):
        self.assertEqual(render.virtual_machine(
            _tipo(in_virtual_machine=True, hypervisor="VMware")),
            "Máquina virtual · VMware")

    def test_sin_identificar_se_dice_igual(self):
        self.assertEqual(render.virtual_machine(_tipo(in_virtual_machine=True)),
                         "Máquina virtual")

    def test_en_hierro_de_verdad_no_hay_nada_que_decir(self):
        self.assertIsNone(render.virtual_machine(_tipo()))


class TestLaFichaLoEnseña(unittest.TestCase):
    """Montando la página de verdad: lo que no se ve no está hecho."""

    def setUp(self):
        try:
            from PySide6.QtWidgets import QApplication
        except ImportError:                                # pragma: no cover
            self.skipTest("PySide6 no está instalado")
        from silux.settings import Preferences
        from silux.ui import theme
        from silux.ui.pages.cpu import CpuPage
        from silux.ui.pages.home import HomePage

        app = QApplication.instance() or QApplication([])
        theme.set_density("normal", "normal")
        paleta = theme.palette_for(app, "dark")
        ajustes = Preferences(font_scale="normal").normalized()
        self.cpu = CpuPage(paleta, ajustes)
        self.inicio = HomePage(paleta, ajustes)

    @staticmethod
    def _insignias(pagina) -> list[str]:
        return [w.text() for w in pagina.badges._widgets]

    def test_la_ficha_de_cpu_avisa_y_lo_pone_delante(self):
        self.cpu.apply(_foto(_tipo(in_virtual_machine=True, hypervisor="VMware")))
        insignias = self._insignias(self.cpu)
        self.assertEqual(insignias[0], "Máquina virtual · VMware")
        # Y sin perder lo que ya había.
        self.assertIn("Core i5 (Comet Lake-S)", insignias)

    def test_en_hierro_la_ficha_sigue_empezando_por_el_nombre_en_clave(self):
        self.cpu.apply(_foto(_tipo()))
        self.assertEqual(self._insignias(self.cpu)[0], "Core i5 (Comet Lake-S)")

    def test_la_portada_lo_dice_donde_se_entra(self):
        self.inicio.apply(_foto(_tipo(in_virtual_machine=True, hypervisor="VMware")))
        self.assertIn("Máquina virtual · VMware", self._insignias(self.inicio))

    def test_la_portada_de_un_equipo_real_no_lo_dice(self):
        self.inicio.apply(_foto(_tipo()))
        self.assertNotIn("Máquina virtual", " ".join(self._insignias(self.inicio)))


class TestElInformeLoDice(unittest.TestCase):
    """Es el primer archivo que se pide cuando algo sale raro."""

    def test_la_cabecera_nombra_al_hipervisor(self):
        texto = report.build(_foto(_tipo(in_virtual_machine=True, hypervisor="VMware")))
        self.assertIn("| Máquina virtual | VMware |", texto)

    def test_sin_identificar_lo_dice_igual(self):
        texto = report.build(_foto(_tipo(in_virtual_machine=True)))
        self.assertIn("| Máquina virtual | sí, hipervisor sin identificar |", texto)

    def test_un_equipo_real_no_gana_una_fila(self):
        self.assertNotIn("Máquina virtual", report.build(_foto(_tipo())))


class TestElAvisoDeFrecuencia(unittest.TestCase):
    """Ámbar es para lo que se puede arreglar; una VM no lo es."""

    def _nota(self, en_vm: bool):
        with tempfile.TemporaryDirectory() as tmp:
            # Un /sys sin cpufreq: es lo que hay dentro de una máquina virtual.
            (pathlib.Path(tmp) / "cpu0").mkdir()
            draft = Draft()
            draft.logical = {0: {}}
            draft.types = {"general": {"cpus": [0], "in_virtual_machine": en_vm}}
            with mock.patch.object(sysfs_cpu, "SYS_CPU", tmp):
                sysfs_cpu.SysfsClocks().collect(draft)
        notas = [n for n in draft.notes if n.path == "cpu.clocks.current_hz"]
        self.assertEqual(len(notas), 1, "el aviso no salió")
        return notas[0]

    def test_dentro_de_una_vm_no_manda_a_cargar_un_modulo(self):
        nota = self._nota(en_vm=True)
        self.assertEqual(nota.need, Need.HARDWARE)
        self.assertIn("hipervisor", nota.message)

    def test_en_hierro_sigue_siendo_un_driver_que_falta(self):
        self.assertEqual(self._nota(en_vm=False).need, Need.DRIVER)


class TestElColorDelAviso(unittest.TestCase):
    """Ámbar es una promesa: «esto se puede arreglar».

    La tabla que reparte los tonos estaba escrita solo en Gráficos, así que
    las otras tres páginas con avisos pintaban de ámbar hasta lo que no
    depende de nadie. Reclasificar el aviso de la frecuencia no se habría
    notado en pantalla: seguiría igual de urgente que un permiso por dar.
    """

    def setUp(self):
        try:
            from PySide6.QtWidgets import QApplication
        except ImportError:                                # pragma: no cover
            self.skipTest("PySide6 no está instalado")
        from silux.settings import Preferences
        from silux.ui import theme
        from silux.ui.pages.cpu import CpuPage

        app = QApplication.instance() or QApplication([])
        theme.set_density("normal", "normal")
        self.pagina = CpuPage(theme.palette_for(app, "dark"),
                              Preferences(font_scale="normal").normalized())

    def _tono(self, need: Need) -> str:
        nota = Note(path="cpu.clocks.current_hz", need=need, message="da igual")
        foto = dataclasses.replace(_foto(_tipo()), notes=(nota,))
        self.pagina.apply(foto)
        host = self.pagina._notices_host
        self.assertEqual(host.count(), 1, "el aviso no llegó a la página")
        return host.itemAt(0).widget().property("tone")

    def test_lo_que_no_se_puede_arreglar_no_va_en_ambar(self):
        self.assertEqual(self._tono(Need.HARDWARE), "idle")
        self.assertEqual(self._tono(Need.PLATFORM), "idle")

    def test_lo_accionable_sigue_en_ambar(self):
        self.assertEqual(self._tono(Need.ROOT), "warn")
        self.assertEqual(self._tono(Need.DRIVER), "warn")

    def test_un_fallo_nuestro_va_en_rojo(self):
        self.assertEqual(self._tono(Need.ERROR), "bad")


if __name__ == "__main__":
    unittest.main()
