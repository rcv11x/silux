//! Silux's benchmarks, measured natively. Memory: how long a load that
//! misses takes, by block size, and how fast memory moves. Disk: how fast a
//! file reads and writes past the page cache. Linux only.

pub mod common;
pub mod cpu;
pub mod disk;
pub mod memory;

#[cfg(feature = "python")]
mod python;
