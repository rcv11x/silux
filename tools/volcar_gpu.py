#!/usr/bin/env python3
"""Vuelca lo que el kernel publica de cada gráfica, para diagnosticar a ciegas.

Cuando a alguien le sale una tarjeta a medias, lo que hace falta no es la
captura: es saber qué archivos existen en su equipo y qué dicen. Los drivers
cambian de sitio los datos entre versiones —i915 movió las frecuencias a
`gt/gt0/` en el kernel 6.2 y dejó las viejas donde estaban— y desde otra
máquina no hay forma de adivinar cuál de las rutas tiene.

    python3 tools/volcar_gpu.py > gpu.txt

No lee nada que necesite permisos y no incluye números de serie.
"""

from __future__ import annotations

import pathlib
import sys

SYS_DRM = pathlib.Path("/sys/class/drm")

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
    "vendor", "device", "subsystem_vendor", "subsystem_device", "revision",
    "gpu_busy_percent", "mem_busy_percent", "vcn_busy_percent",
    "mem_info_vram_total", "mem_info_vram_used", "mem_info_vis_vram_total",
    "mem_info_gtt_total", "mem_info_gtt_used",
    "current_link_speed", "current_link_width",
    "max_link_speed", "max_link_width",
    "pp_dpm_sclk", "pp_dpm_mclk", "power_dpm_force_performance_level",
    "resource", "boot_vga", "local_cpulist",
)


def _leer(ruta: pathlib.Path) -> str | None:
    try:
        return ruta.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return None


def _volcar(titulo: str, base: pathlib.Path, nombres) -> None:
    print(f"\n  [{titulo}]")
    vistos = 0
    for nombre in nombres:
        ruta = base / nombre
        valor = _leer(ruta)
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
    if not SYS_DRM.is_dir():
        print("Este equipo no expone /sys/class/drm.", file=sys.stderr)
        return 1

    print(f"kernel: {_leer(pathlib.Path('/proc/sys/kernel/osrelease'))}")

    tarjetas = sorted(p for p in SYS_DRM.glob("card*") if p.name[4:].isdigit())
    if not tarjetas:
        print("No hay ninguna tarjeta registrada.", file=sys.stderr)
        return 1

    for nodo in tarjetas:
        dispositivo = nodo / "device"
        driver = None
        try:
            driver = (dispositivo / "driver").resolve().name
        except OSError:
            pass
        print(f"\n{'=' * 62}")
        print(f"{nodo.name}  ·  driver {driver or '?'}")
        try:
            print(f"  ranura: {dispositivo.resolve().name}")
        except OSError:
            pass

        _volcar("nodo DRM: frecuencias", nodo, INTERESAN)
        _volcar("nodo PCI", dispositivo, EN_EL_NODO_PCI)

        # Qué hay dentro de gt/, que es donde el kernel moderno las guarda.
        for jerarquia in ("gt", "tile0"):
            directorio = nodo / jerarquia
            if directorio.is_dir():
                print(f"\n  [árbol de {jerarquia}/]")
                for hijo in sorted(directorio.rglob("*")):
                    if hijo.is_file():
                        print(f"    {hijo.relative_to(nodo)}")

        hwmon = dispositivo / "hwmon"
        if hwmon.is_dir():
            for chip in sorted(hwmon.iterdir()):
                print(f"\n  [hwmon: {_leer(chip / 'name')}]")
                for fichero in sorted(chip.glob("*_*")):
                    if (valor := _leer(fichero)) is not None:
                        print(f"    {fichero.name} = {valor}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
