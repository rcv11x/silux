"""Lo que tapa `tools/volcar_equipo.py` y cómo se da cuenta de lo que no."""

import importlib.util
import pathlib
import tempfile
import unittest

from silux import privacidad
from silux.model import CpuInfo, NetworkInterface, Snapshot


def _herramienta():
    ruta = pathlib.Path(__file__).resolve().parent.parent / "tools" / "volcar_equipo.py"
    spec = importlib.util.spec_from_file_location("volcar_equipo", ruta)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


volcar = _herramienta()


def _spd(tipo: int, largo: int) -> bytes:
    datos = bytearray(range(256)) * (largo // 256)
    datos[2] = tipo
    return bytes(datos)


class TestPiezasSinNumeroDeSerie(unittest.TestCase):

    def test_spd_ddr4_y_ddr5(self):
        for tipo, largo, (inicio, fin) in ((0x0C, 512, (325, 329)), (0x12, 1024, (517, 521))):
            with self.subTest(tipo=hex(tipo)):
                datos = _spd(tipo, largo)
                limpio, serie = volcar._spd_sin_serie(datos)
                self.assertEqual(serie, datos[inicio:fin])
                self.assertEqual(limpio[inicio:fin], bytes(fin - inicio))
                # Nada más cambia: el resto es lo que decodifica spd.py.
                self.assertEqual(limpio[:inicio] + limpio[fin:], datos[:inicio] + datos[fin:])

    def test_un_spd_que_no_se_conoce_se_deja(self):
        datos = _spd(0x0B, 256)
        self.assertEqual(volcar._spd_sin_serie(datos), (datos, b""))

    def test_edid_con_la_suma_de_control_al_dia(self):
        bloque = bytearray(128)
        bloque[:8] = b"\x00\xff\xff\xff\xff\xff\xff\x00"
        bloque[12:16] = b"\x12\x34\x56\x78"
        bloque[54:59] = b"\x00\x00\x00\xff\x00"
        bloque[59:72] = b"ABC123456789\n"
        bloque[127] = (-sum(bloque[:127])) % 256
        limpio = volcar._edid_sin_serie(bytes(bloque))
        self.assertEqual(limpio[12:16], bytes(4))
        self.assertNotIn(b"ABC123", limpio)
        self.assertEqual(sum(limpio) % 256, 0)


class TestLaComprobacionFinal(unittest.TestCase):

    def test_encuentra_un_dato_sustituido_y_unos_bytes_crudos(self):
        with tempfile.TemporaryDirectory() as tmp:
            raiz = pathlib.Path(tmp)
            (raiz / "texto").write_text("gateway 203.0.113.7\n")
            (raiz / "binario").write_bytes(b"\x00\x01\xe9\x02\xe4\xc8\x00")
            self.assertEqual(volcar.comprobar(raiz, set()), [])
            hallazgos = volcar.comprobar(raiz, {"203.0.113.7"}, frozenset({b"\xe9\x02\xe4\xc8"}))
            self.assertEqual(len(hallazgos), 2, hallazgos)

    def test_una_direccion_de_verdad_no_pasa_y_el_bucle_local_si(self):
        def foto(*interfaces):
            return Snapshot(monotonic_ns=0, cpu=CpuInfo(), network=tuple(interfaces))

        local = NetworkInterface(name="lo", kind="loopback", ipv4="127.0.0.1",
                                 mac="00:00:00:00:00:00", ipv6=("::1",))
        self.assertEqual(volcar._lo_que_anonimizar_taparia(foto(local)), [])
        casa = NetworkInterface(name="enp1s0", ipv4="198.51.100.20", mac=privacidad.MAC)
        self.assertEqual(volcar._lo_que_anonimizar_taparia(foto(local, casa)),
                         ["network.enp1s0.ipv4"])


class TestLasDireccionesDeProc(unittest.TestCase):

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.limpio = volcar._Anonimizador(pathlib.Path(tmp.name), {})

    def test_la_puerta_de_enlace_de_proc_net_route(self):
        texto = ("Iface\tDestination\tGateway \tFlags\n"
                 "enp1s0\t00000000\t0100A8C0\t0003\n"
                 "enp1s0\t0000A8C0\t00000000\t0001\n")
        salida = self.limpio._ruta_de_red(texto)
        self.assertNotIn("0100A8C0", salida)
        self.assertNotIn("0000A8C0", salida)
        self.assertIn(volcar._ipv4_hex(privacidad.PUERTA), salida)
        self.assertIn("0100A8C0", self.limpio.secretos)

    def test_ipv6_menos_el_bucle_local(self):
        bucle = "0" * 31 + "1"
        texto = (f"fe800000000000000000000000000001 02 40 20 80 enp1s0\n"
                 f"{bucle} 01 80 10 80 lo\n")
        salida = self.limpio._ipv6(texto)
        self.assertNotIn("fe80", salida)
        self.assertIn(bucle, salida)

    def test_los_montajes_de_alguien(self):
        texto = ("/dev/sda2 / btrfs rw 0 0\n"
                 "/dev/sdb1 /run/media/ana/Fotos\\040viejas ext4 rw 0 0\n")
        salida = self.limpio._mounts(texto)
        self.assertIn(" / btrfs", salida)
        self.assertIn("/media/unidad1", salida)
        self.assertNotIn("ana", salida)


if __name__ == "__main__":
    unittest.main()
