"""A test's child process dies with Silux, however Silux ends.

Each child's `main` runs here in a process of its own, with its measure
replaced by one that asks the kernel what the child will get when its parent
ends (PR_GET_PDEATHSIG). Nothing is measured.
"""

import json
import pathlib
import signal
import subprocess
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent

CHILD = """
import ctypes, sys
from silux import {module} as test

def ask(plan, emit):
    signal_number = ctypes.c_int()
    ctypes.CDLL(None).prctl(2, ctypes.byref(signal_number), 0, 0, 0)  # PR_GET_PDEATHSIG
    return {{"on_parent_death": signal_number.value}}

test._measure = ask
sys.argv = ["child", "{{}}"]
test.main()
"""


def _on_parent_death(module: str) -> int:
    done = subprocess.run([sys.executable, "-c", CHILD.format(module=module)],
                          cwd=ROOT, capture_output=True, text=True, timeout=60)
    last = [line for line in done.stdout.splitlines() if line.strip()][-1]
    return json.loads(last)["result"]["on_parent_death"]


@unittest.skipUnless(sys.platform.startswith("linux"), "prctl is Linux's")
class TestTheChildDiesWithItsParent(unittest.TestCase):

    def test_the_memory_tests(self):
        self.assertEqual(_on_parent_death("memtest"), signal.SIGKILL)

    def test_the_disk_tests(self):
        self.assertEqual(_on_parent_death("disktest"), signal.SIGKILL)


if __name__ == "__main__":
    unittest.main()
