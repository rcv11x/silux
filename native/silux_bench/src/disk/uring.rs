//! A lap with a real queue: one thread keeps as many requests in flight as
//! the test asks, through io_uring.
//!
//! The ring is the `io-uring` crate's, which only wraps the kernel's: the
//! memory shared with the kernel and its barriers are the delicate part,
//! and a mistake there doesn't crash, it gives odd figures now and then.
//! What is asked of it is set here and is the plainest there is: single
//! reads and writes with their offset, no kernel thread polling the queue
//! and no registered buffers or files. That is `fio --ioengine=io_uring`
//! without further options, so that the two compare like with like.

use io_uring::{opcode, types, IoUring};
use std::os::fd::AsRawFd;

use crate::common::cancel::Control;
use crate::common::error::{Error, Result};
use crate::common::rng::Rng;
use crate::common::timer::now_ns;
use crate::disk::buffers::{check_read, Buffer};
use crate::disk::histogram::Histogram;
use crate::disk::job::{Direction, Job, Pattern};
use crate::disk::run::{next_sample, Lap, Sample, SAMPLE_NS};
use crate::disk::target::Target;

/// One of the requests the queue holds: its memory, and what it is doing.
struct Slot {
    buffer: Buffer,
    offset: u64,
    began_ns: u64,
}

/// Whether the kernel gives a ring here; the error says why not.
pub fn probe() -> Result<()> {
    ring(1).map(drop)
}

fn ring(depth: usize) -> Result<IoUring> {
    let entries =
        u32::try_from(depth.next_power_of_two()).map_err(|_| Error::BadSetting("depth"))?;
    IoUring::new(entries).map_err(|error| Error::NoUring {
        errno: error.raw_os_error().unwrap_or(0),
    })
}

/// One lap of `job` over `target`, which has to be filled already.
pub fn run(target: &Target, job: &Job, control: &Control) -> Result<Lap> {
    let blocks = job.blocks(target.bytes(), target.align().offset)?;
    let len = u32::try_from(job.block).map_err(|_| Error::BadSize(job.block))?;
    control.check()?;
    let mut ring = ring(job.depth)?;
    let mut rng = Rng::new(job.seed);
    let mut slots = Vec::with_capacity(job.depth);
    for _ in 0..job.depth {
        slots.push(Slot {
            buffer: Buffer::random(job.block, target.align().memory, &mut rng)?,
            offset: 0,
            began_ns: 0,
        });
    }
    let call = match job.direction {
        Direction::Read => "read",
        Direction::Write => "write",
    };

    let mut lap = Lap {
        bytes: 0,
        requests: 0,
        elapsed_ns: 0,
        latency: Histogram::default(),
        samples: Vec::new(),
        threads: 1,
    };
    let lasts_ns = (job.seconds * 1e9) as u64;
    let began_ns = now_ns();
    let deadline_ns = began_ns.saturating_add(lasts_ns);
    let mut next_sample_ns = began_ns + SAMPLE_NS;
    let mut ended_ns = began_ns;
    let mut cursor = 0u64;
    let mut in_flight = 0usize;
    let mut failure: Option<Error> = None;
    let mut cancelled = false;
    let mut done: Vec<(u64, i32)> = Vec::with_capacity(job.depth);

    // Ask for the next block with the request `index`.
    let mut ask = |ring: &mut IoUring, slot: &mut Slot, index: usize, in_flight: &mut usize| {
        let block = match job.pattern {
            Pattern::Sequential => {
                cursor += 1;
                (cursor - 1) % blocks
            }
            Pattern::Random => rng.below(blocks),
        };
        slot.offset = block * job.block as u64;
        slot.began_ns = now_ns();
        let fd = types::Fd(target.as_raw_fd());
        let entry = match job.direction {
            Direction::Read => {
                let memory = slot.buffer.as_mut_slice();
                target.check_aligned(call, memory.as_ptr() as usize, memory.len(), slot.offset)?;
                opcode::Read::new(fd, memory.as_mut_ptr(), len)
                    .offset(slot.offset)
                    .build()
            }
            Direction::Write => {
                // The moment it is written: a block written twice in the
                // same place isn't the same block either.
                slot.buffer.stamp(slot.offset, slot.began_ns);
                let memory = slot.buffer.as_slice();
                target.check_aligned(call, memory.as_ptr() as usize, memory.len(), slot.offset)?;
                opcode::Write::new(fd, memory.as_ptr(), len)
                    .offset(slot.offset)
                    .build()
            }
        }
        .user_data(index as u64);
        // SAFETY: the request's memory is the slot's buffer, which lives in
        // `slots` until this function returns, and it only returns with no
        // request in flight: the one way out before that leaks the buffers.
        unsafe { ring.submission().push(&entry) }
            .map_err(|_| Error::Internal("the ring had no room for a request".to_owned()))?;
        *in_flight += 1;
        Ok::<(), Error>(())
    };

    for (index, slot) in slots.iter_mut().enumerate() {
        if let Err(error) = ask(&mut ring, slot, index, &mut in_flight) {
            failure.get_or_insert(error);
            break;
        }
    }
    while in_flight > 0 {
        if let Err(error) = ring.submit_and_wait(1) {
            let errno = error.raw_os_error().unwrap_or(0);
            if errno == libc::EINTR {
                continue;
            }
            // There is no telling what the kernel still holds: the buffers
            // are never freed, rather than freed under a request.
            std::mem::forget(slots);
            return Err(Error::Io {
                call: "io_uring_enter",
                errno,
            });
        }
        let now = now_ns();
        done.clear();
        done.extend(
            ring.completion()
                .map(|entry| (entry.user_data(), entry.result())),
        );
        cancelled |= control.is_cancelled();
        for &(index, result) in &done {
            in_flight -= 1;
            let Some(slot) = slots.get_mut(index as usize) else {
                failure.get_or_insert(Error::Internal(format!(
                    "the ring answered for request {index}, which was never made"
                )));
                continue;
            };
            let answered = if result < 0 {
                Err(target.refused_with(call, -result, job.block, slot.offset))
            } else if result as usize != job.block {
                // Cut short: past the end of a file shorter than it was made.
                Err(Error::Io { call, errno: 0 })
            } else if job.direction == Direction::Read {
                check_read(slot.buffer.as_slice(), slot.offset)
            } else {
                Ok(())
            };
            match answered {
                Ok(()) => {
                    lap.bytes += job.block as u64;
                    lap.requests += 1;
                    lap.latency.record(now.saturating_sub(slot.began_ns));
                    ended_ns = now;
                }
                Err(error) => {
                    failure.get_or_insert(error);
                }
            }
            // Past the time, or stopping: the requests in flight are waited
            // for, and no more are made.
            if failure.is_none() && !cancelled && now < deadline_ns {
                if let Err(error) = ask(&mut ring, slot, index as usize, &mut in_flight) {
                    failure.get_or_insert(error);
                }
            }
        }
        if now >= next_sample_ns {
            lap.samples.push(Sample {
                at_ns: now - began_ns,
                bytes: lap.bytes,
            });
            next_sample_ns = next_sample(next_sample_ns, now);
        }
    }

    if let Some(error) = failure {
        return Err(error);
    }
    if cancelled {
        return Err(Error::Cancelled);
    }
    // A lap in which nothing ended lasted what it was asked to.
    lap.elapsed_ns = if lap.requests == 0 {
        lasts_ns
    } else {
        ended_ns - began_ns
    };
    Ok(lap)
}
