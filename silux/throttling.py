"""Desde cuándo lleva frenándose algo, y por qué.

Los motivos de recorte ya se leen —`indep_throttle_status` en AMD, NVML en
NVIDIA— y hasta ahora salían como una fila más de una ficha: «recortando por
temperatura del punto caliente». Eso dice qué pasa ahora y no dice lo que uno
quiere saber, que es si lleva así un instante o cuarenta segundos.

La diferencia importa. Una tarjeta que toca su límite de potencia medio
segundo en cada cambio de escena está funcionando como se diseñó; una que
lleva un minuto entero contra el límite térmico tiene un problema de
refrigeración. El dato es el mismo y la conclusión es la contraria.

Se guarda aparte del modelo por lo mismo que `tracking.py`: el snapshot es una
foto y esto es la película. Y se recuerda un rato lo que acaba de terminar,
porque quien mira la pantalla justo después del pico también quiere saberlo.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Optional

# Cuánto se sigue enseñando un episodio ya terminado. Medio minuto es lo que
# tarda uno en apartar la vista del juego y mirar el programa.
MEMORIA_S = 30.0

# Por debajo de esto no se dice nada: un recorte de dos décimas en un cambio de
# escena es el funcionamiento normal de cualquier tarjeta moderna, y avisar de
# él convierte el aviso en ruido de fondo.
MINIMO_S = 1.5


@dataclass
class Episodio:
    """Un tramo continuo de recorte."""

    desde_ns: int
    hasta_ns: Optional[int] = None          # None = sigue en curso
    # Todos los que se han visto durante el episodio, no solo el último: una
    # tarjeta que empieza por potencia y acaba por temperatura ha hecho las dos
    # cosas, y quedarse con la de ahora pierde la mitad de la historia.
    motivos: set[str] = field(default_factory=set)

    def en_curso(self) -> bool:
        return self.hasta_ns is None

    def duracion_s(self, ahora_ns: int) -> float:
        final = self.hasta_ns if self.hasta_ns is not None else ahora_ns
        return max(0.0, (final - self.desde_ns) / 1e9)


@dataclass
class SeguidorDeRecortes:
    """Sigue los episodios de recorte de varias cosas a la vez.

    La clave la pone quien llama: en la práctica es la ranura PCI de cada
    gráfica, que es lo único que no cambia entre muestreos.
    """

    _abiertos: dict[str, Episodio] = field(default_factory=dict)
    _ultimos: dict[str, Episodio] = field(default_factory=dict)

    def update(self, clave: str, activo: Optional[bool],
               motivos: Iterable[str], ahora_ns: int) -> None:
        """Una muestra. `activo` a None es «no se sabe» y no abre ni cierra."""
        if activo is None:
            return

        episodio = self._abiertos.get(clave)
        if activo:
            if episodio is None:
                episodio = Episodio(desde_ns=ahora_ns)
                self._abiertos[clave] = episodio
            episodio.motivos.update(m for m in motivos if m)
        elif episodio is not None:
            episodio.hasta_ns = ahora_ns
            self._ultimos[clave] = episodio
            del self._abiertos[clave]

    def actual(self, clave: str) -> Optional[Episodio]:
        """El episodio en curso, si lleva ya lo bastante para contar."""
        return self._abiertos.get(clave)

    def reciente(self, clave: str, ahora_ns: int) -> Optional[Episodio]:
        """El último que terminó, mientras siga siendo reciente."""
        episodio = self._ultimos.get(clave)
        if episodio is None or episodio.hasta_ns is None:
            return None
        if (ahora_ns - episodio.hasta_ns) / 1e9 > MEMORIA_S:
            return None
        return episodio

    def relevante(self, clave: str, ahora_ns: int) -> Optional[Episodio]:
        """El que hay que enseñar: el de ahora, o el que acaba de terminar.

        Los dos tienen que haber durado lo suyo. Un parpadeo no se cuenta ni
        mientras pasa ni después.
        """
        for episodio in (self.actual(clave), self.reciente(clave, ahora_ns)):
            if episodio is not None and episodio.duracion_s(ahora_ns) >= MINIMO_S:
                return episodio
        return None

    def reset(self, clave: Optional[str] = None) -> None:
        if clave is None:
            self._abiertos.clear()
            self._ultimos.clear()
        else:
            self._abiertos.pop(clave, None)
            self._ultimos.pop(clave, None)
