//! A path tracer whose result is checked bit by bit.
//!
//! The picture is cut into tiles, and a tile at one pass is a unit of work
//! with a fingerprint that has to come out the same on every processor. For
//! that, the code that computes it only uses operations IEEE 754 rounds
//! exactly, in one fixed order, whatever instructions carry them out.

pub mod bvh;
pub mod film;
pub mod math;
pub mod scene;
mod simd;
pub mod trace;

use crate::memory::kernels::Isa;

/// The instructions a unit is rendered with. The first three give the same
/// bits; fusing gives others, and is here only to be measured.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Kernel {
    /// Plain floats, one lane after another: the reference.
    Portable,
    Sse2,
    Avx2,
    /// AVX2 rounding a product and a sum once. Other results.
    Avx2Fused,
}

impl Kernel {
    pub const ALL: [Kernel; 4] = [
        Kernel::Portable,
        Kernel::Sse2,
        Kernel::Avx2,
        Kernel::Avx2Fused,
    ];
    /// The ones that have to agree.
    pub const EXACT: [Kernel; 3] = [Kernel::Portable, Kernel::Sse2, Kernel::Avx2];

    pub fn key(self) -> &'static str {
        match self {
            Kernel::Portable => "portable",
            Kernel::Sse2 => "sse2",
            Kernel::Avx2 => "avx2",
            Kernel::Avx2Fused => "avx2-fused",
        }
    }

    pub fn from_key(key: &str) -> Option<Kernel> {
        Kernel::ALL.into_iter().find(|kernel| kernel.key() == key)
    }

    /// Whether this processor runs it, asked at run time.
    pub fn is_available(self) -> bool {
        match self {
            Kernel::Portable => true,
            Kernel::Sse2 => Isa::Sse2.is_available(),
            Kernel::Avx2 => Isa::Avx2.is_available(),
            #[cfg(target_arch = "x86_64")]
            Kernel::Avx2Fused => {
                Isa::Avx2.is_available() && std::arch::is_x86_feature_detected!("fma")
            }
            #[cfg(not(target_arch = "x86_64"))]
            Kernel::Avx2Fused => false,
        }
    }

    /// The kernel for an instruction set. Nothing here is wider than AVX2
    /// yet, so AVX-512 gets that one.
    pub fn for_isa(isa: Isa) -> Kernel {
        match isa {
            Isa::Portable => Kernel::Portable,
            Isa::Sse2 => Kernel::Sse2,
            Isa::Avx2 | Isa::Avx512 => Kernel::Avx2,
        }
    }

    /// The widest exact kernel this processor runs: what a run uses unless
    /// told otherwise.
    pub fn widest() -> Kernel {
        Kernel::for_isa(Isa::widest())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn keys_go_both_ways() {
        for kernel in Kernel::ALL {
            assert_eq!(Kernel::from_key(kernel.key()), Some(kernel));
        }
        assert_eq!(Kernel::from_key("avx512"), None);
    }

    #[test]
    fn the_widest_is_exact_and_runs_here() {
        let widest = Kernel::widest();
        assert!(widest.is_available());
        assert!(Kernel::EXACT.contains(&widest));
        assert_eq!(Kernel::for_isa(Isa::Avx512), Kernel::Avx2);
        assert!(Kernel::Portable.is_available());
    }
}
