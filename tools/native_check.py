"""Check that a built AppImage measures with its native module.

Run with the AppImage's own interpreter, extracted, so that what is checked
is what ships:

    ./silux-x86_64.AppImage --appimage-extract > /dev/null
    PYTHONHOME=squashfs-root/usr PYTHONPATH=squashfs-root/usr/lib/python \\
        squashfs-root/usr/bin/python3 tools/native_check.py

A short memory test, as the window runs it (in a child process): the module
loads, the curve and a pass come back with figures. Exits 1 with the reason
if not.
"""

import sys

KIB, MIB = 1024, 1024 * 1024


def fail(message: str) -> int:
    print(f"native check: {message}", file=sys.stderr)
    return 1


def main() -> int:
    from silux import memtest

    native = memtest.native_module()
    if native is None:
        return fail("silux_bench doesn't load")
    print("silux_bench", ", ".join(native.instruction_sets()))
    cpus = tuple(native.allowed_cpus()[:2])
    plan = memtest.Plan(cpu=cpus[0], cpus=cpus, sizes=memtest.curve_sizes(64 * KIB),
                        ram_block=None, ram_block_limited=False, single_bytes=2 * MIB,
                        multi_bytes=2 * MIB if len(cpus) > 1 else None,
                        caches=(("L1", 32 * KIB),))
    result = memtest.run(plan)
    if result.engine != "native" or result.reason is not None:
        return fail(f"memory test: {result.engine} {result.reason} {result.detail}")
    if not result.points or not result.rates:
        return fail("memory test: no figures")
    print(f"memory: L1 {result.level('L1').nanoseconds:.2f} ns, "
          f"read {result.rate('read', 1).bytes_per_second / 1e9:.1f} GB/s "
          f"({result.rates[0].isa})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
