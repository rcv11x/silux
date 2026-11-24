//! What a lap of a test leaves: what moved, in how long, and how long each
//! request took.

use crate::disk::histogram::Histogram;

/// How often a lap notes how much has moved so far.
pub const SAMPLE_NS: u64 = 250_000_000;

/// How much had moved in all, this long into the lap.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct Sample {
    pub at_ns: u64,
    pub bytes: u64,
}

#[derive(Debug, Clone, PartialEq)]
pub struct Lap {
    pub bytes: u64,
    pub requests: u64,
    /// From the start to the end of the last request: those in flight when
    /// the time is up are waited for and counted, as fio does.
    pub elapsed_ns: u64,
    /// Each request's whole time, from asking to having it.
    pub latency: Histogram,
    /// One every `SAMPLE_NS`, to see a speed that falls during the lap.
    pub samples: Vec<Sample>,
    /// The threads the queue was made of.
    pub threads: usize,
}

impl Lap {
    pub fn bytes_per_second(&self) -> f64 {
        self.per_second(self.bytes)
    }

    pub fn requests_per_second(&self) -> f64 {
        self.per_second(self.requests)
    }

    fn per_second(&self, amount: u64) -> f64 {
        if self.elapsed_ns == 0 {
            return 0.0;
        }
        amount as f64 * 1e9 / self.elapsed_ns as f64
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn rates_come_from_what_moved_and_how_long_it_took() {
        let mut lap = Lap {
            bytes: 5 << 30,
            requests: 5120,
            elapsed_ns: 2_000_000_000,
            latency: Histogram::default(),
            samples: Vec::new(),
            threads: 1,
        };
        assert_eq!(lap.bytes_per_second(), (5u64 << 29) as f64);
        assert_eq!(lap.requests_per_second(), 2560.0);
        lap.elapsed_ns = 0;
        assert_eq!(lap.bytes_per_second(), 0.0);
    }
}
