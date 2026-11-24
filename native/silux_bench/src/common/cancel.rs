//! Stopping a measurement from outside, and asking how far it went.
//!
//! Shared between the measuring thread and whoever started it. The work looks
//! at the flag between chunks of at most about 50 ms, so a cancel is felt
//! that fast without a check in the timed loops themselves.

use std::sync::atomic::{AtomicBool, AtomicU64, Ordering};

use crate::common::error::{Error, Result};

#[derive(Debug, Default)]
pub struct Control {
    cancelled: AtomicBool,
    done: AtomicU64,
    total: AtomicU64,
}

impl Control {
    pub fn cancel(&self) {
        self.cancelled.store(true, Ordering::Relaxed);
    }

    pub fn is_cancelled(&self) -> bool {
        self.cancelled.load(Ordering::Relaxed)
    }

    /// `Err(Cancelled)` once someone has asked to stop.
    pub fn check(&self) -> Result<()> {
        if self.is_cancelled() {
            Err(Error::Cancelled)
        } else {
            Ok(())
        }
    }

    /// Start counting a new piece of work of `total` steps.
    pub fn begin(&self, total: u64) {
        self.done.store(0, Ordering::Relaxed);
        self.total.store(total, Ordering::Relaxed);
    }

    pub fn advance(&self) {
        self.done.fetch_add(1, Ordering::Relaxed);
    }

    /// Steps done and steps in all.
    pub fn progress(&self) -> (u64, u64) {
        (
            self.done.load(Ordering::Relaxed),
            self.total.load(Ordering::Relaxed),
        )
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn a_cancel_is_seen_by_the_check() {
        let control = Control::default();
        assert_eq!(control.check(), Ok(()));
        control.cancel();
        assert_eq!(control.check(), Err(Error::Cancelled));
    }

    #[test]
    fn progress_counts_from_each_beginning() {
        let control = Control::default();
        control.begin(3);
        control.advance();
        assert_eq!(control.progress(), (1, 3));
        control.begin(2);
        assert_eq!(control.progress(), (0, 2));
    }
}
