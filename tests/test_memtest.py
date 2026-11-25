"""The memory test: what it asks for, how it reads a curve, and a short run.

The curves are real: those in `fixtures/memtest/` are whole runs on a Ryzen
7 5800X3D and on an i5-10400 (two of them with a power manager switching the
turbo mid-test), and the short one below is what that i5-10400 gave. What a test
checks is the reading of them; the run on whoever executes the suite only
has to come back whole, with whatever figures that machine gives.
"""

import dataclasses
import json
import pathlib
import threading
import unittest
from unittest import mock

from silux import memtest
from silux.memtest import GIB, KIB, MIB, Point

FIXTURES = pathlib.Path(__file__).parent / "fixtures" / "memtest"
FIXTURE = FIXTURES / "5800x3d.json"

# An i5-10400 (L1d 32 KiB, L2 256 KiB, L3 12 MiB), huge pages.
I5_CACHES = (("L1", 32 * KIB), ("L2", 256 * KIB), ("L3", 12 * MIB))
I5_CURVE = tuple(Point(size, ns) for size, ns in (
    (16 * KIB, 0.99), (128 * KIB, 2.96), (4 * MIB, 9.62), (8 * MIB, 23.29),
    (16 * MIB, 52.86), (48 * MIB, 67.37), (192 * MIB, 66.05), (GIB, 72.01)))


def recorded(name: str = "5800x3d") -> memtest.Result:
    path = FIXTURES / f"{name}.json"
    return memtest._from_dict(json.loads(path.read_text(encoding="utf-8")))


class TestSizes(unittest.TestCase):
    def test_two_blocks_per_power_of_two_up_to_the_largest(self):
        sizes = memtest.curve_sizes(64 * KIB)
        self.assertEqual(sizes, (4 * KIB, 6 * KIB, 8 * KIB, 12 * KIB, 16 * KIB,
                                 24 * KIB, 32 * KIB, 48 * KIB, 64 * KIB))

    def test_a_largest_that_is_no_power_of_two_is_still_measured(self):
        sizes = memtest.curve_sizes(88 * MIB)
        self.assertEqual(sizes[-1], 88 * MIB)
        self.assertEqual(list(sizes), sorted(set(sizes)))
        self.assertTrue(all(size % 64 == 0 for size in sizes))


class TestClockChange(unittest.TestCase):
    def test_a_turbo_switched_off_mid_curve_is_a_change(self):
        low, high = memtest.clock_change(recorded("i5-10400-auto-cpufreq-curve"))
        self.assertAlmostEqual(low / 1e9, 2.89, places=2)
        self.assertAlmostEqual(high / 1e9, 4.25, places=2)

    def test_a_single_thread_pass_runs_on_the_measured_cpu_too(self):
        """The curve stayed near 4.2 GHz; two single-thread passes ran at 2.89."""
        result = recorded("i5-10400-auto-cpufreq-rates")
        curve_only = dataclasses.replace(result, rates=())
        self.assertIsNone(memtest.clock_change(curve_only))
        low, _high = memtest.clock_change(result)
        self.assertAlmostEqual(low / 1e9, 2.89, places=2)

    def test_the_turbo_s_own_steps_and_every_thread_s_lower_clock_are_not(self):
        """4.14 to 4.27 GHz on the measured CPU, 3.9 with every core busy."""
        result = recorded("i5-10400")
        self.assertTrue(any(r.threads > 1 and r.frequency_hz < 4.0e9 for r in result.rates))
        self.assertIsNone(memtest.clock_change(result))
        self.assertIsNone(memtest.clock_change(recorded()))

    def test_without_a_frequency_there_is_nothing_to_compare(self):
        result = recorded()
        bare = dataclasses.replace(
            result, points=tuple(dataclasses.replace(p, frequency_hz=None) for p in result.points),
            rates=tuple(dataclasses.replace(r, frequency_hz=None) for r in result.rates))
        self.assertIsNone(memtest.clock_change(bare))


class TestSteps(unittest.TestCase):
    def test_the_curve_then_one_thread_then_every_one(self):
        caches = (("L1", 32 * KIB), ("L2", 256 * KIB), ("L3", 12 * MIB))
        plan = memtest.make_plan(caches, tuple(range(12)), cpu=1, available=16 * GIB)
        self.assertEqual(memtest.steps(plan), ("latency", "single", "multi"))

    def test_a_single_cpu_has_no_step_with_every_thread(self):
        caches = (("L1", 32 * KIB), ("L2", 1 * MIB))
        plan = memtest.make_plan(caches, (0,), cpu=0, available=4 * GIB)
        self.assertEqual(memtest.steps(plan), ("latency", "single"))


class TestPlan(unittest.TestCase):
    def plan(self, available, l3=12 * MIB, cpus=(0, 1, 2, 3)):
        caches = (("L1", 32 * KIB), ("L2", 256 * KIB), ("L3", l3))
        return memtest.make_plan(caches, cpus, cpu=1, available=available)

    def test_the_ram_is_measured_over_a_gigabyte(self):
        plan = self.plan(16 * GIB)
        self.assertEqual((plan.ram_block, plan.ram_block_limited), (GIB, False))
        self.assertEqual(plan.sizes[-1], GIB)

    def test_or_over_four_times_a_cache_larger_than_a_quarter_of_that(self):
        self.assertEqual(self.plan(16 * GIB, l3=512 * MIB).ram_block, 2 * GIB)

    def test_with_little_free_memory_the_largest_block_that_fits(self):
        """And the result says the block was not the method's."""
        plan = self.plan(GIB)
        self.assertEqual((plan.ram_block, plan.ram_block_limited), (512 * MIB, True))
        # A copy maps two arrays, and both have to fit too.
        self.assertLessEqual(2 * plan.single_bytes, GIB - memtest.membench.FREE_MARGIN)

    def test_without_room_to_leave_the_cache_there_is_no_ram_block(self):
        plan = self.plan(memtest.membench.FREE_MARGIN + 28 * MIB)
        self.assertIsNone(plan.ram_block)
        self.assertFalse(plan.ram_block_limited)
        # The caches are still walked.
        self.assertEqual(plan.sizes[-1], 12 * MIB)

    def test_one_thread_moves_a_gigabyte(self):
        """With 512 MiB, a 96 MiB L3 served part of the read: 44 GB/s
        against 41 over 1 or 2 GiB, and it changed from run to run."""
        self.assertEqual(self.plan(16 * GIB, l3=96 * MIB).single_bytes, GIB)

    def test_or_eight_times_a_cache_larger_than_an_eighth_of_that(self):
        plan = self.plan(64 * GIB, l3=256 * MIB)
        self.assertEqual(plan.single_bytes, 2 * GIB)
        self.assertEqual(plan.multi_bytes * 4, 2 * GIB)

    def test_one_cpu_has_no_all_thread_pass(self):
        self.assertIsNone(self.plan(16 * GIB, cpus=(0,)).multi_bytes)
        self.assertEqual(self.plan(16 * GIB).multi_bytes, 256 * MIB)

    def test_many_threads_that_would_stay_in_the_cache_are_not_measured(self):
        """With 3 GiB free, sixty-four shares are 20 MiB each: with a cache
        of 768 MiB all of them together don't leave it."""
        plan = self.plan(3 * GIB, l3=768 * MIB, cpus=tuple(range(64)))
        self.assertIsNone(plan.multi_bytes)


class TestPickCpu(unittest.TestCase):
    def types(self):
        cache = lambda level, kind, size: mock.Mock(level=level, kind=kind, size_bytes=size)
        fast = mock.Mock(cpus=(0, 1, 2, 3), caches=(
            cache(1, "data", 48 * KIB), cache(1, "instruction", 32 * KIB),
            cache(2, "unified", 1280 * KIB), cache(3, "unified", 24 * MIB)))
        small = mock.Mock(cpus=(4, 5), caches=(cache(1, "data", 32 * KIB),))
        return fast, small

    def test_the_second_cpu_of_the_first_type_with_its_data_caches(self):
        cpu, caches = memtest.pick_cpu(self.types(), range(6))
        self.assertEqual(cpu, 1)
        self.assertEqual(caches, (("L1", 48 * KIB), ("L2", 1280 * KIB), ("L3", 24 * MIB)))

    def test_only_where_this_process_may_run(self):
        cpu, caches = memtest.pick_cpu(self.types(), [4, 5])
        self.assertEqual((cpu, caches), (5, (("L1", 32 * KIB),)))


class TestReadingTheCurve(unittest.TestCase):
    def test_each_level_is_the_median_of_the_blocks_that_fit_in_it(self):
        levels = memtest.levels_from_curve(I5_CURVE, I5_CACHES, GIB)
        self.assertEqual([(l.level, l.nanoseconds) for l in levels],
                         [("L1", 0.99), ("L2", 2.96), ("L3", 9.62), ("RAM", 72.01)])

    def test_a_block_as_large_as_its_cache_is_not_its_plateau(self):
        """8 MiB of a 12 MiB L3 already gave 23 ns: it shares it."""
        l3 = memtest.levels_from_curve(I5_CURVE, I5_CACHES, GIB)[2]
        self.assertEqual(l3.bytes_, 4 * MIB)

    def test_without_a_ram_block_there_is_no_ram_level(self):
        levels = memtest.levels_from_curve(I5_CURVE, I5_CACHES, None)
        self.assertEqual([l.level for l in levels], ["L1", "L2", "L3"])

    def test_a_whole_run_reads_as_its_caches(self):
        result = recorded()
        levels = memtest.levels_from_curve(result.points, result.caches, result.ram_block)
        self.assertEqual(levels, result.levels)
        self.assertEqual([l.level for l in levels], ["L1", "L2", "L3", "RAM"])
        # Zen 3 answers from L1 in four cycles.
        l1 = levels[0]
        self.assertAlmostEqual(l1.nanoseconds * l1.frequency_hz / 1e9, 4.0, delta=0.1)

    def test_the_steps_fall_where_the_caches_end(self):
        for points, caches, levels in (
                (I5_CURVE, I5_CACHES, memtest.levels_from_curve(I5_CURVE, I5_CACHES, GIB)),
                (recorded().points, recorded().caches, recorded().levels)):
            steps = memtest.curve_steps(points, levels, caches)
            self.assertEqual([s.level for s in steps], ["L1", "L2", "L3"])
            self.assertTrue(all(s.matches for s in steps), steps)

    def test_a_cache_declared_at_another_size_is_caught(self):
        """The curve of a 96 MiB L3, read with the 16 MiB a hypervisor could
        declare: it stays flat far past where that cache would end."""
        result = recorded()
        caches = tuple((n, 16 * MIB if n == "L3" else s) for n, s in result.caches)
        levels = memtest.levels_from_curve(result.points, caches, result.ram_block)
        steps = {s.level: s for s in memtest.curve_steps(result.points, levels, caches)}
        self.assertFalse(steps["L3"].matches)
        self.assertEqual((steps["L3"].flat_until, steps["L3"].rises_by), (64 * MIB, 96 * MIB))
        self.assertTrue(steps["L1"].matches and steps["L2"].matches)

    def test_two_levels_the_curve_cant_tell_apart_have_no_step(self):
        points = (Point(16 * KIB, 1.0), Point(128 * KIB, 1.1), Point(GIB, 60.0))
        caches = (("L1", 32 * KIB), ("L2", 256 * KIB))
        levels = memtest.levels_from_curve(points, caches, GIB)
        self.assertEqual([s.level for s in memtest.curve_steps(points, levels, caches)], ["L2"])


class TestShare(unittest.TestCase):
    def test_the_fastest_read_against_what_the_memory_could_move(self):
        result = dataclasses.replace(recorded(), theoretical_bytes_per_second=51_200_000_000)
        fastest = max(r.bytes_per_second for r in result.rates if r.operation == "read")
        self.assertEqual(memtest.share_of_theoretical(result),
                         round(fastest / 51_200_000_000 * 100, 1))

    def test_without_the_channels_there_is_no_percentage(self):
        self.assertIsNone(memtest.share_of_theoretical(recorded()))


@unittest.skipUnless(memtest.native_module(), "silux_bench is not installed")
class TestNativeRun(unittest.TestCase):
    def plan(self) -> memtest.Plan:
        cpus = tuple(memtest.native_module().allowed_cpus()[:2])
        return memtest.Plan(
            cpu=cpus[0], cpus=cpus, sizes=memtest.curve_sizes(64 * KIB), ram_block=None,
            ram_block_limited=False, single_bytes=2 * MIB,
            multi_bytes=2 * MIB if len(cpus) > 1 else None,
            caches=(("L1", 32 * KIB),))

    def test_a_short_run_comes_back_whole(self):
        phases = []
        plan = self.plan()
        result = memtest.run(plan, lambda phase, done: phases.append((phase, done)),
                             memory=memtest.Memory(1_000_000_000_000, 2, 3200))
        self.assertEqual((result.channels, result.speed_mts), (2, 3200))
        self.assertEqual((result.engine, result.reason), ("native", None), result.detail)
        self.assertEqual([p.bytes_ for p in result.points], list(plan.sizes))
        self.assertTrue(all(0 < p.nanoseconds < 10_000 for p in result.points))
        self.assertEqual(result.cpu, plan.cpu)
        kinds = {(r.operation, r.non_temporal, r.threads) for r in result.rates}
        self.assertEqual(len(kinds), len(memtest.OPERATIONS) * (2 if plan.multi_bytes else 1))
        self.assertTrue(all(r.bytes_per_second > 0 and r.isa for r in result.rates))
        self.assertEqual([l.level for l in result.levels], ["L1"])
        # Every point with its frequency, or none of them.
        with_frequency = [p for p in result.points if p.frequency_hz]
        self.assertIn(len(with_frequency), (0, len(result.points)))
        self.assertEqual(bool(with_frequency), result.frequency_source is not None)
        self.assertEqual(phases[0][0], "latency")
        self.assertEqual([d for _p, d in phases], sorted(d for _p, d in phases))
        # Only the plan's steps, each once and in its order.
        said = list(dict.fromkeys(step for step, _d in phases))
        self.assertEqual(said, list(memtest.steps(plan)))
        self.assertIsNotNone(memtest.share_of_theoretical(result))

    def test_stopping_it_says_cancelled(self):
        stop = threading.Event()
        stop.set()
        self.assertEqual(memtest.run(self.plan(), stop=stop).reason, "cancelled")

    def test_a_cpu_that_isnt_there_is_said_not_raised(self):
        plan = dataclasses.replace(self.plan(), cpu=100_000)
        result = memtest.run(plan)
        self.assertEqual(result.reason, "bad_cpu")
        self.assertFalse(result.measured)


class TestWithoutTheModule(unittest.TestCase):
    def test_the_simple_measure_answers_and_says_it_is(self):
        plan = memtest.make_plan((("L1", 32 * KIB), ("L2", 256 * KIB)), (0,), cpu=0,
                                 available=4 * GIB)
        with mock.patch.object(memtest, "native_module", return_value=None):
            result = memtest.run(plan)
        self.assertEqual(result.engine, "simple")
        self.assertEqual(result.points, ())
        if result.reason is None:
            self.assertTrue(result.measured)


class TestHistory(unittest.TestCase):
    def setUp(self):
        memtest.clear_history()
        self._remove_what_was_set_aside()
        self.addCleanup(memtest.clear_history)
        self.addCleanup(self._remove_what_was_set_aside)

    def test_what_is_saved_comes_back_the_same(self):
        first = recorded()
        second = dataclasses.replace(first, timestamp=first.timestamp + 60)
        memtest.append_history(first)
        self.assertEqual(memtest.append_history(second), [second, first])
        self.assertEqual(memtest.load_history(), [second, first])

    def test_the_report_carries_the_latest_whole(self):
        from silux import report
        from tests.test_equipos import EQUIPOS, shared_snapshot

        snapshot = shared_snapshot(EQUIPOS / "5800x3d")
        self.assertNotIn("## Prueba de memoria", report.build(snapshot))
        memtest.append_history(dataclasses.replace(
            recorded(), theoretical_bytes_per_second=51_200_000_000, channels=2, speed_mts=3200))
        text = report.build(snapshot)
        for expected in ("## Prueba de memoria",
                         "| L1 | 0.90 ns | 4.0 | 4.44 GHz | 16 KiB |",
                         "| read | 1 | 43.9 | avx2 | 4.43 GHz |",
                         "| copy (no temporal) | 16 | 38.5 | avx2 |",
                         "RAM sobre 1 GiB · páginas grandes 100 % · frecuencia por cycles",
                         "lectura al 86 % de 2 × 3200 MT/s × 8 B",
                         "L3 de 96 MiB: la curva sube entre 64 MiB y 96 MiB",
                         "| 1 GiB | 77.44 |"):
            self.assertIn(expected, text)
        self.assertEqual(text.count("| Bloque | ns |"), 1)

    def _write(self, *rows: dict) -> None:
        memtest.history_path().parent.mkdir(parents=True, exist_ok=True)
        memtest.history_path().write_text(
            json.dumps({"version": memtest.HISTORY_VERSION, "tests": list(rows)}),
            encoding="utf-8")

    def _saved_rows(self) -> list[dict]:
        return json.loads(memtest.history_path().read_text(encoding="utf-8"))["tests"]

    def _row_from_a_newer_version(self) -> dict:
        """The recorded test with a field this version doesn't know in the
        result and in one of each of its parts."""
        row = json.loads(FIXTURE.read_text(encoding="utf-8"))
        row["later"] = {"anything": [1, 2]}
        for part in ("points", "levels", "rates"):
            row[part][0]["later"] = part
        return row

    def test_a_name_comes_back_and_none_is_no_name(self):
        named = dataclasses.replace(recorded(), label="after the BIOS update")
        self.assertEqual(recorded().label, "")
        self.assertEqual(memtest.append_history(named)[0].label, "after the BIOS update")
        self.assertEqual(memtest.load_history()[0].label, "after the BIOS update")

    def test_a_file_with_more_fields_reads_whole(self):
        self._write(self._row_from_a_newer_version())
        self.assertEqual(memtest.load_history(), [recorded()])

    def test_one_row_that_cant_be_read_doesnt_empty_the_rest(self):
        good = json.loads(FIXTURE.read_text(encoding="utf-8"))
        for bad in ({"nonsense": 1}, "text", {**good, "points": [3]},
                    {**good, "caches": [["L1"]]}):
            self._write(bad, good)
            self.assertEqual(memtest.load_history(), [recorded()], bad)

    def test_measuring_again_keeps_what_a_newer_version_saved(self):
        self._write(self._row_from_a_newer_version())
        again = dataclasses.replace(recorded(), timestamp=recorded().timestamp + 60)
        memtest.append_history(again)
        new, old = self._saved_rows()
        self.assertEqual(old["later"], {"anything": [1, 2]})
        for part in ("points", "levels", "rates"):
            self.assertEqual(old[part][0]["later"], part)
            self.assertNotIn("later", old[part][1])
            self.assertNotIn("later", new[part][0])
        self.assertNotIn("later", new)
        self.assertEqual(memtest.load_history(), [again, recorded()])

    def _tagged(self) -> dict:
        """The recorded test with a field this version doesn't know in every
        point, level and rate, saying which one it is."""
        row = json.loads(FIXTURE.read_text(encoding="utf-8"))
        for point in row["points"]:
            point["later"] = point["bytes_"]
        for level in row["levels"]:
            level["later"] = level["level"]
        for rate in row["rates"]:
            rate["later"] = [rate["operation"], rate["threads"], rate["non_temporal"]]
        return row

    def _assert_each_kept_its_own(self, row: dict) -> None:
        for point in row["points"]:
            self.assertEqual(point["later"], point["bytes_"])
        for level in row["levels"]:
            self.assertEqual(level["later"], level["level"])
        for rate in row["rates"]:
            self.assertEqual(rate["later"],
                             [rate["operation"], rate["threads"], rate["non_temporal"]])

    def test_what_is_kept_goes_by_what_each_row_is_not_by_its_place(self):
        self._write(self._tagged())
        result = recorded()
        memtest.save_history([dataclasses.replace(
            result, points=result.points[::-1], levels=result.levels[::-1],
            rates=result.rates[::-1])])
        row, = self._saved_rows()
        self.assertEqual(row["points"][0]["bytes_"], result.points[-1].bytes_)
        self._assert_each_kept_its_own(row)

    def test_a_list_that_lost_a_row_keeps_the_rest(self):
        self._write(self._tagged())
        result = recorded()
        memtest.save_history([dataclasses.replace(
            result, points=result.points[1:], levels=result.levels[1:],
            rates=result.rates[1:])])
        row, = self._saved_rows()
        self.assertEqual(len(row["rates"]), len(result.rates) - 1)
        self._assert_each_kept_its_own(row)

    def test_two_rows_that_are_the_same_keep_nothing_of_either(self):
        tagged = self._tagged()
        tagged["points"][1]["bytes_"] = tagged["points"][0]["bytes_"]
        self._write(tagged)
        memtest.save_history([recorded()])
        row, = self._saved_rows()
        self.assertNotIn("later", row["points"][0])
        self.assertEqual(row["points"][2]["later"], row["points"][2]["bytes_"])

    def _other_version(self) -> str:
        text = json.dumps({"version": 2, "tests": [{"of": "a later format"}], "more": 1})
        memtest.history_path().parent.mkdir(parents=True, exist_ok=True)
        memtest.history_path().write_text(text, encoding="utf-8")
        return text

    def _remove_what_was_set_aside(self) -> None:
        for aside in memtest.history_path().parent.glob("memory-tests.json.*"):
            aside.unlink()

    def test_a_file_of_another_version_is_set_aside_not_written_over(self):
        path = memtest.history_path()
        text = self._other_version()
        self.assertEqual(memtest.load_history(), [])
        self.assertEqual(path.read_text(encoding="utf-8"), text)
        self.assertEqual(memtest.append_history(recorded()), [recorded()])
        self.assertEqual(path.with_name("memory-tests.json.v2").read_text(encoding="utf-8"), text)
        self.assertEqual(memtest.load_history(), [recorded()])

        # A second one doesn't take the first one's place.
        second = self._other_version().replace("more", "even more")
        path.write_text(second, encoding="utf-8")
        memtest.append_history(recorded())
        self.assertEqual(path.with_name("memory-tests.json.v2").read_text(encoding="utf-8"), text)
        self.assertEqual(path.with_name("memory-tests.json.v2.1").read_text(encoding="utf-8"),
                         second)
        self.assertEqual(memtest.load_history(), [recorded()])

    def test_a_file_of_another_version_that_cant_be_moved_stays_as_it_is(self):
        text = self._other_version()
        with mock.patch.object(pathlib.Path, "rename", side_effect=OSError("read-only")):
            self.assertFalse(memtest.save_history([recorded()]))
        self.assertEqual(memtest.history_path().read_text(encoding="utf-8"), text)

    def test_a_file_that_cant_be_read_is_set_aside_not_written_over(self):
        path = memtest.history_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        whole = json.dumps({"version": memtest.HISTORY_VERSION,
                            "tests": [json.loads(FIXTURE.read_text(encoding="utf-8"))]})
        again = dataclasses.replace(recorded(), timestamp=recorded().timestamp + 60)
        # Cut short while it was being written, empty, not JSON, not an
        # object, without a version, and one of ours without its tests.
        for text in (whole[:len(whole) // 2], "", "not json", "[]", '{"tests": []}',
                     '{"version": true, "tests": []}', '{"version": 1, "tests": 3}'):
            self._remove_what_was_set_aside()
            path.write_text(text, encoding="utf-8")
            self.assertEqual(memtest.load_history(), [], text)
            self.assertEqual(memtest.append_history(recorded()), [recorded()], text)
            aside = path.with_name("memory-tests.json.broken")
            self.assertEqual(aside.read_text(encoding="utf-8"), text)

            # A second one doesn't take the first one's place.
            path.write_text(text + " ", encoding="utf-8")
            memtest.append_history(again)
            self.assertEqual(aside.read_text(encoding="utf-8"), text)
            self.assertEqual(path.with_name("memory-tests.json.broken.1")
                             .read_text(encoding="utf-8"), text + " ")
            self.assertEqual(memtest.load_history(), [again], text)

    def test_a_file_that_cant_be_read_nor_moved_stays_as_it_is(self):
        path = memtest.history_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('{"version": 1, "tests": [{"engine": "nat', encoding="utf-8")
        with mock.patch.object(pathlib.Path, "rename", side_effect=OSError("read-only")):
            self.assertFalse(memtest.save_history([recorded()]))
        self.assertEqual(path.read_text(encoding="utf-8"),
                         '{"version": 1, "tests": [{"engine": "nat')

    def test_saving_ours_sets_nothing_aside(self):
        memtest.append_history(recorded())
        memtest.append_history(dataclasses.replace(recorded(), timestamp=1.0))
        self.assertEqual([p.name for p in memtest.history_path().parent.glob("memory-tests*")],
                         ["memory-tests.json"])

    def test_a_rate_measured_inside_a_cache_isnt_the_memorys(self):
        row = json.loads(FIXTURE.read_text(encoding="utf-8"))
        row["theoretical_bytes_per_second"] = 51_200_000_000
        in_cache = {**row["rates"][0], "bytes_per_second": 280_000_000_000, "level": "L1"}
        self._write({**row, "rates": row["rates"] + [in_cache]})
        result = memtest.load_history()[0]
        self.assertTrue(all(r.level == "RAM" for r in result.rates[:-1]))
        self.assertEqual(result.rate("read"), recorded().rate("read"))
        self.assertEqual(result.rate("read", 1), recorded().rate("read", 1))
        self.assertEqual(result.rate("read", level="L1").bytes_per_second, 280_000_000_000)
        self.assertEqual(memtest.share_of_theoretical(result), 85.7)

    def test_the_report_names_the_level_of_a_rate_inside_a_cache(self):
        from silux import report
        from tests.test_equipos import EQUIPOS, shared_snapshot

        row = json.loads(FIXTURE.read_text(encoding="utf-8"))
        in_cache = {**row["rates"][0], "bytes_per_second": 280_000_000_000, "level": "L1"}
        self._write({**row, "rates": row["rates"] + [in_cache]})
        text = report.build(shared_snapshot(EQUIPOS / "5800x3d"))
        self.assertIn("| read | 1 | 43.9 | avx2 | 4.43 GHz |", text)
        self.assertIn("| L1 read | 1 | 280.0 | avx2 | 4.43 GHz |", text)

    def test_a_file_that_isnt_ours_reads_as_none(self):
        memtest.history_path().parent.mkdir(parents=True, exist_ok=True)
        for text in ("not json", "[]", '{"version": 99, "tests": []}',
                     '{"version": 1, "tests": [{"nonsense": 1}]}'):
            memtest.history_path().write_text(text, encoding="utf-8")
            self.assertEqual(memtest.load_history(), [], text)


if __name__ == "__main__":
    unittest.main()
