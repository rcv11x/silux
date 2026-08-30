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
