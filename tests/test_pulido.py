"""Renglones que se leían mal en las capturas de otros equipos.

Ninguno es un dato erróneo: son datos ciertos presentados de forma que
confunden, que en un programa cuyo trabajo es informar viene a ser lo mismo.
"""

import unittest

from silux.model import Board
from silux.providers.storage import _de_la_marca
from silux.ui.pages.memory import _sin_el_prefijo_comun


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


class TestNombreDeLosZocalos(unittest.TestCase):
    """Dos zócalos que se llaman casi igual y se distinguen por el final."""

    def test_quita_el_trozo_que_comparten(self):
        corto = _sin_el_prefijo_comun(["Controller0-ChannelA",
                                       "Controller0-ChannelB"])
        self.assertEqual(corto["Controller0-ChannelA"], "ChannelA")
        self.assertEqual(corto["Controller0-ChannelB"], "ChannelB")

    def test_pero_no_toca_los_que_ya_caben(self):
        """Dejar «Zócalo 0» en «0» quita contexto en vez de darlo."""
        self.assertEqual(_sin_el_prefijo_comun(["Zócalo 0", "Zócalo 2"]), {})

    def test_ni_los_que_no_comparten_principio(self):
        self.assertEqual(
            _sin_el_prefijo_comun(["ChannelA-DIMM0", "ChannelB-DIMM0"]), {})

    def test_con_un_solo_modulo_no_hay_nada_que_comparar(self):
        self.assertEqual(_sin_el_prefijo_comun(["Controller0-ChannelA"]), {})

    def test_no_deja_ninguno_vacio(self):
        """Si el prefijo era el nombre entero, mejor no tocar nada."""
        corto = _sin_el_prefijo_comun(["Controller0-ChannelA",
                                       "Controller0-ChannelA-DIMM1"])
        self.assertTrue(all(corto.values()))


class TestNombreDelEquipo(unittest.TestCase):
    """En un portátil la placa no tiene nombre comercial.

    Un IdeaPad 330 lleva dentro una placa «LNVNB161216», que no le dice nada
    a nadie. El nombre de la pegatina está en los campos de sistema del DMI.
    """

    def test_un_portatil_se_llama_por_su_nombre(self):
        board = Board(vendor="LENOVO", name="LNVNB161216", chassis="Notebook",
                      system_vendor="LENOVO",
                      system_version="Lenovo ideapad 330-15ICH")
        self.assertEqual(board.display_name, "Lenovo ideapad 330-15ICH")

    def test_sin_repetir_la_marca_que_ya_viene_dentro(self):
        board = Board(vendor="LENOVO", name="LNVNB161216", chassis="Notebook",
                      system_vendor="LENOVO",
                      system_version="Lenovo ideapad 330-15ICH")
        self.assertNotIn("Lenovo Lenovo", board.display_name)

    def test_y_poniendola_cuando_falta(self):
        board = Board(vendor="ASUSTeK", name="FA506IHRB", chassis="Notebook",
                      system_vendor="ASUSTeK COMPUTER INC.",
                      system_version="TUF Gaming A15")
        self.assertEqual(board.display_name, "ASUS TUF Gaming A15")

    def test_un_sobremesa_sigue_llamandose_por_su_placa(self):
        """Ahí el nombre bueno es el de la placa: es lo que se compró."""
        board = Board(vendor="Micro-Star International Co., Ltd.",
                      name="H510M PRO-E (MS-7D23)", chassis="Sobremesa",
                      system_vendor="Micro-Star", system_version="1.0")
        self.assertEqual(board.display_name, "MSI H510M PRO-E (MS-7D23)")

    def test_un_portatil_sin_nombre_de_equipo_tampoco_se_queda_sin_titulo(self):
        board = Board(vendor="HP", name="8846", chassis="Notebook")
        self.assertEqual(board.display_name, "HP 8846")

    def test_y_una_placa_suelta_sin_nada(self):
        self.assertEqual(Board().display_name, "Placa base")


if __name__ == "__main__":
    unittest.main()
