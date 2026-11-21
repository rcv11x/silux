"""El Collector contra cada equipo volcado: que todo salga y que cuadre.

Cada carpeta de `tests/fixtures/equipos/` es un equipo de verdad, volcado con
`tools/volcar_equipo.py`. Aquí se monta el Collector contra cada uno y se
comprueba lo que tiene que cumplir cualquier equipo, sea Intel o AMD: que no
se mezcla con la máquina que ejecuta la suite, que sale lo mismo que salió al
volcarlo, que dos sitios de la foto que hablan del mismo dato no se
contradicen y que el volcado no delata a nadie.

Lo que solo vale para un equipo —qué frecuencia tiene, cuántos sensores— no
va aquí: va en el test de lo que se arregla, con el volcado en el que se vio.
"""

import json
import pathlib
import unittest

from silux.model import SensorKind
from tests.test_sysroot import _vigilando
from tests.test_volcar_equipo import _herramienta

EQUIPOS = pathlib.Path(__file__).resolve().parent / "fixtures" / "equipos"


def volcados() -> list[pathlib.Path]:
    return sorted(d for d in EQUIPOS.iterdir() if (d / "manifiesto.json").is_file())


def foto(carpeta: pathlib.Path):
    """La foto de un equipo volcado, y los caminos del de verdad que tocó."""
    from silux.collector import Collector

    from tests.interval import second_snapshot

    volcar = _herramienta()
    with volcar.montado(carpeta) as raiz, _vigilando(str(raiz)) as tocados:
        recolector = Collector()
        try:
            return second_snapshot(recolector), sorted(set(tocados))
        finally:
            recolector.close()


class TestEquiposVolcados(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.volcar = _herramienta()
        cls.equipos = {d.name: (d, *foto(d)) for d in volcados()}

    def test_hay_al_menos_un_equipo(self):
        self.assertTrue(self.equipos, "no hay ningún volcado en tests/fixtures/equipos")

    def test_no_se_mezcla_con_la_maquina_que_ejecuta_la_suite(self):
        for nombre, (_carpeta, _foto, tocados) in self.equipos.items():
            with self.subTest(equipo=nombre):
                self.assertEqual(tocados[:10], [], f"{len(tocados)} caminos de esta máquina")

    def test_sale_lo_que_salio_al_volcarlo(self):
        # Si un proveedor deja de leer a través de sysroot, o lee un archivo
        # que el volcado no tiene, el equipo pierde una fuente sin avisar.
        for nombre, (carpeta, f, _tocados) in self.equipos.items():
            manifiesto = json.loads((carpeta / "manifiesto.json").read_text())
            with self.subTest(equipo=nombre):
                self.assertEqual(f.cpu.types[0].brand if f.cpu.types else None,
                                 manifiesto["cpu"])
                self.assertEqual(f.system.kernel if f.system else None, manifiesto["kernel"])
                self.assertEqual([g.name for g in f.gpus], manifiesto["gpus"])
                self.assertEqual(sorted(f.capabilities), manifiesto["fuentes"])

    def test_los_nombres_no_salen_del_pci_ids_de_quien_ejecuta(self):
        # `pci.ids` es de la máquina que corre la suite y cambia con la
        # distribución. En el CI, con el de una Ubuntu 22.04, la Radeon del
        # 5800X3D dejaba de llamarse «Radeon RX 9070 XT 16GB». Un volcado que
        # los grabó tiene que dar los mismos nombres sin ese archivo.
        from unittest import mock

        from silux import pciids
        from silux.collector import Collector

        grabaron = 0
        for nombre, (carpeta, _f, _tocados) in self.equipos.items():
            if "pciids" not in json.loads((carpeta / "grabado.json").read_text()):
                continue        # volcado antes de que se grabaran
            grabaron += 1
            manifiesto = json.loads((carpeta / "manifiesto.json").read_text())
            with self.subTest(equipo=nombre), self.volcar.montado(carpeta), \
                    mock.patch.object(pciids, "database_path", lambda: None):
                pciids._vendor_name.cache_clear()
                self.addCleanup(pciids._vendor_name.cache_clear)
                recolector = Collector()
                try:
                    recolector.snapshot()
                    f = recolector.snapshot()
                finally:
                    recolector.close()
                self.assertEqual([g.name for g in f.gpus], manifiesto["gpus"])
                self.assertTrue(all(g.subsystem_name for g in f.gpus if not g.integrated))
        self.assertGreater(grabaron, 0, "ningún volcado lleva los nombres grabados")

    def test_la_cpu_cuadra_consigo_misma(self):
        for nombre, (_carpeta, f, _tocados) in self.equipos.items():
            with self.subTest(equipo=nombre):
                self.assertTrue(f.cpu.types)
                self.assertGreater(f.cpu.total_cores, 0)
                self.assertGreaterEqual(f.cpu.total_threads, f.cpu.total_cores)
                self.assertEqual(len(f.cpu.logical), f.cpu.total_threads)
                for tipo in f.cpu.types:
                    for cache in tipo.caches:
                        self.assertGreater(cache.size_bytes or 0, 0, cache)

    def test_los_relojes_no_se_contradicen(self):
        for nombre, (_carpeta, f, _tocados) in self.equipos.items():
            for tipo in f.cpu.types:
                c = tipo.clocks
                with self.subTest(equipo=nombre, tipo=tipo.key):
                    if c.min_hz and c.max_hz:
                        self.assertLessEqual(c.min_hz, c.max_hz)
                    if c.base_hz and c.max_turbo_hz:
                        self.assertLessEqual(c.base_hz, c.max_turbo_hz)
                    if c.turbo_enabled is False and c.max_hz and c.base_hz:
                        # Con el turbo apagado, el techo que aplica el kernel
                        # no puede pasar de la frecuencia base.
                        self.assertLessEqual(c.max_hz, c.base_hz)
                    techo = max(filter(None, (c.max_hz, c.max_turbo_hz)), default=None)
                    hilos = [l for l in f.cpu.logical if l.type_key == tipo.key and l.freq_hz]
                    for hilo in hilos:
                        self.assertGreater(hilo.freq_hz, 0)
                        if techo:
                            # Un 2 % de margen: scaling_cur_freq promedia y se
                            # pasa por unos kHz del techo.
                            self.assertLessEqual(hilo.freq_hz, techo * 1.02, hilo)

    def test_la_frecuencia_de_cada_hilo_es_la_que_mide_el_hardware(self):
        # cpuinfo_avg_freq es la media medida por el hardware; scaling_cur_freq,
        # según la documentación del kernel, suele ser el último P-state pedido.
        # Si el volcado tiene la primera, es la que tiene que salir.
        for nombre, (carpeta, f, _tocados) in self.equipos.items():
            cpus = carpeta / "sys" / "devices" / "system" / "cpu"
            for hilo in f.cpu.logical:
                media = cpus / f"cpu{hilo.index}" / "cpufreq" / "cpuinfo_avg_freq"
                if not media.is_file():
                    continue
                with self.subTest(equipo=nombre, cpu=hilo.index):
                    self.assertEqual(hilo.freq_hz, int(media.read_text()) * 1000)

    def test_sin_la_media_del_hardware_sale_la_siguiente_fuente(self):
        # cpuinfo_avg_freq llegó con el kernel 6.14. En uno anterior el mismo
        # equipo no la tiene, y la frecuencia de cada hilo tiene que salir de
        # scaling_cur_freq: no quedarse en blanco ni pasarse del techo.
        from silux.collector import Collector

        for nombre, (carpeta, _f, _tocados) in self.equipos.items():
            cpus = carpeta / "sys" / "devices" / "system" / "cpu"
            if not list(cpus.glob("cpu*/cpufreq/scaling_cur_freq")):
                continue        # volcado antes de que se guardaran las dos
            with self.subTest(equipo=nombre), self.volcar.montado(carpeta) as raiz:
                for media in (raiz / "sys/devices/system/cpu").glob(
                        "cpu*/cpufreq/cpuinfo_avg_freq"):
                    media.unlink()
                recolector = Collector()
                try:
                    recolector.snapshot()
                    f = recolector.snapshot()
                finally:
                    recolector.close()
                self.assertTrue(f.cpu.logical)
                for hilo in f.cpu.logical:
                    pedida = cpus / f"cpu{hilo.index}" / "cpufreq" / "scaling_cur_freq"
                    self.assertEqual(hilo.freq_hz, int(pedida.read_text()) * 1000, hilo.index)
                for tipo in f.cpu.types:
                    c = tipo.clocks
                    techo = max(filter(None, (c.max_hz, c.max_turbo_hz)))
                    self.assertTrue(c.current_hz)
                    self.assertLessEqual(c.current_hz, techo * 1.02)
                self.assertNotIn("cpu.clocks.current_hz", [n.path for n in f.notes])

    def test_un_contador_de_energia_parado_no_da_cero_vatios(self):
        # El consumo sale de restar dos lecturas del contador de RAPL. En un
        # volcado no avanza, y un paquete encendido siempre gasta: 0 W ahí es
        # un dato que parece bueno y no lo es. Que falte, y que se diga.
        for nombre, (carpeta, f, _tocados) in self.equipos.items():
            with self.subTest(equipo=nombre):
                self.assertNotEqual(f.cpu.power.package_w, 0.0)
                vatios = [s.key for s in f.sensors
                          if s.kind == SensorKind.POWER and s.key.startswith("rapl/")]
                self.assertEqual(vatios, [])
                rapl = carpeta / "sys" / "class" / "powercap"
                if f.cpu.power.package_w is None and rapl.is_dir():
                    self.assertIn("cpu.power", [n.path for n in f.notes])

    def test_el_reloj_de_cada_hilo_es_el_mismo_en_sensores(self):
        # La página CPU pinta `cpu.logical` y la de Sensores el árbol: con la
        # misma foto tienen que decir lo mismo de cada hilo.
        for nombre, (_carpeta, f, _tocados) in self.equipos.items():
            relojes = {s.key: s.value for s in f.sensors if s.kind == SensorKind.CLOCK}
            with self.subTest(equipo=nombre):
                for hilo in f.cpu.logical:
                    clave = f"clock/cpu{hilo.index}"
                    if hilo.freq_hz is None or clave not in relojes:
                        continue
                    self.assertAlmostEqual(relojes[clave] * 1e6, hilo.freq_hz, delta=1e6,
                                           msg=clave)

    def test_los_discos_cuadran(self):
        for nombre, (_carpeta, f, _tocados) in self.equipos.items():
            for disco in f.disks:
                for particion in disco.partitions:
                    with self.subTest(equipo=nombre, particion=particion.name):
                        if disco.size_bytes and particion.size_bytes:
                            self.assertLessEqual(particion.size_bytes, disco.size_bytes)
                        if particion.used_bytes is not None and particion.free_bytes is not None \
                                and particion.size_bytes:
                            self.assertLessEqual(particion.used_bytes + particion.free_bytes,
                                                 particion.size_bytes * 1.01)

    def test_ninguna_temperatura_es_imposible(self):
        # Un canal sin sonda conectada da -128 o 127 °C, y un driver que
        # escala mal da miles. Mejor esconderlo que enseñarlo como bueno.
        for nombre, (_carpeta, f, _tocados) in self.equipos.items():
            with self.subTest(equipo=nombre):
                malas = [(s.key, s.value) for s in f.sensors
                         if s.kind == SensorKind.TEMPERATURE and s.value is not None
                         and not -30 <= s.value <= 125]
                self.assertEqual(malas, [])

    def test_el_volcado_no_delata_a_nadie(self):
        for nombre, (carpeta, f, _tocados) in self.equipos.items():
            with self.subTest(equipo=nombre):
                self.assertEqual(self.volcar._lo_que_anonimizar_taparia(f), [])
                # Los de la máquina que ejecuta la suite: en el CI no son los
                # del volcado, pero aquí, en la del autor, sí pueden serlo.
                self.assertEqual(self.volcar.comprobar(carpeta, set()), [])

    def test_ninguna_pieza_lleva_su_numero_de_serie(self):
        # silux no decodifica el serie del SPD ni el numérico del EDID: ni la
        # foto ni el comprobador lo verían. Se mira en los bytes.
        for nombre, (carpeta, _f, _tocados) in self.equipos.items():
            for eeprom in carpeta.rglob("eeprom"):
                datos = eeprom.read_bytes()
                limpio, serie = self.volcar._spd_sin_serie(datos)
                with self.subTest(equipo=nombre, spd=eeprom.parent.name):
                    self.assertFalse(any(serie))
            for edid in carpeta.rglob("edid"):
                datos = edid.read_bytes()
                with self.subTest(equipo=nombre, edid=edid.parent.name):
                    if len(datos) >= 128:
                        self.assertEqual(datos[12:16], bytes(4))
                        self.assertEqual(sum(datos[:128]) % 256, 0, "suma de control")


if __name__ == "__main__":
    unittest.main()
