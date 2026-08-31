"""Topología, cachés y frecuencias desde /sys/devices/system/cpu.

Es la fuente más fiable que hay: la escribe el kernel, no hace falta ningún
permiso y funciona igual en x86, ARM y RISC-V. Cubre casi todo lo que se
enseña en la pestaña de CPU salvo la identidad del procesador, que solo sabe
CPUID.
"""

from __future__ import annotations

import dataclasses
import os
import pathlib

from ..model import Cache, Clocks, Need
from .base import Draft, Provider, mean, parse_cpu_list, parse_size, read_int, read_text
from ..i18n import _

SYS_CPU = "/sys/devices/system/cpu"

# En las CPU híbridas de Intel el kernel publica un PMU por tipo de núcleo.
# Es la forma más limpia de saber qué CPU lógica es un núcleo P y cuál un E.
HYBRID_PMUS = (
    ("/sys/devices/cpu_core", "performance"),
    ("/sys/devices/cpu_atom", "efficiency"),
)

_CACHE_KINDS = {"data": "data", "instruction": "instruction", "unified": "unified"}


def online_cpus() -> tuple[int, ...]:
    cpus = parse_cpu_list(read_text(f"{SYS_CPU}/online"))
    if cpus:
        return cpus
    # Red de seguridad: si `online` no existe, cuenta los directorios cpuN.
    found = []
    for entry in pathlib.Path(SYS_CPU).glob("cpu[0-9]*"):
        if entry.name[3:].isdigit():
            found.append(int(entry.name[3:]))
    return tuple(sorted(found)) or (0,)


def _por_nucleo_arm(cpus: tuple[int, ...]) -> dict[str, list[int]]:
    """Reparte las CPU de un ARM por el núcleo que lleva cada una.

    Devuelve vacío si no hay más de un tipo, que es lo normal fuera de ARM y
    también en un ARM de un solo núcleo: en ese caso manda el reparto de
    siempre y aquí no se toca nada.
    """
    from .armcpu import es_arm, midr_por_cpu

    if not es_arm():
        return {}
    midr = midr_por_cpu()
    grupos: dict[tuple, list[int]] = {}
    for cpu in cpus:
        identidad = midr.get(cpu)
        if identidad is None or identidad == (None, None):
            return {}                     # incompleto: no se adivina
        grupos.setdefault(identidad, []).append(cpu)
    if len(grupos) < 2:
        return {}

    # Los grandes primero, que es como los numera el fabricante y como los
    # espera quien mira: el orden lo da el número de pieza, más alto cuanto
    # más reciente y más grande es el núcleo.
    orden = sorted(grupos, key=lambda k: (k[1] or 0), reverse=True)
    nombres = ["performance", "efficiency"] if len(orden) == 2 else [
        f"nucleo{i}" for i in range(len(orden))]
    return {nombres[i]: grupos[clave] for i, clave in enumerate(orden)}


class SysfsTopology(Provider):
    """Reparto de CPUs por tipo de núcleo, socket, y jerarquía de cachés."""

    name = "sysfs-topology"
    provides = "cpu.topology"
    static = True

    def available(self) -> bool:
        return os.path.isdir(SYS_CPU)

    def unavailable_reason(self):
        if self.available():
            return None
        return ("cpu.topology", Need.PLATFORM,
                _("prov.cpu.nosysfs"), _("prov.cpu.nosysfs.hint"))

    def collect(self, draft: Draft) -> None:
        draft.capabilities.add("sysfs-cpu")
        cpus = online_cpus()

        by_type = self._classify(cpus)
        draft.hybrid = len(by_type) > 1

        packages: set[int] = set()
        for key, members in by_type.items():
            entry = draft.type_for(key)
            entry["cpus"] = list(members)
            entry["threads"] = len(members)

            cores: set[tuple[int, int]] = set()
            for index in members:
                package_id = read_int(f"{SYS_CPU}/cpu{index}/topology/physical_package_id") or 0
                core_id = read_int(f"{SYS_CPU}/cpu{index}/topology/core_id")
                core_id = core_id if core_id is not None else index
                packages.add(package_id)
                cores.add((package_id, core_id))

                cpu = draft.cpu(index)
                cpu["core_id"] = core_id
                cpu["package_id"] = package_id
                cpu["type_key"] = key

            entry["cores"] = len(cores) or len(members)
            entry["smt"] = entry["threads"] > entry["cores"]
            entry["caches"] = self._caches_for(members)
            entry["microcode"] = self._microcode(members[0])
            entry["clocks"] = self._static_clocks(members[0])

        draft.sockets = len(packages) or 1

    # -- interno ------------------------------------------------------------

    @staticmethod
    def _classify(cpus: tuple[int, ...]) -> dict[str, list[int]]:
        buckets: dict[str, list[int]] = {}
        for path, key in HYBRID_PMUS:
            members = [c for c in parse_cpu_list(read_text(f"{path}/cpus")) if c in cpus]
            if members:
                buckets[key] = members

        assigned = {c for members in buckets.values() for c in members}
        leftover = [c for c in cpus if c not in assigned]
        if leftover:
            # Sin PMUs separados hay un solo tipo; con ellos, esto no debería
            # ocurrir, pero si el kernel deja alguna CPU fuera no se pierde.
            buckets["general" if not buckets else "other"] = leftover

        if len(buckets) == 1 and "general" in buckets:
            # Un big.LITTLE de ARM es tan híbrido como un Intel de 12ª, pero
            # el kernel no le publica un PMU por tipo. Lo que sí publica es
            # qué núcleo lleva cada CPU, y con eso se separan igual.
            if reparto := _por_nucleo_arm(tuple(buckets["general"])):
                return reparto
        return buckets or {"general": list(cpus)}

    @staticmethod
    def _caches_for(cpus: list[int]) -> list[Cache]:
        # Cada instancia física de caché aparece repetida en todas las CPUs que
        # la comparten. Se deduplica por el conjunto de CPUs que la comparten.
        seen: dict[tuple, set[frozenset[int]]] = {}
        for index in cpus:
            cache_dir = pathlib.Path(f"{SYS_CPU}/cpu{index}/cache")
            if not cache_dir.is_dir():
                continue
            for entry in sorted(cache_dir.glob("index*")):
                level = read_int(f"{entry}/level")
                kind_raw = (read_text(f"{entry}/type") or "").lower()
                size = parse_size(read_text(f"{entry}/size"))
                if level is None or size is None:
                    continue
                shared = frozenset(parse_cpu_list(read_text(f"{entry}/shared_cpu_list")) or (index,))
                key = (
                    level,
                    _CACHE_KINDS.get(kind_raw, kind_raw or "unified"),
                    size,
                    read_int(f"{entry}/ways_of_associativity"),
                    read_int(f"{entry}/coherency_line_size"),
                    read_int(f"{entry}/number_of_sets"),
                )
                seen.setdefault(key, set()).add(shared)

        caches = []
        for (level, kind, size, ways, line, sets), shared_sets in seen.items():
            grupos = sorted((tuple(sorted(g)) for g in shared_sets), key=lambda g: g[0])
            caches.append(Cache(
                level=level,
                kind=kind,
                size_bytes=size,
                ways=ways,
                line_bytes=line,
                sets=sets,
                instances=len(grupos),
                shared_by=len(grupos[0]) if grupos else 1,
                instance_cpus=tuple(grupos),
            ))
        caches.sort(key=lambda c: (c.level, c.kind))
        return caches

    @staticmethod
    def _microcode(cpu_index: int) -> str | None:
        raw = read_text(f"{SYS_CPU}/cpu{cpu_index}/microcode/version")
        return raw or None

    @staticmethod
    def _static_clocks(cpu_index: int) -> Clocks:
        freq = f"{SYS_CPU}/cpu{cpu_index}/cpufreq"
        khz = lambda name: (lambda v: v * 1000 if v else None)(read_int(f"{freq}/{name}"))
        # Aquí solo va lo que de verdad no cambia. El techo efectivo y el
        # gobernador se releen en cada muestreo porque los perfiles de energía
        # del escritorio los modifican sin avisar.
        return Clocks(
            min_hz=khz("cpuinfo_min_freq"),
            base_hz=khz("base_frequency"),
            driver=read_text(f"{freq}/scaling_driver"),
        )


class SysfsClocks(Provider):
    """Frecuencia instantánea de cada CPU lógica, y el techo vigente."""

    name = "sysfs-clocks"
    provides = "cpu.clocks.current_hz"

    def available(self) -> bool:
        return os.path.isdir(SYS_CPU)

    def collect(self, draft: Draft) -> None:
        any_read = False
        for index, cpu in draft.logical.items():
            khz = read_int(f"{SYS_CPU}/cpu{index}/cpufreq/scaling_cur_freq")
            if khz is None:
                khz = read_int(f"{SYS_CPU}/cpu{index}/cpufreq/cpuinfo_cur_freq")
            if khz is not None:
                cpu["freq_hz"] = khz * 1000
                any_read = True

        for entry in draft.types.values():
            freqs = [draft.logical[i].get("freq_hz") for i in entry.get("cpus", ())]
            average = mean(freqs)
            if average is None:
                continue
            clocks: Clocks = entry.get("clocks") or Clocks()
            leader = entry["cpus"][0]
            ceiling = read_int(f"{SYS_CPU}/cpu{leader}/cpufreq/cpuinfo_max_freq")
            governor = read_text(f"{SYS_CPU}/cpu{leader}/cpufreq/scaling_governor")
            preference = read_text(
                f"{SYS_CPU}/cpu{leader}/cpufreq/energy_performance_preference"
            )
            # `replace` en vez de reconstruir campo a campo: si mañana Clocks
            # gana un campo, este código no se lo come en silencio.
            entry["clocks"] = dataclasses.replace(
                clocks,
                current_hz=int(average),
                max_hz=ceiling * 1000 if ceiling else clocks.max_hz,
                governor=governor or clocks.governor,
                energy_preference=preference or clocks.energy_preference,
            )

        if not any_read:
            # Dentro de una máquina virtual no hay ningún módulo que cargar:
            # el hipervisor no expone cpufreq porque no gobierna el reloj.
            # Decirlo con Need.DRIVER lo pinta de ámbar y manda a buscar un
            # driver que no existe, que es el mismo error que el botón de
            # permisos puesto donde el ayudante no sabía arreglar nada.
            if any(t.get("in_virtual_machine") for t in draft.types.values()):
                draft.note(
                    "cpu.clocks.current_hz", Need.HARDWARE,
                    _("prov.cpu.nofreq.vm"), _("prov.cpu.nofreq.vm.hint"),
                )
            else:
                draft.note(
                    "cpu.clocks.current_hz", Need.DRIVER,
                    _("prov.cpu.nofreq"), _("prov.cpu.nofreq.hint"),
                )
