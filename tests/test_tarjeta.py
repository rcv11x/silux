"""La imagen del equipo que se pega en un chat.

Lo que más se prueba aquí es lo mismo que en el informe: lo que *no* sale. Esto
existe precisamente porque la gente comparte capturas de la ventana, y una
captura lleva dentro el nombre del equipo, las direcciones y los números de
serie sin que nadie se acuerde.
"""

import os
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from silux.model import (Board, Clocks, CpuInfo, CpuType, Disk, Gpu, GpuMemory,
                         Memory, NetworkInterface, Snapshot, System)

EQUIPO = "equipo-de-pruebas"
DIRECCION = "192.0.2.11"
MAC = "00:00:5e:00:53:af"
SERIE = "0000000000000000"


def _snapshot(**cambios) -> Snapshot:
    base = dict(
        monotonic_ns=0,
        cpu=CpuInfo(types=(CpuType(key="general", label="general",
                                   brand="AMD Ryzen 7 5800X3D 8-Core Processor",
                                   cores=8, threads=16, codename="Vermeer",
                                   clocks=Clocks(base_hz=3_400_000_000,
                                                 max_turbo_hz=4_550_000_000)),)),
        board=Board(vendor="Gigabyte", name="X570 AORUS ELITE"),
        system=System(distribution="CachyOS", kernel="Linux 7.2.0",
                      hostname=EQUIPO, desktop="KDE",
                      memory=Memory(total_bytes=32 * 1024**3)),
        gpus=(Gpu(index=0, name="Radeon RX 9070 XT", vendor="AMD",
                  unique_id=SERIE, driver="amdgpu",
                  memory=GpuMemory(total_bytes=16 * 1024**3, kind="GDDR6")),),
        network=(NetworkInterface(name="enp6s0", up=True, ipv4=DIRECCION,
                                  mac=MAC),),
        disks=(Disk(name="nvme0n1", model="SN850X", serial=SERIE,
                    size_bytes=1000 * 1000**3, kind="NVMe"),),
    )
    base.update(cambios)
    return Snapshot(**base)


class TestLoQueNoSale(unittest.TestCase):
    """Una imagen para pegar en público no lleva de quién es el equipo."""

    def _texto_de_las_filas(self, foto):
        from silux.privacidad import anonimizar
        from silux.ui import tarjeta

        filas = tarjeta._fila(anonimizar(foto))
        return " ".join(" ".join(fila) for fila in filas)

    def test_ni_el_nombre_del_equipo_ni_las_direcciones(self):
        texto = self._texto_de_las_filas(_snapshot())
        for secreto in (EQUIPO, DIRECCION, MAC):
            self.assertNotIn(secreto, texto)

    def test_ni_el_numero_de_serie_de_la_grafica(self):
        foto = _snapshot(gpus=(Gpu(index=0, name="Radeon RX 9070 XT",
                                   vendor="AMD", unique_id="GPU-123456"),))
        self.assertNotIn("GPU-123456", self._texto_de_las_filas(foto))

    def test_es_anonima_sin_pedirlo(self):
        """Lo seguro tiene que ser lo que pasa si nadie toca nada."""
        from silux.ui import tarjeta

        with mock.patch.object(tarjeta, "anonimizar",
                               side_effect=tarjeta.anonimizar) as tapar:
            tarjeta.dibujar(_snapshot(), _paleta())
        tapar.assert_called_once()


class TestLoQueSiSale(unittest.TestCase):
    """El hardware, que es de lo que va la imagen."""

    def _filas(self, foto=None):
        from silux.ui import tarjeta

        return tarjeta._fila(foto or _snapshot())

    def test_el_procesador_sin_la_coletilla(self):
        etiqueta, valor, detalle = self._filas()[0]
        self.assertEqual(valor, "AMD Ryzen 7 5800X3D")
        self.assertIn("8", detalle)          # núcleos
        self.assertIn("Vermeer", detalle)

    def test_la_grafica_con_su_memoria(self):
        fila = next(f for f in self._filas() if "Radeon" in f[1])
        self.assertIn("GDDR6", fila[2])

    def test_los_discos_se_resumen_por_tipo(self):
        discos = (Disk(name="nvme0n1", size_bytes=10**12, kind="NVMe"),
                  Disk(name="sda", size_bytes=2 * 10**12, kind="HDD"),
                  Disk(name="sdb", size_bytes=10**12, kind="HDD"))
        fila = next(f for f in self._filas(_snapshot(disks=discos))
                    if "TB" in f[1])
        self.assertIn("2 × HDD", fila[2])
        self.assertIn("1 × NVMe", fila[2])

    def test_un_equipo_pelado_no_revienta(self):
        from silux.ui import tarjeta

        vacio = Snapshot(monotonic_ns=0, cpu=CpuInfo(), board=Board(),
                         system=System())
        imagen = tarjeta.dibujar(vacio, _paleta())
        self.assertFalse(imagen.isNull())

    def test_la_imagen_sale_del_tamaño_de_siempre(self):
        """Fijo para que dos tarjetas de dos equipos se puedan comparar."""
        from silux.ui import tarjeta

        self.assertEqual(tarjeta.dibujar(_snapshot(), _paleta()).width(),
                         tarjeta.ANCHO)

    def test_crece_con_las_filas_y_no_las_recorta(self):
        from silux.ui import tarjeta

        una = tarjeta.dibujar(
            Snapshot(monotonic_ns=0, cpu=CpuInfo(), board=Board(),
                     system=System(distribution="CachyOS")), _paleta())
        muchas = tarjeta.dibujar(_snapshot(), _paleta())
        self.assertGreater(muchas.height(), una.height())


def _paleta():
    from PySide6.QtWidgets import QApplication

    from silux.ui import theme

    QApplication.instance() or QApplication([])
    return theme.palette_for(QApplication.instance(), "dark", "azul")
