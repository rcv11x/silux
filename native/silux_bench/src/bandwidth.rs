//! How fast memory moves: reads, writes or copies over a block per thread,
//! one thread or many, each pinned to its CPU.
//!
//! Every thread maps and touches its own block, so it lands on its CPU's
//! NUMA node. The repetitions start together, behind a barrier, and the
//! bandwidth of one is everything moved over the time from the first thread
//! starting to the last finishing: what the memory gave all of them at once.

use std::panic::{catch_unwind, AssertUnwindSafe};
use std::sync::atomic::{AtomicBool, AtomicU64, Ordering};
use std::sync::{Barrier, Mutex};

use crate::cancel::Control;
use crate::error::{panic_message, Error, Result};
use crate::kernels::{self, Isa, Operation, STEP};
use crate::memory::{Block, Pages};
use crate::stats::{self, Summary};
use crate::timer::{now_ns, Clock};
use crate::topology::pin_current_thread;

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
}

/// What the threads share: the barrier, the flag that stops them all
/// together, how many passes make a repetition long enough, and the first
/// thing that went wrong.
struct Shared<'a> {
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
        barrier: Barrier::new(cpus.len()),
        stop: AtomicBool::new(false),
        passes: AtomicU64::new(1),
        failure: Mutex::new(None),
        control,
    };
    let target = clock.min_sample_ns();
    let spans: Vec<Vec<(u64, u64)>> = std::thread::scope(|scope| {
        let workers: Vec<_> = cpus
            .iter()
            .enumerate()
            .map(|(index, &cpu)| {
                let shared = &shared;
                std::thread::Builder::new()
                    .name(format!("silux-bench-{cpu}"))
                    .spawn_scoped(scope, move || {
                        worker(cpu, index == 0, settings, target, shared)
                    })
            })
            .collect();
        let mut spans = Vec::with_capacity(workers.len());
        let mut spawned = true;
        for worker in workers {
            match worker {
                Ok(handle) => spans.push(handle.join().unwrap_or_default()),
                Err(error) => {
                    spawned = false;
                    shared.fail(Error::Internal(format!("no thread: {error}")));
                }
            }
        }
        if !spawned {
            // A thread that never started would have left the others at the
            // barrier: say so instead of returning half a measurement.
            spans.clear();
        }
        spans
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
    Ok(Bandwidth {
        gbps: stats::summarize(&samples).ok_or(Error::Clock("a sample came out empty"))?,
        threads: cpus.len(),
        passes,
    })
}

/// One thread: pin, map and touch its block, time one pass, then the
/// repetitions in step with the others. Returns when each began and ended.
fn worker(
    cpu: usize,
    leader: bool,
    settings: &Settings,
    target: f64,
    shared: &Shared<'_>,
) -> Vec<(u64, u64)> {
    let mut spans = Vec::with_capacity(settings.repetitions);
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
        Ok(block)
    });
    if !shared.meet() {
        return spans;
    }
    let Some(block) = ready else {
        return spans;
    };
    let (a, b) = arrays(&block, settings.bytes, copy);
    let passes = shared.passes.load(Ordering::Relaxed);
    for _ in 0..settings.repetitions {
        let span = shared.guarded(|| {
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
            Ok((begin, now_ns()))
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
    spans
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
    use crate::topology::allowed_cpus;

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
