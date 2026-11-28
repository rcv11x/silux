//! Vectors, and the few functions the renderer needs beyond the five
//! operations IEEE 754 rounds exactly.
//!
//! Nothing here calls the system's maths library. Its `sin`, `cos` and
//! `floor` change with the C library and with the processor it picks a route
//! for, and a fingerprint has to come out the same everywhere. What isn't a
//! correctly rounded operation is built here from those that are, always in
//! the same order.

use std::ops::{Add, Mul, Neg, Sub};

#[derive(Debug, Clone, Copy, PartialEq, Default)]
pub struct Vec3 {
    pub x: f32,
    pub y: f32,
    pub z: f32,
}

#[inline(always)]
pub const fn vec3(x: f32, y: f32, z: f32) -> Vec3 {
    Vec3 { x, y, z }
}

impl Vec3 {
    pub const ZERO: Vec3 = vec3(0.0, 0.0, 0.0);

    #[inline(always)]
    pub const fn splat(value: f32) -> Vec3 {
        vec3(value, value, value)
    }

    #[inline(always)]
    pub fn dot(self, other: Vec3) -> f32 {
        self.x * other.x + self.y * other.y + self.z * other.z
    }

    #[inline(always)]
    pub fn cross(self, other: Vec3) -> Vec3 {
        vec3(
            self.y * other.z - self.z * other.y,
            self.z * other.x - self.x * other.z,
            self.x * other.y - self.y * other.x,
        )
    }

    #[inline(always)]
    pub fn length(self) -> f32 {
        self.dot(self).sqrt()
    }

    #[inline(always)]
    pub fn normalized(self) -> Vec3 {
        self * (1.0 / self.length())
    }

    #[inline(always)]
    pub fn max_component(self) -> f32 {
        larger(self.x, larger(self.y, self.z))
    }

    #[inline(always)]
    pub fn min_each(self, other: Vec3) -> Vec3 {
        vec3(
            smaller(self.x, other.x),
            smaller(self.y, other.y),
            smaller(self.z, other.z),
        )
    }

    #[inline(always)]
    pub fn max_each(self, other: Vec3) -> Vec3 {
        vec3(
            larger(self.x, other.x),
            larger(self.y, other.y),
            larger(self.z, other.z),
        )
    }
}

/// The second when either isn't a number, as the vector instructions do.
#[inline(always)]
pub fn smaller(a: f32, b: f32) -> f32 {
    if a < b {
        a
    } else {
        b
    }
}

/// The second when either isn't a number, as the vector instructions do.
#[inline(always)]
pub fn larger(a: f32, b: f32) -> f32 {
    if a > b {
        a
    } else {
        b
    }
}

impl Add for Vec3 {
    type Output = Vec3;
    #[inline(always)]
    fn add(self, other: Vec3) -> Vec3 {
        vec3(self.x + other.x, self.y + other.y, self.z + other.z)
    }
}

impl Sub for Vec3 {
    type Output = Vec3;
    #[inline(always)]
    fn sub(self, other: Vec3) -> Vec3 {
        vec3(self.x - other.x, self.y - other.y, self.z - other.z)
    }
}

impl Neg for Vec3 {
    type Output = Vec3;
    #[inline(always)]
    fn neg(self) -> Vec3 {
        vec3(-self.x, -self.y, -self.z)
    }
}

impl Mul<f32> for Vec3 {
    type Output = Vec3;
    #[inline(always)]
    fn mul(self, factor: f32) -> Vec3 {
        vec3(self.x * factor, self.y * factor, self.z * factor)
    }
}

impl Mul<Vec3> for Vec3 {
    type Output = Vec3;
    #[inline(always)]
    fn mul(self, other: Vec3) -> Vec3 {
        vec3(self.x * other.x, self.y * other.y, self.z * other.z)
    }
}

/// The largest whole number not above `x`, for what fits an `i32`. A
/// conversion and a comparison: before SSE4.1 the standard `floor` is a call
/// into libm.
#[inline(always)]
pub fn floor_i32(x: f32) -> i32 {
    let whole = x as i32;
    if (whole as f32) > x {
        whole.wrapping_sub(1)
    } else {
        whole
    }
}

/// 24 random bits as a number in `0..1`: every value is exact.
#[inline(always)]
pub fn unit_f32(bits: u64) -> f32 {
    ((bits >> 40) as f32) * (1.0 / 16_777_216.0)
}

const QUARTER_TURN: f32 = std::f32::consts::FRAC_PI_2;
// Taylor terms: on a quarter of a quarter turn either side of zero the next
// one is below the last bit of a float.
const S3: f32 = -1.0 / 6.0;
const S5: f32 = 1.0 / 120.0;
const S7: f32 = -1.0 / 5040.0;
const S9: f32 = 1.0 / 362_880.0;
const C2: f32 = -1.0 / 2.0;
const C4: f32 = 1.0 / 24.0;
const C6: f32 = -1.0 / 720.0;
const C8: f32 = 1.0 / 40_320.0;
const C10: f32 = -1.0 / 3_628_800.0;

/// Sine and cosine of `turns` whole turns: 0.25 is a right angle. The angle
/// is brought to the nearest quarter turn and two short polynomials do the
/// rest, with products and sums only.
#[inline(always)]
pub fn sin_cos_turns(turns: f32) -> (f32, f32) {
    let quarters = turns * 4.0;
    let nearest = floor_i32(quarters + 0.5);
    let x = (quarters - nearest as f32) * QUARTER_TURN;
    let x2 = x * x;
    let sin = x * (1.0 + x2 * (S3 + x2 * (S5 + x2 * (S7 + x2 * S9))));
    let cos = 1.0 + x2 * (C2 + x2 * (C4 + x2 * (C6 + x2 * (C8 + x2 * C10))));
    match nearest & 3 {
        0 => (sin, cos),
        1 => (cos, -sin),
        2 => (-sin, -cos),
        _ => (-cos, sin),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn sine_and_cosine_match_the_library_closely() {
        let mut worst = 0.0f64;
        for step in -4000..=8000 {
            let turns = step as f32 / 4000.0;
            let (sin, cos) = sin_cos_turns(turns);
            let angle = f64::from(turns) * std::f64::consts::TAU;
            worst = worst
                .max((f64::from(sin) - angle.sin()).abs())
                .max((f64::from(cos) - angle.cos()).abs());
        }
        // A float's own rounding of the angle is the floor here.
        assert!(worst < 2e-6, "{worst}");
    }

    #[test]
    fn the_quarter_turns_are_exact() {
        assert_eq!(sin_cos_turns(0.0), (0.0, 1.0));
        assert_eq!(sin_cos_turns(0.25), (1.0, -0.0));
        assert_eq!(sin_cos_turns(0.5), (-0.0, -1.0));
        assert_eq!(sin_cos_turns(0.75), (-1.0, 0.0));
        assert_eq!(sin_cos_turns(-0.25), (-1.0, 0.0));
    }

    #[test]
    fn floor_goes_down_on_both_sides_of_zero() {
        for (x, whole) in [
            (0.0, 0),
            (0.99, 0),
            (1.0, 1),
            (-0.01, -1),
            (-1.0, -1),
            (-1.5, -2),
            (7.25, 7),
        ] {
            assert_eq!(floor_i32(x), whole, "{x}");
            assert_eq!(floor_i32(x), x.floor() as i32, "{x}");
        }
    }

    #[test]
    fn a_unit_float_stays_below_one() {
        assert_eq!(unit_f32(0), 0.0);
        assert!(unit_f32(u64::MAX) < 1.0);
        assert_eq!(unit_f32(1 << 63), 0.5);
    }

    #[test]
    fn the_smaller_and_the_larger_take_the_second_for_a_nan() {
        assert_eq!(smaller(f32::NAN, 3.0), 3.0);
        assert!(smaller(3.0, f32::NAN).is_nan());
        assert_eq!(larger(f32::NAN, 3.0), 3.0);
        assert_eq!(smaller(1.0, 2.0), 1.0);
        assert_eq!(larger(1.0, 2.0), 2.0);
    }

    #[test]
    fn cross_is_perpendicular_to_both() {
        let (a, b) = (vec3(1.0, 2.0, 3.0), vec3(-2.0, 0.5, 4.0));
        let c = a.cross(b);
        assert_eq!(c.dot(a), 0.0);
        assert_eq!(c.dot(b), 0.0);
        assert_eq!(
            vec3(1.0, 0.0, 0.0).cross(vec3(0.0, 1.0, 0.0)),
            vec3(0.0, 0.0, 1.0)
        );
    }
}
