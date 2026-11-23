//! How long a load takes when nothing can anticipate it: pointer chasing
//! through one random cycle over every line of the block.
//!
//! - Random, because a stride the prefetcher can guess arrives before it's
//!   asked for, and what's timed is then the prefetcher.
//! - Each load's address is the value of the one before, so the processor
//!   can't start a load until the last has finished: what's timed is one
//!   load's latency, not how many it can keep in flight.
//! - One cycle through every line (Sattolo), so the chase covers the whole
//!   block and no smaller loop inside it.

use std::hint::black_box;

use crate::cancel::Control;
use crate::error::{Error, Result};
use crate::memory::{Block, Pages, Residency, LINE};
use crate::rng::Rng;
use crate::stats::{self, Summary};
use crate::timer::{now_ns, Clock};

/// Loads per trip round the chase loop: enough that the loop's own counter
/// is lost in the latency of the loads.
const UNROLL: u64 = 16;
/// The warm-up is a whole lap, up to this many hops. A lap loads a block that
/// fits in a cache and settles the TLB; in a block a few times the last
/// cache it also leaves there what a steady walk would find, instead of the
/// lines the linking wrote last, which would make the first lap look faster.
/// Past 512 MiB the cache holds too little of the block for it to matter.
const WARMUP_MAX_HOPS: u64 = 8 * 1024 * 1024;
/// Chunk of work between two looks at the cancel flag: about 50 ms at the
/// slowest, a random swap that misses every cache.
const SWAPS_PER_CHECK: usize = 1 << 19;
const HOPS_PER_CHECK: u64 = 1 << 19;
pub const MAX_REPETITIONS: usize = 1000;

#[derive(Debug, Clone, Copy)]
pub struct Settings {
    pub pages: Pages,
    pub repetitions: usize,
    pub seed: u64,
}

#[derive(Debug, Clone, PartialEq)]
pub struct Point {
    pub bytes: usize,
    /// Nanoseconds per load, over the repetitions.
    pub ns: Summary,
    /// Loads per repetition.
    pub hops: u64,
    /// Times the point was measured again for being noisy.
    pub retries: usize,
}

#[derive(Debug, Clone, PartialEq)]
pub struct Curve {
    pub points: Vec<Point>,
    pub pages: Pages,
    /// What the kernel gave for the largest block, after the curve touched it
    /// all.
    pub residency: Option<Residency>,
    /// Where the last point ran.
    pub cpu: Option<usize>,
}

/// Latency at each block size, smallest first, all on one block mapped once.
pub fn curve(
    sizes: &[usize],
    settings: &Settings,
    clock: &Clock,
    control: &Control,
) -> Result<Curve> {
    if !(1..=MAX_REPETITIONS).contains(&settings.repetitions) {
        return Err(Error::BadSetting("repetitions"));
    }
    let mut sizes = sizes.to_vec();
    sizes.sort_unstable();
    sizes.dedup();
    if let Some(bad) = sizes.iter().find(|s| **s < 2 * LINE || **s % LINE != 0) {
        return Err(Error::BadSize(*bad));
    }
    let largest = *sizes.last().ok_or(Error::NoSizes)?;
    let block = Block::reserve(largest, settings.pages)?;
    let mut rng = Rng::new(settings.seed);
    control.begin(sizes.len() as u64);
    let mut points = Vec::with_capacity(sizes.len());
    for bytes in sizes {
        control.check()?;
        let start = link_cycle(&block, bytes, &mut rng, control)?;
        let (measured, retries) = stats::steadiest(
            // SAFETY: `link_cycle` just made every word it reaches from
            // `start` hold the address of another such word, inside `block`,
            // which lives until the end of this function; an attempt again
            // walks the same cycle.
            || unsafe { measure(start, (bytes / LINE) as u64, clock, settings, control) },
            |m| m.ns.spread,
        )?;
        points.push(Point {
            bytes,
            ns: measured.ns,
            hops: measured.hops,
            retries,
        });
        control.advance();
    }
    Ok(Curve {
        points,
        pages: settings.pages,
        residency: block.residency(),
        cpu: crate::topology::current_cpu(),
    })
}

/// The first word of line `i`.
///
/// # Safety
/// `i` must be a line of the block: `(i + 1) * LINE <= block.len()`.
unsafe fn word(base: *mut u8, i: usize) -> *mut usize {
    // SAFETY: the caller keeps `i` inside the block; lines are LINE apart from
    // a page-aligned base, so the word is aligned.
    unsafe { base.add(i * LINE).cast::<usize>() }
}

/// Link the first `bytes` of `block` into one random cycle: the first word
/// of each line holds the address of the next line to visit.
pub fn link_cycle(
    block: &Block,
    bytes: usize,
    rng: &mut Rng,
    control: &Control,
) -> Result<*const usize> {
    let lines = bytes / LINE;
    if lines < 2 || bytes > block.len() {
        return Err(Error::BadSize(bytes));
    }
    let base = block.as_mut_ptr();
    // Each line holds its own number. Written in order, by the measuring
    // thread: the pages' first touch, which also puts them on its node.
    for i in 0..lines {
        // SAFETY: `i < lines` and `lines * LINE <= block.len()`.
        unsafe { word(base, i).write(i) };
    }
    // Sattolo's shuffle. Unlike Fisher–Yates it picks `j` below `i`, never
    // `i` itself, and that makes the permutation a single cycle through every
    // line. A plain shuffle leaves several cycles, and the chase would loop in
    // whichever it started on: a smaller block than the one asked for.
    for i in (1..lines).rev() {
        let j = rng.below(i as u64) as usize;
        // SAFETY: `j < i < lines`, both lines of the block, and distinct.
        unsafe { std::ptr::swap(word(base, i), word(base, j)) };
        if i % SWAPS_PER_CHECK == 0 {
            control.check()?;
        }
    }
    // From line numbers to addresses.
    for i in 0..lines {
        // SAFETY: `i < lines`, and every number stored is a line below `lines`.
        unsafe {
            let next = word(base, i).read();
            word(base, i).write(word(base, next) as usize);
        }
    }
    Ok(base as *const usize)
}

/// Follow `hops` links from `start`, a multiple of UNROLL, and return where
/// it stopped, so the loads can't be dropped as unused.
///
/// # Safety
/// Every word reachable from `start` must hold the address of another such
/// word.
#[inline(never)]
unsafe fn chase(start: *const usize, hops: u64) -> *const usize {
    let mut p = start;
    for _ in 0..hops / UNROLL {
        // SAFETY: the caller guarantees each word read holds the address of
        // the next valid word.
        unsafe {
            p = p.read() as *const usize;
            p = p.read() as *const usize;
            p = p.read() as *const usize;
            p = p.read() as *const usize;
            p = p.read() as *const usize;
            p = p.read() as *const usize;
            p = p.read() as *const usize;
            p = p.read() as *const usize;
            p = p.read() as *const usize;
            p = p.read() as *const usize;
            p = p.read() as *const usize;
            p = p.read() as *const usize;
            p = p.read() as *const usize;
            p = p.read() as *const usize;
            p = p.read() as *const usize;
            p = p.read() as *const usize;
        }
    }
    p
}

/// One walk round the cycle, carried on from stretch to stretch.
///
/// Every stretch starts where the last one stopped. Starting each one over
/// from the same line would walk the same few lines again and again: past
/// the caches a sample is a small part of the cycle, and from the second
/// repetition on it would come from the L3 instead of memory.
struct Walk {
    position: *const usize,
    hops: u64,
}

impl Walk {
    /// # Safety
    /// As `chase`, for the position the walk started at.
    unsafe fn advance(&mut self, hops: u64) {
        // SAFETY: passed on from the caller.
        self.position = unsafe { chase(self.position, hops) };
        self.hops += hops;
    }

    /// Nanoseconds to chase the next `hops` links.
    ///
    /// # Safety
    /// As `advance`.
    unsafe fn timed(&mut self, hops: u64) -> f64 {
        let begin = now_ns();
        // SAFETY: passed on from the caller.
        self.position = unsafe { chase(black_box(self.position), hops) };
        let end = now_ns();
        black_box(self.position);
        self.hops += hops;
        end.saturating_sub(begin) as f64
    }
}

struct Measured {
    ns: Summary,
    hops: u64,
    /// The whole walk, warm-up and calibration included, and where it ended:
    /// what the test that the walk carries on looks at.
    #[cfg_attr(not(test), allow(dead_code))]
    walked: u64,
    #[cfg_attr(not(test), allow(dead_code))]
    end: *const usize,
}

/// Warm up, find how many hops make a sample long enough, and take the
/// repetitions.
///
/// # Safety
/// As `chase`, for `start`.
unsafe fn measure(
    start: *const usize,
    lines: u64,
    clock: &Clock,
    settings: &Settings,
    control: &Control,
) -> Result<Measured> {
    let mut walk = Walk {
        position: start,
        hops: 0,
    };
    let mut left = lines.min(WARMUP_MAX_HOPS);
    while left > 0 {
        let chunk = left.min(HOPS_PER_CHECK).next_multiple_of(UNROLL);
        // SAFETY: passed on from the caller.
        unsafe { walk.advance(chunk) };
        left = left.saturating_sub(chunk);
        control.check()?;
    }

    let target = clock.min_sample_ns();
    let mut hops = 1024;
    loop {
        // SAFETY: passed on from the caller.
        if unsafe { walk.timed(hops) } >= target {
            break;
        }
        hops = hops
            .checked_mul(2)
            .ok_or(Error::Clock("a sample never lasts long enough"))?;
        control.check()?;
    }

    let mut samples = Vec::with_capacity(settings.repetitions);
    for _ in 0..settings.repetitions {
        control.check()?;
        // SAFETY: passed on from the caller.
        samples.push(unsafe { walk.timed(hops) } / hops as f64);
    }
    let ns = stats::summarize(&samples).ok_or(Error::Clock("a sample came out empty"))?;
    Ok(Measured {
        ns,
        hops,
        walked: walk.hops,
        end: walk.position,
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    fn walk(start: *const usize, lines: usize, block: &Block) -> Vec<usize> {
        let base = block.as_mut_ptr() as usize;
        let mut seen = Vec::with_capacity(lines);
        let mut p = start;
        for _ in 0..lines {
            let offset = p as usize - base;
            seen.push(offset / LINE);
            assert_eq!(offset % LINE, 0, "every link lands on a line's start");
            // SAFETY: `link_cycle` built the chain inside `block`.
            p = unsafe { p.read() } as *const usize;
        }
        assert_eq!(p, start, "after one lap the chase is back at the start");
        seen
    }

    #[test]
    fn one_cycle_through_every_line() {
        let block = Block::reserve(1 << 20, Pages::Small).unwrap();
        let control = Control::default();
        for lines in [2, 3, 17, 64, 1000, 16384] {
            for seed in [0, 1, 0xDEAD_BEEF] {
                let start =
                    link_cycle(&block, lines * LINE, &mut Rng::new(seed), &control).unwrap();
                let mut seen = walk(start, lines, &block);
                seen.sort_unstable();
                assert_eq!(
                    seen,
                    (0..lines).collect::<Vec<_>>(),
                    "{lines} lines, seed {seed}"
                );
            }
        }
    }

    #[test]
    fn the_cycle_is_not_a_stride() {
        let block = Block::reserve(1 << 20, Pages::Small).unwrap();
        let start = link_cycle(&block, 4096 * LINE, &mut Rng::new(5), &Control::default()).unwrap();
        let seen = walk(start, 4096, &block);
        let neighbours = seen.windows(2).filter(|w| w[1] == w[0] + 1).count();
        assert!(neighbours < 16, "{neighbours} steps to the next line");
    }

    #[test]
    fn a_size_the_block_cant_hold_is_an_error() {
        let block = Block::reserve(1 << 20, Pages::Small).unwrap();
        let control = Control::default();
        let mut rng = Rng::new(1);
        assert_eq!(
            link_cycle(&block, LINE, &mut rng, &control),
            Err(Error::BadSize(LINE))
        );
        let too_big = block.len() + LINE;
        assert_eq!(
            link_cycle(&block, too_big, &mut rng, &control),
            Err(Error::BadSize(too_big))
        );
    }

    #[test]
    fn each_stretch_carries_on_where_the_last_stopped() {
        let block = Block::reserve(1 << 20, Pages::Small).unwrap();
        let clock = Clock::check().unwrap();
        let control = Control::default();
        for (lines, seed) in [(1009, 1), (4093, 2)] {
            let start = link_cycle(&block, lines * LINE, &mut Rng::new(seed), &control).unwrap();
            // SAFETY: `link_cycle` built the chain inside `block`.
            let measured =
                unsafe { measure(start, lines as u64, &clock, &settings(), &control) }.unwrap();
            assert!(measured.walked >= lines as u64 + 3 * measured.hops);
            let mut p = start;
            for _ in 0..measured.walked % lines as u64 {
                // SAFETY: as above.
                p = unsafe { p.read() } as *const usize;
            }
            assert_eq!(p, measured.end, "{lines} lines");
        }
    }

    fn settings() -> Settings {
        Settings {
            pages: Pages::Huge,
            repetitions: 3,
            seed: 1,
        }
    }

    #[test]
    fn a_short_curve_gives_a_number_per_size() {
        let clock = Clock::check().unwrap();
        let curve = curve(
            &[64 * 1024, 4096, 4096],
            &settings(),
            &clock,
            &Control::default(),
        )
        .unwrap();
        let sizes: Vec<usize> = curve.points.iter().map(|p| p.bytes).collect();
        assert_eq!(sizes, [4096, 64 * 1024]);
        for point in &curve.points {
            assert!(
                point.ns.median > 0.0 && point.ns.median < 10_000.0,
                "{point:?}"
            );
            assert_eq!(point.ns.count, 3);
            assert_eq!(point.hops % UNROLL, 0);
        }
        assert!(curve.residency.unwrap().rss_bytes >= 64 * 1024);
    }

    #[test]
    fn bad_sizes_and_settings_are_errors() {
        let clock = Clock::check().unwrap();
        let control = Control::default();
        assert_eq!(
            curve(&[], &settings(), &clock, &control),
            Err(Error::NoSizes)
        );
        assert_eq!(
            curve(&[4100], &settings(), &clock, &control),
            Err(Error::BadSize(4100))
        );
        assert_eq!(
            curve(&[64], &settings(), &clock, &control),
            Err(Error::BadSize(64))
        );
        let none = Settings {
            repetitions: 0,
            ..settings()
        };
        assert_eq!(
            curve(&[4096], &none, &clock, &control),
            Err(Error::BadSetting("repetitions"))
        );
    }

    #[test]
    fn a_cancel_stops_it() {
        let clock = Clock::check().unwrap();
        let control = Control::default();
        control.cancel();
        assert_eq!(
            curve(&[4096], &settings(), &clock, &control),
            Err(Error::Cancelled)
        );
    }

    #[test]
    fn a_cancel_from_another_thread_stops_it_halfway() {
        let clock = Clock::check().unwrap();
        let control = Control::default();
        let sizes: Vec<usize> = (12..=24).map(|p| 1 << p).collect();
        let started = std::time::Instant::now();
        let result = std::thread::scope(|scope| {
            scope.spawn(|| {
                std::thread::sleep(std::time::Duration::from_millis(100));
                control.cancel();
            });
            curve(&sizes, &settings(), &clock, &control)
        });
        assert_eq!(result, Err(Error::Cancelled));
        assert!(control.progress().0 < sizes.len() as u64);
        assert!(started.elapsed() < std::time::Duration::from_secs(2));
    }
}
