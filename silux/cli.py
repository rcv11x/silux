"""Interfaz de línea de órdenes.

Existe por tres razones, y las tres importan: sirve para depurar sin abrir la
ventana, produce JSON que otros programas pueden consumir (cosa que el
`--dump` de CPU-X no puede porque ya es texto) y es la prueba de que la capa
de datos no depende de Qt para nada.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import shutil
import sys
import time
from typing import Optional

from . import __version__, db, render, report
from .collector import Collector
from .model import Need, Snapshot, to_jsonable

NEED_LABELS = {
    Need.ROOT: "requiere root",
    Need.DATABASE: "falta en la base de datos",
    Need.HARDWARE: "no lo expone este hardware",
    Need.DRIVER: "falta un driver",
    Need.PLATFORM: "no aplica aquí",
}


class Style:
    """Colores ANSI, desactivados solos si la salida no es un terminal."""

    def __init__(self, enabled: bool) -> None:
        self.enabled = enabled

    def __call__(self, text: str, code: str) -> str:
        return f"\033[{code}m{text}\033[0m" if self.enabled else text

    def bold(self, text: str) -> str:
        return self(text, "1")

    def dim(self, text: str) -> str:
        return self(text, "2")

    def accent(self, text: str) -> str:
        return self(text, "38;5;173")

    def warn(self, text: str) -> str:
        return self(text, "38;5;179")


def _row(style: Style, label: str, value: str, width: int = 20) -> str:
    return f"  {style.dim(label.ljust(width))} {value}"


def dump(snapshot: Snapshot, style: Style) -> str:
    lines: list[str] = []
    cpu = snapshot.cpu

    for cpu_type in cpu.types:
        title = render.core_type_label(cpu_type, cpu.hybrid)
        lines.append(style.bold(style.accent(f"┌─ {title}")))
        lines.append(_row(style, "Fabricante", cpu_type.vendor or render.DASH))
        lines.append(_row(style, "Especificación", cpu_type.brand or render.DASH))
        lines.append(_row(style, "Nombre en clave", cpu_type.codename or render.DASH))
        lines.append(_row(style, "Tecnología", cpu_type.technology or render.DASH))
        lines.append(_row(style, "Encapsulado", cpu_type.socket or render.DASH))
        lines.append(_row(style, "Arquitectura", cpu_type.architecture or render.DASH))
        lines.append(_row(style, "Núcleos / hilos", f"{cpu_type.cores} / {cpu_type.threads}"))
        lines.append(_row(style, "Familia", render.hex_id(cpu_type.disp_family)))
        lines.append(_row(style, "Modelo", render.hex_id(cpu_type.disp_model)))
        lines.append(_row(style, "Stepping", str(cpu_type.stepping)))
        lines.append(_row(style, "Firma CPUID", render.signature(cpu_type.signature)))
        lines.append(_row(style, "Microcódigo", cpu_type.microcode or render.DASH))
        lines.append(_row(style, "Virtualización",
                          cpu_type.virtualization or "no soportada"))
        lines.append(_row(style, "Instrucciones", render.instructions(cpu_type)))
        lines.append("")

        clocks = cpu_type.clocks
        lines.append(style.bold(style.accent("├─ Relojes")))
        lines.append(_row(style, "Frecuencia", f"{render.hz(clocks.current_hz)}  {render.multiplier(clocks.multiplier)}"))
        lines.append(_row(style, "Base", f"{render.hz(clocks.base_hz)}  {render.multiplier(clocks.base_multiplier)}"))
        lines.append(_row(style, "Mínima", f"{render.hz(clocks.min_hz)}  {render.multiplier(clocks.min_multiplier)}"))
        lines.append(_row(style, "Máxima (kernel)", f"{render.hz(clocks.max_hz)}  {render.multiplier(clocks.max_multiplier)}"))
        lines.append(_row(style, "Máxima (silicio)", f"{render.hz(clocks.max_turbo_hz)}  {render.multiplier(clocks.max_turbo_multiplier)}"))
        lines.append(_row(style, "Bus (BCLK)", render.hz(clocks.bus_hz, 0)))
        lines.append(_row(style, "Driver", f"{clocks.driver or render.DASH} · {clocks.governor or render.DASH}"
                                            f" · {clocks.energy_preference or render.DASH}"))
        if note := render.turbo_note(clocks):
            lines.append(_row(style, "", style.warn(note)))
        lines.append("")

        lines.append(style.bold(style.accent("├─ Cachés")))
        for cache in cpu_type.caches:
            detail = render.cache_summary(cache)
            extra = f"línea {cache.line_bytes} B · compartida por {cache.shared_by} hilos"
            lines.append(_row(style, render.cache_label(cache), f"{detail}   {style.dim(extra)}"))
        lines.append("")

        lines.append(style.bold(style.accent("├─ Estado")))
        lines.append(_row(style, "Uso total", render.percent(cpu.usage_percent)))
        lines.append(_row(style, "Carga media",
                          render.load_average(cpu.load_average, cpu.total_threads)))
        lines.append(_row(style, "Temperatura", render.temperature(cpu_type.temp_c)))
        lines.append(_row(style, "Temp. paquete", render.temperature(cpu.package_temp_c)))
        power = cpu.power
        consumption = render.watts(power.package_w)
        if headline := render.power_headline(power):
            consumption += style.dim(f"   {headline}")
        lines.append(_row(style, "Consumo", consumption))
        if breakdown := render.power_breakdown(power):
            lines.append(_row(style, "", style.dim(breakdown)))
        if power.limit_long_w:
            lines.append(_row(style, "Límites", style.dim(
                f"{render.watts(power.limit_long_w)} sostenido · "
                f"{render.watts(power.limit_short_w)} de pico")))
        lines.append(_row(style, "Voltaje", render.volts(cpu_type.voltage_v)))
        lines.append("")

    if cpu.logical:
        lines.append(style.bold(style.accent("├─ Por núcleo")))
        columns = max(1, (shutil.get_terminal_size((100, 24)).columns - 4) // 34)
        cells = []
        for logical in cpu.logical:
            cells.append(
                f"  CPU{logical.index:<3} {render.hz(logical.freq_hz):>9}"
                f" {render.percent(logical.usage_percent):>7}"
                f" {render.temperature(logical.temp_c):>8}"
            )
        for i in range(0, len(cells), columns):
            lines.append("".join(cells[i : i + columns]))
        lines.append("")

    for gpu in snapshot.gpus:
        lines.append(style.bold(style.accent(f"├─ {gpu.display_name}")))
        lines.append(_row(style, "Fabricante", gpu.vendor or render.DASH))
        lines.append(_row(style, "Ensamblada por", gpu.subsystem_name or render.DASH))
        lines.append(_row(style, "Nombre en clave", gpu.codename or render.DASH))
        lines.append(_row(style, "Driver", f"{gpu.driver or render.DASH}"
                          + (f" · {gpu.driver_version}" if gpu.driver_version else "")))
        lines.append(_row(style, "Identificador", gpu.pci_id or render.DASH))
        lines.append(_row(style, "Subsistema", gpu.subsystem_id or render.DASH))
        lines.append(_row(style, "Ranura", gpu.pci_slot or render.DASH))
        lines.append(_row(style, "BIOS de video", gpu.vbios or render.DASH))
        lines.append(_row(style, "Enlace", render.pcie_link(gpu.link)))
        if nota := render.pcie_note(gpu.link):
            lines.append(_row(style, "", style.dim(nota)))

        lines.append(_row(style, "VRAM", render.gpu_memory_summary(gpu.memory)))
        detalle = " · ".join(p for p in (
            render.vram_kind(gpu.memory) if gpu.memory.kind else None,
            render.bandwidth(gpu.memory.bandwidth_bytes)
            if gpu.memory.bandwidth_bytes else None,
            f"chips de {gpu.memory.vendor}" if gpu.memory.vendor else None) if p)
        if detalle:
            lines.append(_row(style, "", style.dim(detalle)))
        lines.append(_row(style, "Núcleo", f"{render.hz(gpu.clocks.core_hz)}"
                          f"  de {render.hz(gpu.clocks.core_max_hz)}"))
        lines.append(_row(style, "Reloj de memoria", f"{render.hz(gpu.clocks.memory_hz)}"
                          f"  de {render.hz(gpu.clocks.memory_max_hz)}"))
        lines.append(_row(style, "Uso", render.percent(gpu.busy_percent)))
        lines.append(_row(style, "Temperatura", render.temperature(gpu.temp_c)))
        if gpu.hotspot_c is not None:
            lines.append(_row(style, "", style.dim(
                f"punto caliente {render.temperature(gpu.hotspot_c)}"
                f" · memoria {render.temperature(gpu.memory_temp_c)}")))
        consumo = render.watts(gpu.power_w)
        if gpu.power_cap_w:
            consumo += f"  de {render.watts(gpu.power_cap_w)}"
        lines.append(_row(style, "Consumo", consumo))
        lines.append(_row(style, "Ventilador", f"{render.rpm(gpu.fan_rpm)}"
                          + (f"  ({render.percent(gpu.fan_percent)})"
                             if gpu.fan_percent is not None else "")))
        unidades = " · ".join(p for p in (
            f"{gpu.compute_units} unidades de cómputo" if gpu.compute_units else None,
            f"{gpu.rops} ROP" if gpu.rops else None,
            f"{gpu.shader_engines} motores" if gpu.shader_engines else None) if p)
        lines.append(_row(style, "Unidades", unidades or render.DASH))

        for api in gpu.apis:
            lines.append(_row(style, api.name, render.gpu_api_summary(api)))
        for salida in gpu.displays:
            if salida.monitor:
                lines.append(_row(style, salida.connector,
                                  render.monitor_name(salida.monitor)))
                lines.append(_row(style, "", style.dim(
                    f"{render.display_mode(salida)} · "
                    f"{render.monitor_summary(salida.monitor)}")))
            else:
                lines.append(_row(style, salida.connector,
                                  style.dim(render.display_summary(salida))))
        lines.append("")

    if snapshot.sensors:
        lines.append(style.bold(style.accent("├─ Sensores")))
        for device, categories in snapshot.sensor_tree().items():
            lines.append(f"  {style.bold(device)}")
            for category, sensors in categories.items():
                lines.append(f"    {style.dim(category)}")
                for sensor in sensors:
                    digits = 0 if sensor.kind.value in ("fan", "energy") else (
                        3 if sensor.kind.value == "voltage" else 1)
                    value = f"{sensor.value:.{digits}f} {sensor.unit}".strip()
                    mark = style.warn(" ⚠") if sensor.alarm else ""
                    lines.append(f"      {sensor.label:<22} {value:>13}{mark}")
        lines.append("")

    if snapshot.driver_hints:
        lines.append(style.bold(style.accent("├─ Drivers de sensores que faltan")))
        for hint in snapshot.driver_hints:
            lines.append(f"  {style.warn('•')} {style.bold(hint.module)}: {hint.provides}")
            lines.append(f"    {hint.command}")
            if hint.caution:
                lines.append(f"    {style.dim(hint.caution)}")
        lines.append("")

    if snapshot.notes:
        lines.append(style.bold(style.accent("└─ Datos que faltan y por qué")))
        for note in snapshot.notes:
            tag = NEED_LABELS.get(note.need, note.need.value)
            lines.append(f"  {style.warn('•')} {style.bold(note.path)} {style.dim('(' + tag + ')')}")
            lines.append(f"    {note.message}")
            if note.hint:
                lines.append(f"    {style.dim(note.hint)}")
    return "\n".join(lines)


def watch(collector: Collector, style: Style, interval: float) -> int:
    print("\033[?25l", end="")            # oculta el cursor
    try:
        while True:
            snapshot = collector.snapshot()
            body = dump(snapshot, style)
            print("\033[H\033[J" + body, flush=True)
            time.sleep(interval)
    except KeyboardInterrupt:
        return 0
    finally:
        print("\033[?25h", end="")        # y lo devuelve


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="silux", description="Perfilador de hardware para Linux."
    )
    parser.add_argument("--json", action="store_true", help="salida en JSON para otros programas")
    parser.add_argument("--sensors", action="store_true",
                        help="solo el árbol de sensores, como hace HWMonitor")
    parser.add_argument("--watch", nargs="?", type=float, const=1.0, metavar="SEGUNDOS",
                        help="refresca de forma continua (por defecto cada segundo)")
    parser.add_argument("--no-color", action="store_true", help="sin colores ANSI")
    parser.add_argument("--report", nargs="?", const="-", metavar="ARCHIVO",
                        help="informe en Markdown para pegar en un issue; "
                             "sin archivo, lo escribe por pantalla")
    parser.add_argument("--with-identifiers", action="store_true",
                        help="incluye en el informe lo que identifica al equipo "
                             "(nombre, IP, MAC, números de serie)")
    parser.add_argument("--db-info", action="store_true", help="de dónde salió la base de datos")
    parser.add_argument("--version", action="version", version=f"silux {__version__}")
    args = parser.parse_args(argv)

    style = Style(enabled=not args.no_color and sys.stdout.isatty())

    if args.db_info:
        if not db.available():
            print("No hay base de datos. Genérala con: python3 tools/gen_cpu_db.py", file=sys.stderr)
            return 1
        data = db.load()
        print(json.dumps({"sources": data["sources"], "counts": data["counts"]},
                         indent=2, ensure_ascii=False))
        return 0

    collector = Collector()

    if args.watch is not None:
        collector.snapshot()
        return watch(collector, style, max(0.1, args.watch))

    snapshot = collector.sample()

    if args.sensors:
        for device, categories in snapshot.sensor_tree().items():
            print(style.bold(device))
            for category, sensors in categories.items():
                print(f"  {style.dim(category)}")
                for sensor in sensors:
                    digits = 3 if sensor.kind.value == "voltage" else 1
                    mark = style.warn(" ⚠") if sensor.alarm else ""
                    print(f"    {sensor.label:<24} "
                          f"{sensor.value:>10.{digits}f} {sensor.unit}{mark}")
        return 0

    if args.report:
        texto = report.build(snapshot, anonymous=not args.with_identifiers)
        if args.report == "-":
            sys.stdout.write(texto)
        else:
            try:
                pathlib.Path(args.report).write_text(texto, encoding="utf-8")
            except OSError as error:
                print(f"No se pudo escribir el informe: {error}", file=sys.stderr)
                return 1
            print(f"Informe guardado en {args.report}")
            if not args.with_identifiers:
                print("Se han omitido el nombre del equipo, las direcciones IP y "
                      "MAC y los números de serie.\n"
                      "Para incluirlos:  --report ARCHIVO --with-identifiers")
        return 0

    if args.json:
        json.dump(to_jsonable(snapshot), sys.stdout, indent=2, ensure_ascii=False)
        sys.stdout.write("\n")
        return 0

    print(dump(snapshot, style))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
