"""How the CI splits the suite between its jobs (`tests/conftest.py`).

The width tests check every page of every dump at every font size: the
longest of the suite. The CI runs them with the normal package's Python and
PySide6 only. The normal job is split in two halves that, together, run
every test once.
"""

# Classes whose tests are width tests, as they appear in a test's node id.
WIDTH_CLASSES = ("TestEveryFontAt720", "TestTheLargestFontInANarrowWindow")


def is_width_test(nodeid: str) -> bool:
    return any(f"::{name}::" in nodeid for name in WIDTH_CLASSES)


def part_of(nodeids, spec: str) -> set:
    """The node ids of part «N/M»: every M-th, from the N-th, in name order.

    By name, so that every xdist worker and both jobs agree, and every M-th
    rather than a block, so that a dump's long tests are shared out.
    """
    number, total = (int(n) for n in spec.split("/"))
    if not 1 <= number <= total:
        raise ValueError(f"no part {spec}")
    return set(sorted(nodeids)[number - 1::total])
