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
from typing import Any, Optional

# Intérpretes del sistema con los que lanzar el ayudante cuando el del programa
# no sirve. Al ayudante le basta la biblioteca estándar, así que vale cualquiera.
SYSTEM_PYTHON = ("/usr/bin/python3", "/bin/python3", "/usr/local/bin/python3")


def _cache_dir() -> pathlib.Path:
    """Donde dejar la copia del ayudante, siguiendo la convención del sistema."""
    base = os.environ.get("XDG_CACHE_HOME") or (pathlib.Path.home() / ".cache")
    return pathlib.Path(base) / "silux"

from .protocol import (ACTION_GPU_PMU, ACTION_MSR, ACTION_PING, ACTION_SMART,
                       ACTION_SMBIOS, MAX_MESSAGE)

HELPER = pathlib.Path(__file__).resolve().parent / "helper.py"
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
        if not self.supported():
            raise HelperUnavailable(
                "Falta pkexec. Se instala con el paquete polkit de la distribución."
            )

        interprete, ayudante = self._preparar()
        try:
            process = subprocess.Popen(
                ["pkexec", interprete, str(ayudante)],
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

    def _preparar(self) -> tuple[str, pathlib.Path]:
        """El intérprete y el ayudante que pkexec puede llegar a ejecutar.

        Desde un AppImage no valen los de dentro, por dos motivos distintos y
        los dos insalvables:

        * El punto de montaje va con `nosuid`, y pkexec se niega a ejecutar
          nada de un sistema de archivos así. Deniega antes de preguntar, que es
          por lo que no llegaba a salir el diálogo de la contraseña.
        * El montaje es de FUSE y pertenece al usuario, así que **root ni
          siquiera puede leer dentro**. Aunque pkexec arrancara, no encontraría
          el ayudante.

        Así que se usa el intérprete del sistema —al ayudante le basta la
        biblioteca estándar— y se deja una copia del propio ayudante fuera del
        montaje. Fuera de un AppImage no se copia nada.
        """
        if not self.empaquetado():
            return sys.executable, HELPER

        interprete = next((ruta for ruta in SYSTEM_PYTHON if os.path.exists(ruta)),
                          None)
        if interprete is None:
            raise HelperUnavailable(
                "No hay ningún Python del sistema con el que lanzar el ayudante. "
                "El que trae el AppImage no sirve: pkexec no ejecuta nada desde "
                "su punto de montaje."
            )

        destino = _cache_dir() / "helper.py"
        try:
            destino.parent.mkdir(parents=True, exist_ok=True)
            # Se reescribe siempre: si el AppImage se actualiza, la copia de
            # una versión vieja del ayudante hablaría otro protocolo.
            destino.write_bytes(HELPER.read_bytes())
            destino.chmod(0o700)
        except OSError as exc:
            raise HelperUnavailable(
                f"no se pudo preparar el ayudante fuera del AppImage: {exc}"
            ) from exc
        return interprete, destino

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


class PmuUnsupported(HelperError):
    """Esta máquina no tiene contadores de ocupación de gráfica que leer."""


def already_root() -> bool:
    """Si el programa ya corre como root, no hace falta ningún ayudante."""
    return os.geteuid() == 0
