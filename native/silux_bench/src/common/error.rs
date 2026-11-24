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
