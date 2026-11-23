//! The clock every measurement is timed with, checked before it's trusted.

use std::hint::black_box;

use crate::error::{Error, Result};

/// A sample shorter than this many clock ticks is mostly rounding...
const TICKS_PER_SAMPLE: f64 = 1000.0;
/// ...and shorter than this many clock reads, mostly reading the clock.
const READS_PER_SAMPLE: f64 = 100.0;
/// A floor well above both: in a few milliseconds a timer interrupt or a
/// frequency step weighs on one sample, and the median absorbs one, not many.
pub const MIN_SAMPLE_NS: f64 = 10_000_000.0;
/// A clock coarser than this can't time anything here.
const MAX_RESOLUTION_NS: f64 = 1_000_000.0;
const READS_TO_COST: u32 = 10_000;

#[derive(Debug, Clone, Copy, PartialEq)]
pub struct Clock {
    pub resolution_ns: f64,
    pub read_cost_ns: f64,
}

/// Nanoseconds on `CLOCK_MONOTONIC_RAW`, which NTP doesn't slew: a sample
/// doesn't stretch or shrink while the system corrects its time. Read through
/// the vDSO, without a system call. Zero if the clock fails, which
/// `Clock::check` rules out before anything is timed.
pub fn now_ns() -> u64 {
    let mut ts = libc::timespec {
        tv_sec: 0,
        tv_nsec: 0,
    };
    // SAFETY: `ts` is a valid, writable timespec for the whole call.
    let failed = unsafe { libc::clock_gettime(libc::CLOCK_MONOTONIC_RAW, &mut ts) } != 0;
    if failed {
        return 0;
    }
    (ts.tv_sec as u64)
        .saturating_mul(1_000_000_000)
        .saturating_add(ts.tv_nsec as u64)
}

impl Clock {
    /// The clock's resolution and the cost of reading it, and proof that it
    /// moves forward.
    pub fn check() -> Result<Clock> {
        let mut res = libc::timespec {
            tv_sec: 0,
            tv_nsec: 0,
        };
        // SAFETY: `res` is a valid, writable timespec for the whole call.
        if unsafe { libc::clock_getres(libc::CLOCK_MONOTONIC_RAW, &mut res) } != 0 {
            return Err(Error::Clock("clock_getres failed"));
        }
        let resolution_ns = res.tv_sec as f64 * 1e9 + res.tv_nsec as f64;
        if !(resolution_ns > 0.0 && resolution_ns <= MAX_RESOLUTION_NS) {
            return Err(Error::Clock("too coarse"));
        }
        let first = now_ns();
        let mut last = first;
        for _ in 0..READS_TO_COST {
            last = black_box(now_ns());
        }
        if first == 0 || last <= first {
            return Err(Error::Clock("it doesn't move forward"));
        }
        Ok(Clock {
            resolution_ns,
            read_cost_ns: (last - first) as f64 / f64::from(READS_TO_COST),
        })
    }

    /// How long one sample has to last for the clock not to matter.
    pub fn min_sample_ns(&self) -> f64 {
        MIN_SAMPLE_NS
            .max(self.resolution_ns * TICKS_PER_SAMPLE)
            .max(self.read_cost_ns * READS_PER_SAMPLE)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn the_clock_works_here() {
        let clock = Clock::check().unwrap();
        assert!(clock.resolution_ns > 0.0);
        assert!(clock.read_cost_ns > 0.0 && clock.read_cost_ns < 10_000.0);
        assert!(clock.min_sample_ns() >= MIN_SAMPLE_NS);
    }

    #[test]
    fn it_moves_forward() {
        let before = now_ns();
        std::thread::sleep(std::time::Duration::from_millis(2));
        assert!(now_ns() >= before + 1_000_000);
    }
}
