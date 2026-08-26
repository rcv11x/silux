"""El modelo: congelado, serializable y con las propiedades calculadas bien."""

import json
import unittest

import dataclasses

from silux import model
from silux.model import (Cache, Clocks, CpuInfo, CpuType, Need, Note, Snapshot,
                        to_jsonable)


class TestClocks(unittest.TestCase):
    def test_multiplicadores(self):
        clocks = Clocks(current_hz=3_700_000_000, min_hz=800_000_000,
                        max_hz=4_300_000_000, bus_hz=100_000_000)
        self.assertEqual(clocks.multiplier, 37.0)
        self.assertEqual(clocks.min_multiplier, 8.0)
        self.assertEqual(clocks.max_multiplier, 43.0)

    def test_sin_bus_no_hay_multiplicador(self):
        self.assertIsNone(Clocks(current_hz=3_700_000_000).multiplier)

    def test_multiplicador_del_reloj_base(self):
        clocks = Clocks(base_hz=3_401_000_000, bus_hz=100_029_412)
        self.assertEqual(clocks.base_multiplier, 34.0)

    def test_margen_de_turbo(self):
        limitado = Clocks(max_hz=2_900_000_000, max_turbo_hz=4_300_000_000)
        self.assertEqual(limitado.turbo_headroom_hz, 1_400_000_000)
        libre = Clocks(max_hz=4_300_000_000, max_turbo_hz=4_300_000_000)
        self.assertIsNone(libre.turbo_headroom_hz)


class TestPropiedadesExportadas(unittest.TestCase):
    """Toda propiedad calculada tiene que salir también en el JSON.

    La interfaz lee las propiedades del modelo directamente, pero el JSON solo
    lleva las que estén en `_COMPUTED`. Añadir una y olvidarse de la lista deja
    la salida para otros programas con un dato menos que la ventana, y no lo
    nota nadie: el valor no falta, sale nulo.
    """

    # Propiedades que a propósito no salen al JSON, con su motivo. Sacar algo
    # de aquí es una decisión, no un descuido.
    SOLO_INTERNAS = {
        # Filtro del decodificador de SPD: descarta perfiles corruptos antes de
        # guardarlos, así que todo lo que llega al snapshot ya es plausible y
        # exportarlo sería exportar un `true` constante.
        ("Timings", "plausible"),
    }

    def test_ninguna_propiedad_se_queda_fuera(self):
        for nombre, esperadas in model._COMPUTED.items():
            clase = getattr(model, nombre)
            calculadas = {
                atributo for atributo in vars(clase)
                if isinstance(getattr(clase, atributo), property)
                and (nombre, atributo) not in self.SOLO_INTERNAS
            }
            self.assertEqual(calculadas, set(esperadas), f"en {nombre}")

    def test_las_clases_congeladas_no_declaran_de_mas(self):
        for nombre in model._COMPUTED:
            clase = getattr(model, nombre)
            campos = {f.name for f in dataclasses.fields(clase)}
            self.assertFalse(campos & set(model._COMPUTED[nombre]), f"en {nombre}")


class TestCache(unittest.TestCase):
    def test_total_cuenta_las_instancias(self):
        cache = Cache(level=1, kind="data", size_bytes=32 * 1024, instances=6)
        self.assertEqual(cache.total_bytes, 192 * 1024)


class TestSnapshot(unittest.TestCase):
    def _snapshot(self) -> Snapshot:
        cpu_type = CpuType(
            key="performance", label="P", vendor="Intel", cores=8, threads=16,
            caches=(Cache(3, "unified", 24 << 20, 12, 64),),
            clocks=Clocks(current_hz=5_000_000_000, bus_hz=100_000_000),
        )
        other = CpuType(key="efficiency", label="E", vendor="Intel", cores=8, threads=8)
        return Snapshot(
            monotonic_ns=1,
            cpu=CpuInfo(hybrid=True, types=(cpu_type, other)),
            capabilities=frozenset({"cpuid", "hwmon"}),
            notes=(Note("cpu.voltage_v", Need.DRIVER, "falta driver"),),
        )

    def test_es_inmutable(self):
        with self.assertRaises(Exception):
            self._snapshot().cpu.sockets = 4       # type: ignore[misc]

    def test_totales_hibridos(self):
        cpu = self._snapshot().cpu
        self.assertEqual(cpu.total_cores, 16)
        self.assertEqual(cpu.total_threads, 24)

    def test_json_es_serializable_y_estable(self):
        payload = to_jsonable(self._snapshot())
        texto = json.dumps(payload)                # no debe lanzar
        self.assertIn('"total_threads": 24', json.dumps(payload, indent=1).replace("\n", ""))
        self.assertEqual(payload["capabilities"], ["cpuid", "hwmon"])   # conjunto ordenado
        self.assertEqual(payload["notes"][0]["need"], "driver")
        self.assertGreater(len(texto), 100)

    def test_notas_filtradas_por_prefijo(self):
        snapshot = self._snapshot()
        self.assertEqual(len(snapshot.notes_for("cpu.voltage")), 1)
        self.assertEqual(len(snapshot.notes_for("gpu")), 0)


if __name__ == "__main__":
    unittest.main()


class TestFormateoDeTamano(unittest.TestCase):
    """El formateo eligió mal la unidad una vez y se vio en la interfaz."""

    def setUp(self):
        from silux import render

        self.size = render.size

    def test_usa_siempre_la_unidad_mas_grande(self):
        # 13,9 MB se enseñaban como "14208 KB" porque la división en KB era
        # exacta y la de MB no.
        self.assertEqual(self.size(14548992), "13.9 MB")
        self.assertEqual(self.size(1572864), "1.5 MB")

    def test_sin_decimales_cuando_sale_redondo(self):
        self.assertEqual(self.size(12582912), "12 MB")
        self.assertEqual(self.size(32768), "32 KB")

    def test_extremos(self):
        self.assertEqual(self.size(512), "512 B")
        self.assertEqual(self.size(3 * 1024 ** 3), "3 GB")
        self.assertEqual(self.size(None), "—")
