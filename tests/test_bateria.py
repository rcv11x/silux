"""La batería: la pieza que más se degrada de un portátil.

Lo que se prueba aquí es sobre todo la aritmética, porque es donde el kernel
deja trampas: dos convenciones para la capacidad, un signo que no significa lo
mismo en todos los firmwares, y un `/sys/class/power_supply` donde el ratón
inalámbrico se presenta como batería.
"""

import pathlib
import tempfile
import unittest

from silux.model import Battery
from silux.providers import battery
from silux.providers.base import Draft


class _Sysfs:
    """Un `/sys/class/power_supply` de mentira."""

    def __init__(self, raiz: pathlib.Path):
        self.raiz = raiz

    def añadir(self, nombre: str, **campos) -> pathlib.Path:
        carpeta = self.raiz / nombre
        carpeta.mkdir(parents=True, exist_ok=True)
        for clave, valor in campos.items():
            (carpeta / clave).write_text(f"{valor}\n", encoding="utf-8")
        return carpeta


class _ConSysfs(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.raiz = pathlib.Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)
        self.sysfs = _Sysfs(self.raiz)
        from unittest import mock

        parche = mock.patch.object(battery, "POWER_SUPPLY", self.raiz)
        parche.start()
        self.addCleanup(parche.stop)

    def _recoger(self) -> list[Battery]:
        draft = Draft()
        battery.Batteries().collect(draft)
        return draft.batteries


class TestQueEsUnaBateriaDelEquipo(_ConSysfs):
    """El ratón inalámbrico también dice ser una batería.

    Se descubrió en el sitio menos esperado: este sobremesa, que no tiene
    ninguna, declaraba una porque el ratón Logitech publica `hidpp_battery_0`
    con `type=Battery`. Habría salido una ficha de batería en una torre.
    """

    def test_el_raton_no_cuenta(self):
        self.sysfs.añadir("hidpp_battery_0", type="Battery", scope="Device",
                          capacity=55)
        self.assertEqual(self._recoger(), [])

    def test_el_cargador_tampoco(self):
        self.sysfs.añadir("ADP0", type="Mains", online=1)
        self.assertEqual(self._recoger(), [])

    def test_la_del_equipo_sí(self):
        self.sysfs.añadir("BAT0", type="Battery", scope="System", capacity=64,
                          energy_full_design=50_000_000, energy_full=43_500_000)
        self.assertEqual(len(self._recoger()), 1)

    def test_sin_scope_se_da_por_del_equipo(self):
        """Los portátiles antiguos no lo publican."""
        self.sysfs.añadir("BAT1", type="Battery", capacity=80)
        self.assertEqual(len(self._recoger()), 1)


class TestLasDosConvenciones(_ConSysfs):
    """El kernel da la capacidad en µWh o en µAh según el firmware."""

    def test_en_energia_se_toma_tal_cual(self):
        self.sysfs.añadir("BAT0", type="Battery", energy_full_design=50_000_000,
                          energy_full=43_500_000, energy_now=27_800_000)
        bat = self._recoger()[0]
        self.assertAlmostEqual(bat.design_wh, 50.0)
        self.assertAlmostEqual(bat.full_wh, 43.5)

    def test_en_carga_se_multiplica_por_el_voltaje_de_diseño(self):
        """4000 mAh a 7,6 V y a 11,4 V son baterías muy distintas."""
        self.sysfs.añadir("BAT0", type="Battery", charge_full_design=4_000_000,
                          charge_full=3_500_000, voltage_min_design=11_400_000,
                          voltage_now=12_100_000)
        bat = self._recoger()[0]
        self.assertAlmostEqual(bat.design_wh, 45.6)      # 4 Ah × 11,4 V

    def test_manda_el_voltaje_de_diseño_y_no_el_de_ahora(self):
        """El de ahora sube y baja con la carga: daría otra capacidad en cada
        muestreo, y la capacidad nominal no cambia."""
        self.sysfs.añadir("BAT0", type="Battery", charge_full_design=4_000_000,
                          voltage_min_design=11_400_000, voltage_now=12_600_000)
        self.assertAlmostEqual(self._recoger()[0].design_wh, 45.6)


class TestLaSalud(unittest.TestCase):
    """El número por el que se abre esta página."""

    def test_es_lo_que_queda_de_lo_que_venía_de_fábrica(self):
        bat = Battery(design_wh=50.0, full_wh=43.5)
        self.assertAlmostEqual(bat.health_percent, 87.0)

    def test_sin_capacidad_de_diseño_no_se_inventa(self):
        self.assertIsNone(Battery(full_wh=43.5).health_percent)

    def test_una_batería_nueva_da_cien(self):
        self.assertAlmostEqual(
            Battery(design_wh=50.0, full_wh=50.0).health_percent, 100.0)


class TestLaAutonomia(unittest.TestCase):
    def test_descargando_es_lo_que_queda_al_ritmo_de_ahora(self):
        bat = Battery(status="bat.status.discharging", now_wh=20.0, power_w=10.0)
        self.assertEqual(bat.seconds_left, 7200)

    def test_cargando_es_lo_que_falta_para_llenarse(self):
        bat = Battery(status="bat.status.charging", now_wh=20.0, full_wh=50.0,
                      power_w=30.0)
        self.assertEqual(bat.seconds_left, 3600)

    def test_llena_y_enchufada_no_tiene_cuenta_atras(self):
        bat = Battery(status="bat.status.full", now_wh=50.0, full_wh=50.0,
                      power_w=0.0)
        self.assertIsNone(bat.seconds_left)

    def test_sin_consumo_no_se_divide_entre_cero(self):
        bat = Battery(status="bat.status.discharging", now_wh=20.0, power_w=0.0)
        self.assertIsNone(bat.seconds_left)


class TestLoQueSeLee(_ConSysfs):
    def test_el_signo_de_la_corriente_no_importa(self):
        """Unos firmwares lo ponen negativo al descargar y otros no; quien
        dice si entra o sale es `status`."""
        self.sysfs.añadir("BAT0", type="Battery", current_now=-1_500_000,
                          voltage_now=11_500_000)
        self.assertGreater(self._recoger()[0].power_w, 0)

    def test_el_estado_se_guarda_como_clave_y_no_en_inglés(self):
        self.sysfs.añadir("BAT0", type="Battery", status="Discharging")
        self.assertEqual(self._recoger()[0].status, "bat.status.discharging")

    def test_un_estado_que_no_se_conoce_no_revienta(self):
        self.sysfs.añadir("BAT0", type="Battery", status="Vaciándose deprisa")
        self.assertEqual(self._recoger()[0].status, "bat.status.unknown")

    def test_los_topes_de_carga_se_leen_si_los_hay(self):
        self.sysfs.añadir("BAT0", type="Battery",
                          charge_control_start_threshold=58,
                          charge_control_end_threshold=60)
        bat = self._recoger()[0]
        self.assertEqual(bat.charge_start_percent, 58)
        self.assertEqual(bat.charge_end_percent, 60)

    def test_una_batería_pelada_no_revienta(self):
        self.sysfs.añadir("BAT0", type="Battery")
        bat = self._recoger()[0]
        self.assertIsNone(bat.health_percent)
        self.assertIsNone(bat.seconds_left)

    def test_dos_baterías_salen_las_dos(self):
        """Hay portátiles con una interna y otra extraíble."""
        self.sysfs.añadir("BAT0", type="Battery", capacity=50)
        self.sysfs.añadir("BAT1", type="Battery", capacity=90)
        self.assertEqual(len(self._recoger()), 2)


class TestUnSobremesa(_ConSysfs):
    def test_sin_baterías_no_se_anuncia_la_capacidad(self):
        """Y sin nota: que una torre no tenga batería no es una carencia."""
        draft = Draft()
        battery.Batteries().collect(draft)
        self.assertNotIn("battery", draft.capabilities)
        self.assertEqual(draft.batteries, [])


class TestLaBateriaEnElInforme(unittest.TestCase):
    """Lo que se le pide a quien reporta un fallo también la lleva."""

    def _informe(self, **cambios):
        from silux import report
        from silux.model import Board, CpuInfo, Snapshot, System

        base = dict(name="BAT0", status="bat.status.discharging", percent=64.0,
                    design_wh=50.0, full_wh=43.5, power_w=9.4, cycles=312,
                    manufacturer="ASUSTeK", model="ASUS Battery",
                    technology="Li-poly", serial="SERIE-SECRETA-123")
        base.update(cambios)
        foto = Snapshot(monotonic_ns=0, cpu=CpuInfo(), board=Board(),
                        system=System(), batteries=(Battery(**base),))
        return report.build(foto)

    def test_sale_la_salud_que_es_el_dato(self):
        texto = self._informe()
        self.assertIn("## Batería", texto)
        self.assertIn("87 %", texto)
        self.assertIn("312", texto)

    def test_el_numero_de_serie_de_la_celda_no_se_publica(self):
        """Como el del disco y el de la gráfica."""
        self.assertNotIn("SERIE-SECRETA-123", self._informe())

    def test_el_estado_sale_en_castellano_y_no_como_clave(self):
        """El informe es castellano fijo, así que va con `en_español`."""
        texto = self._informe()
        self.assertIn("descargando", texto)
        self.assertNotIn("bat.status", texto)

    def test_los_topes_solo_si_el_portatil_los_trae(self):
        con = self._informe(charge_start_percent=58, charge_end_percent=60)
        self.assertIn("Topes de carga", con)
        self.assertNotIn("Topes de carga", self._informe())

    def test_un_sobremesa_no_gana_una_seccion_vacia(self):
        from silux import report
        from silux.model import Board, CpuInfo, Snapshot, System

        foto = Snapshot(monotonic_ns=0, cpu=CpuInfo(), board=Board(),
                        system=System())
        self.assertNotIn("## Batería", report.build(foto))


class TestLosTopesDeCargaQueNoSonTopes(unittest.TestCase):
    """0 y 100 es el rango entero, o sea no tener límite.

    Un ThinkPad sin límite configurado los publica así, y enseñar
    «Empieza a cargar por debajo de 0 % · Deja de cargar en 100 %» hace creer
    que hay algo puesto. Un Dell con 50 y 90 sí lo tiene, y ahí el dato vale.
    """

    def _hay(self, inicio, fin):
        from silux.ui.pages.battery import _hay_topes

        return _hay_topes(Battery(charge_start_percent=inicio,
                                  charge_end_percent=fin))

    def test_de_cero_a_cien_no_es_un_tope(self):
        self.assertFalse(self._hay(0, 100))

    def test_uno_de_verdad_sí(self):
        self.assertTrue(self._hay(50, 90))

    def test_sin_publicarlos_tampoco(self):
        self.assertFalse(self._hay(None, None))

    def test_solo_el_de_arriba_ya_cuenta(self):
        self.assertTrue(self._hay(None, 80))

    def test_el_informe_hace_lo_mismo(self):
        from silux import report
        from silux.model import Board, CpuInfo, Snapshot, System

        def informe(inicio, fin):
            bat = Battery(name="BAT0", design_wh=50.0, full_wh=43.5,
                          charge_start_percent=inicio, charge_end_percent=fin)
            return report.build(Snapshot(monotonic_ns=0, cpu=CpuInfo(),
                                         board=Board(), system=System(),
                                         batteries=(bat,)))

        self.assertNotIn("Topes de carga", informe(0, 100))
        self.assertIn("Topes de carga", informe(50, 90))
