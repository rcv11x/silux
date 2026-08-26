"""Sensores derivados de datos que ya se han leído.

Los relojes, el uso por núcleo y el desglose de potencia no salen de un chip
hwmon: los da CPUID, cpufreq, /proc/stat y RAPL. Pero en un árbol de sensores
son exactamente eso —magnitudes que cambian y que interesa seguir con sus
mínimos y máximos—, así que aquí se convierten al mismo formato que el resto.

Es lo que hace HWiNFO: bajo el nodo del procesador conviven las temperaturas
del chip de sensores con los relojes y el uso, que vienen de otro sitio.

Este proveedor se ejecuta el último a propósito: solo transforma lo que otros
han recogido y no toca ningún fichero.
"""

from __future__ import annotations

from ..model import Sensor, SensorKind, short_brand
from .base import Draft, Provider


class DerivedSensors(Provider):
    name = "derived"
    provides = "sensors.derived"

    def collect(self, draft: Draft) -> None:
        if not draft.types:
            return
        first = draft.types[next(iter(draft.types))]
        device = short_brand(first.get("brand"))

        draft.sensors.extend(self._power(draft, device))
        draft.sensors.extend(self._clocks(draft, device))
        draft.sensors.extend(self._usage(draft, device))

    # -- interno ------------------------------------------------------------

    @staticmethod
    def _power(draft: Draft, device: str) -> list[Sensor]:
        power = draft.cpu_extra.get("power")
        if power is None:
            return []
        fields = (
            ("package_w", "Paquete", 0),
            ("core_w", "Núcleos", 1),
            ("uncore_w", "Uncore", 2),
            ("dram_w", "DRAM", 3),
        )
        sensors = []
        for attribute, label, order in fields:
            value = getattr(power, attribute)
            if value is None:
                continue
            sensors.append(Sensor(
                key=f"rapl/{attribute}", chip="intel-rapl", device=device,
                label=label, kind=SensorKind.POWER, value=value, order=order,
                # El límite sostenido del propio chip es el umbral natural:
                # pasarlo sostenidamente significa que va a bajar frecuencia.
                high=power.limit_long_w if attribute == "package_w" else None,
                critical=power.limit_short_w if attribute == "package_w" else None,
            ))
        return sensors

    @staticmethod
    def _clocks(draft: Draft, device: str) -> list[Sensor]:
        sensors = []
        for index, cpu in sorted(draft.logical.items()):
            frequency = cpu.get("freq_hz")
            if frequency is None:
                continue
            sensors.append(Sensor(
                key=f"clock/cpu{index}", chip="cpufreq", device=device,
                label=f"Core #{index}", kind=SensorKind.CLOCK,
                value=round(frequency / 1e6, 1), order=index,
            ))
        return sensors

    @staticmethod
    def _usage(draft: Draft, device: str) -> list[Sensor]:
        sensors = []
        total = draft.cpu_extra.get("usage_percent")
        if total is not None:
            sensors.append(Sensor(
                key="usage/total", chip="procfs", device=device,
                label="Total", kind=SensorKind.USAGE, value=total, order=-1,
            ))
        for index, cpu in sorted(draft.logical.items()):
            value = cpu.get("usage_percent")
            if value is None:
                continue
            sensors.append(Sensor(
                key=f"usage/cpu{index}", chip="procfs", device=device,
                label=f"Core #{index}", kind=SensorKind.USAGE,
                value=value, order=index,
            ))
        return sensors
