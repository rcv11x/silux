//! Where a file lies on the device under its file system, as the kernel
//! says with `FS_IOC_FIEMAP`. On a hard disk the outer part of the platter,
//! at the start, reads up to twice as fast as the inner one.

use std::os::fd::RawFd;

use crate::common::error::{errno, Error, Result};

/// `struct fiemap` of linux/fiemap.h, without its array of extents.
#[repr(C)]
#[derive(Default)]
struct Header {
    start: u64,
    length: u64,
    flags: u32,
    mapped_extents: u32,
    extent_count: u32,
    reserved: u32,
}

/// `struct fiemap_extent` of linux/fiemap.h.
#[repr(C)]
#[derive(Clone, Copy, Default)]
struct RawExtent {
    logical: u64,
    physical: u64,
    length: u64,
    reserved64: [u64; 2],
    flags: u32,
    reserved: [u32; 3],
}

const BATCH: usize = 64;

/// The header and room for a batch of extents, as the kernel reads and
/// fills them.
#[repr(C)]
struct Request {
    header: Header,
    extents: [RawExtent; BATCH],
}

/// `_IOWR('f', 11, struct fiemap)`, from linux/fs.h.
const FS_IOC_FIEMAP: libc::Ioctl = 0xC020_660B;
/// The file's data on the disk before it is mapped.
const FLAG_SYNC: u32 = 0x1;
/// The last extent of the file.
pub const EXTENT_LAST: u32 = 0x1;

/// One piece of the file: where it is in the file, where on the device
/// (in bytes from its start) and how long, with the kernel's flags.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct Extent {
    pub logical: u64,
    pub physical: u64,
    pub length: u64,
    pub flags: u32,
}

/// Every extent of the file open as `fd`, in order.
pub fn extents(fd: RawFd) -> Result<Vec<Extent>> {
    let mut found = Vec::new();
    let mut start = 0u64;
    loop {
        let mut request = Request {
            header: Header {
                start,
                length: u64::MAX,
                flags: FLAG_SYNC,
                extent_count: BATCH as u32,
                ..Header::default()
            },
            extents: [RawExtent::default(); BATCH],
        };
        // SAFETY: a descriptor the caller owns, and `request` is a header
        // followed by room for `extent_count` extents, as the call reads
        // and writes them.
        if unsafe { libc::ioctl(fd, FS_IOC_FIEMAP, &mut request) } != 0 {
            return Err(Error::Io {
                call: "fiemap",
                errno: errno(),
            });
        }
        let mapped = (request.header.mapped_extents as usize).min(BATCH);
        let mut batch = request.extents.iter().take(mapped);
        found.extend(batch.clone().map(|raw| Extent {
            logical: raw.logical,
            physical: raw.physical,
            length: raw.length,
            flags: raw.flags,
        }));
        match batch.next_back() {
            Some(last) if last.flags & EXTENT_LAST == 0 && mapped == BATCH => {
                start = last.logical + last.length;
            }
            _ => return Ok(found),
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::disk::target::testing::Folder;
    use std::io::{Seek, SeekFrom, Write};
    use std::os::fd::AsRawFd;

    #[test]
    fn the_structures_are_those_of_linux_fiemap_h() {
        assert_eq!(std::mem::size_of::<Header>(), 32);
        assert_eq!(std::mem::size_of::<RawExtent>(), 56);
        // _IOWR: read and write (3) in bits 30-31, the size in 16-29, the
        // type 'f' in 8-15 and the number, 11.
        let iowr = (3 << 30) | (32 << 16) | ((b'f' as libc::Ioctl) << 8) | 11;
        assert_eq!(FS_IOC_FIEMAP, iowr);
    }

    #[test]
    fn a_file_written_is_mapped_whole() {
        let folder = Folder::new("extents");
        let path = folder.0.join("mapped");
        let mut file = std::fs::File::create(&path).unwrap();
        // Two hundred pieces with a hole after each: more extents than
        // three batches.
        for piece in 0..200u8 {
            file.write_all(&vec![piece + 1; 64 * 1024]).unwrap();
            file.seek(SeekFrom::Current(64 * 1024)).unwrap();
        }
        file.write_all(b"end").unwrap();
        file.sync_all().unwrap();
        let found = match extents(file.as_raw_fd()) {
            Ok(found) => found,
            // tmpfs and some others don't say.
            Err(Error::Io { errno, .. }) if errno == libc::EOPNOTSUPP => return,
            Err(error) => panic!("{error}"),
        };
        std::fs::remove_file(&path).unwrap();
        assert!(!found.is_empty());
        assert_eq!(found[0].logical, 0);
        for pair in found.windows(2) {
            assert!(
                pair[1].logical >= pair[0].logical + pair[0].length,
                "{pair:?}"
            );
        }
        assert!(found.len() > 3 * BATCH, "{}", found.len());
        let last = found.last().unwrap();
        assert_ne!(last.flags & EXTENT_LAST, 0);
        assert!(last.logical + last.length >= 200 * 128 * 1024);
    }
}
