"""La batería, que en un portátil es la pieza que más se degrada.

Hasta aquí de la batería solo salían tres sensores sueltos —voltaje, corriente
y potencia— perdidos entre los noventa y tantos del árbol. Lo que la gente
quiere saber de una batería no es su voltaje: es cuánta capacidad le queda
respecto a la que tenía nueva, y eso no lo enseñaba nadie.

**Dos convenciones y hay que aguantar las dos.** Según el firmware, el kernel
publica la capacidad en `charge_*` (µAh) o en `energy_*` (µWh), y algunos traen
las dos. Los miliamperios-hora no se pueden comparar entre equipos sin saber el
voltaje de la celda —4000 mAh a 7,6 V y 4000 mAh a 11,4 V son baterías muy
distintas—, así que aquí todo sale en vatios-hora: si viene en carga, se
multiplica por el voltaje de diseño, que es el que corresponde a la capacidad
nominal y no cambia con lo llena que esté.

Nada de esto necesita permisos: es sysfs plano.
"""

from __future__ import annotations

import pathlib
from typing import Optional

from ..i18n import _
from ..model import Battery, Need
from .base import Draft, Provider, read_int, read_text

POWER_SUPPLY = pathlib.Path("/sys/class/power_supply")

# Lo que dice el kernel -> la clave con la que se traduce. Se pasa a clave aquí
# y no en la ficha porque el kernel escribe en inglés y con mayúscula, y eso no
# se enseña.
ESTADOS = {
    "charging": "bat.status.charging",
    "discharging": "bat.status.discharging",
    "full": "bat.status.full",
    "not charging": "bat.status.held",
    "unknown": "bat.status.unknown",
}


def _es_bateria(entrada: pathlib.Path) -> bool:
    """La batería del equipo, y no el cargador ni el ratón inalámbrico.

    `/sys/class/power_supply` mezcla de todo: el adaptador de corriente, los
    puertos USB-C y cualquier periférico con pila. Con mirar `type` no basta,
    y se vio en el sitio menos esperado: este sobremesa, que no tiene batería
    ninguna, declaraba una porque el ratón Logitech publica
    `hidpp_battery_0` con `type=Battery`. Habría salido una ficha de batería
    en un ordenador de torre.

    Quien lo distingue es `scope`: los periféricos dicen «Device» y la del
    equipo dice «System» o no dice nada, que es lo que hacen los portátiles
    antiguos.
    """
    if (read_text(str(entrada / "type")) or "").strip().lower() != "battery":
        return False
    ambito = (read_text(str(entrada / "scope")) or "").strip().lower()
    return ambito in ("", "system", "unknown")


def _vatios_hora(entrada: pathlib.Path, cual: str,
                 voltaje_nominal: Optional[float]) -> Optional[float]:
    """`energy_*` si está; si no, `charge_*` por el voltaje de diseño."""
    if (microvatios_hora := read_int(str(entrada / f"energy_{cual}"))) is not None:
        return round(microvatios_hora / 1e6, 2)
    microamperios_hora = read_int(str(entrada / f"charge_{cual}"))
    if microamperios_hora is None or not voltaje_nominal:
        return None
    return round(microamperios_hora / 1e6 * voltaje_nominal, 2)


def _vatios(entrada: pathlib.Path, voltaje: Optional[float]) -> Optional[float]:
    """Lo que entra o sale ahora mismo, siempre positivo.

    El signo de `current_now` no significa lo mismo en todos los firmwares
    —unos lo ponen negativo al descargar y otros no—, así que se toma el valor
    absoluto y quien dice si entra o sale es `status`.
    """
    if (microvatios := read_int(str(entrada / "power_now"))) is not None:
        return round(abs(microvatios) / 1e6, 2)
    microamperios = read_int(str(entrada / "current_now"))
    if microamperios is None or not voltaje:
        return None
    return round(abs(microamperios) / 1e6 * voltaje, 2)


def _leer(entrada: pathlib.Path) -> Battery:
    voltaje = read_int(str(entrada / "voltage_now"))
    voltios = round(voltaje / 1e6, 3) if voltaje else None
    diseno = read_int(str(entrada / "voltage_min_design"))
    voltios_diseno = round(diseno / 1e6, 3) if diseno else None

    # Para convertir mAh en Wh manda el voltaje de diseño: es el que
    # corresponde a la capacidad nominal. El de ahora sube y baja con la carga
    # y daría una capacidad distinta en cada muestreo.
    nominal = voltios_diseno or voltios

    crudo = (read_text(str(entrada / "status")) or "").strip().lower()
    porcentaje = read_int(str(entrada / "capacity"))

    return Battery(
        name=entrada.name,
        present=read_int(str(entrada / "present")) != 0,
        status=ESTADOS.get(crudo, "bat.status.unknown"),
        percent=float(porcentaje) if porcentaje is not None else None,
        design_wh=_vatios_hora(entrada, "full_design", nominal),
        full_wh=_vatios_hora(entrada, "full", nominal),
        now_wh=_vatios_hora(entrada, "now", nominal),
        voltage_v=voltios,
        design_voltage_v=voltios_diseno,
        power_w=_vatios(entrada, voltios),
        cycles=read_int(str(entrada / "cycle_count")) or None,
        manufacturer=read_text(str(entrada / "manufacturer")),
        model=read_text(str(entrada / "model_name")),
        technology=read_text(str(entrada / "technology")),
        serial=read_text(str(entrada / "serial_number")),
        charge_start_percent=read_int(
            str(entrada / "charge_control_start_threshold")),
        charge_end_percent=read_int(
            str(entrada / "charge_control_end_threshold")),
    )


class Batteries(Provider):
    """Las baterías del equipo. En un sobremesa no hay ninguna y se dice."""

    name = "battery"
    provides = "batteries"

    def available(self) -> bool:
        return POWER_SUPPLY.is_dir()

    def unavailable_reason(self):
        if self.available():
            return None
        return ("batteries", Need.PLATFORM,
                _("prov.bat.nosysfs"), _("prov.bat.nosysfs.hint"))

    def collect(self, draft: Draft) -> None:
        if not POWER_SUPPLY.is_dir():
            return
        encontradas = [_leer(entrada)
                       for entrada in sorted(POWER_SUPPLY.iterdir())
                       if _es_bateria(entrada)]
        if not encontradas:
            # Sin nota: un sobremesa no tiene batería y decirlo cada vez sería
            # avisar de que un equipo es lo que es. La sección se esconde sola.
            return
        draft.capabilities.add("battery")
        draft.batteries = encontradas
