"""El orden de la página de Memoria: los datos primero, lo que falta al final.

Sin permisos, la página era: cabecera, una tarjeta que pide permisos, una
que ofrece medir, y dos avisos. No había un dato hasta el tercer bloque, y
con módulos leídos por SPD la tarjeta de permisos iba delante de ellos.
"""

import unittest

from silux import render
from silux.i18n import _

from tests import pantalla, qt
from tests.test_equipos import EQUIPOS, foto

try:
    from PySide6.QtWidgets import QApplication
except ImportError:                                    # pragma: no cover
    QApplication = None


@unittest.skipIf(QApplication is None, "sin PySide6")
class TestElOrdenDeMemoria(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.app = qt.app()
        cls.fotos = {n: foto(EQUIPOS / n)[0] for n in ("5800x3d", "i5-10400")}

    def _alturas(self, ventana):
        ventana.select_section("Memoria")
        for _vez in range(3):
            self.app.processEvents()
        pagina = ventana.memory_page
        raiz = pagina.widget()

        def alto(widget):
            return widget.mapTo(raiz, widget.rect().topLeft()).y()
        return pagina, alto

    def test_lo_que_pide_permisos_va_despues_de_los_datos(self):
        for equipo, f in self.fotos.items():
            with self.subTest(equipo=equipo), pantalla.Ventana(f) as ventana:
                pagina, alto = self._alturas(ventana)
                self.assertTrue(pagina.elevation.isVisible())
                for bloque in (pagina.title.parentWidget(), pagina._slots_host,
                               pagina.timings_card):
                    if bloque.isVisible():
                        self.assertLess(alto(bloque), alto(pagina.elevation))
                # La cabecera sigue siendo lo primero.
                self.assertEqual(alto(pagina.title.parentWidget()),
                                 pagina.widget().layout().contentsMargins().top())

    def test_en_el_intel_los_modulos_van_justo_debajo_de_la_cabecera(self):
        # Sus módulos se leen por SPD sin permisos: son el primer dato.
        with pantalla.Ventana(self.fotos["i5-10400"]) as ventana:
            pagina, alto = self._alturas(ventana)
            self.assertTrue(self.fotos["i5-10400"].modules or pagina._slot_grids)
            self.assertTrue(pagina._slots_host.isVisible())
            visibles = sorted(
                (alto(w), w) for w in (pagina._slots_host, pagina.timings_card,
                                       pagina.elevation) if w.isVisible())
            self.assertIs(visibles[0][1], pagina._slots_host)

    def test_los_avisos_cierran_la_pagina(self):
        from silux.ui.widgets import Notice

        with pantalla.Ventana(self.fotos["5800x3d"]) as ventana:
            pagina, alto = self._alturas(ventana)
            avisos = [a for a in pagina.findChildren(Notice) if a.isVisible()]
            self.assertTrue(avisos)
            self.assertGreater(min(alto(a) for a in avisos), alto(pagina.elevation))




@unittest.skipIf(QApplication is None, "sin PySide6")
class TestSinSpd(unittest.TestCase):
    """En el 5800X3D la placa no deja leer el SPD: con permisos, cada módulo
    salía con «Chips —», «Perfiles rápidos —» y «Fabricado —», tres guiones
    de datos que solo están en ese chip. Se esconden y se dice al pie."""

    @classmethod
    def setUpClass(cls):
        cls.app = qt.app()

    def _pagina(self, f, ventana):
        ventana.select_section("Memoria")
        for _vez in range(4):
            self.app.processEvents()
        return ventana.memory_page

    def test_con_la_tabla_del_firmware_y_sin_spd(self):
        from tests.test_nombres_de_zocalos import PLACAS, _con_la_tabla

        base = foto(EQUIPOS / "5800x3d")[0]
        f = _con_la_tabla(base, PLACAS["Gigabyte X570 (AM4)"][0], {1, 3})
        self.assertTrue(all(m.spd is None for m in f.modules))
        with pantalla.Ventana(f) as ventana:
            pagina = self._pagina(f, ventana)
            self.assertEqual(len(pagina._slot_grids), 2)
            for rejilla in pagina._slot_grids:
                for clave in ("memory.field.chips", "memory.field.profiles", "memory.field.made"):
                    with self.subTest(campo=clave):
                        self.assertFalse(rejilla._values[_(clave)].isVisible())
                        self.assertFalse(rejilla._names[_(clave)].isVisible())
                # El fabricante sí está en la tabla, y se queda.
                self.assertTrue(rejilla._values[_("memory.field.vendor")].isVisible())
                visibles = [v.full_text() for v in rejilla._values.values() if v.isVisible()]
                self.assertNotIn(render.DASH, visibles)
            self.assertTrue(pagina.spd_missing.isVisible())
            # Una frase, no una lista de nombres de campo.
            # Con el porqué que diagnostica el proveedor: en esta placa el
            # firmware se reserva el bus. No «esta placa no deja», a secas.
            self.assertEqual(
                pagina.spd_missing.text(),
                "Los chips, los perfiles rápidos y la fecha de fabricación salen del "
                "chip SPD de cada módulo, y no se puede leer: el controlador SMBus existe "
                "pero el kernel no lo ha activado: el firmware de la placa se reserva ese bus.")

    def test_si_la_tabla_tampoco_dice_el_fabricante_tambien_se_esconde(self):
        import dataclasses
        from tests.test_nombres_de_zocalos import PLACAS, _con_la_tabla

        base = foto(EQUIPOS / "5800x3d")[0]
        f = _con_la_tabla(base, PLACAS["Gigabyte X570 (AM4)"][0], {1, 3})
        f = dataclasses.replace(f, modules=tuple(
            dataclasses.replace(m, manufacturer=None) for m in f.modules))
        with pantalla.Ventana(f) as ventana:
            pagina = self._pagina(f, ventana)
            self.assertFalse(pagina._slot_grids[0]._values[_("memory.field.vendor")].isVisible())
            self.assertTrue(pagina.spd_missing.text().startswith(
                "El fabricante, los chips, los perfiles rápidos y la fecha de fabricación salen"))

    def test_con_spd_solo_se_esconde_lo_que_esos_modulos_no_traen(self):
        # En el i5-10400 el SPD se lee sin permisos: sus fichas salen de él.
        # Sus Crucial no traen XMP: eso, y solo eso, va al pie.
        f = foto(EQUIPOS / "i5-10400")[0]
        with pantalla.Ventana(f) as ventana:
            pagina = self._pagina(f, ventana)
            self.assertTrue(pagina._slot_grids)
            self.assertEqual(pagina.spd_missing.text(), _("memory.na.noprofiles.all"))
            for rejilla in pagina._slot_grids:
                self.assertTrue(rejilla._values[_("memory.field.chips")].isVisible())
                self.assertTrue(rejilla._values[_("memory.field.made")].isVisible())


if __name__ == "__main__":
    unittest.main()
