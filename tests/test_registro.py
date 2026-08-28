"""El registro de la sesión a CSV.

Un monitor abierto durante una partida ve cosas que el usuario no: en qué
minuto empezó a subir la temperatura, cuánto duró de verdad el pico. Todo eso
vivía en la memoria del programa y se perdía al cerrarlo.
"""

import csv
import pathlib
import tempfile
import unittest

from silux.model import CpuInfo, Sensor, SensorKind, Snapshot
from silux.registro import Registro


def _foto(momento_ns: int, **valores) -> Snapshot:
    sensores = tuple(
        Sensor(key=clave, chip="chip", device="Placa", label=clave.upper(),
               kind=SensorKind.TEMPERATURE, value=valor)
        for clave, valor in valores.items()
    )
    return Snapshot(monotonic_ns=momento_ns, cpu=CpuInfo(), sensors=sensores)


class TestRegistro(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.destino = pathlib.Path(self._tmp.name) / "sesion.csv"
        self.addCleanup(self._tmp.cleanup)

    def _leer(self) -> list[list[str]]:
        with open(self.destino, newline="", encoding="utf-8") as f:
            return list(csv.reader(f))

    def test_una_fila_por_muestreo(self):
        r = Registro(self.destino)
        r.abrir(_foto(0, cpu=40.0))
        for i in range(3):
            r.escribir(_foto(i * 10**9, cpu=40.0 + i))
        r.cerrar()
        filas = self._leer()
        self.assertEqual(len(filas), 4)          # cabecera + tres
        self.assertEqual(r.filas, 3)

    def test_la_cabecera_lleva_el_nombre_legible_y_la_unidad(self):
        """Quien abre esto en una hoja de cálculo no sabe qué es
        «hwmon/nct6798/temp3_input»."""
        r = Registro(self.destino)
        r.abrir(_foto(0, cpu=40.0))
        r.cerrar()
        self.assertEqual(self._leer()[0], ["hora", "segundos", "Placa · CPU (°C)"])

    def test_los_segundos_cuentan_desde_que_se_empezo(self):
        r = Registro(self.destino)
        r.abrir(_foto(5 * 10**9, cpu=40.0))
        r.escribir(_foto(5 * 10**9, cpu=40.0))
        r.escribir(_foto(12 * 10**9, cpu=41.0))
        r.cerrar()
        self.assertEqual([f[1] for f in self._leer()[1:]], ["0.0", "7.0"])

    def test_un_sensor_que_desaparece_deja_la_celda_vacia(self):
        """Una hoja de cálculo dibuja el cero y salta el hueco, que es
        exactamente la diferencia que hay que ver."""
        r = Registro(self.destino)
        r.abrir(_foto(0, cpu=40.0, gpu=50.0))
        r.escribir(_foto(0, cpu=40.0))
        r.cerrar()
        self.assertEqual(self._leer()[1][2:], ["40", ""])

    def test_un_sensor_nuevo_no_descoloca_las_filas_anteriores(self):
        """Aparece al enchufar algo o al cargar un módulo. Las columnas se
        fijan con la primera foto."""
        r = Registro(self.destino)
        r.abrir(_foto(0, cpu=40.0))
        r.escribir(_foto(0, cpu=40.0, recien_llegado=1.0))
        r.cerrar()
        filas = self._leer()
        self.assertEqual(len(filas[0]), 3)
        self.assertEqual(len(filas[1]), 3)

    def test_escribir_sin_abrir_no_revienta(self):
        Registro(self.destino).escribir(_foto(0, cpu=40.0))
        self.assertFalse(self.destino.exists())

    def test_lo_escrito_esta_en_el_disco_antes_de_cerrar(self):
        """Si el equipo se cuelga —que es justo el caso para el que se
        enciende un registro— lo de antes tiene que seguir ahí."""
        r = Registro(self.destino)
        r.abrir(_foto(0, cpu=40.0))
        r.escribir(_foto(0, cpu=40.0))
        self.assertGreater(self.destino.stat().st_size, 0)
        self.assertEqual(len(self._leer()), 2)
        r.cerrar()

    def test_un_valor_ausente_no_se_escribe_como_cero(self):
        r = Registro(self.destino)
        r.abrir(_foto(0, cpu=None))
        r.escribir(_foto(0, cpu=None))
        r.cerrar()
        self.assertEqual(self._leer()[1][2], "")

    def test_los_numeros_van_con_punto_decimal(self):
        """Es lo que toda hoja de cálculo entiende sin elegir región."""
        r = Registro(self.destino)
        r.abrir(_foto(0, cpu=40.5))
        r.escribir(_foto(0, cpu=40.5))
        r.cerrar()
        self.assertEqual(self._leer()[1][2], "40.5")

    def test_cerrar_dos_veces_no_falla(self):
        r = Registro(self.destino)
        r.abrir(_foto(0, cpu=40.0))
        r.cerrar()
        r.cerrar()
        self.assertFalse(r.activo)
