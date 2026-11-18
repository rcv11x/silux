"""El uso de una AMD es la media del intervalo, no un instante.

`gpu_busy_percent`, `mem_busy_percent` y `vcn_busy_percent` son lo que midió
el firmware en sus últimos milisegundos. En la RX 9070 XT, diez lecturas
dentro del mismo segundo van de 59 a 100 con la gráfica haciendo lo mismo, y
la ficha «Uso» saltaba de 85 a 42; MangoHud, que hace la media, daba 80-86.
El hilo de muestreo las lee cada 100 ms mientras espera
(`Collector.between_samples`) y la foto lleva la media.
"""

import builtins
import threading
import time
import unittest
from unittest import mock

from silux.collector import Collector
from silux.providers import drm
from silux.providers.base import Draft, Provider
from tests.test_gpu import BancoDrm, _write
from tests.test_grafica_dormida import Espia


class TestLaMediaDelIntervalo(BancoDrm):
    def setUp(self):
        super().setUp()
        self.dispositivo = self.tarjeta(
            1, ranura="0000:0c:00.0", vendor="0x1002", device="0x7550",
            **{"class": "0x030000"}, gpu_busy_percent="85", mem_busy_percent="10",
            vcn_busy_percent="0")
        _write(self.dispositivo / "power" / "runtime_status", "active")
        self.estado = drm.GpuState()

    def recoger(self):
        draft = Draft()
        drm.DrmGpus().collect(draft)
        self.estado.collect(draft)
        return draft.gpus[0]

    def test_sin_lecturas_entre_medias_es_la_de_ahora(self):
        self.assertEqual(self.recoger()["busy_percent"], 85.0)

    def test_con_lecturas_entre_medias_es_su_media(self):
        self.recoger()
        self.assertTrue(self.estado.wants_between_samples())
        for uso, video in (("59", "20"), ("100", "40"), ("42", "30")):
            _write(self.dispositivo / "gpu_busy_percent", uso)
            _write(self.dispositivo / "vcn_busy_percent", video)
            self.estado.between_samples()
        _write(self.dispositivo / "gpu_busy_percent", "91")
        _write(self.dispositivo / "vcn_busy_percent", "30")
        gpu = self.recoger()
        self.assertEqual(gpu["busy_percent"], round((59 + 100 + 42 + 91) / 4, 1))
        self.assertEqual(gpu["video_busy_percent"], 30.0)

    def test_cada_muestra_empieza_de_cero(self):
        self.recoger()
        _write(self.dispositivo / "gpu_busy_percent", "0")
        self.estado.between_samples()
        self.recoger()
        _write(self.dispositivo / "gpu_busy_percent", "50")
        self.assertEqual(self.recoger()["busy_percent"], 50.0)

    def test_una_dormida_no_se_lee_entre_muestras(self):
        self.recoger()
        _write(self.dispositivo / "power" / "runtime_status", "suspended")
        espia = Espia(self.dispositivo)
        with mock.patch.object(builtins, "open", espia):
            self.estado.between_samples()
        self.assertEqual(espia.prohibidos(), [])
        self.assertIn("power/runtime_status", espia.abiertos)

    def test_sin_amd_no_pide_despertar_el_hilo(self):
        self.assertFalse(drm.GpuState().wants_between_samples())


class _Contador(Provider):
    name = "contador"

    def __init__(self, quiere=True):
        self.quiere = quiere
        self.lecturas = 0

    def collect(self, draft):
        pass

    def wants_between_samples(self):
        return self.quiere

    def between_samples(self):
        self.lecturas += 1


class TestElHiloDeMuestreo(unittest.TestCase):
    def esperar(self, quiere, intervalo_ms=450):
        from silux.ui.sampler import Sampler
        proveedor = _Contador(quiere)
        muestreador = Sampler(interval_ms=intervalo_ms)
        inicio = time.monotonic()
        sigue = muestreador._esperar(Collector([proveedor]))
        return proveedor, sigue, time.monotonic() - inicio

    def test_trocea_la_espera_si_alguien_lo_pide(self):
        proveedor, sigue, tardo = self.esperar(True)
        self.assertTrue(sigue)
        self.assertGreaterEqual(proveedor.lecturas, 3)
        self.assertGreaterEqual(tardo, 0.44)

    def test_si_nadie_lo_pide_duerme_de_una_vez(self):
        proveedor, sigue, _tardo = self.esperar(False)
        self.assertTrue(sigue)
        self.assertEqual(proveedor.lecturas, 0)

    def test_parar_corta_la_espera(self):
        from silux.ui.sampler import Sampler
        muestreador = Sampler(interval_ms=5000)
        resultado = {}

        def esperar():
            resultado["sigue"] = muestreador._esperar(Collector([_Contador(True)]))

        hilo = threading.Thread(target=esperar)
        inicio = time.monotonic()
        hilo.start()
        time.sleep(0.25)
        muestreador._mutex.lock()
        muestreador._stopping = True
        muestreador._mutex.unlock()
        muestreador._wake.wakeAll()
        hilo.join(2)
        self.assertFalse(resultado["sigue"])
        self.assertLess(time.monotonic() - inicio, 1.0)

    def test_un_fallo_entre_muestras_no_tumba_nada(self):
        class Roto(_Contador):
            def between_samples(self):
                raise OSError("se fue el archivo")
        Collector([Roto()]).between_samples()


if __name__ == "__main__":
    unittest.main()
