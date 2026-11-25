//! The block being measured: mapped at a huge-page boundary, with the page
//! size asked for, and a way to see which pages the kernel actually gave.

use crate::error::{errno, Error, Result};

/// A cache line: the unit a load brings in.
pub const LINE: usize = 64;
/// A transparent huge page on x86-64 and most arm64 kernels.
pub const HUGE_PAGE: usize = 2 * 1024 * 1024;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Pages {
    /// 2 MiB pages: one TLB entry covers 512 lines' worth of 4 KiB pages, so
    /// the curve shows the caches rather than page walks.
    Huge,
    /// 4 KiB pages, to see what the TLB adds.
    Small,
}

/// Resident bytes of a block, and how many of them sit in huge pages.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct Residency {
    pub rss_bytes: u64,
    pub huge_bytes: u64,
}

pub struct Block {
    map: *mut libc::c_void,
    map_len: usize,
    start: *mut u8,
    len: usize,
}

impl Block {
    /// Map `len` bytes, rounded up to whole huge pages, from a 2 MiB
    /// boundary. Nothing is touched: the pages arrive on the first write,
    /// from the thread that will measure, and so on its NUMA node.
    pub fn reserve(len: usize, pages: Pages) -> Result<Block> {
        let len = len
            .checked_next_multiple_of(HUGE_PAGE)
            .ok_or(Error::BadSize(len))?;
        // One huge page more, to slide the start to a boundary.
        let map_len = len.checked_add(HUGE_PAGE).ok_or(Error::BadSize(len))?;
        // SAFETY: an anonymous private mapping with no file and no fixed
        // address: the kernel only hands back memory nobody else uses.
        let map = unsafe {
            libc::mmap(
                std::ptr::null_mut(),
                map_len,
                libc::PROT_READ | libc::PROT_WRITE,
                libc::MAP_PRIVATE | libc::MAP_ANONYMOUS | libc::MAP_NORESERVE,
                -1,
                0,
            )
        };
        if map == libc::MAP_FAILED {
            return Err(Error::NoMemory {
                bytes: map_len,
                errno: errno(),
            });
        }
        let offset = (HUGE_PAGE - (map as usize) % HUGE_PAGE) % HUGE_PAGE;
        // SAFETY: `offset < HUGE_PAGE` and the mapping is `len + HUGE_PAGE`
        // long, so `start..start + len` lies inside it.
        let start = unsafe { map.cast::<u8>().add(offset) };
        let advice = match pages {
            Pages::Huge => libc::MADV_HUGEPAGE,
            Pages::Small => libc::MADV_NOHUGEPAGE,
        };
        // A kernel without transparent huge pages refuses the advice. The
        // block is measured anyway, and `residency` says what it got.
        // SAFETY: `start..start + len` is inside our own mapping and `start`
        // is page aligned, as madvise requires.
        let _ = unsafe { libc::madvise(start.cast(), len, advice) };
        Ok(Block {
            map,
            map_len,
            start,
            len,
        })
    }

    pub fn len(&self) -> usize {
        self.len
    }

    pub fn is_empty(&self) -> bool {
        self.len == 0
    }

    pub fn as_mut_ptr(&self) -> *mut u8 {
        self.start
    }

    /// What the kernel gave for this block, from `/proc/self/smaps`.
    pub fn residency(&self) -> Option<Residency> {
        let text = std::fs::read_to_string("/proc/self/smaps").ok()?;
        residency_in(&text, self.start as usize, self.len)
    }
}

impl Drop for Block {
    fn drop(&mut self) {
        // SAFETY: `map` and `map_len` are exactly what mmap returned, and
        // nothing points into the block once it's dropped.
        unsafe {
            libc::munmap(self.map, self.map_len);
        }
    }
}

/// Add up `Rss` and `AnonHugePages` of every mapping that overlaps
/// `start..start + len`. The kernel may split one mapping in several, after
/// the madvise, so it isn't only the one that begins at `start`.
pub fn residency_in(smaps: &str, start: usize, len: usize) -> Option<Residency> {
    let end = start.checked_add(len)?;
    let mut inside = false;
    let mut found = false;
    let (mut rss_kib, mut huge_kib) = (0u64, 0u64);
    for line in smaps.lines() {
        if let Some((low, high)) = mapping_range(line) {
            inside = low < end && start < high;
            found |= inside;
            continue;
        }
        if !inside {
            continue;
        }
        if let Some(kib) = field_kib(line, "Rss:") {
            rss_kib += kib;
        } else if let Some(kib) = field_kib(line, "AnonHugePages:") {
            huge_kib += kib;
        }
    }
    found.then_some(Residency {
        rss_bytes: rss_kib * 1024,
        huge_bytes: huge_kib * 1024,
    })
}

/// The address range of a mapping's header line («7f12…-7f13… rw-p …»).
fn mapping_range(line: &str) -> Option<(usize, usize)> {
    let range = line.split_whitespace().next()?;
    let (low, high) = range.split_once('-')?;
    Some((
        usize::from_str_radix(low, 16).ok()?,
        usize::from_str_radix(high, 16).ok()?,
    ))
}

fn field_kib(line: &str, name: &str) -> Option<u64> {
    let rest = line.strip_prefix(name)?;
    rest.split_whitespace().next()?.parse().ok()
}

#[cfg(test)]
mod tests {
    use super::*;

    const SMAPS: &str = "\
55d0a0000000-55d0a0021000 rw-p 00000000 00:00 0                          [heap]
Size:                132 kB
Rss:                   8 kB
AnonHugePages:         0 kB
7f0000000000-7f0000400000 rw-p 00000000 00:00 0
Size:               4096 kB
Rss:                4096 kB
AnonHugePages:      4096 kB
7f0000400000-7f0000600000 rw-p 00000000 00:00 0
Size:               2048 kB
Rss:                 512 kB
AnonHugePages:         0 kB
VmFlags: rd wr mr mw me ac nh
7f0000600000-7f0000800000 r--p 00000000 08:01 1234                       /usr/lib/libc.so.6
Rss:                1000 kB
AnonHugePages:         0 kB
";

    #[test]
    fn adds_every_mapping_the_block_overlaps() {
        let r = residency_in(SMAPS, 0x7f00_0000_0000, 6 * 1024 * 1024).unwrap();
        assert_eq!(r.rss_bytes, (4096 + 512) * 1024);
        assert_eq!(r.huge_bytes, 4096 * 1024);
    }

    #[test]
    fn a_block_nobody_maps_is_none() {
        assert_eq!(residency_in(SMAPS, 0x1000, 4096), None);
    }

    #[test]
    fn starts_on_a_huge_page_and_is_writable() {
        for pages in [Pages::Huge, Pages::Small] {
            let block = Block::reserve(3 * 1024 * 1024, pages).unwrap();
            assert_eq!(block.as_mut_ptr() as usize % HUGE_PAGE, 0);
            assert_eq!(block.len(), 4 * 1024 * 1024);
            let words = block.len() / 8;
            // SAFETY: the block is `len` bytes, aligned, and ours.
            let slice =
                unsafe { std::slice::from_raw_parts_mut(block.as_mut_ptr().cast::<u64>(), words) };
            slice.fill(7);
            assert!(slice.iter().all(|w| *w == 7));
            let residency = block.residency().unwrap();
            assert_eq!(residency.rss_bytes, block.len() as u64);
            if pages == Pages::Small {
                assert_eq!(residency.huge_bytes, 0);
            }
        }
    }

    #[test]
    fn an_impossible_size_is_an_error() {
        assert!(matches!(
            Block::reserve(usize::MAX - 10, Pages::Small),
            Err(Error::BadSize(_))
        ));
    }
}
