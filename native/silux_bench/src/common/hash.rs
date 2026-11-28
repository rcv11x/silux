//! The fingerprint of a piece of work: 64 bits of the exact bits it produced.
//!
//! Not cryptographic. What it guarantees is narrower and enough: one changed
//! word always changes the result. Each step is a bijection of the state for
//! a given word and of the word for a given state, so a difference can't be
//! folded away by the words that follow. Two or more changed words collide
//! once in 2^64.

/// Keeps a run of zero words from leaving the state where it was.
const STEP: u64 = 0x9E37_79B9_7F4A_7C15;
const START: u64 = 0x5111_0C5E_C0DE_0001;

/// SplitMix64's finalizer: a bijection of 64 bits where every input bit
/// reaches every output bit.
#[inline(always)]
pub fn mix(mut z: u64) -> u64 {
    z = (z ^ (z >> 30)).wrapping_mul(0xBF58_476D_1CE4_E5B9);
    z = (z ^ (z >> 27)).wrapping_mul(0x94D0_49BB_1331_11EB);
    z ^ (z >> 31)
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct Fingerprint {
    state: u64,
    words: u64,
}

impl Default for Fingerprint {
    fn default() -> Self {
        Fingerprint {
            state: START,
            words: 0,
        }
    }
}

impl Fingerprint {
    #[inline(always)]
    pub fn word(&mut self, word: u64) {
        self.state = mix(self.state ^ word).wrapping_add(STEP);
        self.words = self.words.wrapping_add(1);
    }

    /// The bit patterns as they are: `-0.0` isn't `0.0`, and two NaN with
    /// different payloads are different results.
    pub fn floats(&mut self, values: &[f32]) {
        for pair in values.chunks(2) {
            match pair {
                [a, b] => self.word(u64::from(a.to_bits()) << 32 | u64::from(b.to_bits())),
                [a] => self.word(u64::from(a.to_bits())),
                _ => {}
            }
        }
    }

    /// The count goes in: a message isn't its own prefix.
    pub fn finish(self) -> u64 {
        mix(self.state ^ self.words)
    }
}

/// The fingerprint of a run of floats.
pub fn of_floats(values: &[f32]) -> u64 {
    let mut fingerprint = Fingerprint::default();
    fingerprint.floats(values);
    fingerprint.finish()
}

#[cfg(test)]
mod tests {
    use super::*;

    fn of_words(words: &[u64]) -> u64 {
        let mut fingerprint = Fingerprint::default();
        for word in words {
            fingerprint.word(*word);
        }
        fingerprint.finish()
    }

    /// Pins the function: a table of fingerprints is only good for the hash
    /// it was made with.
    #[test]
    fn known_answers() {
        assert_eq!(
            [of_words(&[]), of_words(&[0]), of_floats(&[1.0, 2.0, 3.0])],
            [
                0xF096_7CFD_BFE3_DB5D,
                0x9523_40DE_0D80_2D4F,
                0x5864_BF17_484B_2E35,
            ]
        );
    }

    #[test]
    fn any_single_flipped_bit_shows() {
        let message: Vec<u64> = (0..64u64).map(|i| mix(i + 1)).collect();
        let whole = of_words(&message);
        for word in 0..message.len() {
            for bit in 0..64 {
                let mut changed = message.clone();
                changed[word] ^= 1 << bit;
                assert_ne!(of_words(&changed), whole, "word {word}, bit {bit}");
            }
        }
    }

    #[test]
    fn order_and_length_count() {
        assert_ne!(of_words(&[1, 2]), of_words(&[2, 1]));
        assert_ne!(of_words(&[]), of_words(&[0]));
        assert_ne!(of_words(&[0]), of_words(&[0, 0]));
        assert_ne!(of_floats(&[1.0]), of_floats(&[1.0, 0.0]));
    }

    #[test]
    fn floats_are_compared_by_their_bits() {
        assert_ne!(of_floats(&[0.0]), of_floats(&[-0.0]));
        let quiet = f32::from_bits(0x7FC0_0000);
        let other = f32::from_bits(0x7FC0_0001);
        assert_ne!(of_floats(&[quiet]), of_floats(&[other]));
        assert_eq!(of_floats(&[quiet, 1.5]), of_floats(&[quiet, 1.5]));
    }

    #[test]
    fn mix_is_a_bijection_on_a_sample() {
        let mut seen = std::collections::HashSet::new();
        for i in 0..100_000u64 {
            assert!(seen.insert(mix(i)));
        }
    }
}
