//! Silux's memory benchmark, measured natively: how long a load that
//! misses takes, by block size, and how fast memory moves. Linux only.

pub mod bandwidth;
pub mod cancel;
pub mod error;
pub mod frequency;
pub mod kernels;
pub mod latency;
pub mod memory;
pub mod rng;
pub mod stats;
pub mod timer;
pub mod topology;

#[cfg(feature = "python")]
mod python;
