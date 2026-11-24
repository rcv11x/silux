//! The disk benchmark: how fast a file in a folder of the user's reads and
//! writes past the page cache.

pub mod buffers;
pub mod histogram;
pub mod job;
pub mod run;
pub mod target;
pub mod threads;

#[cfg(test)]
mod killed;
