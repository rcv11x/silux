//! Starting several threads together, or none of them.

use std::sync::{Condvar, Mutex, PoisonError};

/// Holds every thread before its first barrier until all of them exist. The
/// barrier waits for one thread per CPU, so a thread that couldn't be started
/// would keep the rest there forever, and the join of any of them too.
#[derive(Default)]
pub struct Gate {
    verdict: Mutex<Option<bool>>,
    opened: Condvar,
}

impl Gate {
    /// Let the threads through, to measure or to leave. The first verdict
    /// stands.
    pub fn open(&self, measure: bool) {
        let mut verdict = self.verdict.lock().unwrap_or_else(PoisonError::into_inner);
        verdict.get_or_insert(measure);
        self.opened.notify_all();
    }

    /// Wait for the verdict: whether to measure.
    pub fn pass(&self) -> bool {
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
pub struct Opener<'a>(pub &'a Gate);

impl Drop for Opener<'_> {
    fn drop(&mut self) {
        self.0.open(false);
    }
}
