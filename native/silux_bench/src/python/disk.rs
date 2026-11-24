//! The disk benchmark, as Python calls it: the file as an object, and one
//! lap of a test at a time. The order of the tests, their laps and the
//! pauses between them are Python's.

use std::os::fd::AsRawFd;
use std::path::PathBuf;
use std::sync::{Arc, Mutex, PoisonError};

use pyo3::prelude::*;
use pyo3::types::{PyDict, PyList};

use super::{control_of, guarded, to_python, Control, SiluxBenchError};
use crate::common::error::Error;
use crate::disk::job::{Direction, Job, Pattern};
use crate::disk::target::{Creation, Target};
use crate::disk::{threads, uring};

/// The file a disk test reads and writes: made in `folder` without a name,
/// so that it is gone when this object is, whatever happens to the process.
/// Its contents are still to be written (`fill`).
#[pyclass(frozen, module = "silux_bench")]
pub struct DiskFile {
    /// `None` once closed. A lap under way keeps the file until it ends.
    target: Mutex<Option<Arc<Target>>>,
}

impl DiskFile {
    fn target(&self) -> PyResult<Arc<Target>> {
        self.target
            .lock()
            .unwrap_or_else(PoisonError::into_inner)
            .clone()
            .ok_or_else(|| SiluxBenchError::new_err(("closed", "the file was closed")))
    }
}

#[pymethods]
impl DiskFile {
    #[new]
    #[pyo3(signature = (folder, *, bytes))]
    fn new(py: Python<'_>, folder: PathBuf, bytes: u64) -> PyResult<Self> {
        let target = guarded(py, move || Target::create(&folder, bytes))?;
        Ok(DiskFile {
            target: Mutex::new(Some(Arc::new(target))),
        })
    }

    /// Write the whole file with random data. `control` counts its MiB and
    /// can stop it.
    #[pyo3(signature = (*, seed = 0x5111_d15c, control = None))]
    fn fill(
        &self,
        py: Python<'_>,
        seed: u64,
        control: Option<&Bound<'_, Control>>,
    ) -> PyResult<()> {
        let (target, control) = (self.target()?, control_of(control));
        guarded(py, move || target.fill(seed, &control))
    }

    /// One lap: `pattern` ("sequential" or "random") and `direction` ("read"
    /// or "write") in requests of `block` bytes, `depth` of them in flight,
    /// for `seconds`. `engine` is "uring", a real queue kept by one thread,
    /// or "threads", a thread for each request in flight: what is left
    /// where `uring_error` says there is no ring. Returns what moved, how
    /// long it took and how long each request did.
    #[pyo3(signature = (pattern, direction, *, block, depth, seconds, engine = "uring", seed = 1, control = None))]
    #[allow(clippy::too_many_arguments)]
    fn lap<'py>(
        &self,
        py: Python<'py>,
        pattern: &str,
        direction: &str,
        block: usize,
        depth: usize,
        seconds: f64,
        engine: &str,
        seed: u64,
        control: Option<&Bound<'py, Control>>,
    ) -> PyResult<Bound<'py, PyDict>> {
        let (engine, run): (_, fn(&Target, &Job, &_) -> _) = match engine {
            "uring" => ("uring", uring::run),
            "threads" => ("threads", threads::run),
            _ => return Err(to_python(&Error::BadSetting("engine"))),
        };
        let job = Job {
            pattern: match pattern {
                "sequential" => Pattern::Sequential,
                "random" => Pattern::Random,
                _ => return Err(to_python(&Error::BadSetting("pattern"))),
            },
            direction: match direction {
                "read" => Direction::Read,
                "write" => Direction::Write,
                _ => return Err(to_python(&Error::BadSetting("direction"))),
            },
            block,
            depth,
            seconds,
            seed,
        };
        let (target, control) = (self.target()?, control_of(control));
        let lap = guarded(py, move || run(&target, &job, &control))?;

        let samples = PyList::empty(py);
        for sample in &lap.samples {
            samples.append((sample.at_ns, sample.bytes))?;
        }
        let out = PyDict::new(py);
        out.set_item("engine", engine)?;
        out.set_item("threads", lap.threads)?;
        out.set_item("bytes", lap.bytes)?;
        out.set_item("requests", lap.requests)?;
        out.set_item("elapsed_ns", lap.elapsed_ns)?;
        out.set_item("bytes_per_second", lap.bytes_per_second())?;
        out.set_item("requests_per_second", lap.requests_per_second())?;
        out.set_item("latency_mean_ns", lap.latency.mean())?;
        out.set_item("latency_min_ns", lap.latency.min())?;
        out.set_item("latency_max_ns", lap.latency.max())?;
        out.set_item("latency_p50_ns", lap.latency.percentile(50.0))?;
        out.set_item("latency_p99_ns", lap.latency.percentile(99.0))?;
        out.set_item("latency_p999_ns", lap.latency.percentile(99.9))?;
        out.set_item("samples", samples)?;
        Ok(out)
    }

    /// Bytes of the file the kernel holds in its page cache: none, when
    /// every request went past it.
    fn cached_bytes(&self, py: Python<'_>) -> PyResult<u64> {
        let target = self.target()?;
        guarded(py, move || target.cached_bytes())
    }

    /// The file's descriptor, to ask the system about it (`os.fstat`) and
    /// for another program to open the same file while this one holds it,
    /// as `/proc/PID/fd/N`. Not to read or write through.
    fn fileno(&self) -> PyResult<i32> {
        Ok(self.target()?.as_raw_fd())
    }

    /// Free the file now instead of when the object goes. A lap under way
    /// ends first.
    fn close(&self) {
        self.target
            .lock()
            .unwrap_or_else(PoisonError::into_inner)
            .take();
    }

    #[getter]
    fn bytes(&self) -> PyResult<u64> {
        Ok(self.target()?.bytes())
    }

    /// "unnamed" where the file never had a name; "unlinked" where it had
    /// one for an instant, before anything was written.
    #[getter]
    fn creation(&self) -> PyResult<&'static str> {
        Ok(match self.target()?.creation() {
            Creation::Unnamed => "unnamed",
            Creation::Unlinked => "unlinked",
        })
    }

    /// On btrfs, whether the file was kept out of copy-on-write; `None` on
    /// any other file system.
    #[getter]
    fn no_cow(&self) -> PyResult<Option<bool>> {
        Ok(self.target()?.no_cow())
    }

    /// The file system's magic number, as `statfs` gives it.
    #[getter]
    fn filesystem(&self) -> PyResult<u32> {
        Ok(self.target()?.filesystem())
    }

    /// What a request has to be a multiple of: its address in memory, its
    /// offset and length in the file, and whether the file said so itself.
    #[getter]
    fn align(&self) -> PyResult<(usize, usize, bool)> {
        let align = self.target()?.align();
        Ok((align.memory, align.offset, align.declared))
    }
}

/// Why there is no io_uring here, as the errno the kernel answered to making
/// a ring; `None` where there is one.
#[pyfunction]
pub(super) fn uring_error() -> Option<i32> {
    match uring::probe() {
        Err(Error::NoUring { errno }) => Some(errno),
        _ => None,
    }
}
