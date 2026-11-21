"""A processor without a frequency driver: a tester's Athlon 3000G read
«Frecuencia: —» everywhere, «Turbo: —» on a part with no turbo, and a
notice blaming a missing kernel module when the BIOS may be the cause.

The machine here is the 5800X3D's dump with what such a machine lacks taken
away the way the kernel shows it: no `cpuN/cpufreq` and no `cpufreq/boost`
(no driver registered), and for the Athlon's case no ACPI CPPC and no `cpb`
flag (no Core Performance Boost). The P-state registers are the 5800X3D's,
read through the helper on 20 November 2026.
"""

import contextlib
import pathlib
import re
import shutil
import unittest

from silux import render, volcado
from silux.collector import Collector
from silux.i18n import _
from silux.model import Need
from silux.privileged.client import HelperError
from silux.providers import msr_pstate
from silux.providers.msr_pstate import AmdPstateClocks
from silux.providers.msr_voltage import MsrVoltage
from silux.providers.sysfs_cpu import cpuinfo_mhz
from tests import pantalla, qt

EQUIPOS = pathlib.Path(__file__).resolve().parent / "fixtures" / "equipos"

# The 5800X3D's P-state MSRs, as the helper read them on every thread.
P_STATES_5800X3D = {0xC0010063: 0x0, 0xC0010064: 0x8000000048920888,
                    0xC0010065: 0x8000000047160A8C, 0xC0010066: 0x80000000459A0C84}


class _Helper:
    """The helper as the providers see it, answering what the 5800X3D's did."""

    def __init__(self, values=P_STATES_5800X3D, fails=False):
        self.values, self.fails, self.reads = values, fails, 0

    def connected(self):
        return True

    def close(self):
        pass

    def read_msr(self, cpu, registers):
        self.reads += 1
        if self.fails:
            raise HelperError("no msr module")
        return {r: self.values[r] for r in registers if r in self.values}


@contextlib.contextmanager
def _machine(dump="5800x3d", cppc=True, boost_flag=True):
    """The dump mounted without a frequency driver (and, if asked, without
    CPPC or the turbo flag)."""
    with volcado.montado(EQUIPOS / dump) as root:
        cpus = root / "sys/devices/system/cpu"
        for gone in [*cpus.glob("cpu[0-9]*/cpufreq"), cpus / "cpufreq" / "boost",
                     *([] if cppc else cpus.glob("cpu[0-9]*/acpi_cppc"))]:
            if gone.is_symlink() or gone.is_file():
                gone.unlink()
            elif gone.is_dir():
                shutil.rmtree(gone)
        if not boost_flag:
            cpuinfo = root / "proc/cpuinfo"
            cpuinfo.write_text(re.sub(r" cpb(?= )", "", cpuinfo.read_text()))
        yield root


def _photo(helper=None):
    collector = Collector()
    if helper is not None:
        for provider in collector.providers:
            if isinstance(provider, (AmdPstateClocks, MsrVoltage)):
                provider.client = helper
    try:
        collector.snapshot()
        return collector.snapshot()
    finally:
        collector.close()


class TestAZenPstate(unittest.TestCase):
    """200 MHz × CpuFid / CpuDfsId, from AMD's PPR for families 17h and 19h."""

    def test_the_5800x3d_pstates(self):
        self.assertEqual([msr_pstate.pstate_hz(P_STATES_5800X3D[0xC0010064 + n]) // 1_000_000
                          for n in range(3)], [3400, 2800, 2200])

    def test_a_disabled_or_broken_one_says_nothing(self):
        p0 = P_STATES_5800X3D[0xC0010064]
        self.assertIsNone(msr_pstate.pstate_hz(p0 & ~(1 << 63)))
        self.assertIsNone(msr_pstate.pstate_hz(p0 & ~(0x3F << 8)))
        self.assertIsNone(msr_pstate.pstate_hz(0))


class TestWithoutPermissions(unittest.TestCase):

    def test_the_frequency_comes_from_proc_cpuinfo(self):
        with _machine():
            mhz = cpuinfo_mhz()
            photo = _photo()
        clocks = photo.cpu.types[0].clocks
        self.assertEqual(clocks.current_from, "cpuinfo")
        self.assertAlmostEqual(clocks.current_hz / 1e6, sum(mhz.values()) / len(mhz), delta=1)
        self.assertEqual(len(mhz), 16)

    def test_the_notice_says_what_is_known_and_blames_no_module(self):
        with _machine():
            photo = _photo()
        notes = {n.path: n for n in photo.notes if n.path.startswith("cpu.clocks")}
        self.assertEqual(notes["cpu.clocks.driver"].need, Need.HARDWARE)
        self.assertIn("BIOS", notes["cpu.clocks.driver"].hint)
        self.assertNotIn("cpu.clocks.current_hz", notes)
        self.assertFalse([n for n in notes.values() if n.need is Need.DRIVER])

    def test_a_zens_base_asks_for_permissions(self):
        with _machine(cppc=False):
            photo = _photo()
        base = [n for n in photo.notes if n.path == "cpu.clocks.base_hz"]
        self.assertEqual([n.need for n in base], [Need.ROOT])
        self.assertIsNone(photo.cpu.types[0].clocks.base_hz)

    def test_a_virtual_machine_still_has_none(self):
        # There /proc/cpuinfo would give the host's clock.
        with volcado.montado(EQUIPOS / "qemu-kvm"):
            photo = _photo()
        self.assertIsNone(photo.cpu.types[0].clocks.current_hz)
        self.assertIsNone(photo.cpu.types[0].clocks.turbo_supported)


class TestTheTurbo(unittest.TestCase):

    def test_what_the_kernel_flags_say(self):
        for dump, flag in (("5800x3d", "cpb"), ("i5-10400", "ida")):
            with self.subTest(dump=dump), volcado.montado(EQUIPOS / dump):
                self.assertTrue(_photo().cpu.types[0].clocks.turbo_supported, flag)

    def test_a_part_without_one_says_so(self):
        with _machine(boost_flag=False):
            clocks = _photo().cpu.types[0].clocks
        self.assertIs(clocks.turbo_supported, False)
        self.assertEqual(render.turbo(clocks), _("cpu.turbo.none"))


class TestWithPermissions(unittest.TestCase):
    """As the Athlon 3000G: no cpufreq, no CPPC, no turbo."""

    def test_the_base_is_p0_and_the_frequency_the_running_pstate(self):
        helper = _Helper()
        with _machine(cppc=False, boost_flag=False):
            photo = _photo(helper)
        clocks = photo.cpu.types[0].clocks
        self.assertEqual(clocks.base_hz, 3_400_000_000)
        self.assertEqual((clocks.current_hz, clocks.current_from), (3_400_000_000, "msr"))
        self.assertFalse([n for n in photo.notes if n.path == "cpu.clocks.base_hz"])
        self.assertIn("msr", photo.capabilities)

    def test_with_a_turbo_the_measure_stays(self):
        # The part goes above P0 on its own: /proc/cpuinfo measures that.
        with _machine(cppc=False):
            photo = _photo(_Helper())
        clocks = photo.cpu.types[0].clocks
        self.assertEqual((clocks.base_hz, clocks.current_from), (3_400_000_000, "cpuinfo"))

    def test_with_a_driver_and_a_base_it_asks_nothing(self):
        helper = _Helper()
        with volcado.montado(EQUIPOS / "5800x3d"):
            _photo(helper)
        # The voltage provider reads once per sample; this one, never.
        self.assertEqual(helper.reads, 2)

    def test_without_the_msr_module_the_padlock_goes(self):
        with _machine(cppc=False):
            photo = _photo(_Helper(fails=True))
        self.assertEqual([n.need for n in photo.notes if n.path == "cpu.clocks.base_hz"],
                         [Need.DRIVER])

    def test_an_unexpected_failure_is_an_error_not_silence(self):
        # It returned without a word, and the base had no reason to be missing.
        class _Broken(_Helper):
            def read_msr(self, cpu, registers):
                raise ValueError("bad register list")

        with _machine(cppc=False):
            photo = _photo(_Broken())
        self.assertEqual([n.need for n in photo.notes if n.path == "cpu.clocks.base_hz"],
                         [Need.ERROR])
        self.assertIn("msr-pstate", [f.where for f in photo.failures])

    def test_not_on_an_intel(self):
        helper = _Helper()
        with volcado.montado(EQUIPOS / "i5-10400"):
            photo = _photo(helper)
        self.assertNotEqual(photo.cpu.types[0].clocks.current_from, "msr")


def _only_when_it_differs() -> str:
    return _("cpu.clock.base.tdp")


class TestTheCpuPage(unittest.TestCase):
    """The rows a machine lacks hide and the foot names them. The configured
    TDP's base is apart: it shows only when it isn't the specification's, and
    hidden it isn't missing."""

    @classmethod
    def setUpClass(cls):
        cls.app = qt.app()

    def _clocks(self, photo):
        from silux.ui.pages.cpu import TypeSection
        with pantalla.Ventana(photo) as window:
            window.select_section("CPU")
            self.app.processEvents()
            section = window.cpu_page.findChildren(TypeSection)[0]
            return ({n: v.full_text() for n, v in section.clocks._values.items()},
                    set(section.clocks._ocultas), section.clocks_foot.text(),
                    section.clocks_foot.isVisibleTo(section))

    def test_without_a_driver_its_rows_go_and_the_foot_says_why(self):
        with _machine(boost_flag=False):
            photo = _photo()
        values, hidden, foot, shown = self._clocks(photo)
        self.assertEqual(values[_("cpu.clock.current")],
                         render.hz(photo.cpu.types[0].clocks.current_hz))
        # No turbo: its row and the silicon ceiling go too, said at the foot.
        self.assertEqual(hidden - {_only_when_it_differs()},
                         {_(k) for k in ("cpu.clock.min", "cpu.clock.maxkernel",
                                         "cpu.clock.driver", "cpu.clock.governor",
                                         "cpu.clock.epp", "cpu.clock.turbo",
                                         "cpu.clock.maxsilicon")})
        self.assertEqual((foot, shown), (_("cpu.clocks.nodriver.cpuinfo") + " "
                                         + _("cpu.clocks.noturbo"), True))

    def test_a_zens_base_without_permissions_has_its_padlock(self):
        from silux.ui.pages.cpu import TypeSection
        with _machine(cppc=False, boost_flag=False):
            photo = _photo()
        with pantalla.Ventana(photo) as window:
            window.select_section("CPU")
            self.app.processEvents()
            section = window.cpu_page.findChildren(TypeSection)[0]
            self.assertTrue(section.clocks.is_locked(_("cpu.clock.base")))

    def test_with_one_nothing_changes(self):
        with volcado.montado(EQUIPOS / "5800x3d"):
            photo = _photo()
        _values, hidden, _foot, shown = self._clocks(photo)
        self.assertEqual((hidden, shown), ({_only_when_it_differs()}, False))


if __name__ == "__main__":
    unittest.main()
