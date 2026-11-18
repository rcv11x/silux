"""La interfaz responde al momento: la página abierta se pone al día sola.

En Memoria, al dar permisos desde la propia página, la cabecera pasaba a
«doble canal · DDR4» y salían los zócalos libres, pero las tarjetas de los
módulos no aparecían hasta cambiar de página y volver. Lo que cambia —unos
permisos, un disco que se conecta, un dato que aparece o desaparece— se
tiene que ver en la página abierta sin salir de ella.

La comprobación es general y no sabe nada de cada página: una página abierta
con la foto «sin permisos» que recibe la foto «con permisos» tiene que
quedar igual que la misma página montada directamente con la segunda. Y al
revés, si los permisos se pierden. Se compara lo que se ve: los textos, las
tarjetas, los candados y las filas, en las trece secciones y con cada
volcado.

La foto «con permisos» se fabrica con lo que devuelve el ayudante: la tabla
de memoria del firmware leída con su mismo código, el diagnóstico de cada
disco y los contadores de la gráfica. No se piden permisos de verdad.
"""

import dataclasses
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from silux.model import DiskHealth, Need
from silux.settings import Preferences
from tests import qt
from tests.test_equipos import EQUIPOS, foto, volcados
from tests.test_nombres_de_zocalos import PLACAS, _con_la_tabla

try:
    from PySide6.QtWidgets import (QAbstractButton, QApplication, QLabel, QTreeWidget,
                                   QTreeWidgetItemIterator)
except ImportError:                                    # pragma: no cover
    QApplication = None


def con_permisos(f):
    """La misma foto, como queda cuando el ayudante contesta."""
    cuatro = len(f.cpu.types[0].features) and "5800" in (f.cpu.types[0].brand or "")
    zocalos = PLACAS["Gigabyte X570 (AM4)" if cuatro else "MSI, dos zócalos"][0]
    f = _con_la_tabla(f, zocalos, {1, 3} if cuatro else {0, 1})
    discos = tuple(dataclasses.replace(
        d, temp_c=d.temp_c if d.temp_c is not None else 31.0,
        health=DiskHealth(power_on_hours=1200 + i, written_bytes=(i + 1) << 40,
                          percentage_used=None if d.rotational else 3))
        for i, d in enumerate(f.disks))
    graficas = tuple(dataclasses.replace(g, busy_percent=3.0, video_busy_percent=0.0,
                                         power_w=g.power_w if g.power_w is not None else 1.5)
                     if g.busy_percent is None else g for g in f.gpus)
    return dataclasses.replace(
        f, disks=discos, gpus=graficas,
        notes=tuple(n for n in f.notes if n.need is not Need.ROOT))


def con_menos(f):
    """La misma foto con cosas desenchufadas: un disco, las interfaces de
    red que no dan servicio, un monitor, y los sensores de lo que se fue."""
    from silux.ui.pages.network import main_interface

    principal, _todas = main_interface(f.network)
    discos = f.disks[:-1] if len(f.disks) > 1 else f.disks
    idos = {d.name for d in f.disks} - {d.name for d in discos}
    red = tuple(i for i in f.network if i is principal)
    graficas = tuple(dataclasses.replace(g, displays=g.displays[:1]) for g in f.gpus)
    quedan = {i.name for i in red}
    sensores = tuple(s for s in f.sensors
                     if not (s.key.startswith("net/") and s.key.split("/")[1] not in quedan)
                     and not any(nombre in s.key for nombre in idos))
    particiones = tuple(p for p in f.partitions
                        if not any(p.device.startswith(nombre) for nombre in idos)) \
        if hasattr(f, "partitions") else None
    cambios = dict(disks=discos, network=red, gpus=graficas, sensors=sensores,
                   usb_devices=f.usb_devices[:-1], cameras=f.cameras[:-1],
                   sound_cards=f.sound_cards[:-1], bluetooth=(),
                   pci_devices=f.pci_devices[:-1])
    if particiones is not None:
        cambios["partitions"] = particiones
    return dataclasses.replace(f, **cambios)


def _asentar(app, veces=5):
    for _vez in range(veces):
        app.processEvents()


def retrato(ventana) -> list[str]:
    """Lo que se ve en la página abierta, sin importar en qué orden se creó."""
    from silux.ui.widgets import Card, ElidingLabel, LockMark

    pagina = ventana.stack.currentWidget()
    visto = []
    for etiqueta in pagina.findChildren(QLabel):
        if etiqueta.isVisibleTo(ventana):
            texto = (etiqueta.full_text() if isinstance(etiqueta, ElidingLabel)
                     else etiqueta.text())
            if texto.strip():
                visto.append(f"texto: {texto}")
    for boton in pagina.findChildren(QAbstractButton):
        if boton.isVisibleTo(ventana) and boton.text().strip():
            visto.append(f"botón: {boton.text()}")
    visto += [f"tarjeta: {c._title_label.text() if c._title_label is not None else ''}"
              for c in pagina.findChildren(Card) if c.isVisibleTo(ventana)]
    visto += ["candado" for c in pagina.findChildren(LockMark) if c.isVisibleTo(ventana)]
    for arbol in pagina.findChildren(QTreeWidget):
        fila = QTreeWidgetItemIterator(arbol)
        while fila.value() is not None:
            if not fila.value().isHidden():
                visto.append(f"fila: {fila.value().text(0)}")
            fila += 1
    return sorted(visto)


@unittest.skipIf(QApplication is None, "sin PySide6")
class TestLaPaginaAbiertaSePoneAlDia(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        from silux.ui import theme

        cls.app = qt.app()
        prefs = Preferences(window_width=1300, window_height=900).normalized()
        theme.apply(cls.app, prefs.theme, prefs.density, prefs.font_scale)
        cls.prefs = prefs

    def _ventana(self):
        from silux.ui.app import MainWindow

        ventana = MainWindow(self.prefs)
        self.addCleanup(ventana.close)
        ventana.resize(1300, 900)
        ventana.show()
        return ventana

    def _poner(self, ventana, f):
        for _vuelta in range(2):
            ventana._on_sample(f)
            _asentar(self.app)

    def _de_golpe(self, f) -> dict:
        """Cada sección, montada directamente con esa foto."""
        ventana = self._ventana()
        self._poner(ventana, f)
        retratos = {}
        for fila in range(ventana.nav.count()):
            ventana.nav.setCurrentRow(fila)
            _asentar(self.app)
            self._poner(ventana, f)
            retratos[ventana.nav.item(fila).text()] = retrato(ventana)
        return retratos

    def _con_la_pagina_abierta(self, antes, despues) -> dict:
        """Cada sección, abierta con una foto y recibiendo la otra."""
        ventana = self._ventana()
        retratos = {}
        for fila in range(ventana.nav.count()):
            self._poner(ventana, antes)
            ventana.nav.setCurrentRow(fila)
            _asentar(self.app)
            self._poner(ventana, antes)
            self._poner(ventana, despues)
            retratos[ventana.nav.item(fila).text()] = retrato(ventana)
        return retratos

    def _comparar(self, sentido, antes, despues, equipo):
        directo = self._de_golpe(despues)
        abierto = self._con_la_pagina_abierta(antes, despues)
        self.assertEqual(sorted(directo), sorted(abierto))
        for seccion in directo:
            with self.subTest(equipo=equipo, sentido=sentido, seccion=seccion):
                falta = [t for t in directo[seccion] if t not in abierto[seccion]]
                sobra = [t for t in abierto[seccion] if t not in directo[seccion]]
                self.assertEqual((falta, sobra), ([], []),
                                 f"sin salir de la página falta {falta[:8]} y sobra {sobra[:8]}")
                self.assertEqual(directo[seccion], abierto[seccion])

    def test_la_foto_con_permisos_cambia_algo(self):
        for carpeta in volcados():
            sin = foto(carpeta)[0]
            con = con_permisos(sin)
            self.assertTrue(any(m.populated for m in con.modules))
            self.assertNotEqual(sin.modules, con.modules)
            self.assertIsNone(con.permission_note("modules"))

    def test_al_dar_los_permisos(self):
        for carpeta in volcados():
            sin = foto(carpeta)[0]
            self._comparar("se dan", sin, con_permisos(sin), carpeta.name)

    def test_al_desenchufar_y_al_volver_a_enchufar(self):
        """Un disco USB que se quita, una interfaz que se va, un monitor
        que se apaga: sus filas y sus tarjetas se van con ellos, y vuelven."""
        for carpeta in volcados():
            todo = foto(carpeta)[0]
            menos = con_menos(todo)
            self.assertNotEqual(todo, menos)
            self._comparar("se quita", todo, menos, carpeta.name)
            self._comparar("se pone", menos, todo, carpeta.name)

    def test_y_al_perderlos(self):
        for carpeta in volcados():
            sin = foto(carpeta)[0]
            self._comparar("se pierden", con_permisos(sin), sin, carpeta.name)


if __name__ == "__main__":
    unittest.main()
