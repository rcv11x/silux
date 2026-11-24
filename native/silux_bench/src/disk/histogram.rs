//! How long each request took, in buckets that widen with the value.
//!
//! Exact below 64 ns; from there, 32 buckets for each doubling, so a value
//! is known to within 1/64 of itself whatever its size. That keeps every
//! request of a lap in 15 KiB, without a list that grows with the disk's
//! speed.

/// Values below this have a bucket each.
const EXACT: u64 = 64;
/// Buckets for each doubling above that.
const PER_DOUBLING: usize = 32;
/// Enough for every `u64`: the exact ones, and 58 doublings.
const BUCKETS: usize = 1920;

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Histogram {
    counts: Vec<u64>,
    count: u64,
    sum: u128,
    min: u64,
    max: u64,
}

impl Default for Histogram {
    fn default() -> Self {
        Histogram {
            counts: vec![0; BUCKETS],
            count: 0,
            sum: 0,
            min: u64::MAX,
            max: 0,
        }
    }
}

fn bucket_of(value: u64) -> usize {
    if value < EXACT {
        return value as usize;
    }
    // The top six bits of the value: the first is always set, the other five
    // pick one of the 32 buckets of its doubling.
    let shift = 58 - value.leading_zeros();
    (shift as usize + 1) * PER_DOUBLING + ((value >> shift) as usize - PER_DOUBLING)
}

/// The lowest value of a bucket, and how many values it holds.
fn range_of(bucket: usize) -> (u64, u64) {
    if bucket < EXACT as usize {
        return (bucket as u64, 1);
    }
    let shift = bucket / PER_DOUBLING - 1;
    let low = ((bucket % PER_DOUBLING + PER_DOUBLING) as u64) << shift;
    (low, 1 << shift)
}

impl Histogram {
    pub fn record(&mut self, value: u64) {
        if let Some(count) = self.counts.get_mut(bucket_of(value)) {
            *count += 1;
        }
        self.count += 1;
        self.sum += u128::from(value);
        self.min = self.min.min(value);
        self.max = self.max.max(value);
    }

    /// Add another histogram's values to this one's.
    pub fn merge(&mut self, other: &Histogram) {
        for (mine, theirs) in self.counts.iter_mut().zip(&other.counts) {
            *mine += theirs;
        }
        self.count += other.count;
        self.sum += other.sum;
        self.min = self.min.min(other.min);
        self.max = self.max.max(other.max);
    }

    pub fn count(&self) -> u64 {
        self.count
    }

    /// Exact, not from the buckets.
    pub fn mean(&self) -> Option<f64> {
        (self.count > 0).then(|| self.sum as f64 / self.count as f64)
    }

    pub fn min(&self) -> Option<u64> {
        (self.count > 0).then_some(self.min)
    }

    pub fn max(&self) -> Option<u64> {
        (self.count > 0).then_some(self.max)
    }

    /// The value `percent` of the values are at or below: the middle of its
    /// bucket, never outside the smallest and largest values seen.
    pub fn percentile(&self, percent: f64) -> Option<u64> {
        if self.count == 0 || !(0.0..=100.0).contains(&percent) {
            return None;
        }
        let rank = ((percent / 100.0 * self.count as f64).ceil() as u64).clamp(1, self.count);
        let mut seen = 0;
        for (bucket, count) in self.counts.iter().enumerate() {
            seen += count;
            if seen >= rank {
                let (low, width) = range_of(bucket);
                return Some((low + width / 2).clamp(self.min, self.max));
            }
        }
        None
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::common::rng::Rng;

    #[test]
    fn an_empty_one_has_no_figures() {
        let empty = Histogram::default();
        assert_eq!(empty.count(), 0);
        assert_eq!(empty.mean(), None);
        assert_eq!(empty.min(), None);
        assert_eq!(empty.max(), None);
        assert_eq!(empty.percentile(50.0), None);
    }

    #[test]
    fn small_values_come_back_exact() {
        let mut histogram = Histogram::default();
        for value in 1..=50 {
            histogram.record(value);
        }
        assert_eq!(histogram.count(), 50);
        assert_eq!(histogram.mean(), Some(25.5));
        assert_eq!(histogram.min(), Some(1));
        assert_eq!(histogram.max(), Some(50));
        assert_eq!(histogram.percentile(0.0), Some(1));
        assert_eq!(histogram.percentile(2.0), Some(1));
        assert_eq!(histogram.percentile(50.0), Some(25));
        assert_eq!(histogram.percentile(51.0), Some(26));
        assert_eq!(histogram.percentile(99.0), Some(50));
        assert_eq!(histogram.percentile(100.0), Some(50));
        assert_eq!(histogram.percentile(101.0), None);
        assert_eq!(histogram.percentile(-1.0), None);
    }

    #[test]
    fn every_bucket_begins_where_the_one_before_ends() {
        assert_eq!(bucket_of(0), 0);
        assert_eq!(bucket_of(63), 63);
        assert_eq!(bucket_of(64), 64);
        assert_eq!(bucket_of(65), 64);
        assert_eq!(bucket_of(66), 65);
        assert_eq!(bucket_of(u64::MAX), BUCKETS - 1);
        let mut next = 0u64;
        for bucket in 0..BUCKETS {
            let (low, width) = range_of(bucket);
            assert_eq!(low, next, "bucket {bucket}");
            assert_eq!(bucket_of(low), bucket);
            assert_eq!(bucket_of(low + (width - 1)), bucket);
            next = low.wrapping_add(width);
        }
        // The last one ends with the largest value there is.
        assert_eq!(next, 0);
    }

    #[test]
    fn a_large_value_is_known_to_within_a_64th() {
        let mut rng = Rng::new(11);
        for _ in 0..10_000 {
            let value = rng.next_u64() >> rng.below(58);
            let (low, width) = range_of(bucket_of(value));
            let middle = low + width / 2;
            assert!(
                middle.abs_diff(value) as f64 <= value as f64 / 64.0,
                "{value}"
            );
        }
    }

    #[test]
    fn a_percentile_matches_the_sorted_values() {
        // Latencies as a disk gives them: most near 80 µs, a few far above.
        let mut rng = Rng::new(5);
        let mut values: Vec<u64> = (0..20_000)
            .map(|i| {
                let slow = if i % 100 == 0 { 2_000_000 } else { 0 };
                70_000 + rng.below(20_000) + slow
            })
            .collect();
        let mut histogram = Histogram::default();
        for value in &values {
            histogram.record(*value);
        }
        values.sort_unstable();
        for percent in [1.0, 50.0, 90.0, 99.0, 99.9, 100.0] {
            let rank = ((percent / 100.0 * values.len() as f64).ceil() as usize).max(1);
            let exact = values[rank - 1];
            let found = histogram.percentile(percent).unwrap();
            assert!(
                found.abs_diff(exact) as f64 <= exact as f64 / 64.0,
                "{percent}: {found} against {exact}"
            );
        }
        let mean = values.iter().sum::<u64>() as f64 / values.len() as f64;
        assert_eq!(histogram.mean(), Some(mean));
    }

    #[test]
    fn merging_is_recording_them_all_in_one() {
        let (mut all, mut odd, mut even) = (
            Histogram::default(),
            Histogram::default(),
            Histogram::default(),
        );
        for value in 0..5_000u64 {
            let value = value * value;
            all.record(value);
            if value % 2 == 1 {
                odd.record(value);
            } else {
                even.record(value);
            }
        }
        odd.merge(&even);
        assert_eq!(odd, all);
        // Merging an empty one changes nothing, the smallest value neither.
        odd.merge(&Histogram::default());
        assert_eq!(odd, all);
    }
}
