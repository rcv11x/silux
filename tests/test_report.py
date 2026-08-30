"""El informe que se adjunta al reportar un fallo.

Lo que más se prueba aquí es lo que *no* sale. El informe está pensado para
pegarlo en un issue público, así que un descuido que deje una MAC o el nombre
del equipo dentro no es un fallo de formato: es publicar los datos de quien
pedía ayuda.
"""

import unittest
from unittest import mock

from silux import report
from silux.model import (Board, Clocks, CpuInfo, CpuType, Disk, DiskHealth, Gpu,
                        GpuMemory, Need, NetworkInterface, Note, Partition,
                        PcieLink, Sensor, SensorKind, Snapshot, System)

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


class TestCpuHibrida(unittest.TestCase):
    """El i9-13980HX de un probador: 8 P con SMT y 16 E sin él.

    Su informe salía con dos apartados titulados igual, uno de «8 / 16» y otro
    de «16 / 16», sin decir cuál era cuál. Y los 24 núcleos y 32 hilos de la
    pieza no aparecían en ninguna parte, que es justo lo que quien lo manda
    quiere que se vea.
    """

    def _hibrida(self):
        marca = "13th Gen Intel(R) Core(TM) i9-13980HX"
        return _snapshot(cpu=CpuInfo(hybrid=True, types=(
            CpuType(key="performance", label="p", brand=marca, cores=8, threads=16,
                    architecture="x86_64", clocks=Clocks(base_hz=2_200_000_000)),
            CpuType(key="efficiency", label="e", brand=marca, cores=16, threads=16,
                    architecture="x86_64", clocks=Clocks(base_hz=1_600_000_000)),
        )))

    def test_dice_cuantos_nucleos_e_hilos_hay_en_total(self):
        texto = report.build(self._hibrida())
        self.assertIn("24 núcleos · 32 hilos", texto)

    def test_cada_bloque_dice_de_qué_núcleos_habla(self):
        texto = report.build(self._hibrida())
        self.assertIn("**Núcleos P (rendimiento)**", texto)
        self.assertIn("**Núcleos E (eficiencia)**", texto)

    def test_y_cada_uno_conserva_su_propio_reparto(self):
        texto = report.build(self._hibrida())
        self.assertIn("8 / 16", texto)
        self.assertIn("16 / 16", texto)

    def test_en_español_aunque_la_interfaz_esté_en_inglés(self):
        """El informe es castellano fijo: con `_()` se mezclarían los idiomas."""
        from silux import i18n
        anterior = i18n.actual()
        try:
            i18n.set_language("en")
            texto = report.build(self._hibrida())
        finally:
            i18n.set_language(anterior)
        self.assertIn("**Núcleos P (rendimiento)**", texto)

    def test_una_cpu_normal_sigue_titulando_con_su_marca(self):
        texto = report.build(_snapshot())
        self.assertIn("**AMD Ryzen 7 5800X3D**", texto)
        self.assertNotIn("núcleos · ", texto.split("## Memoria")[0])


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


class TestRendimientoEnElInforme(unittest.TestCase):
    """El informe lleva la puntuación, que es lo que permite juntar medidas.

    Sin ella, quien manda un informe manda su hardware pero no lo que rinde, y
    la tabla de puntuaciones no se llena nunca.
    """

    def test_sin_pruebas_puntuables_no_sale_la_seccion(self):
        from silux import report

        with mock.patch("silux.history.load", return_value=[]):
            self.assertNotIn("## Rendimiento", report.build(_snapshot()))

    def test_una_prueba_de_otra_escala_tampoco_cuenta(self):
        from silux import history, report, score

        vieja = history.Entry(timestamp=1.0, cpu="x", threads=8, seconds=15.0,
                              scores={}, score_version=score.VERSION - 1)
        with mock.patch("silux.history.load", return_value=[vieja]):
            self.assertNotIn("## Rendimiento", report.build(_snapshot()))

    def test_con_una_prueba_buena_salen_las_condiciones(self):
        from silux import history, report, score

        tabla = score.referencias()
        if not tabla:
            self.skipTest("no hay escala medida")
        hilos = tabla["patron"]["hilos"]
        sc = {f"{c}/1": v for c, v in tabla["un_hilo"].items()}
        sc |= {f"{c}/{hilos}": v for c, v in tabla["multihilo"].items()}
        buena = history.Entry(
            timestamp=1.0, cpu="x", threads=hilos, seconds=15.0, scores=sc,
            governor="performance", temperature_peak_c=84.6,
            score_version=score.VERSION)
        with mock.patch("silux.history.load", return_value=[buena]):
            texto = report.build(_snapshot())
        self.assertIn("## Rendimiento", texto)
        # Las condiciones son la mitad de lo que hace comparable una cifra.
        for esperado in ("Escala", "Gobernador", "performance", "Hilos"):
            self.assertIn(esperado, texto)


class TestLasCategoriasSalenEnCastellano(unittest.TestCase):
    """El informe no puede enseñar las claves de idioma en crudo.

    La sección de sensores agrupa por categoría, y esas categorías son claves
    —«cat.temperature»— porque los nombres que agrupan los inventa el programa
    y son interfaz, no dato del equipo. Sin traducirlas, el informe decía
    «cat.temperature (2), cat.power (2)» a todo el que lo abriera, que es
    justo el archivo que se le pide a alguien cuando reporta un fallo.

    Van en castellano y no en el idioma de quien lo genera, porque el resto del
    informe es castellano fijo: «Procesador», «Placa base». Con `_()` normal,
    un informe hecho con la interfaz en inglés mezclaría los dos idiomas en la
    misma página.
    """

    def _con_varias_categorias(self) -> str:
        sensores = (
            Sensor(key="k/1", chip="k10temp", device="AMD Ryzen 7 5800X3D",
                   label="Tctl", kind=SensorKind.TEMPERATURE, value=45.0),
            Sensor(key="k/2", chip="k10temp", device="AMD Ryzen 7 5800X3D",
                   label="Núcleo", kind=SensorKind.CLOCK, value=4_550.0),
            Sensor(key="k/3", chip="nct6798", device="Gigabyte X570",
                   label="Chasis", kind=SensorKind.FAN, value=900.0),
        )
        return report.build(_snapshot(sensors=sensores))

    def test_no_se_cuela_ninguna_clave_cruda(self):
        texto = self._con_varias_categorias()
        self.assertNotIn("cat.", texto,
                         "el informe enseña una clave de idioma sin traducir")

    def test_y_lo_que_sale_es_el_nombre_castellano(self):
        texto = self._con_varias_categorias()
        for esperado in ("temperaturas", "relojes", "ventiladores"):
            self.assertIn(esperado, texto,
                          f"no aparece la categoría «{esperado}»")

    def test_sigue_en_castellano_con_la_interfaz_en_ingles(self):
        """Lo que rompería esto es cambiar `en_español` por `_`."""
        from silux import i18n

        anterior = i18n.actual()
        try:
            i18n.set_language("en")
            texto = self._con_varias_categorias()
        finally:
            i18n.set_language(anterior)
        self.assertIn("temperaturas", texto,
                      "el informe cambió de idioma con la interfaz: se mezcla "
                      "con el castellano fijo del resto")
        self.assertNotIn("cat.", texto)


def _disco(**cambios) -> Disk:
    base = dict(
        name="nvme0n1", model="SN850X 1000GB", vendor="WD_BLACK",
        firmware="620361WD", serial=SERIE, size_bytes=1000 * 1000**3,
        kind="NVMe", transport="nvme", temp_c=47.9,
        link=PcieLink(current_speed_gts=16.0, current_width=4,
                      max_speed_gts=16.0, max_width=4),
        health=DiskHealth(power_on_hours=1200, written_bytes=45 * 1000**4,
                          percentage_used=3, critical_warning="",
                          unsafe_shutdowns=7),
        partitions=(Partition(name="nvme0n1p1", size_bytes=500 * 1000**3,
                              filesystem="btrfs", mountpoint="/media/pepe/copia",
                              used_bytes=100 * 1000**3, free_bytes=400 * 1000**3),),
    )
    base.update(cambios)
    return Disk(**base)


class TestAlmacenamientoEnElInforme(unittest.TestCase):
    """Los discos, que faltaban enteros.

    Era la única de las once páginas que no salía en el informe, y se notaba al
    pedirlo: para revisar un disco había que pedir además una captura. Aquí se
    han corregido ya un fabricante mal sacado del modelo y un TBW 65 536 veces
    pequeño, y ninguno de los dos se ve sin la cifra delante.
    """

    def test_hay_seccion_y_sale_el_disco(self):
        texto = report.build(_snapshot(disks=(_disco(),)))
        self.assertIn("## Almacenamiento", texto)
        self.assertIn("SN850X 1000GB", texto)

    def test_sin_discos_lo_dice_en_vez_de_callarse(self):
        texto = report.build(_snapshot(disks=()))
        self.assertIn("## Almacenamiento", texto)
        self.assertIn("No se detectó ningún disco", texto)

    def test_el_numero_de_serie_no_se_publica(self):
        """Un disco lleva serie igual que una gráfica, y se tapa igual."""
        texto = report.build(_snapshot(disks=(_disco(serial="WD-XYZ123456"),)))
        self.assertNotIn("WD-XYZ123456", texto)

    def test_no_se_dice_dos_veces_el_fabricante(self):
        """El fabricante se saca del propio modelo: juntarlos duplica."""
        texto = report.build(_snapshot(
            disks=(_disco(vendor="Samsung", model="Samsung SSD 970 EVO Plus"),)))
        self.assertNotIn("Samsung Samsung", texto)
        self.assertIn("Samsung SSD 970 EVO Plus", texto)

    def test_pero_se_pone_cuando_el_modelo_no_lo_trae(self):
        texto = report.build(_snapshot(
            disks=(_disco(vendor="Crucial", model="CT500MX500SSD1"),)))
        self.assertIn("Crucial CT500MX500SSD1", texto)

    def test_no_se_publican_los_puntos_de_montaje(self):
        """Una ruta puede llevar dentro el nombre de quien usa el equipo."""
        texto = report.build(_snapshot(disks=(_disco(),)))
        self.assertNotIn("/media/pepe", texto)
        self.assertNotIn("pepe", texto)

    def test_la_salud_sale_con_sus_contadores(self):
        texto = report.build(_snapshot(disks=(_disco(),)))
        for esperado in ("1200 h encendido", "escritos", "vida consumida"):
            self.assertIn(esperado, texto, f"falta «{esperado}»")

    def test_los_apagones_bruscos_no_se_dan_por_avería(self):
        """Cuentan cortes de luz y botones de reinicio, no un disco roto."""
        texto = report.build(_snapshot(disks=(_disco(),)))
        self.assertIn("7 apagones bruscos", texto)

    def test_un_sata_no_finge_tener_enlace_propio(self):
        """Quien negocia es su controladora, y la comparte con el cable."""
        texto = report.build(_snapshot(
            disks=(_disco(kind="HDD", transport="sata", link=None,
                          health=None, partitions=()),)))
        self.assertNotIn("Enlace:", texto.split("## Almacenamiento")[1])

    def test_un_disco_pelado_no_revienta(self):
        texto = report.build(_snapshot(disks=(Disk(name="sda"),)))
        self.assertIn("## Almacenamiento", texto)


class TestSensoresConDetalle(unittest.TestCase):
    """El recuento decía cuántos hay; lo que se revisa es cómo se llaman."""

    def test_sale_el_nombre_y_el_valor_de_cada_sensor(self):
        sensores = (
            Sensor(key="k/1", chip="k10temp", device="AMD Ryzen 7 5800X3D",
                   label="Tctl", kind=SensorKind.TEMPERATURE, value=45.0),
        )
        texto = report.build(_snapshot(sensors=sensores))
        self.assertIn("Tctl", texto)
        self.assertIn("45.0", texto)

    def test_un_voltaje_conserva_sus_decimales(self):
        """A un decimal deja de ser un voltaje: 0,845 V se queda en 0,8."""
        sensores = (
            Sensor(key="v/1", chip="nct6798", device="Gigabyte X570",
                   label="Vcore", kind=SensorKind.VOLTAGE, value=0.845),
        )
        texto = report.build(_snapshot(sensors=sensores))
        self.assertIn("0.845", texto)


class TestLaTablaDeDecimalesEsUna(unittest.TestCase):
    """Dos tablas iguales en dos archivos se desincronizan solas.

    La página de sensores tenía la suya y el informe habría necesitado otra.
    Vive en `render`, que es donde el proyecto pone lo que convierte valores en
    texto, y la página la toma de allí.
    """

    def test_la_pagina_de_sensores_usa_la_de_render(self):
        from silux import render
        from silux.ui.pages import monitor

        self.assertIs(monitor.DECIMALS, render.SENSOR_DECIMALS)
