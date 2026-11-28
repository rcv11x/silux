//! Following a ray: what it hits first, and the light a path brings back.
//!
//! Written once over `Lanes` and compiled once per tier. The result doesn't
//! depend on the order the tree is walked in: the nearest hit wins, between
//! two at the same distance the one with the lower number, and a box is only
//! skipped when it starts beyond the hit already found.

use super::bvh::{Bvh, EMPTY, LEAF, STACK, WIDTH};
use super::math::{floor_i32, sin_cos_turns, smaller, unit_f32, vec3, Vec3};
use super::scene::{Material, Scene};
use super::simd::Lanes;
use crate::common::rng::Rng;

/// The number of a ray's hit when it hit nothing.
pub const NO_HIT: u32 = u32::MAX;
/// A ray starts this far from where the last one ended, so it doesn't hit
/// the surface it leaves.
const START: f32 = 1e-3;
pub const MAX_BOUNCES: u32 = 12;
/// From this bounce on, a path that carries little light may end.
const ROULETTE_FROM: u32 = 3;

/// The work done, counted the same on every machine: it is what a unit
/// weighs.
#[derive(Debug, Clone, Copy, Default, PartialEq, Eq)]
pub struct Counters {
    /// Tree nodes whose eight boxes were tested.
    pub nodes: u64,
    /// Leaves whose eight triangles were tested.
    pub leaves: u64,
    pub rays: u64,
    pub paths: u64,
    /// Paths whose light wasn't a finite number, and counted as none.
    pub strays: u64,
}

impl Counters {
    pub fn add(&mut self, other: Counters) {
        self.nodes += other.nodes;
        self.leaves += other.leaves;
        self.rays += other.rays;
        self.paths += other.paths;
        self.strays += other.strays;
    }

    pub fn weight(&self) -> u64 {
        self.nodes + self.leaves
    }
}

/// What a thread keeps between rays, so none of it is set up per ray.
pub struct Scratch {
    /// Where each waiting child's box starts along the ray, and the child.
    stack: [(f32, u32); STACK],
    pub(super) overflowed: bool,
}

impl Default for Scratch {
    fn default() -> Self {
        Scratch {
            stack: [(0.0, EMPTY); STACK],
            overflowed: false,
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq)]
pub(super) struct Nearest {
    pub t: f32,
    pub prim: u32,
}

/// # Safety
/// The processor runs `L`'s instructions.
#[inline(always)]
unsafe fn dot<L: Lanes>(a: [L::F; 3], b: [L::F; 3]) -> L::F {
    let ([ax, ay, az], [bx, by, bz]) = (a, b);
    // SAFETY: the caller's guarantee.
    unsafe { L::mul_add(az, bz, L::mul_add(ay, by, L::mul(ax, bx))) }
}

/// # Safety
/// The processor runs `L`'s instructions.
#[inline(always)]
unsafe fn cross<L: Lanes>(a: [L::F; 3], b: [L::F; 3]) -> [L::F; 3] {
    let ([ax, ay, az], [bx, by, bz]) = (a, b);
    // SAFETY: the caller's guarantee.
    unsafe {
        [
            L::mul_sub(ay, bz, L::mul(az, by)),
            L::mul_sub(az, bx, L::mul(ax, bz)),
            L::mul_sub(ax, by, L::mul(ay, bx)),
        ]
    }
}

/// The nearest triangle along the ray that beats `nearest`. Triangles are
/// numbered from `first_triangle`.
///
/// # Safety
/// The processor runs `L`'s instructions.
#[inline(always)]
unsafe fn walk<L: Lanes>(
    bvh: &Bvh,
    origin: Vec3,
    direction: Vec3,
    first_triangle: u32,
    mut nearest: Nearest,
    scratch: &mut Scratch,
    counters: &mut Counters,
) -> Nearest {
    if bvh.root == EMPTY {
        return nearest;
    }
    let inverse = vec3(1.0 / direction.x, 1.0 / direction.y, 1.0 / direction.z);
    let scaled = origin * inverse;
    // The sign of the inverse, not of the direction: a zero that is negative
    // has to take the far plane first like any other negative.
    let backwards = [inverse.x < 0.0, inverse.y < 0.0, inverse.z < 0.0];
    let mut top = 0;
    if let Some(slot) = scratch.stack.get_mut(top) {
        *slot = (0.0, bvh.root);
        top += 1;
    }
    // SAFETY: the caller's guarantee covers every `L::` call below.
    unsafe {
        let o = [L::splat(origin.x), L::splat(origin.y), L::splat(origin.z)];
        let d = [
            L::splat(direction.x),
            L::splat(direction.y),
            L::splat(direction.z),
        ];
        let inv = [
            L::splat(inverse.x),
            L::splat(inverse.y),
            L::splat(inverse.z),
        ];
        let o_inv = [L::splat(scaled.x), L::splat(scaled.y), L::splat(scaled.z)];
        let (zero, one, start) = (L::splat(0.0), L::splat(1.0), L::splat(START));
        while top > 0 {
            top -= 1;
            let Some(&(entered, reference)) = scratch.stack.get(top) else {
                break;
            };
            if entered > nearest.t {
                continue;
            }
            if reference & LEAF != 0 {
                counters.leaves += 1;
                let Some(leaf) = bvh.leaves.get((reference & !LEAF) as usize) else {
                    continue;
                };
                // Möller and Trumbore's test, eight triangles at a time. A
                // flat triangle, and a lane without one, divide by zero and
                // fail every comparison.
                let [e1, e2, v0] = [&leaf.e1, &leaf.e2, &leaf.v0]
                    .map(|[x, y, z]| [L::load(x), L::load(y), L::load(z)]);
                let p = cross::<L>(d, e2);
                let scale = L::div(one, dot::<L>(e1, p));
                let [ox, oy, oz] = o;
                let [vx, vy, vz] = v0;
                let s = [L::sub(ox, vx), L::sub(oy, vy), L::sub(oz, vz)];
                let u = L::mul(dot::<L>(s, p), scale);
                let q = cross::<L>(s, e1);
                let v = L::mul(dot::<L>(d, q), scale);
                let t = L::mul(dot::<L>(e2, q), scale);
                let inside = L::both(
                    L::both(L::le(zero, u), L::le(zero, v)),
                    L::le(L::add(u, v), one),
                );
                let ahead = L::both(L::lt(start, t), L::le(t, L::splat(nearest.t)));
                let mut hits = L::bits(L::both(inside, ahead));
                if hits == 0 {
                    continue;
                }
                let mut distances = [0.0; WIDTH];
                L::store(t, &mut distances);
                while hits != 0 {
                    let slot = hits.trailing_zeros() as usize;
                    hits &= hits - 1;
                    let (Some(&t), Some(&id)) = (distances.get(slot), leaf.id.get(slot)) else {
                        continue;
                    };
                    let prim = id.wrapping_add(first_triangle);
                    if t < nearest.t || (t == nearest.t && prim < nearest.prim) {
                        nearest = Nearest { t, prim };
                    }
                }
                continue;
            }
            counters.nodes += 1;
            let Some(node) = bvh.nodes.get(reference as usize) else {
                continue;
            };
            // Each box is three pairs of planes; the ray is inside it from
            // the last near plane it crosses to the first far one. What
            // isn't a number (a ray along a plane it starts on) drops out,
            // because the limit it is compared with always comes second.
            let mut near = L::splat(START);
            let mut far = L::splat(nearest.t);
            let axes = node.lo.iter().zip(&node.hi).zip(backwards);
            for ((((lo, hi), backwards), o), (inv, o_inv)) in
                axes.zip(o).zip(inv.into_iter().zip(o_inv))
            {
                let (first, last) = if backwards { (hi, lo) } else { (lo, hi) };
                near = L::max(L::slab(L::load(first), o, inv, o_inv), near);
                far = L::min(L::slab(L::load(last), o, inv, o_inv), far);
            }
            let mut hits = L::bits(L::le(near, far));
            if hits == 0 {
                continue;
            }
            let mut starts = [0.0; WIDTH];
            L::store(near, &mut starts);
            // The children that were hit, farthest first, so the nearest is
            // the next one off the stack.
            let mut order = [(0.0f32, EMPTY); WIDTH];
            let mut count = 0;
            while hits != 0 {
                let slot = hits.trailing_zeros() as usize;
                hits &= hits - 1;
                let (Some(&at), Some(&child)) = (starts.get(slot), node.child.get(slot)) else {
                    continue;
                };
                if child == EMPTY {
                    continue;
                }
                let mut place = count;
                while place > 0 {
                    let Some(&before) = order.get(place - 1) else {
                        break;
                    };
                    if before.0 >= at {
                        break;
                    }
                    if let Some(moved) = order.get_mut(place) {
                        *moved = before;
                    }
                    place -= 1;
                }
                if let Some(placed) = order.get_mut(place) {
                    *placed = (at, child);
                }
                count += 1;
            }
            for entry in order.iter().take(count) {
                match scratch.stack.get_mut(top) {
                    Some(slot) => {
                        *slot = *entry;
                        top += 1;
                    }
                    None => scratch.overflowed = true,
                }
            }
        }
    }
    nearest
}

/// The first thing the ray hits, spheres and triangles together.
///
/// # Safety
/// The processor runs `L`'s instructions.
#[inline(always)]
pub(super) unsafe fn nearest<L: Lanes>(
    scene: &Scene,
    origin: Vec3,
    direction: Vec3,
    scratch: &mut Scratch,
    counters: &mut Counters,
) -> Nearest {
    let mut nearest = Nearest {
        t: f32::INFINITY,
        prim: NO_HIT,
    };
    for (sphere, index) in scene.spheres.iter().zip(0u32..) {
        let from_center = origin - sphere.center;
        let half_b = from_center.dot(direction);
        let c = from_center.dot(from_center) - sphere.radius * sphere.radius;
        let discriminant = half_b * half_b - c;
        if discriminant < 0.0 {
            continue;
        }
        let root = discriminant.sqrt();
        // The near crossing, or the far one from inside the sphere.
        let mut t = -half_b - root;
        if t <= START {
            t = root - half_b;
        }
        if t > START && t < nearest.t {
            nearest = Nearest { t, prim: index };
        }
    }
    let first_triangle = scene.spheres.len() as u32;
    // SAFETY: the caller's guarantee.
    unsafe {
        walk::<L>(
            &scene.bvh,
            origin,
            direction,
            first_triangle,
            nearest,
            scratch,
            counters,
        )
    }
}

#[inline(always)]
fn sky(direction: Vec3) -> Vec3 {
    let up = 0.5 * (direction.y + 1.0);
    vec3(0.75, 0.78, 0.82) * (1.0 - up) + vec3(0.25, 0.42, 0.78) * up
}

#[inline(always)]
fn mirrored(direction: Vec3, normal: Vec3) -> Vec3 {
    direction - normal * (2.0 * direction.dot(normal))
}

/// A direction around `normal`, more likely the closer to it: what a matte
/// surface does with light.
#[inline(always)]
fn scattered(normal: Vec3, rng: &mut Rng) -> Vec3 {
    let (out, around) = (unit_f32(rng.next_u64()), unit_f32(rng.next_u64()));
    let (sin, cos) = sin_cos_turns(around);
    let spread = out.sqrt();
    // Two directions square to the normal and to each other, without a
    // branch on which axis the normal is close to (Duff and others, 2017).
    let sign = if normal.z < 0.0 { -1.0 } else { 1.0 };
    let a = -1.0 / (sign + normal.z);
    let b = normal.x * normal.y * a;
    let first = vec3(
        1.0 + sign * normal.x * normal.x * a,
        sign * b,
        -sign * normal.x,
    );
    let second = vec3(b, sign + normal.y * normal.y * a, -normal.y);
    (first * (spread * cos) + second * (spread * sin) + normal * (1.0 - out).sqrt()).normalized()
}

/// How much of the light glass reflects at this angle (Schlick).
#[inline(always)]
fn reflectance(cos: f32, index: f32) -> f32 {
    let head_on = (1.0 - index) / (1.0 + index);
    let head_on = head_on * head_on;
    let away = 1.0 - cos;
    head_on + (1.0 - head_on) * away * away * away * away * away
}

/// The light one path brings back to the camera.
///
/// # Safety
/// The processor runs `L`'s instructions.
#[inline(always)]
pub(super) unsafe fn radiance<L: Lanes>(
    scene: &Scene,
    mut origin: Vec3,
    mut direction: Vec3,
    rng: &mut Rng,
    scratch: &mut Scratch,
    counters: &mut Counters,
) -> Vec3 {
    let mut carried = Vec3::splat(1.0);
    let mut light = Vec3::ZERO;
    for bounce in 0..MAX_BOUNCES {
        counters.rays += 1;
        // SAFETY: the caller's guarantee.
        let hit = unsafe { nearest::<L>(scene, origin, direction, scratch, counters) };
        if hit.prim == NO_HIT {
            light = light + carried * sky(direction);
            break;
        }
        let point = origin + direction * hit.t;
        let Some((outward, material)) = scene.surface(hit.prim, point) else {
            break;
        };
        let outside = outward.dot(direction) < 0.0;
        let normal = if outside { outward } else { -outward };
        match material {
            Material::Light { emission } => {
                light = light + carried * emission;
                break;
            }
            Material::Diffuse { albedo } => {
                carried = carried * albedo;
                direction = scattered(normal, rng);
            }
            Material::Checker { dark, pale } => {
                let square = floor_i32(point.x * 0.5).wrapping_add(floor_i32(point.z * 0.5));
                carried = carried * if square & 1 == 0 { dark } else { pale };
                direction = scattered(normal, rng);
            }
            Material::Metal { albedo, fuzz } => {
                let bounced =
                    (mirrored(direction, normal) + scattered(normal, rng) * fuzz).normalized();
                if bounced.dot(normal) <= 0.0 {
                    break;
                }
                carried = carried * albedo;
                direction = bounced;
            }
            Material::Glass { index, tint } => {
                let ratio = if outside { 1.0 / index } else { index };
                let cos_in = -direction.dot(normal);
                let sin2_out = ratio * ratio * (1.0 - cos_in * cos_in);
                // Past the critical angle everything reflects.
                let cos_out = if sin2_out < 1.0 {
                    Some((1.0 - sin2_out).sqrt())
                } else {
                    None
                };
                let through = cos_out.filter(|&cos_out| {
                    // Schlick's curve is for the angle on the thin side.
                    let cos = if outside { cos_in } else { cos_out };
                    unit_f32(rng.next_u64()) >= reflectance(cos, index)
                });
                match through {
                    Some(cos_out) => {
                        direction =
                            (direction * ratio + normal * (ratio * cos_in - cos_out)).normalized();
                        carried = carried * tint;
                    }
                    None => direction = mirrored(direction, normal),
                }
            }
        }
        origin = point;
        if bounce >= ROULETTE_FROM {
            let keep = smaller(carried.max_component(), 0.95);
            if unit_f32(rng.next_u64()) >= keep {
                break;
            }
            carried = carried * (1.0 / keep);
        }
    }
    light
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::cpu::render::bvh::tests::scattered as scattered_triangles;
    use crate::cpu::render::bvh::{build, Triangle};
    use crate::cpu::render::simd::Portable;
    #[cfg(target_arch = "x86_64")]
    use crate::cpu::render::simd::{Avx2, Sse2};

    fn rays(count: usize, seed: u64) -> Vec<(Vec3, Vec3)> {
        let mut rng = Rng::new(seed);
        let mut unit = || unit_f32(rng.next_u64());
        (0..count)
            .map(|_| {
                let origin = vec3(unit(), unit(), unit()) * 14.0 - Vec3::splat(2.0);
                let towards = vec3(unit(), unit(), unit()) * 10.0;
                (origin, (towards - origin).normalized())
            })
            .collect()
    }

    /// The same test as the walk's, one triangle at a time and all of them.
    fn by_brute_force(triangles: &[Triangle], origin: Vec3, direction: Vec3) -> Nearest {
        let mut nearest = Nearest {
            t: f32::INFINITY,
            prim: NO_HIT,
        };
        for (triangle, index) in triangles.iter().zip(0u32..) {
            let (e1, e2) = (triangle.v1 - triangle.v0, triangle.v2 - triangle.v0);
            let p = direction.cross(e2);
            let scale = 1.0 / e1.dot(p);
            let s = origin - triangle.v0;
            let u = s.dot(p) * scale;
            let q = s.cross(e1);
            let v = direction.dot(q) * scale;
            let t = e2.dot(q) * scale;
            let hit = 0.0 <= u && 0.0 <= v && u + v <= 1.0 && START < t;
            if hit && (t < nearest.t || (t == nearest.t && index < nearest.prim)) {
                nearest = Nearest { t, prim: index };
            }
        }
        nearest
    }

    /// # Safety
    /// The processor runs `L`'s instructions.
    unsafe fn walked<L: Lanes>(bvh: &Bvh, origin: Vec3, direction: Vec3) -> (Nearest, Counters) {
        let mut scratch = Scratch::default();
        let mut counters = Counters::default();
        let nothing = Nearest {
            t: f32::INFINITY,
            prim: NO_HIT,
        };
        // SAFETY: the caller's guarantee.
        let nearest = unsafe {
            walk::<L>(
                bvh,
                origin,
                direction,
                0,
                nothing,
                &mut scratch,
                &mut counters,
            )
        };
        assert!(!scratch.overflowed);
        (nearest, counters)
    }

    #[test]
    fn the_walk_finds_what_testing_every_triangle_finds() {
        let triangles = scattered_triangles(3000, 21);
        let bvh = build(&triangles).unwrap();
        let mut hits = 0;
        for (origin, direction) in rays(2000, 4) {
            let expected = by_brute_force(&triangles, origin, direction);
            // SAFETY: plain floats run anywhere.
            let (found, counters) = unsafe { walked::<Portable>(&bvh, origin, direction) };
            assert_eq!(found, expected);
            hits += usize::from(found.prim != NO_HIT);
            // The tree has to save work, not only agree.
            assert!(counters.leaves < 200, "{}", counters.leaves);
        }
        assert!(hits > 500, "{hits}");
    }

    #[cfg(target_arch = "x86_64")]
    #[test]
    fn every_tier_walks_to_the_same_hit_by_the_same_steps() {
        let triangles = scattered_triangles(3000, 22);
        let bvh = build(&triangles).unwrap();
        let avx2 = std::arch::is_x86_feature_detected!("avx2");
        for (origin, direction) in rays(2000, 5) {
            // SAFETY: plain floats run anywhere.
            let portable = unsafe { walked::<Portable>(&bvh, origin, direction) };
            // SAFETY: SSE2 is part of x86-64.
            assert_eq!(unsafe { walked::<Sse2>(&bvh, origin, direction) }, portable);
            if avx2 {
                // SAFETY: the processor just said it has AVX2.
                assert_eq!(unsafe { walked::<Avx2>(&bvh, origin, direction) }, portable);
            }
        }
    }

    #[test]
    fn rays_along_the_axes_and_from_inside_a_box_are_walked() {
        let triangles = scattered_triangles(500, 23);
        let bvh = build(&triangles).unwrap();
        let mut hits = 0;
        for triangle in &triangles {
            let middle = (triangle.v0 + triangle.v1 + triangle.v2) * (1.0 / 3.0);
            for (axis, sign) in [
                (0, 1.0),
                (1, 1.0),
                (2, 1.0),
                (0, -1.0),
                (1, -1.0),
                (2, -1.0),
            ] {
                // A direction with two zeros, one of them negative.
                let mut direction = vec3(0.0, -0.0, 0.0);
                match axis {
                    0 => direction.x = sign,
                    1 => direction.y = sign,
                    _ => direction.z = sign,
                }
                let origin = middle - direction * 3.0;
                let expected = by_brute_force(&triangles, origin, direction);
                // SAFETY: plain floats run anywhere.
                let (found, _) = unsafe { walked::<Portable>(&bvh, origin, direction) };
                assert_eq!(found, expected);
                hits += usize::from(found.prim != NO_HIT);
            }
        }
        assert!(hits > 1000, "{hits}");
    }

    #[test]
    fn of_two_triangles_at_the_same_distance_the_lower_number_wins() {
        let one = Triangle {
            v0: vec3(-1.0, -1.0, 5.0),
            v1: vec3(1.0, -1.0, 5.0),
            v2: vec3(0.0, 1.0, 5.0),
        };
        // Many copies: they end up in different leaves and nodes.
        let bvh = build(&vec![one; 300]).unwrap();
        let towards = vec3(0.0, 0.0, 1.0);
        // SAFETY: plain floats run anywhere.
        let (found, _) = unsafe { walked::<Portable>(&bvh, Vec3::ZERO, towards) };
        assert_eq!(found, Nearest { t: 5.0, prim: 0 });
    }

    #[test]
    fn a_ray_inside_a_sphere_hits_its_far_side() {
        let scene = crate::cpu::render::scene::prototype(0).unwrap();
        let mut scratch = Scratch::default();
        let mut counters = Counters::default();
        // From the middle of the glass sphere, of radius 2, straight up.
        let (origin, up) = (vec3(0.0, 2.0, 0.0), vec3(0.0, 1.0, 0.0));
        // SAFETY: plain floats run anywhere.
        let hit = unsafe { nearest::<Portable>(&scene, origin, up, &mut scratch, &mut counters) };
        assert_eq!(hit, Nearest { t: 2.0, prim: 0 });
        // And from above it, down: its near side, not the floor behind.
        let above = vec3(0.0, 9.0, 0.0);
        // SAFETY: plain floats run anywhere.
        let hit = unsafe { nearest::<Portable>(&scene, above, -up, &mut scratch, &mut counters) };
        assert_eq!(hit, Nearest { t: 5.0, prim: 0 });
    }

    #[test]
    fn a_scattered_direction_is_a_unit_on_the_normals_side() {
        let mut rng = Rng::new(8);
        for normal in [
            vec3(0.0, 0.0, 1.0),
            vec3(0.0, 0.0, -1.0),
            vec3(0.0, 1.0, 0.0),
            vec3(0.6, -0.8, 0.0),
            vec3(-0.48, 0.6, -0.64),
        ] {
            let mut mean = Vec3::ZERO;
            for _ in 0..2000 {
                let direction = scattered(normal, &mut rng);
                assert!((direction.length() - 1.0).abs() < 1e-5);
                assert!(direction.dot(normal) >= 0.0);
                mean = mean + direction * (1.0 / 2000.0);
            }
            // Weighted by the cosine, the mean is two thirds of the normal.
            assert!((mean - normal * (2.0 / 3.0)).length() < 0.05, "{mean:?}");
        }
    }

    #[test]
    fn glass_reflects_little_head_on_and_everything_at_a_glance() {
        assert!((reflectance(1.0, 1.5) - 0.04).abs() < 1e-6);
        assert!((reflectance(0.0, 1.5) - 1.0).abs() < 1e-6);
    }
}
