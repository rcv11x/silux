"""El ayudante privilegiado: contrato, límites y camino completo.

El ayudante no se puede lanzar de verdad en una prueba —abriría un diálogo de
autenticación— así que se ejercen sus funciones directamente y se sustituye el
cliente por uno falso para probar el proveedor de punta a punta.
"""

import json
import os
import struct
import unittest
from unittest import mock

from silux.model import Need, PrivilegedState
from silux.privileged import helper, protocol
from silux.providers.base import Draft
from silux.providers.privileged_memory import PrivilegedMemory

from tests.test_smbios import _end, _memory_array, _memory_device, _empty_slot

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


class TestContrato(unittest.TestCase):
    """El ayudante solo debe saber hacer lo que dice el contrato."""

    def test_las_acciones_del_ayudante_son_las_declaradas(self):
        for accion in protocol.ACTIONS:
            with self.subTest(accion=accion):
                respuesta = helper.handle({"action": accion})
                self.assertIsInstance(respuesta, dict)
                self.assertIn("ok", respuesta)

    def test_una_accion_desconocida_se_rechaza(self):
        respuesta = helper.handle({"action": "borrar_todo"})
        self.assertFalse(respuesta["ok"])
        self.assertEqual(respuesta["error"], "bad_request")

    def test_no_hay_forma_de_pedir_una_ruta(self):
        # El ayudante no acepta ningún parámetro que sea una ruta: las dos que
        # abre están escritas como constantes en su propio módulo.
        fuente = open(helper.__file__, encoding="utf-8").read()
        self.assertIn('DMI_TABLE = "/sys/firmware/dmi/tables/DMI"', fuente)
        for peligroso in ("subprocess", "os.system", "eval(", "exec(", "__import__"):
            with self.subTest(termino=peligroso):
                self.assertNotIn(peligroso, fuente)

    def test_el_ayudante_solo_importa_biblioteca_estandar(self):
        fuente = open(helper.__file__, encoding="utf-8").read()
        self.assertNotIn("from silux", fuente)
        self.assertNotIn("import silux", fuente)


class TestListaBlancaDeMsr(unittest.TestCase):
    def test_un_registro_fuera_de_la_lista_se_rechaza(self):
        respuesta = helper.read_msr(0, [0x1234])
        self.assertFalse(respuesta["ok"])
        self.assertEqual(respuesta["error"], "forbidden")

    def test_mezclar_uno_permitido_con_uno_prohibido_rechaza_todo(self):
        respuesta = helper.read_msr(0, [0x0198, 0xDEAD])
        self.assertFalse(respuesta["ok"])
        self.assertEqual(respuesta["error"], "forbidden")

    def test_una_cpu_absurda_se_rechaza(self):
        for cpu in (-1, 99999, "0", None):
            with self.subTest(cpu=cpu):
                self.assertFalse(helper.read_msr(cpu, [0x0198])["ok"])

    def test_hacen_falta_registros(self):
        self.assertFalse(helper.read_msr(0, [])["ok"])
        self.assertFalse(helper.read_msr(0, "0x198")["ok"])

    def test_las_dos_listas_blancas_coinciden(self):
        # Una en el ayudante y otra en el contrato: si se separan, el cliente
        # pediría registros que el ayudante rechaza.
        self.assertEqual(set(protocol.MSR_ALLOWED), set(helper.MSR_ALLOWED))


class TestRespuestas(unittest.TestCase):
    def test_ping(self):
        respuesta = helper.handle({"action": "ping"})
        self.assertTrue(respuesta["ok"])
        self.assertEqual(respuesta["version"], helper.VERSION)

    def test_smbios_sin_tabla_lo_dice(self):
        with mock.patch.object(helper, "DMI_TABLE", "/no/existe"):
            respuesta = helper.read_smbios()
        self.assertFalse(respuesta["ok"])
        self.assertEqual(respuesta["error"], "unsupported")

    def test_toda_respuesta_es_json_serializable(self):
        for peticion in ({"action": "ping"}, {"action": "nada"},
                         {"action": "msr", "cpu": 0, "registers": [1]}):
            with self.subTest(peticion=peticion):
                json.dumps(helper.handle(peticion))


class _FakeClient:
    """Un cliente que devuelve una tabla SMBIOS fabricada."""

    def __init__(self, table: bytes = b"", fail=None):
        self._table = table
        self._fail = fail
        self.connected_flag = False

    def supported(self):
        return True

    def connected(self):
        return self.connected_flag

    def connect(self):
        if self._fail:
            raise self._fail
        self.connected_flag = True

    def smbios_table(self):
        return self._table

    def close(self):
        self.connected_flag = False


class TestProveedorDeModulos(unittest.TestCase):
    TABLA = _memory_array(slots=2) + _memory_device() + _empty_slot() + _end()

    def test_sin_pedirlo_no_eleva_nada(self):
        """Un programa que pide la contraseña al arrancar es un programa que
        se desinstala."""
        cliente = _FakeClient(self.TABLA)
        draft = Draft()
        PrivilegedMemory(cliente).collect(draft)

        self.assertFalse(cliente.connected_flag)
        self.assertEqual(draft.modules, [])
        self.assertEqual([n.need for n in draft.notes], [Need.ROOT])

    def test_al_pedirlo_lee_y_analiza(self):
        cliente = _FakeClient(self.TABLA)
        proveedor = PrivilegedMemory(cliente)
        proveedor.requested = True
        draft = Draft()
        proveedor.collect(draft)

        self.assertTrue(cliente.connected_flag)
        self.assertEqual(len(draft.modules), 2)
        self.assertTrue(draft.modules[0].populated)
        self.assertFalse(draft.modules[1].populated)
        self.assertEqual(draft.modules[0].manufacturer, "Kingston")
        self.assertEqual(draft.memory_array.slots, 2)
        self.assertIn("smbios", draft.capabilities)

    def test_si_el_usuario_cancela_se_explica_y_no_se_insiste(self):
        from silux.privileged.client import HelperDenied

        proveedor = PrivilegedMemory(_FakeClient(fail=HelperDenied("cancelado")))
        proveedor.requested = True
        draft = Draft()
        proveedor.collect(draft)

        self.assertFalse(proveedor.requested, "no debe reintentar solo")
        self.assertEqual(draft.modules, [])
        self.assertTrue(any("autoriz" in n.message.lower() for n in draft.notes))

    def test_el_estado_viaja_en_el_snapshot(self):
        draft = Draft()
        PrivilegedMemory(_FakeClient(self.TABLA)).collect(draft)
        self.assertIsInstance(draft.privileged, PrivilegedState)
        self.assertTrue(draft.privileged.supported)
        self.assertFalse(draft.privileged.connected)

    def test_como_root_lee_directamente_sin_ayudante(self):
        cliente = _FakeClient(self.TABLA)
        proveedor = PrivilegedMemory(cliente)
        draft = Draft()
        with mock.patch("silux.providers.privileged_memory.already_root", return_value=True), \
             mock.patch("builtins.open", mock.mock_open(read_data=self.TABLA)):
            proveedor.collect(draft)
        self.assertFalse(cliente.connected_flag, "como root no hace falta pkexec")
        self.assertEqual(len(draft.modules), 2)


class TestPeticionDeElevacion(unittest.TestCase):
    def test_el_colector_marca_el_proveedor(self):
        from silux.collector import Collector

        colector = Collector()
        proveedores = [p for p in colector.providers if isinstance(p, PrivilegedMemory)]
        self.assertEqual(len(proveedores), 1)
        self.assertFalse(proveedores[0].requested)

        colector.request_elevation()
        self.assertTrue(proveedores[0].requested)


if __name__ == "__main__":
    unittest.main()
