//! Silux's memory benchmark, measured natively: how long a load that
//! misses takes, by block size, and how fast memory moves. Linux only.

pub mod common;
pub mod disk;
pub mod memory;

#[cfg(feature = "python")]
mod python;
