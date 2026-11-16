"""Qué se admite de un informe ajeno y qué no.

El cliente es código abierto: cualquiera puede mandar un informe con la cifra
que le apetezca y no hay forma de impedirlo. Lo que sí se puede es que una
entrada inventada no mueva la tabla, y para eso están las condiciones que el
informe trae al lado de la puntuación.
"""

import importlib.util
import pathlib
import unittest

RAIZ = pathlib.Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location(
    "anadir_puntuacion", RAIZ / "tools" / "anadir_puntuacion.py")
herramienta = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(herramienta)

from silux import score  # noqa: E402


def _muestra(**cambios):
    # Una pieza de dieciséis hilos que escala unas nueve veces, como el patrón:
    # las dos cifras salen parecidas porque ya van divididas por las suyas.
    base = {"cpu": "Una CPU", "multihilo": 955, "un_hilo": 1000, "hilos": 16,
            "escala": f"v{score.VERSION}", "gobernador": "performance",
            "carga": 0.5, "origen": "x.md"}
    return base | cambios


class TestLoQueEntraEnLaTabla(unittest.TestCase):
    def test_una_medida_normal_entra(self):
        self.assertEqual(herramienta.revisar(_muestra()), "")

    def test_una_escala_que_ya_no_es_la_vigente_no_entra(self):
        self.assertIn("otra escala", herramienta.revisar(_muestra(escala="v1")))

    def test_una_medida_con_el_equipo_ocupado_no_entra(self):
        """Describe el momento, no la pieza."""
        self.assertIn("carga de fondo", herramienta.revisar(_muestra(carga=40.0)))

    def test_una_puntuacion_imposible_no_entra(self):
        """Ninguna carga escala por encima del número de hilos."""
        motivo = herramienta.revisar(_muestra(multihilo=99999))
        self.assertIn("imposible", motivo)

    def test_pero_una_escala_creible_sí(self):
        """Ocho núcleos con SMT dan del orden de ocho o nueve veces."""
        self.assertEqual(herramienta.revisar(self._con_escala(9.0)), "")

    def _con_escala(self, veces, hilos=16, un_hilo=1000):
        """Una muestra cuyo equipo escala `veces` de un hilo a todos.

        Las dos puntuaciones ya van divididas por las del patrón, así que su
        cociente no es la escala del equipo: es la del equipo dividida entre
        la del patrón. Se compone a partir de la del patrón para que el test
        hable de la escala de verdad.
        """
        multihilo = round(un_hilo * veces / herramienta.escala_del_patron())
        return _muestra(multihilo=multihilo, un_hilo=un_hilo, hilos=hilos)

    def test_escalar_ochenta_veces_con_dieciseis_hilos_no_entra(self):
        """1700 contra 200 parecía 8,5 veces y era unas ochenta, porque el
        patrón ya escala nueve. La comprobación comparaba las cifras
        normalizadas con el número de hilos y lo daba por bueno (F-M34)."""
        self.assertIn("imposible", herramienta.revisar(
            _muestra(multihilo=1700, un_hilo=200, hilos=16)))

    def test_ni_escalar_un_poco_mas_que_los_hilos(self):
        self.assertIn("imposible", herramienta.revisar(self._con_escala(17.5)))

    def test_sin_puntuacion_no_hay_nada_que_añadir(self):
        self.assertEqual(herramienta.revisar(_muestra(multihilo=None)),
                         "sin puntuación")


class TestLecturaDeUnInforme(unittest.TestCase):
    def test_un_informe_sin_rendimiento_se_rechaza_diciendo_por_que(self):
        import tempfile

        with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False) as fh:
            fh.write("## Procesador\n\n**Una CPU**\n")
            ruta = pathlib.Path(fh.name)
        datos, fallo = herramienta.leer(ruta)
        self.assertIn("rendimiento", fallo)
        ruta.unlink()



class TestConUnInformeDeVerdad(unittest.TestCase):
    """Los informes que se leen aquí los escribe `report.build`.

    Los demás tests de este archivo usan nombres inventados y muestras ya
    troceadas, y así no se veía lo que pasaba con un informe de verdad: la
    herramienta guardaba la pieza con la marca entera que lleva el informe
    —«Intel(R) Core(TM) i5-10400 CPU @ 2.90GHz»— y la interfaz la busca por
    el nombre corto que pone `render.cpu_short_name` —«Intel Core
    i5-10400»—, así que la barra de comparación no salía nunca, por muchas
    muestras que hubiera (F-A6).
    """

    MARCA = "Intel(R) Core(TM) i5-10400 CPU @ 2.90GHz"

    def _informe(self, **cambios) -> pathlib.Path:
        import tempfile
        from unittest import mock

        from silux import history, report
        from silux.model import CpuInfo, CpuType, Snapshot
        from tests.escala import tabla_de_la_escala

        tabla = tabla_de_la_escala(self)
        hilos = tabla["patron"]["hilos"]
        medidas = {f"{c}/1": v for c, v in tabla["un_hilo"].items()}
        medidas |= {f"{c}/{hilos}": v for c, v in tabla["multihilo"].items()}
        prueba = history.Entry(
            timestamp=1.0, cpu="Intel Core i5-10400", threads=hilos, seconds=15.0,
            scores=medidas, governor="performance", score_version=score.VERSION,
            background_load=0.3, **cambios)
        foto = Snapshot(monotonic_ns=0, cpu=CpuInfo(types=(
            CpuType(key="general", label="general", brand=self.MARCA,
                    cores=6, threads=12),)))
        with mock.patch("silux.history.load", return_value=[prueba]):
            texto = report.build(foto)
        carpeta = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(__import__("shutil").rmtree, carpeta)
        ruta = carpeta / "informe.md"
        ruta.write_text(texto, encoding="utf-8")
        return ruta

    def test_se_lee_entero(self):
        datos, fallo = herramienta.leer(self._informe())
        self.assertEqual(fallo, "")
        self.assertEqual(herramienta.revisar(datos), "")

    def test_la_pieza_se_guarda_con_el_nombre_que_busca_la_interfaz(self):
        from silux import render

        datos, _fallo = herramienta.leer(self._informe())
        self.assertEqual(datos["cpu"], render.cpu_short_name(self.MARCA))


class TestRemedirLaEscalaNoBorraLoAjeno(unittest.TestCase):
    """Las medidas de otros equipos no se pueden volver a tomar.

    `anadir_puntuacion.py` las acumula en «piezas» a partir de los informes que
    manda la gente, y `medir_referencia.py` reescribía el archivo entero sin
    esa clave: remedir la escala las borraba todas, sin decirlo. No se llegó a
    notar porque cuando se encontró todavía no había ninguna guardada.

    Cuando cambia la versión de la fórmula sí se descartan, y ahí es lo
    correcto: una cifra medida con la escala anterior no significa lo mismo que
    una de ahora.
    """

    def _herramienta(self):
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "medir_referencia", RAIZ / "tools" / "medir_referencia.py")
        modulo = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(modulo)
        return modulo

    def _con_tabla(self, tabla):
        import json
        from unittest import mock

        medir = self._herramienta()
        datos = json.dumps(tabla)
        abrir = mock.mock_open(read_data=datos)
        return medir, mock.patch("pathlib.Path.open", abrir)

    def test_con_la_misma_version_las_piezas_se_conservan(self):
        piezas = {"AMD Ryzen 5 5600G": {"hilos": 12, "multihilo": [800, 810, 795]}}
        medir, parche = self._con_tabla(
            {"version_formula": score.VERSION, "piezas": piezas})
        with parche:
            self.assertEqual(medir._piezas_que_siguen_valiendo(), piezas)

    def test_con_otra_version_se_descartan(self):
        """Y se dice, que borrar en silencio es lo que hacía antes."""
        medir, parche = self._con_tabla(
            {"version_formula": score.VERSION - 1,
             "piezas": {"Una CPU": {"hilos": 8, "multihilo": [500]}}})
        with parche:
            self.assertEqual(medir._piezas_que_siguen_valiendo(), {})

    def test_sin_piezas_guardadas_no_inventa_la_clave(self):
        medir, parche = self._con_tabla({"version_formula": score.VERSION})
        with parche:
            self.assertEqual(medir._piezas_que_siguen_valiendo(), {})

    def test_un_archivo_ilegible_no_revienta_la_medida(self):
        from unittest import mock

        medir = self._herramienta()
        with mock.patch("pathlib.Path.open", side_effect=OSError):
            self.assertEqual(medir._piezas_que_siguen_valiendo(), {})
