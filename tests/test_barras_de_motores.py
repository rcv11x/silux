"""Una integrada tiene en «Ahora mismo» una barra por motor.

Con el volcado del i5-10400 (UHD 630, i915, sin permisos): los motores salen
de `engine/` en el nodo DRM, que no pide nada, y su uso del PMU del kernel,
que sí. Sin permisos, cada barra con su candado; con permisos, su cifra. La
RX 9070 XT no cambia: no es integrada.
"""

import dataclasses
import unittest

from silux.i18n import _
from tests import qt
from tests.test_equipos import EQUIPOS, foto


class TestLasBarras(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = qt.app()
        cls.fotos = {n: foto(EQUIPOS / n)[0] for n in ("5800x3d", "i5-10400")}

    def seccion(self, snapshot):
        from silux.settings import Preferences
        from silux.ui import theme
        from silux.ui.pages.graphics import GraphicsPage
        pagina = GraphicsPage(theme.palette_for(self.app, "dark"), Preferences().normalized())
        self.addCleanup(pagina.deleteLater)
        pagina.resize(1200, 900)
        pagina.show()
        pagina.apply(snapshot)
        self.app.processEvents()
        return pagina._sections[0]

    @staticmethod
    def nombre(clave):
        texto = _(clave)
        return texto[:1].upper() + texto[1:]

    def test_sin_permisos_cada_motor_con_su_candado(self):
        seccion = self.seccion(self.fotos["i5-10400"])
        self.assertTrue(seccion.now_card.isVisible())
        for clave in ("engine.render", "engine.video", "engine.videoenhance", "engine.copy"):
            with self.subTest(clave):
                self.assertTrue(seccion.now.is_locked(self.nombre(clave)))

    def test_con_permisos_su_cifra(self):
        # Lo que el ayudante devuelve con permisos: el uso de cada motor del PMU.
        sin = self.fotos["i5-10400"]
        gpu = sin.gpus[0]
        motores = tuple(dataclasses.replace(m, busy_percent=12.0 if m.name == "rcs0" else 0.0)
                        for m in gpu.engines)
        con = dataclasses.replace(sin, gpus=(dataclasses.replace(gpu, engines=motores),),
                                  notes=tuple(n for n in sin.notes if not n.path.startswith("gpus.0")))
        seccion = self.seccion(con)
        render = self.nombre("engine.render")
        self.assertFalse(seccion.now.is_locked(render))
        self.assertEqual(seccion.now.text_of(render), "12 %")
        self.assertEqual(seccion.now.text_of(self.nombre("engine.copy")), "0 %")

    def test_una_dedicada_no_las_tiene(self):
        seccion = self.seccion(self.fotos["5800x3d"])
        self.assertFalse(seccion.now.has(self.nombre("engine.render")))


if __name__ == "__main__":
    unittest.main()
