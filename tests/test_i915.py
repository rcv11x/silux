"""El ioctl que cuenta las unidades de ejecución de una gráfica Intel.

Misma limitación honesta que en `test_nvidia.py`: la máquina donde se escribió
esto lleva una Radeon, así que no hay ningún i915 al que preguntar. Lo que se
prueba es lo que rodea a la llamada —cómo se arma la petición, qué se descarta
y qué se hace con lo que conteste— y no la llamada en sí. Quien lo ejecute con
una Intel puesta, que contraste con `intel_gpu_top -L` o con
`clinfo | grep -i "compute units"` multiplicado por dieciséis.
"""

import ctypes
import unittest
from unittest import mock

from silux import i915


class TestLaPeticion(unittest.TestCase):
    def test_mide_lo_que_el_kernel_espera(self):
        """Un s32, cuatro bytes de relleno y un puntero de ocho."""
        self.assertEqual(ctypes.sizeof(i915._Peticion), 16)

    def test_el_numero_de_orden_es_el_de_i915_getparam(self):
        # DRM_IOWR('d', 0x46, 16): lectura y escritura, tamaño 16, letra 'd'.
        esperado = (3 << 30) | (16 << 16) | (ord("d") << 8) | 0x46
        self.assertEqual(i915._ORDEN, esperado)


class TestQuery(unittest.TestCase):
    """Con el ioctl fingido, que es hasta donde se puede llegar sin hardware."""

    def _con(self, respuestas, **kwargs):
        """`respuestas` va por número de parámetro; lo que falte, un error."""
        def falso(descriptor, orden, peticion):
            valor = respuestas.get(peticion.param)
            if valor is None:
                raise OSError(22, "Invalid argument")
            peticion.value[0] = valor
            return 0

        with mock.patch.object(i915.os, "open", return_value=3), \
             mock.patch.object(i915.os, "close"), \
             mock.patch.object(i915.fcntl, "ioctl", side_effect=falso):
            return i915.query("/dev/dri/renderD128", **kwargs)

    def test_una_iris_xe_de_ochenta_unidades(self):
        """El i5-1135G7 del ThinkPad: 5 subslices de 16 EU cada uno.

        El 5 es justo lo que contestaba OpenCL y lo que salía en la ficha con
        la etiqueta de los 80.
        """
        info = self._con({i915.I915_PARAM_CHIPSET_ID: 0x9A49,
                          i915.I915_PARAM_EU_TOTAL: 80,
                          i915.I915_PARAM_SUBSLICE_TOTAL: 5})
        self.assertEqual(info.eu_total, 80)
        self.assertEqual(info.subslices, 5)

    def test_si_el_chip_no_es_el_que_dice_sysfs_se_descarta_entero(self):
        """Sería hablar con otra tarjeta y atribuirle lo que conteste."""
        info = self._con({i915.I915_PARAM_CHIPSET_ID: 0x9A49,
                          i915.I915_PARAM_EU_TOTAL: 80},
                         expected_device_id=0x46A6)
        self.assertIsNone(info)

    def test_un_parametro_que_el_driver_no_conoce_no_tira_el_resto(self):
        info = self._con({i915.I915_PARAM_CHIPSET_ID: 0x9A49,
                          i915.I915_PARAM_EU_TOTAL: 96})
        self.assertEqual(info.eu_total, 96)
        self.assertIsNone(info.subslices)

    def test_cero_no_es_una_respuesta(self):
        """Ninguna gráfica tiene cero unidades: es el driver callándose."""
        info = self._con({i915.I915_PARAM_CHIPSET_ID: 0x9A49,
                          i915.I915_PARAM_EU_TOTAL: 0})
        self.assertIsNone(info.eu_total)

    def test_un_nodo_que_no_se_puede_abrir_no_revienta(self):
        with mock.patch.object(i915.os, "open", side_effect=OSError):
            self.assertIsNone(i915.query("/dev/dri/renderD128"))


if __name__ == "__main__":
    unittest.main()
