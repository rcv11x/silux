//! The frequency the core ran at while a sample was timed.
//!
//! A cache answers in core cycles, so the same block reads slower in
//! nanoseconds on a core that hasn't come up to speed: a latency without its
//! frequency is half a figure. Two ways to get it, the first that works:
//!
//! - Counting the thread's own cycles with a perf counter, user mode only,
//!   which the usual `perf_event_paranoid` of 2 allows. Cycles over the
//!   sample's time is the frequency it ran at. Time in the kernel isn't
//!   counted, so an interrupt makes it read a little low, as it makes the
//!   sample read slow.
//! - What the kernel says the CPU is running at (`scaling_cur_freq`), read
//!   by the measuring thread as the sample ends.

use std::fs::File;
use std::os::fd::{AsRawFd, FromRawFd};
use std::path::{Path, PathBuf};

use crate::topology::current_cpu;

/// Below or above these no core runs: a counter that reads so is counting
/// something else.
const PLAUSIBLE_HZ: std::ops::RangeInclusive<f64> = 50e6..=10e9;

const PERF_TYPE_HARDWARE: u32 = 0;
const PERF_COUNT_HW_CPU_CYCLES: u64 = 0;
const EXCLUDE_KERNEL: u64 = 1 << 5;
const EXCLUDE_HV: u64 = 1 << 6;
const PERF_FLAG_FD_CLOEXEC: libc::c_ulong = 1 << 3;
/// Where a hardware event's `config` carries the PMU it is for.
const PMU_TYPE_SHIFT: u32 = 32;
const EVENT_SOURCES: &str = "/sys/bus/event_source/devices";
const CPUFREQ: &str = "/sys/devices/system/cpu";

/// `perf_event_attr` as its first version defined it, which every kernel
/// accepts: the fields after `config1` are for features not used here.
#[repr(C)]
#[derive(Default)]
struct PerfEventAttr {
    kind: u32,
    size: u32,
    config: u64,
    sample_period: u64,
    sample_type: u64,
    read_format: u64,
    flags: u64,
    wakeup_events: u32,
    bp_type: u32,
    config1: u64,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Source {
    /// Cycles the thread ran, over the sample's time.
    Cycles,
    /// The kernel's figure for the CPU, read as the sample ended.
    Cpufreq,
}

impl Source {
    pub fn key(self) -> &'static str {
        match self {
            Source::Cycles => "cycles",
            Source::Cpufreq => "cpufreq",
        }
    }
}

enum Kind {
    Cycles(File),
    Cpufreq(PathBuf),
    Off,
}

/// Measures the frequency of the thread that opened it.
pub struct Meter {
    kind: Kind,
}

/// The cycle count as a sample began.
#[derive(Debug, Clone, Copy)]
pub struct Mark(Option<u64>);

impl Meter {
    /// For the calling thread, which should already be on the CPU it will
    /// measure on: on a processor with two kinds of core, each kind has its
    /// own counter.
    pub fn open() -> Meter {
        let cpu = current_cpu();
        if let Some(counter) = open_cycles(cpu.and_then(pmu_of)) {
            return Meter {
                kind: Kind::Cycles(counter),
            };
        }
        let path =
            cpu.map(|cpu| Path::new(CPUFREQ).join(format!("cpu{cpu}/cpufreq/scaling_cur_freq")));
        match path {
            Some(path) if read_khz(&path).is_some() => Meter {
                kind: Kind::Cpufreq(path),
            },
            _ => Meter::off(),
        }
    }

    /// A meter that measures nothing.
    pub fn off() -> Meter {
        Meter { kind: Kind::Off }
    }

    pub fn source(&self) -> Option<Source> {
        match self.kind {
            Kind::Cycles(_) => Some(Source::Cycles),
            Kind::Cpufreq(_) => Some(Source::Cpufreq),
            Kind::Off => None,
        }
    }

    /// Call right before the sample's first clock read.
    pub fn begin(&self) -> Mark {
        Mark(match &self.kind {
            Kind::Cycles(counter) => read_counter(counter),
            _ => None,
        })
    }

    /// Call right after the sample's last clock read. Hertz, or `None` where
    /// it couldn't be measured or the figure is no frequency.
    pub fn end(&self, mark: Mark, elapsed_ns: f64) -> Option<f64> {
        let hz = match &self.kind {
            Kind::Cycles(counter) => {
                let cycles = read_counter(counter)?.checked_sub(mark.0?)?;
                if elapsed_ns <= 0.0 {
                    return None;
                }
                cycles as f64 / elapsed_ns * 1e9
            }
            Kind::Cpufreq(path) => read_khz(path)? * 1e3,
            Kind::Off => return None,
        };
        PLAUSIBLE_HZ.contains(&hz).then_some(hz)
    }
}

/// A counter of the calling thread's user-mode cycles, already counting.
fn open_cycles(pmu: Option<u32>) -> Option<File> {
    let attr = PerfEventAttr {
        kind: PERF_TYPE_HARDWARE,
        size: std::mem::size_of::<PerfEventAttr>() as u32,
        config: PERF_COUNT_HW_CPU_CYCLES | (u64::from(pmu.unwrap_or(0)) << PMU_TYPE_SHIFT),
        flags: EXCLUDE_KERNEL | EXCLUDE_HV,
        ..PerfEventAttr::default()
    };
    // SAFETY: `attr` is a valid perf_event_attr of the size it declares, alive
    // for the whole call; pid 0 and cpu -1 mean this thread wherever it runs.
    let fd = unsafe {
        libc::syscall(
            libc::SYS_perf_event_open,
            &attr as *const PerfEventAttr,
            0 as libc::pid_t,
            -1 as libc::c_int,
            -1 as libc::c_int,
            PERF_FLAG_FD_CLOEXEC,
        )
    };
    let fd = libc::c_int::try_from(fd).ok().filter(|fd| *fd >= 0)?;
    // SAFETY: the kernel just returned `fd` to us, open and owned by nobody else.
    let counter = unsafe { File::from_raw_fd(fd) };
    // A counter that can't be read, or that a hypervisor leaves at zero, is
    // found out here and not at the first sample.
    read_counter(&counter).map(|_| counter)
}

fn read_counter(counter: &File) -> Option<u64> {
    let mut value = 0u64;
    // SAFETY: `value` is 8 writable bytes, which is what a counter without a
    // read format gives.
    let read = unsafe {
        libc::read(
            counter.as_raw_fd(),
            (&mut value as *mut u64).cast::<libc::c_void>(),
            std::mem::size_of::<u64>(),
        )
    };
    (read == std::mem::size_of::<u64>() as isize).then_some(value)
}

/// The PMU of the cores `cpu` is one of, where the processor has more than
/// one kind: each publishes the CPUs it covers. `None` where there is a
/// single PMU for all, which needs no naming.
fn pmu_of(cpu: usize) -> Option<u32> {
    let devices = std::fs::read_dir(EVENT_SOURCES).ok()?;
    for device in devices.flatten() {
        let path = device.path();
        let Ok(cpus) = std::fs::read_to_string(path.join("cpus")) else {
            continue;
        };
        if parse_cpu_list(&cpus).contains(&cpu) {
            return std::fs::read_to_string(path.join("type"))
                .ok()?
                .trim()
                .parse()
                .ok();
        }
    }
    None
}

/// The CPUs in a kernel list like `0-7,16,18-19`. What doesn't parse is
/// left out.
pub fn parse_cpu_list(list: &str) -> Vec<usize> {
    let mut cpus = Vec::new();
    for part in list.trim().split(',') {
        let mut ends = part.splitn(2, '-').map(|n| n.trim().parse::<usize>());
        match (ends.next(), ends.next()) {
            (Some(Ok(first)), None) => cpus.push(first),
            (Some(Ok(first)), Some(Ok(last))) if first <= last => cpus.extend(first..=last),
            _ => {}
        }
    }
    cpus
}

fn read_khz(path: &Path) -> Option<f64> {
    std::fs::read_to_string(path).ok()?.trim().parse().ok()
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::timer::now_ns;

    #[test]
    fn cpu_lists() {
        assert_eq!(parse_cpu_list("0-3,8,10-11\n"), vec![0, 1, 2, 3, 8, 10, 11]);
        assert_eq!(parse_cpu_list("5"), vec![5]);
        assert_eq!(parse_cpu_list(""), Vec::<usize>::new());
        assert_eq!(parse_cpu_list("3-1,x,7"), vec![7]);
    }

    #[test]
    fn a_meter_that_is_off_measures_nothing() {
        let meter = Meter::off();
        assert_eq!(meter.source(), None);
        assert_eq!(meter.end(meter.begin(), 1e7), None);
    }

    /// Wherever this runs, a busy stretch reads as a frequency a core can
    /// run at, or as nothing: never as a number that is no frequency.
    #[test]
    fn a_busy_stretch_reads_as_a_frequency_or_nothing() {
        let meter = Meter::open();
        let mark = meter.begin();
        let begin = now_ns();
        let mut spin = 0u64;
        while now_ns() - begin < 20_000_000 {
            spin = std::hint::black_box(spin.wrapping_add(1));
        }
        let elapsed = (now_ns() - begin) as f64;
        if let Some(hz) = meter.end(mark, elapsed) {
            assert!(PLAUSIBLE_HZ.contains(&hz), "{hz} Hz");
        }
    }

    #[test]
    fn the_kernels_figure_is_kilohertz() {
        let path = std::env::temp_dir().join(format!("silux-bench-khz-{}", std::process::id()));
        let meter = Meter {
            kind: Kind::Cpufreq(path.clone()),
        };
        std::fs::write(&path, "3500000\n").unwrap();
        assert_eq!(meter.end(meter.begin(), 1e7), Some(3.5e9));
        // The kernel writes a zero for a CPU it has no figure for.
        std::fs::write(&path, "0\n").unwrap();
        assert_eq!(meter.end(meter.begin(), 1e7), None);
        std::fs::remove_file(&path).unwrap();
        assert_eq!(meter.end(meter.begin(), 1e7), None);
    }

    #[test]
    fn no_time_is_no_frequency() {
        let meter = Meter::open();
        if meter.source() == Some(Source::Cycles) {
            assert_eq!(meter.end(meter.begin(), 0.0), None);
        }
    }
}
