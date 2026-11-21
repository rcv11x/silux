"""Cada gráfica tiene en «Ahora mismo» una barra por motor que deja medir.

Lo que da cada driver está en docs/motores-de-graficas.md:

- Intel (el volcado del i5-10400, UHD 630, i915, sin permisos): los motores
  salen de `engine/` en el nodo DRM, que no pide nada, y su uso del PMU del
  kernel, que sí. Sin permisos, cada barra con su candado; con permisos, su
  cifra.
- AMD (el del 5800X3D, RX 9070 XT): «Render / 3D» y una sola de video,
  porque codificar y decodificar van por el mismo motor y con una cifra.
- NVIDIA: render, decodificar y codificar, que NVML mide aparte.

Lo que el driver no publica no tiene barra y se nombra al pie.
"""

import ctypes
import dataclasses
import unittest
from unittest import mock

from silux import nvml, render
from silux.i18n import _
from tests import qt
from tests.test_equipos import EQUIPOS, foto
from tests.test_nvidia import UNA_4070, recolectar


def nombre(clave):
    from silux.ui.pages.graphics import BARRAS_DE_MOTOR
    return _(BARRAS_DE_MOTOR[clave])


class _Pagina:
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


class TestIntel(_Pagina, unittest.TestCase):
    def test_sin_permisos_cada_motor_con_su_candado(self):
        seccion = self.seccion(self.fotos["i5-10400"])
        self.assertTrue(seccion.now_card.isVisible())
        for clave in ("engine.render", "engine.video", "engine.videoenhance", "engine.copy"):
            with self.subTest(clave):
                self.assertTrue(seccion.now.is_locked(nombre(clave)))
        self.assertFalse(seccion.now_pie.isVisible(), "con candado no es que falte")

    def test_con_permisos_su_cifra(self):
        # Lo que el ayudante devuelve con permisos: el uso de cada motor del PMU.
        sin = self.fotos["i5-10400"]
        gpu = sin.gpus[0]
        motores = tuple(dataclasses.replace(m, busy_percent=12.0 if m.name == "rcs0" else 0.0)
                        for m in gpu.engines)
        con = dataclasses.replace(sin, gpus=(dataclasses.replace(gpu, engines=motores),),
                                  notes=tuple(n for n in sin.notes if not n.path.startswith("gpus.0")))
        seccion = self.seccion(con)
        self.assertFalse(seccion.now.is_locked(nombre("engine.render")))
        self.assertEqual(seccion.now.text_of(nombre("engine.render")), "12 %")
        self.assertEqual(seccion.now.text_of(nombre("engine.copy")), "0 %")


    def test_con_xe_no_se_dice_que_no_lo_publique(self):
        """xe publica el uso con un PMU que silux todavía no lee: no hay
        barras, y el pie no puede decir que la gráfica no lo da."""
        gpu = dataclasses.replace(self.fotos["i5-10400"].gpus[0], driver="xe", engines=())
        self.assertEqual(render.engine_levels(gpu), [])
        self.assertEqual(render.engine_gaps(gpu), [])


class TestAmd(_Pagina, unittest.TestCase):
    def test_la_rx_9070_xt_tiene_render_y_una_de_video(self):
        foto_amd = self.fotos["5800x3d"]
        gpu = foto_amd.gpus[0]
        seccion = self.seccion(foto_amd)
        self.assertEqual(seccion.now.text_of(nombre("engine.render")),
                         f"{gpu.busy_percent:.0f} %")
        self.assertEqual(seccion.now.text_of(nombre("engine.video")),
                         f"{gpu.video_busy_percent:.0f} %")
        for clave in ("engine.decode", "engine.encode"):
            self.assertFalse(seccion.now.has(nombre(clave)), "un dato no se reparte en dos")
        for fila in (_("gpu.now.vram"), _("gpu.now.power"), _("gpu.now.bus")):
            self.assertIn(fila, seccion.now.visible_rows(), "las de antes se quedan")
        self.assertFalse(seccion.now_pie.isVisible())

    def test_el_video_no_sale_dos_veces(self):
        seccion = self.seccion(self.fotos["5800x3d"])
        self.assertTrue(seccion.sensors._names[_("gpu.sensor.videouse")].isHidden())

    def test_sin_uso_del_video_se_dice_al_pie(self):
        """Una AMD sin `vcn_busy_percent` (antes de Linux 6.10) y con la
        telemetría en el formato 1.0, que no se interpreta: no hay de dónde
        sacar el uso del video."""
        foto_amd = self.fotos["5800x3d"]
        gpu = dataclasses.replace(foto_amd.gpus[0], video_busy_percent=None)
        seccion = self.seccion(dataclasses.replace(foto_amd, gpus=(gpu,)))
        self.assertFalse(seccion.now.has(nombre("engine.video"))
                         and nombre("engine.video") in seccion.now.visible_rows())
        self.assertTrue(seccion.now_pie.isVisible())
        self.assertEqual(seccion.now_pie.text(),
                         _("gpu.now.gap").format(motores=_("gpu.now.gap.video")))
        # Said once, at the foot of «Right now»: its row goes, no dash.
        self.assertTrue(seccion.sensors._names[_("gpu.sensor.videouse")].isHidden())

    def test_dormida_no_tiene_barras_ni_pie(self):
        gpu = dataclasses.replace(self.fotos["5800x3d"].gpus[0], suspended=True,
                                  busy_percent=None, video_busy_percent=None)
        self.assertEqual(render.engine_levels(gpu), [])
        self.assertEqual(render.engine_gaps(gpu), [])


class TestNvidia(_Pagina, unittest.TestCase):
    """Sin una NVIDIA delante: la foto sale del proveedor con lo que NVML
    devolvería (tests/test_nvidia.py)."""

    def foto(self, tarjetas):
        draft = recolectar([{"vendor": "NVIDIA", "pci_slot": "0000:01:00.0",
                             "driver": "nvidia", "integrated": False}], tarjetas)
        return dataclasses.replace(self.fotos["5800x3d"], gpus=draft.freeze().gpus)

    def test_render_decodificar_y_codificar_aparte(self):
        tarjeta = dataclasses.replace(UNA_4070, decode_busy_percent=37.0, encode_busy_percent=5.0)
        seccion = self.seccion(self.foto((tarjeta,)))
        self.assertEqual(seccion.now.text_of(nombre("engine.render")), "31 %")
        self.assertEqual(seccion.now.text_of(nombre("engine.decode")), "37 %")
        self.assertEqual(seccion.now.text_of(nombre("engine.encode")), "5 %")
        self.assertFalse(seccion.now.has(nombre("engine.video")))
        self.assertFalse(seccion.now_pie.isVisible())

    def test_sin_codificador_ni_decodificador_se_dice_al_pie(self):
        seccion = self.seccion(self.foto((UNA_4070,)))
        self.assertEqual(seccion.now.text_of(nombre("engine.render")), "31 %")
        self.assertEqual(seccion.now_pie.text(), _("gpu.now.gap").format(
            motores=render.enumeration([_("gpu.now.gap.decode"), _("gpu.now.gap.encode")],
                                       "list.nor")))

    def test_sin_nvml_no_hay_barras_pero_si_pie(self):
        """nouveau: ni uso ni nada. La tarjeta se queda para decirlo."""
        seccion = self.seccion(self.foto(()))
        self.assertTrue(seccion.now_card.isVisible())
        self.assertIn(_("gpu.now.gap.render"), seccion.now_pie.text())

    def test_nvml_escribe_dos_enteros(self):
        """El uso de NVENC y NVDEC viene con su periodo de medida: la llamada
        lleva dos punteros, o la biblioteca escribiría en memoria de nadie."""
        recibido = []

        def funcion(asa, uso, periodo):
            recibido.append((uso, periodo))
            ctypes.cast(uso, ctypes.POINTER(ctypes.c_uint)).contents.value = 25
            ctypes.cast(periodo, ctypes.POINTER(ctypes.c_uint)).contents.value = 167000
            return nvml.NVML_SUCCESS

        sesion = nvml.Nvml()
        with mock.patch.object(sesion, "_symbol", lambda *nombres: funcion):
            self.assertEqual(sesion._utilization("nvmlDeviceGetEncoderUtilization", None), 25.0)
        self.assertEqual(len(recibido[0]), 2)


if __name__ == "__main__":
    unittest.main()
