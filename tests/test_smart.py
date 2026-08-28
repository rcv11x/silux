"""Los datos de diagnóstico de los discos.

Se arman a mano porque leerlos de un disco real exige permisos de
administrador, y porque hace falta probar discos que no se tienen: uno gastado,
uno con avisos críticos, uno que no implementa el registro.

El reparto de trabajo importa y está probado aquí: el ayudante privilegiado
pide los bytes y no los mira; interpretarlos es de este módulo, que corre sin
privilegios. Analizar formatos binarios es de donde salen los fallos de
memoria, y hacerlo como root sería regalar el problema.
"""

import struct
import unittest

from silux import smart


def registro_nvme(*, temperatura_k=273 + 45, repuesto=100, gastado=7,
                  escrito=200_000_000, leido=100_000_000, horas=8760,
                  ciclos=340, apagones=3, errores=0, aviso=0) -> bytes:
    """El registro de salud de NVMe, cuyos campos son fijos por especificación."""
    b = bytearray(512)
    b[0] = aviso
    struct.pack_into("<H", b, 1, temperatura_k)
    b[3] = repuesto
    b[5] = gastado
    for offset, valor in ((32, leido), (48, escrito), (112, ciclos),
                          (128, horas), (144, apagones), (160, errores)):
        struct.pack_into("<QQ", b, offset, valor, 0)
    return bytes(b)


def tabla_ata(atributos=None) -> bytes:
    """La tabla de treinta atributos numerados de SATA."""
    b = bytearray(512)
    b[0], b[1] = 0x10, 0x00
    for indice, (identificador, normalizado, crudo) in enumerate(atributos or ()):
        inicio = 2 + indice * 12
        b[inicio] = identificador
        b[inicio + 3] = normalizado
        b[inicio + 4] = normalizado
        b[inicio + 5:inicio + 11] = crudo.to_bytes(6, "little")
    return bytes(b)


class TestNvme(unittest.TestCase):
    def setUp(self):
        self.salud = smart.parse(registro_nvme(), "nvme")

    def test_horas_y_ciclos(self):
        self.assertEqual(self.salud.power_on_hours, 8760)
        self.assertEqual(self.salud.power_cycles, 340)

    def test_lo_escrito_va_en_unidades_de_mil_sectores(self):
        # NVMe no cuenta bytes: cuenta «unidades de datos» de 512 000 bytes.
        self.assertEqual(self.salud.written_bytes, 200_000_000 * 512_000)

    def test_el_desgaste_y_la_vida_que_queda(self):
        self.assertEqual(self.salud.percentage_used, 7)
        self.assertEqual(self.salud.life_left_percent, 93)

    def test_un_disco_sano(self):
        self.assertTrue(self.salud.healthy)
        self.assertEqual(self.salud.spare_percent, 100)

    def test_un_disco_con_aviso_critico(self):
        salud = smart.parse(registro_nvme(aviso=0x01), "nvme")
        self.assertFalse(salud.healthy)

    def test_un_disco_pasado_de_garantia(self):
        # Los SSD siguen funcionando después del 100 %: es lo que el fabricante
        # garantizaba, no un límite físico.
        salud = smart.parse(registro_nvme(gastado=118), "nvme")
        self.assertEqual(salud.percentage_used, 118)
        self.assertEqual(salud.life_left_percent, 0)

    def test_la_temperatura_viene_en_kelvin(self):
        self.assertAlmostEqual(smart.nvme_temperature(registro_nvme()), 44.9, places=1)

    def test_un_registro_a_ceros_es_un_disco_que_no_lo_implementa(self):
        # No es un disco recién estrenado con cero horas: es que no contesta.
        self.assertIsNone(smart.parse(bytes(512), "nvme"))

    def test_un_registro_cortado(self):
        self.assertIsNone(smart.parse(registro_nvme()[:100], "nvme"))


class TestAta(unittest.TestCase):
    def test_los_atributos_con_significado_acordado(self):
        salud = smart.parse(tabla_ata([
            (9, 95, 21000),          # horas encendido
            (12, 99, 1200),          # ciclos de encendido
            (241, 100, 40_000_000),  # sectores escritos
        ]), "ata")
        self.assertEqual(salud.power_on_hours, 21000)
        self.assertEqual(salud.power_cycles, 1200)
        self.assertEqual(salud.written_bytes, 40_000_000 * 512)

    def test_el_desgaste_de_un_ssd_va_al_reves_que_en_nvme(self):
        # El atributo guarda la vida que queda; el modelo, la gastada.
        salud = smart.parse(tabla_ata([(231, 88, 0)]), "ata")
        self.assertEqual(salud.percentage_used, 12)
        self.assertEqual(salud.life_left_percent, 88)

    def test_cada_fabricante_usa_un_atributo_distinto_para_lo_mismo(self):
        for identificador in (231, 233, 177, 202):
            salud = smart.parse(tabla_ata([(identificador, 70, 0)]), "ata")
            self.assertEqual(salud.life_left_percent, 70, f"atributo {identificador}")

    def test_los_sectores_con_problemas_se_suman(self):
        salud = smart.parse(tabla_ata([
            (5, 100, 4),      # reasignados
            (197, 100, 2),    # pendientes
            (198, 100, 1),    # incorregibles
        ]), "ata")
        self.assertEqual(salud.media_errors, 7)

    def test_la_temperatura_esta_en_el_byte_bajo(self):
        # Muchos discos guardan mínimos y máximos en los bits altos del mismo
        # contador; la temperatura de ahora está abajo.
        self.assertEqual(smart.ata_temperature(tabla_ata([(194, 62, 0x1E0027)])), 39.0)

    def test_una_temperatura_imposible_se_descarta(self):
        self.assertIsNone(smart.ata_temperature(tabla_ata([(194, 0, 200)])))

    def test_una_tabla_vacia(self):
        self.assertIsNone(smart.parse(tabla_ata(), "ata"))


class TestEntradasRaras(unittest.TestCase):
    def test_una_familia_que_no_existe(self):
        self.assertIsNone(smart.parse(registro_nvme(), "scsi"))

    def test_sin_datos(self):
        self.assertIsNone(smart.parse(b"", "nvme"))
        self.assertIsNone(smart.parse(b"", "ata"))


class TestElAyudanteSoloLeeBytes(unittest.TestCase):
    """El ayudante privilegiado no interpreta nada, y eso está probado.

    Es la decisión de diseño que mantiene pequeño el código que corre como
    root: si el análisis viviera ahí, un fallo interpretando el registro de un
    disco raro sería un fallo con privilegios.
    """

    def test_el_modulo_de_analisis_no_necesita_privilegios(self):
        import inspect

        from silux.privileged import helper
        fuente = inspect.getsource(helper)
        # El ayudante no importa el analizador ni lo llama.
        self.assertNotIn("import smart", fuente)
        self.assertNotIn("smart.parse", fuente)

    def test_solo_acepta_nombres_de_disco_conocidos(self):
        from silux.privileged.helper import DISK_NAME
        for bueno in ("sda", "sdb", "nvme0n1", "nvme0", "hda"):
            self.assertTrue(DISK_NAME.match(bueno), bueno)
        for malo in ("../etc/shadow", "sda; rm -rf /", "mem", "/dev/sda",
                     "sda1", "", "nvme0n1p2"):
            self.assertFalse(DISK_NAME.match(malo), malo)


if __name__ == "__main__":
    unittest.main()


class TestContadoresDeFabricante(unittest.TestCase):
    """Los atributos de SATA no significan lo mismo en todos los discos.

    Es la trampa que advierte la cabecera del módulo, y en la que se cayó igual:
    un Seagate declaraba 132 658 654 884 699 horas de encendido, que son quince
    mil millones de años. Guarda algo suyo en los dos bytes altos del contador.
    """

    def test_las_horas_se_leen_en_32_bits(self):
        # El valor real de un ST2000DM008 de año y medio.
        salud = smart.parse(tabla_ata([(9, 80, 132658654884699)]), "ata")
        self.assertEqual(salud.power_on_hours, 13147)

    def test_lo_escrito_sí_usa_los_48_bits(self):
        # Ahí no sobra sitio: un disco puede escribir más de lo que cabe en 32
        # bits de sectores, así que se leen los seis bytes.
        salud = smart.parse(tabla_ata([(241, 100, 40_000_000_000)]), "ata")
        self.assertEqual(salud.written_bytes, 40_000_000_000 * 512)

    def test_unas_horas_imposibles_se_descartan(self):
        # Por si algún fabricante usa los 32 bits bajos para otra cosa: ningún
        # disco fabricado lleva doscientos años encendido.
        salud = smart.parse(tabla_ata([(9, 80, 0x7FFFFFFF)]), "ata")
        self.assertIsNone(salud.power_on_hours)

    def test_crucial_guarda_lo_escrito_en_otro_atributo(self):
        # Los MX500 usan el 246 donde otros usan el 241.
        salud = smart.parse(tabla_ata([(246, 100, 17_800_000_000)]), "ata")
        self.assertEqual(salud.written_bytes, 17_800_000_000 * 512)

    def test_si_están_los_dos_gana_el_de_siempre(self):
        salud = smart.parse(tabla_ata([(241, 100, 1000), (246, 100, 2000)]), "ata")
        self.assertEqual(salud.written_bytes, 1000 * 512)

    def test_un_disco_mecanico_no_tiene_desgaste(self):
        # Los platos no se gastan por escribir, así que no publican el atributo.
        salud = smart.parse(tabla_ata([(9, 80, 13147), (241, 100, 1000)]), "ata")
        self.assertIsNone(salud.life_left_percent)


class TestUnidadDeEscritura(unittest.TestCase):
    """En qué unidades cuenta cada disco lo que lleva escrito.

    El atributo 241 se llama «LBAs escritas» y casi todos cuentan sectores de
    512 bytes, pero no es obligatorio. Kioxia cuenta bloques de 32 MiB: dando
    por hecho los 512, un disco con 23 TiB escritos declaraba 367 MB.
    """

    def test_lo_normal_siguen_siendo_sectores(self):
        # Lo que no esté en la tabla no cambia de comportamiento.
        for fabricante, modelo in (("Crucial", "CT500MX500SSD1"),
                                   ("Samsung", "SSD 870 EVO"),
                                   ("WDC", "WD Blue SA510"),
                                   (None, None)):
            with self.subTest(fabricante=fabricante):
                self.assertEqual(smart._unidad_escritura(fabricante, modelo),
                                 smart.ATA_SECTOR)

    def test_kioxia_cuenta_en_bloques_de_32_mib(self):
        # Medido: escritos 4,09 GiB, el contador subió 133 → 31,5 MiB por unidad.
        self.assertEqual(smart._unidad_escritura("Kioxia", "KIOXIA-EXCERIA S"),
                         32 * 1024 * 1024)

    def test_toshiba_tambien(self):
        """Son los mismos discos antes del cambio de nombre de la división."""
        self.assertEqual(smart._unidad_escritura(None, "TOSHIBA THNSNJ256GCSU"),
                         32 * 1024 * 1024)

    def test_da_igual_dónde_venga_el_nombre(self):
        # Unos discos ponen la marca en el fabricante y otros solo en el modelo.
        self.assertEqual(smart._unidad_escritura("KIOXIA", None), 32 * 1024 * 1024)
        self.assertEqual(smart._unidad_escritura(None, "kioxia exceria"),
                         32 * 1024 * 1024)

    def test_el_disco_real_da_una_cifra_creible(self):
        """752 881 unidades de un KIOXIA-EXCERIA son 23 TiB, no 367 MB."""
        crudo = 752_881
        escrito = crudo * smart._unidad_escritura("Kioxia", "KIOXIA-EXCERIA S")
        self.assertAlmostEqual(escrito / 1024 ** 4, 23.0, places=1)
        # Y con la cuenta de antes salía algo imposible para 3 834 horas.
        self.assertLess(crudo * smart.ATA_SECTOR / 1024 ** 2, 400)
