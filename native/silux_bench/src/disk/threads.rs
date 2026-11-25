//! A lap with a queue made of threads: as many as requests in flight, each
//! reading or writing one block at a time and waiting for it.
//!
//! It runs anywhere, without asking the kernel for anything new, so it is
//! what measures where io_uring isn't there or isn't allowed. With a queue
//! of one it is the same thing an asynchronous queue does; with more, each
//! request in flight costs a thread, which shows on the fastest disks.
//!
//! Sequential requests take their blocks from one counter shared by all the
//! threads, so the blocks in flight are consecutive ones, as in a queue. It
//! isn't `fio --ioengine=psync --numjobs=N`, where each job reads the file
//! from its beginning on its own.

use std::panic::{catch_unwind, AssertUnwindSafe};
use std::sync::atomic::{AtomicBool, AtomicU64, Ordering};
use std::sync::{Barrier, Mutex};
use std::thread::Builder;
use std::time::Duration;

use crate::common::cancel::Control;
use crate::common::error::{panic_message, Error, Result};
use crate::common::gate::{Gate, Opener};
use crate::common::rng::Rng;
use crate::common::timer::now_ns;
use crate::disk::buffers::{check_read, Buffer};
use crate::disk::histogram::Histogram;
use crate::disk::job::{Direction, Job, Pattern};
use crate::disk::run::{next_sample, Lap, Sample, SAMPLE_NS};
use crate::disk::target::Target;

/// How long the timing thread sleeps at most between two looks at whether
/// to stop: a cancel is felt this fast, plus the request in flight.
const LOOK_NS: u64 = 50_000_000;

/// What one thread has moved so far, on a cache line of its own: the others
/// write theirs at the same time.
#[repr(align(64))]
#[derive(Default)]
struct Moved(AtomicU64);

/// What a thread did in the lap.
#[derive(Default)]
struct Tally {
    bytes: u64,
    requests: u64,
    latency: Histogram,
    /// When its last request ended.
    last_ns: u64,
}

struct Shared<'a> {
    target: &'a Target,
    job: &'a Job,
    blocks: u64,
    gate: Gate,
    /// The threads and the one that times them: once with everything
    /// ready, and again with the deadline set.
    barrier: Barrier,
    stop: AtomicBool,
    deadline_ns: AtomicU64,
    /// The next block of a sequential job.
    cursor: AtomicU64,
    moved: Vec<Moved>,
    failure: Mutex<Option<Error>>,
}

impl Shared<'_> {
    fn fail(&self, error: Error) {
        if let Ok(mut failure) = self.failure.lock() {
            failure.get_or_insert(error);
        }
        self.stop.store(true, Ordering::Relaxed);
    }

    /// Run `work` so that neither an error nor a panic keeps a thread from
    /// the barrier, where the rest would wait for it forever.
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

    fn moved(&self) -> u64 {
        self.moved
            .iter()
            .map(|moved| moved.0.load(Ordering::Relaxed))
            .sum()
    }
}

/// One lap of `job` over `target`, which has to be filled already.
pub fn run(target: &Target, job: &Job, control: &Control) -> Result<Lap> {
    measure(target, job, control, |_, builder| builder)
}

/// `run`, with `prepare` adjusting each thread's builder by its index: how a
/// test makes one of them fail to start.
fn measure(
    target: &Target,
    job: &Job,
    control: &Control,
    prepare: impl Fn(usize, Builder) -> Builder,
) -> Result<Lap> {
    let blocks = job.blocks(target.bytes(), target.align().offset)?;
    control.check()?;
    let lasts_ns = (job.seconds * 1e9) as u64;
    let shared = Shared {
        target,
        job,
        blocks,
        gate: Gate::default(),
        barrier: Barrier::new(job.depth + 1),
        stop: AtomicBool::new(false),
        deadline_ns: AtomicU64::new(0),
        cursor: AtomicU64::new(0),
        moved: (0..job.depth).map(|_| Moved::default()).collect(),
        failure: Mutex::new(None),
    };
    let mut began_ns = 0;
    let mut samples = Vec::new();
    let tallies: Vec<Tally> = std::thread::scope(|scope| {
        let opener = Opener(&shared.gate);
        let workers: Vec<_> = (0..job.depth)
            .map(|index| {
                let shared = &shared;
                prepare(index, Builder::new().name(format!("silux-disk-{index}")))
                    .spawn_scoped(scope, move || worker(index, shared))
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
        let all = handles.len() == job.depth;
        shared.gate.open(all);
        drop(opener);
        if all {
            shared.barrier.wait();
            began_ns = now_ns();
            let deadline_ns = began_ns.saturating_add(lasts_ns);
            shared.deadline_ns.store(deadline_ns, Ordering::Relaxed);
            shared.barrier.wait();
            samples = watch(&shared, began_ns, deadline_ns, control);
        }
        handles
            .into_iter()
            .map(|handle| handle.join().unwrap_or_default())
            .collect()
    });

    if let Some(error) = shared.failure.lock().ok().and_then(|mut f| f.take()) {
        return Err(error);
    }
    control.check()?;
    let mut lap = Lap {
        bytes: 0,
        requests: 0,
        elapsed_ns: 0,
        latency: Histogram::default(),
        samples,
        threads: job.depth,
    };
    let mut ended_ns = began_ns;
    for tally in &tallies {
        lap.bytes += tally.bytes;
        lap.requests += tally.requests;
        lap.latency.merge(&tally.latency);
        ended_ns = ended_ns.max(tally.last_ns);
    }
    // A lap in which nothing ended lasted what it was asked to.
    lap.elapsed_ns = if lap.requests == 0 {
        lasts_ns
    } else {
        ended_ns - began_ns
    };
    Ok(lap)
}

/// The timing thread's part: note how much has moved every `SAMPLE_NS`, and
/// stop the others when the lap is cancelled.
fn watch(shared: &Shared<'_>, began_ns: u64, deadline_ns: u64, control: &Control) -> Vec<Sample> {
    let mut samples = Vec::new();
    let mut next_ns = began_ns + SAMPLE_NS;
    loop {
        let now = now_ns();
        if now >= deadline_ns || shared.stop.load(Ordering::Relaxed) {
            break;
        }
        if control.is_cancelled() {
            shared.stop.store(true, Ordering::Relaxed);
            break;
        }
        if now >= next_ns {
            samples.push(Sample {
                at_ns: now - began_ns,
                bytes: shared.moved(),
            });
            next_ns = next_sample(next_ns, now);
            continue;
        }
        let until = next_ns.min(deadline_ns) - now;
        std::thread::sleep(Duration::from_nanos(until.min(LOOK_NS)));
    }
    samples
}

/// One thread of the queue: its buffer, the two meetings with the rest, and
/// then one request after another until the time is up.
fn worker(index: usize, shared: &Shared<'_>) -> Tally {
    let mut tally = Tally::default();
    if !shared.gate.pass() {
        return tally;
    }
    let job = shared.job;
    let ready = shared.guarded(|| {
        // Each thread its own data and its own path through the file.
        let mut rng = Rng::new(job.seed.wrapping_add(index as u64));
        let buffer = Buffer::random(job.block, shared.target.align().memory, &mut rng)?;
        Ok((buffer, rng))
    });
    shared.barrier.wait();
    shared.barrier.wait();
    let Some((mut buffer, mut rng)) = ready else {
        return tally;
    };
    let deadline_ns = shared.deadline_ns.load(Ordering::Relaxed);
    let moved = shared.moved.get(index);
    shared.guarded(|| {
        loop {
            let begin = now_ns();
            if begin >= deadline_ns || shared.stop.load(Ordering::Relaxed) {
                return Ok(());
            }
            let block = match job.pattern {
                Pattern::Sequential => {
                    shared.cursor.fetch_add(1, Ordering::Relaxed) % shared.blocks
                }
                Pattern::Random => rng.below(shared.blocks),
            };
            let offset = block * job.block as u64;
            match job.direction {
                Direction::Read => {
                    shared.target.read_at(buffer.as_mut_slice(), offset)?;
                    check_read(buffer.as_slice(), offset)?;
                }
                Direction::Write => {
                    // The moment it is written: a block written twice in
                    // the same place isn't the same block either.
                    buffer.stamp(offset, begin);
                    shared.target.write_at(buffer.as_slice(), offset)?;
                }
            }
            let end = now_ns();
            tally.bytes += job.block as u64;
            tally.requests += 1;
            tally.latency.record(end.saturating_sub(begin));
            tally.last_ns = end;
            if let Some(moved) = moved {
                moved.0.fetch_add(job.block as u64, Ordering::Relaxed);
            }
        }
    });
    tally
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::disk::target::testing::Folder;

    /// What the engines have in common is tested for both in `engines`.
    #[test]
    fn a_thread_that_cannot_start_lets_the_others_go() {
        let folder = Folder::new("no-thread");
        let Some(target) = folder.target(8 << 20) else {
            return;
        };
        target.fill(1, &Control::default()).unwrap();
        let job = Job {
            pattern: Pattern::Random,
            direction: Direction::Read,
            block: 4096,
            depth: 4,
            seconds: 0.2,
            seed: 3,
        };
        // No address space holds a stack of 4 EiB: the third spawn fails.
        let lap = measure(&target, &job, &Control::default(), |index, builder| {
            if index == 2 {
                builder.stack_size(1 << 62)
            } else {
                builder
            }
        });
        assert!(matches!(lap, Err(Error::NoThread { .. })), "{lap:?}");
        // And the file is as usable as before.
        assert!(run(&target, &job, &Control::default()).is_ok());
    }
}
