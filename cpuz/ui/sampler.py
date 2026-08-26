"""Hilo de muestreo.

Todo lo que toca el hardware ocurre aquí, nunca en el hilo de la interfaz.
No es una preferencia de estilo: leer decenas de ficheros de sysfs y fijar la
afinidad del hilo para consultar CPUID son operaciones que bloquearían la
ventana y, en el caso de la afinidad, dejarían la interfaz clavada en un solo
núcleo para siempre.

El objeto que viaja por la señal es un `Snapshot` inmutable, así que cruzar
el límite entre hilos es seguro sin ningún cerrojo.
"""

from __future__ import annotations

from PySide6.QtCore import QMutex, QThread, QWaitCondition, Signal

from ..collector import Collector
from ..model import Snapshot


class Sampler(QThread):
    sampled = Signal(object)          # Snapshot
    failed = Signal(str)

    def __init__(self, interval_ms: int = 1000, parent=None) -> None:
        super().__init__(parent)
        self._interval_ms = interval_ms
        self._mutex = QMutex()
        self._wake = QWaitCondition()
        self._stopping = False
        self._elevate = False

    def set_interval(self, milliseconds: int) -> None:
        self._mutex.lock()
        self._interval_ms = max(100, milliseconds)
        self._mutex.unlock()
        self._wake.wakeAll()

    def request_elevation(self) -> None:
        """Pide al colector los datos privilegiados y despierta el bucle.

        Se llama desde el hilo de la interfaz, pero solo marca una bandera: el
        trabajo —y el diálogo de polkit, que bloquea— ocurre en este hilo.
        """
        self._elevate = True
        self._wake.wakeAll()

    def stop(self) -> None:
        self._mutex.lock()
        self._stopping = True
        self._mutex.unlock()
        self._wake.wakeAll()
        self.wait(3000)

    def run(self) -> None:
        # El colector se crea DENTRO del hilo: así la afinidad que fija CPUID
        # afecta solo a este hilo y no al de la interfaz.
        try:
            collector = Collector()
        except Exception as exc:                        # noqa: BLE001
            self.failed.emit(str(exc))
            return

        try:
            self._loop(collector)
        finally:
            # Cierra el ayudante privilegiado si llegó a arrancar: dejarlo
            # vivo tras cerrar la ventana sería un proceso root huérfano.
            collector.close()

    def _loop(self, collector) -> None:
        while True:
            if self._elevate:
                self._elevate = False
                try:
                    collector.request_elevation()
                except Exception as exc:                # noqa: BLE001
                    self.failed.emit(str(exc))
            try:
                self.sampled.emit(collector.snapshot())
            except Exception as exc:                    # noqa: BLE001
                self.failed.emit(str(exc))

            self._mutex.lock()
            try:
                if self._stopping:
                    return
                self._wake.wait(self._mutex, self._interval_ms)
                if self._stopping:
                    return
            finally:
                self._mutex.unlock()

    def __del__(self) -> None:
        pass
