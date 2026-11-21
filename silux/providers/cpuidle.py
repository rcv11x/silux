"""Residencia en los estados de reposo del procesador (C-states).

El kernel cuenta, por hilo y por estado, los microsegundos que lleva ahí
desde el arranque (`cpuidle/stateN/time`). Restando dos lecturas sale qué
parte del último intervalo pasó cada hilo en cada estado, que es lo que dice
si el equipo descansa de verdad cuando no hace nada. Sin permisos.

Como el uso por hilo y como RAPL, la primera lectura solo pone la
referencia.
"""

from __future__ import annotations

import glob
import os
import re
import time
from typing import Optional

from .. import sysroot
from ..model import IdleState
from .base import Draft, Provider, read_int, read_text
from .counters import increase, window_s

CPUS = "/sys/devices/system/cpu"


class CpuIdle(Provider):
    name = "cpuidle"
    provides = "cpu.idle_states"

    def __init__(self) -> None:
        # Los nombres no cambian; se leen una vez. cpu → [(carpeta, nombre, descripción)]
        self._estados: Optional[dict[int, list[tuple[str, str, Optional[str]]]]] = None
        self._previo: Optional[tuple[float, dict[tuple[int, str], int]]] = None

    def available(self) -> bool:
        return os.path.isdir(sysroot.ruta(f"{CPUS}/cpu0/cpuidle"))

    def _enumerar(self) -> dict:
        estados: dict[int, list] = {}
        for camino in glob.glob(os.path.join(sysroot.ruta(CPUS), "cpu[0-9]*", "cpuidle", "state[0-9]*")):
            base = sysroot.fuera(camino)
            encaje = re.search(r"/cpu(\d+)/cpuidle/", base)
            if not encaje:
                continue
            cpu = int(encaje.group(1))
            nombre = read_text(f"{base}/name")
            if nombre:
                estados.setdefault(cpu, []).append((base, nombre, read_text(f"{base}/desc")))
        for lista in estados.values():
            lista.sort(key=lambda e: int(e[0].rsplit("state", 1)[-1]))
        return estados

    def collect(self, draft: Draft) -> None:
        # Un equipo volcado guarda una sola lectura de cada contador: restada
        # consigo misma daría «0 % en todos los estados», que parece un dato
        # y no lo es. Como el uso por hilo y el consumo, ahí no sale.
        if sysroot.activo():
            return
        if self._estados is None:
            self._estados = self._enumerar()
        ahora = time.monotonic()
        lectura: dict[tuple[int, str], int] = {}
        for cpu, estados in self._estados.items():
            for base, nombre, _descripcion in estados:
                micros = read_int(f"{base}/time")
                if micros is not None:
                    lectura[(cpu, nombre)] = micros
        previo, self._previo = self._previo, (ahora, lectura)
        if previo is None or not lectura:
            return
        segundos = window_s(previo[0], ahora, draft.interval_s)
        if segundos is None:
            return
        draft.cpu_extra["idle_states"] = self.residencia(
            previo[1], lectura, segundos, self._estados)

    @staticmethod
    def residencia(antes: dict, despues: dict, segundos: float, estados: dict) -> list[IdleState]:
        """El porcentaje del intervalo en cada estado: media, mínimo y máximo
        entre los hilos. En el orden del kernel, del más ligero al más hondo."""
        if segundos <= 0:
            return []
        orden: list[tuple[str, Optional[str]]] = []
        for lista in estados.values():
            for _base, nombre, descripcion in lista:
                if nombre not in [n for n, _d in orden]:
                    orden.append((nombre, descripcion))
        salida = []
        for nombre, descripcion in orden:
            partes = []
            for (cpu, estado), micros in despues.items():
                if estado != nombre or (cpu, estado) not in antes:
                    continue
                gastado = increase(antes[(cpu, estado)], micros)
                # Un contador que retrocede (un hilo que se apagó y volvió)
                # no da un porcentaje: ese hilo no cuenta en esta vuelta.
                if gastado is None:
                    continue
                partes.append(min(100.0, gastado / (segundos * 1e6) * 100.0))
            if partes:
                salida.append(IdleState(
                    name=nombre, description=descripcion,
                    percent=round(sum(partes) / len(partes), 1),
                    low=round(min(partes), 1), high=round(max(partes), 1)))
        return salida
