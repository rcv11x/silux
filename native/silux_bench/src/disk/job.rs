//! What one test asks of the disk.

use crate::common::error::{Error, Result};

/// More requests in flight than this is past what any of the tests asks.
pub const MAX_DEPTH: usize = 256;
/// The longest a lap may be asked to last.
pub const MAX_SECONDS: f64 = 600.0;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Pattern {
    /// One block after another, round the file.
    Sequential,
    /// Any block of the file, each as likely as the rest.
    Random,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Direction {
    Read,
    Write,
}

#[derive(Debug, Clone, Copy, PartialEq)]
pub struct Job {
    pub pattern: Pattern,
    pub direction: Direction,
    /// Bytes of each request.
    pub block: usize,
    /// Requests in flight at a time.
    pub depth: usize,
    /// How long the lap lasts: it is timed, not a set amount of data.
    pub seconds: f64,
    pub seed: u64,
}

impl Job {
    /// How many blocks of this job a file of `bytes` holds, where every
    /// request has to begin at a multiple of `offset_align`.
    pub fn blocks(&self, bytes: u64, offset_align: usize) -> Result<u64> {
        if !(1..=MAX_DEPTH).contains(&self.depth) {
            return Err(Error::BadSetting("depth"));
        }
        if !(self.seconds > 0.0 && self.seconds <= MAX_SECONDS) {
            return Err(Error::BadSetting("seconds"));
        }
        let block = self.block as u64;
        if block == 0 || offset_align == 0 || !self.block.is_multiple_of(offset_align) {
            return Err(Error::BadSize(self.block));
        }
        match bytes / block {
            0 => Err(Error::BadSize(self.block)),
            blocks => Ok(blocks),
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    const JOB: Job = Job {
        pattern: Pattern::Random,
        direction: Direction::Read,
        block: 4096,
        depth: 32,
        seconds: 5.0,
        seed: 1,
    };

    #[test]
    fn counts_the_whole_blocks_of_the_file() {
        assert_eq!(JOB.blocks(1 << 30, 4096), Ok(262_144));
        assert_eq!(JOB.blocks(1 << 30, 512), Ok(262_144));
        assert_eq!(JOB.blocks(4096 * 3 + 100, 4096), Ok(3));
    }

    #[test]
    fn what_cant_be_run_is_an_error() {
        for depth in [0, MAX_DEPTH + 1] {
            let job = Job { depth, ..JOB };
            assert_eq!(job.blocks(1 << 30, 4096), Err(Error::BadSetting("depth")));
        }
        for seconds in [0.0, -1.0, f64::NAN, f64::INFINITY, MAX_SECONDS + 1.0] {
            let job = Job { seconds, ..JOB };
            assert_eq!(job.blocks(1 << 30, 4096), Err(Error::BadSetting("seconds")));
        }
        // A block that isn't a whole number of what the file is read by, an
        // empty one and one larger than the file.
        for (block, align, bytes) in [
            (4096, 65536, 1 << 30),
            (0, 4096, 1 << 30),
            (8192, 4096, 4096),
        ] {
            let job = Job { block, ..JOB };
            assert_eq!(job.blocks(bytes, align), Err(Error::BadSize(block)));
        }
        assert_eq!(JOB.blocks(1 << 30, 0), Err(Error::BadSize(4096)));
    }
}
