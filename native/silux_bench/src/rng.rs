//! A small, seedable random generator: SplitMix64.
//!
//! The cycle only needs addresses the prefetcher can't guess, not
//! cryptographic quality, and a fixed seed makes two runs walk the same path.

pub struct Rng {
    state: u64,
}

impl Rng {
    pub fn new(seed: u64) -> Self {
        Rng { state: seed }
    }

    pub fn next_u64(&mut self) -> u64 {
        self.state = self.state.wrapping_add(0x9E37_79B9_7F4A_7C15);
        let mut z = self.state;
        z = (z ^ (z >> 30)).wrapping_mul(0xBF58_476D_1CE4_E5B9);
        z = (z ^ (z >> 27)).wrapping_mul(0x94D0_49BB_1331_11EB);
        z ^ (z >> 31)
    }

    /// Uniform in `0..bound`, for `bound > 0`. Lemire's multiply and shift:
    /// the bias is below `bound / 2^64`, nothing next to the timing noise.
    pub fn below(&mut self, bound: u64) -> u64 {
        ((u128::from(self.next_u64()) * u128::from(bound)) >> 64) as u64
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn stays_below_its_bound() {
        let mut rng = Rng::new(7);
        for bound in [1, 2, 3, 1000, u64::MAX] {
            for _ in 0..1000 {
                assert!(rng.below(bound) < bound);
            }
        }
    }

    #[test]
    fn the_same_seed_gives_the_same_numbers() {
        let (mut a, mut b) = (Rng::new(42), Rng::new(42));
        for _ in 0..100 {
            assert_eq!(a.next_u64(), b.next_u64());
        }
        assert_ne!(Rng::new(1).next_u64(), Rng::new(2).next_u64());
    }

    #[test]
    fn covers_every_value_of_a_small_range() {
        let mut rng = Rng::new(3);
        let mut seen = [false; 10];
        for _ in 0..1000 {
            seen[rng.below(10) as usize] = true;
        }
        assert!(seen.iter().all(|s| *s));
    }
}
