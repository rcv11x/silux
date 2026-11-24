//! Where the measurement runs: one thread, pinned to the CPU asked for.

use std::mem::size_of;

use crate::common::error::{errno, panic_message, Error, Result};

/// Run `work` on a new thread pinned to `cpu` (or wherever the scheduler
/// puts it, for `None`). A thread of its own, so the caller's affinity is
/// never touched; and a panic in it comes back as an error.
pub fn on_cpu<T, F>(cpu: Option<usize>, work: F) -> Result<T>
where
    T: Send,
    F: FnOnce() -> Result<T> + Send,
{
    std::thread::scope(|scope| {
        let worker = std::thread::Builder::new()
            .name("silux-bench".to_owned())
            .spawn_scoped(scope, move || {
                if let Some(cpu) = cpu {
                    pin_current_thread(cpu)?;
                }
                work()
            })
            .map_err(|e| Error::NoThread {
                errno: e.raw_os_error().unwrap_or(0),
            })?;
        match worker.join() {
            Ok(result) => result,
            Err(payload) => Err(Error::Internal(panic_message(&*payload))),
        }
    })
}

/// Keep the calling thread on `cpu` alone.
pub fn pin_current_thread(cpu: usize) -> Result<()> {
    if cpu >= libc::CPU_SETSIZE as usize {
        return Err(Error::BadCpu {
            cpu,
            errno: libc::EINVAL,
        });
    }
    // SAFETY: cpu_set_t is plain bits, and all zeros is the empty set.
    let mut set: libc::cpu_set_t = unsafe { std::mem::zeroed() };
    // SAFETY: `cpu < CPU_SETSIZE`, checked above, so the bit is inside the set.
    unsafe { libc::CPU_SET(cpu, &mut set) };
    // SAFETY: pid 0 is the calling thread, and `set` is valid for its size.
    let failed = unsafe { libc::sched_setaffinity(0, size_of::<libc::cpu_set_t>(), &set) } != 0;
    if failed {
        return Err(Error::BadCpu {
            cpu,
            errno: errno(),
        });
    }
    Ok(())
}

/// The CPU the calling thread is on right now.
pub fn current_cpu() -> Option<usize> {
    // SAFETY: no arguments; it only reads the calling thread's state.
    let cpu = unsafe { libc::sched_getcpu() };
    usize::try_from(cpu).ok()
}

/// The CPUs the calling thread may run on.
pub fn allowed_cpus() -> Vec<usize> {
    // SAFETY: cpu_set_t is plain bits, and all zeros is the empty set.
    let mut set: libc::cpu_set_t = unsafe { std::mem::zeroed() };
    // SAFETY: pid 0 is the calling thread, and `set` is valid and writable.
    let failed = unsafe { libc::sched_getaffinity(0, size_of::<libc::cpu_set_t>(), &mut set) } != 0;
    if failed {
        return Vec::new();
    }
    (0..libc::CPU_SETSIZE as usize)
        // SAFETY: every `cpu` is below CPU_SETSIZE, inside the set.
        .filter(|cpu| unsafe { libc::CPU_ISSET(*cpu, &set) })
        .collect()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn runs_where_it_is_pinned() {
        for cpu in allowed_cpus().into_iter().take(4) {
            let seen = on_cpu(Some(cpu), || Ok(current_cpu())).unwrap();
            assert_eq!(seen, Some(cpu));
        }
    }

    #[test]
    fn the_callers_affinity_is_left_alone() {
        let before = allowed_cpus();
        let first = *before.first().unwrap();
        on_cpu(Some(first), || Ok(())).unwrap();
        assert_eq!(allowed_cpus(), before);
    }

    #[test]
    fn a_cpu_that_isnt_there_is_an_error() {
        let past = libc::CPU_SETSIZE as usize;
        assert!(matches!(
            on_cpu(Some(past), || Ok(())),
            Err(Error::BadCpu { .. })
        ));
        let last = past - 1;
        if !allowed_cpus().contains(&last) {
            assert!(matches!(
                on_cpu(Some(last), || Ok(())),
                Err(Error::BadCpu { .. })
            ));
        }
    }

    #[test]
    #[allow(clippy::panic)]
    fn a_panic_comes_back_as_an_error() {
        let result: Result<()> = on_cpu(None, || panic!("boom"));
        assert_eq!(result, Err(Error::Internal("boom".to_owned())));
    }
}
