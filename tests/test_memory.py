"""La memoria: canales, velocidad y lo que se puede decir de los dos.

En canal único la memoria rinde la mitad, y no hay nada en todo el sistema que
lo diga. Es de los pocos problemas de hardware a la vez muy comunes, muy caros
en rendimiento y completamente invisibles.
"""

import pathlib
import unittest

from silux import render




class TestCanalesDeMemoria(unittest.TestCase):
    """Cuántos canales tienen módulo puesto, y cuándo eso es un problema."""

    def _mod(self, locator=None, bank=None, poblado=True):
        from silux.model import MemoryModule

        return MemoryModule(locator=locator, bank=bank, populated=poblado)

    def test_dos_bancos_distintos_son_doble_canal(self):
        """Los datos son los de una X570 de verdad."""
        modulos = [
            self._mod("DIMM 0", "P0 CHANNEL A", False),
            self._mod("DIMM 1", "P0 CHANNEL A", True),
            self._mod("DIMM 0", "P0 CHANNEL B", False),
            self._mod("DIMM 1", "P0 CHANNEL B", True),
        ]
        self.assertEqual(render.memory_channels(modulos), 2)
        self.assertIn("doble canal", render.memory_channel_label(modulos))
        self.assertIsNone(render.memory_channel_warning(modulos))

    def test_dos_modulos_en_el_mismo_canal_se_avisan(self):
        modulos = [self._mod("DIMM 0", "P0 CHANNEL A"),
                   self._mod("DIMM 1", "P0 CHANNEL A"),
                   self._mod("DIMM 0", "P0 CHANNEL B", False)]
        self.assertEqual(render.memory_channels(modulos), 1)
        aviso = render.memory_channel_warning(modulos)
        self.assertIn("mismo canal", aviso)

    def test_un_portatil_con_un_solo_modulo(self):
        """La convención de los portátiles es otra: el canal va en el
        localizador y no en el banco."""
        modulos = [self._mod("ChannelA-DIMM0", None, True),
                   self._mod("ChannelB-DIMM0", None, False)]
        self.assertEqual(render.memory_channels(modulos), 1)
        self.assertIn("mitad de ancho de banda",
                      render.memory_channel_warning(modulos))

    def test_cuatro_canales_se_llaman_por_su_nombre(self):
        modulos = [self._mod(f"DIMM_{c}1") for c in "ABCD"]
        self.assertEqual(render.memory_channels(modulos), 4)
        self.assertIn("cuádruple canal", render.memory_channel_label(modulos))

    def test_una_placa_que_no_dice_el_canal_no_se_adivina(self):
        """Inventarlo sería peor que callarse: manda a alguien a abrir el
        equipo para nada."""
        modulos = [self._mod("DIMM 0", "BANK 0"), self._mod("DIMM 1", "BANK 1")]
        self.assertIsNone(render.memory_channels(modulos))
        self.assertIsNone(render.memory_channel_label(modulos))
        self.assertIsNone(render.memory_channel_warning(modulos))

    def test_los_zocalos_vacios_no_cuentan_como_canal(self):
        modulos = [self._mod("DIMM_A1", None, True),
                   self._mod("DIMM_B1", None, False)]
        self.assertEqual(render.memory_channels(modulos), 1)

    def test_sin_modulos_no_hay_nada_que_decir(self):
        self.assertIsNone(render.memory_channels([]))
        self.assertIsNone(render.memory_channel_warning([]))

    def test_un_solo_modulo_sin_zocalos_libres_no_se_reprocha(self):
        """Si no hay dónde poner otro, el aviso solo sirve para fastidiar."""
        self.assertIsNone(render.memory_channel_warning([self._mod("DIMM_A1")]))


class TestElCanalNoEsSoloLaLetra(unittest.TestCase):
    """Dos canales pueden llamarse los dos «A».

    Lo trajo un ThinkPad T14 con dos módulos bien repartidos: el firmware los
    llama «Controller0-ChannelA» y «Controller1-ChannelA-DIMM0», que son dos
    canales, uno por controlador. Contando solo la letra salía «canal único»
    en una máquina que va en doble canal, y encima con el consejo de repartir
    los módulos, que ya estaban repartidos.
    """

    class _Modulo:
        def __init__(self, locator, bank=None, populated=True):
            self.locator, self.bank, self.populated = locator, bank, populated

    def test_dos_controladores_son_dos_canales(self):
        from silux import render

        modulos = [self._Modulo("Controller0-ChannelA"),
                   self._Modulo("Controller1-ChannelA-DIMM0")]
        self.assertEqual(render.memory_channels(modulos), 2)

    def test_y_no_se_aconseja_repartir_lo_que_ya_está_repartido(self):
        from silux import render

        modulos = [self._Modulo("Controller0-ChannelA"),
                   self._Modulo("Controller1-ChannelA-DIMM0")]
        self.assertIsNone(render.memory_channel_warning(modulos))

    def test_dos_en_el_mismo_controlador_siguen_siendo_uno(self):
        from silux import render

        modulos = [self._Modulo("ChannelA-DIMM0"),
                   self._Modulo("ChannelA-DIMM1")]
        self.assertEqual(render.memory_channels(modulos), 1)
        self.assertIsNotNone(render.memory_channel_warning(modulos))

    def test_el_sobremesa_de_toda_la_vida_no_cambia(self):
        from silux import render

        modulos = [self._Modulo("DIMM A1"), self._Modulo("DIMM B1")]
        self.assertEqual(render.memory_channels(modulos), 2)

    def test_sin_canal_en_el_localizador_se_sigue_callando(self):
        from silux import render

        self.assertIsNone(render.memory_channels([self._Modulo("BANK 0")]))


def _modulo(catalogado, funcionando, poblado=True):
    """Un módulo sin SPD, donde `rated_mts` cae en la velocidad de SMBIOS."""
    from silux.model import MemoryModule

    return MemoryModule(populated=poblado, speed_mts=catalogado,
                        configured_mts=funcionando)


class TestElRedondeoDeLosGradosJedec(unittest.TestCase):
    """Un MT/s de diferencia no es un recorte.

    Los grados JEDEC salen de un reloj que cae en tercios —DDR4-2666 son
    1333,33 MHz, o sea 2666,67 MT/s— y cada firmware redondea a su manera: el
    SPD de un SK Hynix dice 2667 y la BIOS pone 2666. Comparando a pelo, eso
    encendía el aviso, la insignia «por debajo de su velocidad» y el triángulo
    de la fila. Lo trajo un ThinkCentre M80q.
    """

    def test_un_mts_de_diferencia_no_marca_nada(self):
        self.assertFalse(_modulo(2667, 2666).underclocked)

    def test_ni_en_los_otros_grados_con_tercio(self):
        for catalogado, funcionando in ((2134, 2133), (2934, 2933),
                                        (3734, 3733), (1867, 1866)):
            with self.subTest(grado=catalogado):
                self.assertFalse(_modulo(catalogado, funcionando).underclocked)

    def test_un_recorte_de_verdad_se_sigue_viendo(self):
        """El margen no puede tragarse un grado entero: entre dos contiguos
        hay 133 MT/s como poco en DDR4 y 400 en DDR5."""
        for catalogado, funcionando in ((3200, 2666), (2666, 2400),
                                        (5600, 4800), (2933, 2666)):
            with self.subTest(de=catalogado, a=funcionando):
                self.assertTrue(_modulo(catalogado, funcionando).underclocked)


class TestElTechoDelConjuntoEsElDelMasLento(unittest.TestCase):
    """El consejo mandaba a la BIOS a por algo imposible.

    Se tomaba el primer módulo que fuera lento y se prometía su velocidad
    catalogada. Con uno de 3200 y otro de 2667 eso decía «va a 2666 de los
    3200 que declara admitir, suele ser el perfil rápido sin activar», y es
    falso: todos los módulos van al mismo reloj, así que el conjunto se queda
    en el del que menos da y ese equipo no verá 3200 active lo que active.
    """

    def _aviso(self, *pares):
        from silux import render

        return render.memory_speed_warning([_modulo(c, f) for c, f in pares])

    def test_con_modulos_desparejos_ya_a_tope_no_se_promete_nada(self):
        """El caso del M80q entero: 3200 y 2667 corriendo a 2666."""
        aviso = self._aviso((3200, 2666), (2667, 2666))
        self.assertIsNotNone(aviso, "callarse deja la cifra de 3200 sin explicar")
        self.assertIn("2667", aviso)
        self.assertNotIn("perfil rápido", aviso,
                         "no hay perfil que activar: ya va a tope")

    def test_y_se_dice_que_el_3200_no_cambia_nada(self):
        aviso = self._aviso((3200, 2666), (2667, 2666))
        self.assertIn("3200", aviso, "hay que nombrar al que declara más")
        self.assertIn("2666", aviso)

    def test_cuando_hay_margen_de_verdad_se_promete_el_techo_del_conjunto(self):
        """Desparejos y los dos por debajo: lo alcanzable es 2667, no 3200."""
        aviso = self._aviso((3200, 2133), (2667, 2133))
        self.assertIn("2667", aviso)
        self.assertNotIn("3200", aviso,
                         "prometer 3200 manda a pelearse con la BIOS para nada")

    def test_con_modulos_iguales_sigue_el_consejo_de_siempre(self):
        aviso = self._aviso((3200, 2666), (3200, 2666))
        self.assertIn("3200", aviso)
        self.assertIn("XMP", aviso)

    def test_todo_en_orden_no_dice_nada(self):
        self.assertIsNone(self._aviso((3200, 3200), (3200, 3200)))

    def test_el_redondeo_tampoco_dispara_el_aviso(self):
        self.assertIsNone(self._aviso((2667, 2666), (2667, 2666)))

    def test_sin_velocidades_no_se_inventa(self):
        """Sin permisos no hay SMBIOS y no se sabe a cuánto va."""
        from silux import render

        self.assertIsNone(render.memory_speed_warning(
            [_modulo(None, None), _modulo(None, None)]))


class TestElTituloDeCadaZocalo(unittest.TestCase):
    """El localizador del firmware no es un título.

    Llega con el controlador, el canal y el número pegados y sin espacios, y
    cada fabricante lo escribe a su manera: «Controller0-ChannelA» en un
    Lenovo, «DIMM_A1» en una placa de escritorio. Así la misma pestaña se ve
    distinta en cada equipo, y con cuatro zócalos el nombre se repite entre
    canales: salían dos «DIMM 0» y dos «DIMM 1».

    Los localizadores de aquí son todos de máquinas reales.
    """

    def _titulos(self, *locators):
        from silux import render

        salida = render.slot_labels(list(locators))
        return [salida.get(l, l) for l in locators]

    def test_el_canal_sale_siempre_que_se_conozca(self):
        """Es lo que decide el rendimiento y a lo que se viene aquí."""
        self.assertEqual(
            self._titulos("Controller0-ChannelA", "Controller0-ChannelB"),
            ["Canal A", "Canal B"])

    def test_el_controlador_solo_cuando_hace_falta(self):
        """Un ThinkPad T14 con los dos módulos en canal A de controladores
        distintos: sin el controlador los dos se llamarían igual."""
        self.assertEqual(
            self._titulos("Controller0-ChannelA", "Controller1-ChannelA"),
            ["Controlador 0 · Canal A", "Controlador 1 · Canal A"])

    def test_con_cuatro_zocalos_ya_no_se_repiten(self):
        self.assertEqual(
            self._titulos("ChannelA-DIMM0", "ChannelA-DIMM1",
                          "ChannelB-DIMM0", "ChannelB-DIMM1"),
            ["Canal A · DIMM 0", "Canal A · DIMM 1",
             "Canal B · DIMM 0", "Canal B · DIMM 1"])

    def test_el_canal_pegado_al_numero_tambien_se_entiende(self):
        """«DIMM_A1» y «DIMM A» son de placas de escritorio."""
        self.assertEqual(self._titulos("DIMM_A1", "DIMM_B1"),
                         ["Canal A", "Canal B"])
        self.assertEqual(self._titulos("DIMM A", "DIMM B"),
                         ["Canal A", "Canal B"])

    def test_un_solo_modulo_tambien_se_limpia(self):
        self.assertEqual(self._titulos("Controller0-ChannelA"), ["Canal A"])

    def test_lo_que_no_se_entiende_se_deja_crudo(self):
        """Inventarse una posición a partir de algo que no se reconoce es peor
        que enseñar lo que puso el firmware."""
        for crudos in (("A_RARO_1", "B_RARO_2"), ("Zócalo 0", "Zócalo 2"),
                       ("SODIMM", "SODIMM2")):
            with self.subTest(crudos=crudos):
                self.assertEqual(self._titulos(*crudos), list(crudos))

    def test_si_no_hay_nada_que_mejorar_no_se_toca(self):
        """«DIMM 0» ya es el título que saldría, así que no se reescribe."""
        from silux import render

        self.assertEqual(render.slot_labels(["DIMM 0", "DIMM 1"]), {})

    def test_nunca_deja_dos_zocalos_con_el_mismo_titulo(self):
        """Es el fallo que venía a arreglar: dos tarjetas iguales no se
        pueden distinguir, y entonces mejor el crudo."""
        from silux import render

        for locators in (["ChannelA-DIMM0", "ChannelA-DIMM1"],
                         ["Controller0-ChannelA", "Controller1-ChannelA"],
                         ["ChannelA-DIMM0", "ChannelB-DIMM0"],
                         ["Controller0-ChannelA-DIMM1", "Controller1-ChannelA-DIMM0"]):
            with self.subTest(locators=locators):
                salida = render.slot_labels(locators)
                titulos = [salida.get(l, l) for l in locators]
                self.assertEqual(len(set(titulos)), len(titulos), titulos)


class TestLasDosDetectorasDeCanalNoSePisan(unittest.TestCase):
    """`render` tiene dos lecturas del localizador y son cosas distintas.

    Una cuenta canales para saber si la memoria va en doble canal; la otra
    compone el título del zócalo. Al escribir la segunda se reutilizaron los
    nombres `_CANAL` y `_CONTROLADOR` de la primera y se la llevaron por
    delante: diecisiete tests en rojo. En un módulo de novecientas líneas eso
    no se ve al escribirlo.
    """

    def test_cada_una_tiene_sus_propios_patrones(self):
        from silux import render

        self.assertIsInstance(render._CANAL, tuple,
                              "la de contar canales usa varios patrones")
        self.assertTrue(hasattr(render, "_ZOC_CANAL"),
                        "la del título tiene que llevar su propio prefijo")

    def test_contar_canales_sigue_funcionando(self):
        """La prueba de que no se pisan, ejecutada y no razonada."""
        from silux import render
        from silux.model import MemoryModule

        modulos = [MemoryModule(populated=True, locator="Controller0-ChannelA"),
                   MemoryModule(populated=True, locator="Controller1-ChannelA")]
        self.assertEqual(render.memory_channels(modulos), 2)


class TestElTituloLlegaALaTarjeta(unittest.TestCase):
    """Probar la función no es probar que se vea.

    La regla de la casa: un dato no está terminado hasta que hay un test que lo
    mira en pantalla, montando la página de verdad. `slot_labels` puede estar
    perfecta y la tarjeta seguir titulándose con el localizador crudo si nadie
    la llama, que es como estaba antes.
    """

    @classmethod
    def setUpClass(cls):
        import os

        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication

        cls.app = QApplication.instance() or QApplication([])

    def _titulos_en_pantalla(self, *locators):
        from silux.model import CpuInfo, CpuType, MemoryModule, Snapshot
        from silux.settings import Preferences
        from silux.ui import theme
        from silux.ui.pages.memory import MemoryPage

        pagina = MemoryPage(theme.palette_for(self.app, "dark"), Preferences())
        self.addCleanup(pagina.deleteLater)
        modulos = [MemoryModule(populated=True, locator=l, size_bytes=8 << 30)
                   for l in locators]
        pagina.apply(Snapshot(
            monotonic_ns=0,
            cpu=CpuInfo(types=(CpuType(key="general", label="g"),)),
            modules=tuple(modulos),
        ))
        self.app.processEvents()

        from silux.ui.widgets import Card

        # En minúsculas: que el título se pinte en versalitas lo decide la
        # hoja de estilos, y aquí se comprueba el dato, no el estilo.
        return [c._title_label.text().lower() for c in pagina.findChildren(Card)
                if c._title_label is not None]

    def test_las_tarjetas_se_titulan_con_el_canal(self):
        titulos = self._titulos_en_pantalla("Controller0-ChannelA",
                                            "Controller0-ChannelB")
        self.assertIn("canal a", titulos)
        self.assertIn("canal b", titulos)
        self.assertNotIn("controller0-channela", titulos,
                         "la tarjeta sigue con el localizador crudo")

    def test_y_lo_que_no_se_reconoce_se_queda_como_estaba(self):
        titulos = self._titulos_en_pantalla("SODIMM", "SODIMM2")
        self.assertIn("sodimm", titulos)
        self.assertIn("sodimm2", titulos)


class TestLaTarjetaDePermisos(TestElTituloLlegaALaTarjeta):
    """La que se titulaba «Detalle de los módulos» y no traía ningún detalle.

    Dentro solo hay la explicación de qué falta y los dos botones, y desaparece
    en cuanto se dan los permisos: nunca llega a contener un detalle de nada.
    El título nuevo dice lo que hay, y este test lo ata al comportamiento —si
    algún día se quedara puesta con los módulos ya leídos, pasaría a mentir.
    """

    def _pagina(self, con_modulos):
        from silux.model import CpuInfo, CpuType, MemoryModule, Snapshot
        from silux.settings import Preferences
        from silux.ui import theme
        from silux.ui.pages.memory import MemoryPage

        pagina = MemoryPage(theme.palette_for(self.app, "dark"), Preferences())
        self.addCleanup(pagina.deleteLater)
        modulos = ((MemoryModule(populated=True, locator="DIMM 0",
                                 size_bytes=8 << 30),) if con_modulos else ())
        pagina.apply(Snapshot(
            monotonic_ns=0,
            cpu=CpuInfo(types=(CpuType(key="general", label="g"),)),
            modules=modulos,
        ))
        self.app.processEvents()
        return pagina

    def test_sale_solo_mientras_falten_los_modulos(self):
        pagina = self._pagina(con_modulos=False)
        self.assertFalse(pagina.elevation.isHidden(),
                         "sin los módulos es cuando hay algo que pedir")

    def test_y_desaparece_en_cuanto_se_leen(self):
        pagina = self._pagina(con_modulos=True)
        self.assertTrue(pagina.elevation.isHidden(),
                        "con los módulos ya leídos la tarjeta sobra, y su "
                        "título dejaría de ser cierto")


class TestLosDosPerfilesNoSeLlamanIgual(unittest.TestCase):
    """Arriba «Perfiles —» y abajo una tarjeta «Perfiles y temporizaciones»
    con filas dentro: a la vista se contradecían.

    Son cosas distintas. La fila cuenta los perfiles rápidos que trae el chip
    —XMP o EXPO—, que este programa reconoce pero no interpreta; la tarjeta
    enseña las temporizaciones, empezando por las de JEDEC, que existen
    siempre. Con las dos llamándose «Perfiles» parecía que una desmentía a la
    otra.
    """

    def test_la_fila_dice_de_qué_perfiles_habla(self):
        import json
        import pathlib as _p

        for codigo in ("es", "en"):
            idioma = json.loads(
                (_p.Path("silux/db/lang") / f"{codigo}.json").read_text(
                    encoding="utf-8"))
            fila = idioma["memory.field.profiles"]
            tarjeta = idioma["memory.card.timings"]
            with self.subTest(idioma=codigo):
                self.assertNotEqual(fila.lower(), tarjeta.lower())
                self.assertNotEqual(
                    fila.lower(), tarjeta.lower().split()[0],
                    "la fila se llama igual que la primera palabra de la "
                    "tarjeta, que es como se leían la una contra la otra")


class TestLaVelocidadQueEnsenaLaFicha(TestElTituloLlegaALaTarjeta):
    """Dos convenciones en la misma ficha.

    El «Catalogado a» sale del SPD y lo nombramos nosotros como grado —3200,
    2666—; el «Funcionando a» venía crudo de la tabla SMBIOS, y cada BIOS
    redondea a su manera el grado que lleva tercio. En un i5-10400 se leía
    «Catalogado a 3200» y «Funcionando a 2667», y 2667 no es el nombre de
    ninguna velocidad.
    """

    def _ficha(self, configurada):
        from silux.model import CpuInfo, CpuType, MemoryModule, Snapshot
        from silux.settings import Preferences
        from silux.ui import theme
        from silux.ui.pages.memory import MemoryPage

        pagina = MemoryPage(theme.palette_for(self.app, "dark"), Preferences())
        self.addCleanup(pagina.deleteLater)
        pagina.apply(Snapshot(
            monotonic_ns=0,
            cpu=CpuInfo(types=(CpuType(key="g", label="g"),)),
            modules=(MemoryModule(populated=True, locator="DIMM 0",
                                  size_bytes=8 << 30, speed_mts=3200,
                                  configured_mts=configurada),),
        ))
        self.app.processEvents()
        from PySide6.QtWidgets import QLabel

        return [w.text() for w in pagina.findChildren(QLabel)]

    def test_el_2667_de_la_bios_se_ensena_como_su_grado(self):
        textos = self._ficha(2667)
        self.assertTrue(any("2666 MT/s" in t for t in textos), textos)
        self.assertFalse(any("2667 MT/s" in t for t in textos),
                         "2667 no es el nombre de ninguna velocidad")

    def test_una_bios_que_ya_escribe_2666_sale_igual(self):
        """Las dos convenciones tienen que llevar al mismo sitio."""
        self.assertTrue(any("2666 MT/s" in t for t in self._ficha(2666)))

    def test_el_numero_del_firmware_no_se_pierde(self):
        """Es el que sale en dmidecode: hace falta para contrastar."""
        from silux import render

        self.assertEqual(render.velocidad_de_memoria(2667), 2666)
        idioma = __import__("json").loads(
            (RAIZ_LANG / "es.json").read_text(encoding="utf-8"))
        self.assertIn("dmidecode", idioma["memory.tip.firmware"])

    def test_el_aviso_dice_la_misma_cifra_que_la_ficha(self):
        """Si la ficha dice 2666 y el aviso 2667, uno de los dos miente."""
        from silux import render
        from silux.model import MemoryModule

        aviso = render.memory_speed_warning(
            [MemoryModule(populated=True, speed_mts=3200, configured_mts=2667)])
        self.assertIn("2666", aviso)
        self.assertNotIn("2667", aviso)


RAIZ_LANG = pathlib.Path(__file__).resolve().parent.parent / "silux" / "db" / "lang"
