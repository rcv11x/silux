"""What decides never looks at a translated text.

Soldered memory was decided by comparing its form factor with «Fila de
chips», the SPD's cause by comparing a message with `_("spd.nodriver")`, a
driver's note was found by its translated message, and the sensor tree
grouped devices by their translated names and kept the user's folds by
them. What decides works on codes, keys or raw values; the translation comes
last, when painting.

So every dump, collected with the interface in Spanish and in English, gives
the same model in everything that is not a text for the person (`TEXTS`,
said in the interface's language by design), computed properties included.
The sensor tree groups the same sensors under the same keys. And a firmware
table's memory, parsed in each language, is the same.
"""

import dataclasses
import unittest

from silux import i18n, model
from silux.providers.base import Draft
from silux.providers.privileged_memory import PrivilegedMemory
from tests.test_equipos import foto, volcados
from tests.test_nada_en_bruto import DOS_DE_CUATRO, SIN_TIPO

# The model's fields that are texts for the person: everything else is the
# same whatever the interface's language.
TEXTS = {
    ("Note", "message"), ("Note", "hint"), ("Note", "what"), ("Note", "detail"),
    ("Sensor", "device"), ("Sensor", "label"),
    ("DriverHint", "provides"), ("DriverHint", "caution"),
    ("GpuApi", "extra"),
}


def flatten(valor, ruta="", salida=None) -> dict:
    """Every value of the model by its path, texts for the person left out."""
    salida = {} if salida is None else salida
    if dataclasses.is_dataclass(valor) and not isinstance(valor, type):
        clase = type(valor).__name__
        campos = [f.name for f in dataclasses.fields(valor)]
        campos += list(model._COMPUTED.get(clase, ()))
        for campo in campos:
            if (clase, campo) not in TEXTS:
                flatten(getattr(valor, campo), f"{ruta}.{campo}", salida)
    elif isinstance(valor, dict):
        for clave, dentro in valor.items():
            flatten(dentro, f"{ruta}[{clave!r}]", salida)
    elif isinstance(valor, (list, tuple)):
        for indice, dentro in enumerate(valor):
            flatten(dentro, f"{ruta}[{indice}]", salida)
    elif isinstance(valor, (set, frozenset)):
        salida[ruta] = tuple(sorted(map(repr, valor)))
    else:
        salida[ruta] = valor
    return salida


def in_each_language(hacer):
    resultado = {}
    for idioma in ("es", "en"):
        i18n.set_language(idioma)
        try:
            resultado[idioma] = hacer()
        finally:
            i18n.set_language("es")
    return resultado


def grouping(snapshot) -> dict:
    return {clave: {categoria: tuple(s.key for s in sensores)
                    for categoria, sensores in categorias.items()}
            for clave, categorias in snapshot.sensor_tree().items()}


class TestEveryDumpInBothLanguages(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.fotos = {carpeta.name: in_each_language(lambda c=carpeta: foto(c)[0])
                     for carpeta in volcados()}

    def test_the_same_model_but_its_texts(self):
        for equipo, fotos in self.fotos.items():
            es, en = (flatten(fotos[i]) for i in ("es", "en"))
            distintos = sorted(ruta for ruta in set(es) | set(en)
                               if es.get(ruta) != en.get(ruta) and "monotonic" not in ruta)
            with self.subTest(equipo=equipo):
                self.assertEqual(distintos, [],
                                 [(r, es.get(r), en.get(r)) for r in distintos[:5]])

    def test_the_sensor_tree_groups_by_raw_keys(self):
        for equipo, fotos in self.fotos.items():
            with self.subTest(equipo=equipo):
                self.assertEqual(grouping(fotos["es"]), grouping(fotos["en"]))
                # Folds are kept by these: none is a name in either language.
                nombres = {s.device for s in fotos["es"].sensors} | {s.device for s in fotos["en"].sensors}
                self.assertFalse(set(grouping(fotos["es"])) & nombres - {""})


class TestTheFirmwaresMemoryInBothLanguages(unittest.TestCase):

    def test_parsed_the_same_and_decided_the_same(self):
        for nombre, tabla in (("dos de cuatro", DOS_DE_CUATRO), ("sin tipo", SIN_TIPO)):
            def parsear(tabla=tabla):
                draft = Draft()
                PrivilegedMemory._parse(draft, tabla)
                return ([flatten(m) for m in draft.modules],
                        [m.in_a_slot for m in draft.modules], flatten(draft.memory_array))
            with self.subTest(tabla=nombre):
                hechos = in_each_language(parsear)
                self.assertEqual(hechos["es"], hechos["en"])


if __name__ == "__main__":
    unittest.main()
