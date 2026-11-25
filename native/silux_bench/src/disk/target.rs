//! The file the tests read and write: one that never has a name.
//!
//! It is made inside a folder, never out of a device, and it isn't in the
//! folder at any moment: the kernel frees it when its descriptor closes,
//! whether the test ends, is cancelled or the process is killed. Nothing has
//! to remember to delete it, and nothing is left to look for afterwards.

use std::ffi::CString;
use std::fs::File;
use std::os::fd::{AsRawFd, FromRawFd, OwnedFd, RawFd};
use std::os::unix::ffi::OsStrExt;
use std::path::Path;

use crate::common::cancel::Control;
use crate::common::error::{errno, Error, Result};
use crate::common::rng::Rng;
use crate::common::timer::now_ns;
use crate::disk::buffers::Buffer;

/// Free space left alone besides the file's own.
pub const MARGIN: u64 = 1 << 30;
/// The file is written, and sized, in blocks of this.
pub const FILL_BLOCK: usize = 1 << 20;
/// Offsets and sizes are multiples of this where the file doesn't say what
/// it needs: every block the tests use is, and no disk asks for more.
const ASSUMED_ALIGN: usize = 4096;
/// Ours alone to read and write.
const MODE: libc::c_uint = 0o600;
/// Names tried when the file has to be given one for an instant.
const NAME_TRIES: usize = 8;
/// What that name begins with; sixteen hexadecimal digits follow.
const NAME_PREFIX: &str = ".silux-disk-test-";
const NAME_DIGITS: usize = 16;

// `linux/magic.h`.
const TMPFS_MAGIC: u32 = 0x0102_1994;
const RAMFS_MAGIC: u32 = 0x8584_58f6;
const NFS_SUPER_MAGIC: u32 = 0x6969;
const SMB_SUPER_MAGIC: u32 = 0x517b;
const CIFS_SUPER_MAGIC: u32 = 0xff53_4d42;
const SMB2_SUPER_MAGIC: u32 = 0xfe53_4d42;
const BTRFS_SUPER_MAGIC: u32 = 0x9123_683e;
/// `FS_NOCOW_FL` of `linux/fs.h`: what `chattr +C` sets.
const FS_NOCOW_FL: libc::c_int = 0x0080_0000;
/// `STATX_DIOALIGN` of `linux/stat.h`, since Linux 6.1.
const STATX_DIOALIGN: u32 = 0x2000;

/// `struct statx` of `linux/stat.h`. libc's own lacks the two alignments
/// with glibc, and the call goes straight to the kernel so that it doesn't
/// depend on which glibc is there.
#[repr(C)]
struct Statx {
    mask: u32,
    blksize: u32,
    attributes: u64,
    nlink: u32,
    uid: u32,
    gid: u32,
    mode: u16,
    spare0: u16,
    ino: u64,
    size: u64,
    blocks: u64,
    attributes_mask: u64,
    /// Four timestamps of 16 bytes.
    times: [u64; 8],
    rdev_major: u32,
    rdev_minor: u32,
    dev_major: u32,
    dev_minor: u32,
    mnt_id: u64,
    dio_mem_align: u32,
    dio_offset_align: u32,
    spare: [u64; 12],
}

/// How the file came to have no name.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Creation {
    /// Made without one (`O_TMPFILE`).
    Unnamed,
    /// Made with one and unlinked before anything was written, where the
    /// file system can't make one without.
    Unlinked,
}

/// What reading and writing past the page cache asks of each request.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct Align {
    /// The address of its memory is a multiple of this.
    pub memory: usize,
    /// Its offset in the file and its length are multiples of this.
    pub offset: usize,
    /// Whether the file said so itself, or it is assumed.
    pub declared: bool,
}

pub struct Target {
    file: File,
    bytes: u64,
    align: Align,
    creation: Creation,
    no_cow: Option<bool>,
    filesystem: u32,
}

impl Target {
    /// A file of `bytes`, a whole number of MiB, in `folder`: without a
    /// name, with its space reserved, and set to be read and written past
    /// the page cache. Its contents are still to be written (`fill`).
    pub fn create(folder: &Path, bytes: u64) -> Result<Target> {
        Target::create_as(folder, bytes, true)
    }

    /// `create`, starting from a name when `unnamed` is false: what happens
    /// by itself where a file can't be made without one.
    fn create_as(path: &Path, bytes: u64, unnamed: bool) -> Result<Target> {
        if bytes == 0 || !bytes.is_multiple_of(FILL_BLOCK as u64) || i64::try_from(bytes).is_err() {
            return Err(Error::BadSetting("bytes"));
        }
        let c_path = CString::new(path.as_os_str().as_bytes()).map_err(|_| Error::NoFolder {
            errno: libc::EINVAL,
        })?;
        // `O_DIRECTORY`: a device or a file given as the folder is refused
        // here, before anything could be written to it.
        // SAFETY: `c_path` is a NUL-terminated string that outlives the call.
        let raw = unsafe {
            libc::open(
                c_path.as_ptr(),
                libc::O_RDONLY | libc::O_DIRECTORY | libc::O_CLOEXEC,
            )
        };
        if raw < 0 {
            return Err(Error::NoFolder { errno: errno() });
        }
        // SAFETY: `raw` is a descriptor just opened, that nothing else owns.
        let folder = unsafe { OwnedFd::from_raw_fd(raw) };

        let (filesystem, free) = filesystem_of(&folder)?;
        match filesystem {
            TMPFS_MAGIC | RAMFS_MAGIC => return Err(Error::InMemory),
            NFS_SUPER_MAGIC | SMB_SUPER_MAGIC | CIFS_SUPER_MAGIC | SMB2_SUPER_MAGIC => {
                return Err(Error::Network)
            }
            _ => {}
        }
        let needed = bytes.saturating_add(MARGIN);
        if free < needed {
            return Err(Error::NoSpace { needed, free });
        }

        remove_leftovers(path, &folder);
        let (file, creation) = open_without_a_name(&folder, unnamed)?;
        // While it's empty: btrfs only takes the flag then. Without it a
        // direct write to a file with checksums goes through the page cache
        // since Linux 6.15, and the test would time the memory.
        let no_cow = (filesystem == BTRFS_SUPER_MAGIC).then(|| set_no_cow(&file));
        reserve(&file, bytes)?;
        let align = alignment(&file)?;
        let target = Target {
            file,
            bytes,
            align,
            creation,
            no_cow,
            filesystem,
        };
        target.set_direct(true)?;
        Ok(target)
    }

    pub fn bytes(&self) -> u64 {
        self.bytes
    }

    pub fn align(&self) -> Align {
        self.align
    }

    pub fn creation(&self) -> Creation {
        self.creation
    }

    /// On btrfs, whether the file could be kept from copy-on-write and
    /// checksums; `None` anywhere else, where there is nothing to ask.
    pub fn no_cow(&self) -> Option<bool> {
        self.no_cow
    }

    /// The file system's magic number, as `statfs` gives it.
    pub fn filesystem(&self) -> u32 {
        self.filesystem
    }

    /// Whether requests go past the page cache from here on. Off is only
    /// for seeing `cached_bytes` notice.
    pub(crate) fn set_direct(&self, on: bool) -> Result<()> {
        let fd = self.file.as_raw_fd();
        // SAFETY: only reads the flags of a descriptor we own.
        let flags = unsafe { libc::fcntl(fd, libc::F_GETFL) };
        if flags < 0 {
            return Err(Error::Io {
                call: "fcntl",
                errno: errno(),
            });
        }
        let wanted = if on {
            flags | libc::O_DIRECT
        } else {
            flags & !libc::O_DIRECT
        };
        // SAFETY: sets the flags of a descriptor we own; no memory involved.
        if unsafe { libc::fcntl(fd, libc::F_SETFL, wanted) } != 0 {
            // A file system without direct reads and writes says so here.
            return Err(match errno() {
                libc::EINVAL => Error::NoDirect {
                    errno: libc::EINVAL,
                },
                other => Error::Io {
                    call: "fcntl",
                    errno: other,
                },
            });
        }
        Ok(())
    }

    /// Write the whole file, with random data stamped with where it goes: no
    /// holes and no blocks reserved but unwritten, which a file system
    /// writes over differently. `control` counts its blocks and can stop it.
    pub fn fill(&self, seed: u64, control: &Control) -> Result<()> {
        let mut buffer = Buffer::random(FILL_BLOCK, self.align.memory, &mut Rng::new(seed))?;
        let blocks = self.bytes / FILL_BLOCK as u64;
        control.begin(blocks);
        for block in 0..blocks {
            control.check()?;
            let offset = block * FILL_BLOCK as u64;
            buffer.stamp(offset, 0);
            self.write_at(buffer.as_slice(), offset)?;
            control.advance();
        }
        // SAFETY: a descriptor we own; no memory involved.
        if unsafe { libc::fdatasync(self.file.as_raw_fd()) } != 0 {
            return Err(Error::Io {
                call: "fdatasync",
                errno: errno(),
            });
        }
        Ok(())
    }

    /// A request that isn't aligned as the file asks is a bug of ours, and
    /// is stopped here: some file systems would serve it through the page
    /// cache without a word instead of refusing it.
    pub(crate) fn check_aligned(
        &self,
        call: &'static str,
        address: usize,
        len: usize,
        offset: u64,
    ) -> Result<()> {
        let Align {
            memory, offset: by, ..
        } = self.align;
        if address.is_multiple_of(memory)
            && len.is_multiple_of(by)
            && offset.is_multiple_of(by as u64)
        {
            return Ok(());
        }
        Err(Error::Internal(format!(
            "{call} of {len} bytes at offset {offset} from address {address:#x} isn't aligned \
             to {by} in the file and {memory} in memory"
        )))
    }

    /// The error of a request the kernel just refused.
    fn refused(&self, call: &'static str, len: usize, offset: u64) -> Error {
        self.refused_with(call, errno(), len, offset)
    }

    /// The error of a request the kernel refused with `errno`.
    pub(crate) fn refused_with(
        &self,
        call: &'static str,
        errno: i32,
        len: usize,
        offset: u64,
    ) -> Error {
        let free = filesystem_of(&self.file).ok().map(|(_, free)| free);
        refused(call, errno, self.align, len, offset, free)
    }

    /// Read the whole of `block` from `offset` of the file.
    pub fn read_at(&self, block: &mut [u8], offset: u64) -> Result<()> {
        self.check_aligned("pread", block.as_ptr() as usize, block.len(), offset)?;
        let mut done = 0;
        while let Some(rest) = block.get_mut(done..).filter(|rest| !rest.is_empty()) {
            // SAFETY: `rest` is writable memory of its own length for the
            // whole call.
            let moved = unsafe {
                libc::pread64(
                    self.file.as_raw_fd(),
                    rest.as_mut_ptr().cast(),
                    rest.len(),
                    (offset + done as u64) as i64,
                )
            };
            match moved {
                moved if moved > 0 => done += moved as usize,
                // Past the end of the file: it is shorter than it was made.
                0 => {
                    return Err(Error::Io {
                        call: "pread",
                        errno: 0,
                    })
                }
                _ if errno() == libc::EINTR => {}
                _ => return Err(self.refused("pread", block.len(), offset)),
            }
        }
        Ok(())
    }

    /// Write the whole of `block` at `offset` of the file.
    pub fn write_at(&self, block: &[u8], offset: u64) -> Result<()> {
        self.check_aligned("pwrite", block.as_ptr() as usize, block.len(), offset)?;
        let mut done = 0;
        while let Some(rest) = block.get(done..).filter(|rest| !rest.is_empty()) {
            // SAFETY: `rest` is readable memory of its own length for the
            // whole call.
            let moved = unsafe {
                libc::pwrite64(
                    self.file.as_raw_fd(),
                    rest.as_ptr().cast(),
                    rest.len(),
                    (offset + done as u64) as i64,
                )
            };
            match moved {
                moved if moved > 0 => done += moved as usize,
                0 => {
                    return Err(Error::Io {
                        call: "pwrite",
                        errno: 0,
                    })
                }
                _ if errno() == libc::EINTR => {}
                _ => return Err(self.refused("pwrite", block.len(), offset)),
            }
        }
        Ok(())
    }

    /// How much of the file the kernel holds in its page cache. Read and
    /// written past it, none: anything else means a request went through
    /// memory, and its time isn't the disk's.
    pub fn cached_bytes(&self) -> Result<u64> {
        let len = usize::try_from(self.bytes).map_err(|_| Error::BadSetting("bytes"))?;
        let page = page_size();
        // SAFETY: a new shared mapping of a file we own, at an address the
        // kernel picks; nothing is read through it.
        let map = unsafe {
            libc::mmap(
                std::ptr::null_mut(),
                len,
                libc::PROT_READ,
                libc::MAP_SHARED,
                self.file.as_raw_fd(),
                0,
            )
        };
        if map == libc::MAP_FAILED {
            return Err(Error::Io {
                call: "mmap",
                errno: errno(),
            });
        }
        let mut resident = vec![0u8; len.div_ceil(page)];
        // SAFETY: `map` is `len` bytes long and `resident` has a byte for
        // each of its pages, which is what mincore writes.
        let failed = unsafe { libc::mincore(map, len, resident.as_mut_ptr()) } != 0;
        let why = errno();
        // SAFETY: exactly what mmap returned, and nothing points into it.
        unsafe { libc::munmap(map, len) };
        if failed {
            return Err(Error::Io {
                call: "mincore",
                errno: why,
            });
        }
        let pages = resident.iter().filter(|page| **page & 1 == 1).count();
        Ok((pages * page) as u64)
    }
}

impl AsRawFd for Target {
    fn as_raw_fd(&self) -> RawFd {
        self.file.as_raw_fd()
    }
}

/// What a request the kernel refused with `errno` means. It was aligned to
/// `align` (`check_aligned`), and `free` is what the file system has left,
/// where that could be asked.
fn refused(
    call: &'static str,
    errno: i32,
    align: Align,
    len: usize,
    offset: u64,
    free: Option<u64>,
) -> Error {
    match (errno, free) {
        // The file said this alignment was enough: the fault isn't a file
        // system without direct requests, it is in what was sent.
        (libc::EINVAL, _) if align.declared => Error::Internal(format!(
            "{call} of {len} bytes at offset {offset} was refused as invalid, aligned to the \
             {} in the file and {} in memory that the file declared",
            align.offset, align.memory
        )),
        // It didn't say: what a file system that took `O_DIRECT` and then
        // can't do it answers to the request itself.
        (libc::EINVAL, _) => Error::NoDirect { errno },
        (libc::ENOSPC | libc::EDQUOT, Some(free)) => Error::NoSpace {
            needed: len as u64,
            free,
        },
        // Past the largest file the file system takes: not a failing disk.
        (libc::EFBIG, _) => Error::TooBig {
            bytes: offset + len as u64,
        },
        _ => Error::Io { call, errno },
    }
}

fn page_size() -> usize {
    // SAFETY: no arguments but a constant; it only reads.
    let size = unsafe { libc::sysconf(libc::_SC_PAGESIZE) };
    usize::try_from(size).unwrap_or(ASSUMED_ALIGN)
}

/// The magic number of the file system a descriptor is on, and the bytes a
/// user may still write to it: not root's reserve.
fn filesystem_of(fd: &impl AsRawFd) -> Result<(u32, u64)> {
    // SAFETY: statfs is plain numbers, and all zeros is a valid one.
    let mut found: libc::statfs = unsafe { std::mem::zeroed() };
    // SAFETY: an open descriptor, and `found` is valid and writable.
    if unsafe { libc::fstatfs(fd.as_raw_fd(), &mut found) } != 0 {
        return Err(Error::Io {
            call: "fstatfs",
            errno: errno(),
        });
    }
    let block = if found.f_frsize > 0 {
        found.f_frsize
    } else {
        found.f_bsize
    };
    let free = (found.f_bavail as u64).saturating_mul(block as u64);
    Ok((found.f_type as u32, free))
}

/// A new, empty file in `folder` that isn't in it.
fn open_without_a_name(folder: &OwnedFd, unnamed: bool) -> Result<(File, Creation)> {
    let cannot = |errno| match errno {
        libc::EACCES | libc::EPERM | libc::EROFS => Error::NoWrite { errno },
        errno => Error::Io {
            call: "openat",
            errno,
        },
    };
    if unnamed {
        // `O_EXCL` here means it can't be given a name later either.
        // SAFETY: `folder` is an open directory and the path is a
        // NUL-terminated literal.
        let raw = unsafe {
            libc::openat(
                folder.as_raw_fd(),
                c".".as_ptr(),
                libc::O_TMPFILE | libc::O_EXCL | libc::O_RDWR | libc::O_CLOEXEC,
                MODE,
            )
        };
        if raw >= 0 {
            // SAFETY: a descriptor just opened, that nothing else owns.
            return Ok((unsafe { File::from_raw_fd(raw) }, Creation::Unnamed));
        }
        match errno() {
            // The file system can't, or the kernel doesn't know how.
            libc::EOPNOTSUPP | libc::EISDIR | libc::ENOSYS => {}
            other => return Err(cannot(other)),
        }
    }
    let mut rng = Rng::new(now_ns() ^ (u64::from(std::process::id()) << 32));
    for _ in 0..NAME_TRIES {
        let name = CString::new(format!("{NAME_PREFIX}{:016x}", rng.next_u64()))
            .map_err(|_| Error::Internal("a name with a NUL in it".to_owned()))?;
        // Never an existing file, nor through a link someone left there.
        // SAFETY: `folder` is an open directory and `name` is a
        // NUL-terminated string that outlives the call.
        let raw = unsafe {
            libc::openat(
                folder.as_raw_fd(),
                name.as_ptr(),
                libc::O_CREAT | libc::O_EXCL | libc::O_NOFOLLOW | libc::O_RDWR | libc::O_CLOEXEC,
                MODE,
            )
        };
        if raw < 0 {
            match errno() {
                libc::EEXIST => continue,
                other => return Err(cannot(other)),
            }
        }
        // SAFETY: a descriptor just opened, that nothing else owns.
        let file = unsafe { File::from_raw_fd(raw) };
        // The name goes before the first byte is written: from here on the
        // file is freed when the descriptor closes, as the unnamed one.
        // SAFETY: as the call above.
        if unsafe { libc::unlinkat(folder.as_raw_fd(), name.as_ptr(), 0) } != 0 {
            match errno() {
                // Another test starting in this folder took it for a
                // leftover: the name is gone all the same.
                libc::ENOENT => {}
                errno => {
                    return Err(Error::Io {
                        call: "unlinkat",
                        errno,
                    })
                }
            }
        }
        return Ok((file, Creation::Unlinked));
    }
    Err(Error::Io {
        call: "openat",
        errno: libc::EEXIST,
    })
}

/// Whether a name is one this module gives a file for an instant.
fn is_ours(name: &[u8]) -> bool {
    name.strip_prefix(NAME_PREFIX.as_bytes())
        .is_some_and(|digits| {
            digits.len() == NAME_DIGITS
                && digits
                    .iter()
                    .all(|digit| matches!(digit, b'0'..=b'9' | b'a'..=b'f'))
        })
}

/// Remove what a process that died between naming its file and unlinking it
/// left in the folder: files with our name, ours, and empty. Nothing else is
/// touched, and whatever can't be read or removed is left as it is.
fn remove_leftovers(path: &Path, folder: &OwnedFd) {
    let Ok(entries) = std::fs::read_dir(path) else {
        return;
    };
    // SAFETY: no arguments; it only reads who this process runs as.
    let me = unsafe { libc::geteuid() };
    for entry in entries.flatten() {
        let name = entry.file_name();
        if !is_ours(name.as_bytes()) {
            continue;
        }
        let Ok(name) = CString::new(name.as_bytes()) else {
            continue;
        };
        // SAFETY: stat is plain numbers, and all zeros is a valid one.
        let mut found: libc::stat = unsafe { std::mem::zeroed() };
        // The entry itself, not what a link with that name points at.
        // SAFETY: `folder` is an open directory, `name` a NUL-terminated
        // string that outlives the call, and `found` is valid and writable.
        let failed = unsafe {
            libc::fstatat(
                folder.as_raw_fd(),
                name.as_ptr(),
                &mut found,
                libc::AT_SYMLINK_NOFOLLOW,
            )
        } != 0;
        let empty_file_of_ours = !failed
            && found.st_mode & libc::S_IFMT == libc::S_IFREG
            && found.st_size == 0
            && found.st_uid == me;
        if empty_file_of_ours {
            // SAFETY: as the call above; no memory is written.
            unsafe { libc::unlinkat(folder.as_raw_fd(), name.as_ptr(), 0) };
        }
    }
}

/// What `chattr +C` does, on an empty file of ours: no root needed, and it
/// touches this file alone. Whether the flag is set afterwards.
fn set_no_cow(file: &File) -> bool {
    let fd = file.as_raw_fd();
    // The kernel reads and writes an `int` here, whatever the `long` in the
    // request's name says.
    let mut flags: libc::c_int = 0;
    // SAFETY: a descriptor we own, and `flags` is valid and writable.
    if unsafe { libc::ioctl(fd, libc::FS_IOC_GETFLAGS, &mut flags) } != 0 {
        return false;
    }
    flags |= FS_NOCOW_FL;
    // SAFETY: a descriptor we own, and `flags` is valid for the call.
    if unsafe { libc::ioctl(fd, libc::FS_IOC_SETFLAGS, &flags) } != 0 {
        return false;
    }
    let mut now: libc::c_int = 0;
    // SAFETY: as the first call.
    let read = unsafe { libc::ioctl(fd, libc::FS_IOC_GETFLAGS, &mut now) } == 0;
    read && now & FS_NOCOW_FL != 0
}

/// Give the file its size and its space now: what doesn't fit is known
/// before a byte is written.
fn reserve(file: &File, bytes: u64) -> Result<()> {
    let fd = file.as_raw_fd();
    // SAFETY: a descriptor we own; no memory involved.
    if unsafe { libc::fallocate64(fd, 0, 0, bytes as i64) } == 0 {
        return Ok(());
    }
    match errno() {
        libc::ENOSPC | libc::EDQUOT => {
            let free = filesystem_of(file).map_or(0, |(_, free)| free);
            Err(Error::NoSpace {
                needed: bytes,
                free,
            })
        }
        // The file system can't reserve: the size alone, and writing the
        // file will say if it doesn't fit.
        libc::EOPNOTSUPP | libc::ENOSYS => {
            // SAFETY: a descriptor we own; no memory involved.
            if unsafe { libc::ftruncate64(fd, bytes as i64) } == 0 {
                Ok(())
            } else {
                Err(not_reserved("ftruncate", errno(), bytes))
            }
        }
        other => Err(not_reserved("fallocate", other, bytes)),
    }
}

/// What a refusal to give the file its size means, other than no space.
fn not_reserved(call: &'static str, errno: i32, bytes: u64) -> Error {
    match errno {
        // Past the largest file the file system takes (`s_maxbytes`).
        libc::EFBIG => Error::TooBig { bytes },
        _ => Error::Io { call, errno },
    }
}

/// What the file asks of a direct request. ext4, XFS and f2fs say; where
/// the kernel is older than 6.1 or the file system doesn't answer, it is
/// assumed and the first request tells.
fn alignment(file: &File) -> Result<Align> {
    let page = page_size().max(ASSUMED_ALIGN);
    // SAFETY: Statx is plain numbers, and all zeros is a valid one.
    let mut found: Statx = unsafe { std::mem::zeroed() };
    // SAFETY: an empty path with `AT_EMPTY_PATH` is the descriptor itself,
    // and `found` is the 256 bytes the kernel writes.
    let failed = unsafe {
        libc::syscall(
            libc::SYS_statx,
            file.as_raw_fd(),
            c"".as_ptr(),
            libc::AT_EMPTY_PATH,
            STATX_DIOALIGN,
            &mut found as *mut Statx,
        )
    } != 0;
    if failed || found.mask & STATX_DIOALIGN == 0 {
        return Ok(Align {
            memory: page,
            offset: ASSUMED_ALIGN,
            declared: false,
        });
    }
    // Answered, and with zeros: this file can't be read or written directly.
    if found.dio_mem_align == 0 || found.dio_offset_align == 0 {
        return Err(Error::NoDirect { errno: 0 });
    }
    Ok(Align {
        // A page is a multiple of whatever smaller it asks for.
        memory: page.max(found.dio_mem_align as usize),
        offset: found.dio_offset_align as usize,
        declared: true,
    })
}

/// What the tests of this module and of the engines share.
#[cfg(test)]
pub(crate) mod testing {
    use std::os::unix::fs::MetadataExt;
    use std::path::PathBuf;
    use std::sync::{Mutex, MutexGuard};

    use super::*;

    /// Where tests make their files, instead of the crate's `target` folder:
    /// to run them on another disk or another file system.
    pub const FOLDER_VARIABLE: &str = "SILUX_BENCH_DISK_DIR";

    /// A folder of a test's own, removed with it, and the disk to itself
    /// while it lives: tests writing to the same disk at once slowed each
    /// other past the times they check (a lap of 0.2 s taking 2).
    pub struct Folder(pub PathBuf, #[allow(dead_code)] MutexGuard<'static, ()>);

    static ONE_AT_A_TIME: Mutex<()> = Mutex::new(());

    impl Folder {
        pub fn new(name: &str) -> Folder {
            let base = std::env::var_os(FOLDER_VARIABLE).map_or_else(
                || {
                    Path::new(env!("CARGO_MANIFEST_DIR"))
                        .join("target")
                        .join("disk-tests")
                },
                PathBuf::from,
            );
            // A test that failed with it held doesn't stop the rest.
            let turn = ONE_AT_A_TIME
                .lock()
                .unwrap_or_else(|poisoned| poisoned.into_inner());
            let path = base.join(format!("{name}-{}", std::process::id()));
            std::fs::create_dir_all(&path).unwrap();
            Folder(path, turn)
        }

        pub fn names(&self) -> Vec<String> {
            std::fs::read_dir(&self.0)
                .unwrap()
                .map(|entry| entry.unwrap().file_name().to_string_lossy().into_owned())
                .collect()
        }

        /// What a user may still write to its file system, with everything
        /// freed so far counted.
        pub fn free(&self) -> u64 {
            let folder = File::open(&self.0).unwrap();
            // btrfs gives space back when it next commits.
            // SAFETY: a descriptor we own; no memory involved.
            unsafe { libc::syncfs(folder.as_raw_fd()) };
            filesystem_of(&folder).unwrap().1
        }

        /// A file to test with, or `None` where this folder can't hold one
        /// read and written past the page cache (a container, a folder kept
        /// in memory): the test has nothing to say there.
        pub fn target(&self, bytes: u64) -> Option<Target> {
            match Target::create(&self.0, bytes) {
                Ok(target) => Some(target),
                Err(error @ (Error::NoDirect { .. } | Error::InMemory | Error::NoSpace { .. })) => {
                    eprintln!("not tested here: {error}");
                    None
                }
                Err(error) => panic!("{error}"),
            }
        }
    }

    impl Drop for Folder {
        fn drop(&mut self) {
            let _ = std::fs::remove_dir_all(&self.0);
        }
    }

    impl Target {
        /// How many names the file has.
        pub fn links(&self) -> u64 {
            self.file.metadata().unwrap().nlink()
        }

        /// The size the file has now.
        pub fn size(&self) -> u64 {
            self.file.metadata().unwrap().len()
        }

        /// The file as another program can open it while this one holds
        /// it: how fio reads the very same blocks.
        pub fn path_while_open(&self) -> String {
            format!("/proc/{}/fd/{}", std::process::id(), self.file.as_raw_fd())
        }

        /// Cut the file short behind the test's back: every read past the
        /// cut then finds nothing.
        pub fn truncate(&self, bytes: u64) {
            self.file.set_len(bytes).unwrap();
        }

        pub fn create_with_a_name_first(folder: &Path, bytes: u64) -> Result<Target> {
            Target::create_as(folder, bytes, false)
        }
    }
}

#[cfg(test)]
mod tests {
    use std::mem::{offset_of, size_of};

    use super::testing::Folder;
    use super::*;
    use crate::disk::buffers::{stamps, STAMP_EVERY};

    const SMALL: u64 = 8 << 20;

    /// Against the offsets `linux/stat.h` writes next to each field, not
    /// against what this file thinks they are.
    #[test]
    fn statx_is_laid_out_as_the_kernel_writes_it() {
        assert_eq!(size_of::<Statx>(), 0x100);
        assert_eq!(offset_of!(Statx, mask), 0x00);
        assert_eq!(offset_of!(Statx, nlink), 0x10);
        assert_eq!(offset_of!(Statx, ino), 0x20);
        assert_eq!(offset_of!(Statx, size), 0x28);
        assert_eq!(offset_of!(Statx, times), 0x40);
        assert_eq!(offset_of!(Statx, rdev_major), 0x80);
        assert_eq!(offset_of!(Statx, mnt_id), 0x90);
        assert_eq!(offset_of!(Statx, dio_mem_align), 0x98);
        assert_eq!(offset_of!(Statx, dio_offset_align), 0x9c);
        assert_eq!(offset_of!(Statx, spare), 0xa0);
    }

    /// The kernel fills the same struct for any file: its size and its links
    /// have to come out as `fstat` gives them.
    #[test]
    fn statx_reads_a_real_file_right() {
        let folder = Folder::new("statx");
        let path = folder.0.join("seven");
        std::fs::write(&path, b"1234567").unwrap();
        let file = File::open(&path).unwrap();
        // SAFETY: Statx is plain numbers, and all zeros is a valid one.
        let mut found: Statx = unsafe { std::mem::zeroed() };
        // SAFETY: as the call in `alignment`.
        let failed = unsafe {
            libc::syscall(
                libc::SYS_statx,
                file.as_raw_fd(),
                c"".as_ptr(),
                libc::AT_EMPTY_PATH,
                0x7ffu32,
                &mut found as *mut Statx,
            )
        } != 0;
        assert!(!failed);
        assert_eq!(found.size, 7);
        assert_eq!(found.nlink, 1);
        assert_eq!(found.mode & 0o170000, 0o100000);
    }

    #[test]
    fn what_isnt_a_folder_is_refused() {
        let folder = Folder::new("not-a-folder");
        let file = folder.0.join("a-file");
        std::fs::write(&file, b"untouched").unwrap();
        assert_eq!(
            Target::create(&file, SMALL).err(),
            Some(Error::NoFolder {
                errno: libc::ENOTDIR
            })
        );
        assert_eq!(std::fs::read(&file).unwrap(), b"untouched");
        assert_eq!(
            Target::create(&folder.0.join("missing"), SMALL).err(),
            Some(Error::NoFolder {
                errno: libc::ENOENT
            })
        );
        // A device is not a folder either: nothing is ever opened to write
        // but a file made here.
        assert_eq!(
            Target::create(Path::new("/dev/null"), SMALL).err(),
            Some(Error::NoFolder {
                errno: libc::ENOTDIR
            })
        );
    }

    #[test]
    fn a_folder_kept_in_memory_is_refused() {
        let shm = Path::new("/dev/shm");
        let Ok(folder) = File::open(shm) else {
            return;
        };
        if filesystem_of(&folder).unwrap().0 != TMPFS_MAGIC {
            return;
        }
        assert_eq!(Target::create(shm, SMALL).err(), Some(Error::InMemory));
    }

    #[test]
    fn a_size_that_cant_be_made_is_an_error() {
        let folder = Folder::new("sizes");
        for bytes in [
            0,
            1,
            FILL_BLOCK as u64 + 512,
            u64::MAX - (u64::MAX % (1 << 20)),
        ] {
            assert_eq!(
                Target::create(&folder.0, bytes).err(),
                Some(Error::BadSetting("bytes")),
                "{bytes}"
            );
        }
        assert!(folder.names().is_empty());
    }

    #[test]
    fn a_file_that_doesnt_fit_is_refused_before_it_is_made() {
        let folder = Folder::new("too-big");
        let free = folder.free();
        // What is free fits by itself, but not with its margin.
        let bytes = free - free % FILL_BLOCK as u64;
        if bytes == 0 {
            return;
        }
        match Target::create(&folder.0, bytes).err() {
            Some(Error::NoSpace { needed, free: seen }) => {
                assert_eq!(needed, bytes + MARGIN);
                assert!(seen < needed);
            }
            // A folder in memory is refused first.
            Some(Error::InMemory) => {}
            other => panic!("{other:?}"),
        }
        assert!(folder.names().is_empty());
    }

    #[test]
    fn the_file_is_never_in_its_folder() {
        let folder = Folder::new("no-name");
        for unnamed in [true, false] {
            let target = if unnamed {
                folder.target(SMALL)
            } else {
                Target::create_with_a_name_first(&folder.0, SMALL).ok()
            };
            let Some(target) = target else {
                return;
            };
            if !unnamed {
                assert_eq!(target.creation(), Creation::Unlinked);
            }
            assert_eq!(target.links(), 0);
            assert_eq!(target.size(), SMALL);
            assert_eq!(target.bytes(), SMALL);
            assert!(folder.names().is_empty(), "{:?}", folder.names());
            target.fill(1, &Control::default()).unwrap();
            assert!(folder.names().is_empty(), "{:?}", folder.names());
        }
    }

    #[test]
    fn its_space_comes_back_when_it_is_dropped() {
        let folder = Folder::new("space");
        let bytes = 256 << 20;
        let Some(target) = folder.target(bytes) else {
            return;
        };
        target.fill(1, &Control::default()).unwrap();
        let held = folder.free();
        drop(target);
        // Other programs write to this disk too: half of it back is proof
        // enough that it was freed.
        let back = (0..20).any(|_| {
            std::thread::sleep(std::time::Duration::from_millis(100));
            folder.free() >= held + bytes / 2
        });
        assert!(back, "{held} held, {} now", folder.free());
    }

    #[test]
    fn what_it_asks_of_a_request_is_usable() {
        let folder = Folder::new("align");
        let Some(target) = folder.target(SMALL) else {
            return;
        };
        let align = target.align();
        assert!(align.memory.is_power_of_two() && align.memory >= 4096);
        assert!(align.offset.is_power_of_two());
        assert!(FILL_BLOCK.is_multiple_of(align.offset));
        // btrfs is asked to leave the file out of copy-on-write, and the
        // answer is kept either way; nothing else is asked.
        assert_eq!(
            target.no_cow().is_some(),
            target.filesystem() == BTRFS_SUPER_MAGIC
        );
    }

    #[test]
    fn filling_writes_every_block_where_it_says() {
        let folder = Folder::new("fill");
        let Some(target) = folder.target(SMALL) else {
            return;
        };
        let control = Control::default();
        target.fill(9, &control).unwrap();
        assert_eq!(control.progress(), (8, 8));
        let mut block =
            Buffer::random(FILL_BLOCK, target.align().memory, &mut Rng::new(1)).unwrap();
        let mut first = Vec::new();
        for index in 0..SMALL / FILL_BLOCK as u64 {
            let offset = index * FILL_BLOCK as u64;
            target.read_at(block.as_mut_slice(), offset).unwrap();
            let expected: Vec<(u64, u64)> = (0..FILL_BLOCK / STAMP_EVERY)
                .map(|piece| (offset + (piece * STAMP_EVERY) as u64, 0))
                .collect();
            assert_eq!(stamps(block.as_slice()).collect::<Vec<_>>(), expected);
            if index == 0 {
                first = block.as_slice().to_vec();
            } else {
                // The same random data, but for its stamps.
                assert!(block.as_slice() != first.as_slice());
                assert!(block.as_slice()[16..4096] == first[16..4096]);
            }
        }
        // What was read back is what `seed` gives, not what the buffer held.
        let seeded = Buffer::random(FILL_BLOCK, 4096, &mut Rng::new(9)).unwrap();
        for (read, made) in first
            .chunks(STAMP_EVERY)
            .zip(seeded.as_slice().chunks(STAMP_EVERY))
        {
            assert!(read[16..] == made[16..]);
        }
    }

    #[test]
    fn a_cancelled_fill_stops() {
        let folder = Folder::new("cancelled-fill");
        let Some(target) = folder.target(SMALL) else {
            return;
        };
        let control = Control::default();
        control.cancel();
        assert_eq!(target.fill(1, &control), Err(Error::Cancelled));
        assert_eq!(control.progress(), (0, 8));
    }

    /// The check that nothing went through the page cache, seen to notice
    /// when something did.
    #[test]
    fn what_goes_through_the_page_cache_is_seen() {
        let folder = Folder::new("cached");
        let Some(target) = folder.target(SMALL) else {
            return;
        };
        target.fill(1, &Control::default()).unwrap();
        if target.no_cow() == Some(false) {
            // btrfs without the flag: direct writes may be buffered.
            return;
        }
        assert_eq!(target.cached_bytes(), Ok(0));
        let mut block =
            Buffer::random(FILL_BLOCK, target.align().memory, &mut Rng::new(1)).unwrap();
        target.read_at(block.as_mut_slice(), 0).unwrap();
        target
            .write_at(block.as_slice(), FILL_BLOCK as u64)
            .unwrap();
        assert_eq!(target.cached_bytes(), Ok(0));

        target.set_direct(false).unwrap();
        target.read_at(block.as_mut_slice(), 0).unwrap();
        let cached = target.cached_bytes().unwrap();
        assert!(cached >= FILL_BLOCK as u64, "{cached}");
        assert!(cached <= SMALL);
    }

    #[test]
    fn a_request_that_isnt_aligned_is_our_bug_and_never_reaches_the_file() {
        let folder = Folder::new("misaligned");
        let Some(target) = folder.target(SMALL) else {
            return;
        };
        target.fill(1, &Control::default()).unwrap();
        let mut buffer =
            Buffer::random(2 * FILL_BLOCK, target.align().memory, &mut Rng::new(1)).unwrap();
        let by = target.align().offset;
        // The offset, the length and the address, each off by itself.
        let (whole, _) = buffer.as_mut_slice().split_at_mut(FILL_BLOCK);
        for (found, expected) in [
            (
                target.read_at(whole, 1),
                "pread of 1048576 bytes at offset 1 ",
            ),
            (
                target.write_at(whole, 7),
                "pwrite of 1048576 bytes at offset 7 ",
            ),
            (
                target.read_at(&mut whole[..by + 1], 0),
                &*format!("pread of {} bytes at offset 0 ", by + 1),
            ),
            (
                target.write_at(&whole[1..by + 1], 0),
                &*format!("pwrite of {by} bytes at offset 0 "),
            ),
        ] {
            let Err(Error::Internal(text)) = found else {
                panic!("{found:?}");
            };
            assert!(text.contains(expected), "{text}");
            assert!(
                text.contains(&format!("aligned to {by} in the file")),
                "{text}"
            );
        }
        // Nothing of that was read through the page cache, nor written.
        if target.no_cow() != Some(false) {
            assert_eq!(target.cached_bytes(), Ok(0));
        }
        target.read_at(whole, 0).unwrap();
        assert_eq!(stamps(whole).next(), Some((0, 0)));
    }

    #[test]
    fn a_file_too_large_for_its_file_system_is_not_a_failing_disk() {
        for call in ["fallocate", "ftruncate"] {
            assert_eq!(
                not_reserved(call, libc::EFBIG, 4 << 30),
                Error::TooBig { bytes: 4 << 30 }
            );
            assert_eq!(
                not_reserved(call, libc::EIO, 4 << 30),
                Error::Io {
                    call,
                    errno: libc::EIO
                }
            );
        }
        assert_eq!(Error::TooBig { bytes: 1 }.key(), "too_big");
    }

    #[test]
    fn a_refused_request_says_whose_fault_it_is() {
        let declared = Align {
            memory: 4096,
            offset: 512,
            declared: true,
        };
        let assumed = Align {
            declared: false,
            ..declared
        };
        // The file said how to ask, we asked that way and it said no: ours.
        let ours = refused("pwrite", libc::EINVAL, declared, 4096, 8192, Some(5));
        let Error::Internal(text) = &ours else {
            panic!("{ours:?}");
        };
        for expected in [
            "pwrite of 4096 bytes at offset 8192",
            "512 in the file",
            "4096 in memory",
        ] {
            assert!(text.contains(expected), "{text}");
        }
        // It never said: the file system has no direct requests.
        assert_eq!(
            refused("pread", libc::EINVAL, assumed, 4096, 8192, Some(5)),
            Error::NoDirect {
                errno: libc::EINVAL
            }
        );
        // No space, with what was asked for and what is left; and without
        // knowing what is left, no figure is made up.
        for errno in [libc::ENOSPC, libc::EDQUOT] {
            assert_eq!(
                refused("pwrite", errno, declared, 4096, 0, Some(1234)),
                Error::NoSpace {
                    needed: 4096,
                    free: 1234
                }
            );
            assert_eq!(
                refused("pwrite", errno, assumed, 4096, 0, None),
                Error::Io {
                    call: "pwrite",
                    errno
                }
            );
        }
        assert_eq!(
            refused("pread", libc::EIO, declared, 4096, 0, Some(5)),
            Error::Io {
                call: "pread",
                errno: libc::EIO
            }
        );
        // Past the largest file the file system takes: the size it would
        // have had, not a failing disk.
        assert_eq!(
            refused("pwrite", libc::EFBIG, declared, 4096, 8192, Some(5)),
            Error::TooBig { bytes: 12288 }
        );
    }

    #[test]
    fn only_our_own_empty_leftovers_are_removed() {
        let folder = Folder::new("leftovers");
        let ours = ".silux-disk-test-0123456789abcdef";
        let kept = [
            // Ours by its name, but with something in it.
            ".silux-disk-test-00000000000000aa",
            // Not our name: a letter that isn't a digit, too short, too
            // long, something after it, something before it, capitals.
            ".silux-disk-test-0123456789abcdeg",
            ".silux-disk-test-0123456789abcde",
            ".silux-disk-test-0123456789abcdef0",
            ".silux-disk-test-0123456789abcdef.bak",
            "a.silux-disk-test-0123456789abcdef",
            ".silux-disk-test-0123456789ABCDEF",
            "notes.txt",
        ];
        std::fs::write(folder.0.join(ours), b"").unwrap();
        std::fs::write(folder.0.join(kept[0]), b"someone's data").unwrap();
        for name in &kept[1..] {
            std::fs::write(folder.0.join(name), b"").unwrap();
        }
        // Our name on what isn't a file: a folder, a link to an empty file
        // and a pipe, which has no size either.
        let folder_named = ".silux-disk-test-1111111111111111";
        let link_named = ".silux-disk-test-2222222222222222";
        let pipe_named = ".silux-disk-test-3333333333333333";
        std::fs::create_dir(folder.0.join(folder_named)).unwrap();
        std::os::unix::fs::symlink("notes.txt", folder.0.join(link_named)).unwrap();
        let pipe = CString::new(folder.0.join(pipe_named).as_os_str().as_bytes()).unwrap();
        // SAFETY: a NUL-terminated path that outlives the call.
        assert_eq!(unsafe { libc::mkfifo(pipe.as_ptr(), 0o600) }, 0);

        let target = folder.target(SMALL);
        let mut names = folder.names();
        names.sort();
        let mut expected: Vec<String> = kept
            .iter()
            .chain(&[folder_named, link_named, pipe_named])
            .map(|name| (*name).to_owned())
            .collect();
        expected.sort();
        if target.is_some() {
            assert_eq!(names, expected);
            assert_eq!(
                std::fs::read(folder.0.join(kept[0])).unwrap(),
                b"someone's data"
            );
        }
    }

    #[test]
    fn a_name_is_ours_only_if_it_is_exactly_one_we_give() {
        assert!(is_ours(b".silux-disk-test-0123456789abcdef"));
        assert!(is_ours(
            format!("{NAME_PREFIX}{:016x}", u64::MAX).as_bytes()
        ));
        assert!(is_ours(format!("{NAME_PREFIX}{:016x}", 0).as_bytes()));
        for name in [
            "",
            ".silux-disk-test-",
            ".silux-disk-test-0123456789abcde",
            ".silux-disk-test-0123456789abcdef0",
            ".silux-disk-test-0123456789abcdeF",
            ".silux-disk-test-0123456789abcde/",
            "silux-disk-test-0123456789abcdef",
        ] {
            assert!(!is_ours(name.as_bytes()), "{name}");
        }
    }

    #[test]
    fn a_read_past_the_end_is_an_error() {
        let folder = Folder::new("short");
        let Some(target) = folder.target(SMALL) else {
            return;
        };
        target.fill(1, &Control::default()).unwrap();
        target.truncate(FILL_BLOCK as u64);
        let mut block =
            Buffer::random(FILL_BLOCK, target.align().memory, &mut Rng::new(1)).unwrap();
        assert_eq!(target.read_at(block.as_mut_slice(), 0), Ok(()));
        assert_eq!(
            target.read_at(block.as_mut_slice(), FILL_BLOCK as u64),
            Err(Error::Io {
                call: "pread",
                errno: 0
            })
        );
    }
}
