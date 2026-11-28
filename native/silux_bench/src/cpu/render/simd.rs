//! Eight single-precision lanes at a time, once per instruction tier.
//!
//! Every operation works lane by lane and is one IEEE 754 rounds exactly, or
//! a comparison, so each lane ends with the bits it would have computed
//! alone: the width of the registers doesn't show in the result. `min` and
//! `max` follow the x86 rule in every tier, the second operand when either
//! isn't a number.
//!
//! The one exception is `Avx2Fused`, which rounds a product and a sum once
//! instead of twice. Its results are another class, there to measure what
//! fusing would buy.
//!
//! # Safety
//! Every method is unsafe for one reason: the processor has to run that
//! tier's instructions. `Kernel::is_available` is what says so.

#[cfg(target_arch = "x86_64")]
use std::arch::x86_64::*;

use super::math::{larger, smaller};

pub(super) trait Lanes {
    type F: Copy;
    /// A lane-wide yes or no, as a comparison leaves it.
    type M: Copy;

    unsafe fn splat(value: f32) -> Self::F;
    unsafe fn load(from: &[f32; 8]) -> Self::F;
    unsafe fn store(value: Self::F, to: &mut [f32; 8]);
    unsafe fn add(a: Self::F, b: Self::F) -> Self::F;
    unsafe fn sub(a: Self::F, b: Self::F) -> Self::F;
    unsafe fn mul(a: Self::F, b: Self::F) -> Self::F;
    unsafe fn div(a: Self::F, b: Self::F) -> Self::F;
    unsafe fn min(a: Self::F, b: Self::F) -> Self::F;
    unsafe fn max(a: Self::F, b: Self::F) -> Self::F;
    unsafe fn le(a: Self::F, b: Self::F) -> Self::M;
    unsafe fn lt(a: Self::F, b: Self::F) -> Self::M;
    unsafe fn both(a: Self::M, b: Self::M) -> Self::M;
    /// One bit per lane, lane 0 lowest.
    unsafe fn bits(mask: Self::M) -> u32;

    /// `a * b + c`.
    #[inline(always)]
    unsafe fn mul_add(a: Self::F, b: Self::F, c: Self::F) -> Self::F {
        // SAFETY: the caller's guarantee is this trait's.
        unsafe { Self::add(Self::mul(a, b), c) }
    }

    /// `a * b - c`.
    #[inline(always)]
    unsafe fn mul_sub(a: Self::F, b: Self::F, c: Self::F) -> Self::F {
        // SAFETY: the caller's guarantee is this trait's.
        unsafe { Self::sub(Self::mul(a, b), c) }
    }

    /// Where a ray crosses a plane: `(plane - origin) * inverse`.
    /// `origin_inverse` is their product, for the tier that fuses.
    #[inline(always)]
    unsafe fn slab(
        plane: Self::F,
        origin: Self::F,
        inverse: Self::F,
        _origin_inverse: Self::F,
    ) -> Self::F {
        // SAFETY: the caller's guarantee is this trait's.
        unsafe { Self::mul(Self::sub(plane, origin), inverse) }
    }
}

/// Plain floats, one lane after another: any processor, and the reference
/// the vector tiers are compared with.
pub(super) struct Portable;

#[inline(always)]
fn each(a: [f32; 8], b: [f32; 8], op: impl Fn(f32, f32) -> f32) -> [f32; 8] {
    let mut out = [0.0; 8];
    for ((out, a), b) in out.iter_mut().zip(a).zip(b) {
        *out = op(a, b);
    }
    out
}

#[inline(always)]
fn which(a: [f32; 8], b: [f32; 8], test: impl Fn(f32, f32) -> bool) -> u32 {
    let mut bits = 0;
    for (lane, (a, b)) in a.into_iter().zip(b).enumerate() {
        if test(a, b) {
            bits |= 1 << lane;
        }
    }
    bits
}

impl Lanes for Portable {
    type F = [f32; 8];
    type M = u32;

    #[inline(always)]
    unsafe fn splat(value: f32) -> Self::F {
        [value; 8]
    }
    #[inline(always)]
    unsafe fn load(from: &[f32; 8]) -> Self::F {
        *from
    }
    #[inline(always)]
    unsafe fn store(value: Self::F, to: &mut [f32; 8]) {
        *to = value;
    }
    #[inline(always)]
    unsafe fn add(a: Self::F, b: Self::F) -> Self::F {
        each(a, b, |a, b| a + b)
    }
    #[inline(always)]
    unsafe fn sub(a: Self::F, b: Self::F) -> Self::F {
        each(a, b, |a, b| a - b)
    }
    #[inline(always)]
    unsafe fn mul(a: Self::F, b: Self::F) -> Self::F {
        each(a, b, |a, b| a * b)
    }
    #[inline(always)]
    unsafe fn div(a: Self::F, b: Self::F) -> Self::F {
        each(a, b, |a, b| a / b)
    }
    #[inline(always)]
    unsafe fn min(a: Self::F, b: Self::F) -> Self::F {
        each(a, b, smaller)
    }
    #[inline(always)]
    unsafe fn max(a: Self::F, b: Self::F) -> Self::F {
        each(a, b, larger)
    }
    #[inline(always)]
    unsafe fn le(a: Self::F, b: Self::F) -> Self::M {
        which(a, b, |a, b| a <= b)
    }
    #[inline(always)]
    unsafe fn lt(a: Self::F, b: Self::F) -> Self::M {
        which(a, b, |a, b| a < b)
    }
    #[inline(always)]
    unsafe fn both(a: Self::M, b: Self::M) -> Self::M {
        a & b
    }
    #[inline(always)]
    unsafe fn bits(mask: Self::M) -> u32 {
        mask
    }
}

/// Two registers of four lanes: every x86-64 processor.
#[cfg(target_arch = "x86_64")]
pub(super) struct Sse2;

#[cfg(target_arch = "x86_64")]
macro_rules! sse2_pairs {
    ($($name:ident -> $out:ident = $op:ident;)*) => {$(
        #[inline]
        #[target_feature(enable = "sse2")]
        unsafe fn $name(a: Self::F, b: Self::F) -> Self::$out {
            let ([a0, a1], [b0, b1]) = (a, b);
            [$op(a0, b0), $op(a1, b1)]
        }
    )*};
}

#[cfg(target_arch = "x86_64")]
impl Lanes for Sse2 {
    type F = [__m128; 2];
    type M = [__m128; 2];

    #[inline]
    #[target_feature(enable = "sse2")]
    unsafe fn splat(value: f32) -> Self::F {
        let lanes = _mm_set1_ps(value);
        [lanes, lanes]
    }
    #[inline]
    #[target_feature(enable = "sse2")]
    unsafe fn load(from: &[f32; 8]) -> Self::F {
        let first = from.as_ptr();
        // SAFETY: `from` is eight floats: four from its start and four from
        // its middle. Neither load asks for alignment.
        unsafe { [_mm_loadu_ps(first), _mm_loadu_ps(first.add(4))] }
    }
    #[inline]
    #[target_feature(enable = "sse2")]
    unsafe fn store(value: Self::F, to: &mut [f32; 8]) {
        let [low, high] = value;
        let first = to.as_mut_ptr();
        // SAFETY: `to` is eight writable floats, filled in two halves.
        unsafe {
            _mm_storeu_ps(first, low);
            _mm_storeu_ps(first.add(4), high);
        }
    }
    sse2_pairs! {
        add -> F = _mm_add_ps;
        sub -> F = _mm_sub_ps;
        mul -> F = _mm_mul_ps;
        div -> F = _mm_div_ps;
        min -> F = _mm_min_ps;
        max -> F = _mm_max_ps;
        le -> M = _mm_cmple_ps;
        lt -> M = _mm_cmplt_ps;
        both -> M = _mm_and_ps;
    }
    #[inline]
    #[target_feature(enable = "sse2")]
    unsafe fn bits(mask: Self::M) -> u32 {
        let [low, high] = mask;
        (_mm_movemask_ps(low) as u32) | ((_mm_movemask_ps(high) as u32) << 4)
    }
}

/// The methods the two 256-bit tiers share, each compiled for `$features`.
#[cfg(target_arch = "x86_64")]
macro_rules! avx_lanes {
    ($features:literal) => {
        type F = __m256;
        type M = __m256;

        #[inline]
        #[target_feature(enable = $features)]
        unsafe fn splat(value: f32) -> Self::F {
            _mm256_set1_ps(value)
        }
        #[inline]
        #[target_feature(enable = $features)]
        unsafe fn load(from: &[f32; 8]) -> Self::F {
            // SAFETY: `from` is eight floats, and the load asks for no
            // alignment.
            unsafe { _mm256_loadu_ps(from.as_ptr()) }
        }
        #[inline]
        #[target_feature(enable = $features)]
        unsafe fn store(value: Self::F, to: &mut [f32; 8]) {
            // SAFETY: `to` is eight writable floats.
            unsafe { _mm256_storeu_ps(to.as_mut_ptr(), value) }
        }
        avx_lanes!(@pairs $features;
            add -> F = _mm256_add_ps;
            sub -> F = _mm256_sub_ps;
            mul -> F = _mm256_mul_ps;
            div -> F = _mm256_div_ps;
            min -> F = _mm256_min_ps;
            max -> F = _mm256_max_ps;
            both -> M = _mm256_and_ps;
        );
        #[inline]
        #[target_feature(enable = $features)]
        unsafe fn le(a: Self::F, b: Self::F) -> Self::M {
            _mm256_cmp_ps::<_CMP_LE_OQ>(a, b)
        }
        #[inline]
        #[target_feature(enable = $features)]
        unsafe fn lt(a: Self::F, b: Self::F) -> Self::M {
            _mm256_cmp_ps::<_CMP_LT_OQ>(a, b)
        }
        #[inline]
        #[target_feature(enable = $features)]
        unsafe fn bits(mask: Self::M) -> u32 {
            _mm256_movemask_ps(mask) as u32
        }
    };
    (@pairs $features:literal; $($name:ident -> $out:ident = $op:ident;)*) => {$(
        #[inline]
        #[target_feature(enable = $features)]
        unsafe fn $name(a: Self::F, b: Self::F) -> Self::$out {
            $op(a, b)
        }
    )*};
}

/// One register of eight lanes, and no fused operations: the same results
/// as `Sse2`.
#[cfg(target_arch = "x86_64")]
pub(super) struct Avx2;

#[cfg(target_arch = "x86_64")]
impl Lanes for Avx2 {
    avx_lanes!("avx2");
}

/// As `Avx2`, rounding a product and a sum once where the code asks for
/// both: other results.
#[cfg(target_arch = "x86_64")]
pub(super) struct Avx2Fused;

#[cfg(target_arch = "x86_64")]
impl Lanes for Avx2Fused {
    avx_lanes!("avx2,fma");

    #[inline]
    #[target_feature(enable = "avx2,fma")]
    unsafe fn mul_add(a: Self::F, b: Self::F, c: Self::F) -> Self::F {
        _mm256_fmadd_ps(a, b, c)
    }
    #[inline]
    #[target_feature(enable = "avx2,fma")]
    unsafe fn mul_sub(a: Self::F, b: Self::F, c: Self::F) -> Self::F {
        _mm256_fmsub_ps(a, b, c)
    }
    #[inline]
    #[target_feature(enable = "avx2,fma")]
    unsafe fn slab(
        plane: Self::F,
        _origin: Self::F,
        inverse: Self::F,
        origin_inverse: Self::F,
    ) -> Self::F {
        _mm256_fmsub_ps(plane, inverse, origin_inverse)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    /// One bit above one: its square needs more bits than a float has.
    const NEXT_AFTER_ONE: f32 = 1.0 + f32::EPSILON;
    const A: [f32; 8] = [
        NEXT_AFTER_ONE,
        -2.0,
        0.0,
        1e-30,
        3.25,
        f32::NAN,
        f32::INFINITY,
        -0.0,
    ];
    const B: [f32; 8] = [-1.0, 7.0, -0.0, 3e30, 3.25, 1.0, f32::NEG_INFINITY, 0.0];
    const C: [f32; 8] = [NEXT_AFTER_ONE, 0.3, 1.0, -1e-3, 2.5, 2.0, 1.0, 5.0];

    /// A float's bits, with one pattern for everything that isn't a number.
    /// Which of them an operation gives isn't fixed: the processor makes
    /// one, the compiler folding the same operation makes another, and of
    /// two that meet the first operand's comes out. That it isn't a number
    /// is what every tier has to agree on.
    fn bits(value: f32) -> u32 {
        if value.is_nan() {
            f32::NAN.to_bits()
        } else {
            value.to_bits()
        }
    }

    /// Every operation on two awkward vectors, as bits.
    ///
    /// # Safety
    /// The processor runs `L`'s instructions.
    unsafe fn everything<L: Lanes>() -> Vec<u32> {
        // SAFETY: the caller's guarantee.
        unsafe {
            let (a, b) = (L::load(&A), L::load(&B));
            let mut out = Vec::new();
            let mut keep = |value: L::F| {
                let mut lanes = [0.0; 8];
                L::store(value, &mut lanes);
                out.extend(lanes.map(bits));
            };
            keep(L::add(a, b));
            keep(L::sub(a, b));
            keep(L::mul(a, b));
            keep(L::div(a, b));
            keep(L::min(a, b));
            keep(L::max(a, b));
            keep(L::min(b, a));
            keep(L::max(b, a));
            keep(L::splat(0.7));
            let masks = [
                L::bits(L::le(a, b)),
                L::bits(L::lt(a, b)),
                L::bits(L::both(L::le(a, b), L::le(b, a))),
            ];
            out.extend(masks);
            out
        }
    }

    /// As `everything`, for the three that a fusing tier rounds once.
    ///
    /// # Safety
    /// The processor runs `L`'s instructions.
    unsafe fn products_and_sums<L: Lanes>() -> Vec<u32> {
        // SAFETY: the caller's guarantee.
        unsafe {
            let (a, b, c) = (L::load(&A), L::load(&B), L::load(&C));
            let mut out = Vec::new();
            for value in [
                L::mul_add(a, c, b),
                L::mul_sub(a, c, b),
                L::slab(a, b, c, L::mul(b, c)),
            ] {
                let mut lanes = [0.0; 8];
                L::store(value, &mut lanes);
                out.extend(lanes.map(bits));
            }
            out
        }
    }

    #[test]
    fn the_portable_lanes_do_what_scalar_code_does() {
        // SAFETY: plain floats run anywhere.
        let got = unsafe { everything::<Portable>() };
        let sum: Vec<u32> = A.iter().zip(B).map(|(a, b)| bits(a + b)).collect();
        assert_eq!(got.get(..8), Some(sum.as_slice()));
        // The first is above -1; -2 <= 7; 0 <= -0; 1e-30 <= 3e30; 3.25 <= 3.25;
        // a NaN compares false; inf <= -inf is false; -0 <= 0.
        assert_eq!(got.get(72), Some(&0b1001_1110));
        assert_eq!(got.get(73), Some(&0b0000_1010));
        assert_eq!(got.get(74), Some(&0b1001_0100));
    }

    #[cfg(target_arch = "x86_64")]
    #[test]
    fn every_tier_gives_the_bits_of_the_portable_one() {
        // SAFETY: plain floats, and SSE2 is part of x86-64.
        let (portable, sse2) = unsafe { (everything::<Portable>(), everything::<Sse2>()) };
        assert_eq!(sse2, portable);
        // SAFETY: as above.
        let (portable, sse2) =
            unsafe { (products_and_sums::<Portable>(), products_and_sums::<Sse2>()) };
        assert_eq!(sse2, portable);
        if std::arch::is_x86_feature_detected!("avx2") {
            // SAFETY: the processor just said it has AVX2.
            let avx2 = unsafe { (everything::<Avx2>(), products_and_sums::<Avx2>()) };
            // SAFETY: as above.
            let portable = unsafe { (everything::<Portable>(), products_and_sums::<Portable>()) };
            assert_eq!(avx2, portable);
        }
    }

    /// The comparison above can fail: fusing changes the last bit of at
    /// least one of these lanes, and nothing else does.
    #[cfg(target_arch = "x86_64")]
    #[test]
    fn fusing_gives_other_bits_only_where_it_fuses() {
        if !(std::arch::is_x86_feature_detected!("avx2")
            && std::arch::is_x86_feature_detected!("fma"))
        {
            return;
        }
        // SAFETY: the processor just said it has AVX2 and FMA.
        let (plain, fused) = unsafe { (everything::<Avx2>(), everything::<Avx2Fused>()) };
        assert_eq!(fused, plain);
        // SAFETY: as above.
        let (plain, fused) = unsafe {
            (
                products_and_sums::<Avx2>(),
                products_and_sums::<Avx2Fused>(),
            )
        };
        assert_ne!(fused, plain);
    }
}
