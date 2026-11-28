//! One thread per CPU rendering units until the work or the time runs out.
//!
//! The units are handed out by a shared counter: whoever finishes takes the
//! next, so a fast core does more of them than a slow one without anyone
//! deciding it. Each thread counts its own work and its own time, and the
//! figure is the sum of their rates. The total over the wall clock would
//! charge every thread for the unit it has half done when time is up.

use std::io::Write;
use std::sync::atomic::{AtomicBool, AtomicU64, Ordering};
use std::sync::{Mutex, MutexGuard, PoisonError};
use std::time::Duration;

use crate::common::cancel::Control;
use crate::common::error::{panic_message, Error, Result};
use crate::common::frequency::Meter;
use crate::common::gate::{Gate, Opener};
use crate::common::hash::Fingerprint;
use crate::common::timer::{now_ns, Clock};
use crate::common::topology::pin_current_thread;
use crate::cpu::render::film::{fingerprint, render_unit, Layout, Unit, MAX_PASSES};
use crate::cpu::render::scene::Scene;
use crate::cpu::render::trace::{Counters, Scratch};
use crate::cpu::render::Kernel;

/// Rows a thread has room for before it has to ask for more memory.
const ROWS_AT_START: usize = 1 << 14;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Stop {
    /// Render the first `n` units of the table, each once.
    AfterUnits(u64),
    /// Render for this long, going round the table as often as it takes.
    /// The unit a thread is on when time is up is finished and counts.
    AfterNs(u64),
}

/// Who watches a run: told `hz` times a second which units were finished and
/// what each thread is on, a line of JSON each time.
pub struct Reporter {
    pub hz: f64,
    pub sink: Mutex<Box<dyn Write + Send>>,
}

pub struct Plan<'a> {
    pub scene: &'a Scene,
    pub layout: Layout,
    pub kernel: Kernel,
    /// One thread for each entry, kept on that CPU; `None` leaves it to the
    /// scheduler.
    pub cpus: Vec<Option<usize>>,
    /// The table is this many passes over every tile.
    pub passes: u32,
    pub stop: Stop,
    /// What is rendered before this has passed isn't counted: the cores are
    /// still coming up to speed.
    pub warmup_ns: u64,
    /// Add every unit into a whole picture, to look at afterwards.
    pub keep_film: bool,
    pub reporter: Option<Reporter>,
}

/// One rendered unit.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct Row {
    /// Which unit of the table: `pass * tiles + tile`.
    pub index: u64,
    pub unit: Unit,
    pub fingerprint: u64,
    pub counters: Counters,
    /// From the run's start.
    pub begin_ns: u64,
    pub end_ns: u64,
    pub worker: u32,
    /// Inside the counted stretch.
    pub counted: bool,
}

#[derive(Debug, Clone, PartialEq)]
pub struct Worker {
    pub cpu: Option<usize>,
    /// Units, work and time in the counted stretch.
    pub units: u64,
    pub counters: Counters,
    pub ns: u64,
    /// The frequency the thread ran at over that stretch, where it could be
    /// measured.
    pub hz: Option<f64>,
}

impl Worker {
    /// Work per second.
    pub fn rate(&self) -> f64 {
        if self.ns == 0 {
            0.0
        } else {
            self.counters.weight() as f64 / (self.ns as f64 / 1e9)
        }
    }
}

#[derive(Debug, Clone, PartialEq)]
pub struct Outcome {
    pub workers: Vec<Worker>,
    /// Every unit rendered, in the order of the table and then of time.
    pub rows: Vec<Row>,
    /// The sum of every sample of every pixel, three floats each, if asked.
    pub film: Option<Vec<f32>>,
    pub wall_ns: u64,
}

impl Outcome {
    /// Work per second: the sum of every thread's own rate.
    pub fn rate(&self) -> f64 {
        self.workers.iter().map(Worker::rate).sum()
    }

    pub fn counters(&self) -> Counters {
        let mut all = Counters::default();
        for worker in &self.workers {
            all.add(worker.counters);
        }
        all
    }

    /// One number for every row's result and work, in table order.
    pub fn table_id(&self) -> u64 {
        let mut id = Fingerprint::default();
        for row in &self.rows {
            id.word(row.index);
            id.word(row.fingerprint);
            id.word(row.counters.nodes);
            id.word(row.counters.leaves);
            id.word(row.counters.rays);
            id.word(row.counters.paths);
        }
        id.finish()
    }
}

/// What a worker leaves for the reporter without waiting for it.
#[derive(Default)]
struct Feed {
    done: Mutex<Vec<Unit>>,
    /// The table index of the unit in hand, plus one; zero for none.
    active: AtomicU64,
}

struct Shared<'a> {
    plan: &'a Plan<'a>,
    table: u64,
    next: AtomicU64,
    gate: Gate,
    start_ns: AtomicU64,
    finished: AtomicBool,
    control: &'a Control,
    film: Option<Mutex<Vec<f32>>>,
    feeds: Vec<Feed>,
}

fn locked<T>(mutex: &Mutex<T>) -> MutexGuard<'_, T> {
    mutex.lock().unwrap_or_else(PoisonError::into_inner)
}

fn no_thread(error: std::io::Error) -> Error {
    Error::NoThread {
        errno: error.raw_os_error().unwrap_or(0),
    }
}

pub fn run(plan: &Plan, control: &Control) -> Result<Outcome> {
    Clock::check()?;
    let tiles = u64::from(plan.layout.tiles());
    let table = u64::from(plan.passes) * tiles;
    if table == 0 || plan.passes > MAX_PASSES {
        return Err(Error::BadSetting("passes"));
    }
    if plan.cpus.is_empty() {
        return Err(Error::BadSetting("cpus"));
    }
    if !plan.kernel.is_available() {
        return Err(Error::BadSetting("kernel"));
    }
    if matches!(plan.stop, Stop::AfterUnits(units) if units > table) {
        return Err(Error::BadSetting("units"));
    }
    if matches!(&plan.reporter, Some(reporter) if reporter.hz.is_nan() || reporter.hz <= 0.0) {
        return Err(Error::BadSetting("reporter"));
    }
    let pixels = plan.layout.width as usize * plan.layout.height as usize;
    let shared = Shared {
        plan,
        table,
        next: AtomicU64::new(0),
        gate: Gate::default(),
        start_ns: AtomicU64::new(0),
        finished: AtomicBool::new(false),
        control,
        film: plan.keep_film.then(|| Mutex::new(vec![0.0; pixels * 3])),
        feeds: plan.cpus.iter().map(|_| Feed::default()).collect(),
    };
    let shared = &shared;

    let (results, wall_ns) = std::thread::scope(|scope| {
        // If a thread can't be started, this lets the ones that were leave.
        let opener = Opener(&shared.gate);
        let mut handles = Vec::new();
        for (index, cpu) in plan.cpus.iter().enumerate() {
            let handle = std::thread::Builder::new()
                .name(format!("silux-cpu-{index}"))
                .spawn_scoped(scope, move || work(shared, index as u32, *cpu))
                .map_err(no_thread)?;
            handles.push(handle);
        }
        let reporting = match &plan.reporter {
            Some(reporter) => Some(
                std::thread::Builder::new()
                    .name("silux-cpu-report".to_owned())
                    .spawn_scoped(scope, move || report(shared, reporter))
                    .map_err(no_thread)?,
            ),
            None => None,
        };
        let start = now_ns();
        shared.start_ns.store(start, Ordering::Relaxed);
        shared.gate.open(true);
        drop(opener);
        let results: Vec<Result<(Worker, Vec<Row>)>> = handles
            .into_iter()
            .map(|handle| match handle.join() {
                Ok(result) => result,
                Err(payload) => Err(Error::Internal(panic_message(&*payload))),
            })
            .collect();
        let wall_ns = now_ns().saturating_sub(start);
        shared.finished.store(true, Ordering::Relaxed);
        if let Some(reporting) = reporting {
            if let Err(payload) = reporting.join() {
                return Err(Error::Internal(panic_message(&*payload)));
            }
        }
        Ok((results, wall_ns))
    })?;

    let mut workers = Vec::new();
    let mut rows = Vec::new();
    for result in results {
        let (worker, own) = result?;
        workers.push(worker);
        rows.extend(own);
    }
    control.check()?;
    rows.sort_by_key(|row| (row.index, row.begin_ns));
    let film = shared
        .film
        .as_ref()
        .map(|film| std::mem::take(&mut *locked(film)));
    Ok(Outcome {
        workers,
        rows,
        film,
        wall_ns,
    })
}

fn work(shared: &Shared, index: u32, cpu: Option<usize>) -> Result<(Worker, Vec<Row>)> {
    let plan = shared.plan;
    let pinned = cpu.map_or(Ok(()), pin_current_thread);
    let meter = Meter::open();
    let mut scratch = Scratch::default();
    let largest = plan.layout.tile as usize * plan.layout.tile as usize * 3;
    let mut sums = vec![0.0f32; largest];
    let mut rows = Vec::with_capacity(ROWS_AT_START);
    let feed = match &plan.reporter {
        Some(_) => shared.feeds.get(index as usize),
        None => None,
    };
    // Every thread reaches the gate, the one that can't run too: the gate
    // opens for all or for none.
    let measure = shared.gate.pass();
    pinned?;
    if !measure {
        return Err(Error::Cancelled);
    }
    let start = shared.start_ns.load(Ordering::Relaxed);
    let counted_from = start.saturating_add(plan.warmup_ns);
    let tiles = u64::from(plan.layout.tiles());

    let mut worker = Worker {
        cpu,
        units: 0,
        counters: Counters::default(),
        ns: 0,
        hz: None,
    };
    let mut first = None;
    let mut last = 0;
    loop {
        if shared.control.is_cancelled() {
            break;
        }
        let begin = now_ns();
        if matches!(plan.stop, Stop::AfterNs(ns) if begin >= counted_from.saturating_add(ns)) {
            break;
        }
        let taken = shared.next.fetch_add(1, Ordering::Relaxed);
        if matches!(plan.stop, Stop::AfterUnits(units) if taken >= units) {
            break;
        }
        let at = taken % shared.table;
        let unit = Unit {
            pass: (at / tiles) as u32,
            tile: (at % tiles) as u32,
        };
        let floats = plan
            .layout
            .floats(unit.tile)
            .ok_or(Error::BadSetting("tile"))?;
        let sums = sums.get_mut(..floats).ok_or(Error::BadSetting("tile"))?;
        if let Some(feed) = feed {
            feed.active.store(at + 1, Ordering::Relaxed);
        }
        let counters = render_unit(
            plan.kernel,
            plan.scene,
            plan.layout,
            unit,
            &mut scratch,
            sums,
        )?;
        let print = fingerprint(sums);
        let end = now_ns();
        let counted = begin >= counted_from;
        if counted {
            first.get_or_insert_with(|| (begin, meter.begin()));
            worker.units += 1;
            worker.counters.add(counters);
            last = end;
        }
        rows.push(Row {
            index: at,
            unit,
            fingerprint: print,
            counters,
            begin_ns: begin.saturating_sub(start),
            end_ns: end.saturating_sub(start),
            worker: index,
            counted,
        });
        if let Some(film) = &shared.film {
            add_to_film(&mut locked(film), plan.layout, unit.tile, sums);
        }
        if let Some(feed) = feed {
            locked(&feed.done).push(unit);
        }
    }
    if let Some(feed) = feed {
        feed.active.store(0, Ordering::Relaxed);
    }
    if let Some((begin, mark)) = first {
        worker.ns = last.saturating_sub(begin);
        worker.hz = meter.end(mark, worker.ns as f64);
    }
    Ok((worker, rows))
}

fn add_to_film(film: &mut [f32], layout: Layout, tile: u32, sums: &[f32]) {
    let Some((left, top, width, height)) = layout.rect(tile) else {
        return;
    };
    let row_floats = width as usize * 3;
    for (row, sums) in (top..top + height).zip(sums.chunks_exact(row_floats)) {
        let from = (row as usize * layout.width as usize + left as usize) * 3;
        let Some(pixels) = film.get_mut(from..from + row_floats) else {
            return;
        };
        for (pixel, sum) in pixels.iter_mut().zip(sums) {
            *pixel += sum;
        }
    }
}

/// The reporter's thread. It takes what each worker left by swapping their
/// list for an empty one, so a worker never waits longer than that.
fn report(shared: &Shared, reporter: &Reporter) {
    let period = Duration::from_secs_f64(1.0 / reporter.hz.clamp(0.1, 1000.0));
    let mut taken = Vec::new();
    let mut line = String::new();
    loop {
        // Read before draining: whatever was finished by now is in this
        // line, which is then the last.
        let last = shared.finished.load(Ordering::Relaxed);
        line.clear();
        line.push_str("{\"done\":[");
        let mut any = false;
        for (worker, feed) in shared.feeds.iter().enumerate() {
            std::mem::swap(&mut *locked(&feed.done), &mut taken);
            for unit in taken.drain(..) {
                if std::mem::replace(&mut any, true) {
                    line.push(',');
                }
                line.push_str(&format!("[{},{},{worker}]", unit.pass, unit.tile));
            }
        }
        line.push_str("],\"active\":[");
        any = false;
        for (worker, feed) in shared.feeds.iter().enumerate() {
            let active = feed.active.load(Ordering::Relaxed);
            if active == 0 {
                continue;
            }
            if std::mem::replace(&mut any, true) {
                line.push(',');
            }
            line.push_str(&format!("[{worker},{}]", active - 1));
        }
        line.push_str("]}\n");
        // A sink that fails is whoever was watching gone: the run goes on.
        let _ = locked(&reporter.sink).write_all(line.as_bytes());
        if last {
            return;
        }
        std::thread::sleep(period);
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::common::topology::allowed_cpus;
    use crate::cpu::render::film::tests::{table, SMALL};
    use crate::cpu::render::scene::prototype;
    use std::sync::Arc;

    const PASSES: u32 = 3;

    fn plan(scene: &Scene, cpus: Vec<Option<usize>>, stop: Stop) -> Plan<'_> {
        Plan {
            scene,
            layout: SMALL,
            kernel: Kernel::widest(),
            cpus,
            passes: PASSES,
            stop,
            warmup_ns: 0,
            keep_film: false,
            reporter: None,
        }
    }

    fn whole_table() -> Stop {
        Stop::AfterUnits(u64::from(PASSES) * u64::from(SMALL.tiles()))
    }

    fn some_cpus(count: usize) -> Vec<Option<usize>> {
        allowed_cpus()
            .into_iter()
            .cycle()
            .take(count)
            .map(Some)
            .collect()
    }

    #[test]
    fn any_number_of_threads_gives_the_units_one_alone_gives() {
        let scene = prototype(0).unwrap();
        let expected = table(Kernel::widest(), &scene, PASSES);
        for threads in [1, 2, 5] {
            let outcome = run(
                &plan(&scene, some_cpus(threads), whole_table()),
                &Control::default(),
            )
            .unwrap();
            let got: Vec<_> = outcome
                .rows
                .iter()
                .map(|row| (row.fingerprint, row.counters))
                .collect();
            assert_eq!(got, expected, "{threads} threads");
            assert_eq!(outcome.workers.len(), threads);
            // Every unit was counted by exactly one thread.
            let units: u64 = outcome.workers.iter().map(|worker| worker.units).sum();
            assert_eq!(units, expected.len() as u64);
            let mut work = Counters::default();
            for (_, counters) in &expected {
                work.add(*counters);
            }
            assert_eq!(outcome.counters(), work);
        }
    }

    #[test]
    fn the_table_id_changes_with_any_unit() {
        let scene = prototype(0).unwrap();
        let outcome = run(
            &plan(&scene, vec![None], whole_table()),
            &Control::default(),
        )
        .unwrap();
        let id = outcome.table_id();
        let mut wrong = outcome.clone();
        wrong.rows[17].fingerprint ^= 1;
        assert_ne!(wrong.table_id(), id);
        let mut heavier = outcome.clone();
        heavier.rows[40].counters.nodes += 1;
        assert_ne!(heavier.table_id(), id);
        // And the two-thread run of the test above has the same one.
        let two = run(
            &plan(&scene, some_cpus(2), whole_table()),
            &Control::default(),
        )
        .unwrap();
        assert_eq!(two.table_id(), id);
    }

    #[test]
    fn a_timed_run_goes_round_the_table_and_counts_after_the_warm_up() {
        let scene = prototype(0).unwrap();
        let mut plan = plan(&scene, some_cpus(2), Stop::AfterNs(120_000_000));
        plan.passes = 1;
        plan.warmup_ns = 30_000_000;
        let outcome = run(&plan, &Control::default()).unwrap();
        let expected = table(Kernel::widest(), &scene, 1);
        // One pass of this picture takes a few milliseconds: it comes round.
        assert!(outcome.rows.len() > expected.len());
        for row in &outcome.rows {
            let (print, counters) = expected[row.index as usize];
            assert_eq!((row.fingerprint, row.counters), (print, counters));
            assert_eq!(row.counted, row.begin_ns >= plan.warmup_ns);
        }
        assert!(outcome.rows.iter().any(|row| !row.counted));
        for (index, worker) in outcome.workers.iter().enumerate() {
            let counted = outcome
                .rows
                .iter()
                .filter(|row| row.counted && row.worker as usize == index);
            assert_eq!(worker.units, counted.count() as u64);
            // Its own time, from its first counted unit to its last: about
            // the stretch asked for, however busy the machine is.
            assert!(
                worker.ns > 60_000_000 && worker.ns < 2_000_000_000,
                "{}",
                worker.ns
            );
            assert!(worker.rate() > 0.0);
        }
        assert!(
            (outcome.rate() - outcome.workers.iter().map(Worker::rate).sum::<f64>()).abs() < 1.0
        );
    }

    #[test]
    fn the_film_is_the_sum_of_every_unit() {
        let scene = prototype(0).unwrap();
        let mut plan = plan(&scene, some_cpus(3), whole_table());
        plan.keep_film = true;
        let outcome = run(&plan, &Control::default()).unwrap();
        let film = outcome.film.unwrap();
        assert_eq!(film.len(), (SMALL.width * SMALL.height * 3) as usize);
        // One tile, added by hand over the passes.
        let tile = 9;
        let (left, top, width, height) = SMALL.rect(tile).unwrap();
        let mut expected = vec![0.0f32; SMALL.floats(tile).unwrap()];
        let mut scratch = Scratch::default();
        for pass in 0..PASSES {
            let mut sums = vec![0.0; expected.len()];
            let unit = Unit { pass, tile };
            render_unit(
                Kernel::widest(),
                &scene,
                SMALL,
                unit,
                &mut scratch,
                &mut sums,
            )
            .unwrap();
            for (total, sum) in expected.iter_mut().zip(&sums) {
                *total += sum;
            }
        }
        let mut expected = expected.chunks_exact(3);
        for y in top..top + height {
            for x in left..left + width {
                let at = ((y * SMALL.width + x) * 3) as usize;
                assert_eq!(Some(&film[at..at + 3]), expected.next());
            }
        }
        assert!(film.iter().any(|sum| *sum > 0.0));
    }

    /// A sink the test can read back.
    #[derive(Clone, Default)]
    struct Kept(Arc<Mutex<Vec<u8>>>);

    impl Write for Kept {
        fn write(&mut self, bytes: &[u8]) -> std::io::Result<usize> {
            locked(&self.0).extend_from_slice(bytes);
            Ok(bytes.len())
        }
        fn flush(&mut self) -> std::io::Result<()> {
            Ok(())
        }
    }

    #[test]
    fn the_reporter_tells_every_unit_once_and_changes_nothing() {
        let scene = prototype(0).unwrap();
        let quiet = run(
            &plan(&scene, some_cpus(3), whole_table()),
            &Control::default(),
        )
        .unwrap();
        let kept = Kept::default();
        let mut plan = plan(&scene, some_cpus(3), whole_table());
        plan.reporter = Some(Reporter {
            hz: 200.0,
            sink: Mutex::new(Box::new(kept.clone())),
        });
        let watched = run(&plan, &Control::default()).unwrap();
        assert_eq!(watched.table_id(), quiet.table_id());

        let text = String::from_utf8(locked(&kept.0).clone()).unwrap();
        let mut told = Vec::new();
        for line in text.lines() {
            assert!(
                line.starts_with("{\"done\":[") && line.ends_with("]}"),
                "{line}"
            );
            let done = line
                .strip_prefix("{\"done\":[")
                .and_then(|rest| rest.split("],\"active\":[").next())
                .unwrap();
            for entry in done.split("],[").filter(|entry| !entry.is_empty()) {
                let numbers: Vec<u64> = entry
                    .trim_matches(|c| c == '[' || c == ']')
                    .split(',')
                    .map(|n| n.parse().unwrap())
                    .collect();
                assert_eq!(numbers.len(), 3, "{entry}");
                assert!(numbers[2] < 3);
                told.push(numbers[0] * u64::from(SMALL.tiles()) + numbers[1]);
            }
        }
        told.sort_unstable();
        let every: Vec<u64> = (0..watched.rows.len() as u64).collect();
        assert_eq!(told, every);
        // The last line is written after every thread has left.
        assert!(text.lines().last().unwrap().ends_with("\"active\":[]}"));
    }

    #[test]
    fn a_cancelled_run_stops_and_says_so() {
        let scene = prototype(0).unwrap();
        let control = Control::default();
        control.cancel();
        let plan = plan(&scene, some_cpus(2), Stop::AfterNs(60_000_000_000));
        assert_eq!(run(&plan, &control), Err(Error::Cancelled));
    }

    #[test]
    fn a_cpu_that_isnt_there_fails_the_run_without_hanging_it() {
        let scene = prototype(0).unwrap();
        let mut cpus = some_cpus(2);
        cpus.push(Some(libc::CPU_SETSIZE as usize));
        let result = run(&plan(&scene, cpus, whole_table()), &Control::default());
        assert!(matches!(result, Err(Error::BadCpu { .. })), "{result:?}");
    }

    #[test]
    fn what_cant_run_is_refused() {
        let scene = prototype(0).unwrap();
        let control = Control::default();
        let refused = |change: &dyn Fn(&mut Plan)| {
            let mut plan = plan(&scene, vec![None], whole_table());
            change(&mut plan);
            run(&plan, &control).map(|_| ())
        };
        assert_eq!(
            refused(&|plan| plan.cpus.clear()),
            Err(Error::BadSetting("cpus"))
        );
        assert_eq!(
            refused(&|plan| plan.passes = 0),
            Err(Error::BadSetting("passes"))
        );
        assert_eq!(
            refused(&|plan| plan.passes = MAX_PASSES + 1),
            Err(Error::BadSetting("passes"))
        );
        assert_eq!(
            refused(&|plan| plan.stop = Stop::AfterUnits(u64::MAX)),
            Err(Error::BadSetting("units"))
        );
        assert_eq!(
            refused(&|plan| {
                plan.reporter = Some(Reporter {
                    hz: 0.0,
                    sink: Mutex::new(Box::new(std::io::sink())),
                })
            }),
            Err(Error::BadSetting("reporter"))
        );
        assert_eq!(refused(&|_| {}), Ok(()));
    }
}
