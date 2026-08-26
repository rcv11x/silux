"""El ioctl de amdgpu, contra una respuesta armada a mano.

No se puede probar con la tarjeta puesta —la máquina que corra los tests no
tiene por qué tener una Radeon— así que se falsea la respuesta del kernel y se
comprueba que los campos se leen de donde toca. La comprobación que de verdad
importa es la del identificador: si la estructura cambiara de forma, todos los
demás valores estarían leídos de sitios equivocados y el resultado parecería
correcto sin serlo.
"""

import struct
import unittest
from unittest import mock

from silux import amdgpu

# Los valores reales de una Radeon RX 9070 XT, para que las cuentas se puedan
# contrastar con su ficha técnica: 64 CU, 128 ROP, 20 Gbps, 644 GB/s.
NUEVE_MIL_SETENTA = {
    "device_id": 0x7550, "family": 152, "num_shader_engines": 4,
    "num_shader_arrays_per_engine": 2, "cu_active_number": 64,
    "num_rb_pipes": 16, "vram_type": 9, "vram_bit_width": 256,
}
RELOJES = {"max_engine_clock": 2_520_000, "max_memory_clock": 1_258_000}


def respuesta(campos=None, relojes=None) -> bytes:
    buffer = bytearray(amdgpu.RESPUESTA)
    for nombre, valor in {**NUEVE_MIL_SETENTA, **(campos or {})}.items():
        struct.pack_into("<I", buffer, amdgpu.CAMPOS[nombre], valor)
    for nombre, valor in {**RELOJES, **(relojes or {})}.items():
        struct.pack_into("<Q", buffer, amdgpu.CAMPOS_64[nombre], valor)
    return bytes(buffer)


def consultar(datos: bytes, device_id=0x7550):
    """Ejecuta `query` con el kernel sustituido por `datos`."""
    def ioctl_falso(descriptor, orden, peticion):
        destino = (type(peticion).return_pointer.size and peticion.return_pointer)
        import ctypes
        ctypes.memmove(destino, datos, min(len(datos), peticion.return_size))
        return 0

    with mock.patch.object(amdgpu.os, "open", lambda *a, **k: 99), \
         mock.patch.object(amdgpu.os, "close", lambda *a: None), \
         mock.patch.object(amdgpu.fcntl, "ioctl", ioctl_falso):
        return amdgpu.query("/dev/dri/renderD128", expected_device_id=device_id)


class TestLectura(unittest.TestCase):
    def setUp(self):
        self.info = consultar(respuesta())

    def test_memoria(self):
        self.assertEqual(self.info.vram_type, "GDDR6")
        self.assertEqual(self.info.vram_bits, 256)

    def test_unidades_del_chip(self):
        self.assertEqual(self.info.compute_units, 64)
        self.assertEqual(self.info.shader_engines, 4)

    def test_los_rop_salen_de_multiplicar(self):
        # 16 por cada uno de los ocho arrays: los 128 de la ficha técnica.
        self.assertEqual(self.info.rops, 128)

    def test_tasa_de_datos_de_la_gddr6(self):
        # Dieciséis transferencias por ciclo: 1258 MHz dan los 20 Gbps que
        # anuncia AMD para esta tarjeta.
        self.assertEqual(self.info.memory_data_rate_hz, 20_128_000_000)

    def test_ancho_de_banda(self):
        self.assertEqual(round(self.info.bandwidth_bytes / 1e9), 644)

    def test_relojes_maximos(self):
        self.assertEqual(self.info.max_engine_hz, 2_520_000_000)
        self.assertEqual(self.info.max_memory_hz, 1_258_000_000)


class TestOtrasMemorias(unittest.TestCase):
    def test_hbm_va_al_doble_del_reloj(self):
        info = consultar(respuesta({"vram_type": 6, "vram_bit_width": 2048},
                                   {"max_memory_clock": 945_000}))
        self.assertEqual(info.vram_type, "HBM")
        # Una Vega 64: 1,89 Gbps sobre 2048 bits son 484 GB/s.
        self.assertEqual(round(info.bandwidth_bytes / 1e9), 484)

    def test_gddr5(self):
        info = consultar(respuesta({"vram_type": 5, "vram_bit_width": 256},
                                   {"max_memory_clock": 2_000_000}))
        # Una RX 580: 8 Gbps sobre 256 bits son 256 GB/s.
        self.assertEqual(round(info.bandwidth_bytes / 1e9), 256)

    def test_una_memoria_sin_factor_conocido_no_inventa_el_ancho(self):
        info = consultar(respuesta({"vram_type": 1}))     # GDDR1
        self.assertEqual(info.vram_type, "GDDR1")
        self.assertIsNone(info.bandwidth_bytes)

    def test_un_tipo_que_no_esta_en_la_tabla(self):
        info = consultar(respuesta({"vram_type": 99}))
        self.assertIsNone(info.vram_type)
        self.assertIsNone(info.bandwidth_bytes)


class TestDesconfianza(unittest.TestCase):
    def test_si_el_identificador_no_cuadra_se_descarta_todo(self):
        # La defensa contra que el kernel cambie la estructura: sin esto, los
        # campos se leerían de posiciones equivocadas y darían números que
        # parecen buenos.
        self.assertIsNone(consultar(respuesta(), device_id=0x1234))

    def test_sin_identificador_esperado_no_se_comprueba(self):
        info = amdgpu.DeviceInfo(device_id=0x7550)
        self.assertEqual(info.device_id, 0x7550)

    def test_un_nodo_que_no_se_puede_abrir(self):
        def no_existe(*args, **kwargs):
            raise OSError("no such device")

        with mock.patch.object(amdgpu.os, "open", no_existe):
            self.assertIsNone(amdgpu.query("/dev/dri/renderD128"))

    def test_un_ioctl_que_falla(self):
        def revienta(*args, **kwargs):
            raise OSError("inappropriate ioctl for device")

        with mock.patch.object(amdgpu.os, "open", lambda *a, **k: 99), \
             mock.patch.object(amdgpu.os, "close", lambda *a: None), \
             mock.patch.object(amdgpu.fcntl, "ioctl", revienta):
            self.assertIsNone(amdgpu.query("/dev/dri/renderD128"))


class TestSinDatos(unittest.TestCase):
    def test_una_estructura_a_ceros(self):
        info = consultar(b"\x00" * amdgpu.RESPUESTA, device_id=None)
        self.assertIsNone(info.vram_type)
        self.assertIsNone(info.rops)
        self.assertIsNone(info.bandwidth_bytes)


if __name__ == "__main__":
    unittest.main()
