"""Una muestra nueva con los mismos campos no mueve nada de la página.

En Gráficos, cada segundo la página parpadeaba y se movía todo: las filas
de las frecuencias del silicio se enseñaban y se volvían a esconder en la
misma muestra, y el área de desplazamiento medía la página en ese instante.
Una vez sí y otra no, la página quedaba 23 píxeles más alta, y con ella
desplazada hacia abajo saltaba entera. En Almacenamiento, cada candado se
quitaba y se volvía a poner. Ninguno cambiaba nada que se leyera: era la
página deshaciendo y rehaciendo su propio estado.

Aquí se monta cada página de cada equipo volcado, se le dan dos muestras
seguidas del mismo volcado —los mismos campos— y se mira, de cada widget a
la vista, su sitio y su tamaño, y si alguno se enseña o se esconde.
"""

import unittest

from tests import pantalla, qt
from tests.per_dump import per_dump
from tests.test_equipos import EQUIPOS

try:
    from PySide6.QtWidgets import QApplication
except ImportError:                                    # pragma: no cover
    QApplication = None


def dos_fotos(carpeta):
    """A dump's third and fourth samples, with the same fields. A dump with
    a second reading has its rates on the second sample and stands still
    from then on, like the others: no counter moves between these two."""
    from silux.collector import Collector
    from tests.test_volcar_equipo import _herramienta

    from tests.interval import fake_clock, next_snapshot

    with _herramienta().mounted(carpeta), fake_clock() as reloj:
        recolector = Collector()
        try:
            recolector.snapshot()
            next_snapshot(recolector, reloj)
            return next_snapshot(recolector, reloj), next_snapshot(recolector, reloj)
        finally:
            recolector.close()


def avanzar(raiz, ocupadas: int, octetos: int) -> None:
    """Lo que pasa en un equipo entre dos muestras: los contadores suben.

    Cada CPU, `ocupadas` milésimas del intervalo trabajando (el resto, en
    reposo), y `octetos` más por cada interfaz y cada disco, en los dos
    sentidos.
    """
    import pathlib
    paquetes = max(1, octetos // 1000)

    raiz = pathlib.Path(raiz)
    estadistica = raiz / "proc" / "stat"
    if estadistica.is_file():
        lineas = []
        for linea in estadistica.read_text().splitlines():
            campos = linea.split()
            if campos and campos[0].startswith("cpu"):
                campos[1] = str(int(campos[1]) + ocupadas)
                campos[4] = str(int(campos[4]) + 1000 - ocupadas)
                linea = " ".join(campos)
            lineas.append(linea)
        estadistica.write_text("\n".join(lineas) + "\n")
    dev = raiz / "proc" / "net" / "dev"
    if dev.is_file():
        lineas = dev.read_text().splitlines()
        for i, linea in enumerate(lineas[2:], start=2):
            nombre, _dos_puntos, resto = linea.partition(":")
            numeros = resto.split()
            numeros[0] = str(int(numeros[0]) + octetos)
            numeros[8] = str(int(numeros[8]) + octetos)
            # The packets with them, as traffic moves them: bytes alone are
            # more per packet than a frame holds.
            numeros[1] = str(int(numeros[1]) + paquetes)
            numeros[9] = str(int(numeros[9]) + paquetes)
            lineas[i] = f"{nombre}: " + " ".join(numeros)
        dev.write_text("\n".join(lineas) + "\n")
    for contador in (*raiz.glob("sys/class/net/*/statistics/rx_bytes"),
                     *raiz.glob("sys/class/net/*/statistics/tx_bytes")):
        contador.write_text(f"{int(contador.read_text()) + octetos}\n")
    for contador in (*raiz.glob("sys/class/net/*/statistics/rx_packets"),
                     *raiz.glob("sys/class/net/*/statistics/tx_packets")):
        contador.write_text(f"{int(contador.read_text()) + paquetes}\n")
    for disco in raiz.glob("sys/block/*/stat"):
        campos = disco.read_text().split()
        if len(campos) >= 7:
            campos[2] = str(int(campos[2]) + octetos // 512)      # sectores leídos
            campos[6] = str(int(campos[6]) + octetos // 512)      # sectores escritos
            disco.write_text(" ".join(campos) + "\n")


def _without_their_second_reading(raiz) -> None:
    """The counters moved here are read from their files, not from the
    second reading the dump recorded a second later: with a dump taken on a
    busy machine (71 % on one) that reading said the opposite of the test."""
    import json
    import pathlib

    grabado = pathlib.Path(raiz) / "grabado.json"
    datos = json.loads(grabado.read_text())
    segunda = datos.get("segunda_lectura")
    if not isinstance(segunda, dict):
        return
    movidos = ("/proc/stat", "/net/dev", "/statistics/rx_", "/statistics/tx_", "/stat")
    datos["segunda_lectura"] = {ruta: texto for ruta, texto in segunda.items()
                                if not ruta.endswith(movidos) and "/statistics/" not in ruta}
    grabado.write_text(json.dumps(datos))


def con_contadores_avanzando(carpeta):
    """Dos muestras de un volcado con los mismos campos y otras cifras.

    Antes de cada una los contadores avanzan (`avanzar`), para que las dos
    tengan sus usos y sus ritmos: un volcado quieto no tiene ninguno, que
    salen de restar dos lecturas. Entre la una y la otra, las CPU pasan del
    5 % al 100 % y la red y los discos, de unos bytes a megas por segundo.
    """
    from silux.collector import Collector
    from tests.test_volcar_equipo import _herramienta

    from tests.interval import fake_clock, next_snapshot

    with _herramienta().mounted(carpeta) as raiz, fake_clock() as reloj:
        # Before the first snapshot, which loads the recording.
        _without_their_second_reading(raiz)
        recolector = Collector()
        try:
            recolector.snapshot()
            avanzar(raiz, ocupadas=50, octetos=1024)
            segunda = next_snapshot(recolector, reloj)
            avanzar(raiz, ocupadas=1000, octetos=50_000_000)
            return segunda, next_snapshot(recolector, reloj)
        finally:
            recolector.close()


def asentar() -> None:
    """Hasta que Qt haya recolocado todo lo que se le pidió."""
    for _vez in range(6):
        QApplication.processEvents()


def _nombre(widget, pagina) -> str:
    partes = []
    while widget is not None and widget is not pagina and len(partes) < 3:
        partes.append(type(widget).__name__ + (f"#{widget.objectName()}"
                                               if widget.objectName() else ""))
        widget = widget.parentWidget()
    return "<".join(partes)


def geometria(pagina) -> dict:
    """De cada widget a la vista: su sitio en la página y su tamaño."""
    import shiboken6
    from PySide6.QtCore import QPoint
    from PySide6.QtWidgets import QWidget

    vistos = {}
    for widget in pagina.findChildren(QWidget):
        if widget.isVisible():
            sitio = widget.mapTo(pagina, QPoint(0, 0))
            vistos[shiboken6.getCppPointer(widget)[0]] = (
                _nombre(widget, pagina),
                (sitio.x(), sitio.y(), widget.width(), widget.height()))
    return vistos


def diferencias(antes: dict, despues: dict) -> list[str]:
    salida = []
    for clave in sorted(set(antes) | set(despues), key=str):
        if clave not in despues:
            salida.append(f"se va {antes[clave][0]} {antes[clave][1]}")
        elif clave not in antes:
            salida.append(f"aparece {despues[clave][0]} {despues[clave][1]}")
        elif antes[clave][1] != despues[clave][1]:
            salida.append(f"se mueve {antes[clave][0]} {antes[clave][1]} → {despues[clave][1]}")
    return salida


class Visibilidad:
    """Los Show y Hide de los widgets de una página mientras dura el bloque.

    Aunque al final quede todo igual, enseñar y volver a esconder en la misma
    muestra recoloca la página entera: es lo que la hacía parpadear.
    """

    def __init__(self, pagina):
        from PySide6.QtCore import QObject

        espia = self

        class _Filtro(QObject):
            def eventFilter(self, objeto, evento):  # noqa: N802
                espia._mirar(objeto, evento)
                return False

        self._pagina = pagina
        self._filtro = _Filtro()
        self.cambios: list[str] = []

    def _mirar(self, objeto, evento) -> None:
        from PySide6.QtCore import QEvent
        from PySide6.QtWidgets import QWidget

        tipo = evento.type()
        if tipo not in (QEvent.Type.Show, QEvent.Type.Hide) or not isinstance(objeto, QWidget):
            return
        if objeto is self._pagina or not self._pagina.isAncestorOf(objeto):
            return
        texto = objeto.text() if hasattr(objeto, "text") and callable(objeto.text) else ""
        self.cambios.append(f"{'Show' if tipo == QEvent.Type.Show else 'Hide'} "
                            f"{_nombre(objeto, self._pagina)} {str(texto)[:30]!r}")

    def __enter__(self):
        QApplication.instance().installEventFilter(self._filtro)
        return self

    def __exit__(self, *_error):
        QApplication.instance().removeEventFilter(self._filtro)


@unittest.skipIf(QApplication is None, "sin PySide6")
class TestNadaSeMueve(unittest.TestCase):

    # Each dump's two snapshots, taken when a test asks for them: split by
    # dump, a test needs one dump's, not nineteen.
    _equal: dict = {}
    _advancing: dict = {}

    @classmethod
    def setUpClass(cls):
        qt.app()

    def _two(self, nombre: str) -> dict:
        if nombre not in self._equal:
            self._equal[nombre] = dos_fotos(EQUIPOS / nombre)
        return {nombre: self._equal[nombre]}

    def _moving(self, nombre: str) -> dict:
        if nombre not in self._advancing:
            self._advancing[nombre] = con_contadores_avanzando(EQUIPOS / nombre)
        return {nombre: self._advancing[nombre]}

    def _sin_moverse(self, nombre: str, fotos: dict, como: str) -> None:
        primera, segunda = fotos[nombre]
        with pantalla.Ventana(primera) as ventana:
            for seccion, pagina in pantalla.recorrer(ventana):
                with self.subTest(equipo=nombre, pagina=seccion, muestras=como):
                    ventana._on_sample(primera)
                    asentar()
                    antes = geometria(pagina)
                    with Visibilidad(pagina) as visibilidad:
                        ventana._on_sample(segunda)
                        asentar()
                    self.assertEqual(visibilidad.cambios, [])
                    self.assertEqual(diferencias(antes, geometria(pagina)), [])

    def _every_page(self, carpeta):
        self._sin_moverse(carpeta.name, self._two(carpeta.name), "iguales")

    def _figures_changing_width(self, carpeta):
        # Una cifra que pasa de «0» a «100», o de «0 B/s» a megas, no mueve
        # su unidad ni nada de al lado: cada ficha reserva lo más ancho que
        # puede decir (`StatTile.reserve`).
        self._sin_moverse(carpeta.name, self._moving(carpeta.name),
                          "con los contadores avanzando")

    def _figures_at_their_extremes(self, carpeta):
        # Lo de arriba depende de lo rápido que vaya la máquina: los ritmos
        # salen de 50 MB divididos por el tiempo real entre dos lecturas. En
        # el CI, con DejaVu, una tarjeta de Inicio se ensanchó 21 px y se
        # repartió la fila entera. Aquí las cifras van a sus extremos a
        # propósito, de «1 B/s» a «1000.0 MB/s» y del 1 % al 100 %.
        import dataclasses

        def con(foto, ritmo, uso):
            red = tuple(dataclasses.replace(i, traffic=dataclasses.replace(
                i.traffic, rx_rate_bps=ritmo, tx_rate_bps=ritmo)) if i.traffic else i
                for i in foto.network)
            discos = tuple(dataclasses.replace(d, io=dataclasses.replace(
                d.io, read_rate_bps=ritmo, write_rate_bps=ritmo)) if d.io else d
                for d in foto.disks)
            return dataclasses.replace(foto, network=red, disks=discos,
                                       cpu=dataclasses.replace(foto.cpu, usage_percent=uso))

        extremos = {nombre: (con(despues, 1.0, 1.0), con(despues, 999_960_000.0, 100.0))
                    for nombre, (_antes, despues) in self._moving(carpeta.name).items()}
        for nombre in extremos:
            self._sin_moverse(nombre, extremos, "con las cifras en sus extremos")

    def _advancing_changes_the_figures(self, carpeta):
        # Si las dos muestras dijeran lo mismo, la prueba de arriba no
        # probaría nada.
        antes, despues = self._moving(carpeta.name)[carpeta.name]
        self.assertLess(antes.cpu.usage_percent, 10.0)
        self.assertGreater(despues.cpu.usage_percent, 99.0)
        self.assertTrue(any(d.io.read_rate_bps for d in despues.disks))
        self.assertTrue(any(i.traffic and i.traffic.rx_rate_bps
                            for i in despues.network))

    def test_la_guarda_ve_una_fila_que_se_enseña_y_se_esconde(self):
        # Si no cazara una página que se deshace y se rehace, no vigilaría
        # nada: una fila de Gráficos que se enseña y se vuelve a esconder en
        # cada muestra, como hacían las del silicio.
        from silux.i18n import _
        from silux.ui.pages.graphics import GpuSection

        # A dump with a graphics card.
        primera, segunda = self._two("5800x3d")["5800x3d"]
        with pantalla.Ventana(primera) as ventana:
            ventana.select_section("nav.graphics")
            asentar()
            pagina = ventana.stack.currentWidget()
            seccion = pagina.findChildren(GpuSection)[0]
            original = seccion._apply_no_aplica

            def con_parpadeo(gpu):
                original(gpu)
                seccion.clocks.set_visible(_("gpu.clock.memory"), False)
                seccion.clocks.set_visible(_("gpu.clock.memory"), True)

            seccion._apply_no_aplica = con_parpadeo
            ventana._on_sample(primera)
            asentar()
            with Visibilidad(pagina) as visibilidad:
                ventana._on_sample(segunda)
                asentar()
        self.assertTrue(visibilidad.cambios)


per_dump(TestNadaSeMueve, "cada_pagina_de_cada_equipo", TestNadaSeMueve._every_page)
per_dump(TestNadaSeMueve, "con_las_cifras_cambiando_de_ancho",
         TestNadaSeMueve._figures_changing_width)
per_dump(TestNadaSeMueve, "con_las_cifras_en_sus_extremos",
         TestNadaSeMueve._figures_at_their_extremes)
per_dump(TestNadaSeMueve, "avanzar_cambia_las_cifras", TestNadaSeMueve._advancing_changes_the_figures)


if __name__ == "__main__":
    unittest.main()
