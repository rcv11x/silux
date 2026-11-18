"""El fondo de las barras de «Ahora mismo» no cambia de largo con las cifras.

La columna de la cifra («4.6 GB de 15.9 GB») es una para todos los renglones
y medía lo que su texto más ancho de ese momento: al pasar de «97 GB/s de
644 GB/s» a «116 GB/s de 644 GB/s», el fondo gris de todas las barras
encogía unos píxeles (en las capturas de casa-18/motores, de x=1195 a 1187).
Ahora cada renglón reserva el ancho de lo más largo que puede llegar a
decir, con cifras tabulares.
"""

import dataclasses
import unittest

from silux import render
from silux.i18n import _
from tests import qt
from tests.test_equipos import EQUIPOS, foto


class TestElFondoFijo(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = qt.app()
        cls.foto = foto(EQUIPOS / "5800x3d")[0]

    def seccion(self):
        from silux.settings import Preferences
        from silux.ui import theme
        from silux.ui.pages.graphics import GraphicsPage
        pagina = GraphicsPage(theme.palette_for(self.app, "dark"), Preferences().normalized())
        self.addCleanup(pagina.deleteLater)
        pagina.resize(1300, 900)
        pagina.show()
        return pagina

    def con(self, usada, vatios, bus):
        gpu = self.foto.gpus[0]
        memoria = dataclasses.replace(gpu.memory, used_bytes=usada)
        gpu = dataclasses.replace(gpu, memory=memoria, power_w=vatios, memory_busy_percent=bus)
        return dataclasses.replace(self.foto, gpus=(gpu,))

    def anchos(self, pagina, foto_):
        pagina.apply(foto_)
        for _vez in range(3):
            self.app.processEvents()
        lista = pagina._sections[0].now
        return {nombre: fila[1].width() for nombre, fila in lista._rows.items()
                if not fila[1].isHidden()}

    def test_las_cifras_cortas_y_las_largas_dejan_el_mismo_fondo(self):
        pagina = self.seccion()
        total = self.foto.gpus[0].memory.total_bytes
        cortas = self.anchos(pagina, self.con(300 * 1024**2, 9.0, 1.0))
        largas = self.anchos(pagina, self.con(int(1023.9 * 1024**2), 339.0, 99.0))
        llena = self.anchos(pagina, self.con(total, 340.0, 100.0))
        self.assertEqual(cortas, largas)
        self.assertEqual(cortas, llena)

    def test_lo_mas_largo_cabe_entero(self):
        """La reserva es de verdad la del texto más largo: «1023.9 MB de
        15.9 GB» no se recorta."""
        pagina = self.seccion()
        self.anchos(pagina, self.con(int(1023.9 * 1024**2), 9.0, 1.0))
        cifra = pagina._sections[0].now._rows[_("gpu.now.vram")][2]
        texto = cifra.text()
        self.assertIn("1023.9 MB", texto)
        self.assertGreaterEqual(cifra.width(), cifra.fontMetrics().horizontalAdvance(texto))

    def test_los_textos_posibles_incluyen_el_cambio_de_unidad(self):
        textos = render.possible_texts(render.size, 16 * 1024**3)
        self.assertIn("1023.9 MB", textos)
        self.assertIn("16 GB", textos)


if __name__ == "__main__":
    unittest.main()
