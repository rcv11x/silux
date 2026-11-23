"""Command line interface.

It exists for three reasons: debugging without opening the window, JSON
that other programs can consume (which CPU-X's `--dump` can't give, being
text already), and proof that the data layer doesn't depend on Qt at all.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import shutil
import sys
import time
from typing import Optional

from . import __version__, build_id, db, render, report
from .collector import Collector
from .i18n import _
from .model import Need, SensorKind, Snapshot, to_jsonable

NEED_LABELS = {
    Need.ROOT: "requiere root",
    Need.DATABASE: "esta versión no lo conoce todavía",
    Need.HARDWARE: "no lo expone este hardware",
    Need.DRIVER: "falta un driver",
    Need.PLATFORM: "no aplica aquí",
    Need.ERROR: "falló al leerse",
    Need.KERNEL: "kernel anterior al dato",
    Need.PACKAGE: "falta un paquete",
}


class Style:
    """ANSI colours, turned off on their own when the output isn't a terminal."""

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
        lines.append(_row(style, "Nombre en clave", render.from_cpu_table(cpu_type.codename)))
        lines.append(_row(style, "Tecnología", render.from_cpu_table(cpu_type.technology)))
        lines.append(_row(style, "Encapsulado", render.from_cpu_table(cpu_type.socket)))
        lines.append(_row(style, "Arquitectura", cpu_type.architecture or render.DASH))
        lines.append(_row(style, "Núcleos / hilos", f"{cpu_type.cores} / {cpu_type.threads}"))
        lines.append(_row(style, "Familia", render.hex_id(cpu_type.disp_family)))
        lines.append(_row(style, "Modelo", render.hex_id(cpu_type.disp_model)))
        lines.append(_row(style, "Stepping", render.dec(cpu_type.stepping)))
        lines.append(_row(style, "Firma CPUID", render.signature(cpu_type.signature)))
        lines.append(_row(style, "Microcódigo", cpu_type.microcode or render.DASH))
        lines.append(_row(style, "Virtualización",
                          cpu_type.virtualization or "no soportada"))
        lines.append(_row(style, "Instrucciones", render.instructions(cpu_type)))
        lines.append("")

        clocks = cpu_type.clocks
        lines.append(style.bold(style.accent("├─ Relojes")))
        lines.append(_row(style, "Frecuencia", f"{render.hz(clocks.current_hz)}  {render.multiplier(clocks.multiplier)}"))
        lines.append(_row(style, "Base", render.clock_and_multiplier(clocks.base_hz, clocks.base_multiplier)))
        if configured := render.configured_base(clocks):
            lines.append(_row(style, _("cpu.clock.base.tdp"), configured))
        lines.append(_row(style, "Mínima", f"{render.hz(clocks.min_hz)}  {render.multiplier(clocks.min_multiplier)}"))
        lines.append(_row(style, "Máxima (kernel)", f"{render.hz(clocks.max_hz)}  {render.multiplier(clocks.max_multiplier)}"))
        lines.append(_row(style, "Máxima (silicio)", f"{render.hz(clocks.max_turbo_hz)}  {render.multiplier(clocks.max_turbo_multiplier)}"))
        lines.append(_row(style, "Bus (BCLK)", render.hz(clocks.bus_hz, 0)))
        lines.append(_row(style, "Driver", f"{clocks.driver or render.DASH} · {clocks.governor or render.DASH}"
                                            f" · {clocks.energy_preference or render.DASH}"))
        if note := render.turbo_note(clocks):
            lines.append(_row(style, "", style.warn(note)))
        if spread := render.core_quality_spread(snapshot.cpu.logical):
            lines.append(_row(style, "Mejores núcleos",
                              f"{render.best_cores(snapshot.cpu.logical)} · {spread}"))
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
        lines.append(style.bold(style.accent(f"├─ {render.gpu_name(gpu)}")))
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
        if link_note := render.pcie_note(gpu.link):
            lines.append(_row(style, "", style.dim(link_note)))

        # If how much is used isn't known, at least say how much there is.
        summary = render.gpu_memory_summary(gpu.memory)
        if summary == render.DASH and gpu.memory.total_bytes:
            summary = render.size(gpu.memory.total_bytes)
        lines.append(_row(style, "VRAM", summary))
        detail_text = " · ".join(p for p in (
            f"{render.vram_kind(gpu.memory)} · {render.vram_bus(gpu.memory)}"
            if gpu.memory.kind else None,
            render.bandwidth(gpu.memory.bandwidth_bytes)
            if gpu.memory.bandwidth_bytes else None,
            f"chips de {gpu.memory.vendor}" if gpu.memory.vendor else None) if p)
        if detail_text:
            lines.append(_row(style, "", style.dim(detail_text)))
        lines.append(_row(style, "Núcleo", f"{render.gpu_clock(gpu.clocks.core_hz)}"
                          f"  de {render.hz(gpu.clocks.core_max_hz)}"))
        lines.append(_row(style, "Reloj de memoria", f"{render.hz(gpu.clocks.memory_hz)}"
                          f"  de {render.hz(gpu.clocks.memory_max_hz)}"))
        lines.append(_row(style, "Uso", render.percent(gpu.busy_percent)))
        if gpu.sleep_percent is not None:
            lines.append(_row(style, "En reposo", render.percent(gpu.sleep_percent)))
        for engine in gpu.engines:
            # The per-engine detail is what tells «the card can't give more»
            # from «only the video decoder is busy».
            detail_text = " · ".join(p for p in (
                engine.kind, ", ".join(engine.capabilities) or None) if p)
            lines.append(_row(style, f"  {engine.name}",
                              f"{render.percent(engine.busy_percent)}"
                              + (f"  {style.dim(detail_text)}" if detail_text else "")))
        if gpu.codecs:
            lines.append(_row(style, "Códecs", ""))
            for codec in gpu.codecs:
                flags = ("decodifica" if codec.decode else "") + \
                         (" y codifica" if codec.encode and codec.decode
                          else "codifica" if codec.encode else "")
                if codec.max_bit_depth:
                    flags += f" · {codec.max_bit_depth} bits"
                lines.append(_row(style, f"  {codec.name}", style.dim(flags)))
        lines.append(_row(style, "Temperatura", render.temperature(gpu.temp_c)))
        if gpu.hotspot_c is not None:
            lines.append(_row(style, "", style.dim(
                f"punto caliente {render.temperature(gpu.hotspot_c)}"
                f" · memoria {render.temperature(gpu.memory_temp_c)}")))
        power_text = render.watts(gpu.power_w)
        if gpu.power_cap_w:
            power_text += f"  de {render.watts(gpu.power_cap_w)}"
        lines.append(_row(style, "Consumo", power_text))
        lines.append(_row(style, "Ventilador", f"{render.rpm(gpu.fan_rpm)}"
                          + (f"  ({render.percent(gpu.fan_percent)})"
                             if gpu.fan_percent is not None else "")))
        units = " · ".join(p for p in (
            render.compute_units(gpu) if gpu.compute_units else None,
            f"{gpu.rops} ROP" if gpu.rops else None,
            f"{gpu.shader_engines} motores" if gpu.shader_engines else None) if p)
        lines.append(_row(style, "Unidades", units or render.DASH))

        for api in gpu.apis:
            lines.append(_row(style, api.name, render.gpu_api_summary(api)))
        for output in gpu.displays:
            if output.monitor:
                lines.append(_row(style, output.connector,
                                  render.monitor_name(output.monitor)))
                lines.append(_row(style, "", style.dim(
                    f"{render.display_mode(output)} · "
                    f"{render.monitor_summary(output.monitor)}")))
            else:
                lines.append(_row(style, output.connector,
                                  style.dim(render.display_summary(output))))
        lines.append("")

    if snapshot.sensors:
        lines.append(style.bold(style.accent("├─ Sensores")))
        for categories in snapshot.sensor_tree().values():
            lines.append(f"  {style.bold(Snapshot.device_name(categories))}")
            for category, sensors in categories.items():
                lines.append(f"    {style.dim(category)}")
                for sensor in sensors:
                    digits = 0 if sensor.kind.value in ("fan", "energy") else (
                        3 if sensor.kind.value == "voltage" else 1)
                    value = (render.temperature(sensor.value)
                             if sensor.kind is SensorKind.TEMPERATURE
                             else f"{sensor.value:.{digits}f} {sensor.unit}".strip())
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


def sensors_text(snapshot: Snapshot, style: Style) -> str:
    """The sensor tree, as `--sensors` shows it."""
    lines = []
    for categories in snapshot.sensor_tree().values():
        lines.append(style.bold(Snapshot.device_name(categories)))
        for category, sensors in categories.items():
            # The category is a key («cat.temperature»): translated, as in the
            # window and the report.
            lines.append(f"  {style.dim(_(category))}")
            for sensor in sensors:
                digits = 3 if sensor.kind.value == "voltage" else 1
                mark = style.warn(" ⚠") if sensor.alarm else ""
                # A temperature through its format; the rest as it comes.
                reading = (f"{render.temperature(sensor.value):>13}"
                           if sensor.kind is SensorKind.TEMPERATURE
                           else f"{sensor.value:>10.{digits}f} {sensor.unit}")
                lines.append(f"    {sensor.label:<24} {reading}{mark}")
    return "\n".join(lines)


def watch(collector: Collector, style: Style, interval: float,
          only_sensors: bool = False) -> int:
    """Repeat every `interval` seconds. With `--sensors`, only the sensor
    tree: the help gives that as an example («the sensors, every second»)
    and the whole dump came out."""
    collector.interval_s = interval
    print("\033[?25l", end="")            # hide the cursor
    try:
        while True:
            snapshot = collector.snapshot()
            body = sensors_text(snapshot, style) if only_sensors else dump(snapshot, style)
            print("\033[H\033[J" + body, flush=True)
            time.sleep(interval)
    except KeyboardInterrupt:
        return 0
    finally:
        print("\033[?25h", end="")        # and bring it back


def _sections() -> list[str]:
    """The sections the full report can be asked for. Written here rather than
    imported from the interface, so the help comes out without Qt."""
    return ["home", "cpu", "caches", "board", "memory", "graphics", "storage",
            "network", "devices", "battery", "system", "benchmark", "sensors"]


def qt_can_start() -> bool:
    """Whether Qt can start here, for the full report, which builds the
    window without a screen.

    On a processor without x86-64-v2, Qt 6.10 and later die with «Illegal
    instruction» while loading, before anything can be said. Inside the
    AppImage, Python's guard can't tell which PySide6 it carries (it is
    copied, not installed), so it looks at the build's mark: `-compat`
    carries a Qt that starts on any x86-64.
    """
    import importlib.util

    if importlib.util.find_spec("PySide6") is None:
        return False
    from .ui import guarda

    if not guarda.banderas_que_faltan():
        return True
    if (build_id() or "").endswith("-compat"):
        return True
    version = guarda.version_de_pyside()
    return version is not None and version < (6, 10)


def build_parser() -> argparse.ArgumentParser:
    """The terminal dump's options.

    Kept apart so they can be listed without running anything: the AppImage
    dispatches between the interface and this by how it is called, and a
    test checks against this list that none is left out. Nor the Spanish
    aliases.

    The texts are in the interface's language: the caller sets it first
    (`main`, with the saved preferences).
    """
    from .options import Parser, epilog_for_cli, how_to_call

    _window, terminal = how_to_call()
    parser = Parser(prog=terminal, description=_("cli.description"),
                    epilog=epilog_for_cli())
    parser.add_argument("--report", nargs="?", const="-", metavar=_("cli.metavar.file"),
                        help=_("cli.opt.report"))
    parser.add_argument("--short", action="store_true", help=_("cli.opt.short"))
    parser.add_argument("--sections", metavar=_("cli.metavar.sections"),
                        help=_("cli.opt.sections").format(
                            lista=", ".join(_sections())))
    parser.add_argument("--without-permissions", action="store_true",
                        help=_("cli.opt.withoutperms"))
    parser.add_argument("--json", action="store_true", help=_("cli.opt.json"))
    parser.add_argument("--sensors", action="store_true", help=_("cli.opt.sensors"))
    parser.add_argument("--watch", nargs="?", type=float, const=1.0,
                        metavar=_("cli.metavar.seconds"), help=_("cli.opt.watch"))
    parser.add_argument("--no-color", action="store_true", help=_("cli.opt.nocolor"))
    parser.add_argument("--with-identifiers", action="store_true", help=_("cli.opt.ids"))
    parser.add_argument("--db-info", action="store_true", help=_("cli.opt.dbinfo"))
    parser.add_argument("--version", action="version", help=_("cli.version"),
                        version=f"silux {__version__}"
                                + (f" ({build_id()})" if build_id() else ""))
    for spanish, english in (("--informe", "--report"), ("--sensores", "--sensors"),
                            ("--vigilar", "--watch"), ("--sin-color", "--no-color"),
                            ("--con-identificadores", "--with-identifiers"),
                            ("--base-de-datos", "--db-info"), ("--corto", "--short"),
                            ("--secciones", "--sections"),
                            ("--sin-permisos", "--without-permissions")):
        parser.alias(spanish, of=english)
    return parser


def _comma_list(text: Optional[str]) -> Optional[list[str]]:
    if not text:
        return None
    return [s.strip() for s in text.split(",") if s.strip()]


def main(argv: Optional[list[str]] = None) -> int:
    # The interface's language, the one chosen in Settings: the help and the
    # report come out in it.
    from . import i18n, settings
    i18n.set_language(settings.load().language)
    parser = build_parser()
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
        return watch(collector, style, max(0.1, args.watch), only_sensors=args.sensors)

    if args.report == "":
        parser.error(_("cli.report.empty"))
    if args.report and args.sections and not args.short and qt_can_start():
        # Before asking for the password: a typo shouldn't cost it.
        from .ui import full_report
        unknown = full_report.unknown_sections(_comma_list(args.sections))
        if unknown:
            print(_("cli.report.unknownsection").format(
                names=", ".join(unknown), known=", ".join(full_report.section_ids())),
                file=sys.stderr)
            return 2

    if args.report and not args.short and not args.without_permissions:
        # The report is for understanding a failure, and what only the
        # administrator sees (the memory, the disks' health) is often what's
        # needed. Asked for at the start, as in the window.
        from .privileged.client import already_root
        if not already_root():
            print(_("cli.report.asking"), file=sys.stderr)
            collector.request_elevation()
    snapshot = collector.sample()

    if args.sensors:
        print(sensors_text(snapshot, style))
        return 0

    if args.report:
        full = not args.short and qt_can_start()
        if not args.short and not full:
            print(_("cli.report.noqt"), file=sys.stderr)
        if full:
            from .ui import full_report
            text = full_report.build(snapshot, sections=_comma_list(args.sections),
                                      anonymous=not args.with_identifiers)
            if not args.sections:
                # What it read to show all that, to reproduce it in the
                # tests; a chosen part of the report is not for that.
                from . import annex
                block, reason = annex.of_this_machine()
                text = text.rstrip("\n") + "\n" + annex.section(block, reason)
        else:
            text = report.build(snapshot, anonymous=not args.with_identifiers)
        if args.report == "-":
            sys.stdout.write(text)
        else:
            try:
                pathlib.Path(args.report).write_text(text, encoding="utf-8")
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
