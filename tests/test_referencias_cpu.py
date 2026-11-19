"""Cientos de procesadores de verdad contra la tabla de identificación.

`tests/fixtures/referencias_cpu.json` sale de los volcados de CPUID de los
tests de libcpuid (`tools/gen_referencias_cpu.py`): de cada uno, su firma,
su marca, sus núcleos y cachés, y el nombre en clave y el nodo que espera
libcpuid. Cada uno pasa por `db.identify_x86`, que es lo que hace la ficha de
CPU con el procesador de quien la abre.

Es la red de la tabla propia (fase 2): lo que hoy sale como libcpuid tiene
que seguir saliendo, y lo que no, está en `referencias_cpu_pendientes.json`
con lo que da hoy Silux. Esa lista solo puede encoger: si uno de ella empieza
a salir bien, el test pide quitarlo, para que no tape un fallo nuevo.
"""

import json
import pathlib
import unittest

from silux import db

FIXTURES = pathlib.Path(__file__).resolve().parent / "fixtures"
CON_TABLA = ("GenuineIntel", "AuthenticAMD")


def _referencias() -> list[dict]:
    return json.loads((FIXTURES / "referencias_cpu.json").read_text(encoding="utf-8"))["cpus"]


def _pendientes() -> dict[str, dict]:
    return json.loads((FIXTURES / "referencias_cpu_pendientes.json").read_text(
        encoding="utf-8"))["cpus"]


def identificar(cpu: dict) -> tuple[str, str]:
    """Lo que da hoy la tabla, como texto comparable con lo de libcpuid."""
    ident = db.identify_x86(
        vendor_id=cpu["vendor"], family=cpu["family"], model=cpu["model"],
        stepping=cpu["stepping"], ext_family=cpu["ext_family"], ext_model=cpu["ext_model"],
        cores=cpu["cores"], brand=cpu["brand"], l2_kb=cpu["l2_kb"], l3_kb=cpu["l3_kb"])
    return ident.codename or "", ident.technology or ""


def esperado(cpu: dict) -> tuple[str, str]:
    # libcpuid escribe «Unknown» cuando su fila no trae nodo; Silux, nada.
    nodo = "" if cpu["technology"].lower() == "unknown" else cpu["technology"]
    return cpu["codename"], nodo


class TestLasReferencias(unittest.TestCase):

    def test_son_bastantes_y_de_los_dos_fabricantes(self):
        cpus = [c for c in _referencias() if c["vendor"] in CON_TABLA]
        self.assertGreater(len(cpus), 300)
        self.assertGreater(sum(c["vendor"] == "AuthenticAMD" for c in cpus), 100)
        self.assertGreater(sum(c["vendor"] == "GenuineIntel" for c in cpus), 100)

    def test_lo_que_sale_bien_sigue_saliendo(self):
        pendientes = _pendientes()
        for cpu in _referencias():
            if cpu["vendor"] not in CON_TABLA or cpu["source"] in pendientes:
                continue
            with self.subTest(cpu=cpu["source"]):
                codename, node = identificar(cpu)
                expected_codename, expected_node = esperado(cpu)
                self.assertEqual(codename, expected_codename)
                # Where libcpuid has no node, another source may give one:
                # knowing more isn't worse.
                if expected_node:
                    self.assertEqual(node, expected_node)

    def test_los_pendientes_siguen_dando_lo_apuntado(self):
        """Si uno empieza a salir bien, se quita de la lista; si da otra cosa
        mal, se mira: puede ser que haya empeorado."""
        referencias = {c["source"]: c for c in _referencias()}
        for fuente, apuntado in _pendientes().items():
            with self.subTest(cpu=fuente):
                self.assertIn(fuente, referencias)
                cpu = referencias[fuente]
                hoy = identificar(cpu)
                codename, node = esperado(cpu)
                self.assertFalse(hoy[0] == codename and (not node or hoy[1] == node),
                                 "ya sale bien: quítalo de referencias_cpu_pendientes.json")
                self.assertEqual(list(hoy), apuntado["silux"])


if __name__ == "__main__":
    unittest.main()
