"""El ayudante privilegiado: contrato, límites y camino completo.

El ayudante no se puede lanzar de verdad en una prueba —abriría un diálogo de
autenticación— así que se ejercen sus funciones directamente y se sustituye el
cliente por uno falso para probar el proveedor de punta a punta.
"""

import io
import json
import re
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
        for peligroso in ("os.system", "os.exec", "os.spawn", "os.popen", "eval(", "exec(",
                          "__import__", "shell="):
            with self.subTest(termino=peligroso):
                self.assertNotIn(peligroso, fuente)

    def test_the_one_program_it_runs_is_modprobe(self):
        import ast

        tree = ast.parse(open(helper.__file__, encoding="utf-8").read())
        runs = []
        for function in (n for n in tree.body if isinstance(n, ast.FunctionDef)):
            for node in ast.walk(function):
                if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                        and getattr(node.func.value, "id", None) == "subprocess"):
                    runs.append((function.name, node.func.attr, ast.unparse(node.args[0])))
        self.assertEqual(runs, [("load_module", "run", "[modprobe, '-b', '--', name]")])

    def test_it_writes_no_file(self):
        fuente = open(helper.__file__, encoding="utf-8").read()
        for writing in ("O_WRONLY", "O_RDWR", "O_CREAT", "O_TRUNC", "O_APPEND", "write_text",
                        "write_bytes", "os.write(", "os.rename", "os.replace", "os.unlink",
                        "os.remove", "os.mkdir", "os.makedirs", "shutil"):
            with self.subTest(term=writing):
                self.assertNotIn(writing, fuente)
        for mode in re.findall(r"open\([^)]*\)", fuente):
            self.assertNotRegex(mode, r"[\"'][rwab+]*[wa+][rwab+]*[\"']")

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

    def test_invalid_utf8_gets_an_answer_and_the_helper_goes_on(self):
        stdin = mock.Mock(buffer=io.BytesIO(
            b'{"action": "smart", "device": "\xff\xfe"}\n\xff\xfe\n{"action": "ping"}\n'))
        out = io.StringIO()
        with mock.patch.object(helper.os, "geteuid", return_value=0), \
             mock.patch.object(helper.sys, "stdin", stdin), \
             mock.patch("sys.stdout", out):
            self.assertEqual(helper.main(), 0)
        replies = [json.loads(line) for line in out.getvalue().splitlines()]
        self.assertEqual([r["ok"] for r in replies], [False, False, True])

    def test_toda_respuesta_es_json_serializable(self):
        for peticion in ({"action": "ping"}, {"action": "nada"},
                         {"action": "msr", "cpu": 0, "registers": [1]}):
            with self.subTest(peticion=peticion):
                json.dumps(helper.handle(peticion))


class TestTheContract(unittest.TestCase):
    """protocol.py is what the helper and the program agree on: nothing in it
    that nobody uses, and one version, the real one."""

    def test_every_name_is_used(self):
        import ast
        import pathlib
        import re
        origen = pathlib.Path(protocol.__file__).resolve()
        raiz = origen.parents[2]
        arbol = ast.parse(origen.read_text(encoding="utf-8"))
        nombres = {t.id for n in arbol.body if isinstance(n, (ast.Assign, ast.AnnAssign))
                   for t in (n.targets if isinstance(n, ast.Assign) else [n.target])
                   if isinstance(t, ast.Name)}
        nombres |= {n.name for n in arbol.body if isinstance(n, (ast.ClassDef, ast.FunctionDef))}
        usados = set()
        # The helper has its own copies by the same names: they do not count.
        for archivo in [*(raiz / "silux").rglob("*.py"), *(raiz / "tests").rglob("*.py")]:
            if archivo.resolve() in (origen, pathlib.Path(helper.__file__).resolve()):
                continue
            texto = archivo.read_text(encoding="utf-8")
            usados |= {n for n in nombres if re.search(rf"\b{n}\b", texto)}
        self.assertEqual(sorted(nombres - usados), [])

    def test_one_version_the_helpers(self):
        self.assertFalse(hasattr(protocol, "PROTOCOL_VERSION"))
        self.assertEqual(protocol.HELPER_VERSION, helper.VERSION)


class TestOnePkexecCommand(unittest.TestCase):
    """Every pkexec command is built by client.py: four places built their
    own, each with its own handling of a missing interpreter."""

    def test_nobody_else_builds_one(self):
        import ast
        import pathlib
        paquete = pathlib.Path(protocol.__file__).resolve().parents[1]
        cliente = paquete / "privileged" / "client.py"
        fuera = []
        for archivo in paquete.rglob("*.py"):
            if archivo.resolve() == cliente.resolve():
                continue
            for nodo in ast.walk(ast.parse(archivo.read_text(encoding="utf-8"))):
                if isinstance(nodo, ast.Call):
                    nombre = getattr(nodo.func, "attr", getattr(nodo.func, "id", ""))
                    if nombre in ("pkexec_path", "inline_command"):
                        fuera.append(f"{archivo.relative_to(paquete)}:{nodo.lineno} {nombre}")
        self.assertEqual(fuera, [])


class TestALineTooLong(unittest.TestCase):
    """The helper runs as root: a line with no end must not be held whole in
    its memory. It read the line and checked its size afterwards."""

    def _run(self, data: bytes):
        import contextlib
        import io
        import tracemalloc
        entrada = io.TextIOWrapper(io.BytesIO(data), encoding="utf-8")
        salida = io.StringIO()
        tracemalloc.start()
        try:
            with mock.patch.object(helper.sys, "stdin", entrada), \
                    mock.patch.object(helper.os, "geteuid", return_value=0), \
                    contextlib.redirect_stdout(salida):
                helper.main()
            pico = tracemalloc.get_traced_memory()[1]
        finally:
            tracemalloc.stop()
        return [json.loads(l) for l in salida.getvalue().splitlines()], pico

    def test_it_is_refused_without_holding_it(self):
        enorme = b"x" * (20 * 1024 * 1024)
        respuestas, pico = self._run(enorme + b"\n" + b'{"action": "ping"}\n')
        self.assertEqual(respuestas[0]["error"], "bad_request")
        self.assertLess(pico, 2 * 1024 * 1024, "the line was held whole")
        # And the next request still goes.
        self.assertTrue(respuestas[1]["ok"])

    def test_one_with_no_end_at_all(self):
        respuestas, pico = self._run(b"y" * (5 * 1024 * 1024))
        self.assertEqual([r["error"] for r in respuestas], ["bad_request"])
        self.assertLess(pico, 2 * 1024 * 1024)


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
    """Lo que hace el proveedor sin ser root, que es el caso normal.

    Hay que decírselo: `collect()` empieza preguntando `already_root()` y, si
    dice que sí, lee la tabla DMI él mismo y el cliente falso no llega a usarse
    nunca. Ejecutada como root —el CI corre así— la clase entera medía otra
    cosa: `Need.HARDWARE` donde estas pruebas esperan `Need.ROOT`, y el
    proveedor sin marcar como conectado porque no había a quién conectarse. El
    camino de root tiene su propio test y ahí se pide expresamente.
    """

    TABLA = _memory_array(slots=2) + _memory_device() + _empty_slot() + _end()

    def setUp(self):
        parche = mock.patch(
            "silux.providers.privileged_memory.already_root", return_value=False)
        parche.start()
        self.addCleanup(parche.stop)

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
        # Pisa el parche de setUp: aquí el euid que interesa es el contrario, y
        # tampoco se lee de él —la tabla y el permiso son los dos fingidos—.
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
            self.assertEqual(helper._pmu_field("x", "event"), 8)
        self.assertEqual(helper._pmu_field("x", "config"), 0)

    def test_un_formato_que_no_apunta_a_config_se_descarta(self):
        with mock.patch("silux.privileged.helper.open",
                        mock.mock_open(read_data="config1:0-7")):
            self.assertIsNone(helper._pmu_field("x", "event"))

    def test_a_memory_controllers_events_of_two_fields(self):
        # The LOQ's free-running counters, as its kernel publishes them:
        # «event=0xff,umask=0x20» over «config:0-7» and «config:8-15».
        devices = (pathlib.Path(__file__).parent / "fixtures" / "equipos" / "i5-12450h"
                   / "sys" / "bus" / "event_source" / "devices")
        with mock.patch.object(helper, "PMU_ROOT", str(devices)):
            self.assertEqual(helper._pmu_config("uncore_imc_free_running_0", "data_read"),
                             0xFF | 0x20 << 8)
            self.assertEqual(helper._pmu_config("uncore_imc_free_running_1", "data_write"),
                             0xFF | 0x30 << 8)
            # perf's own reading of that line: the same number.
            self.assertEqual(_as_perf(devices / "uncore_imc_free_running_0", "data_total"),
                             helper._pmu_config("uncore_imc_free_running_0", "data_total"))

    def test_what_it_does_not_take(self):
        formats = {"event": "config:0-7", "umask": "config:8-15", "edge": "config:18",
                   "split": "config:8-15,32-35", "other": "config1:0-7"}

        def fake_open(path, *args, **kwargs):
            name = pathlib.Path(path).name
            if "/events/" in str(path):
                return io.StringIO(events[name])
            if name in formats:
                return io.StringIO(formats[name])
            raise FileNotFoundError(path)

        events = {"ok": "event=0x04,umask=0x01", "one_bit": "event=0x04,edge=1",
                  "too_wide": "event=0x100", "asks": "event=0x04,umask=?",
                  "split": "event=0x04,split=0x01", "other": "event=0x04,other=0x01",
                  "unknown": "event=0x04,cmask=0x01", "flag": "event=0x04,edge"}
        with mock.patch("silux.privileged.helper.open", fake_open):
            self.assertEqual(helper._pmu_config("x", "ok"), 0x0104)
            self.assertEqual(helper._pmu_config("x", "one_bit"), 0x04 | 1 << 18)
            for name in ("too_wide", "asks", "split", "other", "unknown", "flag"):
                with self.subTest(event=name):
                    self.assertIsNone(helper._pmu_config("x", name))

    def test_sin_privilegios_falla_diciendo_por_qué(self):
        respuesta = helper.handle({"action": protocol.ACTION_GPU_PMU})
        self.assertIn("ok", respuesta)
        if not respuesta["ok"]:
            self.assertEqual(respuesta["error"], "unsupported")
            self.assertTrue(respuesta["message"])


def _as_perf(pmu: pathlib.Path, event: str) -> int:
    """How perf turns an event line into `config` (tools/perf/util/pmu.c):
    each term's value shifted to the first bit of its format, a field at a
    time. Written apart from the helper's, to check it against."""
    config = 0
    for term in (pmu / "events" / event).read_text().strip().split(","):
        name, value = term.split("=")
        spec = (pmu / "format" / name).read_text().strip()
        first = int(spec.split(":")[1].split("-")[0])
        config += int(value, 16) * 2 ** first
    return config


class TestInstaladorDelAyudante(unittest.TestCase):
    """El instalador que deja de pedir la contraseña en cada arranque.

    No hace falta root para probarlo: se le cambian las rutas de destino por
    unas del directorio temporal.
    """

    def setUp(self):
        import tempfile
        from silux.privileged import instalar

        self.modulo = instalar
        self._tmp = tempfile.TemporaryDirectory()
        raiz = pathlib.Path(self._tmp.name)
        self.destino = raiz / "libexec" / "silux" / "silux-helper"
        self.politica = raiz / "actions" / "org.silux.helper.policy"
        self.politica.parent.mkdir(parents=True)

        parches = [
            mock.patch.object(instalar, "TARGET", self.destino),
            mock.patch.object(instalar, "POLICY", self.politica),
            # chown pide root; lo que importa aquí es el resto. And the folders
            # have to be root's: here, whoever runs the tests.
            mock.patch.object(instalar.os, "chown", lambda *a: None),
            mock.patch.object(instalar.os, "fchown", lambda *a: None),
            mock.patch.object(instalar, "OWNER", os.getuid()),
        ]
        for parche in parches:
            parche.start()
            self.addCleanup(parche.stop)
        self.addCleanup(self._tmp.cleanup)

    def instalar(self, cuerpo: str = None) -> None:
        """El instalador informa por pantalla; aquí solo estorba.

        Recibe el texto del ayudante y no su ruta: aceptar una ruta es aceptar
        que otro proceso decida qué se instala como root, y por eso la bandera
        que la pasaba ya no existe.
        """
        import contextlib
        import io

        if cuerpo is None:
            cuerpo = self.modulo.from_package()
        with contextlib.redirect_stdout(io.StringIO()):
            self.modulo.install(cuerpo)

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
        interprete, *banderas = primera[2:].split()
        self.assertTrue(os.path.exists(interprete), primera)
        # Isolated: no PYTHONPATH, PYTHONSTARTUP or user site-packages as root.
        self.assertEqual(banderas, ["-I"])

    def test_not_into_a_folder_someone_else_can_change(self):
        self.destino.parent.mkdir(parents=True)
        with mock.patch.object(self.modulo, "OWNER", os.getuid() + 1), \
             self.assertRaises(SystemExit):
            self.instalar()
        self.assertFalse(self.destino.exists())

    def test_never_writes_through_a_link(self):
        """A link left where the helper goes made root write the helper over
        whatever it pointed to."""
        victima = pathlib.Path(self._tmp.name) / "victima"
        victima.write_text("intacta\n")
        self.destino.parent.mkdir(parents=True)
        self.destino.symlink_to(victima)
        self.politica.symlink_to(victima)
        self.instalar()
        self.assertEqual(victima.read_text(), "intacta\n")
        for ruta in (self.destino, self.politica):
            with self.subTest(ruta=ruta.name):
                self.assertFalse(ruta.is_symlink())
        self.assertEqual(self.destino.stat().st_mode & 0o777, 0o755)
        self.assertEqual(self.politica.stat().st_mode & 0o777, 0o644)

    def test_la_politica_apunta_al_ayudante_y_no_al_interprete(self):
        """Si la acción colgara de `python3`, la autorización valdría para
        cualquier script de Python de la máquina."""
        self.instalar()
        texto = self.politica.read_text(encoding="utf-8")
        self.assertIn(f">{self.destino}<", texto)
        self.assertNotIn("python3<", texto)

    def test_no_se_pide_la_contrasena_para_siempre(self):
        """`yes` dejaría la puerta abierta a cualquier proceso del usuario.
        `auth_admin_keep` la pide al dar permisos y la recuerda unos minutos
        para ese proceso (docs/privilegios.md)."""
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
            self.modulo.uninstall()
        self.assertFalse(self.destino.exists())
        self.assertFalse(self.politica.exists())

    def test_el_cuerpo_del_ayudante_llega_entero(self):
        """Se copia, no se enlaza: el original vive donde el usuario escribe."""
        self.instalar()
        original = self.modulo.SOURCE.read_text(encoding="utf-8")
        copia = self.destino.read_text(encoding="utf-8")
        cuerpo = original.split("\n", 1)[1]
        self.assertEqual(copia.split("\n", 1)[1], cuerpo)


class TestElInstaladorViajaConElPaquete(unittest.TestCase):
    """Vive dentro de `silux/` y no en `tools/`, y eso no es cosmético.

    El AppImage copia `silux/` entero y no copia `tools/`, así que con el
    instalador allí el botón de la interfaz se quedaba sin nada que lanzar en
    la única forma del programa que se reparte.
    """

    def test_esta_dentro_del_paquete(self):
        from silux.privileged import instalar

        ruta = pathlib.Path(instalar.__file__).resolve()
        paquete = pathlib.Path(__file__).resolve().parent.parent / "silux"
        self.assertTrue(ruta.is_relative_to(paquete), ruta)

    def test_no_importa_nada_de_silux(self):
        """Se copia como archivo suelto fuera del punto de montaje del
        AppImage, donde el resto del paquete no está."""
        from silux.privileged import instalar

        fuente = pathlib.Path(instalar.__file__).read_text(encoding="utf-8")
        for linea in fuente.splitlines():
            limpia = linea.strip()
            if limpia.startswith(("import ", "from ")):
                self.assertNotIn("silux", limpia, linea)
                self.assertFalse(limpia.startswith("from ."), linea)

    def test_encuentra_el_ayudante_a_su_lado(self):
        from silux.privileged import instalar

        self.assertTrue(instalar.SOURCE.is_file(), instalar.SOURCE)


class TestLoadingAModule(unittest.TestCase):
    """`load_module` runs as root: what matters is where the module's name
    comes from. A helper that loads whatever it is told loads any module on
    the system."""

    def _run(self, name, loaded_before=False, loaded_after=True, returncode=0, stderr=""):
        seen = {"before": loaded_before, "after": loaded_after}

        def isdir(path):
            return seen["after"] if run.called else seen["before"]

        with mock.patch.object(helper.subprocess, "run") as run, \
             mock.patch.object(helper.os.path, "isdir", side_effect=isdir), \
             mock.patch.object(helper.os.path, "isfile", side_effect=lambda p: p == "/usr/sbin/modprobe"), \
             mock.patch.object(helper.os, "access", return_value=True):
            run.return_value = mock.Mock(returncode=returncode, stderr=stderr)
            reply = helper.handle({"action": protocol.ACTION_LOAD_MODULE, "module": name})
        return reply, run

    def test_the_two_lists_match(self):
        self.assertEqual(set(protocol.MODULES_ALLOWED), set(helper.MODULES_ALLOWED))

    def test_only_sensor_readers(self):
        self.assertEqual(set(helper.MODULES_ALLOWED), {"drivetemp", "spd5118", "ee1004", "at24"})

    def test_any_other_name_is_refused_before_running_anything(self):
        for name in ("nvidia", "kvm", "i2c-dev", "nct6775", "msr", "drivetemp; rm -rf /",
                     "../../etc/passwd", "-drivetemp", "DRIVETEMP", "", None, 5, ["drivetemp"]):
            with self.subTest(name=name):
                reply, run = self._run(name)
                self.assertFalse(reply["ok"])
                self.assertEqual(reply["error"], "forbidden")
                run.assert_not_called()

    def test_modprobe_by_its_path_with_the_blacklist_and_a_fixed_environment(self):
        reply, run = self._run("drivetemp")
        self.assertTrue(reply["ok"])
        self.assertEqual(run.call_args.args[0], ["/usr/sbin/modprobe", "-b", "--", "drivetemp"])
        self.assertEqual(run.call_args.kwargs["env"], helper.MODPROBE_ENV)
        self.assertNotIn("shell", run.call_args.kwargs)
        self.assertTrue(all(path.startswith("/") for path in helper.MODPROBE))

    def test_one_already_loaded_runs_nothing(self):
        reply, run = self._run("spd5118", loaded_before=True)
        self.assertTrue(reply["ok"])
        run.assert_not_called()

    def test_a_blacklisted_module_is_said(self):
        # modprobe -b answers 0 and loads nothing.
        reply, _run = self._run("drivetemp", loaded_after=False)
        self.assertFalse(reply["ok"])
        self.assertEqual(reply["error"], "blacklisted")

    def test_modprobe_failing_says_why(self):
        reply, _run = self._run("ee1004", loaded_after=False, returncode=1,
                                stderr="modprobe: FATAL: Module ee1004 not found.\n")
        self.assertFalse(reply["ok"])
        self.assertIn("not found", reply["message"])


class TestLaVersionDelAyudante(unittest.TestCase):
    """Instalar los permisos permanentes deja una copia congelada.

    Nadie la actualiza, así que quien los diera hace meses seguiría hablando
    con aquel ayudante. Lo que este programa le pidiera de nuevo saldría
    rechazado con un mensaje que no menciona la causa: pasó al añadir los
    registros del voltaje del núcleo, y el usuario veía «registros no
    permitidos» sin ninguna pista de que el ayudante fuera viejo.
    """

    def test_las_dos_versiones_van_juntas(self):
        from silux.privileged import helper, protocol
        self.assertEqual(helper.VERSION, protocol.HELPER_VERSION)

    def test_un_ayudante_viejo_se_deja_de_lado(self):
        from silux.privileged import client
        c = client.PrivilegedClient()
        with mock.patch.object(client.PrivilegedClient, "installed",
                               return_value=True), \
             mock.patch.object(client.PrivilegedClient, "up_to_date",
                               return_value=True):
            self.assertEqual(c._command()[1], str(client.INSTALLED_HELPER))
            c._skip_installed = True
            # Sin él, el ayudante viaja por argv. Se mira el programa que se
            # ejecuta y no la orden entera: la fuente del ayudante va dentro y
            # menciona esa ruta en un comentario, así que buscar la cadena
            # suelta encontraba el comentario y no el ejecutable.
            self.assertNotEqual(c._command()[1], str(client.INSTALLED_HELPER))
            self.assertEqual(c._command()[1], client.interpreter())


class TestElAyudanteDesfasado(unittest.TestCase):
    """Un ayudante instalado no se actualiza solo, y eso es un problema de
    seguridad y no de comodidad.

    El de esta máquina es del 28 de agosto: anterior a los tres arreglos de
    escalada de privilegios del 31. Mientras siguiera usándose, el programa
    hablaría con un ayudante instalado por un camino que no garantizaba qué se
    instalaba, y el archivo seguiría en /usr/local/libexec siendo de root con
    su acción de polkit apuntándole.
    """

    def test_se_compara_el_contenido_y_no_un_numero_de_version(self):
        """Un número hay que acordarse de subirlo; los arreglos que no cambian
        el contrato no lo tocan. El contenido no se olvida de cambiar."""
        from silux.privileged import client
        import inspect
        fuente = inspect.getsource(client.PrivilegedClient.up_to_date)
        self.assertIn("read_text", fuente)
        self.assertNotIn("VERSION", fuente)

    def test_el_shebang_no_cuenta_como_diferencia(self):
        """El instalador lo cambia por el intérprete clavado, así que dos
        copias del mismo ayudante difieren siempre en esa línea."""
        from silux.privileged.client import PrivilegedClient as C
        self.assertEqual(C._body("#!/usr/bin/python3\nhola"),
                         C._body("#!/usr/bin/env python3\nhola"))

    def test_uno_desfasado_no_se_ejecuta(self):
        from silux.privileged import client
        c = client.PrivilegedClient()
        with mock.patch.object(client.PrivilegedClient, "installed",
                               return_value=True), \
             mock.patch.object(client.PrivilegedClient, "up_to_date",
                               return_value=False):
            self.assertNotEqual(c._command()[1], str(client.INSTALLED_HELPER))

    def test_y_se_pide_sustituirlo_en_vez_de_solo_ignorarlo(self):
        """Ignorarlo deja el archivo en el sistema. Hay que reemplazarlo."""
        from silux.privileged import client
        with mock.patch.object(client.PrivilegedClient, "installed",
                               return_value=True), \
             mock.patch.object(client.PrivilegedClient, "up_to_date",
                               return_value=False):
            self.assertTrue(client.PrivilegedClient.needs_reinstall())

    def _instalados(self, carpeta, regla: str):
        """El ayudante de este programa y una regla, puestos donde se miran."""
        import pathlib
        from silux.privileged import client
        binario = pathlib.Path(carpeta) / "silux-helper"
        binario.write_text("#!/usr/bin/python3\n" + client.PrivilegedClient._body(
            client.HELPER.read_text(encoding="utf-8")), encoding="utf-8")
        binario.chmod(0o755)
        politica = pathlib.Path(carpeta) / "org.silux.helper.policy"
        politica.write_text(regla, encoding="utf-8")
        return (mock.patch.object(client, "INSTALLED_HELPER", binario),
                mock.patch.object(client, "INSTALLED_POLICY", politica))

    def test_una_regla_con_el_texto_viejo_pide_sustituirlo(self):
        """La regla es lo que dice la ventana de la contraseña. La que se
        instalaba hasta el 19 de noviembre nombraba solo la memoria y los
        discos; quien la tenga puesta tiene que enterarse de que hay otra."""
        import tempfile
        from silux.privileged import client, instalar
        vieja = instalar.policy().replace(
            instalar.MESSAGES["es"],
            "Se necesita autorización para leer los módulos de memoria y el "
            "diagnóstico de los discos")
        with tempfile.TemporaryDirectory() as carpeta:
            uno, otro = self._instalados(carpeta, vieja)
            with uno, otro:
                self.assertTrue(client.PrivilegedClient.installed())
                self.assertFalse(client.PrivilegedClient.up_to_date())
                self.assertTrue(client.PrivilegedClient.needs_reinstall())

    def test_con_la_regla_de_ahora_esta_al_dia(self):
        import tempfile
        from silux.privileged import client, instalar
        with tempfile.TemporaryDirectory() as carpeta:
            uno, otro = self._instalados(carpeta, instalar.policy())
            with uno, otro:
                self.assertTrue(client.PrivilegedClient.up_to_date())

    def test_el_que_esta_al_dia_se_sigue_usando(self):
        from silux.privileged import client
        c = client.PrivilegedClient()
        with mock.patch.object(client.PrivilegedClient, "installed",
                               return_value=True), \
             mock.patch.object(client.PrivilegedClient, "up_to_date",
                               return_value=True):
            self.assertEqual(c._command()[1], str(client.INSTALLED_HELPER))
            self.assertFalse(client.PrivilegedClient.needs_reinstall())


class TestElTextoDeLaVentanaDeLaContrasena(unittest.TestCase):
    """Lo que dice polkit con la regla puesta.

    Lo escribe root, que no puede leer dentro del AppImage del usuario, así
    que el texto va copiado en `instalar.py`. Copiado, se separa de la
    interfaz en cuanto alguien cambia uno de los dos: aquí se comparan.
    """

    def test_es_el_de_la_interfaz_en_cada_idioma(self):
        import json
        import pathlib
        from silux.privileged import instalar
        carpeta = pathlib.Path(instalar.__file__).resolve().parent.parent / "db" / "lang"
        for idioma, texto in instalar.MESSAGES.items():
            with self.subTest(idioma=idioma):
                tabla = json.loads((carpeta / f"{idioma}.json").read_text(encoding="utf-8"))
                self.assertEqual(texto, tabla["perm.polkit.message"])

    def test_la_regla_lleva_los_dos_y_el_ingles_marcado(self):
        from silux.privileged import instalar
        regla = instalar.policy()
        self.assertIn(f"<message>{instalar.MESSAGES['es']}</message>", regla)
        self.assertIn(f'<message xml:lang="en">{instalar.MESSAGES["en"]}</message>', regla)

    def test_nombra_todo_lo_que_abre_el_permiso(self):
        # SMBIOS (memoria), SMART (discos), MSR (voltaje), RAPL (consumo) y
        # los contadores del PMU (el uso de la gráfica).
        from silux.privileged import instalar
        for palabra in ("memoria", "discos", "voltaje", "consumo", "uso de la gráfica",
                        "Solo lee"):
            self.assertIn(palabra, instalar.MESSAGES["es"])
