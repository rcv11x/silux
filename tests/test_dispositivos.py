"""Dispositivos: lo enchufado por USB, el sonido, las cámaras y el Bluetooth.

Los archivos tienen la forma de los de sysfs y `/proc/asound` de un equipo
de verdad (el 5800X3D); los nombres de los aparatos son genéricos a
propósito: el inventario de nadie va al repositorio.
"""

import dataclasses
import random
import unittest
from unittest import mock

from silux import privacidad, render
from silux.i18n import _
from silux.model import BluetoothAdapter, Camera, SoundCard, UsbDevice
from silux.providers.base import Draft
from silux.providers.devices import ConnectedDevices
from tests import pantalla, qt
from tests.arbol import arbol
from tests.test_equipos import EQUIPOS, foto

try:
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication
except ImportError:                                    # pragma: no cover
    QApplication = None

USB = "/sys/bus/usb/devices/"


def _usb(puerto, clase, velocidad, version, producto=None, fabricante=None, interfaces=()):
    archivos = {f"{USB}{puerto}/bDeviceClass": clase + "\n",
                f"{USB}{puerto}/speed": velocidad + "\n",
                f"{USB}{puerto}/version": f" {version}\n",
                f"{USB}{puerto}/idVendor": "1234\n", f"{USB}{puerto}/idProduct": "abcd\n",
                # Está en el equipo, y no se tiene que leer nunca.
                f"{USB}{puerto}/serial": "SERIE-QUE-NO-SE-LEE\n"}
    if producto:
        archivos[f"{USB}{puerto}/product"] = producto + "\n"
    if fabricante:
        archivos[f"{USB}{puerto}/manufacturer"] = fabricante + "\n"
    for n, (clase_i, protocolo) in enumerate(interfaces):
        archivos[f"{USB}{puerto}/{puerto}:1.{n}/bInterfaceClass"] = clase_i + "\n"
        archivos[f"{USB}{puerto}/{puerto}:1.{n}/bInterfaceProtocol"] = protocolo + "\n"
    return archivos


EQUIPO = {
    **_usb("1-3", "09", "480", "2.00", "USB2.0 Hub"),
    **_usb("1-3.4", "00", "12", "1.10", "Teclado", "Acme", [("03", "01"), ("03", "00")]),
    **_usb("1-5", "ef", "12", "2.00", "Microfono", "Acme", [("01", "00"), ("01", "00"), ("03", "00")]),
    **_usb("5-4", "09", "480", "2.10", "USB2.1 Hub", "Hubs SA"),
    **_usb("5-4.1", "09", "480", "2.10", "USB2.1 Hub", "Hubs SA"),
    **_usb("5-4.1.4", "ef", "480", "2.00", "Camara", "Acme", [("0e", "00"), ("0e", "00"), ("01", "00")]),
    **_usb("5-4.2", "00", "12", "2.00", "Llave", "Acme", [("03", "01"), ("03", "00"), ("0b", "00")]),
    **_usb("5-4.4", "00", "480", "2.00", "Receptor", "Acme", [("03", "01"), ("03", "02")]),
    **_usb("6-2", "00", "480", "3.20", "Disco externo", "Acme", [("08", "50")]),
    f"{USB}usb1/bDeviceClass": "09\n", f"{USB}usb1/speed": "480\n",
    "/proc/asound/cards": (
        " 0 [HDMI           ]: HDA-Intel - HDA ATI HDMI\n"
        "                      HDA ATI HDMI at 0xfcda0000 irq 140\n"
        " 1 [Generic        ]: HDA-Intel - HD-Audio Generic\n"
        "                      HD-Audio Generic at 0xfcc00000 irq 142\n"
        " 2 [Pro            ]: USB-Audio - Microfono\n"
        "                      Acme Microfono at usb-0000:0e:00.3-3, high speed\n"),
    "/proc/asound/card0/codec#0": "Codec: ATI R6xx HDMI\nAddress: 0\n",
    "/proc/asound/card1/codec#0": "Codec: Realtek ALCS1200A\nAddress: 0\n",
    "/sys/class/video4linux/video0/name": "Camara virtual\n",
}


def _leer(archivos=EQUIPO):
    with arbol(archivos):
        draft = Draft()
        ConnectedDevices().collect(draft)
        return draft


class TestElProveedor(unittest.TestCase):

    def test_cada_cosa_dice_lo_que_es_y_nunca_segun_la_interfaz(self):
        clases = {u.port: u.kind for u in _leer().usb_devices}
        self.assertEqual(clases, {
            "1-3": "hub", "1-3.4": "keyboard", "1-5": "audio", "5-4": "hub", "5-4.1": "hub",
            "5-4.1.4": "video", "5-4.2": "smartcard", "5-4.4": "keyboard_mouse",
            "6-2": "storage"})

    def test_las_raices_y_las_interfaces_no_son_dispositivos(self):
        puertos = [u.port for u in _leer().usb_devices]
        self.assertNotIn("usb1", puertos)
        self.assertFalse([p for p in puertos if ":" in p])

    def test_de_quien_cuelga_cada_uno(self):
        por_puerto = {u.port: u for u in _leer().usb_devices}
        self.assertIsNone(por_puerto["5-4"].parent)
        self.assertEqual(por_puerto["5-4.1"].parent, "5-4")
        self.assertEqual(por_puerto["5-4.1.4"].parent, "5-4.1")

    def test_solo_avisa_de_lo_rapido_que_negocia_despacio(self):
        lentos = [u.port for u in _leer().usb_devices if u.slower_than_capable]
        # El disco es USB 3.2 y va a 480; el teclado USB 1.1 a 12 va a lo suyo.
        self.assertEqual(lentos, ["6-2"])

    def test_el_numero_de_serie_no_llega_a_ninguna_parte(self):
        draft = _leer()
        self.assertNotIn("SERIE", repr(draft.usb_devices))
        self.assertFalse([c for c in dataclasses.fields(UsbDevice) if "serial" in c.name])

    def test_el_sonido_con_nombres_que_se_entienden(self):
        tarjetas = _leer().sound_cards
        self.assertEqual(tarjetas, [SoundCard(kind="hdmi", codec="ATI R6xx HDMI"),
                                    SoundCard(kind="board", codec="Realtek ALCS1200A"),
                                    SoundCard(name="Microfono", kind="usb")])
        self.assertEqual([render.sound_card(t) for t in tarjetas],
                         ["HDMI de la gráfica", "Placa base · Realtek ALCS1200A", "Microfono"])

    def test_una_camara_que_no_cuelga_de_nada_es_virtual(self):
        self.assertEqual(_leer().cameras, [Camera(name="Camara virtual", nodes=1, virtual=True)])

    def test_sin_nada_enchufado_no_revienta(self):
        draft = _leer({"/proc/uptime": "1 1\n"})
        self.assertEqual((draft.usb_devices, draft.sound_cards, draft.cameras, draft.bluetooth),
                         ([], [], [], []))


class TestCadaMuestreoSoloMiraLoQueCambia(unittest.TestCase):
    """El proveedor corre en cada muestreo para ver lo que se enchufa al
    momento. Leer otra vez los nombres de cada USB y los códecs de sonido
    (`codec#N` es el volcado entero del códec, que el kernel genera al
    abrirlo) era el 10 % de lo que gastaba silux con la ventana escondida."""

    def abiertos(self, proveedor, raiz):
        import builtins
        rutas = []
        original = builtins.open

        def abrir(ruta, *args, **kwargs):
            rutas.append(str(ruta)[len(str(raiz)):])
            return original(ruta, *args, **kwargs)

        with mock.patch.object(builtins, "open", abrir):
            draft = Draft()
            proveedor.collect(draft)
        return draft, rutas

    def test_sin_cambios_no_se_vuelve_a_leer_nada_de_cada_aparato(self):
        with arbol(EQUIPO) as raiz:
            proveedor = ConnectedDevices()
            primera, _rutas = self.abiertos(proveedor, raiz)
            segunda, rutas = self.abiertos(proveedor, raiz)
        self.assertEqual(primera.usb_devices, segunda.usb_devices)
        self.assertEqual(primera.sound_cards, segunda.sound_cards)
        self.assertEqual([r for r in rutas if "codec#" in r or r.endswith("/product")], [])

    def test_lo_que_se_enchufa_y_se_quita_se_ve_igual(self):
        import shutil
        with arbol(EQUIPO) as raiz:
            proveedor = ConnectedDevices()
            proveedor.collect(Draft())
            shutil.rmtree(raiz / "sys/bus/usb/devices/6-2")
            for camino, texto in _usb("6-3", "00", "480", "2.00", "Pincho", "Acme",
                                      [("08", "50")]).items():
                destino = raiz / camino.lstrip("/")
                destino.parent.mkdir(parents=True, exist_ok=True)
                destino.write_text(texto)
            (raiz / "proc/asound/cards").write_text(EQUIPO["/proc/asound/cards"].split(" 2 [")[0])
            draft = Draft()
            proveedor.collect(draft)
        puertos = [u.port for u in draft.usb_devices]
        self.assertNotIn("6-2", puertos)
        self.assertIn("6-3", puertos)
        self.assertEqual(len(draft.sound_cards), 2)


class TestLosNombres(unittest.TestCase):

    def test_la_velocidad_es_la_negociada_y_no_una_version(self):
        self.assertEqual(render.usb_speed(12.0), "Velocidad completa · 12 Mb/s")
        self.assertEqual(render.usb_speed(480.0), "Alta velocidad · 480 Mb/s")
        self.assertEqual(render.usb_speed(5000.0), "SuperSpeed · 5 Gb/s")
        self.assertEqual(render.usb_speed(1.5), "Baja velocidad · 1.5 Mb/s")
        self.assertNotIn("USB 1.1", render.usb_speed(12.0))
        self.assertEqual(render.usb_speed(None), render.DASH)

    def test_anonima_la_foto_dice_la_clase_y_no_la_marca(self):
        draft = _leer()
        base = foto(EQUIPOS / "5800x3d")[0]
        f = dataclasses.replace(
            base, usb_devices=tuple(draft.usb_devices), sound_cards=tuple(draft.sound_cards),
            cameras=tuple(draft.cameras),
            bluetooth=(BluetoothAdapter(name="hci0", product="Adaptador Acme", bus="usb",
                                        powered=True),))
        anonima = privacidad.anonimizar(f)
        self.assertEqual({(u.vendor, u.product, u.usb_id) for u in anonima.usb_devices},
                         {(None, None, None)})
        self.assertEqual([u.kind for u in anonima.usb_devices],
                         [u.kind for u in f.usb_devices])
        self.assertEqual([u.speed_mbps for u in anonima.usb_devices],
                         [u.speed_mbps for u in f.usb_devices])
        self.assertNotIn("Acme", repr((anonima.usb_devices, anonima.sound_cards,
                                       anonima.cameras, anonima.bluetooth)))
        self.assertEqual(render.usb_name(anonima.usb_devices[1]), "Teclado")


@unittest.skipIf(QApplication is None, "sin PySide6")
class TestEnLaPagina(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.app = qt.app()
        draft = _leer()
        cls.base = foto(EQUIPOS / "5800x3d")[0]
        cls.foto = dataclasses.replace(
            cls.base, usb_devices=tuple(draft.usb_devices),
            sound_cards=tuple(draft.sound_cards), cameras=tuple(draft.cameras),
            bluetooth=(BluetoothAdapter(name="hci0", product="Adaptador Acme", bus="usb",
                                        powered=True),))

    def _pagina(self, ventana):
        self.assertTrue(ventana.select_section("Dispositivos"))
        for _vez in range(4):
            self.app.processEvents()
        return ventana.devices_page

    @staticmethod
    def _arbol(pagina) -> dict:
        """Nombre → (nombre del padre, columnas)."""
        salida, pendientes = {}, [(pagina.usb.topLevelItem(i), None)
                                  for i in range(pagina.usb.topLevelItemCount())]
        while pendientes:
            item, padre = pendientes.pop(0)
            salida[item.text(0) + "@" + str(len(salida))] = (
                padre, [item.text(c) for c in range(4)], item.toolTip(0))
            pendientes += [(item.child(i), item.text(0)) for i in range(item.childCount())]
        return salida

    def test_los_concentradores_no_cuentan(self):
        with pantalla.Ventana(self.foto) as ventana:
            pagina = self._pagina(ventana)
            self.assertEqual(pagina.title.text(), "6 dispositivos USB")
            self.assertEqual(sum(1 for u in self.foto.usb_devices if u.is_hub), 3)
            self.assertIn("3 concentradores", [c for c in pantalla.textos_de(pagina)])

    def test_cada_cosa_cuelga_de_su_concentrador(self):
        with pantalla.Ventana(self.foto) as ventana:
            filas = {clave.split("@")[0]: valor
                     for clave, valor in self._arbol(self._pagina(ventana)).items()}
            self.assertEqual(filas["Teclado"][0], "USB2.0 Hub")
            self.assertEqual(filas["Camara"][0], "USB2.1 Hub")
            self.assertIsNone(filas["Microfono"][0])
            self.assertEqual(filas["Camara"][1], ["Camara", "Acme", "video",
                                                  "Alta velocidad · 480 Mb/s"])
            self.assertEqual(filas["Receptor"][1][2], "teclado y ratón")
            # El puerto y el identificador, al pasar el ratón.
            self.assertIn("5-4.1.4", filas["Camara"][2])

    def test_el_aviso_solo_donde_algo_rapido_va_despacio(self):
        with pantalla.Ventana(self.foto) as ventana:
            pagina = self._pagina(ventana)
            filas = {clave.split("@")[0]: valor for clave, valor in self._arbol(pagina).items()}
            con_aviso = [n for n, (_p, columnas, _t) in filas.items() if "⚠" in columnas[3]]
            self.assertEqual(con_aviso, ["Disco externo"])
            self.assertIn("3.20", filas["Disco externo"][2])
            self.assertIn(_("dev.chip.slow").format(n=1), pantalla.textos_de(pagina))

    def test_sonido_camaras_y_bluetooth(self):
        with pantalla.Ventana(self.foto) as ventana:
            pagina = self._pagina(ventana)
            self.assertEqual([[c.full_text() for c in fila] for fila in pagina.sound._cells],
                             [["HDMI de la gráfica", "en la gráfica"],
                              ["Placa base · Realtek ALCS1200A", "en la placa"],
                              ["Microfono", "por USB"]])
            self.assertEqual([[c.full_text() for c in fila] for fila in pagina.cameras._cells],
                             [["Camara virtual", "virtual"]])
            self.assertEqual(pagina.bluetooth._values["hci0"].full_text(),
                             "Adaptador Acme · por USB · encendido")

    def test_un_usb_que_se_quita_con_la_pagina_abierta(self):
        with pantalla.Ventana(self.foto) as ventana:
            pagina = self._pagina(ventana)
            sin_disco = dataclasses.replace(self.foto, usb_devices=tuple(
                u for u in self.foto.usb_devices if u.port != "6-2"), cameras=(), bluetooth=())
            ventana._on_sample(sin_disco)
            for _vez in range(4):
                self.app.processEvents()
            nombres = [clave.split("@")[0] for clave in self._arbol(pagina)]
            self.assertNotIn("Disco externo", nombres)
            self.assertEqual(pagina.title.text(), "5 dispositivos USB")
            self.assertFalse(pagina.cameras.isVisible())
            self.assertTrue(pagina.cameras_none.isVisible())
            self.assertTrue(pagina.bluetooth_none.isVisible())
            # Y vuelve.
            ventana._on_sample(self.foto)
            for _vez in range(4):
                self.app.processEvents()
            self.assertIn("Disco externo", [c.split("@")[0] for c in self._arbol(pagina)])
            self.assertTrue(pagina.cameras.isVisible())

    @staticmethod
    def _tree_state(page) -> tuple:
        """Each row in order: depth, texts, tooltip, colours and whether it is open."""
        rows = []

        def walk(item, depth):
            rows.append((depth, [item.text(c) for c in range(4)], item.toolTip(0),
                         [item.foreground(c).color().name() for c in range(4)],
                         item.isExpanded() if item.childCount() else None))
            for i in range(item.childCount()):
                walk(item.child(i), depth + 1)

        for i in range(page.usb.topLevelItemCount()):
            walk(page.usb.topLevelItem(i), 0)
        return rows, [page.usb.isColumnHidden(c) for c in range(4)]

    @staticmethod
    def _rows_by_tooltip(page) -> dict:
        everything = Qt.MatchFlag.MatchContains | Qt.MatchFlag.MatchRecursive
        return {item.toolTip(0): item for item in page.usb.findItems("", everything)}

    def test_rows_still_plugged_in_are_kept(self):
        """Rule 6: the tree updates its rows; it does not empty and rebuild itself."""
        with pantalla.Ventana(self.foto) as window:
            page = self._pagina(window)
            before = self._rows_by_tooltip(page)
            window._on_sample(dataclasses.replace(self.foto, usb_devices=tuple(
                u for u in self.foto.usb_devices if u.port != "6-2")))
            after = self._rows_by_tooltip(page)
            self.assertEqual(len(after), len(before) - 1)
            for tooltip, item in after.items():
                self.assertIs(item, before[tooltip])

    def test_plugging_and_unplugging_looks_like_a_fresh_page(self):
        """Rule 9 for the USB tree: plugging, unplugging and swapping what is
        on a port leaves the open page as if it had been built with that photo."""
        from silux.settings import Preferences
        from silux.ui import theme
        from silux.ui.pages.devices import DevicesPage

        palette = theme.palette_for(self.app, "dark")
        page = DevicesPage(palette, Preferences().normalized())
        self.addCleanup(page.deleteLater)
        page.apply(self.foto)
        devices = self.foto.usb_devices
        leaves = [u for u in devices if not u.is_hub]
        rng = random.Random(7)
        for step in range(40):
            gone = {u.port for u in devices if rng.random() < 0.3}
            left = [u for u in devices
                    if not any(u.port == g or u.port.startswith(g + ".") for g in gone)]
            # Another device on the same port: unplug one thing, plug another.
            swappable = [n for n, u in enumerate(left) if not u.is_hub]
            if swappable and rng.random() < 0.5:
                n = rng.choice(swappable)
                left[n] = dataclasses.replace(rng.choice(leaves), port=left[n].port)
            photo = dataclasses.replace(self.foto, usb_devices=tuple(left))
            page.apply(photo)
            fresh = DevicesPage(palette, Preferences().normalized())
            fresh.apply(photo)
            self.assertEqual(self._tree_state(page), self._tree_state(fresh), f"step {step}")
            fresh.deleteLater()

    def test_el_icono_de_la_barra_es_el_suyo(self):
        from silux.ui import icons

        self.assertIn("nav.devices", icons.NAV)
        self.assertNotEqual(icons.NAV["nav.devices"], icons.NAV["nav.board"])


if __name__ == "__main__":
    unittest.main()
