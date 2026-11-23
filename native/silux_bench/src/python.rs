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
use pyo3::types::{PyDict, PyList};

use crate::error::{panic_message, Error, Result};
use crate::latency::{self, Settings};
use crate::memory::Pages;
use crate::timer::Clock;
use crate::{cancel, topology};

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

/// Latency at each block size in `sizes` (bytes), on one thread pinned to
/// `cpu`. Returns a dict with `points` (one per size, smallest first), the
/// pages asked for and those the kernel gave, the CPU and the clock.
#[pyfunction]
#[pyo3(signature = (sizes, *, huge_pages = true, cpu = None, repetitions = 7, seed = 0x5111_0c5e, control = None))]
fn latency_curve<'py>(
    py: Python<'py>,
    sizes: Vec<usize>,
    huge_pages: bool,
    cpu: Option<usize>,
    repetitions: usize,
    seed: u64,
    control: Option<&Bound<'py, Control>>,
) -> PyResult<Bound<'py, PyDict>> {
    let control = control_of(control);
    let settings = Settings {
        pages: if huge_pages {
            Pages::Huge
        } else {
            Pages::Small
        },
        repetitions,
        seed,
    };
    let (curve, clock) = guarded(py, move || {
        let clock = Clock::check()?;
        let curve = topology::on_cpu(cpu, || latency::curve(&sizes, &settings, &clock, &control))?;
        Ok((curve, clock))
    })?;

    let points = PyList::empty(py);
    for point in &curve.points {
        let entry = PyDict::new(py);
        entry.set_item("bytes", point.bytes)?;
        entry.set_item("median_ns", point.ns.median)?;
        entry.set_item("min_ns", point.ns.min)?;
        entry.set_item("max_ns", point.ns.max)?;
        entry.set_item("spread", point.ns.spread)?;
        entry.set_item("noisy", point.ns.is_noisy())?;
        entry.set_item("repetitions", point.ns.count)?;
        entry.set_item("hops", point.hops)?;
        points.append(entry)?;
    }
    let result = PyDict::new(py);
    result.set_item("points", points)?;
    result.set_item(
        "pages",
        match curve.pages {
            Pages::Huge => "huge",
            Pages::Small => "small",
        },
    )?;
    result.set_item("rss_bytes", curve.residency.map(|r| r.rss_bytes))?;
    result.set_item("huge_bytes", curve.residency.map(|r| r.huge_bytes))?;
    result.set_item("cpu", curve.cpu)?;
    result.set_item("clock_resolution_ns", clock.resolution_ns)?;
    result.set_item("clock_read_ns", clock.read_cost_ns)?;
    Ok(result)
}

/// The CPUs this process may run on, for choosing where to measure.
#[pyfunction]
fn allowed_cpus() -> Vec<usize> {
    topology::allowed_cpus()
}

#[pymodule]
mod silux_bench {
    #[pymodule_export]
    use super::{allowed_cpus, latency_curve, Cancelled, Control, SiluxBenchError};
}
