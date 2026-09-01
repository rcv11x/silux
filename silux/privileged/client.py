"""El lado sin privilegios: lanza el ayudante y habla con él.

Nunca se llama desde el hilo de la interfaz. `pkexec` abre un diálogo de
autenticación y bloquea hasta que el usuario responde; hacerlo en el hilo de
Qt congelaría la ventana con el diálogo abierto delante, que es la peor
combinación posible.

El proceso se deja vivo mientras dure la sesión. Volver a pedir la contraseña
en cada muestreo sería inaceptable, y mantener una tubería abierta con un
proceso que solo sabe hacer dos lecturas es poco riesgo a cambio de mucha
comodidad.
"""

from __future__ import annotations

import base64
import json
import os
import pathlib
import select
import shutil
import subprocess
import sys
from typing import Any, NamedTuple, Optional

from . import protocol
from .protocol import (ACTION_GPU_PMU, ACTION_IMC, ACTION_MSR, ACTION_PING,
                       ACTION_RAPL, ACTION_SMART, ACTION_SMBIOS, MAX_MESSAGE)

# Intérpretes del sistema con los que lanzar el ayudante cuando el del programa
# no sirve. Al ayudante le basta la biblioteca estándar, así que vale cualquiera.
SYSTEM_PYTHON = ("/usr/bin/python3", "/bin/python3", "/usr/local/bin/python3")


def _cache_dir() -> pathlib.Path:
    """La carpeta de caché del programa, siguiendo la convención del sistema."""
    base = os.environ.get("XDG_CACHE_HOME") or (pathlib.Path.home() / ".cache")
    return pathlib.Path(base) / "silux"


# Lo que se le pasa a `python3 -c` para ejecutar un guion que no está en
# ningún archivo. Recibe por argv el nombre con el que compilarlo y su fuente
# entera, y deja en `sys.argv` lo que venga detrás, que es lo que espera quien
# se ejecute.
#
# El nombre y el `linecache` no son adorno: sin ellos el traceback de un fallo
# dice «File "<string>", line 40» y se queda sin el texto de la línea, y lo
# primero que se le pide a quien reporta algo es justamente eso. Con ellos sale
# «File "silux-helper.py", line 40» con su línea debajo, igual que si viniera
# de un archivo.
#
# El `excepthook` es la otra mitad y hace falta hasta Python 3.12. Quien pinta
# una excepción que nadie atrapa es, hasta esa versión, el escritor en C, y ese
# busca el código abriendo el archivo por su nombre: como aquí no hay archivo,
# se queda sin línea aunque `linecache` la tenga. El módulo `traceback` sí lo
# consulta. En 3.13 el camino por defecto ya pasa por ahí y esto sobra, pero el
# suelo declarado es 3.10 y es el Python que va dentro del AppImage.
# `SystemExit` no pasa por el hook, así que los guiones que avisan con
# `raise SystemExit("...")` siguen sacando su mensaje a secas.
ARRANQUE = """\
import linecache, sys, traceback
_nombre, _fuente = sys.argv[1], sys.argv[2]
linecache.cache[_nombre] = (len(_fuente), None, _fuente.splitlines(True), _nombre)
sys.argv = [_nombre] + sys.argv[3:]
sys.excepthook = lambda *fallo: traceback.print_exception(*fallo)
exec(compile(_fuente, _nombre, "exec"), {"__name__": "__main__", "__file__": _nombre})
"""


def en_linea(interprete: str, nombre: str, fuente: str,
             *argumentos: str) -> list[str]:
    """La orden que ejecuta `fuente` sin que exista como archivo.

    Es lo que evita que en la línea de `pkexec` aparezca una ruta que el
    usuario pueda reescribir. Lo que va por `argv` queda fijado por el
    `exec()` y nadie lo puede cambiar después; un archivo, sí.
    """
    return [interprete, "-c", ARRANQUE, nombre, fuente, *argumentos]


# Lo que dejaban en la caché las versiones que copiaban los guiones ahí para
# lanzarlos con pkexec. Ya no las escribe nadie y no las ejecuta nadie, pero
# eran la superficie del agujero y no hay motivo para dejarlas en el disco de
# quien actualice.
COPIAS_VIEJAS = ("helper.py", "instalar.py", "cargar_modulo.py")


def limpiar_copias_viejas() -> None:
    """Borra los guiones que las versiones anteriores dejaban en la caché."""
    carpeta = _cache_dir()
    for nombre in COPIAS_VIEJAS:
        try:
            (carpeta / nombre).unlink()
        except OSError:
            pass
    try:
        carpeta.rmdir()          # solo si no queda nada más dentro
    except OSError:
        pass


def interprete() -> str:
    """Con qué Python se lanza por pkexec un guion que va por `argv`.

    Desde un AppImage el de dentro no vale, por dos motivos distintos y los dos
    insalvables:

    * El punto de montaje va con `nosuid`, y pkexec se niega a ejecutar nada de
      un sistema de archivos así. Deniega antes de preguntar, que es por lo que
      no llegaba a salir el diálogo de la contraseña.
    * El montaje es de FUSE y pertenece al usuario, así que **root ni siquiera
      puede leer dentro**.

    Así que se usa el del sistema, al que le basta la biblioteca estándar.
    Fuera del AppImage vale el nuestro, pero solo si no lo puede reescribir el
    usuario: el de un entorno virtual suyo lo es, y entonces la ruta que recibe
    pkexec vuelve a ser sustituible, que es justo lo que se está quitando de en
    medio.
    """
    for ruta in SYSTEM_PYTHON:
        if os.path.exists(ruta):
            return ruta
    if (not PrivilegedClient.empaquetado()
            and not escribible_por_el_usuario(sys.executable)):
        return sys.executable
    raise HelperUnavailable(
        "No hay ningún Python del sistema con el que lanzar el ayudante."
    )


def escribible_por_el_usuario(ruta) -> bool:
    """Si este usuario puede cambiar lo que hay en esa ruta.

    Mira también las carpetas de encima: poder escribir el directorio permite
    sustituir el archivo entero aunque el archivo no se deje tocar.
    """
    if already_root():
        # Como root todo es escribible y la pregunta no significa nada; y si
        # somos root no hay pkexec de por medio que proteger.
        return False
    camino = pathlib.Path(ruta).resolve()
    if camino.exists() and os.access(camino, os.W_OK):
        return True
    return any(os.access(padre, os.W_OK)
               for padre in camino.parents if padre.exists())


HELPER = pathlib.Path(__file__).resolve().parent / "helper.py"

# El ayudante instalado en el sistema, si alguien pulsó el botón de permisos
# permanentes. Se prefiere al del repositorio porque trae su propia acción de
# polkit: la contraseña se pide una vez por sesión en vez de en cada arranque.
# Lo instala `silux/privileged/instalar.py`, que es también quien explica por qué
# tiene que vivir en un sitio que el usuario no pueda escribir.
HELPER_INSTALADO = pathlib.Path("/usr/local/libexec/silux/silux-helper")
# Su acción de polkit. Sin ella el ayudante instalado sigue ejecutándose,
# pero por la acción genérica: contraseña en cada arranque en vez de una
# por sesión. Las dos rutas las escribe `instalar.py` y hay un test que
# vigila que no se separen de estas.
POLITICA_INSTALADA = pathlib.Path(
    "/usr/share/polkit-1/actions/org.silux.helper.policy")

DEFAULT_TIMEOUT = 15.0
# Autenticarse puede tardar lo que el usuario tarde en teclear.
CONNECT_TIMEOUT = 120.0


class HelperError(RuntimeError):
    """No se pudo hablar con el ayudante."""


class HelperUnavailable(HelperError):
    """Falta pkexec o el propio ayudante: no hay nada que intentar."""


class HelperDenied(HelperError):
    """El usuario canceló el diálogo o no está autorizado."""


class PrivilegedClient:
    def __init__(self) -> None:
        self._process: Optional[subprocess.Popen] = None
        self._last_error: Optional[str] = None
        # Se enciende cuando el ayudante instalado resulta ser de una versión
        # anterior: a partir de ahí se usa el que viaja por argv, que siempre
        # es el de este programa. Cuesta una contraseña por arranque, que es
        # mejor que una función que no va y no dice por qué.
        self._sin_el_instalado = False

    # -- estado -------------------------------------------------------------

    @staticmethod
    def supported() -> bool:
        return bool(shutil.which("pkexec")) and HELPER.is_file()

    @staticmethod
    def empaquetado() -> bool:
        """Si el programa corre desde dentro de un AppImage."""
        return bool(os.environ.get("APPIMAGE")) or "/.mount_" in sys.executable

    def connected(self) -> bool:
        return self._process is not None and self._process.poll() is None

    @property
    def last_error(self) -> Optional[str]:
        return self._last_error

    # -- ciclo de vida ------------------------------------------------------

    def connect(self) -> None:
        """Pide autorización y deja el ayudante escuchando. Bloquea."""
        if self.connected():
            return
        # Aquí es donde las versiones anteriores escribían la copia, así que
        # aquí es donde toca recogerla.
        limpiar_copias_viejas()
        if not self.supported():
            raise HelperUnavailable(
                "Falta pkexec. Se instala con el paquete polkit de la distribución."
            )

        orden = self._orden()
        try:
            process = subprocess.Popen(
                orden,
                stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL, text=True, bufsize=1,
            )
        except OSError as exc:
            raise HelperUnavailable(f"no se pudo lanzar pkexec: {exc}") from exc

        self._process = process
        try:
            reply = self.request({"action": ACTION_PING}, timeout=CONNECT_TIMEOUT)
        except HelperError:
            code = process.poll()
            self.close()
            # 126 = el usuario canceló el diálogo; 127 = no autorizado.
            if code in (126, 127):
                raise HelperDenied("Autorización cancelada o denegada.") from None
            if code == 1 and self.empaquetado():
                raise HelperUnavailable(
                    "pkexec no pudo lanzar el ayudante desde el AppImage."
                ) from None
            raise

        if not reply.get("ok") or reply.get("uid") != 0:
            self.close()
            raise HelperError("el ayudante no arrancó con privilegios")

        # Y que sea el de esta versión. Instalar los permisos permanentes deja
        # una copia en /usr/local/libexec que no la actualiza nadie: quien los
        # diera hace meses seguiría hablando con aquel ayudante, y lo que este
        # programa le pidiera de nuevo —una acción, un registro— saldría
        # rechazado con un mensaje que no menciona la causa. Se cayó justo así
        # al añadir los registros del voltaje del núcleo.
        if reply.get("version", 0) < protocol.VERSION_REQUERIDA and self.instalado():
            self.close()
            self._sin_el_instalado = True
            self.connect()

    @staticmethod
    def instalado() -> bool:
        """Si el ayudante del sistema está puesto, con su acción de polkit.

        La política cuenta: es lo que hace que la contraseña se pida una vez
        por sesión y no en cada arranque, que es el motivo entero de instalar
        nada. Sin ella el ayudante se ejecuta igual, pero el botón de permisos
        permanentes se escondía diciendo que ya estaba hecho cuando faltaba la
        mitad. `instalar.instalado()` ya miraba las dos.
        """
        return (HELPER_INSTALADO.is_file()
                and os.access(HELPER_INSTALADO, os.X_OK)
                and POLITICA_INSTALADA.is_file())

    @staticmethod
    def _cuerpo(texto: str) -> str:
        """El ayudante sin su primera línea.

        El instalador cambia el shebang por el intérprete clavado, así que dos
        copias del mismo ayudante difieren siempre en esa línea y solo en esa.
        """
        return texto.split("\n", 1)[1] if texto.startswith("#!") else texto

    @classmethod
    def al_dia(cls) -> bool:
        """Si el ayudante instalado es el mismo que trae este programa.

        Se compara el contenido y no un número de versión, y la diferencia
        importa: un número hay que acordarse de subirlo, y los arreglos que no
        cambian el contrato —los de seguridad, sobre todo— no lo tocan. El
        contenido no se olvida de cambiar.
        """
        try:
            instalado = HELPER_INSTALADO.read_text(encoding="utf-8")
            actual = HELPER.read_text(encoding="utf-8")
        except OSError:
            return False
        return cls._cuerpo(instalado) == cls._cuerpo(actual)

    @classmethod
    def necesita_reinstalar(cls) -> bool:
        """Hay un ayudante puesto y no es el de este programa.

        Lo que hay que hacer entonces no es solo dejar de usarlo: hay que
        sustituirlo. El archivo se queda en /usr/local/libexec siendo de root y
        con su acción de polkit apuntándole, así que sigue siendo ejecutable
        con privilegios aunque este programa lo ignore. Y si se instaló con una
        versión anterior a los arreglos de escalada, no hay ninguna garantía de
        que lo que hay ahí sea lo que se quiso instalar.
        """
        return cls.instalado() and not cls.al_dia()

    def _orden(self) -> list[str]:
        """Lo que se le pasa a pkexec, en el orden de preferencia que toca.

        El ayudante instalado va solo, sin intérprete delante: pkexec asocia la
        autorización a la ruta del programa que ejecuta, así que con `python3`
        por delante la acción quedaría colgada del intérprete y valdría para
        cualquier script de la máquina.

        Y si no está instalado, el ayudante viaja por `argv` y no como archivo.
        **En esta lista no puede aparecer ninguna ruta que el usuario pueda
        reescribir**, y hay un test que lo comprueba en las tres órdenes de
        pkexec que construye el programa.
        """
        # Solo se usa el instalado si es exactamente el de este programa.
        if (self.instalado() and self.al_dia()
                and not self._sin_el_instalado):
            return ["pkexec", str(HELPER_INSTALADO)]
        return ["pkexec", *en_linea(interprete(), "silux-helper.py",
                                    self._fuente_del_ayudante())]

    @staticmethod
    def _fuente_del_ayudante() -> str:
        try:
            return HELPER.read_text(encoding="utf-8")
        except OSError as exc:
            raise HelperUnavailable(
                f"no se pudo leer el ayudante: {exc}") from exc


    def close(self) -> None:
        process, self._process = self._process, None
        if process is None:
            return
        try:
            if process.stdin:
                process.stdin.close()
            process.wait(timeout=3)
        except (OSError, subprocess.TimeoutExpired):
            process.kill()

    # -- peticiones ---------------------------------------------------------

    def request(self, payload: dict, timeout: float = DEFAULT_TIMEOUT) -> dict:
        process = self._process
        if process is None or process.poll() is not None:
            raise HelperError("el ayudante no está en marcha")

        try:
            process.stdin.write(json.dumps(payload) + "\n")
            process.stdin.flush()
        except (OSError, ValueError) as exc:
            self.close()
            raise HelperError(f"se cortó la comunicación: {exc}") from exc

        ready, _, _ = select.select([process.stdout], [], [], timeout)
        if not ready:
            self.close()
            raise HelperError("el ayudante no respondió a tiempo")

        line = process.stdout.readline()
        if not line:
            self.close()
            raise HelperError("el ayudante se cerró sin responder")
        if len(line) > MAX_MESSAGE:
            self.close()
            raise HelperError("respuesta desmesurada")

        try:
            reply = json.loads(line)
        except ValueError as exc:
            raise HelperError(f"respuesta ilegible: {exc}") from exc
        if not isinstance(reply, dict):
            raise HelperError("la respuesta no es un objeto")
        return reply

    # -- operaciones --------------------------------------------------------

    def smbios_table(self) -> bytes:
        reply = self.request({"action": ACTION_SMBIOS})
        if not reply.get("ok"):
            self._last_error = reply.get("message")
            raise HelperError(reply.get("message", "no se pudo leer SMBIOS"))
        return base64.b64decode(reply.get("table", ""))

    def read_msr(self, cpu: int, registers: list[int]) -> dict[int, int]:
        reply = self.request({"action": ACTION_MSR, "cpu": cpu, "registers": registers})
        if not reply.get("ok"):
            self._last_error = reply.get("message")
            raise HelperError(reply.get("message", "no se pudieron leer los MSR"))
        return {int(k): v for k, v in reply.get("values", {}).items()}


    def read_smart(self, device: str) -> tuple[bytes, str]:
        """Los datos de diagnóstico de un disco, y de qué familia son.

        Devuelve los bytes sin tocar: interpretarlos es cosa de `silux.smart`,
        que corre sin privilegios.
        """
        reply = self.request({"action": ACTION_SMART, "device": device})
        if not reply.get("ok"):
            self._last_error = reply.get("message")
            raise HelperError(reply.get("message", "no se pudo leer el diagnóstico"))
        return base64.b64decode(reply.get("data", "")), reply.get("kind", "")

    def rapl(self) -> dict[str, int]:
        """Los contadores de energía en microjulios, por zona.

        En crudo: los vatios son la derivada y eso lo calcula quien llama, que
        es quien guarda la lectura anterior. Hace falta porque desde el kernel
        5.10 `energy_uj` no se lee sin privilegios, y en las máquinas donde
        pasa —AMD sobre todo— el consumo del procesador salía en blanco aunque
        el usuario hubiera dado los permisos.
        """
        reply = self.request({"action": ACTION_RAPL})
        if not reply.get("ok"):
            self._last_error = reply.get("message")
            raise HelperError(reply.get("message", "no se pudo leer RAPL"))
        zonas = reply.get("zones")
        if not isinstance(zonas, dict):
            raise HelperError("el ayudante contestó algo que no encaja")
        return {str(k): int(v) for k, v in zonas.items() if isinstance(v, int)}

    def gpu_pmu(self) -> tuple[int, dict[str, dict[str, int]], dict[str, dict[str, float]]]:
        """Contadores de la gráfica, en crudo, con su reloj y sus escalas.

        Los de ocupación son nanosegundos acumulados y los de energía llevan
        la escala que publica el kernel. Restarlos y convertirlos en un
        porcentaje o en vatios es cosa de quien llama: el ayudante no
        interpreta nada.
        """
        reply = self.request({"action": ACTION_GPU_PMU})
        if not reply.get("ok"):
            self._last_error = reply.get("message")
            mensaje = reply.get("message", "no se pudo leer el PMU de la gráfica")
            if reply.get("error") == "unsupported":
                raise PmuUnsupported(mensaje)
            raise HelperError(mensaje)

        reloj = reply.get("monotonic_ns")
        motores = reply.get("engines")
        if not isinstance(reloj, int) or not isinstance(motores, dict):
            raise HelperError("el ayudante contestó algo que no encaja")
        limpio = {
            str(pmu): {str(e): v for e, v in eventos.items() if isinstance(v, int)}
            for pmu, eventos in motores.items() if isinstance(eventos, dict)
        }
        crudas = reply.get("scales")
        escalas = {
            str(pmu): {str(e): float(v) for e, v in valores.items()
                       if isinstance(v, (int, float))}
            for pmu, valores in (crudas or {}).items() if isinstance(valores, dict)
        }
        return reloj, limpio, escalas

    def imc(self) -> LecturaImc:
        """Cuánto tráfico lleva movido el controlador de memoria, en crudo.

        Igual que los de la gráfica: contadores que solo suben, con el factor
        y la unidad que publica el kernel al lado. Los bytes por segundo son
        la derivada y los calcula quien llama, que es quien guarda la lectura
        anterior.
        """
        reply = self.request({"action": ACTION_IMC})
        if not reply.get("ok"):
            self._last_error = reply.get("message")
            mensaje = reply.get("message", "no se pudo leer el controlador de memoria")
            if reply.get("error") == "unsupported":
                raise PmuUnsupported(mensaje)
            raise HelperError(mensaje)

        reloj = reply.get("monotonic_ns")
        contadores = reply.get("counters")
        if not isinstance(reloj, int) or not isinstance(contadores, dict):
            raise HelperError("el ayudante contestó algo que no encaja")
        limpio = {
            str(pmu): {str(e): v for e, v in eventos.items() if isinstance(v, int)}
            for pmu, eventos in contadores.items() if isinstance(eventos, dict)
        }
        escalas = {
            str(pmu): {str(e): float(v) for e, v in valores.items()
                       if isinstance(v, (int, float))}
            for pmu, valores in (reply.get("scales") or {}).items()
            if isinstance(valores, dict)
        }
        unidades = {
            str(pmu): {str(e): str(v) for e, v in valores.items() if isinstance(v, str)}
            for pmu, valores in (reply.get("units") or {}).items()
            if isinstance(valores, dict)
        }
        return LecturaImc(reloj, limpio, escalas, unidades,
                          bool(reply.get("truncated")))


class PmuUnsupported(HelperError):
    """Esta máquina no publica los contadores que se le pedían.

    No es un fallo ni un permiso que falte: es hardware que no los tiene. Sirve
    para que quien pregunta deje de hacerlo en cada muestreo, y para que el
    aviso salga en gris y no en ámbar.
    """


class LecturaImc(NamedTuple):
    """Lo que el ayudante devuelve del controlador de memoria, sin interpretar.

    `counters` son cuentas acumuladas desde que se abrió cada contador, y
    `scales` y `units` es lo que el kernel publica para convertirlas. Se
    guardan juntas porque separadas no significan nada: una cuenta sin su
    escala no es un tamaño.
    """

    monotonic_ns: int
    counters: dict[str, dict[str, int]]
    scales: dict[str, dict[str, float]]
    units: dict[str, dict[str, str]]
    truncated: bool


def already_root() -> bool:
    """Si el programa ya corre como root, no hace falta ningún ayudante."""
    return os.geteuid() == 0
