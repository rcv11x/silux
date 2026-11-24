//! The memory a request reads into or writes from: aligned as reading and
//! writing past the page cache asks, and filled with random data once.
//!
//! Random, so that a disk or a file system that compresses has nothing to
//! squeeze. And each write only changes a stamp at every 4 KiB of the block,
//! saying where in the file it goes and when: no two blocks written are ever
//! the same, so nothing can be deduplicated either, and making the data
//! costs a few bytes per request instead of the whole block.

use std::alloc::{alloc_zeroed, dealloc, Layout};
use std::ptr::NonNull;

use crate::common::error::{Error, Result};
use crate::common::rng::Rng;

/// A stamp at each of these: the smallest block file systems deduplicate by.
pub const STAMP_EVERY: usize = 4096;
/// Where it goes in the file, and which write it was: two `u64`.
pub const STAMP_BYTES: usize = 16;

pub struct Buffer {
    start: NonNull<u8>,
    layout: Layout,
}

// SAFETY: the buffer owns its memory and nothing else points into it, so it
// can move to the thread that will use it.
unsafe impl Send for Buffer {}

impl Buffer {
    /// `len` bytes of random data at an address that is a multiple of
    /// `align`, a power of two.
    pub fn random(len: usize, align: usize, rng: &mut Rng) -> Result<Buffer> {
        if len == 0 {
            return Err(Error::BadSize(len));
        }
        let layout =
            Layout::from_size_align(len, align).map_err(|_| Error::BadSetting("alignment"))?;
        // SAFETY: the layout's size isn't zero, checked above.
        let start = NonNull::new(unsafe { alloc_zeroed(layout) }).ok_or(Error::NoMemory {
            bytes: len,
            errno: libc::ENOMEM,
        })?;
        let mut buffer = Buffer { start, layout };
        for word in buffer.as_mut_slice().chunks_mut(8) {
            for (byte, random) in word.iter_mut().zip(rng.next_u64().to_le_bytes()) {
                *byte = random;
            }
        }
        Ok(buffer)
    }

    pub fn as_slice(&self) -> &[u8] {
        // SAFETY: `start` points at `layout.size()` bytes this buffer owns,
        // initialized since they were allocated zeroed.
        unsafe { std::slice::from_raw_parts(self.start.as_ptr(), self.layout.size()) }
    }

    pub fn as_mut_slice(&mut self) -> &mut [u8] {
        // SAFETY: as in `as_slice`, and `&mut self` makes this the only
        // reference to them.
        unsafe { std::slice::from_raw_parts_mut(self.start.as_ptr(), self.layout.size()) }
    }

    /// Mark the block as the one that goes at `offset` of the file, written
    /// at `turn`. The rest of its data stays as it was.
    pub fn stamp(&mut self, offset: u64, turn: u64) {
        let turn = turn.to_le_bytes();
        for (index, piece) in self.as_mut_slice().chunks_mut(STAMP_EVERY).enumerate() {
            let place = offset + (index * STAMP_EVERY) as u64;
            if let Some(stamp) = piece.first_chunk_mut::<STAMP_BYTES>() {
                let (where_it_goes, when) = stamp.split_at_mut(8);
                where_it_goes.copy_from_slice(&place.to_le_bytes());
                when.copy_from_slice(&turn);
            }
        }
    }
}

impl Drop for Buffer {
    fn drop(&mut self) {
        // SAFETY: `start` came from `alloc_zeroed` with this same layout,
        // and nothing uses it after the buffer is dropped.
        unsafe { dealloc(self.start.as_ptr(), self.layout) };
    }
}

/// The stamps of a block as it was read back: where each 4 KiB says it goes,
/// and the write it says it was.
pub fn stamps(block: &[u8]) -> impl Iterator<Item = (u64, u64)> + '_ {
    block.chunks(STAMP_EVERY).filter_map(|piece| {
        let place = piece.first_chunk::<8>()?;
        let turn = piece.get(8..STAMP_BYTES)?.first_chunk::<8>()?;
        Some((u64::from_le_bytes(*place), u64::from_le_bytes(*turn)))
    })
}

/// Check that a block read from `offset` is the one that lives there, by
/// the stamp it begins with. Every block of the file carries one since it
/// was filled, so a read that brings another block is a bug of ours: a
/// figure made of the wrong blocks is not a measurement.
pub fn check_read(block: &[u8], offset: u64) -> Result<()> {
    // A block that doesn't begin where a stamp goes can't be told.
    if !offset.is_multiple_of(STAMP_EVERY as u64) {
        return Ok(());
    }
    match stamps(block).next() {
        Some((place, _)) if place != offset => Err(Error::Internal(format!(
            "the block read at offset {offset} says it belongs at {place}"
        ))),
        _ => Ok(()),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn a_block_read_from_elsewhere_is_told_by_its_stamp() {
        let mut buffer = Buffer::random(2 * STAMP_EVERY, 4096, &mut Rng::new(3)).unwrap();
        buffer.stamp(8192, 1);
        assert_eq!(check_read(buffer.as_slice(), 8192), Ok(()));
        let found = check_read(buffer.as_slice(), 4096);
        let Err(Error::Internal(text)) = &found else {
            panic!("{found:?}");
        };
        assert!(
            text.contains("read at offset 4096 says it belongs at 8192"),
            "{text}"
        );
        // Where no stamp begins the block there is nothing to compare.
        assert_eq!(check_read(buffer.as_slice(), 4096 + 512), Ok(()));
        assert_eq!(check_read(&[], 4096), Ok(()));
    }

    #[test]
    fn starts_where_it_was_asked_to() {
        let mut rng = Rng::new(1);
        for align in [512, 4096, 65536] {
            let buffer = Buffer::random(4096, align, &mut rng).unwrap();
            assert_eq!(buffer.as_slice().as_ptr() as usize % align, 0);
            assert_eq!(buffer.as_slice().len(), 4096);
        }
    }

    #[test]
    fn what_cant_be_allocated_is_an_error() {
        let mut rng = Rng::new(1);
        assert_eq!(
            Buffer::random(0, 4096, &mut rng).err(),
            Some(Error::BadSize(0))
        );
        assert_eq!(
            Buffer::random(4096, 3000, &mut rng).err(),
            Some(Error::BadSetting("alignment"))
        );
    }

    #[test]
    fn its_data_is_random_and_follows_the_seed() {
        let one = Buffer::random(1 << 20, 4096, &mut Rng::new(7)).unwrap();
        let same = Buffer::random(1 << 20, 4096, &mut Rng::new(7)).unwrap();
        let other = Buffer::random(1 << 20, 4096, &mut Rng::new(8)).unwrap();
        assert!(one.as_slice() == same.as_slice());
        assert!(one.as_slice() != other.as_slice());
        // Every value of a byte turns up about as often as the rest: nothing
        // for a compressor to hold on to.
        let mut seen = [0u32; 256];
        for byte in one.as_slice() {
            seen[*byte as usize] += 1;
        }
        let expected = (1 << 20) / 256;
        assert!(seen.iter().all(|n| n.abs_diff(expected) < expected / 5));
        // And no 4 KiB of it is the same as another.
        let mut pieces: Vec<&[u8]> = one.as_slice().chunks(STAMP_EVERY).collect();
        pieces.sort_unstable();
        pieces.dedup();
        assert_eq!(pieces.len(), (1 << 20) / STAMP_EVERY);
    }

    #[test]
    fn a_stamp_says_where_each_4_kib_goes_and_changes_nothing_else() {
        let mut buffer = Buffer::random(3 * STAMP_EVERY, 4096, &mut Rng::new(3)).unwrap();
        let before = buffer.as_slice().to_vec();
        buffer.stamp(1 << 30, 77);
        let found: Vec<(u64, u64)> = stamps(buffer.as_slice()).collect();
        assert_eq!(
            found,
            [
                (1 << 30, 77),
                ((1 << 30) + 4096, 77),
                ((1 << 30) + 8192, 77)
            ]
        );
        for (index, (now, was)) in buffer.as_slice().iter().zip(&before).enumerate() {
            if index % STAMP_EVERY >= STAMP_BYTES {
                assert_eq!(now, was, "byte {index}");
            }
        }
        // The same block stamped for somewhere else is another block.
        let first = buffer.as_slice().to_vec();
        buffer.stamp(0, 77);
        assert!(buffer.as_slice() != first.as_slice());
    }

    #[test]
    fn a_block_smaller_than_4_kib_is_stamped_too() {
        let mut buffer = Buffer::random(512, 512, &mut Rng::new(3)).unwrap();
        buffer.stamp(1024, 5);
        assert_eq!(stamps(buffer.as_slice()).collect::<Vec<_>>(), [(1024, 5)]);
    }

    /// Not a test: what stamping costs, to set against what a fast disk
    /// moves. `cargo test --release -- --ignored --nocapture stamping`.
    #[test]
    #[ignore = "a measurement, printed"]
    fn what_stamping_costs() {
        use crate::common::timer::now_ns;
        for (len, name) in [(4096, "4 KiB"), (1 << 20, "1 MiB")] {
            let mut buffer = Buffer::random(len, 4096, &mut Rng::new(3)).unwrap();
            let rounds = 2_000_000 / (len / 4096) as u64;
            let mut best = f64::MAX;
            for _ in 0..5 {
                let begin = now_ns();
                for round in 0..rounds {
                    buffer.stamp(round * len as u64, round);
                    std::hint::black_box(buffer.as_slice());
                }
                best = best.min((now_ns() - begin) as f64 / rounds as f64);
            }
            println!(
                "{name}: {best:.1} ns a block, {:.0} GB/s, {:.1} million blocks a second",
                len as f64 / best,
                1e3 / best
            );
        }
    }
}
