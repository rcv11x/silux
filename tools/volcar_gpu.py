#!/usr/bin/env python3
"""Vuelca lo que el kernel publica de cada gráfica, para diagnosticar a ciegas.

Cuando a alguien le sale una tarjeta a medias, lo que hace falta no es la
captura: es saber qué archivos existen en su equipo y qué dicen. Los drivers
cambian de sitio los datos entre versiones —i915 movió las frecuencias a
`gt/gt0/` en el kernel 6.2 y dejó las viejas donde estaban— y desde otra
máquina no hay forma de adivinar cuál de las rutas tiene.

    python3 tools/volcar_gpu.py > gpu.txt

No lee nada que necesite permisos y no incluye números de serie. Una gráfica
que el sistema tiene dormida se queda dormida: de ella solo se lee quién es y
su estado de energía (ver `SIN_DESPERTAR`).
"""

from __future__ import annotations

import pathlib
import sys

RAIZ = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from silux import sysroot  # noqa: E402
from silux.volcado import POWER_FILES, SYS_DRM, _read, _resolved, is_asleep, power_state  # noqa: E402

# Lo que se busca en cada nodo. Las rutas con barra se prueban tal cual.
INTERESAN = (
    "gt_act_freq_mhz", "gt_cur_freq_mhz", "gt_max_freq_mhz", "gt_min_freq_mhz",
    "gt_boost_freq_mhz", "gt_RP0_freq_mhz", "gt_RP1_freq_mhz", "gt_RPn_freq_mhz",
    "gt/gt0/rps_act_freq_mhz", "gt/gt0/rps_cur_freq_mhz",
    "gt/gt0/rps_max_freq_mhz", "gt/gt0/rps_min_freq_mhz",
    "gt/gt0/rps_RP0_freq_mhz", "gt/gt0/rps_RP1_freq_mhz",
    "gt/gt0/rps_RPn_freq_mhz",
    "tile0/gt0/freq0/act_freq", "tile0/gt0/freq0/cur_freq",
    "tile0/gt0/freq0/max_freq", "tile0/gt0/freq0/min_freq",
)
EN_EL_NODO_PCI = (
    "subsystem_vendor", "subsystem_device", "revision",
    "gpu_busy_percent", "mem_busy_percent", "vcn_busy_percent",
    "mem_info_vram_total", "mem_info_vram_used", "mem_info_vis_vram_total",
    "mem_info_gtt_total", "mem_info_gtt_used",
    "current_link_speed", "current_link_width",
    "max_link_speed", "max_link_width",
    "pp_dpm_sclk", "pp_dpm_mclk", "power_dpm_force_performance_level",
    "resource", "boot_vga", "local_cpulist",
)


def _volcar(titulo: str, base, nombres) -> None:
    print(f"\n  [{titulo}]")
    vistos = 0
    for nombre in nombres:
        valor = _read(f"{base}/{nombre}")
        if valor is None:
            continue
        vistos += 1
        if "\n" in valor:
            print(f"    {nombre}:")
            for linea in valor.splitlines():
                print(f"      {linea}")
        else:
            print(f"    {nombre} = {valor}")
    if not vistos:
        print("    (ninguno de los que se buscan)")


def main() -> int:
    drm = pathlib.Path(sysroot.path(SYS_DRM))
    if not drm.is_dir():
        print("Este equipo no expone /sys/class/drm.", file=sys.stderr)
        return 1

    print(f"kernel: {_read('/proc/sys/kernel/osrelease')}")

    tarjetas = sorted(p.name for p in drm.glob("card*") if p.name[4:].isdigit())
    if not tarjetas:
        print("No hay ninguna tarjeta registrada.", file=sys.stderr)
        return 1

    for tarjeta in tarjetas:
        nodo = f"{SYS_DRM}/{tarjeta}"
        dispositivo = f"{nodo}/device"
        enlace = pathlib.Path(sysroot.path(f"{dispositivo}/driver"))
        driver = _resolved(enlace).name if enlace.exists() else None
        print(f"\n{'=' * 62}")
        print(f"{tarjeta}  ·  driver {driver or '?'}")
        try:
            print(f"  ranura: {_resolved(dispositivo).name}")
        except OSError:
            pass

        # Lo primero, antes de tocar nada que la despierte.
        estado = power_state(dispositivo)
        _volcar("energía", dispositivo, POWER_FILES)
        _volcar("identidad", dispositivo, ("vendor", "device", "class"))
        if is_asleep(estado):
            print("\n  La tarjeta está dormida: no se lee nada más de ella para no "
                  "despertarla. Para volcarla entera, que la use un programa "
                  "(o `power/control` a `on`) y se repite.")
            continue

        _volcar("nodo DRM: frecuencias", nodo, INTERESAN)
        _volcar("nodo PCI", dispositivo, EN_EL_NODO_PCI)

        # Qué hay dentro de gt/, que es donde el kernel moderno las guarda.
        for jerarquia in ("gt", "tile0"):
            directorio = pathlib.Path(sysroot.path(f"{nodo}/{jerarquia}"))
            if directorio.is_dir():
                print(f"\n  [árbol de {jerarquia}/]")
                for hijo in sorted(directorio.rglob("*")):
                    if hijo.is_file():
                        print(f"    {hijo.relative_to(directorio.parent)}")

        hwmon = pathlib.Path(sysroot.path(f"{dispositivo}/hwmon"))
        if hwmon.is_dir():
            for chip in sorted(hwmon.iterdir()):
                print(f"\n  [hwmon: {_read(chip / 'name')}]")
                for fichero in sorted(chip.glob("*_*")):
                    if (valor := _read(fichero)) is not None:
                        print(f"    {fichero.name} = {valor}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
