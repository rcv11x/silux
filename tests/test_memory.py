"""La memoria: canales, velocidad y lo que se puede decir de los dos.

En canal único la memoria rinde la mitad, y no hay nada en todo el sistema que
lo diga. Es de los pocos problemas de hardware a la vez muy comunes, muy caros
en rendimiento y completamente invisibles.
"""

import pathlib
import unittest

from silux import render
from tests import pantalla, qt




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

        return render.slot_names([(l, None) for l in locators])

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

        self.assertEqual(render.slot_names([("DIMM 0", None), ("DIMM 1", None)]),
                         ["DIMM 0", "DIMM 1"])

    def test_nunca_deja_dos_zocalos_con_el_mismo_titulo(self):
        """Es el fallo que venía a arreglar: dos tarjetas iguales no se
        pueden distinguir, y entonces mejor el crudo."""
        from silux import render

        for locators in (["ChannelA-DIMM0", "ChannelA-DIMM1"],
                         ["Controller0-ChannelA", "Controller1-ChannelA"],
                         ["ChannelA-DIMM0", "ChannelB-DIMM0"],
                         ["Controller0-ChannelA-DIMM1", "Controller1-ChannelA-DIMM0"]):
            with self.subTest(locators=locators):
                titulos = render.slot_names([(l, None) for l in locators])
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
    mira en pantalla, montando la página de verdad. `slot_names` puede estar
    perfecta y la tarjeta seguir titulándose con el localizador crudo si nadie
    la llama, que es como estaba antes.
    """

    @classmethod
    def setUpClass(cls):
        import os

        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication

        cls.app = qt.app()

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

        from silux.i18n import _

        # El zócalo va en su campo de la ficha; el título es «Módulo N», el
        # mismo con permisos y sin ellos. En minúsculas: aquí se comprueba el
        # dato, no el estilo.
        return [g._values[_("memory.field.slot")].full_text().lower()
                for g in pagina._slot_grids]

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


class TestLosZocalosLibresNoOcupanUnaTarjeta(TestElTituloLlegaALaTarjeta):
    """Una tarjeta entera por zócalo vacío para poner «Vacío».

    Con cuatro zócalos y dos módulos se llevaban la mitad del ancho, y
    apretaban a las dos que sí tienen datos en un cuarto de pantalla cada una.
    Con ocho zócalos serían tres cuartos. Es lo mismo que ya se resolvió en
    Gráficos con las salidas de vídeo sin nada enchufado.
    """

    def _pagina(self):
        from silux.model import CpuInfo, CpuType, MemoryModule, Snapshot
        from silux.settings import Preferences
        from silux.ui import theme
        from silux.ui.pages.memory import MemoryPage

        pagina = MemoryPage(theme.palette_for(self.app, "dark"), Preferences())
        self.addCleanup(pagina.deleteLater)
        puesto = lambda l: MemoryModule(populated=True, locator=l,
                                        size_bytes=8 << 30)
        vacio = lambda l: MemoryModule(populated=False, locator=l)
        pagina.apply(Snapshot(
            monotonic_ns=0,
            cpu=CpuInfo(types=(CpuType(key="g", label="g"),)),
            modules=(puesto("ChannelA-DIMM0"), vacio("ChannelA-DIMM1"),
                     puesto("ChannelB-DIMM0"), vacio("ChannelB-DIMM1")),
        ))
        self.app.processEvents()
        return pagina

    def test_solo_hay_tarjeta_para_los_que_tienen_modulo(self):
        from silux.ui.widgets import Card

        from silux.i18n import _

        pagina = self._pagina()
        zocalos = [g._values[_("memory.field.slot")].full_text().lower()
                   for g in pagina._slot_grids]
        self.assertEqual(zocalos, ["canal a · dimm 0", "canal b · dimm 0"],
                         "un zócalo vacío no necesita una tarjeta entera")

    def test_no_se_dice_cuantos_hay_libres_ni_el_total(self):
        """La H510M PRO-E de la oficina tiene dos ranuras y su firmware
        declara cuatro: con permisos salía «2 de 4 zócalos» y dos libres
        que no existen. Una vacía de verdad y una fantasma son iguales en
        la tabla del firmware, así que no se dice ni lo uno ni lo otro."""
        pagina = self._pagina()
        self.assertFalse(hasattr(pagina, "slots_free"))
        self.assertIn("2 módulos", pagina.subtitle.text())
        self.assertNotIn("de 4", pagina.subtitle.text())
        self.assertNotIn("libre", " ".join(pantalla.textos_de(pagina)))


RAIZ_LANG = pathlib.Path(__file__).resolve().parent.parent / "silux" / "db" / "lang"


class TestSinSmbiosNoSeAfirmaUnZocalo(TestElTituloLlegaALaTarjeta):
    """La pantalla decía no saber el zócalo y titulaba con un número de zócalo.

    El `slot` del SPD es la dirección del chip en el bus i2c —0x50 es 0 y 0x52
    es 2—, no la posición en la placa. Titulando «Zócalo 0» y «Zócalo 2» se
    contradecía el subtítulo de dos líneas más arriba, «el zócalo y la
    capacidad necesitan permisos», y hacía pensar que el zócalo 1 estaba libre
    cuando resulta que son el primero de cada canal.
    """

    def _pagina_desde_spd(self):
        from silux.model import CpuInfo, CpuType, Snapshot
        from silux.settings import Preferences
        from silux.spd import SpdInfo
        from silux.ui import theme
        from silux.ui.pages.memory import MemoryPage

        pagina = MemoryPage(theme.palette_for(self.app, "dark"), Preferences())
        self.addCleanup(pagina.deleteLater)
        pagina.apply(Snapshot(
            monotonic_ns=0,
            cpu=CpuInfo(types=(CpuType(key="g", label="g"),)),
            modules=(),                       # sin permisos no hay SMBIOS
            spd=(SpdInfo(address="10-0050", slot=0, decoded=True),
                 SpdInfo(address="10-0052", slot=2, decoded=True)),
        ))
        self.app.processEvents()
        return pagina

    def _tarjetas(self, pagina):
        from silux.ui.widgets import Card

        return [c for c in pagina.findChildren(Card) if c._title_label]

    def test_no_se_titula_con_un_numero_de_zocalo(self):
        titulos = [c._title_label.text().lower()
                   for c in self._tarjetas(self._pagina_desde_spd())]
        self.assertNotIn("zócalo 0", titulos,
                         "ese 0 es la dirección del chip, no el zócalo")
        self.assertNotIn("zócalo 2", titulos)

    def test_se_numeran_por_orden_de_lectura(self):
        titulos = [c._title_label.text().lower()
                   for c in self._tarjetas(self._pagina_desde_spd())]
        self.assertIn("módulo 1", titulos)
        self.assertIn("módulo 2", titulos)

    def test_la_direccion_del_chip_no_se_pierde(self):
        """Es el único dato de posición que hay, y sigue estando donde no
        puede confundirse con el zócalo de la placa."""
        pistas = [c.toolTip() for c in self._tarjetas(self._pagina_desde_spd())]
        self.assertTrue(any("10-0050" in p for p in pistas), pistas)
        self.assertTrue(any("10-0052" in p for p in pistas), pistas)

    def test_con_smbios_el_zocalo_va_en_su_campo_y_el_titulo_no_cambia(self):
        """Revisión del autor: las tarjetas se llaman igual con permisos y sin
        ellos. Con el firmware el zócalo de verdad va en su campo."""
        from silux.i18n import _

        pagina = self._pagina_con_smbios()
        titulos = [c._title_label.text().lower() for c in self._tarjetas(pagina)]
        self.assertIn("módulo 1", titulos)
        self.assertEqual(pagina._slot_grids[0]._values[_("memory.field.slot")].full_text(),
                         "Canal A")

    def test_sin_permisos_el_zocalo_no_se_afirma(self):
        from silux.i18n import _

        pagina = self._pagina_desde_spd()
        campo = pagina._slot_grids[0]._values[_("memory.field.slot")]
        self.assertFalse(campo.isVisibleTo(pagina) and campo.full_text())

    def _pagina_con_smbios(self):
        from silux.model import CpuInfo, CpuType, MemoryModule, Snapshot
        from silux.settings import Preferences
        from silux.ui import theme
        from silux.ui.pages.memory import MemoryPage

        pagina = MemoryPage(theme.palette_for(self.app, "dark"), Preferences())
        self.addCleanup(pagina.deleteLater)
        pagina.apply(Snapshot(
            monotonic_ns=0,
            cpu=CpuInfo(types=(CpuType(key="g", label="g"),)),
            modules=(MemoryModule(populated=True, locator="ChannelA-DIMM0",
                                  size_bytes=8 << 30),
                     MemoryModule(populated=True, locator="ChannelB-DIMM0",
                                  size_bytes=8 << 30)),
        ))
        self.app.processEvents()
        return pagina


class TestElBancoNoSeDiceDosVeces(unittest.TestCase):
    """La fila se titula «Banco» y el firmware escribe «BANK 0»."""

    def test_se_quita_la_palabra_que_ya_lleva_la_fila(self):
        from silux import render

        for crudo, esperado in (("BANK 0", "0"), ("BANK 1", "1"),
                                ("Bank0", "0"), ("bank_2", "2")):
            with self.subTest(crudo=crudo):
                self.assertEqual(render.banco_de_memoria(crudo), esperado)

    def test_lo_que_trae_algo_más_se_deja_entero(self):
        """En «Node0_Bank0» el resto sí distingue, y recortarlo perdería el
        nodo. Solo se quita cuando la palabra va delante y sobra."""
        from silux import render

        for crudo in ("Node0_Bank0", "A1_BANK0", "BANK", ""):
            with self.subTest(crudo=crudo):
                self.assertEqual(render.banco_de_memoria(crudo), crudo)

    def test_sin_banco_no_se_inventa(self):
        from silux import render

        self.assertIsNone(render.banco_de_memoria(None))


class TestElMaximoDelProcesador(unittest.TestCase):
    """Un i5-10400 con módulos de 3200: va a 2666 porque es su máximo.

    En la oficina, con permisos, Memoria decía «por debajo de su velocidad» y
    mandaba a activar XMP. No hay perfil que activar: 2666 es lo que Intel
    garantiza para ese procesador (tabla oficial de memoria por generación y
    ficha del i5-10400), y los módulos de 3200 no lo cambian.
    """

    from silux.db import MemoryLimit
    LIMITE = MemoryLimit("i5-10400", 2666, "https://www.intel.com/")

    def test_la_tabla_lo_sabe(self):
        from silux import db

        limite = db.memory_limit("Intel(R) Core(TM) i5-10400 CPU @ 2.90GHz", "DDR4")
        self.assertEqual((limite.model, limite.mts, limite.layout), ("i5-10400", 2666, None))
        # El de portátil con el mismo número es otro chip, con su propia cifra
        # (DDR4-2933 en su ficha de ARK).
        portatil = db.memory_limit("Intel(R) Core(TM) i5-10400H CPU @ 2.60GHz", "DDR4")
        self.assertEqual((portatil.model, portatil.mts), ("i5-10400H", 2933))
        self.assertIsNone(db.memory_limit("Intel(R) Core(TM) i5-10400 CPU @ 2.90GHz", "DDR5"))
        # En AMD hace falta saber los módulos: sin rangos no hay cifra.
        self.assertIsNone(db.memory_limit("AMD Ryzen 7 5800X3D 8-Core Processor", "DDR4"))

    def test_al_maximo_del_procesador_no_se_sugiere_xmp(self):
        from silux import render

        aviso = render.memory_speed_warning([_modulo(3200, 2667), _modulo(3200, 2667)],
                                            self.LIMITE)
        self.assertIn("i5-10400", aviso)
        self.assertIn("2666", aviso)
        self.assertNotIn("XMP", aviso)
        self.assertEqual(render.memory_module_verdict(_modulo(3200, 2667), self.LIMITE),
                         "cpu_max")

    def test_por_debajo_del_maximo_del_procesador_si(self):
        from silux import render

        aviso = render.memory_speed_warning([_modulo(3200, 2133)], self.LIMITE)
        self.assertIn("XMP", aviso)
        self.assertEqual(render.memory_module_verdict(_modulo(3200, 2133), self.LIMITE), "slow")

    def test_sin_saber_el_maximo_sigue_como_antes(self):
        from silux import render

        self.assertIn("XMP", render.memory_speed_warning([_modulo(3200, 2667)]))
        self.assertEqual(render.memory_module_verdict(_modulo(3200, 2667), None), "slow")
        self.assertIsNone(render.memory_module_verdict(_modulo(3200, 3200), None))


class TestElMaximoDelProcesadorEnPantalla(unittest.TestCase):
    """Con el volcado del i5-10400 y los módulos como los da su firmware."""

    @classmethod
    def setUpClass(cls):
        cls.app = qt.app()

    def test_la_pagina_dice_que_es_el_maximo(self):
        import dataclasses
        from silux.i18n import _
        from silux.model import MemoryModule
        from silux.settings import Preferences
        from silux.ui import theme
        from silux.ui.pages.memory import MemoryPage
        from tests.test_equipos import EQUIPOS, foto

        base = foto(EQUIPOS / "i5-10400")[0]
        # Lo que dice `dmidecode -t 17` de esta máquina con permisos: el
        # módulo admite 3200 y la BIOS lo configura a 2667.
        modulos = tuple(MemoryModule(populated=True, locator=f"DIMM {n}", type="DDR4",
                                     size_bytes=8 << 30, speed_mts=3200, configured_mts=2667)
                        for n in (1, 2))
        pagina = MemoryPage(theme.palette_for(self.app, "dark"), Preferences())
        self.addCleanup(pagina.deleteLater)
        pagina.resize(1200, 900)
        pagina.show()
        pagina.apply(dataclasses.replace(base, modules=modulos))
        self.app.processEvents()

        self.assertIn("i5-10400", pagina.avisos.text())
        self.assertNotIn("XMP", pagina.avisos.text())
        chips = [texto for texto, _resaltada in pagina.badges._chips]
        self.assertNotIn(_("memory.chip.underclocked"), chips)
        self.assertIn(_("memory.chip.cpumax"), chips)
        # The speed next to it is the one it runs at: a tester's header read
        # «3200 MT/s · al máximo del procesador» with the memory at 2933.
        self.assertIn("2666 MT/s", chips)
        self.assertNotIn("3200 MT/s", chips)
        ficha = pagina._slot_grids[0]
        funcionando = ficha._values[_("memory.field.running")]
        self.assertNotIn("⚠", funcionando.full_text())
        self.assertIn("i5-10400", funcionando.toolTip())


class TestModulosSinPerfilesRapidos(unittest.TestCase):
    """Los Crucial del i5-10400 no traen XMP: «Perfiles rápidos —» era un
    guion para un dato que no existe (regla 5), y la nota del SPD hablaba de
    «XMP sin activar» en unos módulos que no lo tienen. Visto con permisos
    de verdad en la oficina; el volcado lee el mismo SPD sin ellos."""

    @classmethod
    def setUpClass(cls):
        cls.app = qt.app()

    def _pagina(self):
        from silux.settings import Preferences
        from silux.ui import theme
        from silux.ui.pages.memory import MemoryPage
        from tests.test_equipos import EQUIPOS, foto

        f = foto(EQUIPOS / "i5-10400")[0]
        self.assertTrue(f.spd)
        self.assertFalse([s for s in f.spd if s.overclock_profiles])
        pagina = MemoryPage(theme.palette_for(self.app, "dark"), Preferences())
        self.addCleanup(pagina.deleteLater)
        pagina.resize(1200, 900)
        pagina.show()
        pagina.apply(f)
        self.app.processEvents()
        return pagina

    def test_la_fila_se_esconde_y_se_dice_al_pie(self):
        from silux.i18n import _

        pagina = self._pagina()
        for ficha in pagina._slot_grids:
            self.assertFalse(ficha._values[_("memory.field.profiles")].isVisibleTo(pagina))
        # Una sola vez, en la nota de la tabla de perfiles: ni al pie de las
        # fichas ni repetido en otro sitio de la página.
        self.assertFalse(pagina.spd_missing.isVisibleTo(pagina))
        textos = " ".join(pantalla.textos_de(pagina))
        self.assertEqual(textos.count("no traen perfiles rápidos"), 1)

    def test_ningun_guion_en_las_fichas(self):
        from silux import render

        pagina = self._pagina()
        for ficha in pagina._slot_grids:
            visibles = {n: v.full_text() for n, v in ficha._values.items()
                        if v.isVisibleTo(pagina)}
            self.assertNotIn(render.DASH, visibles.values(), visibles)

    def test_la_nota_no_habla_de_activar_xmp(self):
        from silux.i18n import _

        pagina = self._pagina()
        self.assertEqual(pagina.spd_note.text(), _("memory.spd.note.noxmp"))
        self.assertNotIn("activado", pagina.spd_note.text())


class TestElFabricanteNoCambiaAlDarPermisos(unittest.TestCase):
    """Sin permisos la ficha decía «Crucial» (del SPD) y con permisos
    «Crucial Technology» (de la tabla del firmware): la misma pieza con dos
    nombres según se hubiera metido la contraseña. Visto en la oficina."""

    def test_con_spd_manda_el_del_spd(self):
        import dataclasses
        from silux.i18n import _
        from silux.settings import Preferences
        from silux.ui import theme
        from silux.ui.pages.memory import MemoryPage
        from silux.model import MemoryModule
        from tests.test_equipos import EQUIPOS, foto

        app = qt.app()
        base = foto(EQUIPOS / "i5-10400")[0]
        spd = base.spd[0]
        self.assertEqual(render.maker(spd.manufacturer), "Crucial")
        # Lo que da `dmidecode -t 17` de esta máquina.
        modulo = MemoryModule(populated=True, locator="Controller0-ChannelA", bank="BANK 0",
                              type="DDR4", size_bytes=8 << 30, speed_mts=2667,
                              configured_mts=2667, manufacturer="Crucial Technology", spd=spd)
        pagina = MemoryPage(theme.palette_for(app, "dark"), Preferences())
        self.addCleanup(pagina.deleteLater)
        pagina.apply(dataclasses.replace(base, modules=(modulo,)))
        app.processEvents()
        self.assertEqual(pagina._slot_grids[0]._values[_("memory.field.vendor")].full_text(),
                         "Crucial")


class TestElMaximoDeAmdDependeDeLosModulos(unittest.TestCase):
    """La ficha de AMD da una cifra por disposición: 5800X3D, DDR4-3200 con
    dos módulos de uno o dos rangos, 2933 con cuatro de uno y 2667 con
    cuatro de dos (generado de amd.com por tools/gen_memory_limits.py)."""

    MARCA = "AMD Ryzen 7 5800X3D 8-Core Processor"

    def test_cada_disposicion_su_cifra(self):
        from silux import db

        for rangos, cifra in (((1, 1), 3200), ((2, 2), 3200), ((1, 1, 1, 1), 2933),
                              ((2, 2, 2, 2), 2667)):
            with self.subTest(rangos=rangos):
                limite = db.memory_limit(self.MARCA, "DDR4", rangos)
                self.assertEqual(limite.mts, cifra)
                self.assertTrue(limite.source.startswith("https://www.amd.com/"))

    def test_lo_que_la_ficha_no_nombra_no_tiene_cifra(self):
        from silux import db

        self.assertIsNone(db.memory_limit(self.MARCA, "DDR4", (1, 1, 1)))
        self.assertIsNone(db.memory_limit(self.MARCA, "DDR4", (1, 2)))
        self.assertIsNone(db.memory_limit(self.MARCA, "DDR4", (None, None)))
        self.assertIsNone(db.memory_limit(self.MARCA, "DDR5", (1, 1)))

    def test_la_pagina_lo_dice_con_la_disposicion(self):
        import dataclasses
        from silux.model import MemoryModule
        from silux.settings import Preferences
        from silux.ui import theme
        from silux.ui.pages.memory import MemoryPage
        from tests.test_equipos import EQUIPOS, foto

        app = qt.app()
        base = foto(EQUIPOS / "5800x3d")[0]
        self.assertIn("5800X3D", base.cpu.types[0].brand)
        modulos = tuple(MemoryModule(populated=True, locator=f"DIMM {n}", type="DDR4",
                                     size_bytes=16 << 30, speed_mts=3600, configured_mts=2667,
                                     rank=2) for n in range(4))
        pagina = MemoryPage(theme.palette_for(app, "dark"), Preferences())
        self.addCleanup(pagina.deleteLater)
        pagina.apply(dataclasses.replace(base, modules=modulos))
        app.processEvents()
        self.assertIn("Ryzen 7 5800X3D con 4 módulos de 2 rangos", pagina.avisos.text())
        self.assertNotIn("XMP", pagina.avisos.text())


class TestAntesDeNehalemLaMemoriaEsDelChipset(unittest.TestCase):
    """Decisión del autor: en un Core 2 el controlador de memoria va en el
    chipset de la placa; no se habla del máximo del procesador, y la página
    lo dice. Un Core 2 Duo E8400 es Wolfdale: familia 6, modelo 0x17."""

    def _foto(self, familia, modelo, marca):
        import dataclasses
        from silux.model import MemoryModule
        from tests.test_equipos import EQUIPOS, foto

        base = foto(EQUIPOS / "i5-10400")[0]
        tipo = dataclasses.replace(base.cpu.types[0], brand=marca, disp_family=familia,
                                   disp_model=modelo, codename=None)
        cpu = dataclasses.replace(base.cpu, types=(tipo,))
        modulos = tuple(MemoryModule(populated=True, locator=f"DIMM{n}", type="DDR2",
                                     size_bytes=2 << 30, speed_mts=800, configured_mts=667)
                        for n in range(2))
        return dataclasses.replace(base, cpu=cpu, modules=modulos, spd=())

    def test_la_regla(self):
        from silux import db
        from silux.model import CpuType

        for familia, modelo, chipset in ((6, 0x17, True), (6, 0x0F, True), (15, 0x06, True),
                                         (6, 0x1A, False), (6, 0xA5, False)):
            with self.subTest(familia=familia, modelo=hex(modelo)):
                tipo = CpuType(key="g", label="g", vendor="Intel",
                               disp_family=familia, disp_model=modelo)
                self.assertIs(db.memory_controller_in_chipset(tipo), chipset)
        amd = CpuType(key="g", label="g", vendor="AMD", disp_family=15, disp_model=0x6B)
        self.assertFalse(db.memory_controller_in_chipset(amd))

    def test_la_pagina_lo_dice_y_no_habla_del_procesador(self):
        from silux.i18n import _
        from silux.settings import Preferences
        from silux.ui import theme
        from silux.ui.pages.memory import MemoryPage

        app = qt.app()
        pagina = MemoryPage(theme.palette_for(app, "dark"), Preferences())
        self.addCleanup(pagina.deleteLater)
        pagina.apply(self._foto(6, 0x17, "Intel(R) Core(TM)2 Duo CPU     E8400  @ 3.00GHz"))
        app.processEvents()
        texto = pagina.avisos.text()
        self.assertIn(_("mem.chipset"), texto)
        self.assertNotIn("procesador", texto.replace(_("mem.chipset"), ""))


class TestSinSpdNoSeCulpaALaPlaca(unittest.TestCase):
    """«… salen del chip SPD de cada módulo, y esta placa no deja leerlo» se
    decía siempre que faltaba el SPD, sin mirar el porqué. El proveedor lo
    diagnostica: sin bus o con el bus reservado por el firmware es la placa;
    con el bus y sin driver, el SPD está y se lee cargándolo, con permisos:
    candado, no culpa de la placa."""

    @classmethod
    def setUpClass(cls):
        cls.app = qt.app()

    def _pagina(self, muestra):
        import dataclasses
        from silux.model import MemoryModule
        from silux.settings import Preferences
        from silux.ui import theme
        from silux.ui.pages.memory import MemoryPage

        # Los módulos como los da la tabla del firmware con permisos.
        modulos = tuple(MemoryModule(populated=True, locator=f"DIMM {n}", bank=f"BANK {n}",
                                     type="DDR4", size_bytes=8 << 30, speed_mts=3200,
                                     configured_mts=3200, manufacturer="Kingston", rank=1)
                        for n in (0, 1))
        pagina = MemoryPage(theme.palette_for(self.app, "dark"), Preferences())
        self.addCleanup(pagina.deleteLater)
        pagina.resize(1200, 900)
        pagina.show()
        pagina.apply(dataclasses.replace(muestra, modules=modulos, spd=()))
        self.app.processEvents()
        return pagina

    def test_con_el_bus_reservado_lo_dice_el_diagnostico(self):
        from silux.i18n import _
        from tests.test_equipos import EQUIPOS, foto

        pagina = self._pagina(foto(EQUIPOS / "5800x3d")[0])
        texto = pagina.spd_missing.text()
        # Aquí sí es de la placa, y se dice por qué.
        self.assertIn(_("spd.nobus")[1:40], texto)
        self.assertNotIn("esta placa no deja", texto)

    def test_el_proveedor_distingue_driver_de_placa(self):
        from unittest import mock
        from silux.i18n import _
        from silux.model import Need
        from silux.providers.spd_modules import SpdModules

        proveedor = SpdModules()
        from silux import spd
        for causa, need in ((spd.CAUSE_NO_DRIVER, Need.DRIVER), (spd.CAUSE_NO_BUS, Need.HARDWARE),
                            (spd.CAUSE_NO_SMBUS, Need.HARDWARE)):
            with self.subTest(causa=causa), \
                    mock.patch.object(SpdModules, "available", return_value=False), \
                    mock.patch("silux.spd.unreadable_cause", return_value=causa):
                razon = proveedor.unavailable_reason()
                self.assertIs(razon[1], need)
                self.assertEqual(razon[2], _(spd.CAUSES[causa][0]))


class TestElFabricanteSiempreIgual(unittest.TestCase):
    """Revisión del autor: con el SPD «Crucial», sin él «Crucial
    Technology» (lo que escribe la tabla del firmware). Una marca, un nombre."""

    def test_venga_de_donde_venga(self):
        from silux import render

        for crudo, marca in (("Crucial Technology", "Crucial"), ("Crucial", "Crucial"),
                             ("Micron Technology", "Micron"), ("Kingston", "Kingston"),
                             ("SK Hynix", "SK Hynix"), ("Hynix Semiconductor", "SK Hynix"),
                             ("G Skill Intl", "G.Skill"), ("Samsung", "Samsung")):
            with self.subTest(crudo=crudo):
                self.assertEqual(render.maker(crudo), marca)

    def test_en_la_ficha_sin_spd(self):
        import dataclasses
        from silux.i18n import _
        from silux.model import MemoryModule
        from silux.settings import Preferences
        from silux.ui import theme
        from silux.ui.pages.memory import MemoryPage
        from tests.test_equipos import EQUIPOS, foto

        app = qt.app()
        base = foto(EQUIPOS / "i5-10400")[0]
        modulo = MemoryModule(populated=True, locator="Controller0-ChannelA", type="DDR4",
                              size_bytes=8 << 30, manufacturer="Crucial Technology")
        pagina = MemoryPage(theme.palette_for(app, "dark"), Preferences())
        self.addCleanup(pagina.deleteLater)
        pagina.apply(dataclasses.replace(base, modules=(modulo,), spd=()))
        app.processEvents()
        self.assertEqual(pagina._slot_grids[0]._values[_("memory.field.vendor")].full_text(),
                         "Crucial")


class TestLasFichasSeLlamanIgualConYSinPermisos(unittest.TestCase):
    """Revisión del autor: sin permisos «Módulo 1» y «Módulo 2»; con ellos
    «Canal A» y «Canal B». La misma pieza, dos nombres."""

    def test_en_el_i5_10400(self):
        import dataclasses
        from silux.model import MemoryModule
        from silux.settings import Preferences
        from silux.ui import theme
        from silux.ui.pages.memory import MemoryPage
        from silux.ui.widgets import Card
        from tests.test_equipos import EQUIPOS, foto

        app = qt.app()
        sin = foto(EQUIPOS / "i5-10400")[0]
        # Lo que da `dmidecode -t 17` en esta máquina con permisos.
        modulos = tuple(MemoryModule(populated=puesto, locator=loc, bank=banco, type="DDR4"
                                     if puesto else None, size_bytes=(8 << 30) if puesto else 0,
                                     speed_mts=2667 if puesto else None,
                                     configured_mts=2667 if puesto else None, rank=1)
                        for loc, banco, puesto in (
                            ("Controller0-ChannelA", "BANK 0", True),
                            ("Controller0-ChannelA-DIMM1", "BANK 0", False),
                            ("Controller0-ChannelB", "BANK 1", True),
                            ("Controller0-ChannelB-DIMM1", "BANK 1", False)))
        # El proveedor pega a cada módulo de la tabla su SPD, en orden.
        spd = iter(sin.spd)
        modulos = tuple(dataclasses.replace(m, spd=next(spd)) if m.populated else m
                        for m in modulos)
        con = dataclasses.replace(sin, modules=modulos)

        def nombres(muestra):
            pagina = MemoryPage(theme.palette_for(app, "dark"), Preferences())
            self.addCleanup(pagina.deleteLater)
            pagina.apply(muestra)
            app.processEvents()
            fichas = [c._title_label.text() for c in pagina._slots_host.findChildren(Card)
                      if c._title_label is not None]
            perfiles = [fila[0].full_text() for fila in pagina.timings._cells]
            return fichas, perfiles

        self.assertEqual(nombres(sin), nombres(con))
        self.assertEqual(nombres(con)[0], ["Módulo 1", "Módulo 2"])
        self.assertEqual(nombres(con)[1], ["Módulo 1 · JEDEC", "Módulo 2 · JEDEC"])
