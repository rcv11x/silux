"""The helper never outlives Silux.

It runs as root, so it must go when Silux goes: on a normal close, and also
when Silux hangs and is killed and nothing gets to close it. It reads its
requests from Silux's pipe and ends at the end of that pipe, which the kernel
closes with the process, whatever kills it.

The helper runs for real here, without root: in its own process `geteuid` is
made to say 0, which is the only thing it checks.
"""

import os
import pathlib
import signal
import subprocess
import sys
import time
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent

# A stand-in for Silux: connects the real client to the real helper, says the
# helper's pid and waits to be killed.
FAKE_SILUX = f"""
import sys, time
sys.path.insert(0, {str(ROOT)!r})
from silux.privileged import client
helper = [sys.executable, "-I", "-c",
          "import os, runpy, sys; os.geteuid = lambda: 0; "
          "runpy.run_path(sys.argv[1], run_name='__main__')", str(client.HELPER)]
c = client.PrivilegedClient()
c._orden = lambda: helper
c.supported = lambda: True
c.connect()
print(c._process.pid, flush=True)
if sys.argv[1:] == ["close"]:
    c.close()
    print("closed", flush=True)
time.sleep(120)
"""


def _alive(pid: int) -> bool:
    try:
        estado = pathlib.Path(f"/proc/{pid}/stat").read_text().split(")")[-1].split()[0]
    except OSError:
        return False
    return estado != "Z"


def _wait_gone(pid: int, seconds: float = 5.0) -> bool:
    fin = time.monotonic() + seconds
    while time.monotonic() < fin:
        if not _alive(pid):
            return True
        time.sleep(0.05)
    return False


class TestTheHelperGoesWithSilux(unittest.TestCase):

    def _start(self, *args):
        silux = subprocess.Popen([sys.executable, "-c", FAKE_SILUX, *args],
                                 stdout=subprocess.PIPE, text=True)
        self.addCleanup(lambda: silux.poll() is None and silux.kill())
        helper = int(silux.stdout.readline())
        self.addCleanup(lambda: _alive(helper) and os.kill(helper, signal.SIGKILL))
        self.assertTrue(_alive(helper))
        return silux, helper

    def test_when_silux_is_killed(self):
        silux, helper = self._start()
        silux.kill()                            # SIGKILL: nothing gets to close it
        silux.wait()
        self.assertTrue(_wait_gone(helper), "the helper outlived a killed Silux")

    def test_when_silux_closes_it(self):
        silux, helper = self._start("close")
        self.assertEqual(silux.stdout.readline().strip(), "closed")
        self.assertTrue(_wait_gone(helper), "the helper outlived its close")


if __name__ == "__main__":
    unittest.main()
