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

from .protocol import ACTION_MSR, ACTION_PING, ACTION_SMBIOS, MAX_MESSAGE

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

        try:
            process = subprocess.Popen(
                ["pkexec", sys.executable, str(HELPER)],
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
            raise

        if not reply.get("ok") or reply.get("uid") != 0:
            self.close()
            raise HelperError("el ayudante no arrancó con privilegios")

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


def already_root() -> bool:
    """Si el programa ya corre como root, no hace falta ningún ayudante."""
    return os.geteuid() == 0
