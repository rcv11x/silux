//! How fast memory moves: reads, writes or copies over a block per thread,
//! one thread or many, each pinned to its CPU.
//!
//! Every thread maps and touches its own block, so it lands on its CPU's
//! NUMA node. The repetitions start together, behind a barrier, and the
//! bandwidth of one is everything moved over the time from the first thread
//! starting to the last finishing: what the memory gave all of them at once.

use std::panic::{catch_unwind, AssertUnwindSafe};
use std::sync::atomic::{AtomicBool, AtomicU64, Ordering};
use std::sync::{Barrier, Condvar, Mutex, PoisonError};
use std::thread::Builder;

use crate::common::cancel::Control;
use crate::common::error::{panic_message, Error, Result};
use crate::common::frequency::{Meter, Source};
use crate::common::stats::{self, Summary};
use crate::common::timer::{now_ns, Clock};
use crate::common::topology::pin_current_thread;
use crate::memory::block::{Block, Pages};
use crate::memory::kernels::{self, Isa, Operation, STEP};

pub const MAX_REPETITIONS: usize = 1000;
/// How far past the end of a copy's source its destination starts. Two
/// arrays a whole number of pages apart load and store at the same offsets
/// within their pages, and a copy between them came out about a tenth slower
/// than bw_mem's; a few lines more apart, it doesn't. A multiple of the line
/// and of every vector width.
const COPY_GAP: usize = 2048 - 128;

#[derive(Debug, Clone, Copy)]
pub struct Settings {
    pub operation: Operation,
    pub non_temporal: bool,
    pub isa: Isa,
    /// Bytes of each array, per thread: a copy has two.
    pub bytes: usize,
    pub pages: Pages,
    pub repetitions: usize,
}

#[derive(Debug, Clone, PartialEq)]
pub struct Bandwidth {
    /// Bytes per nanosecond, which is GB/s, over the repetitions. A copy
    /// counts what it reads and what it writes, as STREAM does.
    pub gbps: Summary,
    pub threads: usize,
    /// Passes over the block per repetition, the same for every thread.
    pub passes: u64,
    /// Hertz the cores ran at, the mean of the threads in each repetition,
    /// where every thread could measure it.
    pub hz: Option<Summary>,
    pub frequency: Option<Source>,
}

/// When a thread's repetition began and ended, and the hertz it ran at.
type Span = (u64, u64, Option<f64>);

/// Holds every thread before its first barrier until all of them exist. The
/// barrier waits for one thread per CPU, so a thread that couldn't be started
/// would keep the rest there forever, and the join of any of them too.
struct Gate {
    verdict: Mutex<Option<bool>>,
    opened: Condvar,
}

impl Gate {
    fn new() -> Self {
        Gate {
            verdict: Mutex::new(None),
            opened: Condvar::new(),
        }
    }

    /// Let the threads through, to measure or to leave. The first verdict
    /// stands.
    fn open(&self, measure: bool) {
        let mut verdict = self.verdict.lock().unwrap_or_else(PoisonError::into_inner);
        verdict.get_or_insert(measure);
        self.opened.notify_all();
    }

    /// Wait for the verdict: whether to measure.
    fn pass(&self) -> bool {
        let verdict = self.verdict.lock().unwrap_or_else(PoisonError::into_inner);
        let verdict = self
            .opened
            .wait_while(verdict, |verdict| verdict.is_none())
            .unwrap_or_else(PoisonError::into_inner);
        *verdict == Some(true)
    }
}

/// Opens the gate without measuring if the thread starting the others
/// unwinds before it opens it itself: the scope would wait for them.
struct Opener<'a>(&'a Gate);

impl Drop for Opener<'_> {
    fn drop(&mut self) {
        self.0.open(false);
    }
}

/// What the threads share: the gate and the barrier, the flag that stops
/// them all together, how many passes make a repetition long enough, and the
/// first thing that went wrong.
struct Shared<'a> {
    gate: Gate,
    barrier: Barrier,
    stop: AtomicBool,
    passes: AtomicU64,
    failure: Mutex<Option<Error>>,
    control: &'a Control,
}

impl Shared<'_> {
    fn fail(&self, error: Error) {
        if let Ok(mut failure) = self.failure.lock() {
            failure.get_or_insert(error);
        }
        self.stop.store(true, Ordering::Relaxed);
    }

    /// Run `work` without letting an error or a panic leave a thread out of
    /// the next barrier, where the rest would wait for it forever.
    fn guarded<T>(&self, work: impl FnOnce() -> Result<T>) -> Option<T> {
        match catch_unwind(AssertUnwindSafe(work)) {
            Ok(Ok(value)) => Some(value),
            Ok(Err(error)) => {
                self.fail(error);
                None
            }
            Err(payload) => {
                self.fail(Error::Internal(panic_message(&*payload)));
                None
            }
        }
    }

    /// Wait for every thread, and tell them all the same: whether to go on.
    /// The flag is only written between one meeting's second barrier and the
    /// next meeting's first, so every thread reads the same value.
    fn meet(&self) -> bool {
        self.barrier.wait();
        let stop = self.stop.load(Ordering::Relaxed);
        self.barrier.wait();
        !stop
    }
}

pub fn bandwidth(
    cpus: &[usize],
    settings: &Settings,
    clock: &Clock,
    control: &Control,
) -> Result<Bandwidth> {
    measure(cpus, settings, clock, control, |_, builder| builder)
}

/// `bandwidth`, with `prepare` adjusting each thread's builder by its index:
/// how a test makes one of them fail to start.
fn measure(
    cpus: &[usize],
    settings: &Settings,
    clock: &Clock,
    control: &Control,
    prepare: impl Fn(usize, Builder) -> Builder,
) -> Result<Bandwidth> {
    if !(1..=MAX_REPETITIONS).contains(&settings.repetitions) {
        return Err(Error::BadSetting("repetitions"));
    }
    if cpus.is_empty() {
        return Err(Error::BadSetting("cpus"));
    }
    if settings.bytes < STEP || !settings.bytes.is_multiple_of(STEP) {
        return Err(Error::BadSize(settings.bytes));
    }
    kernels::check(settings.isa, settings.operation, settings.non_temporal)?;
    control.begin(settings.repetitions as u64);
    let shared = Shared {
        gate: Gate::new(),
        barrier: Barrier::new(cpus.len()),
        stop: AtomicBool::new(false),
        passes: AtomicU64::new(1),
        failure: Mutex::new(None),
        control,
    };
    let target = clock.min_sample_ns();
    let spans: Vec<(Vec<Span>, Option<Source>)> = std::thread::scope(|scope| {
        let opener = Opener(&shared.gate);
        let workers: Vec<_> = cpus
            .iter()
            .enumerate()
            .map(|(index, &cpu)| {
                let shared = &shared;
                prepare(index, Builder::new().name(format!("silux-bench-{cpu}")))
                    .spawn_scoped(scope, move || {
                        worker(cpu, index == 0, settings, target, shared)
                    })
            })
            .collect();
        let mut handles = Vec::with_capacity(workers.len());
        for worker in workers {
            match worker {
                Ok(handle) => handles.push(handle),
                Err(error) => shared.fail(Error::NoThread {
                    errno: error.raw_os_error().unwrap_or(0),
                }),
            }
        }
        shared.gate.open(handles.len() == cpus.len());
        drop(opener);
        handles
            .into_iter()
            .map(|handle| handle.join().unwrap_or_default())
            .collect()
    });

    if let Some(error) = shared.failure.lock().ok().and_then(|mut f| f.take()) {
        return Err(error);
    }
    control.check()?;
    let passes = shared.passes.load(Ordering::Relaxed);
    let arrays: u64 = if settings.operation == Operation::Copy {
        2
    } else {
        1
    };
    let moved = passes * settings.bytes as u64 * arrays * cpus.len() as u64;
    let frequency = spans.first().and_then(|(_, source)| *source);
    let spans: Vec<Vec<Span>> = spans.into_iter().map(|(spans, _)| spans).collect();
    let samples: Vec<f64> = (0..settings.repetitions)
        .filter_map(|rep| {
            let begin = spans.iter().filter_map(|s| s.get(rep)).map(|s| s.0).min()?;
            let end = spans.iter().filter_map(|s| s.get(rep)).map(|s| s.1).max()?;
            (end > begin).then(|| moved as f64 / (end - begin) as f64)
        })
        .collect();
    if samples.len() != settings.repetitions {
        return Err(Error::Internal("a repetition went missing".to_owned()));
    }
    // The mean of the threads in each repetition; a repetition some thread
    // couldn't measure has none, and then neither has the result.
    let hertz: Vec<f64> = (0..settings.repetitions)
        .filter_map(|rep| {
            let of_threads: Vec<f64> = spans
                .iter()
                .filter_map(|s| s.get(rep).and_then(|s| s.2))
                .collect();
            (of_threads.len() == cpus.len())
                .then(|| of_threads.iter().sum::<f64>() / of_threads.len() as f64)
        })
        .collect();
    let hz = (hertz.len() == samples.len())
        .then(|| stats::summarize(&hertz))
        .flatten();
    Ok(Bandwidth {
        gbps: stats::summarize(&samples).ok_or(Error::Clock("a sample came out empty"))?,
        threads: cpus.len(),
        passes,
        hz,
        frequency: hz.and(frequency),
    })
}

/// One thread: wait for the rest to exist, pin, map and touch its block,
/// time one pass, then the repetitions in step with the others. Returns when
/// each began and ended and what it ran at, and how that was measured.
fn worker(
    cpu: usize,
    leader: bool,
    settings: &Settings,
    target: f64,
    shared: &Shared<'_>,
) -> (Vec<Span>, Option<Source>) {
    let mut spans = Vec::with_capacity(settings.repetitions);
    if !shared.gate.pass() {
        return (spans, None);
    }
    let copy = settings.operation == Operation::Copy;
    let ready = shared.guarded(|| {
        pin_current_thread(cpu)?;
        let size = if copy {
            2 * settings.bytes + COPY_GAP
        } else {
            settings.bytes
        };
        let block = Block::reserve(size, settings.pages)?;
        let (a, b) = arrays(&block, settings.bytes, copy);
        // The first touch, by this thread: its pages come from its node.
        // SAFETY: the whole block is ours, aligned, a multiple of STEP.
        unsafe { kernels::run(Isa::Portable, Operation::Write, false, a, a, block.len()) };
        let begin = now_ns();
        // SAFETY: `check` accepted the settings; `a` and `b` are the
        // block's arrays, `bytes` long each, apart for a copy.
        let folded = unsafe {
            kernels::run(
                settings.isa,
                settings.operation,
                settings.non_temporal,
                a,
                b,
                settings.bytes,
            )
        };
        let one_pass = now_ns().saturating_sub(begin).max(1) as f64;
        std::hint::black_box(folded);
        let passes = (target / one_pass).ceil().max(1.0) as u64;
        shared.passes.fetch_max(passes, Ordering::Relaxed);
        // Opened once pinned: the counter is this thread's, on this CPU.
        Ok((block, Meter::open()))
    });
    if !shared.meet() {
        return (spans, None);
    }
    let Some((block, meter)) = ready else {
        return (spans, None);
    };
    let (a, b) = arrays(&block, settings.bytes, copy);
    let passes = shared.passes.load(Ordering::Relaxed);
    for _ in 0..settings.repetitions {
        let span = shared.guarded(|| {
            let mark = meter.begin();
            let begin = now_ns();
            for _ in 0..passes {
                // SAFETY: as in the timed pass above.
                let folded = unsafe {
                    kernels::run(
                        settings.isa,
                        settings.operation,
                        settings.non_temporal,
                        a,
                        b,
                        settings.bytes,
                    )
                };
                std::hint::black_box(folded);
            }
            let end = now_ns();
            let hz = meter.end(mark, end.saturating_sub(begin) as f64);
            Ok((begin, end, hz))
        });
        if let Some(span) = span {
            spans.push(span);
        }
        if shared.control.is_cancelled() {
            shared.stop.store(true, Ordering::Relaxed);
        }
        if !shared.meet() {
            break;
        }
        if leader {
            shared.control.advance();
        }
    }
    (spans, meter.source())
}

/// The two arrays of a copy, `COPY_GAP` apart, or the one of a read or a
/// write twice.
fn arrays(block: &Block, bytes: usize, copy: bool) -> (*mut u8, *mut u8) {
    let a = block.as_mut_ptr();
    let b = if copy {
        a.wrapping_add(bytes + COPY_GAP)
    } else {
        a
    };
    (a, b)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::common::topology::allowed_cpus;

    fn settings(operation: Operation, non_temporal: bool) -> Settings {
        Settings {
            operation,
            non_temporal,
            isa: Isa::widest(),
            bytes: 4 * 1024 * 1024,
            pages: Pages::Huge,
            repetitions: 3,
        }
    }

    #[test]
    fn every_operation_on_one_and_on_several_threads() {
        let clock = Clock::check().unwrap();
        let cpus = allowed_cpus();
        for threads in [&cpus[..1], &cpus[..cpus.len().min(4)]] {
            for (operation, non_temporal) in [
                (Operation::Read, false),
                (Operation::Write, false),
                (Operation::Write, true),
                (Operation::Copy, false),
                (Operation::Copy, true),
            ] {
                let result = bandwidth(
                    threads,
                    &settings(operation, non_temporal),
                    &clock,
                    &Control::default(),
                )
                .unwrap();
                assert_eq!(result.threads, threads.len());
                assert_eq!(result.gbps.count, 3);
                assert!(
                    result.gbps.median > 0.1 && result.gbps.median < 10_000.0,
                    "{result:?}"
                );
                // The frequency with the way it was measured, or neither.
                assert_eq!(result.hz.is_some(), result.frequency.is_some());
                if let Some(hz) = result.hz {
                    assert_eq!(hz.count, 3);
                    assert!(hz.median > 50e6 && hz.median < 10e9, "{hz:?}");
                }
            }
        }
    }

    #[test]
    fn a_failing_thread_stops_them_all() {
        let clock = Clock::check().unwrap();
        let mut cpus = allowed_cpus();
        cpus.truncate(2);
        cpus.push(libc::CPU_SETSIZE as usize);
        let result = bandwidth(
            &cpus,
            &settings(Operation::Read, false),
            &clock,
            &Control::default(),
        );
        assert!(matches!(result, Err(Error::BadCpu { .. })), "{result:?}");
    }

    #[test]
    fn a_thread_that_cannot_start_lets_the_others_go() {
        let cpus: Vec<usize> = allowed_cpus().into_iter().cycle().take(3).collect();
        let (sender, receiver) = std::sync::mpsc::channel();
        std::thread::spawn(move || {
            let clock = Clock::check().unwrap();
            // No address space holds a stack of 4 EiB: the third spawn fails.
            let result = measure(
                &cpus,
                &settings(Operation::Read, false),
                &clock,
                &Control::default(),
                |index, builder| {
                    if index == 2 {
                        builder.stack_size(1 << 62)
                    } else {
                        builder
                    }
                },
            );
            sender.send(result).ok();
        });
        let result = receiver
            .recv_timeout(std::time::Duration::from_secs(30))
            .expect("the threads that started never came back");
        assert!(matches!(result, Err(Error::NoThread { .. })), "{result:?}");
    }

    #[test]
    fn a_panic_while_starting_them_lets_the_others_go() {
        let cpus: Vec<usize> = allowed_cpus().into_iter().cycle().take(3).collect();
        let (sender, receiver) = std::sync::mpsc::channel();
        std::thread::spawn(move || {
            let clock = Clock::check().unwrap();
            let unwound = catch_unwind(|| {
                measure(
                    &cpus,
                    &settings(Operation::Read, false),
                    &clock,
                    &Control::default(),
                    |index, builder| {
                        if index == 2 {
                            panic!("while starting the third");
                        }
                        builder
                    },
                )
            });
            sender.send(unwound.is_err()).ok();
        });
        let unwound = receiver
            .recv_timeout(std::time::Duration::from_secs(30))
            .expect("the threads that started never came back");
        assert!(unwound);
    }

    #[test]
    fn a_cancel_stops_them_all() {
        let clock = Clock::check().unwrap();
        let control = Control::default();
        control.cancel();
        let cpus = allowed_cpus();
        let result = bandwidth(
            &cpus[..cpus.len().min(3)],
            &settings(Operation::Copy, false),
            &clock,
            &control,
        );
        assert_eq!(result, Err(Error::Cancelled));
    }

    #[test]
    fn bad_settings_are_errors() {
        let clock = Clock::check().unwrap();
        let control = Control::default();
        let one = [*allowed_cpus().first().unwrap()];
        assert_eq!(
            bandwidth(&[], &settings(Operation::Read, false), &clock, &control),
            Err(Error::BadSetting("cpus"))
        );
        let odd = Settings {
            bytes: 1000,
            ..settings(Operation::Read, false)
        };
        assert_eq!(
            bandwidth(&one, &odd, &clock, &control),
            Err(Error::BadSize(1000))
        );
        assert_eq!(
            bandwidth(&one, &settings(Operation::Read, true), &clock, &control),
            Err(Error::BadSetting("non_temporal"))
        );
    }
}
