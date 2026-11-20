"""Una orden que tarda, fuera del hilo de la interfaz.

`pkexec` abre el diálogo de la contraseña y no vuelve hasta que alguien la
escribe o lo cierra. Lanzado con `subprocess.run` desde un botón, la ventana
se queda sin repintar todo ese rato: las gráficas paradas, y el gestor de
ventanas ofreciendo matar el programa. Aquí la espera ocurre en otro hilo y el
resultado vuelve por una señal, que Qt entrega en el hilo de quien la escucha.

Solo cambia dónde se espera. Qué se ejecuta lo decide quien construye la
orden, igual que antes.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from typing import Optional, Sequence

from PySide6.QtCore import QThread, Signal

from ..system_env import system_environment


@dataclass(frozen=True)
class CommandResult:
    """Cómo acabó la orden. `error` va relleno cuando ni siquiera arrancó o
    hubo que cortarla; entonces no hay código de salida."""

    returncode: Optional[int] = None
    stdout: str = ""
    stderr: str = ""
    error: Optional[str] = None


class BackgroundCommand(QThread):
    """Ejecuta una orden y avisa con `done` cuando termina."""

    done = Signal(object)

    def __init__(self, argv: Sequence[str], stdin: Optional[str] = None,
                 timeout: float = 180.0, parent=None) -> None:
        super().__init__(parent)
        self._argv = list(argv)
        self._stdin = stdin
        self._timeout = timeout
        self._proceso: Optional[subprocess.Popen] = None
        self._cancelada = False

    def run(self) -> None:  # noqa: D102 - el de QThread
        try:
            self._proceso = subprocess.Popen(
                self._argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, text=True, env=system_environment())
        except OSError as error:
            self.done.emit(CommandResult(error=str(error)))
            return
        try:
            salida, errores = self._proceso.communicate(self._stdin, timeout=self._timeout)
        except subprocess.TimeoutExpired as error:
            self._proceso.kill()
            self._proceso.communicate()
            self.done.emit(CommandResult(error=str(error)))
            return
        if self._cancelada:
            # Quien la cortó ya no está para escuchar: la ventana se cierra.
            return
        self.done.emit(CommandResult(self._proceso.returncode, salida or "", errores or ""))

    def cancel(self) -> None:
        """Corta la orden y espera al hilo. Para cuando se cierra la ventana.

        Destruir un QThread que sigue corriendo aborta el proceso entero, y
        esperar a que alguien escriba una contraseña para poder cerrar no es
        una opción.
        """
        self._cancelada = True
        proceso = self._proceso
        if proceso is not None and proceso.poll() is None:
            proceso.kill()
        self.wait(5000)
