"""Cada nota de permisos dice, en corto, qué es lo que falta.

Una nota explica por qué falta un dato, con un párrafo. Para juntar en Inicio
todo lo que falta por permisos hace falta lo otro: qué falta, en tres
palabras. Lo escribe el mismo proveedor que pone la nota. Deducirlo de la
ruta —`disks.health`, `gpus.0`— sería volver a adivinar por el nombre lo que
el proveedor ya sabía.

Con los volcados de los dos equipos, que son sin permisos.
"""

import dataclasses
import unittest

from silux.model import Need, Note, PrivilegedState
from tests.test_equipos import EQUIPOS, foto, shared_snapshot


class TestLoQueFaltaPorPermisos(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.fotos = {n: shared_snapshot(EQUIPOS / n) for n in ("i5-10400", "5800x3d")}

    def test_cada_nota_de_permisos_dice_que_falta(self):
        for nombre, f in self.fotos.items():
            de_permisos = [n for n in f.notes if n.need is Need.ROOT]
            self.assertTrue(de_permisos, nombre)
            for nota in de_permisos:
                with self.subTest(equipo=nombre, nota=nota.path):
                    self.assertTrue(nota.what, "no dice qué falta")
                    # Corto: va en una lista, y en compacto en una línea.
                    self.assertLess(len(nota.what), 40)
                    self.assertNotEqual(nota.what, nota.message)

    def test_no_hay_dos_que_se_llamen_igual(self):
        for nombre, f in self.fotos.items():
            with self.subTest(equipo=nombre):
                nombres = [n.what for n in f.permission_notes]
                self.assertEqual(len(nombres), len(set(nombres)), nombres)

    def test_las_que_no_son_de_permisos_no_entran(self):
        # En el 5800X3D el consumo falta porque el contador no avanza en un
        # volcado, y el SPD porque el kernel no activó el SMBus: ninguna de
        # las dos se arregla con una contraseña.
        f = self.fotos["5800x3d"]
        self.assertEqual({n.path for n in f.permission_notes},
                         {"modules", "disks.health", "cpu.voltage_v"})

    def test_en_el_intel_estan_las_cinco(self):
        f = self.fotos["i5-10400"]
        self.assertEqual({n.path for n in f.permission_notes},
                         {"modules", "gpus.0", "disks.health", "memory.traffic",
                          "cpu.voltage_v"})

    def test_sin_ayudante_no_hay_nada_que_ofrecer(self):
        # Sin pkexec o sin un Python del sistema, el botón no sabría arreglar
        # nada: prometer esos datos sería el botón que no hace nada.
        f = dataclasses.replace(self.fotos["i5-10400"],
                                privileged=PrivilegedState(supported=False))
        self.assertEqual(f.permission_notes, ())

    def test_un_permiso_denegado_sin_nombre_no_se_promete(self):
        # La nota genérica del colector —un archivo que no se deja leer en un
        # entorno enjaulado— no la sabe resolver el ayudante.
        f = self.fotos["i5-10400"]
        ajena = Note(path="network", need=Need.ROOT, message="no se deja leer /sys/class/net")
        con_ella = dataclasses.replace(f, notes=f.notes + (ajena,))
        self.assertNotIn(ajena, con_ella.permission_notes)
        self.assertEqual(len(con_ella.permission_notes), len(f.permission_notes))


if __name__ == "__main__":
    unittest.main()
