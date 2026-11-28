//! The prototype's scene, made by code: a few exact spheres, one of them
//! glass, and a tree of triangles around them.
//!
//! Everything comes from formulas and a fixed seed, with this module's own
//! sine and cosine, so the scene has the same bits on every machine. `detail`
//! only changes how finely the small balls are cut: the picture stays the
//! same and the tree grows fourfold with each step.

use super::bvh::{self, Bvh, Triangle};
use super::math::{floor_i32, sin_cos_turns, unit_f32, vec3, Vec3};
use crate::common::error::{Error, Result};
use crate::common::hash::mix;

/// Each step cuts every triangle of a ball in four. Five would be a tree of
/// gigabytes.
pub const MAX_DETAIL: u32 = 4;

#[derive(Debug, Clone, Copy, PartialEq)]
pub enum Material {
    Diffuse {
        albedo: Vec3,
    },
    /// A diffuse floor in squares of two colours.
    Checker {
        dark: Vec3,
        pale: Vec3,
    },
    Metal {
        albedo: Vec3,
        fuzz: f32,
    },
    Glass {
        index: f32,
        tint: Vec3,
    },
    Light {
        emission: Vec3,
    },
}

#[derive(Debug, Clone, Copy, PartialEq)]
pub struct Sphere {
    pub center: Vec3,
    pub radius: f32,
    pub material: Material,
}

/// What shading needs of a triangle once a ray has hit it.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct Facet {
    /// Unit length, pointing out of the solid the triangle is part of.
    pub normal: Vec3,
    pub material: u32,
}

#[derive(Debug, Clone, Copy, PartialEq)]
pub struct Camera {
    eye: Vec3,
    forward: Vec3,
    /// Scaled so the edges of the picture are at -1 and 1.
    right: Vec3,
    up: Vec3,
}

impl Camera {
    /// `half_height` is the tangent of half the vertical angle of view.
    pub fn looking(eye: Vec3, target: Vec3, half_height: f32, aspect: f32) -> Camera {
        let forward = (target - eye).normalized();
        let right = vec3(0.0, 1.0, 0.0).cross(forward).normalized();
        let up = forward.cross(right);
        Camera {
            eye,
            forward,
            right: right * (half_height * aspect),
            up: up * half_height,
        }
    }

    /// The ray through a point of the picture: `across` and `down` go from
    /// 0 to 1 from its top left corner.
    #[inline(always)]
    pub fn ray(&self, across: f32, down: f32) -> (Vec3, Vec3) {
        let direction =
            self.forward + self.right * (2.0 * across - 1.0) + self.up * (1.0 - 2.0 * down);
        (self.eye, direction.normalized())
    }
}

#[derive(Debug, Clone, PartialEq)]
pub struct Scene {
    pub spheres: Vec<Sphere>,
    pub bvh: Bvh,
    /// One per triangle, by its index.
    pub facets: Vec<Facet>,
    pub materials: Vec<Material>,
    pub camera: Camera,
}

impl Scene {
    /// What a ray hit: spheres come first, then triangles. The normal points
    /// out of the solid, and the material may depend on where it was hit.
    #[inline(always)]
    pub fn surface(&self, prim: u32, point: Vec3) -> Option<(Vec3, Material)> {
        let prim = prim as usize;
        if let Some(sphere) = self.spheres.get(prim) {
            let outward = (point - sphere.center) * (1.0 / sphere.radius);
            return Some((outward, sphere.material));
        }
        let facet = self.facets.get(prim - self.spheres.len())?;
        let material = self.materials.get(facet.material as usize)?;
        Some((facet.normal, *material))
    }

    pub fn triangles(&self) -> usize {
        self.facets.len()
    }

    /// The memory the rays read: the tree and what shading looks up.
    pub fn bytes(&self) -> usize {
        self.bvh.bytes() + self.facets.len() * size_of::<Facet>()
    }
}

// A regular icosahedron on the unit sphere: its twelve corners are the
// rotations of (0, ±A, ±B), with B / A the golden ratio.
const A: f32 = 0.525_731_1;
const B: f32 = 0.850_650_8;
const CORNERS: [Vec3; 12] = [
    vec3(-A, B, 0.0),
    vec3(A, B, 0.0),
    vec3(-A, -B, 0.0),
    vec3(A, -B, 0.0),
    vec3(0.0, -A, B),
    vec3(0.0, A, B),
    vec3(0.0, -A, -B),
    vec3(0.0, A, -B),
    vec3(B, 0.0, -A),
    vec3(B, 0.0, A),
    vec3(-B, 0.0, -A),
    vec3(-B, 0.0, A),
];
const FACES: [[usize; 3]; 20] = [
    [0, 11, 5],
    [0, 5, 1],
    [0, 1, 7],
    [0, 7, 10],
    [0, 10, 11],
    [1, 5, 9],
    [5, 11, 4],
    [11, 10, 2],
    [10, 7, 6],
    [7, 1, 8],
    [3, 9, 4],
    [3, 4, 2],
    [3, 2, 6],
    [3, 6, 8],
    [3, 8, 9],
    [4, 9, 5],
    [2, 4, 11],
    [6, 2, 10],
    [8, 6, 7],
    [9, 8, 1],
];

#[derive(Default)]
struct Mesh {
    triangles: Vec<Triangle>,
    facets: Vec<Facet>,
}

impl Mesh {
    /// Add a triangle of a solid whose inside is on the side of `inside`.
    fn push(&mut self, mut triangle: Triangle, inside: Vec3, material: u32) {
        let mut normal = (triangle.v1 - triangle.v0).cross(triangle.v2 - triangle.v0);
        if normal.dot(triangle.v0 - inside) < 0.0 {
            std::mem::swap(&mut triangle.v1, &mut triangle.v2);
            normal = -normal;
        }
        self.triangles.push(triangle);
        self.facets.push(Facet {
            normal: normal.normalized(),
            material,
        });
    }

    /// A ball of flat faces: an icosahedron with each face cut in four
    /// `level` times, and every new corner pushed out to the sphere.
    fn ball(&mut self, center: Vec3, radius: f32, level: u32, material: u32) -> Result<()> {
        for face in FACES {
            let corner = |index: usize| {
                CORNERS
                    .get(index)
                    .copied()
                    .ok_or_else(|| Error::Internal("scene: icosahedron corner".to_owned()))
            };
            let [a, b, c] = face;
            self.face(
                center,
                radius,
                level,
                material,
                [corner(a)?, corner(b)?, corner(c)?],
            );
        }
        Ok(())
    }

    fn face(&mut self, center: Vec3, radius: f32, level: u32, material: u32, corners: [Vec3; 3]) {
        let [a, b, c] = corners;
        if level == 0 {
            let triangle = Triangle {
                v0: center + a * radius,
                v1: center + b * radius,
                v2: center + c * radius,
            };
            self.push(triangle, center, material);
            return;
        }
        let (ab, bc, ca) = (
            (a + b).normalized(),
            (b + c).normalized(),
            (c + a).normalized(),
        );
        for corners in [[a, ab, ca], [b, bc, ab], [c, ca, bc], [ab, bc, ca]] {
            self.face(center, radius, level - 1, material, corners);
        }
    }
}

const FLOOR: u32 = 0;
const GLASS: u32 = 1;
const FIRST_BEAD_MATERIAL: u32 = 2;
const RINGS: u32 = 14;
const FIRST_RING: f32 = 5.6;
const RING_STEP: f32 = 0.64;
const SEED: u64 = 0x5111_0C5E_0000_5CE7;

fn materials() -> Vec<Material> {
    let diffuse = |r, g, b| Material::Diffuse {
        albedo: vec3(r, g, b),
    };
    let metal = |r, g, b, fuzz| Material::Metal {
        albedo: vec3(r, g, b),
        fuzz,
    };
    vec![
        Material::Checker {
            dark: vec3(0.16, 0.17, 0.2),
            pale: vec3(0.62, 0.62, 0.6),
        },
        Material::Glass {
            index: 1.5,
            tint: vec3(0.98, 0.9, 0.72),
        },
        diffuse(0.85, 0.42, 0.1),
        diffuse(0.8, 0.8, 0.78),
        diffuse(0.15, 0.4, 0.75),
        diffuse(0.25, 0.6, 0.3),
        diffuse(0.75, 0.2, 0.25),
        metal(0.95, 0.75, 0.4, 0.15),
        metal(0.9, 0.9, 0.92, 0.02),
        metal(0.85, 0.5, 0.35, 0.3),
    ]
}

/// The prototype's scene, with the small balls cut `detail` times.
pub fn prototype(detail: u32) -> Result<Scene> {
    if detail > MAX_DETAIL {
        return Err(Error::BadSetting("detail"));
    }
    let materials = materials();
    let bead_materials = materials.len() as u64 - u64::from(FIRST_BEAD_MATERIAL);
    let mut mesh = Mesh::default();

    let reach = 60.0;
    let below = vec3(0.0, -1.0, 0.0);
    let corner = |x: f32, z: f32| vec3(x * reach, 0.0, z * reach);
    for [v0, v1, v2] in [
        [corner(-1.0, -1.0), corner(1.0, -1.0), corner(1.0, 1.0)],
        [corner(-1.0, -1.0), corner(1.0, 1.0), corner(-1.0, 1.0)],
    ] {
        mesh.push(Triangle { v0, v1, v2 }, below, FLOOR);
    }

    // A cut-glass ball: few faces, so the light breaks on each one.
    mesh.ball(vec3(-3.5, 1.3, -1.6), 1.3, 1, GLASS)?;

    for ring in 0..RINGS {
        let radius = FIRST_RING + RING_STEP * ring as f32;
        let count = floor_i32(std::f32::consts::TAU * radius / RING_STEP).max(1) as u32;
        for bead in 0..count {
            // Every other ring is turned half a step, so they interlock.
            let turns = (bead as f32 + 0.5 * (ring & 1) as f32) / count as f32;
            let (sin, cos) = sin_cos_turns(turns);
            let chance = mix((u64::from(ring) << 32 | u64::from(bead)) ^ SEED);
            let size = 0.2 + 0.1 * unit_f32(chance);
            let material = FIRST_BEAD_MATERIAL + ((chance & 0xFFFF) % bead_materials) as u32;
            let center = vec3(radius * cos, size, radius * sin);
            mesh.ball(center, size, detail, material)?;
        }
    }

    let spheres = vec![
        Sphere {
            center: vec3(0.0, 2.0, 0.0),
            radius: 2.0,
            material: Material::Glass {
                index: 1.5,
                tint: vec3(0.94, 0.98, 1.0),
            },
        },
        Sphere {
            center: vec3(3.7, 1.4, -1.0),
            radius: 1.4,
            material: Material::Metal {
                albedo: vec3(0.92, 0.78, 0.5),
                fuzz: 0.04,
            },
        },
        Sphere {
            center: vec3(-9.0, 18.0, -10.0),
            radius: 5.0,
            material: Material::Light {
                emission: vec3(9.0, 8.4, 7.6),
            },
        },
    ];

    Ok(Scene {
        spheres,
        bvh: bvh::build(&mesh.triangles)?,
        facets: mesh.facets,
        materials,
        camera: Camera::looking(vec3(0.0, 7.5, -19.0), vec3(0.0, 1.0, 0.0), 0.36, 16.0 / 9.0),
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::common::hash::Fingerprint;

    fn fingerprint(scene: &Scene) -> u64 {
        let mut fingerprint = Fingerprint::default();
        for node in &scene.bvh.nodes {
            for lanes in node.lo.iter().chain(&node.hi) {
                fingerprint.floats(lanes);
            }
            for child in node.child {
                fingerprint.word(u64::from(child));
            }
        }
        for leaf in &scene.bvh.leaves {
            for lanes in leaf.v0.iter().chain(&leaf.e1).chain(&leaf.e2) {
                fingerprint.floats(lanes);
            }
            for id in leaf.id {
                fingerprint.word(u64::from(id));
            }
        }
        for facet in &scene.facets {
            fingerprint.floats(&[facet.normal.x, facet.normal.y, facet.normal.z]);
            fingerprint.word(u64::from(facet.material));
        }
        fingerprint.finish()
    }

    /// The scene's own bits, pinned: built with another C library, compiler
    /// or processor, it has to come out the same. If the scene is changed on
    /// purpose, this is the first number to change.
    #[test]
    fn the_scene_has_the_bits_it_had() {
        let scene = prototype(0).unwrap();
        assert_eq!(scene.triangles(), 2 + 80 + 1334 * 20);
        assert_eq!(fingerprint(&scene), 0xB4ED_D6DE_2402_8381);
    }

    #[test]
    fn detail_cuts_each_bead_triangle_in_four() {
        let (coarse, fine) = (prototype(0).unwrap(), prototype(1).unwrap());
        assert_eq!(fine.triangles() - 82, 4 * (coarse.triangles() - 82));
        assert!(fine.bytes() > 3 * coarse.bytes());
        assert_eq!(prototype(MAX_DETAIL + 1), Err(Error::BadSetting("detail")));
    }

    #[test]
    fn every_normal_is_a_unit_pointing_out() {
        let scene = prototype(1).unwrap();
        for facet in &scene.facets {
            let length = facet.normal.length();
            assert!((length - 1.0).abs() < 1e-5, "{length}");
        }
        // The floor's two triangles face up.
        assert_eq!(scene.facets[0].normal, vec3(0.0, 1.0, 0.0));
        assert_eq!(scene.facets[1].normal, vec3(0.0, 1.0, 0.0));
    }

    #[test]
    fn the_ball_is_closed_and_on_its_sphere() {
        let mut mesh = Mesh::default();
        let center = vec3(1.0, 2.0, 3.0);
        mesh.ball(center, 2.0, 2, 0).unwrap();
        assert_eq!(mesh.triangles.len(), 320);
        for (triangle, facet) in mesh.triangles.iter().zip(&mesh.facets) {
            for corner in [triangle.v0, triangle.v1, triangle.v2] {
                assert!(((corner - center).length() - 2.0).abs() < 1e-5);
            }
            let middle = (triangle.v0 + triangle.v1 + triangle.v2) * (1.0 / 3.0);
            assert!(facet.normal.dot(middle - center) > 0.0);
        }
        // Closed: every edge is shared by two triangles, so each corner
        // position turns up an even number of times... six or five faces
        // meet at each.
        let mut corners = std::collections::HashMap::new();
        for triangle in &mesh.triangles {
            for corner in [triangle.v0, triangle.v1, triangle.v2] {
                let key = [corner.x, corner.y, corner.z].map(|c| (c * 1e4).round() as i64);
                *corners.entry(key).or_insert(0) += 1;
            }
        }
        assert_eq!(corners.len(), 162);
        assert!(corners.values().all(|faces| *faces == 5 || *faces == 6));
    }

    #[test]
    fn the_camera_looks_at_its_target_through_the_middle() {
        let camera = Camera::looking(vec3(0.0, 0.0, -5.0), Vec3::ZERO, 0.5, 2.0);
        let (eye, middle) = camera.ray(0.5, 0.5);
        assert_eq!(eye, vec3(0.0, 0.0, -5.0));
        assert_eq!(middle, vec3(0.0, 0.0, 1.0));
        let (_, corner) = camera.ray(1.0, 0.0);
        // Right and up of the middle, by the two half sizes.
        assert!(corner.x > 0.0 && corner.y > 0.0);
        assert!((corner.x / corner.z - 1.0).abs() < 1e-6);
        assert!((corner.y / corner.z - 0.5).abs() < 1e-6);
    }
}
