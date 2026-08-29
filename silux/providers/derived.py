"""Sensores derivados de datos que ya se han leído.

Los relojes, el uso por núcleo y el desglose de potencia no salen de un chip
hwmon: los da CPUID, cpufreq, /proc/stat y RAPL. Pero en un árbol de sensores
son exactamente eso (magnitudes que cambian y que interesa seguir con sus
mínimos y máximos), así que aquí se convierten al mismo formato que el resto.

Es lo que hace HWiNFO: bajo el nodo del procesador conviven las temperaturas
del chip de sensores con los relojes y el uso, que vienen de otro sitio.

Este proveedor se ejecuta el último a propósito: solo transforma lo que otros
han recogido y no toca ningún fichero.
"""

from __future__ import annotations

from typing import Optional

from ..i18n import _
from ..model import Sensor, SensorKind, short_brand
from .base import Draft, Provider


# Un voltaje redondeado a un decimal deja de ser un voltaje: 0,845 V se
# convierte en 0,8 y ya no dice nada. Cada magnitud tiene la suya.
DECIMALES = {SensorKind.VOLTAGE: 3, SensorKind.TEMPERATURE: 1, SensorKind.CLOCK: 1,
             SensorKind.USAGE: 1, SensorKind.MEMORY: 0, SensorKind.NETWORK: 1}


def _mhz(hz: Optional[int]) -> Optional[float]:
    return round(hz / 1e6, 1) if hz else None


def _megas(byte: Optional[int]) -> Optional[float]:
    return round(byte / 1024**2, 1) if byte else None


class DerivedSensors(Provider):
    name = "derived"
    provides = "sensors.derived"

    def collect(self, draft: Draft) -> None:
        if not draft.types:
            # Aun sin procesador identificado, las gráficas pueden tener datos.
            draft.sensors.extend(self._graphics(draft))
            return
        first = draft.types[next(iter(draft.types))]
        device = short_brand(first.get("brand"))

        draft.sensors.extend(self._power(draft, device))
        draft.sensors.extend(self._clocks(draft, device))
        draft.sensors.extend(self._usage(draft, device))
        draft.sensors.extend(self._graphics(draft))
        draft.sensors.extend(self._network(draft))

    @staticmethod
    def _network(draft: Draft) -> list[Sensor]:
        """El ritmo de cada interfaz que esté moviendo algo.

        Solo las que están levantadas: un equipo con Docker puede tener quince
        interfaces virtuales a cero, y llenar el árbol con ellas lo hace
        ilegible sin añadir nada.
        """
        sensors: list[Sensor] = []
        for interfaz in draft.network:
            if not interfaz.up or interfaz.kind == "loopback":
                continue
            device = f"Red ({interfaz.name})"
            trafico = interfaz.traffic
            campos = (
                ("rx", "Bajada", SensorKind.NETWORK, trafico.rx_rate_bps, 0),
                ("tx", "Subida", SensorKind.NETWORK, trafico.tx_rate_bps, 1),
                ("rx_total", "Recibido", SensorKind.MEMORY,
                 _megas(trafico.rx_bytes), 10),
                ("tx_total", "Enviado", SensorKind.MEMORY,
                 _megas(trafico.tx_bytes), 11),
            )
            for clave, etiqueta, tipo, valor, orden in campos:
                if valor is None:
                    continue
                sensors.append(Sensor(
                    key=f"net/{interfaz.name}/{clave}", chip="net", device=device,
                    label=etiqueta, kind=tipo,
                    value=round(float(valor) / (1024 if tipo is SensorKind.NETWORK else 1),
                                DECIMALES.get(tipo, 1)),
                    order=orden,
                ))
        return sensors

    @staticmethod
    def _graphics(draft: Draft) -> list[Sensor]:
        """Lo de la gráfica que no sale de hwmon.

        El chip de sensores de una tarjeta da temperaturas, ventilador y poco
        más. El uso, la memoria ocupada, los relojes que solo conoce el firmware
        y las temperaturas de los reguladores vienen del driver y del ioctl, y
        en el árbol pintan tanto como los otros: son magnitudes que cambian y
        que interesa seguir con su mínimo y su máximo.
        """
        sensors: list[Sensor] = []
        for gpu in draft.gpus:
            device = gpu.get("name") or _("sensor.dev.gpu").format(
                n=gpu.get("index", 0))
            marca = f"gpu{gpu.get('index', 0)}"
            relojes = gpu.get("clocks")
            memoria = gpu.get("memory")

            campos: list[tuple[str, str, SensorKind, object, int]] = [
                ("busy", _("sensor.gpu.core"), SensorKind.USAGE,
                 gpu.get("busy_percent"), 0),
                ("mem_busy", _("sensor.gpu.mem"), SensorKind.USAGE,
                 gpu.get("memory_busy_percent"), 1),
                ("video_busy", _("sensor.gpu.video"), SensorKind.USAGE,
                 gpu.get("video_busy_percent"), 2),
                ("vr_gfx", _("sensor.gpu.vrgfx"), SensorKind.TEMPERATURE,
                 gpu.get("vr_gfx_c"), 10),
                ("vr_soc", _("sensor.gpu.vrsoc"), SensorKind.TEMPERATURE,
                 gpu.get("vr_soc_c"), 11),
                ("vr_mem", _("sensor.gpu.vrmem"), SensorKind.TEMPERATURE,
                 gpu.get("vr_memory_c"), 12),
                ("v_soc", "SoC", SensorKind.VOLTAGE, gpu.get("voltage_soc_v"), 20),
                ("v_mem", _("sensor.mem"), SensorKind.VOLTAGE,
                 gpu.get("voltage_memory_v"), 21),
                ("fan_pct", _("sensor.fan"), SensorKind.USAGE,
                 gpu.get("fan_percent"), 3),
            ]
            if relojes is not None:
                campos += [
                    ("clk_soc", "SoC", SensorKind.CLOCK, _mhz(relojes.soc_hz), 32),
                    ("clk_mem_eff", _("sensor.mem.effective"), SensorKind.CLOCK,
                     _mhz(relojes.memory_effective_hz), 31),
                ]
            if memoria is not None:
                campos += [
                    ("vram_pct", _("sensor.vram"), SensorKind.USAGE,
                     memoria.used_percent, 4),
                    ("vram_mb", _("sensor.vram"), SensorKind.MEMORY,
                     _megas(memoria.used_bytes), 40),
                    ("gtt_mb", _("sensor.gtt"), SensorKind.MEMORY,
                     _megas(memoria.gtt_used_bytes), 41),
                ]

            for clave, etiqueta, tipo, valor, orden in campos:
                if valor is None:
                    continue
                sensors.append(Sensor(
                    key=f"{marca}/{clave}", chip="drm", device=device,
                    label=etiqueta, kind=tipo,
                    value=round(float(valor), DECIMALES.get(tipo, 1)),
                    order=orden,
                ))
        return sensors

    # -- interno ------------------------------------------------------------

    @staticmethod
    def _power(draft: Draft, device: str) -> list[Sensor]:
        power = draft.cpu_extra.get("power")
        if power is None:
            return []
        fields = (
            ("package_w", _("sensor.package"), 0),
            ("core_w", _("sensor.cores"), 1),
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
                label=_("sensor.total"), kind=SensorKind.USAGE,
                value=total, order=-1,
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
