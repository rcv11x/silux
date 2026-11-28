//! The picture as units of work: a tile of it at one pass, the sums that
//! unit must produce, and their fingerprint.
//!
//! Passes double: the first two add one sample to every pixel, the third
//! two, the fourth four. Every sample has its own seed, from its pixel and
//! its number, so which thread renders a unit, and when, doesn't change what
//! comes out.

use super::math::{unit_f32, Vec3};
use super::scene::Scene;
#[cfg(target_arch = "x86_64")]
use super::simd::{Avx2, Avx2Fused, Sse2};
use super::simd::{Lanes, Portable};
use super::trace::{radiance, Counters, Scratch};
use super::Kernel;
use crate::common::error::{Error, Result};
use crate::common::hash::{mix, of_floats};
use crate::common::rng::Rng;

/// Past this a pass alone is millions of samples per pixel.
pub const MAX_PASSES: u32 = 24;
const SEED: u64 = 0x5111_0C5E_5EED_0001;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct Layout {
    pub width: u32,
    pub height: u32,
    /// The side of a tile, in pixels. Those on the right and bottom edges
    /// are cut where the picture ends.
    pub tile: u32,
}

impl Layout {
    pub const FULL: Layout = Layout {
        width: 1280,
        height: 720,
        tile: 40,
    };

    pub fn columns(&self) -> u32 {
        self.width.div_ceil(self.tile.max(1))
    }

    pub fn rows(&self) -> u32 {
        self.height.div_ceil(self.tile.max(1))
    }

    pub fn tiles(&self) -> u32 {
        self.columns() * self.rows()
    }

    /// A tile's left, top, width and height.
    pub fn rect(&self, tile: u32) -> Option<(u32, u32, u32, u32)> {
        if self.tile == 0 || tile >= self.tiles() {
            return None;
        }
        let left = (tile % self.columns()) * self.tile;
        let top = (tile / self.columns()) * self.tile;
        Some((
            left,
            top,
            self.tile.min(self.width - left),
            self.tile.min(self.height - top),
        ))
    }

    /// How many floats a tile's sums are: three per pixel.
    pub fn floats(&self, tile: u32) -> Option<usize> {
        let (_, _, width, height) = self.rect(tile)?;
        Some(width as usize * height as usize * 3)
    }
}

/// The first sample a pass adds to each pixel, and how many.
pub fn pass_samples(pass: u32) -> (u32, u32) {
    match pass {
        0 => (0, 1),
        _ => (1 << (pass - 1), 1 << (pass - 1)),
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct Unit {
    pub pass: u32,
    pub tile: u32,
}

struct Job<'a> {
    scene: &'a Scene,
    layout: Layout,
    unit: Unit,
}

/// A path's light if every part of it is a finite number. What isn't a
/// number has no bits of its own: its sign and payload depend on who made it
/// and on the order two of them met, which a compiler may change. So none
/// reaches a sum, and whether a value is one is the same everywhere.
#[inline(always)]
fn finite(light: Vec3) -> Option<Vec3> {
    (light.x.is_finite() && light.y.is_finite() && light.z.is_finite()).then_some(light)
}

/// The unit's sums, pixel by pixel: every sample of the pass, added in
/// order.
///
/// # Safety
/// The processor runs `L`'s instructions.
#[inline(always)]
unsafe fn render<L: Lanes>(job: &Job, scratch: &mut Scratch, sums: &mut [f32]) -> Counters {
    let mut counters = Counters::default();
    let Some((left, top, width, height)) = job.layout.rect(job.unit.tile) else {
        return counters;
    };
    let (first, count) = pass_samples(job.unit.pass);
    let (across, down) = (
        1.0 / job.layout.width as f32,
        1.0 / job.layout.height as f32,
    );
    let mut pixels = sums.chunks_exact_mut(3);
    for y in top..top + height {
        for x in left..left + width {
            let Some([red, green, blue]) = pixels.next() else {
                return counters;
            };
            let pixel = u64::from(y) * u64::from(job.layout.width) + u64::from(x);
            let mut sum = Vec3::ZERO;
            for sample in first..first + count {
                let mut rng = Rng::new(mix((pixel << 32 | u64::from(sample)) ^ SEED));
                let (dx, dy) = (unit_f32(rng.next_u64()), unit_f32(rng.next_u64()));
                let (origin, direction) = job
                    .scene
                    .camera
                    .ray((x as f32 + dx) * across, (y as f32 + dy) * down);
                // SAFETY: the caller's guarantee.
                let light = unsafe {
                    radiance::<L>(
                        job.scene,
                        origin,
                        direction,
                        &mut rng,
                        scratch,
                        &mut counters,
                    )
                };
                match finite(light) {
                    Some(light) => sum = sum + light,
                    None => counters.strays += 1,
                }
                counters.paths += 1;
            }
            (*red, *green, *blue) = (sum.x, sum.y, sum.z);
        }
    }
    counters
}

fn render_unit_portable(job: &Job, scratch: &mut Scratch, sums: &mut [f32]) -> Counters {
    // SAFETY: the portable lanes are plain floats.
    unsafe { render::<Portable>(job, scratch, sums) }
}

#[cfg(target_arch = "x86_64")]
#[target_feature(enable = "sse2")]
fn render_unit_sse2(job: &Job, scratch: &mut Scratch, sums: &mut [f32]) -> Counters {
    // SAFETY: SSE2 is part of x86-64.
    unsafe { render::<Sse2>(job, scratch, sums) }
}

#[cfg(target_arch = "x86_64")]
#[target_feature(enable = "avx2")]
fn render_unit_avx2(job: &Job, scratch: &mut Scratch, sums: &mut [f32]) -> Counters {
    // SAFETY: this function is compiled for AVX2 and only called where the
    // processor has it.
    unsafe { render::<Avx2>(job, scratch, sums) }
}

#[cfg(target_arch = "x86_64")]
#[target_feature(enable = "avx2,fma")]
fn render_unit_avx2_fused(job: &Job, scratch: &mut Scratch, sums: &mut [f32]) -> Counters {
    // SAFETY: this function is compiled for AVX2 and FMA and only called
    // where the processor has both.
    unsafe { render::<Avx2Fused>(job, scratch, sums) }
}

/// Render one unit into `sums`, which has to be exactly its size
/// (`Layout::floats`). What comes back is the work it took.
pub fn render_unit(
    kernel: Kernel,
    scene: &Scene,
    layout: Layout,
    unit: Unit,
    scratch: &mut Scratch,
    sums: &mut [f32],
) -> Result<Counters> {
    if unit.pass >= MAX_PASSES {
        return Err(Error::BadSetting("pass"));
    }
    if layout.floats(unit.tile) != Some(sums.len()) {
        return Err(Error::BadSetting("tile"));
    }
    if !kernel.is_available() {
        return Err(Error::BadSetting("kernel"));
    }
    let job = Job {
        scene,
        layout,
        unit,
    };
    scratch.overflowed = false;
    let counters = match kernel {
        Kernel::Portable => render_unit_portable(&job, scratch, sums),
        #[cfg(target_arch = "x86_64")]
        // SAFETY: SSE2 is part of x86-64.
        Kernel::Sse2 => unsafe { render_unit_sse2(&job, scratch, sums) },
        #[cfg(target_arch = "x86_64")]
        // SAFETY: `is_available` just said the processor has AVX2.
        Kernel::Avx2 => unsafe { render_unit_avx2(&job, scratch, sums) },
        #[cfg(target_arch = "x86_64")]
        // SAFETY: `is_available` just said the processor has AVX2 and FMA.
        Kernel::Avx2Fused => unsafe { render_unit_avx2_fused(&job, scratch, sums) },
        #[cfg(not(target_arch = "x86_64"))]
        _ => return Err(Error::BadSetting("kernel")),
    };
    if scratch.overflowed {
        return Err(Error::Internal(
            "render: the walk's stack overflowed".to_owned(),
        ));
    }
    Ok(counters)
}

/// What a unit's sums have to be, as one number.
pub fn fingerprint(sums: &[f32]) -> u64 {
    of_floats(sums)
}

/// A pixel's colour for the screen, from one channel's sum over `samples`.
/// Only for looking at: it is no part of any fingerprint.
pub fn to_screen(sum: f32, samples: u32) -> u8 {
    let light = sum / samples.max(1) as f32;
    let light = if light > 0.0 { light } else { 0.0 };
    // Bright light is squeezed below one, and the square root stands in for
    // the screen's curve.
    let shown = (light / (1.0 + light)).sqrt();
    (shown * 255.0 + 0.5) as u8
}

#[cfg(test)]
pub(crate) mod tests {
    use super::*;
    use crate::cpu::render::scene::prototype;

    pub(crate) const SMALL: Layout = Layout {
        width: 96,
        height: 54,
        tile: 16,
    };

    /// Every unit of the first `passes` passes, as fingerprints and work.
    pub(crate) fn table(kernel: Kernel, scene: &Scene, passes: u32) -> Vec<(u64, Counters)> {
        let mut scratch = Scratch::default();
        let mut out = Vec::new();
        for pass in 0..passes {
            for tile in 0..SMALL.tiles() {
                let mut sums = vec![0.0; SMALL.floats(tile).unwrap()];
                let unit = Unit { pass, tile };
                let counters =
                    render_unit(kernel, scene, SMALL, unit, &mut scratch, &mut sums).unwrap();
                assert!(sums.iter().all(|sum| sum.is_finite() && *sum >= 0.0));
                out.push((fingerprint(&sums), counters));
            }
        }
        out
    }

    #[test]
    fn tiles_cover_the_picture_once() {
        for layout in [Layout::FULL, SMALL] {
            let mut covered = vec![0u8; (layout.width * layout.height) as usize];
            for tile in 0..layout.tiles() {
                let (left, top, width, height) = layout.rect(tile).unwrap();
                assert_eq!(layout.floats(tile), Some((width * height * 3) as usize));
                for y in top..top + height {
                    for x in left..left + width {
                        covered[(y * layout.width + x) as usize] += 1;
                    }
                }
            }
            assert!(covered.iter().all(|times| *times == 1));
            assert_eq!(layout.rect(layout.tiles()), None);
        }
        assert_eq!(Layout::FULL.tiles(), 576);
        // 54 rows in tiles of 16: the last row of tiles is 6 pixels high.
        assert_eq!(SMALL.rect(SMALL.tiles() - 1), Some((80, 48, 16, 6)));
    }

    #[test]
    fn each_pass_doubles_the_samples_so_far() {
        let mut so_far = 0;
        for pass in 0..12 {
            let (first, count) = pass_samples(pass);
            assert_eq!(first, so_far);
            so_far += count;
            assert_eq!(so_far, 1 << pass);
        }
    }

    /// The question the whole design rests on: every exact kernel this
    /// processor runs gives the same bits, and does the same work.
    #[test]
    fn every_exact_kernel_gives_the_same_bits() {
        let scene = prototype(0).unwrap();
        let reference = table(Kernel::Portable, &scene, 3);
        let mut compared = 0;
        for kernel in Kernel::EXACT {
            if kernel.is_available() {
                assert_eq!(table(kernel, &scene, 3), reference, "{kernel:?}");
                compared += 1;
            }
        }
        assert!(compared >= 1);
        // The picture isn't flat: units differ from one another.
        let mut distinct: Vec<u64> = reference.iter().map(|(print, _)| *print).collect();
        distinct.sort_unstable();
        distinct.dedup();
        assert_eq!(distinct.len(), reference.len());
    }

    /// The same bits on every machine, not only between kernels on one:
    /// these were taken on a Ryzen 7 5800X3D. A processor that rounds
    /// anything differently, or a compiler that reorders a sum, fails here.
    #[test]
    fn the_bits_are_the_ones_pinned() {
        let scene = prototype(0).unwrap();
        let mut all = crate::common::hash::Fingerprint::default();
        let mut work = Counters::default();
        for (print, counters) in table(Kernel::widest(), &scene, 3) {
            all.word(print);
            work.add(counters);
        }
        assert_eq!(all.finish(), 0xB77D_D72E_C92D_8B91);
        // The work is the same too: it is what the units weigh.
        assert_eq!(
            (work.paths, work.rays, work.nodes, work.leaves, work.strays),
            (20_736, 49_832, 389_047, 308_339, 0)
        );
    }

    /// The comparison above can fail: one rounding less per product and sum
    /// in the walk is enough to change some units, and leaves others as
    /// they were.
    #[test]
    fn fusing_gives_other_bits() {
        if !Kernel::Avx2Fused.is_available() {
            return;
        }
        let scene = prototype(0).unwrap();
        let exact = table(Kernel::Avx2, &scene, 2);
        let fused = table(Kernel::Avx2Fused, &scene, 2);
        let differ = exact.iter().zip(&fused).filter(|(a, b)| a.0 != b.0).count();
        assert!(differ > 0);
        assert!(differ < exact.len());
    }

    #[test]
    fn light_that_isnt_a_finite_number_is_no_light() {
        let good = Vec3 {
            x: 0.5,
            y: 0.0,
            z: 3.0,
        };
        assert_eq!(finite(good), Some(good));
        for bad in [f32::NAN, -f32::NAN, f32::INFINITY, f32::NEG_INFINITY] {
            assert_eq!(finite(Vec3 { x: bad, ..good }), None);
            assert_eq!(finite(Vec3 { y: bad, ..good }), None);
            assert_eq!(finite(Vec3 { z: bad, ..good }), None);
        }
    }

    #[test]
    fn a_unit_doesnt_depend_on_what_was_rendered_before() {
        let scene = prototype(0).unwrap();
        let unit = Unit { pass: 2, tile: 7 };
        let mut sums = vec![0.0; SMALL.floats(7).unwrap()];
        let mut fresh = Scratch::default();
        let kernel = Kernel::widest();
        let alone = render_unit(kernel, &scene, SMALL, unit, &mut fresh, &mut sums).unwrap();
        let alone = (fingerprint(&sums), alone);
        // After other units, with a used scratch and stale sums.
        let mut used = Scratch::default();
        for tile in [3, 11, 0] {
            let mut other = vec![0.0; SMALL.floats(tile).unwrap()];
            let unit = Unit { pass: 1, tile };
            render_unit(kernel, &scene, SMALL, unit, &mut used, &mut other).unwrap();
        }
        sums.fill(123.0);
        let after = render_unit(kernel, &scene, SMALL, unit, &mut used, &mut sums).unwrap();
        assert_eq!((fingerprint(&sums), after), alone);
    }

    #[test]
    fn what_cant_be_rendered_is_refused() {
        let scene = prototype(0).unwrap();
        let mut scratch = Scratch::default();
        let mut sums = vec![0.0; SMALL.floats(0).unwrap()];
        let mut refused = |unit: Unit, sums: &mut [f32]| {
            render_unit(Kernel::Portable, &scene, SMALL, unit, &mut scratch, sums)
        };
        let past = Unit {
            pass: 0,
            tile: SMALL.tiles(),
        };
        assert_eq!(refused(past, &mut sums), Err(Error::BadSetting("tile")));
        let deep = Unit {
            pass: MAX_PASSES,
            tile: 0,
        };
        assert_eq!(refused(deep, &mut sums), Err(Error::BadSetting("pass")));
        let unit = Unit { pass: 0, tile: 0 };
        assert_eq!(
            refused(unit, &mut sums[1..]),
            Err(Error::BadSetting("tile"))
        );
    }

    #[test]
    fn the_screen_colour_is_dark_for_nothing_and_never_wraps() {
        assert_eq!(to_screen(0.0, 4), 0);
        assert_eq!(to_screen(-1.0, 4), 0);
        assert_eq!(to_screen(f32::NAN, 4), 0);
        assert_eq!(to_screen(1e30, 1), 255);
        assert!(to_screen(4.0, 4) > to_screen(2.0, 4));
        assert_eq!(to_screen(8.0, 8), to_screen(1.0, 1));
    }
}
