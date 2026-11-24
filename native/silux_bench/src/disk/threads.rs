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
use crate::disk::buffers::Buffer;
use crate::disk::histogram::Histogram;
use crate::disk::job::{Direction, Job, Pattern};
use crate::disk::run::{Lap, Sample, SAMPLE_NS};
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
            next_ns += SAMPLE_NS;
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
                Direction::Read => shared.target.read_at(buffer.as_mut_slice(), offset)?,
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
    use std::sync::Arc;

    use super::*;
    use crate::disk::buffers::{stamps, STAMP_EVERY};
    use crate::disk::target::testing::Folder;
    use crate::disk::target::FILL_BLOCK;

    const SMALL: u64 = 8 << 20;

    fn job(pattern: Pattern, direction: Direction, block: usize, depth: usize) -> Job {
        Job {
            pattern,
            direction,
            block,
            depth,
            seconds: 0.2,
            seed: 3,
        }
    }

    fn filled(folder: &Folder, bytes: u64) -> Option<Target> {
        let target = folder.target(bytes)?;
        target.fill(1, &Control::default()).unwrap();
        Some(target)
    }

    /// Every 4 KiB of the file as it is now: where it says it goes, and the
    /// write it says it was.
    fn stamps_of(target: &Target) -> Vec<(u64, u64)> {
        let mut block =
            Buffer::random(FILL_BLOCK, target.align().memory, &mut Rng::new(1)).unwrap();
        let mut found = Vec::new();
        for index in 0..target.bytes() / FILL_BLOCK as u64 {
            target
                .read_at(block.as_mut_slice(), index * FILL_BLOCK as u64)
                .unwrap();
            found.extend(stamps(block.as_slice()));
        }
        found
    }

    #[test]
    fn each_of_the_four_tests_counts_what_it_moves() {
        let folder = Folder::new("four");
        let Some(target) = filled(&folder, SMALL) else {
            return;
        };
        let control = Control::default();
        for (pattern, block, depth) in [
            (Pattern::Sequential, 1 << 20, 8),
            (Pattern::Sequential, 1 << 20, 1),
            (Pattern::Random, 4096, 32),
            (Pattern::Random, 4096, 1),
        ] {
            for direction in [Direction::Read, Direction::Write] {
                let job = job(pattern, direction, block, depth);
                let lap = run(&target, &job, &control).unwrap();
                let what = format!("{pattern:?} {direction:?} {block} x{depth}");
                assert!(lap.requests > 0, "{what}");
                assert_eq!(lap.bytes, lap.requests * block as u64, "{what}");
                assert_eq!(lap.latency.count(), lap.requests, "{what}");
                assert_eq!(lap.threads, depth, "{what}");
                // It lasts what it was asked to, and the request in flight.
                assert!(lap.elapsed_ns >= 190_000_000, "{what}: {}", lap.elapsed_ns);
                assert!(lap.elapsed_ns < 2_000_000_000, "{what}: {}", lap.elapsed_ns);
                assert!(lap.bytes_per_second() > 0.0, "{what}");
                // No request took longer than the lap, and their times add
                // up to what the threads spent in it.
                let longest = lap.latency.max().unwrap();
                assert!(longest <= lap.elapsed_ns, "{what}");
                let spent = lap.latency.mean().unwrap() * lap.requests as f64;
                assert!(spent <= lap.elapsed_ns as f64 * depth as f64, "{what}");
                assert!(
                    spent >= lap.elapsed_ns as f64 * depth as f64 * 0.5,
                    "{what}"
                );
            }
        }
        assert!(folder.names().is_empty());
    }

    #[test]
    fn what_moved_is_noted_as_the_lap_goes() {
        let folder = Folder::new("samples");
        let Some(target) = filled(&folder, SMALL) else {
            return;
        };
        let job = Job {
            seconds: 0.9,
            ..job(Pattern::Random, Direction::Read, 4096, 2)
        };
        let lap = run(&target, &job, &Control::default()).unwrap();
        assert_eq!(lap.samples.len(), 3, "{:?}", lap.samples);
        for (index, pair) in lap.samples.windows(2).enumerate() {
            assert!(pair[1].at_ns > pair[0].at_ns);
            assert!(pair[1].bytes >= pair[0].bytes);
            assert!(pair[1].at_ns - pair[0].at_ns >= SAMPLE_NS / 2, "{index}");
        }
        assert!(lap.samples[0].at_ns >= SAMPLE_NS);
        assert!(lap.samples[2].bytes <= lap.bytes);
        assert!(lap.samples[2].bytes > 0);
    }

    #[test]
    fn a_write_lands_where_its_stamp_says() {
        let folder = Folder::new("stamps");
        let Some(target) = filled(&folder, SMALL) else {
            return;
        };
        assert!(stamps_of(&target).iter().all(|(_, turn)| *turn == 0));
        for (pattern, block, depth) in [
            (Pattern::Random, 4096, 8),
            (Pattern::Sequential, 1 << 20, 4),
        ] {
            let job = job(pattern, Direction::Write, block, depth);
            let lap = run(&target, &job, &Control::default()).unwrap();
            let found = stamps_of(&target);
            assert_eq!(found.len() as u64, SMALL / STAMP_EVERY as u64);
            for (index, (place, _)) in found.iter().enumerate() {
                assert_eq!(*place, (index * STAMP_EVERY) as u64);
            }
            // The lap wrote: blocks carry the moment of a write, not the
            // zero the file was filled with.
            let rewritten = found.iter().filter(|(_, turn)| *turn != 0).count() as u64;
            assert!(rewritten > 0);
            assert!(rewritten * STAMP_EVERY as u64 <= lap.bytes.max(SMALL));
        }
    }

    #[test]
    fn a_sequential_lap_goes_round_the_file_in_order() {
        let folder = Folder::new("sequential");
        let Some(target) = filled(&folder, SMALL) else {
            return;
        };
        let job = job(Pattern::Sequential, Direction::Write, 1 << 20, 1);
        let lap = run(&target, &job, &Control::default()).unwrap();
        // One thread, one block after another: each MiB of the file was
        // written after the one before it, up to where the lap stopped.
        let turns: Vec<u64> = stamps_of(&target)
            .chunks(FILL_BLOCK / STAMP_EVERY)
            .map(|block| block[0].1)
            .collect();
        let last = ((lap.requests - 1) % 8) as usize;
        for index in 0..8 {
            if index != last {
                let next = (index + 1) % 8;
                assert!(turns[index] < turns[next], "{turns:?} {last}");
            }
        }
    }

    #[test]
    fn a_read_changes_nothing() {
        let folder = Folder::new("reads");
        let Some(target) = filled(&folder, SMALL) else {
            return;
        };
        let before = stamps_of(&target);
        for pattern in [Pattern::Sequential, Pattern::Random] {
            run(
                &target,
                &job(pattern, Direction::Read, 4096, 4),
                &Control::default(),
            )
            .unwrap();
        }
        assert_eq!(stamps_of(&target), before);
    }

    #[test]
    fn nothing_goes_through_the_page_cache_and_what_does_is_seen() {
        let folder = Folder::new("lap-cache");
        let Some(target) = filled(&folder, SMALL) else {
            return;
        };
        if target.no_cow() == Some(false) {
            return;
        }
        let control = Control::default();
        for direction in [Direction::Read, Direction::Write] {
            for pattern in [Pattern::Sequential, Pattern::Random] {
                run(&target, &job(pattern, direction, 4096, 4), &control).unwrap();
                assert_eq!(target.cached_bytes(), Ok(0), "{pattern:?} {direction:?}");
            }
        }
        // The same lap without direct reads: the check has to notice.
        target.set_direct(false).unwrap();
        run(
            &target,
            &job(Pattern::Sequential, Direction::Read, 1 << 20, 1),
            &control,
        )
        .unwrap();
        assert!(target.cached_bytes().unwrap() > 0);
    }

    #[test]
    fn a_cancel_stops_the_lap() {
        let folder = Folder::new("cancel");
        let Some(target) = filled(&folder, SMALL) else {
            return;
        };
        let control = Arc::new(Control::default());
        let canceller = {
            let control = Arc::clone(&control);
            std::thread::spawn(move || {
                std::thread::sleep(Duration::from_millis(100));
                control.cancel();
            })
        };
        let job = Job {
            seconds: 60.0,
            ..job(Pattern::Random, Direction::Read, 4096, 4)
        };
        let began = now_ns();
        assert_eq!(run(&target, &job, &control).err(), Some(Error::Cancelled));
        assert!(now_ns() - began < 5_000_000_000);
        canceller.join().unwrap();
        // And one cancelled before it starts doesn't start.
        assert_eq!(run(&target, &job, &control).err(), Some(Error::Cancelled));
    }

    #[test]
    fn bad_settings_are_errors() {
        let folder = Folder::new("settings");
        let Some(target) = filled(&folder, SMALL) else {
            return;
        };
        let control = Control::default();
        let good = job(Pattern::Random, Direction::Read, 4096, 1);
        for (bad, error) in [
            (Job { depth: 0, ..good }, Error::BadSetting("depth")),
            (
                Job {
                    seconds: 0.0,
                    ..good
                },
                Error::BadSetting("seconds"),
            ),
            (Job { block: 0, ..good }, Error::BadSize(0)),
            (
                Job {
                    block: 4097,
                    ..good
                },
                Error::BadSize(4097),
            ),
            (
                Job {
                    block: 16 << 20,
                    ..good
                },
                Error::BadSize(16 << 20),
            ),
        ] {
            assert_eq!(run(&target, &bad, &control).err(), Some(error));
        }
    }

    #[test]
    fn a_failing_request_stops_them_all() {
        let folder = Folder::new("failing");
        let Some(target) = filled(&folder, SMALL) else {
            return;
        };
        // The file loses its second half: a read there finds nothing.
        target.truncate(SMALL / 2);
        let job = Job {
            seconds: 60.0,
            ..job(Pattern::Random, Direction::Read, 4096, 8)
        };
        let began = now_ns();
        assert_eq!(
            run(&target, &job, &Control::default()).err(),
            Some(Error::Io {
                call: "pread",
                errno: 0
            })
        );
        assert!(now_ns() - began < 5_000_000_000);
    }

    #[test]
    fn a_thread_that_cannot_start_lets_the_others_go() {
        let folder = Folder::new("no-thread");
        let Some(target) = filled(&folder, SMALL) else {
            return;
        };
        let job = job(Pattern::Random, Direction::Read, 4096, 4);
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

    /// Not a test: the figures of each of the four tests in a folder, to
    /// set against fio's. It only reads unless told to write too.
    ///
    /// `SILUX_BENCH_DISK_DIR=/a/folder cargo test --release -- --ignored
    /// --nocapture figures`, with these variables to change it:
    ///
    /// - `SILUX_BENCH_DISK_WRITE=1`: the writes too;
    /// - `SILUX_BENCH_DISK_SECONDS`, `SILUX_BENCH_DISK_MIB` and
    ///   `SILUX_BENCH_DISK_ROUNDS`: instead of 5 s, 1 GiB and once;
    /// - `SILUX_BENCH_DISK_THEN=/a/program`: run after each round with the
    ///   file's path as its argument, while the file is held open. That is
    ///   how fio measures the same blocks of the same file, in turns.
    #[test]
    #[ignore = "a measurement, printed"]
    fn figures() {
        let number = |name: &str, default: f64| {
            std::env::var(name)
                .ok()
                .and_then(|text| text.parse().ok())
                .unwrap_or(default)
        };
        let seconds = number("SILUX_BENCH_DISK_SECONDS", 5.0);
        let bytes = (number("SILUX_BENCH_DISK_MIB", 1024.0) as u64) << 20;
        let rounds = number("SILUX_BENCH_DISK_ROUNDS", 1.0) as usize;
        let writes = std::env::var_os("SILUX_BENCH_DISK_WRITE").is_some();
        let then = std::env::var_os("SILUX_BENCH_DISK_THEN");
        let folder = Folder::new("figures");
        let target = folder.target(bytes).expect("a folder to measure in");
        let control = Control::default();
        let began = now_ns();
        target.fill(1, &control).unwrap();
        println!(
            "{} MiB written in {:.1} s; align {:?}, no_cow {:?}, {:?}",
            bytes >> 20,
            (now_ns() - began) as f64 / 1e9,
            target.align(),
            target.no_cow(),
            target.creation()
        );
        for round in 1..=rounds {
            println!("round {round}");
            for (name, pattern, block, depth) in [
                ("SEQ1M Q8T1", Pattern::Sequential, 1 << 20, 8),
                ("SEQ1M Q1T1", Pattern::Sequential, 1 << 20, 1),
                ("RND4K Q32T1", Pattern::Random, 4096, 32),
                ("RND4K Q1T1", Pattern::Random, 4096, 1),
            ] {
                for direction in [Direction::Read, Direction::Write] {
                    if direction == Direction::Write && !writes {
                        continue;
                    }
                    let job = Job {
                        pattern,
                        direction,
                        block,
                        depth,
                        seconds,
                        seed: round as u64,
                    };
                    let lap = run(&target, &job, &control).unwrap();
                    println!(
                        "  silux {name} {direction:?}: {:.1} MB/s, {:.0} IOPS, mean {:.1} µs, \
                         p99 {:.1} µs, cached {:?}",
                        lap.bytes_per_second() / 1e6,
                        lap.requests_per_second(),
                        lap.latency.mean().unwrap_or(0.0) / 1e3,
                        lap.latency.percentile(99.0).unwrap_or(0) as f64 / 1e3,
                        target.cached_bytes()
                    );
                }
            }
            if let Some(then) = &then {
                let status = std::process::Command::new(then)
                    .arg(target.path_while_open())
                    .status()
                    .unwrap();
                assert!(status.success());
            }
        }
    }
}
