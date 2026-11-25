//! What a lap has to do whichever engine runs it: every test here goes
//! through the queue of threads and through io_uring, on the same file.

use std::sync::Arc;
use std::time::Duration;

use crate::common::cancel::Control;
use crate::common::error::{Error, Result};
use crate::common::rng::Rng;
use crate::common::timer::now_ns;
use crate::disk::buffers::{stamps, Buffer, STAMP_EVERY};
use crate::disk::job::{Direction, Job, Pattern};
use crate::disk::run::{Lap, SAMPLE_NS};
use crate::disk::target::testing::Folder;
use crate::disk::target::{Target, FILL_BLOCK};
use crate::disk::{threads, uring};

const SMALL: u64 = 8 << 20;

type Run = fn(&Target, &Job, &Control) -> Result<Lap>;

/// The engines there are here: the threads always, and io_uring where the
/// kernel gives a ring (a container may not).
fn engines() -> Vec<(&'static str, Run)> {
    let mut engines: Vec<(&'static str, Run)> = vec![("threads", threads::run)];
    match uring::probe() {
        Ok(()) => engines.push(("io_uring", uring::run)),
        Err(error) => eprintln!("io_uring not tested here: {error}"),
    }
    engines
}

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
/// write it says it was. Read one block at a time, by neither engine.
fn stamps_of(target: &Target) -> Vec<(u64, u64)> {
    let mut block = Buffer::random(FILL_BLOCK, target.align().memory, &mut Rng::new(1)).unwrap();
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
    for (engine, run) in engines() {
        for (pattern, block, depth) in [
            (Pattern::Sequential, 1 << 20, 8),
            (Pattern::Sequential, 1 << 20, 1),
            (Pattern::Random, 4096, 32),
            (Pattern::Random, 4096, 1),
        ] {
            for direction in [Direction::Read, Direction::Write] {
                let job = job(pattern, direction, block, depth);
                let lap = run(&target, &job, &control).unwrap();
                let what = format!("{engine} {pattern:?} {direction:?} {block} x{depth}");
                assert!(lap.requests > 0, "{what}");
                assert_eq!(lap.bytes, lap.requests * block as u64, "{what}");
                assert_eq!(lap.latency.count(), lap.requests, "{what}");
                // A thread for each request in flight, or one for them all.
                let threads = if engine == "threads" { depth } else { 1 };
                assert_eq!(lap.threads, threads, "{what}");
                // It lasts what it was asked to, and the requests in flight.
                assert!(lap.elapsed_ns >= 190_000_000, "{what}: {}", lap.elapsed_ns);
                assert!(lap.elapsed_ns < 2_000_000_000, "{what}: {}", lap.elapsed_ns);
                assert!(lap.bytes_per_second() > 0.0, "{what}");
                // No request took longer than the lap, and their times add
                // up to what the queue spent in it.
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
    }
    assert!(folder.names().is_empty());
}

#[test]
fn what_moved_is_noted_as_the_lap_goes() {
    let folder = Folder::new("samples");
    let Some(target) = filled(&folder, SMALL) else {
        return;
    };
    for (engine, run) in engines() {
        let job = Job {
            seconds: 0.9,
            ..job(Pattern::Random, Direction::Read, 4096, 2)
        };
        let lap = run(&target, &job, &Control::default()).unwrap();
        // A quarter of a second each; one fewer when the watcher woke late.
        assert!(
            (2..=3).contains(&lap.samples.len()),
            "{engine} {:?}",
            lap.samples
        );
        for pair in lap.samples.windows(2) {
            assert!(pair[1].at_ns > pair[0].at_ns, "{engine}");
            assert!(pair[1].bytes >= pair[0].bytes, "{engine}");
            assert!(pair[1].at_ns - pair[0].at_ns >= SAMPLE_NS / 2, "{engine}");
        }
        assert!(lap.samples[0].at_ns >= SAMPLE_NS, "{engine}");
        assert!(lap.samples[2].bytes <= lap.bytes, "{engine}");
        assert!(lap.samples[2].bytes > 0, "{engine}");
    }
}

#[test]
fn a_write_lands_where_its_stamp_says() {
    let folder = Folder::new("stamps");
    for (engine, run) in engines() {
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
                assert_eq!(*place, (index * STAMP_EVERY) as u64, "{engine}");
            }
            // The lap wrote: blocks carry the moment of a write, not the
            // zero the file was filled with.
            let rewritten = found.iter().filter(|(_, turn)| *turn != 0).count() as u64;
            assert!(rewritten > 0, "{engine}");
            assert!(
                rewritten * STAMP_EVERY as u64 <= lap.bytes.max(SMALL),
                "{engine}"
            );
        }
    }
}

#[test]
fn a_sequential_lap_goes_round_the_file_in_order() {
    let folder = Folder::new("sequential");
    for (engine, run) in engines() {
        let Some(target) = filled(&folder, SMALL) else {
            return;
        };
        let job = job(Pattern::Sequential, Direction::Write, 1 << 20, 1);
        let lap = run(&target, &job, &Control::default()).unwrap();
        // One request at a time, one block after another: each MiB of the
        // file was written after the one before it, up to where it stopped.
        let turns: Vec<u64> = stamps_of(&target)
            .chunks(FILL_BLOCK / STAMP_EVERY)
            .map(|block| block[0].1)
            .collect();
        let written = lap.requests as usize;
        if written < turns.len() {
            // A slow disk didn't go round once: what it wrote, in order, and
            // the rest as the fill left it.
            for index in 1..written {
                assert!(turns[index - 1] < turns[index], "{engine} {turns:?}");
            }
            for turn in &turns[written..] {
                assert!(*turn < turns[0], "{engine} {turns:?}");
            }
            continue;
        }
        let last = ((lap.requests - 1) % 8) as usize;
        for index in 0..8 {
            if index != last {
                let next = (index + 1) % 8;
                assert!(turns[index] < turns[next], "{engine} {turns:?} {last}");
            }
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
    for (_engine, run) in engines() {
        for pattern in [Pattern::Sequential, Pattern::Random] {
            run(
                &target,
                &job(pattern, Direction::Read, 4096, 4),
                &Control::default(),
            )
            .unwrap();
        }
    }
    assert_eq!(stamps_of(&target), before);
}

/// A read is checked against the stamp of the block it asked for: seen to
/// notice when the file holds another block there.
#[test]
fn a_read_that_brings_another_block_is_an_error() {
    let folder = Folder::new("wrong-block");
    let Some(target) = filled(&folder, SMALL) else {
        return;
    };
    // The third MiB of the file, written as if it were the sixth.
    let mut wrong = Buffer::random(FILL_BLOCK, target.align().memory, &mut Rng::new(2)).unwrap();
    wrong.stamp(5 * FILL_BLOCK as u64, 9);
    target
        .write_at(wrong.as_slice(), 2 * FILL_BLOCK as u64)
        .unwrap();
    for (engine, run) in engines() {
        for (block, depth) in [(1 << 20, 1), (1 << 20, 4), (4096, 1)] {
            let job = Job {
                seconds: 60.0,
                ..job(Pattern::Sequential, Direction::Read, block, depth)
            };
            let began = now_ns();
            let found = run(&target, &job, &Control::default());
            let Err(Error::Internal(text)) = &found else {
                panic!("{engine}: {found:?}");
            };
            assert!(
                text.contains("read at offset 2097152 says it belongs at 5242880"),
                "{engine}: {text}"
            );
            // It stops the lap, long before its minute: a slow disk under
            // the other tests' writes took more than 5 s to get there.
            assert!(now_ns() - began < 30_000_000_000, "{engine}");
        }
    }
}

#[test]
fn nothing_goes_through_the_page_cache_and_what_does_is_seen() {
    let folder = Folder::new("lap-cache");
    for (engine, run) in engines() {
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
                assert_eq!(
                    target.cached_bytes(),
                    Ok(0),
                    "{engine} {pattern:?} {direction:?}"
                );
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
        assert!(target.cached_bytes().unwrap() > 0, "{engine}");
    }
}

#[test]
fn a_cancel_stops_the_lap() {
    let folder = Folder::new("cancel");
    let Some(target) = filled(&folder, SMALL) else {
        return;
    };
    for (engine, run) in engines() {
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
        assert_eq!(
            run(&target, &job, &control).err(),
            Some(Error::Cancelled),
            "{engine}"
        );
        assert!(now_ns() - began < 5_000_000_000, "{engine}");
        canceller.join().unwrap();
        // And one cancelled before it starts doesn't start.
        assert_eq!(
            run(&target, &job, &control).err(),
            Some(Error::Cancelled),
            "{engine}"
        );
    }
}

#[test]
fn bad_settings_are_errors() {
    let folder = Folder::new("settings");
    let Some(target) = filled(&folder, SMALL) else {
        return;
    };
    let control = Control::default();
    let good = job(Pattern::Random, Direction::Read, 4096, 1);
    for (engine, run) in engines() {
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
            assert_eq!(run(&target, &bad, &control).err(), Some(error), "{engine}");
        }
    }
}

#[test]
fn a_failing_request_stops_them_all() {
    let folder = Folder::new("failing");
    for (engine, run) in engines() {
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
        let found = run(&target, &job, &Control::default()).err();
        assert!(
            matches!(found, Some(Error::Io { errno: 0, .. })),
            "{engine}: {found:?}"
        );
        assert!(now_ns() - began < 5_000_000_000, "{engine}");
    }
}

/// Not a test: the figures of each of the four tests in a folder, by both
/// engines. It only reads unless told to write too.
///
/// `SILUX_BENCH_DISK_DIR=/a/folder cargo test --release -- --ignored
/// --nocapture figures`, with these variables to change it:
///
/// - `SILUX_BENCH_DISK_WRITE=1`: the writes too;
/// - `SILUX_BENCH_DISK_SECONDS`, `SILUX_BENCH_DISK_MIB` and
///   `SILUX_BENCH_DISK_ROUNDS`: instead of 5 s, 1 GiB and once;
/// - `SILUX_BENCH_DISK_THEN=/a/program`: run after each round with the
///   file's path as its argument, while the file is held open. That is how
///   fio measures the same blocks of the same file, in turns.
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
                for (engine, run) in engines() {
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
                        "  {engine:<8} {name} {direction:?}: {:.1} MB/s, {:.0} IOPS, mean {:.1} µs, \
                         p99 {:.1} µs, cached {:?}",
                        lap.bytes_per_second() / 1e6,
                        lap.requests_per_second(),
                        lap.latency.mean().unwrap_or(0.0) / 1e3,
                        lap.latency.percentile(99.0).unwrap_or(0) as f64 / 1e3,
                        target.cached_bytes()
                    );
                }
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
