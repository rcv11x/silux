//! A path tracer whose result is checked bit by bit.
//!
//! The picture is cut into tiles, and a tile at one pass is a unit of work
//! with a fingerprint that has to come out the same on every processor. For
//! that, the code that computes it only uses operations IEEE 754 rounds
//! exactly, in one fixed order, whatever instructions carry them out.

pub mod bvh;
pub mod math;
