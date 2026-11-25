//! What a set of repetitions says: its median, its range and how scattered it is.

/// A point whose spread is above this is flagged as noisy.
pub const NOISY_SPREAD: f64 = 0.05;

#[derive(Debug, Clone, Copy, PartialEq)]
pub struct Summary {
    pub median: f64,
    pub min: f64,
    pub max: f64,
    /// The median absolute deviation over the median: robust to the one
    /// repetition an interrupt landed on, unlike the standard deviation.
    pub spread: f64,
    pub count: usize,
}

impl Summary {
    pub fn is_noisy(&self) -> bool {
        self.spread > NOISY_SPREAD
    }
}

/// How many times a noisy measurement is taken again.
pub const RETRIES: usize = 2;

/// Measure, and measure again while the result is noisy, up to `RETRIES`
/// more times: a desktop that wakes up for a moment spoils one attempt, not
/// three. Keeps the attempt with the least spread, and says how many retries
/// it took; a result still noisy after them is for the caller to flag.
pub fn steadiest<T>(
    mut measure: impl FnMut() -> crate::common::error::Result<T>,
    spread: impl Fn(&T) -> f64,
) -> crate::common::error::Result<(T, usize)> {
    let mut best = measure()?;
    let mut retries = 0;
    while spread(&best) > NOISY_SPREAD && retries < RETRIES {
        retries += 1;
        let again = measure()?;
        if spread(&again) < spread(&best) {
            best = again;
        }
    }
    Ok((best, retries))
}

/// `None` for no values, or for any value that isn't a finite number.
pub fn summarize(values: &[f64]) -> Option<Summary> {
    if values.is_empty() || values.iter().any(|v| !v.is_finite()) {
        return None;
    }
    let mut sorted = values.to_vec();
    sorted.sort_by(f64::total_cmp);
    let median = median_of_sorted(&sorted)?;
    let mut deviations: Vec<f64> = sorted.iter().map(|v| (v - median).abs()).collect();
    deviations.sort_by(f64::total_cmp);
    let deviation = median_of_sorted(&deviations)?;
    Some(Summary {
        median,
        min: *sorted.first()?,
        max: *sorted.last()?,
        spread: if median > 0.0 {
            deviation / median
        } else {
            0.0
        },
        count: sorted.len(),
    })
}

fn median_of_sorted(sorted: &[f64]) -> Option<f64> {
    let half = sorted.len() / 2;
    if sorted.len() % 2 == 1 {
        sorted.get(half).copied()
    } else {
        Some((sorted.get(half.checked_sub(1)?)? + sorted.get(half)?) / 2.0)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn odd_count() {
        let s = summarize(&[3.0, 1.0, 2.0]).unwrap();
        assert_eq!((s.median, s.min, s.max, s.count), (2.0, 1.0, 3.0, 3));
        // Deviations 1, 0, 1: their median is 1, over a median of 2.
        assert_eq!(s.spread, 0.5);
    }

    #[test]
    fn even_count_takes_the_middle_two() {
        let s = summarize(&[4.0, 1.0, 3.0, 2.0]).unwrap();
        assert_eq!(s.median, 2.5);
    }

    #[test]
    fn all_equal_has_no_spread() {
        let s = summarize(&[5.0; 7]).unwrap();
        assert_eq!((s.median, s.spread), (5.0, 0.0));
        assert!(!s.is_noisy());
    }

    #[test]
    fn one_outlier_moves_neither_median_nor_spread() {
        let s = summarize(&[10.0, 10.0, 10.1, 9.9, 10.0, 10.0, 500.0]).unwrap();
        assert_eq!(s.median, 10.0);
        assert_eq!(s.max, 500.0);
        assert!(!s.is_noisy());
    }

    #[test]
    fn scattered_values_are_noisy() {
        assert!(summarize(&[8.0, 10.0, 12.0, 9.0, 11.0]).unwrap().is_noisy());
    }

    fn attempts(spreads: &[f64]) -> (f64, usize, usize) {
        let mut taken = 0;
        let (best, retries) = steadiest(
            || {
                taken += 1;
                Ok(spreads[taken - 1])
            },
            |s| *s,
        )
        .unwrap();
        (best, retries, taken)
    }

    #[test]
    fn a_steady_result_is_taken_once() {
        assert_eq!(attempts(&[0.01]), (0.01, 0, 1));
    }

    #[test]
    fn a_noisy_result_is_taken_again_until_steady() {
        assert_eq!(attempts(&[0.15, 0.02]), (0.02, 1, 2));
        assert_eq!(attempts(&[0.15, 0.09, 0.03]), (0.03, 2, 3));
    }

    #[test]
    fn after_two_retries_the_steadiest_stays() {
        assert_eq!(attempts(&[0.15, 0.08, 0.12, 0.01]), (0.08, 2, 3));
    }

    #[test]
    fn an_error_on_a_retry_is_the_result() {
        let mut first = true;
        let result = steadiest(
            || {
                if std::mem::take(&mut first) {
                    Ok(0.5)
                } else {
                    Err(crate::common::error::Error::Cancelled)
                }
            },
            |s: &f64| *s,
        );
        assert_eq!(result, Err(crate::common::error::Error::Cancelled));
    }

    #[test]
    fn nothing_or_not_a_number_is_no_summary() {
        assert_eq!(summarize(&[]), None);
        assert_eq!(summarize(&[1.0, f64::NAN]), None);
        assert_eq!(summarize(&[f64::INFINITY]), None);
    }
}
