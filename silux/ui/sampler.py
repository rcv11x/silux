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

import time

from PySide6.QtCore import QMutex, QThread, QWaitCondition, Signal

from ..collector import Collector
from ..model import Snapshot


# Cada cuánto se leen, mientras se espera, los contadores que el hardware da
# como un instante (el uso de una AMD, `GpuState.between_samples`). Medido en
# la RX 9070 XT contra MangoHud (mediana 83 %): con cuatro por segundo la
# media sale igual (83) y baila poco más que con diez (desviación 3,6 y 2,8;
# una suelta, 10). Cuestan 0,24 puntos de un núcleo; diez, 0,56.
ENTRE_LECTURAS_MS = 250


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
        trabajo (y el diálogo de polkit, que bloquea) ocurre en este hilo.
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
            elevating = self._elevate
            if elevating:
                self._elevate = False
                try:
                    collector.request_elevation()
                except Exception as exc:                # noqa: BLE001
                    self.failed.emit(str(exc))
            try:
                snapshot = collector.snapshot()
            except Exception as exc:                    # noqa: BLE001
                self.failed.emit(str(exc))
            else:
                self.sampled.emit(snapshot)
            if elevating:
                # The password window opens inside that snapshot and blocks it.
                # Whatever was asked while it was open is answered by it, not
                # by a second window after a cancel.
                self._elevate = False

            if not self._esperar(collector):
                return

    def _esperar(self, collector) -> bool:
        """Espera el intervalo; dice si hay que seguir.

        Si algún proveedor lo pide, la espera va a trozos y entre trozo y
        trozo se lee lo suyo (`Collector.between_samples`). Lo que despierta
        antes de tiempo (parar, otro intervalo, pedir permisos) corta la
        espera igual que antes.
        """
        trocear = collector.wants_between_samples()
        self._mutex.lock()
        try:
            fin = time.monotonic() + self._interval_ms / 1000
            while not self._stopping:
                if self._elevate:
                    # Pedido mientras se leía sin el cerrojo, cuando nadie
                    # esperaba el aviso: no se hace esperar al intervalo.
                    return True
                queda_ms = int((fin - time.monotonic()) * 1000)
                if queda_ms <= 0:
                    return True
                tramo = min(queda_ms, ENTRE_LECTURAS_MS) if trocear else queda_ms
                if self._wake.wait(self._mutex, tramo):
                    return not self._stopping
                if trocear and not self._stopping:
                    # Sin el cerrojo: quien quiera parar no tiene que esperar
                    # a que acabe una lectura de sysfs.
                    self._mutex.unlock()
                    try:
                        collector.between_samples()
                    finally:
                        self._mutex.lock()
            return False
        finally:
            self._mutex.unlock()

    def __del__(self) -> None:
        pass
