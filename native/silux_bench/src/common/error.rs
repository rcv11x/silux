//! What can go wrong, with a stable key the interface translates.

use std::fmt;

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum Error {
    /// A block size that can't be measured: smaller than two lines, or not a
    /// whole number of lines.
    BadSize(usize),
    /// Nothing to measure.
    NoSizes,
    /// A setting out of its range, by name.
    BadSetting(&'static str),
    /// The kernel refused the memory.
    NoMemory { bytes: usize, errno: i32 },
    /// The CPU doesn't exist, or this process may not run on it.
    BadCpu { cpu: usize, errno: i32 },
    /// The system refused another thread.
    NoThread { errno: i32 },
    /// The clock can't time a measurement.
    Clock(&'static str),
    /// The folder can't be opened as one.
    NoFolder { errno: i32 },
    /// The folder is kept in memory (tmpfs, ramfs): there is no disk under it.
    InMemory,
    /// The folder is on another machine (NFS, SMB).
    Network,
    /// No file can be created in the folder: read-only, or not ours to write.
    NoWrite { errno: i32 },
    /// The file doesn't fit: what it needs, margin included, and what is free.
    NoSpace { needed: u64, free: u64 },
    /// The file system won't read or write past the page cache here.
    NoDirect { errno: i32 },
    /// A call on the file failed; errno 0 is a read or a write cut short.
    Io { call: &'static str, errno: i32 },
    /// Stopped from outside.
    Cancelled,
    /// A bug of ours: a panic caught before it reached Python.
    Internal(String),
}

impl Error {
    /// The key Python matches on; the message is only for the report.
    pub fn key(&self) -> &'static str {
        match self {
            Error::BadSize(_) => "bad_size",
            Error::NoSizes => "no_sizes",
            Error::BadSetting(_) => "bad_setting",
            Error::NoMemory { .. } => "no_memory",
            Error::BadCpu { .. } => "bad_cpu",
            Error::NoThread { .. } => "no_thread",
            Error::Clock(_) => "clock",
            Error::NoFolder { .. } => "no_folder",
            Error::InMemory => "in_memory",
            Error::Network => "network",
            Error::NoWrite { .. } => "no_write",
            Error::NoSpace { .. } => "no_space",
            Error::NoDirect { .. } => "no_direct",
            Error::Io { .. } => "io",
            Error::Cancelled => "cancelled",
            Error::Internal(_) => "internal",
        }
    }
}

impl fmt::Display for Error {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Error::BadSize(bytes) => write!(f, "a block of {bytes} bytes can't be measured"),
            Error::NoSizes => write!(f, "no block sizes to measure"),
            Error::BadSetting(name) => write!(f, "{name} is out of range"),
            Error::NoMemory { bytes, errno } => {
                write!(f, "could not map {bytes} bytes (errno {errno})")
            }
            Error::BadCpu { cpu, errno } => write!(f, "can't run on CPU {cpu} (errno {errno})"),
            Error::NoThread { errno } => write!(f, "could not start a thread (errno {errno})"),
            Error::Clock(why) => write!(f, "the clock can't time this: {why}"),
            Error::NoFolder { errno } => write!(f, "that isn't a folder (errno {errno})"),
            Error::InMemory => write!(f, "that folder is kept in memory, not on a disk"),
            Error::Network => write!(f, "that folder is on another machine"),
            Error::NoWrite { errno } => {
                write!(f, "no file can be created in that folder (errno {errno})")
            }
            Error::NoSpace { needed, free } => {
                write!(f, "the file needs {needed} bytes and {free} are free")
            }
            Error::NoDirect { errno } => {
                write!(
                    f,
                    "no reading or writing past the page cache here (errno {errno})"
                )
            }
            Error::Io { call, errno } => write!(f, "{call} failed (errno {errno})"),
            Error::Cancelled => write!(f, "cancelled"),
            Error::Internal(why) => write!(f, "internal error: {why}"),
        }
    }
}

impl std::error::Error for Error {}

pub type Result<T> = std::result::Result<T, Error>;

/// The calling thread's errno after a failed call.
pub fn errno() -> i32 {
    std::io::Error::last_os_error().raw_os_error().unwrap_or(0)
}

/// The text of a caught panic, whatever type it was raised with.
pub fn panic_message(payload: &(dyn std::any::Any + Send)) -> String {
    if let Some(text) = payload.downcast_ref::<&str>() {
        (*text).to_owned()
    } else if let Some(text) = payload.downcast_ref::<String>() {
        text.clone()
    } else {
        "panic without a message".to_owned()
    }
}
