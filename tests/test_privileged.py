"""El ayudante privilegiado: contrato, límites y camino completo.

El ayudante no se puede lanzar de verdad en una prueba —abriría un diálogo de
autenticación— así que se ejercen sus funciones directamente y se sustituye el
cliente por uno falso para probar el proveedor de punta a punta.
"""

import json
import os
import pathlib
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


class TestContadoresDeLaGrafica(unittest.TestCase):
    """El PMU de la gráfica: lo único que el ayudante enumera él solo.

    Es la única acción sin parámetros. El cliente no manda ni rutas ni nombres
    de evento ni números: el ayudante mira qué PMU hay, filtra por patrón y
    traduce el nombre a un `config` leyendo el propio sysfs del kernel.
    """

    def test_es_una_accion_del_contrato(self):
        self.assertIn(protocol.ACTION_GPU_PMU, protocol.ACTIONS)

    def test_los_patrones_del_contrato_y_del_ayudante_coinciden(self):
        # Igual que con los MSR: si se separan, el cliente pediría cosas que
        # el ayudante rechaza, o al revés.
        self.assertEqual(protocol.PMU_GPU, helper.PMU_GPU.pattern)
        self.assertEqual(protocol.PMU_EVENT, helper.PMU_EVENT.pattern)
        self.assertEqual(protocol.PMU_ROOT, helper.PMU_ROOT)

    def test_el_patron_del_pmu_no_deja_salirse_del_directorio(self):
        for malo in ("..", "../../etc", "i915/../cpu", "cpu", "intel_pt",
                     "tracepoint", "kprobe", "uncore_imc", "i915x"):
            with self.subTest(nombre=malo):
                self.assertIsNone(helper.PMU_GPU.match(malo))

    def test_el_patron_admite_i915_y_el_nombre_con_ranura_de_xe(self):
        self.assertTrue(helper.PMU_GPU.match("i915"))
        self.assertTrue(helper.PMU_GPU.match("xe_0000_03_00.0"))

    def test_solo_se_abren_contadores_de_ocupacion(self):
        # Nada de muestreo, ni tracepoints, ni eventos de CPU.
        for bueno in ("rcs0-busy", "vcs1-busy", "vecs0-busy", "ccs0-busy"):
            with self.subTest(evento=bueno):
                self.assertTrue(helper.PMU_EVENT.match(bueno))
        for malo in ("rcs0-sema", "rcs0-wait", "interrupts", "actual-frequency",
                     "rc6-residency", "software-gt-awake-time", "cycles"):
            with self.subTest(evento=malo):
                self.assertIsNone(helper.PMU_EVENT.match(malo))

    def test_de_rapl_solo_el_plano_de_la_grafica(self):
        # Los otros tres —paquete, núcleos y memoria— ya se leen por powercap
        # sin privilegios, así que aquí no pintan nada.
        self.assertTrue(helper.PMU_POWER_EVENT.match("energy-gpu"))
        for malo in ("energy-pkg", "energy-cores", "energy-ram"):
            with self.subTest(evento=malo):
                self.assertIsNone(helper.PMU_POWER_EVENT.match(malo))

    def test_el_evento_se_traduce_con_el_formato_que_publica_el_kernel(self):
        # i915 escribe «config=0x2000» y RAPL «event=0x04», que no es lo
        # mismo: el segundo va corrido a los bits que diga el formato del PMU.
        with mock.patch("silux.privileged.helper.open",
                        mock.mock_open(read_data="config:8-15")):
            self.assertEqual(helper._pmu_campo("x", "event"), 8)
        self.assertEqual(helper._pmu_campo("x", "config"), 0)

    def test_un_formato_que_no_apunta_a_config_se_descarta(self):
        with mock.patch("silux.privileged.helper.open",
                        mock.mock_open(read_data="config1:0-7")):
            self.assertIsNone(helper._pmu_campo("x", "event"))

    def test_un_evento_con_parametros_de_sobra_no_se_toca(self):
        with mock.patch("silux.privileged.helper.open",
                        mock.mock_open(read_data="event=0x04,umask=0x01")):
            self.assertIsNone(helper._pmu_config("power", "energy-gpu"))

    def test_sin_privilegios_falla_diciendo_por_qué(self):
        respuesta = helper.handle({"action": protocol.ACTION_GPU_PMU})
        self.assertIn("ok", respuesta)
        if not respuesta["ok"]:
            self.assertEqual(respuesta["error"], "unsupported")
            self.assertTrue(respuesta["message"])


class TestInstaladorDelAyudante(unittest.TestCase):
    """El instalador que deja de pedir la contraseña en cada arranque.

    No hace falta root para probarlo: se le cambian las rutas de destino por
    unas del directorio temporal.
    """

    def setUp(self):
        import tempfile
        from tools import install_helper

        self.modulo = install_helper
        self._tmp = tempfile.TemporaryDirectory()
        raiz = pathlib.Path(self._tmp.name)
        self.destino = raiz / "libexec" / "silux" / "silux-helper"
        self.politica = raiz / "actions" / "org.silux.helper.policy"
        self.politica.parent.mkdir(parents=True)

        parches = [
            mock.patch.object(install_helper, "DESTINO", self.destino),
            mock.patch.object(install_helper, "POLITICA", self.politica),
            # chown pide root; lo que importa aquí es el resto.
            mock.patch.object(install_helper.os, "chown", lambda *a: None),
        ]
        for parche in parches:
            parche.start()
            self.addCleanup(parche.stop)
        self.addCleanup(self._tmp.cleanup)

    def instalar(self) -> None:
        """El instalador informa por pantalla; aquí solo estorba."""
        import contextlib
        import io

        with contextlib.redirect_stdout(io.StringIO()):
            self.modulo.instalar()

    def test_instala_el_ayudante_y_su_politica(self):
        self.instalar()
        self.assertTrue(self.destino.is_file())
        self.assertTrue(self.politica.is_file())

    def test_el_ayudante_queda_ejecutable(self):
        """pkexec ejecuta el archivo directamente, no `python3 archivo`."""
        self.instalar()
        self.assertTrue(os.access(self.destino, os.X_OK))
        self.assertEqual(self.destino.stat().st_mode & 0o777, 0o755)

    def test_el_shebang_apunta_a_un_python_del_sistema(self):
        """El de `env python3` resuelve contra el PATH de quien lo ejecute, y
        aquí lo ejecuta root a través de pkexec."""
        self.instalar()
        primera = self.destino.read_text(encoding="utf-8").splitlines()[0]
        self.assertTrue(primera.startswith("#!/"), primera)
        self.assertNotIn("env", primera)
        self.assertTrue(os.path.exists(primera[2:]), primera)

    def test_la_politica_apunta_al_ayudante_y_no_al_interprete(self):
        """Si la acción colgara de `python3`, la autorización valdría para
        cualquier script de Python de la máquina."""
        self.instalar()
        texto = self.politica.read_text(encoding="utf-8")
        self.assertIn(f">{self.destino}<", texto)
        self.assertNotIn("python3<", texto)

    def test_no_se_pide_la_contrasena_para_siempre(self):
        """`yes` dejaría la puerta abierta a cualquier proceso del usuario.
        `auth_admin_keep` la pide una vez y la recuerda mientras dure la
        sesión, que es lo que hacen los demás programas que leen hardware."""
        self.instalar()
        texto = self.politica.read_text(encoding="utf-8")
        self.assertIn("<allow_active>auth_admin_keep</allow_active>", texto)
        self.assertNotIn("<allow_active>yes</allow_active>", texto)
        # Una sesión que no está delante del equipo —un SSH— no lee sensores.
        self.assertIn("<allow_inactive>no</allow_inactive>", texto)

    def test_desinstalar_lo_deja_como_estaba(self):
        self.instalar()
        import contextlib, io
        with contextlib.redirect_stdout(io.StringIO()):
            self.modulo.desinstalar()
        self.assertFalse(self.destino.exists())
        self.assertFalse(self.politica.exists())

    def test_el_cuerpo_del_ayudante_llega_entero(self):
        """Se copia, no se enlaza: el original vive donde el usuario escribe."""
        self.instalar()
        original = self.modulo.ORIGEN.read_text(encoding="utf-8")
        copia = self.destino.read_text(encoding="utf-8")
        cuerpo = original.split("\n", 1)[1]
        self.assertEqual(copia.split("\n", 1)[1], cuerpo)
