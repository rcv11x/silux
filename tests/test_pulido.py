"""Renglones que se leían mal en las capturas de otros equipos.

Ninguno es un dato erróneo: son datos ciertos presentados de forma que
confunden, que en un programa cuyo trabajo es informar viene a ser lo mismo.
"""

import unittest

from silux.model import Board
from silux.providers.storage import _de_la_marca


class TestFabricanteDelDisco(unittest.TestCase):
    """El campo `vendor` de sysfs dice «ATA» en SATA y nada en NVMe.

    El nombre solo está dentro del modelo, y salía un guion en discos que se
    llaman «Samsung SSD 870» y «KIOXIA-EXCERIA S».
    """

    def test_sale_de_como_empieza_el_modelo(self):
        for modelo, esperado in [
            ("KIOXIA-EXCERIA S", "Kioxia"),
            ("Samsung SSD 870", "Samsung"),
            ("Intenso NVME", "Intenso"),
            ("CT500MX500SSD1", "Crucial"),
        ]:
            self.assertEqual(_de_la_marca(modelo), esperado, modelo)

    def test_los_prefijos_largos_ganan_a_los_cortos(self):
        """«wd_black» antes que «wd », «sk hynix» antes que «hynix»."""
        self.assertEqual(_de_la_marca("WD_BLACK SN850X"), "Western Digital")
        self.assertEqual(_de_la_marca("SK hynix BC711"), "SK hynix")

    def test_las_series_de_seagate_van_por_numero(self):
        self.assertEqual(_de_la_marca("ST8000DM004-2CX188"), "Seagate")

    def test_lo_que_no_reconoce_no_se_lo_inventa(self):
        self.assertIsNone(_de_la_marca("Disco Genérico 9000"))
        self.assertIsNone(_de_la_marca(""))
        self.assertIsNone(_de_la_marca(None))


class TestNombreDelEquipo(unittest.TestCase):
    """En un portátil la placa no tiene nombre comercial.

    Un IdeaPad 330 lleva dentro una placa «LNVNB161216», que no le dice nada
    a nadie. El nombre de la pegatina está en los campos de sistema del DMI.
    """

    def test_un_portatil_se_llama_por_su_nombre(self):
        board = Board(vendor="LENOVO", name="LNVNB161216", chassis="chassis.notebook",
                      system_vendor="LENOVO",
                      system_version="Lenovo ideapad 330-15ICH")
        self.assertEqual(board.display_name, "Lenovo ideapad 330-15ICH")

    def test_sin_repetir_la_marca_que_ya_viene_dentro(self):
        board = Board(vendor="LENOVO", name="LNVNB161216", chassis="chassis.notebook",
                      system_vendor="LENOVO",
                      system_version="Lenovo ideapad 330-15ICH")
        self.assertNotIn("Lenovo Lenovo", board.display_name)

    def test_y_poniendola_cuando_falta(self):
        board = Board(vendor="ASUSTeK", name="FA506IHRB", chassis="chassis.notebook",
                      system_vendor="ASUSTeK COMPUTER INC.",
                      system_version="TUF Gaming A15")
        self.assertEqual(board.display_name, "ASUS TUF Gaming A15")

    def test_un_sobremesa_sigue_llamandose_por_su_placa(self):
        """Ahí el nombre bueno es el de la placa: es lo que se compró."""
        board = Board(vendor="Micro-Star International Co., Ltd.",
                      name="H510M PRO-E (MS-7D23)", chassis="chassis.desktop",
                      system_vendor="Micro-Star", system_version="1.0")
        self.assertEqual(board.display_name, "MSI H510M PRO-E (MS-7D23)")

    def test_un_portatil_sin_nombre_de_equipo_tampoco_se_queda_sin_titulo(self):
        board = Board(vendor="HP", name="8846", chassis="chassis.notebook")
        self.assertEqual(board.display_name, "HP 8846")

    def test_y_una_placa_suelta_sin_nada(self):
        # The model gives no text; render says it, translated.
        from silux import render
        self.assertIsNone(Board().display_name)
        self.assertEqual(render.board_name(Board()), "Placa base")

    def test_without_a_board_the_machine_names_it(self):
        # QEMU declares no baseboard: a tester's VM was titled «Placa base».
        qemu = Board(system_vendor="QEMU", system_name="Standard PC (i440FX + PIIX, 1996)")
        self.assertEqual(qemu.display_name, "QEMU Standard PC (i440FX + PIIX, 1996)")


class TestElNombreDeUnEquipoDeMarca(unittest.TestCase):
    """La frontera no era portátil contra sobremesa.

    Preguntar por el chasis era una aproximación a «¿tiene este equipo un
    nombre comercial?» y falló dos veces: con un IdeaPad 330 y con un
    ThinkCentre M80q, que es un Mini PC y salía como «Lenovo 316C». Ampliar la
    lista de chasis tampoco lo habría cerrado, porque los sobremesas de marca
    suelen declararse «Desktop» a secas.

    Ahora se pregunta lo que decide: si hay nombre comercial. La señal está en
    el propio dato —una placa suelta deja «1.0» o un relleno de fábrica— y no
    hace falta adivinar nada.
    """

    def test_un_mini_pc_de_marca_se_llama_por_su_nombre(self):
        board = Board(vendor="LENOVO", name="316C", chassis="chassis.minipc",
                      system_vendor="LENOVO", system_version="ThinkCentre M80q",
                      system_family="ThinkCentre M80q")
        self.assertEqual(board.display_name, "Lenovo ThinkCentre M80q")

    def test_una_gigabyte_suelta_se_llama_como_la_placa(self):
        """Los rellenos de Gigabyte no son números ni «Default string».

        En una X570 AORUS ELITE la versión del sistema es «-CF» y la familia
        «X570 MB», y el equipo salía «Gigabyte -CF» en la cabecera de Inicio
        y en el árbol de sensores. Los valores son los del volcado del
        5800X3D.
        """
        board = Board(vendor="Gigabyte Technology Co., Ltd.", name="X570 AORUS ELITE",
                      system_vendor="Gigabyte Technology Co., Ltd.",
                      system_name="X570 AORUS ELITE", system_version="-CF",
                      system_family="X570 MB")
        self.assertIsNone(board.system_display_name)
        self.assertEqual(board.display_name, "Gigabyte X570 AORUS ELITE")

    def test_y_asi_sale_en_el_equipo_volcado(self):
        from tests.test_equipos import EQUIPOS, foto

        f = foto(EQUIPOS / "5800x3d")[0]
        self.assertEqual(f.board.display_name, "Gigabyte X570 AORUS ELITE")
        self.assertNotIn("Gigabyte -CF", {s.device for s in f.sensors})

    def test_y_tambien_si_se_declara_un_sobremesa_cualquiera(self):
        """Es lo que ampliar la lista de chasis no habría arreglado."""
        board = Board(vendor="LENOVO", name="316C", chassis="chassis.desktop",
                      system_vendor="LENOVO", system_version="ThinkCentre M80q")
        self.assertEqual(board.display_name, "Lenovo ThinkCentre M80q")

    def test_vale_el_nombre_aunque_solo_este_en_la_familia(self):
        board = Board(vendor="LENOVO", name="3102", chassis="chassis.aio",
                      system_vendor="LENOVO", system_version="1.0",
                      system_family="ThinkCentre M90a")
        self.assertEqual(board.display_name, "Lenovo ThinkCentre M90a")

    def test_un_numero_de_version_no_es_el_nombre_de_nada(self):
        """Es lo que deja una placa que se vende suelta, y es lo que protege
        al caso de arriba: sin esto un sobremesa montado saldría «MSI 1.0»."""
        for version in ("1.0", "1.1", "Rev 1.0", "01", "2.00"):
            with self.subTest(version=version):
                board = Board(vendor="Micro-Star International Co., Ltd.",
                              name="H510M PRO-E (MS-7D23)",
                              chassis="chassis.desktop",
                              system_vendor="Micro-Star", system_version=version)
                self.assertEqual(board.display_name,
                                 "MSI H510M PRO-E (MS-7D23)")

    def test_ni_un_relleno_de_fabrica(self):
        board = Board(vendor="ASRock", name="B450M Pro4",
                      chassis="chassis.desktop", system_vendor="ASRock",
                      system_version="Default string")
        self.assertEqual(board.display_name, "ASRock B450M Pro4")

    def test_el_codigo_de_producto_no_se_usa(self):
        """`system_name` trae «11DQS0KM00» en un OEM y «MS-7D23» en una placa
        suelta: las dos veces es peor que lo que ya se tiene."""
        board = Board(vendor="LENOVO", name="316C", chassis="chassis.desktop",
                      system_vendor="LENOVO", system_name="11DQS0KM00")
        self.assertEqual(board.display_name, "Lenovo 316C")


class TestElInformeDejaDiagnosticarElNombre(unittest.TestCase):
    """De dónde sale el titular, en crudo.

    Cada fabricante escribe el nombre del equipo donde le parece, así que un
    «me sale un nombre raro» necesitaba un dmidecode aparte para saber qué
    había puesto el firmware. Ahora está en el informe que ya se pide.
    """

    def _informe(self, board):
        import dataclasses

        from silux import report
        from silux.model import CpuInfo, CpuType, Snapshot

        return report.build(Snapshot(
            monotonic_ns=0,
            cpu=CpuInfo(types=(CpuType(key="g", label="g"),)),
            board=board,
        ))

    def test_van_los_cinco_campos_y_el_chasis(self):
        texto = self._informe(Board(
            vendor="LENOVO", name="316C", version="No DPK",
            chassis="chassis.minipc", system_vendor="LENOVO",
            system_name="11DQS0KM00", system_version="ThinkCentre M80q",
            system_family="ThinkCentre M80q"))
        for dato in ("316C", "No DPK", "11DQS0KM00", "ThinkCentre M80q"):
            with self.subTest(dato=dato):
                self.assertIn(dato, texto)
        self.assertIn("Chasis:", texto)

    def test_lo_que_falta_sale_como_falta(self):
        texto = self._informe(Board(vendor="Gigabyte", name="B550 AORUS ELITE"))
        self.assertIn("DMI del sistema:", texto)


class TestEnumerar(unittest.TestCase):
    """Las notas nombran lo que falta como se dice, no como una lista."""

    def test_con_y_y_con_ni(self):
        from silux import render

        self.assertEqual(render.enumeration(["el fabricante", "los chips", "la fecha"]),
                         "el fabricante, los chips y la fecha")
        self.assertEqual(render.enumeration(["su revisión", "el fabricante del chasis"],
                                            "list.nor"),
                         "su revisión ni el fabricante del chasis")
        self.assertEqual(render.enumeration(["su revisión"]), "su revisión")
        self.assertEqual(render.enumeration([]), "")


if __name__ == "__main__":
    unittest.main()
