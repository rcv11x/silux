//! The border with Python: the only part that knows about it.
//!
//! Every call measures without the GIL, so the interface keeps running, and
//! nothing that goes wrong crosses as a panic: errors arrive as
//! `SiluxBenchError` with a key, and a panic of ours is caught and arrives
//! the same way, as an internal error. PyO3's `PanicException` would be a
//! panic reaching Python under another name.

use std::panic::{catch_unwind, AssertUnwindSafe};
use std::sync::Arc;

use pyo3::exceptions::PyException;
use pyo3::prelude::*;

use crate::common::error::{panic_message, Error, Result};
use crate::common::{cancel, topology};

mod memory;

pyo3::create_exception!(silux_bench, SiluxBenchError, PyException);
pyo3::create_exception!(silux_bench, Cancelled, SiluxBenchError);

/// Stop a measurement from another thread, and see how far it went.
#[pyclass(frozen, module = "silux_bench")]
pub struct Control {
    inner: Arc<cancel::Control>,
}

#[pymethods]
impl Control {
    #[new]
    fn new() -> Self {
        Control {
            inner: Arc::new(cancel::Control::default()),
        }
    }

    fn cancel(&self) {
        self.inner.cancel();
    }

    #[getter]
    fn cancelled(&self) -> bool {
        self.inner.is_cancelled()
    }

    /// `(done, total)` steps of the measurement under way.
    fn progress(&self) -> (u64, u64) {
        self.inner.progress()
    }
}

fn to_python(error: &Error) -> PyErr {
    let args = (error.key(), error.to_string());
    match error {
        Error::Cancelled => Cancelled::new_err(args),
        _ => SiluxBenchError::new_err(args),
    }
}

/// Run `work` without the GIL, with every panic caught on this side.
fn guarded<T, F>(py: Python<'_>, work: F) -> PyResult<T>
where
    T: Send,
    F: FnOnce() -> Result<T> + Send,
{
    let outcome = py.detach(move || catch_unwind(AssertUnwindSafe(work)));
    match outcome {
        Ok(Ok(value)) => Ok(value),
        Ok(Err(error)) => Err(to_python(&error)),
        Err(payload) => Err(to_python(&Error::Internal(panic_message(&*payload)))),
    }
}

fn control_of(control: Option<&Bound<'_, Control>>) -> Arc<cancel::Control> {
    control.map_or_else(
        || Arc::new(cancel::Control::default()),
        |c| Arc::clone(&c.get().inner),
    )
}

/// The CPUs this process may run on, for choosing where to measure.
#[pyfunction]
fn allowed_cpus() -> Vec<usize> {
    topology::allowed_cpus()
}

#[pymodule]
mod silux_bench {
    #[pymodule_export]
    use super::memory::{instruction_sets, latency_curve, memory_bandwidth};
    #[pymodule_export]
    use super::{allowed_cpus, Cancelled, Control, SiluxBenchError};
}
