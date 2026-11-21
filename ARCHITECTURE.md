# Architecture

A short map of the code. The long version, with the reason behind each
rule and every module commented, is [docs/arquitectura.md](docs/arquitectura.md)
(in Spanish until 0.4).

## How a reading travels

```
kernel (/sys, /proc, ioctl, CPUID)      root helper (SMBIOS, MSR, SMART, PMU)
          │                                       │ through a pipe, after pkexec
          ▼                                       ▼
   providers/*  ──── write into a mutable Draft ───
          │
   Collector.snapshot()   static data is read once and cloned;
          │               dynamic data, on every sample
          ▼
   Snapshot (frozen)      numbers, never text
          │
   ui/sampler.py          a QThread: nothing is read on the interface thread
          │  `sampled` signal
          ▼
   MainWindow             the open page gets `apply(snapshot)`;
          │               the others keep their history with `record(snapshot)`
          ▼
   render.py              the only place where a number becomes text
```

Each provider reads one source and knows none of the others. When it cannot
read something it says why, with a `Note` and its `Need` (permissions, a
kernel module, a package, hardware that does not have it, or a failure of
ours). The `Collector` calls them in an order that matters and is commented
in `collector.py`.

## The rules

They are not style: each one comes from something that went wrong.

1. **The model holds numbers, not text.** All formatting lives in
   `silux/render.py`, at paint time.
2. **`Snapshot` is immutable.** Pages compare snapshots and repaint what
   changed.
3. **`cpu.types` is a list**: a hybrid Intel has P and E cores with
   different caches and clocks.
4. **Nothing is read on the interface thread.**
5. **A missing value is explained**, never hidden or painted as a dash.
   What this hardware does not have is hidden and named below; what needs
   permissions carries a padlock.
6. **Widgets refreshed often reuse what exists.**
7. **A budget**: 300 MB of memory and a few percent of one core
   (`tools/medir_consumo.py` checks it).
8. **What costs memory for good runs in another process**: the graphics
   APIs are asked in a child that exits after answering.
9. **The interface responds at once**: what changes is seen on the open
   page.

And, from the reports of people's machines:

- No rate from two counter readings without a valid window
  (`providers/counters.py`).
- Logic never decides on translated text: codes and keys, translated at
  paint time.
- A chart draws one series, with its key and unit.
- Silux's own failures are errors with their traceback in the report, never
  «this machine does not have it».

## Where things are

```
silux/
├─ model.py         frozen dataclasses: Snapshot, CpuType, Sensor, Board…
├─ render.py        the only place a value becomes text
├─ collector.py     runs the providers; their order matters
├─ failures.py      Silux's own failures, kept for the report
├─ cli.py           terminal output, JSON, sensors and the report
├─ report.py        the Markdown report for bug reports
├─ privacidad.py    what identifies someone: the report and screenshots
├─ volcado.py       dumping this machine, anonymized (tests and the annex)
├─ providers/       one source each
├─ privileged/      the root helper, its client, installer and module loader
├─ db/              CPU tables, languages (lang/es.json, lang/en.json)
└─ ui/              theme, sampler thread, one page per section
tests/
├─ fixtures/equipos/   dumped machines, replayed with SILUX_SYSROOT
└─ fixtures/screens/   what each dump shows, page by page
tools/              generators, packaging, dumps and checks
```

## Testing against real machines

A dump is a machine's `/sys`, `/proc` and recorded answers (CPUID, NVML,
graphics APIs), anonymized. Every test that reads hardware runs against
each dump, and `tests/fixtures/screens/` holds what each one shows, so a
change that alters a machine's pages fails until the reference is rebuilt
and its diff reviewed. `tools/dump_fingerprint.py` does the same for the
JSON and the report.
