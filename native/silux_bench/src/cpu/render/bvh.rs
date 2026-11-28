//! The tree the rays walk: eight children to a node, eight triangles to a
//! leaf, laid out so one node's boxes are tested in one go.
//!
//! The build is the same on every machine and with any number of threads:
//! the triangles are sorted by where their centre falls on a space-filling
//! curve, with a sort that never compares floats, and every later choice is
//! made by position, with ties going to the lower index. The same tree
//! serves every instruction tier; what changes between them is how many
//! boxes one instruction tests.

use super::math::{vec3, Vec3};
use crate::common::error::{Error, Result};

pub const WIDTH: usize = 8;
/// A child reference with this bit is a leaf; the rest is its index.
pub const LEAF: u32 = 1 << 31;
/// No child in this slot. Tested before `LEAF`, whose bit it also has.
pub const EMPTY: u32 = u32::MAX;
/// The walk's stack. A node leaves at most `WIDTH` entries on it, so a tree
/// this deep or less can't overflow it; `build` refuses a deeper one.
pub const STACK: usize = 512;

#[derive(Debug, Clone, Copy, PartialEq)]
pub struct Triangle {
    pub v0: Vec3,
    pub v1: Vec3,
    pub v2: Vec3,
}

#[derive(Debug, Clone, Copy, PartialEq)]
pub struct Aabb {
    pub lo: Vec3,
    pub hi: Vec3,
}

impl Aabb {
    /// Holds nothing, and no ray hits it from any direction.
    pub const EMPTY: Aabb = Aabb {
        lo: Vec3::splat(f32::INFINITY),
        hi: Vec3::splat(f32::NEG_INFINITY),
    };

    pub fn with(self, point: Vec3) -> Aabb {
        Aabb {
            lo: self.lo.min_each(point),
            hi: self.hi.max_each(point),
        }
    }

    pub fn union(self, other: Aabb) -> Aabb {
        Aabb {
            lo: self.lo.min_each(other.lo),
            hi: self.hi.max_each(other.hi),
        }
    }

    pub fn of(triangle: &Triangle) -> Aabb {
        Aabb::EMPTY
            .with(triangle.v0)
            .with(triangle.v1)
            .with(triangle.v2)
    }

    pub fn contains(self, other: Aabb) -> bool {
        self.lo.x <= other.lo.x
            && self.lo.y <= other.lo.y
            && self.lo.z <= other.lo.z
            && self.hi.x >= other.hi.x
            && self.hi.y >= other.hi.y
            && self.hi.z >= other.hi.z
    }

    /// Half the surface: only ever compared with another.
    fn half_area(self) -> f32 {
        let size = self.hi - self.lo;
        size.x * size.y + size.y * size.z + size.z * size.x
    }
}

/// Eight boxes, one coordinate of all eight together, and what is in each.
#[repr(C, align(64))]
#[derive(Debug, Clone, PartialEq)]
pub struct Node {
    pub lo: [[f32; WIDTH]; 3],
    pub hi: [[f32; WIDTH]; 3],
    pub child: [u32; WIDTH],
}

/// Up to eight triangles, as a corner and two edges, one coordinate of all
/// eight together. A lane without a triangle is all zeros, which no ray hits.
#[repr(C, align(64))]
#[derive(Debug, Clone, PartialEq)]
pub struct Leaf {
    pub v0: [[f32; WIDTH]; 3],
    pub e1: [[f32; WIDTH]; 3],
    pub e2: [[f32; WIDTH]; 3],
    pub id: [u32; WIDTH],
}

#[derive(Debug, Clone, PartialEq)]
pub struct Bvh {
    pub nodes: Vec<Node>,
    pub leaves: Vec<Leaf>,
    /// A child reference: a node, a single leaf, or `EMPTY` for no triangles.
    pub root: u32,
    /// Nodes and leaves from the root down to the deepest leaf.
    pub depth: u32,
}

impl Bvh {
    pub fn bytes(&self) -> usize {
        self.nodes.len() * size_of::<Node>() + self.leaves.len() * size_of::<Leaf>()
    }
}

fn internal(what: &str) -> Error {
    Error::Internal(format!("bvh: {what}"))
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
struct Key {
    code: u64,
    index: u32,
}

/// Bits per axis of a position on the curve.
const CURVE_BITS: u32 = 21;

/// Spread the low 21 bits of `value` so two zeros follow each one.
fn spread(value: u64) -> u64 {
    let mut x = value & 0x1F_FFFF;
    x = (x | x << 32) & 0x001F_0000_0000_FFFF;
    x = (x | x << 16) & 0x001F_0000_FF00_00FF;
    x = (x | x << 8) & 0x100F_00F0_0F00_F00F;
    x = (x | x << 4) & 0x10C3_0C30_C30C_30C3;
    x = (x | x << 2) & 0x1249_2492_4924_9249;
    x
}

/// Where `point` falls on a Z-order curve through `bounds`: 63 bits.
fn curve_code(point: Vec3, bounds: Aabb) -> u64 {
    let cells = (1u32 << CURVE_BITS) as f32;
    let size = bounds.hi - bounds.lo;
    // A flat axis divides by zero: the cast takes what isn't a number to
    // cell 0, which is where everything on that axis belongs.
    let cell = |at: f32, lo: f32, size: f32| {
        let cell = ((at - lo) / size * cells) as u64;
        cell.min((1 << CURVE_BITS) - 1)
    };
    spread(cell(point.x, bounds.lo.x, size.x)) << 2
        | spread(cell(point.y, bounds.lo.y, size.y)) << 1
        | spread(cell(point.z, bounds.lo.z, size.z))
}

/// Sort by code, eight bits at a time. Stable, so equal codes stay in index
/// order, and with no comparison of floats anywhere.
fn radix_sort(keys: &mut Vec<Key>) -> Result<()> {
    let mut other = keys.clone();
    for pass in 0..8 {
        let shift = pass * 8;
        let digit = |key: &Key| ((key.code >> shift) & 0xFF) as usize;
        let mut starts = [0usize; 256];
        for key in keys.iter() {
            *starts
                .get_mut(digit(key))
                .ok_or_else(|| internal("digit"))? += 1;
        }
        if starts.contains(&keys.len()) {
            continue;
        }
        let mut next = 0;
        for start in starts.iter_mut() {
            let count = *start;
            *start = next;
            next += count;
        }
        for key in keys.iter() {
            let start = starts
                .get_mut(digit(key))
                .ok_or_else(|| internal("digit"))?;
            *other.get_mut(*start).ok_or_else(|| internal("bucket"))? = *key;
            *start += 1;
        }
        std::mem::swap(keys, &mut other);
    }
    Ok(())
}

fn sorted_along_the_curve(triangles: &[Triangle]) -> Result<Vec<Key>> {
    let centre = |t: &Triangle| (t.v0 + t.v1 + t.v2) * (1.0 / 3.0);
    let bounds = triangles
        .iter()
        .fold(Aabb::EMPTY, |bounds, t| bounds.with(centre(t)));
    let mut keys: Vec<Key> = triangles
        .iter()
        .zip(0u32..)
        .map(|(triangle, index)| Key {
            code: curve_code(centre(triangle), bounds),
            index,
        })
        .collect();
    radix_sort(&mut keys)?;
    Ok(keys)
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum Kind {
    /// Up to eight triangles.
    Leaf,
    /// Up to eight leaves' worth of triangles: one wide node whose children
    /// are all leaves, each a run of neighbours on the curve. Cutting these
    /// few by the curve's bits instead leaves nodes and leaves half empty.
    Bundle,
    /// Two children.
    Split,
}

/// A node of the two-way tree the wide one is made from, over
/// `first..first + count` of the sorted keys.
#[derive(Debug, Clone, Copy)]
struct Binary {
    kind: Kind,
    bounds: Aabb,
    left: u32,
    right: u32,
    first: u32,
    count: u32,
}

struct Builder<'a> {
    triangles: &'a [Triangle],
    keys: &'a [Key],
    binary: Vec<Binary>,
    nodes: Vec<Node>,
    leaves: Vec<Leaf>,
    depth: u32,
}

impl Builder<'_> {
    fn binary(&self, index: u32) -> Result<Binary> {
        self.binary
            .get(index as usize)
            .copied()
            .ok_or_else(|| internal("binary node"))
    }

    fn keys(&self, first: usize, end: usize) -> Result<&[Key]> {
        self.keys.get(first..end).ok_or_else(|| internal("keys"))
    }

    fn triangle(&self, key: &Key) -> Result<&Triangle> {
        self.triangles
            .get(key.index as usize)
            .ok_or_else(|| internal("triangle"))
    }

    /// Split `first..end` where the curve says the two halves part: at the
    /// highest bit in which its ends differ. Codes that are all equal are
    /// cut in the middle.
    fn split(&mut self, first: usize, end: usize) -> Result<u32> {
        let keys = self.keys(first, end)?;
        let index = self.binary.len() as u32;
        if keys.len() <= WIDTH * WIDTH {
            self.binary.push(Binary {
                kind: if keys.len() <= WIDTH {
                    Kind::Leaf
                } else {
                    Kind::Bundle
                },
                bounds: self.bounds(first, end)?,
                left: EMPTY,
                right: EMPTY,
                first: first as u32,
                count: keys.len() as u32,
            });
            return Ok(index);
        }
        let (Some(low), Some(high)) = (keys.first(), keys.last()) else {
            return Err(internal("empty range"));
        };
        let middle = if low.code == high.code {
            first + keys.len() / 2
        } else {
            let bit = 63 - (low.code ^ high.code).leading_zeros();
            first + keys.partition_point(|key| (key.code >> bit) & 1 == 0)
        };
        self.binary.push(Binary {
            kind: Kind::Split,
            bounds: Aabb::EMPTY,
            left: EMPTY,
            right: EMPTY,
            first: first as u32,
            count: keys.len() as u32,
        });
        let left = self.split(first, middle)?;
        let right = self.split(middle, end)?;
        let bounds = self.binary(left)?.bounds.union(self.binary(right)?.bounds);
        let node = self
            .binary
            .get_mut(index as usize)
            .ok_or_else(|| internal("binary node"))?;
        (node.bounds, node.left, node.right) = (bounds, left, right);
        Ok(index)
    }

    /// Turn the two-way subtree under `binary` into wide nodes: a node takes
    /// its two children and keeps opening the largest that splits until it
    /// has eight or none does. Between two as large, the one with more
    /// triangles, and then the first.
    fn widen(&mut self, binary: u32, depth: u32) -> Result<u32> {
        let top = self.binary(binary)?;
        let (first, end) = (top.first as usize, (top.first + top.count) as usize);
        match top.kind {
            Kind::Leaf => {
                self.depth = self.depth.max(depth);
                return self.leaf(first, end);
            }
            Kind::Bundle => {
                self.depth = self.depth.max(depth + 1);
                return self.bundle(first, end);
            }
            Kind::Split => {}
        }
        let mut children = vec![top.left, top.right];
        while children.len() < WIDTH {
            let mut largest: Option<(usize, f32, Binary)> = None;
            for (at, child) in children.iter().enumerate() {
                let child = self.binary(*child)?;
                let area = child.bounds.half_area();
                let larger = largest.is_none_or(|(_, most, other)| {
                    area > most || (area == most && child.count > other.count)
                });
                if child.kind == Kind::Split && larger {
                    largest = Some((at, area, child));
                }
            }
            let Some((at, _, opened)) = largest else {
                break;
            };
            *children.get_mut(at).ok_or_else(|| internal("child"))? = opened.left;
            children.insert(at + 1, opened.right);
        }
        let index = self.new_node();
        for (slot, child) in children.into_iter().enumerate() {
            let bounds = self.binary(child)?.bounds;
            let reference = self.widen(child, depth + 1)?;
            self.set_child(index, slot, bounds, reference)?;
        }
        Ok(index as u32)
    }

    fn new_node(&mut self) -> usize {
        self.nodes.push(Node {
            lo: [[f32::INFINITY; WIDTH]; 3],
            hi: [[f32::NEG_INFINITY; WIDTH]; 3],
            child: [EMPTY; WIDTH],
        });
        self.nodes.len() - 1
    }

    fn set_child(&mut self, node: usize, slot: usize, bounds: Aabb, child: u32) -> Result<()> {
        let node = self.nodes.get_mut(node).ok_or_else(|| internal("node"))?;
        set_lanes(&mut node.lo, slot, bounds.lo)?;
        set_lanes(&mut node.hi, slot, bounds.hi)?;
        *node.child.get_mut(slot).ok_or_else(|| internal("slot"))? = child;
        Ok(())
    }

    fn bounds(&self, first: usize, end: usize) -> Result<Aabb> {
        let mut bounds = Aabb::EMPTY;
        for key in self.keys(first, end)? {
            bounds = bounds.union(Aabb::of(self.triangle(key)?));
        }
        Ok(bounds)
    }

    /// One node over `first..end`, eight triangles to a child.
    fn bundle(&mut self, first: usize, end: usize) -> Result<u32> {
        let index = self.new_node();
        for (slot, start) in (first..end).step_by(WIDTH).enumerate() {
            let stop = (start + WIDTH).min(end);
            let bounds = self.bounds(start, stop)?;
            let leaf = self.leaf(start, stop)?;
            self.set_child(index, slot, bounds, leaf)?;
        }
        Ok(index as u32)
    }

    fn leaf(&mut self, first: usize, end: usize) -> Result<u32> {
        let mut leaf = Leaf {
            v0: [[0.0; WIDTH]; 3],
            e1: [[0.0; WIDTH]; 3],
            e2: [[0.0; WIDTH]; 3],
            id: [EMPTY; WIDTH],
        };
        for (slot, key) in self.keys(first, end)?.iter().enumerate() {
            let triangle = self.triangle(key)?;
            set_lanes(&mut leaf.v0, slot, triangle.v0)?;
            set_lanes(&mut leaf.e1, slot, triangle.v1 - triangle.v0)?;
            set_lanes(&mut leaf.e2, slot, triangle.v2 - triangle.v0)?;
            *leaf.id.get_mut(slot).ok_or_else(|| internal("slot"))? = key.index;
        }
        let index = self.leaves.len() as u32;
        self.leaves.push(leaf);
        Ok(LEAF | index)
    }
}

fn set_lanes(lanes: &mut [[f32; WIDTH]; 3], slot: usize, value: Vec3) -> Result<()> {
    let [x, y, z] = lanes;
    for (axis, value) in [(x, value.x), (y, value.y), (z, value.z)] {
        *axis.get_mut(slot).ok_or_else(|| internal("lane"))? = value;
    }
    Ok(())
}

/// One coordinate of one lane of a node or a leaf, as a point.
pub fn lane(lanes: &[[f32; WIDTH]; 3], slot: usize) -> Option<Vec3> {
    let [x, y, z] = lanes;
    Some(vec3(*x.get(slot)?, *y.get(slot)?, *z.get(slot)?))
}

pub fn build(triangles: &[Triangle]) -> Result<Bvh> {
    // A triangle's index has to leave the leaf bit free, and so does a
    // leaf's: there are never more leaves than triangles.
    if triangles.len() >= LEAF as usize {
        return Err(Error::BadSetting("triangles"));
    }
    if triangles.is_empty() {
        return Ok(Bvh {
            nodes: Vec::new(),
            leaves: Vec::new(),
            root: EMPTY,
            depth: 0,
        });
    }
    let keys = sorted_along_the_curve(triangles)?;
    let mut builder = Builder {
        triangles,
        keys: &keys,
        binary: Vec::new(),
        nodes: Vec::new(),
        leaves: Vec::new(),
        depth: 0,
    };
    let top = builder.split(0, keys.len())?;
    let root = builder.widen(top, 1)?;
    if builder.depth as usize * WIDTH > STACK {
        return Err(Error::BadSetting("tree depth"));
    }
    Ok(Bvh {
        nodes: builder.nodes,
        leaves: builder.leaves,
        root,
        depth: builder.depth,
    })
}

#[cfg(test)]
pub(crate) mod tests {
    use super::*;
    use crate::common::rng::Rng;
    use crate::cpu::render::math::unit_f32;

    /// Small triangles scattered through a cube, from a seed.
    pub(crate) fn scattered(count: usize, seed: u64) -> Vec<Triangle> {
        let mut rng = Rng::new(seed);
        let mut point = |scale: f32| {
            vec3(
                unit_f32(rng.next_u64()),
                unit_f32(rng.next_u64()),
                unit_f32(rng.next_u64()),
            ) * scale
        };
        (0..count)
            .map(|_| {
                let v0 = point(10.0);
                Triangle {
                    v0,
                    v1: v0 + point(0.5),
                    v2: v0 + point(0.5),
                }
            })
            .collect()
    }

    /// Every triangle under `reference`, checking on the way down that each
    /// box holds what hangs from it.
    fn collect(bvh: &Bvh, reference: u32, within: Aabb, found: &mut Vec<u32>) {
        if reference == EMPTY {
            return;
        }
        if reference & LEAF != 0 {
            let leaf = &bvh.leaves[(reference & !LEAF) as usize];
            for slot in 0..WIDTH {
                if leaf.id[slot] == EMPTY {
                    assert_eq!(lane(&leaf.e1, slot), Some(Vec3::ZERO));
                    continue;
                }
                let v0 = lane(&leaf.v0, slot).unwrap();
                let triangle = Triangle {
                    v0,
                    v1: v0 + lane(&leaf.e1, slot).unwrap(),
                    v2: v0 + lane(&leaf.e2, slot).unwrap(),
                };
                // The corners come back from an edge, so to the last bit or so.
                let grown = Aabb {
                    lo: within.lo - Vec3::splat(1e-4),
                    hi: within.hi + Vec3::splat(1e-4),
                };
                assert!(grown.contains(Aabb::of(&triangle)));
                found.push(leaf.id[slot]);
            }
            return;
        }
        let node = &bvh.nodes[reference as usize];
        for slot in 0..WIDTH {
            let bounds = Aabb {
                lo: lane(&node.lo, slot).unwrap(),
                hi: lane(&node.hi, slot).unwrap(),
            };
            if node.child[slot] == EMPTY {
                assert_eq!(bounds, Aabb::EMPTY);
                continue;
            }
            assert!(within.contains(bounds));
            collect(bvh, node.child[slot], bounds, found);
        }
    }

    const EVERYWHERE: Aabb = Aabb {
        lo: Vec3::splat(f32::NEG_INFINITY),
        hi: Vec3::splat(f32::INFINITY),
    };

    #[test]
    fn every_triangle_is_in_the_tree_once_and_inside_its_boxes() {
        for count in [1, 7, 8, 9, 64, 1000, 5000] {
            let triangles = scattered(count, 11);
            let bvh = build(&triangles).unwrap();
            let mut found = Vec::new();
            collect(&bvh, bvh.root, EVERYWHERE, &mut found);
            found.sort_unstable();
            assert_eq!(found, (0..count as u32).collect::<Vec<_>>(), "{count}");
            assert!(bvh.depth as usize * WIDTH <= STACK);
        }
    }

    #[test]
    fn nodes_fill_up_with_children() {
        let bvh = build(&scattered(5000, 3)).unwrap();
        let children: usize = bvh
            .nodes
            .iter()
            .map(|node| node.child.iter().filter(|c| **c != EMPTY).count())
            .sum();
        let triangles: usize = bvh
            .leaves
            .iter()
            .map(|leaf| leaf.id.iter().filter(|id| **id != EMPTY).count())
            .sum();
        assert_eq!(triangles, 5000);
        // A two-way tree would give two children to a node, and cutting by
        // the curve down to the last triangle, half-empty leaves.
        assert!(children as f64 / bvh.nodes.len() as f64 > 4.0);
        assert!(triangles as f64 / bvh.leaves.len() as f64 > 7.0);
        assert_eq!(size_of::<Node>(), 256);
        assert_eq!(size_of::<Leaf>(), 320);
    }

    #[test]
    fn the_same_triangles_give_the_same_tree() {
        let triangles = scattered(3000, 5);
        assert_eq!(build(&triangles).unwrap(), build(&triangles).unwrap());
        let mut moved = triangles.clone();
        moved[1234].v0.x += 0.25;
        assert_ne!(build(&moved).unwrap(), build(&triangles).unwrap());
    }

    #[test]
    fn triangles_in_one_place_still_make_a_shallow_tree() {
        let one = scattered(1, 9)[0];
        let bvh = build(&vec![one; 4000]).unwrap();
        let mut found = Vec::new();
        collect(&bvh, bvh.root, EVERYWHERE, &mut found);
        assert_eq!(found.len(), 4000);
        assert!(bvh.depth <= 6, "{}", bvh.depth);
    }

    #[test]
    fn no_triangles_is_an_empty_tree() {
        let bvh = build(&[]).unwrap();
        assert_eq!((bvh.root, bvh.depth, bvh.bytes()), (EMPTY, 0, 0));
    }

    #[test]
    fn the_sort_orders_by_code_and_keeps_equal_codes_in_order() {
        let mut rng = Rng::new(1);
        let mut keys: Vec<Key> = (0..5000)
            .map(|index| Key {
                // Few distinct codes, spread over all eight digits.
                code: (rng.below(50)).wrapping_mul(0x0123_4567_89AB_CDEF),
                index,
            })
            .collect();
        let mut expected = keys.clone();
        expected.sort_by_key(|key| key.code);
        radix_sort(&mut keys).unwrap();
        assert_eq!(keys, expected);
    }

    #[test]
    fn spreading_leaves_two_zeros_after_each_bit() {
        for value in [0u64, 1, 0b101, 0x1F_FFFF, 0x15_5555, 0x0A_BCDE] {
            let mut slow = 0;
            for bit in 0..21 {
                slow |= ((value >> bit) & 1) << (3 * bit);
            }
            assert_eq!(spread(value), slow, "{value:#x}");
        }
    }

    #[test]
    fn the_curve_keeps_neighbours_together() {
        let bounds = Aabb {
            lo: Vec3::ZERO,
            hi: Vec3::splat(1.0),
        };
        let code = |x, y, z| curve_code(vec3(x, y, z), bounds);
        assert_eq!(code(0.0, 0.0, 0.0), 0);
        assert_eq!(code(1.0, 1.0, 1.0), (1 << 63) - 1);
        // The top bit is the first axis's half.
        assert_eq!(code(0.75, 0.0, 0.0) >> 62, 1);
        assert_eq!(code(0.25, 0.9, 0.9) >> 62, 0);
        // A flat box puts everything in cell 0 of that axis.
        let flat = Aabb {
            lo: Vec3::ZERO,
            hi: vec3(1.0, 0.0, 1.0),
        };
        assert_eq!(curve_code(vec3(0.0, 0.0, 0.0), flat), 0);
    }
}
