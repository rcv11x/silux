"""El informe que se adjunta al reportar un fallo.

Lo que más se prueba aquí es lo que *no* sale. El informe está pensado para
pegarlo en un issue público, así que un descuido que deje una MAC o el nombre
del equipo dentro no es un fallo de formato: es publicar los datos de quien
pedía ayuda.
"""

import unittest
from unittest import mock

from silux import report
from silux.model import (Board, Clocks, CpuInfo, CpuType, Gpu, GpuMemory, Need,
                        NetworkInterface, Note, Sensor, SensorKind, Snapshot,
                        System)

# Inventados a propósito, y de los rangos que existen para esto: 192.0.2.0/24
# es la TEST-NET-1 de la RFC 5737 y 00:00:5E:00:53:xx el bloque que la RFC 7042
# reserva para documentación. Antes eran los del equipo del autor, que es una
# forma curiosa de publicarlos desde el test que comprueba que no se publican.
EQUIPO = "equipo-de-pruebas"
DIRECCION = "192.0.2.11"
MAC = "00:00:5e:00:53:af"
SERIE = "0000000000000000"


def _snapshot(**cambios) -> Snapshot:
    base = dict(
        monotonic_ns=0,
        cpu=CpuInfo(types=(CpuType(key="general", label="general", brand="AMD Ryzen 7 5800X3D",
                                   cores=8, threads=16,
                                   clocks=Clocks(base_hz=3_401_000_000)),)),
        board=Board(vendor="Gigabyte", name="X570 AORUS ELITE"),
        system=System(distribution="CachyOS", kernel="Linux 7.2.0",
                      hostname=EQUIPO, desktop="KDE"),
        gpus=(Gpu(index=0, name="Radeon RX 9070 XT", vendor="AMD",
                  unique_id=SERIE, memory=GpuMemory(total_bytes=16 * 1024**3)),),
        network=(NetworkInterface(name="enp6s0", up=True, ipv4=DIRECCION, mac=MAC,
                                  speed_mbps=2500, duplex="full"),),
        sensors=(Sensor(key="k/1", chip="k10temp", device="AMD Ryzen 7 5800X3D",
                        label="Tctl", kind=SensorKind.TEMPERATURE, value=45.0),),
    )
    base.update(cambios)
    return Snapshot(**base)


class TestPrivacidad(unittest.TestCase):
    def test_por_omision_no_salen_los_datos_del_equipo(self):
        texto = report.build(_snapshot())
        for secreto in (EQUIPO, DIRECCION, MAC, SERIE):
            self.assertNotIn(secreto, texto, f"se ha colado {secreto}")

    def test_pero_el_hardware_si_sale(self):
        texto = report.build(_snapshot())
        self.assertIn("Ryzen 7 5800X3D", texto)
        self.assertIn("X570 AORUS ELITE", texto)
        self.assertIn("Radeon RX 9070 XT", texto)
        self.assertIn("enp6s0", texto)

    def test_se_pueden_pedir_a_proposito(self):
        texto = report.build(_snapshot(), anonymous=False)
        self.assertIn(EQUIPO, texto)
        self.assertIn(DIRECCION, texto)
        self.assertIn(SERIE, texto)

    def test_lo_omitido_se_dice_en_vez_de_borrarse(self):
        # Un hueco en blanco haría dudar de si el dato faltaba o se ocultó.
        self.assertIn(report.OCULTO, report.build(_snapshot()))


class TestContenido(unittest.TestCase):
    def test_lleva_lo_que_hace_falta_para_diagnosticar(self):
        texto = report.build(_snapshot())
        for encabezado in ("# Informe de silux", "## Procesador", "## Placa base",
                           "## Gráficos", "## Red", "## Sensores", "## Diagnóstico"):
            self.assertIn(encabezado, texto)

    def test_dice_qué_versiones_hay_debajo(self):
        texto = report.build(_snapshot())
        self.assertIn("Python", texto)
        self.assertIn("Kernel", texto)
        self.assertIn("CachyOS", texto)

    def test_los_datos_que_faltan_son_la_parte_util(self):
        notas = (Note(path="cpu.voltage_v", need=Need.DRIVER,
                      message="Ningún sensor publica el voltaje."),)
        texto = report.build(_snapshot(notes=notas))
        self.assertIn("cpu.voltage_v", texto)
        self.assertIn("falta un módulo del kernel", texto)

    def test_los_modulos_que_faltan_salen_con_su_orden(self):
        # El informe reventaba al llegar aquí: pedía un campo que DriverHint no
        # tiene, y como en la máquina de desarrollo no faltaba ningún módulo,
        # no se veía nunca.
        from silux.model import DriverHint
        pistas = (DriverHint(module="drivetemp",
                             provides="la temperatura de los discos SATA",
                             command="sudo modprobe drivetemp"),)
        texto = report.build(_snapshot(driver_hints=pistas))
        self.assertIn("drivetemp", texto)
        self.assertIn("sudo modprobe drivetemp", texto)

    def test_dice_desde_donde_se_ejecuta(self):
        # Desde un AppImage el ayudante privilegiado necesita un rodeo, así que
        # un «no me deja elevar permisos» sin este dato no lleva a ninguna parte.
        import os
        with mock.patch.dict(os.environ, {"APPIMAGE": "/home/x/silux.AppImage"}):
            self.assertIn("AppImage", report.build(_snapshot()))

    def test_sin_nada_que_falte_tambien_lo_dice(self):
        self.assertIn("Sin datos ausentes", report.build(_snapshot()))

    def test_un_equipo_sin_grafica(self):
        texto = report.build(_snapshot(gpus=()))
        self.assertIn("No se detectó ninguna tarjeta", texto)

    def test_un_equipo_sin_sensores(self):
        self.assertIn("Ninguno detectado", report.build(_snapshot(sensors=())))

    def test_es_markdown_valido_de_principio_a_fin(self):
        texto = report.build(_snapshot())
        self.assertTrue(texto.startswith("# "))
        self.assertTrue(texto.endswith("\n"))
        # Sin líneas sueltas de guiones que rompan una tabla a medias.
        self.assertNotIn("|---|---|\n\n", texto)


class TestCasosVacios(unittest.TestCase):
    def test_un_snapshot_pelado_no_revienta(self):
        texto = report.build(Snapshot(monotonic_ns=0, cpu=CpuInfo()))
        self.assertIn("# Informe de silux", texto)


if __name__ == "__main__":
    unittest.main()


class TestDatosAusentes(unittest.TestCase):
    """Una máquina de la que apenas se sabe nada.

    El caso salió de un aarch64 con Debian dentro de PRoot, donde casi todo
    proveedor se queda a medias. El informe se llenó de «None»: la familia, el
    modelo y el stepping se interpolaban crudos, y `None` es lo que escribe
    Python cuando le pides el texto de un dato que no tiene.
    """

    def _pelado(self):
        return _snapshot(
            cpu=CpuInfo(types=(CpuType(key="general", label="general", brand=None,
                                       cores=8, threads=8,
                                       clocks=Clocks(max_hz=1_612_800_000,
                                                     driver="sprd-cpufreq-v2",
                                                     governor="schedutil")),)),
            board=Board(), gpus=(), network=(), sensors=(),
        )

    def test_no_escribe_None_en_ningun_sitio(self):
        texto = report.build(self._pelado())
        self.assertNotIn("None", texto)

    def test_lo_que_falta_sale_con_su_guion(self):
        texto = report.build(self._pelado())
        self.assertIn("Familia — · modelo — · stepping —", texto)

    def test_lo_que_si_se_sabe_sigue_saliendo(self):
        texto = report.build(self._pelado())
        self.assertIn("8 / 8", texto)
        self.assertIn("sprd-cpufreq-v2", texto)

    def test_un_stepping_cero_es_un_stepping(self):
        """Con `or` en vez de comparar contra None, el 0 se volvía guion."""
        texto = report.build(_snapshot(
            cpu=CpuInfo(types=(CpuType(key="general", label="general", brand="Intel",
                                       cores=6, threads=12, stepping=0,
                                       clocks=Clocks()),)),
        ))
        self.assertIn("stepping 0", texto)


class TestMotivosDeFallo(unittest.TestCase):
    """Por qué falta un dato, que no siempre es lo que parece."""

    def test_un_permiso_denegado_no_es_una_plataforma_que_no_aplica(self):
        nota = Note("network", Need.ROOT, "Sin permiso para leer /sys/class/net.")
        texto = report.build(_snapshot(notes=(nota,)))
        self.assertIn("requiere permisos de administrador", texto)
        self.assertNotIn("no aplica a esta plataforma", texto)

    def test_un_fallo_nuestro_se_dice_como_tal(self):
        nota = Note("spd", Need.ERROR, "El proveedor «spd» falló: vaya")
        texto = report.build(_snapshot(notes=(nota,)))
        self.assertIn("falló al leerse", texto)
