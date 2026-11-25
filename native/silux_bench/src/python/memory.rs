//! The memory benchmark, as Python calls it.

use pyo3::prelude::*;
use pyo3::types::{PyDict, PyList};

use super::{control_of, guarded, to_python, Control};
use crate::common::error::Error;
use crate::common::frequency::Source;
use crate::common::timer::Clock;
use crate::common::{stats, topology};
use crate::memory::bandwidth;
use crate::memory::block::Pages;
use crate::memory::kernels::{Isa, Operation};
use crate::memory::latency::{self, Settings};

/// Latency at each block size in `sizes` (bytes), on one thread pinned to
/// `cpu`. Returns a dict with `points` (one per size, smallest first, each
/// with the frequency it ran at), the pages asked for and those the kernel
/// gave, the CPU, how the frequency was measured and the clock.
#[pyfunction]
#[pyo3(signature = (sizes, *, huge_pages = true, cpu = None, repetitions = 7, seed = 0x5111_0c5e, control = None))]
pub(super) fn latency_curve<'py>(
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
        entry.set_item("mhz", point.hz.map(|hz| hz.median / 1e6))?;
        entry.set_item("mhz_min", point.hz.map(|hz| hz.min / 1e6))?;
        entry.set_item("hops", point.hops)?;
        entry.set_item("retries", point.retries)?;
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
    result.set_item("frequency_source", curve.frequency.map(Source::key))?;
    result.set_item("clock_resolution_ns", clock.resolution_ns)?;
    result.set_item("clock_read_ns", clock.read_cost_ns)?;
    Ok(result)
}

/// How fast memory moves: `operation` ("read", "write" or "copy") over
/// `bytes` per array and per thread, one thread pinned to each CPU in `cpus`,
/// with the instruction set `isa` (the widest this processor runs, by
/// default). A noisy result is measured again, up to twice.
#[pyfunction]
#[pyo3(signature = (operation, *, bytes, cpus, isa = None, non_temporal = false, huge_pages = true, repetitions = 7, control = None))]
#[allow(clippy::too_many_arguments)]
pub(super) fn memory_bandwidth<'py>(
    py: Python<'py>,
    operation: &str,
    bytes: usize,
    cpus: Vec<usize>,
    isa: Option<&str>,
    non_temporal: bool,
    huge_pages: bool,
    repetitions: usize,
    control: Option<&Bound<'py, Control>>,
) -> PyResult<Bound<'py, PyDict>> {
    let operation = match operation {
        "read" => Operation::Read,
        "write" => Operation::Write,
        "copy" => Operation::Copy,
        _ => return Err(to_python(&Error::BadSetting("operation"))),
    };
    let isa = match isa {
        None => Isa::widest(),
        Some(key) => Isa::from_key(key).ok_or_else(|| to_python(&Error::BadSetting("isa")))?,
    };
    let control = control_of(control);
    let settings = bandwidth::Settings {
        operation,
        non_temporal,
        isa,
        bytes,
        pages: if huge_pages {
            Pages::Huge
        } else {
            Pages::Small
        },
        repetitions,
    };
    let (result, retries) = guarded(py, move || {
        let clock = Clock::check()?;
        stats::steadiest(
            || bandwidth::bandwidth(&cpus, &settings, &clock, &control),
            |b| b.gbps.spread,
        )
    })?;
    let out = PyDict::new(py);
    out.set_item("isa", isa.key())?;
    out.set_item("threads", result.threads)?;
    out.set_item("passes", result.passes)?;
    out.set_item("median_gbps", result.gbps.median)?;
    out.set_item("min_gbps", result.gbps.min)?;
    out.set_item("max_gbps", result.gbps.max)?;
    out.set_item("spread", result.gbps.spread)?;
    out.set_item("noisy", result.gbps.is_noisy())?;
    out.set_item("repetitions", result.gbps.count)?;
    out.set_item("mhz", result.hz.map(|hz| hz.median / 1e6))?;
    out.set_item("mhz_min", result.hz.map(|hz| hz.min / 1e6))?;
    out.set_item("frequency_source", result.frequency.map(Source::key))?;
    out.set_item("retries", retries)?;
    Ok(out)
}

/// The instruction sets this processor runs, widest last.
#[pyfunction]
pub(super) fn instruction_sets() -> Vec<&'static str> {
    Isa::available().into_iter().map(Isa::key).collect()
}
