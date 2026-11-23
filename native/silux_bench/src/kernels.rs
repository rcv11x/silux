//! The loops that move memory, one set per instruction set.
//!
//! Every loop works on whole steps of `STEP` bytes from a 64-byte aligned
//! address.
//!
//! - Reads fold into four accumulators: with one, what's timed is the chain
//!   of XORs, each waiting for the last, not the loads.
//! - Normal stores are volatile. A loop that stores one value, or loads and
//!   stores the same, is what the compiler turns into `memset` or `memcpy`,
//!   and glibc's own switch to non-temporal stores past some size would then
//!   decide which stores were measured.
//! - Non-temporal stores end with `sfence`: they are weakly ordered, and the
//!   time has to include their reaching memory.
//!
//! Each function carries its instruction set in its name (`read_avx2`): the
//! AppImage builder's instruction-set check recognises dispatched code by it.

use crate::error::{Error, Result};

/// Bytes per trip round every loop: a whole number of vectors of every width.
pub const STEP: usize = 256;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Isa {
    /// Plain 64-bit words: any processor.
    Portable,
    Sse2,
    Avx2,
    Avx512,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Operation {
    Read,
    Write,
    Copy,
}

impl Isa {
    pub const ALL: [Isa; 4] = [Isa::Portable, Isa::Sse2, Isa::Avx2, Isa::Avx512];

    pub fn key(self) -> &'static str {
        match self {
            Isa::Portable => "portable",
            Isa::Sse2 => "sse2",
            Isa::Avx2 => "avx2",
            Isa::Avx512 => "avx512",
        }
    }

    pub fn from_key(key: &str) -> Option<Isa> {
        Isa::ALL.into_iter().find(|isa| isa.key() == key)
    }

    /// Whether this processor runs it, asked at run time: the binary is built
    /// for the oldest processor it supports.
    pub fn is_available(self) -> bool {
        match self {
            Isa::Portable => true,
            #[cfg(target_arch = "x86_64")]
            Isa::Sse2 => true,
            #[cfg(target_arch = "x86_64")]
            Isa::Avx2 => std::arch::is_x86_feature_detected!("avx2"),
            #[cfg(target_arch = "x86_64")]
            Isa::Avx512 => std::arch::is_x86_feature_detected!("avx512f"),
            #[cfg(not(target_arch = "x86_64"))]
            _ => false,
        }
    }

    /// Every set this processor runs, widest last.
    pub fn available() -> Vec<Isa> {
        Isa::ALL
            .into_iter()
            .filter(|isa| isa.is_available())
            .collect()
    }

    pub fn widest() -> Isa {
        Isa::available().last().copied().unwrap_or(Isa::Portable)
    }
}

/// Whether `run` can do this: the set is there, and non-temporal stores are
/// asked only of something that stores, with instructions that have them.
pub fn check(isa: Isa, operation: Operation, non_temporal: bool) -> Result<()> {
    if !isa.is_available() {
        return Err(Error::BadSetting("isa"));
    }
    if non_temporal && (operation == Operation::Read || isa == Isa::Portable) {
        return Err(Error::BadSetting("non_temporal"));
    }
    Ok(())
}

/// One pass of `operation` over `len` bytes: a read of `a`, a write to `a`,
/// or a copy from `a` to `b`. Returns what a read folded, for `black_box`.
///
/// # Safety
/// `check` accepted these settings; `a`, and `b` for a copy, are valid for
/// `len` bytes, 64-byte aligned and don't overlap; `len` is a multiple of
/// `STEP`.
pub unsafe fn run(
    isa: Isa,
    operation: Operation,
    non_temporal: bool,
    a: *mut u8,
    b: *mut u8,
    len: usize,
) -> u64 {
    // SAFETY: every arm is one of the loops above with the caller's
    // guarantees, and `check` ruled out a set this processor doesn't run.
    unsafe {
        match (isa, operation, non_temporal) {
            (Isa::Portable, Operation::Read, _) => portable::read_portable(a, len),
            (Isa::Portable, Operation::Write, _) => {
                portable::write_portable(a, len);
                0
            }
            (Isa::Portable, Operation::Copy, _) => {
                portable::copy_portable(a, b, len);
                0
            }
            #[cfg(target_arch = "x86_64")]
            (Isa::Sse2, Operation::Read, _) => x86::read_sse2(a, len),
            #[cfg(target_arch = "x86_64")]
            (Isa::Sse2, Operation::Write, false) => {
                x86::write_sse2(a, len);
                0
            }
            #[cfg(target_arch = "x86_64")]
            (Isa::Sse2, Operation::Write, true) => {
                x86::write_nt_sse2(a, len);
                0
            }
            #[cfg(target_arch = "x86_64")]
            (Isa::Sse2, Operation::Copy, false) => {
                x86::copy_sse2(a, b, len);
                0
            }
            #[cfg(target_arch = "x86_64")]
            (Isa::Sse2, Operation::Copy, true) => {
                x86::copy_nt_sse2(a, b, len);
                0
            }
            #[cfg(target_arch = "x86_64")]
            (Isa::Avx2, Operation::Read, _) => x86::read_avx2(a, len),
            #[cfg(target_arch = "x86_64")]
            (Isa::Avx2, Operation::Write, false) => {
                x86::write_avx2(a, len);
                0
            }
            #[cfg(target_arch = "x86_64")]
            (Isa::Avx2, Operation::Write, true) => {
                x86::write_nt_avx2(a, len);
                0
            }
            #[cfg(target_arch = "x86_64")]
            (Isa::Avx2, Operation::Copy, false) => {
                x86::copy_avx2(a, b, len);
                0
            }
            #[cfg(target_arch = "x86_64")]
            (Isa::Avx2, Operation::Copy, true) => {
                x86::copy_nt_avx2(a, b, len);
                0
            }
            #[cfg(target_arch = "x86_64")]
            (Isa::Avx512, Operation::Read, _) => x86::read_avx512(a, len),
            #[cfg(target_arch = "x86_64")]
            (Isa::Avx512, Operation::Write, false) => {
                x86::write_avx512(a, len);
                0
            }
            #[cfg(target_arch = "x86_64")]
            (Isa::Avx512, Operation::Write, true) => {
                x86::write_nt_avx512(a, len);
                0
            }
            #[cfg(target_arch = "x86_64")]
            (Isa::Avx512, Operation::Copy, false) => {
                x86::copy_avx512(a, b, len);
                0
            }
            #[cfg(target_arch = "x86_64")]
            (Isa::Avx512, Operation::Copy, true) => {
                x86::copy_nt_avx512(a, b, len);
                0
            }
            #[cfg(not(target_arch = "x86_64"))]
            _ => 0,
        }
    }
}

mod portable {
    use super::STEP;

    const WORDS: usize = STEP / 8;
    const VALUE: u64 = 0x5111_0c5e_5111_0c5e;

    /// # Safety
    /// As `run`.
    pub unsafe fn read_portable(src: *const u8, len: usize) -> u64 {
        let (mut a0, mut a1, mut a2, mut a3) = (0u64, 0u64, 0u64, 0u64);
        let mut offset = 0;
        while offset < len {
            // SAFETY: `offset + STEP <= len`, inside the caller's block.
            let q = unsafe { src.add(offset) }.cast::<u64>();
            let mut k = 0;
            while k < WORDS {
                // SAFETY: `k + 3 < WORDS`: every word is inside this step.
                unsafe {
                    a0 ^= q.add(k).read();
                    a1 ^= q.add(k + 1).read();
                    a2 ^= q.add(k + 2).read();
                    a3 ^= q.add(k + 3).read();
                }
                k += 4;
            }
            offset += STEP;
        }
        a0 ^ a1 ^ a2 ^ a3
    }

    /// # Safety
    /// As `run`.
    pub unsafe fn write_portable(dst: *mut u8, len: usize) {
        let mut offset = 0;
        while offset < len {
            // SAFETY: `offset + STEP <= len`, inside the caller's block.
            let q = unsafe { dst.add(offset) }.cast::<u64>();
            for k in 0..WORDS {
                // SAFETY: `k < WORDS`: inside this step.
                unsafe { q.add(k).write_volatile(VALUE) };
            }
            offset += STEP;
        }
    }

    /// # Safety
    /// As `run`.
    pub unsafe fn copy_portable(src: *const u8, dst: *mut u8, len: usize) {
        let mut offset = 0;
        while offset < len {
            // SAFETY: `offset + STEP <= len`, inside both blocks.
            let (s, d) = unsafe { (src.add(offset).cast::<u64>(), dst.add(offset).cast::<u64>()) };
            for k in 0..WORDS {
                // SAFETY: `k < WORDS`: inside this step of both blocks.
                unsafe { d.add(k).write_volatile(s.add(k).read()) };
            }
            offset += STEP;
        }
    }
}

#[cfg(target_arch = "x86_64")]
mod x86 {
    use std::arch::x86_64::*;

    use super::STEP;

    const VALUE: i64 = 0x5111_0c5e_5111_0c5e;

    #[target_feature(enable = "sse2")]
    fn fold_sse2(v: __m128i) -> u64 {
        (_mm_cvtsi128_si64(v) ^ _mm_cvtsi128_si64(_mm_unpackhi_epi64(v, v))) as u64
    }

    #[target_feature(enable = "avx2")]
    fn fold_avx2(v: __m256i) -> u64 {
        fold_sse2(_mm_xor_si128(
            _mm256_castsi256_si128(v),
            _mm256_extracti128_si256::<1>(v),
        ))
    }

    #[target_feature(enable = "avx512f")]
    fn fold_avx512(v: __m512i) -> u64 {
        fold_avx2(_mm256_xor_si256(
            _mm512_castsi512_si256(v),
            _mm512_extracti64x4_epi64::<1>(v),
        ))
    }

    macro_rules! kernels {
        (
            $feature:literal, $vector:ty,
            $read:ident, $write:ident, $write_nt:ident, $copy:ident, $copy_nt:ident,
            $load:ident, $stream:ident, $xor:ident, $zero:ident, $splat:ident, $fold:ident
        ) => {
            /// # Safety
            /// As `run`.
            #[target_feature(enable = $feature)]
            pub unsafe fn $read(src: *const u8, len: usize) -> u64 {
                const N: usize = STEP / size_of::<$vector>();
                let (mut a0, mut a1, mut a2, mut a3) = ($zero(), $zero(), $zero(), $zero());
                let mut offset = 0;
                while offset < len {
                    // SAFETY: `offset + STEP <= len`, inside the caller's block.
                    let q = unsafe { src.add(offset) }.cast::<$vector>();
                    let mut k = 0;
                    while k < N {
                        // SAFETY: `k + 3 < N`: every vector is inside this
                        // step, and aligned with the block.
                        unsafe {
                            a0 = $xor(a0, $load(q.add(k)));
                            a1 = $xor(a1, $load(q.add(k + 1)));
                            a2 = $xor(a2, $load(q.add(k + 2)));
                            a3 = $xor(a3, $load(q.add(k + 3)));
                        }
                        k += 4;
                    }
                    offset += STEP;
                }
                $fold($xor($xor(a0, a1), $xor(a2, a3)))
            }

            /// # Safety
            /// As `run`.
            #[target_feature(enable = $feature)]
            pub unsafe fn $write(dst: *mut u8, len: usize) {
                const N: usize = STEP / size_of::<$vector>();
                let value = $splat(VALUE);
                let mut offset = 0;
                while offset < len {
                    // SAFETY: `offset + STEP <= len`, inside the caller's block.
                    let q = unsafe { dst.add(offset) }.cast::<$vector>();
                    for k in 0..N {
                        // SAFETY: `k < N`: inside this step, aligned.
                        unsafe { q.add(k).write_volatile(value) };
                    }
                    offset += STEP;
                }
            }

            /// # Safety
            /// As `run`.
            #[target_feature(enable = $feature)]
            pub unsafe fn $write_nt(dst: *mut u8, len: usize) {
                const N: usize = STEP / size_of::<$vector>();
                let value = $splat(VALUE);
                let mut offset = 0;
                while offset < len {
                    // SAFETY: `offset + STEP <= len`, inside the caller's block.
                    let q = unsafe { dst.add(offset) }.cast::<$vector>();
                    for k in 0..N {
                        // SAFETY: `k < N`: inside this step, aligned as the
                        // streaming store requires.
                        unsafe { $stream(q.add(k), value) };
                    }
                    offset += STEP;
                }
                _mm_sfence();
            }

            /// # Safety
            /// As `run`.
            #[target_feature(enable = $feature)]
            pub unsafe fn $copy(src: *const u8, dst: *mut u8, len: usize) {
                const N: usize = STEP / size_of::<$vector>();
                let mut offset = 0;
                while offset < len {
                    // SAFETY: `offset + STEP <= len`, inside both blocks.
                    let (s, d) = unsafe {
                        (
                            src.add(offset).cast::<$vector>(),
                            dst.add(offset).cast::<$vector>(),
                        )
                    };
                    for k in 0..N {
                        // SAFETY: `k < N`: inside this step of both, aligned.
                        unsafe { d.add(k).write_volatile($load(s.add(k))) };
                    }
                    offset += STEP;
                }
            }

            /// # Safety
            /// As `run`.
            #[target_feature(enable = $feature)]
            pub unsafe fn $copy_nt(src: *const u8, dst: *mut u8, len: usize) {
                const N: usize = STEP / size_of::<$vector>();
                let mut offset = 0;
                while offset < len {
                    // SAFETY: `offset + STEP <= len`, inside both blocks.
                    let (s, d) = unsafe {
                        (
                            src.add(offset).cast::<$vector>(),
                            dst.add(offset).cast::<$vector>(),
                        )
                    };
                    for k in 0..N {
                        // SAFETY: `k < N`: inside this step of both, aligned.
                        unsafe { $stream(d.add(k), $load(s.add(k))) };
                    }
                    offset += STEP;
                }
                _mm_sfence();
            }
        };
    }

    kernels!(
        "sse2",
        __m128i,
        read_sse2,
        write_sse2,
        write_nt_sse2,
        copy_sse2,
        copy_nt_sse2,
        _mm_load_si128,
        _mm_stream_si128,
        _mm_xor_si128,
        _mm_setzero_si128,
        _mm_set1_epi64x,
        fold_sse2
    );
    kernels!(
        "avx2",
        __m256i,
        read_avx2,
        write_avx2,
        write_nt_avx2,
        copy_avx2,
        copy_nt_avx2,
        _mm256_load_si256,
        _mm256_stream_si256,
        _mm256_xor_si256,
        _mm256_setzero_si256,
        _mm256_set1_epi64x,
        fold_avx2
    );
    kernels!(
        "avx512f",
        __m512i,
        read_avx512,
        write_avx512,
        write_nt_avx512,
        copy_avx512,
        copy_nt_avx512,
        _mm512_load_si512,
        _mm512_stream_si512,
        _mm512_xor_si512,
        _mm512_setzero_si512,
        _mm512_set1_epi64,
        fold_avx512
    );
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::memory::{Block, Pages};

    const LEN: usize = 64 * 1024;

    fn block() -> Block {
        Block::reserve(2 * LEN, Pages::Small).unwrap()
    }

    #[test]
    fn every_available_set_reads_writes_and_copies_the_same() {
        for isa in Isa::available() {
            for non_temporal in [false, true] {
                if check(isa, Operation::Write, non_temporal).is_err() {
                    continue;
                }
                let block = block();
                let a = block.as_mut_ptr();
                let b = a.wrapping_add(LEN);
                // SAFETY: two halves of one block, aligned, LEN a multiple of STEP.
                unsafe {
                    run(isa, Operation::Write, non_temporal, a, b, LEN);
                    run(isa, Operation::Copy, non_temporal, a, b, LEN);
                }
                // SAFETY: the block is 2 * LEN bytes, aligned for u64.
                let words = unsafe { std::slice::from_raw_parts(a.cast::<u64>(), 2 * LEN / 8) };
                assert!(words.iter().all(|w| *w == 0x5111_0c5e_5111_0c5e), "{isa:?}");
                // An even number of equal words folds to zero; one changed
                // word shows.
                assert_eq!(
                    // SAFETY: as above.
                    unsafe { run(isa, Operation::Read, false, a, b, LEN) },
                    0,
                    "{isa:?}"
                );
                // SAFETY: word 9 is inside the block.
                unsafe { a.cast::<u64>().add(9).write(0x0f) };
                // SAFETY: as above.
                let folded = unsafe { run(isa, Operation::Read, false, a, b, LEN) };
                assert_eq!(folded, 0x5111_0c5e_5111_0c5e ^ 0x0f, "{isa:?}");
            }
        }
    }

    #[test]
    fn what_cant_run_is_refused() {
        assert_eq!(
            check(Isa::Portable, Operation::Write, true),
            Err(Error::BadSetting("non_temporal"))
        );
        assert_eq!(
            check(Isa::widest(), Operation::Read, true),
            Err(Error::BadSetting("non_temporal"))
        );
        for isa in Isa::ALL {
            assert_eq!(
                check(isa, Operation::Read, false).is_ok(),
                isa.is_available()
            );
        }
    }

    #[test]
    fn keys_go_both_ways() {
        for isa in Isa::ALL {
            assert_eq!(Isa::from_key(isa.key()), Some(isa));
        }
        assert_eq!(Isa::from_key("mmx"), None);
    }
}
