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
    base = {"cpu": "Una CPU", "multihilo": 1000, "un_hilo": 200, "hilos": 16,
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
        self.assertEqual(herramienta.revisar(_muestra(multihilo=1700)), "")

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
