//! Speed-critical similarity compute for AutoIssue root-cause clustering.
//!
//! This crate owns the hot numeric path of the clustering pipeline described in
//! `docs/specs/fr-root-cause-clustering.md`: turning a feature set into a
//! MinHash signature, banding signatures for Locality-Sensitive Hashing (LSH)
//! candidate generation, and estimating Jaccard resemblance between two
//! signatures. The decision logic (template extraction, blend weights, cluster
//! selection) lives in the Haskell tier; this crate is pure arithmetic.
//!
//! Sources:
//! - Broder, *On the Resemblance and Containment of Documents*, SEQUENCES 1997
//!   (MinHash / min-wise resemblance).
//! - Indyk & Motwani, STOC 1998 (Locality-Sensitive Hashing).
//! - Leskovec, Rajaraman, Ullman, *Mining of Massive Datasets*, 3rd ed., Ch. 3
//!   (shingling, MinHash signatures, LSH banding).

#![forbid(unsafe_code)]
#![allow(clippy::pedantic, clippy::nursery, clippy::cargo)]
use std::collections::HashMap;

/// Number of slots in a MinHash signature.
pub const SIGNATURE_LEN: usize = 64;

/// Number of LSH bands. `LSH_BANDS * LSH_ROWS` must equal [`SIGNATURE_LEN`].
pub const LSH_BANDS: usize = 8;

/// Number of signature rows per LSH band.
pub const LSH_ROWS: usize = 8;

/// A fixed-length MinHash signature. Empty inputs map to all-`u64::MAX`.
pub type Signature = [u64; SIGNATURE_LEN];

/// SplitMix64 finalizer — a fast, well-distributed 64-bit mixer used as the
/// MinHash hash family and the LSH band fold. Reference: Steele, Lea, Flood,
/// *Fast Splittable Pseudorandom Number Generators*, OOPSLA 2014.
#[must_use]
const fn splitmix64(seed: u64) -> u64 {
    let mut z = seed.wrapping_add(0x9E37_79B9_7F4A_7C15);
    z = (z ^ (z >> 30)).wrapping_mul(0xBF58_476D_1CE4_E5B9);
    z = (z ^ (z >> 27)).wrapping_mul(0x94D0_49BB_1331_11EB);
    z ^ (z >> 31)
}

/// Runtime clustering parameters. `bands * rows` must equal `signature_len`.
/// These are the knobs the Optuna tuner varies; the defaults match the const
/// API ([`SIGNATURE_LEN`] / [`LSH_BANDS`] / [`LSH_ROWS`]).
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct Params {
    /// MinHash signature length (`m`).
    pub signature_len: usize,
    /// Number of LSH bands.
    pub bands: usize,
    /// Rows per LSH band.
    pub rows: usize,
}

impl Default for Params {
    fn default() -> Self {
        Self {
            signature_len: SIGNATURE_LEN,
            bands: LSH_BANDS,
            rows: LSH_ROWS,
        }
    }
}

impl Params {
    /// True when the band geometry tiles the signature exactly and is non-empty.
    #[must_use]
    pub fn is_valid(&self) -> bool {
        self.signature_len > 0
            && self.bands > 0
            && self.rows > 0
            && self.bands * self.rows == self.signature_len
    }
}

/// MinHash signature of length `m` — the variable-length form of [`minhash`].
#[must_use]
pub fn minhash_n(features: &[u64], m: usize) -> Vec<u64> {
    let mut sig = vec![u64::MAX; m];
    if features.is_empty() {
        return sig;
    }
    for (slot_index, slot) in sig.iter_mut().enumerate() {
        let slot_seed = splitmix64(slot_index as u64);
        let mut minimum = u64::MAX;
        for &feature in features {
            let hashed = splitmix64(feature ^ slot_seed);
            if hashed < minimum {
                minimum = hashed;
            }
        }
        *slot = minimum;
    }
    sig
}

/// Jaccard estimate over two equal-length signature slices. Returns 0.0 when the
/// lengths differ or are empty.
#[must_use]
pub fn jaccard_estimate_slice(a: &[u64], b: &[u64]) -> f64 {
    if a.is_empty() || a.len() != b.len() {
        return 0.0;
    }
    let agreeing = a.iter().zip(b.iter()).filter(|(x, y)| x == y).count();
    f64::from(u32::try_from(agreeing).unwrap_or(u32::MAX)) / a.len() as f64
}

/// Band hashes for a signature slice under an explicit band geometry.
#[must_use]
pub fn band_hashes_n(sig: &[u64], bands: usize, rows: usize) -> Vec<u64> {
    let mut out = vec![0u64; bands];
    for (band_index, band) in out.iter_mut().enumerate() {
        let start = band_index * rows;
        let mut acc = 0xcbf2_9ce4_8422_2325; // FNV-1a offset basis
        for &row in &sig[start..start + rows] {
            acc = splitmix64(acc ^ row);
        }
        *band = splitmix64(acc ^ band_index as u64);
    }
    out
}

/// Collapse LSH buckets into unique, ordered candidate index pairs.
fn pairs_from_buckets(buckets: &HashMap<(usize, u64), Vec<usize>>) -> Vec<(usize, usize)> {
    let mut pairs: Vec<(usize, usize)> = Vec::new();
    for members in buckets.values() {
        for (offset, &low) in members.iter().enumerate() {
            for &high in &members[offset + 1..] {
                pairs.push((low.min(high), low.max(high)));
            }
        }
    }
    pairs.sort_unstable();
    pairs.dedup();
    pairs
}

/// Candidate pairs over variable-length signatures under a band geometry.
#[must_use]
pub fn candidate_pairs_n(
    signatures: &[Vec<u64>],
    bands: usize,
    rows: usize,
) -> Vec<(usize, usize)> {
    let mut buckets: HashMap<(usize, u64), Vec<usize>> = HashMap::new();
    for (idx, sig) in signatures.iter().enumerate() {
        for (band_index, &hash) in band_hashes_n(sig, bands, rows).iter().enumerate() {
            buckets.entry((band_index, hash)).or_default().push(idx);
        }
    }
    pairs_from_buckets(&buckets)
}

/// Compute candidate edges under explicit [`Params`]. Invalid params fall back
/// to [`Params::default`] so a bad tuner suggestion can never crash the run.
#[must_use]
pub fn edges_with_params(items: &[Vec<u64>], params: Params) -> Vec<(usize, usize, f64)> {
    let p = if params.is_valid() {
        params
    } else {
        Params::default()
    };
    let signatures: Vec<Vec<u64>> = items
        .iter()
        .map(|f| minhash_n(f, p.signature_len))
        .collect();
    candidate_pairs_n(&signatures, p.bands, p.rows)
        .into_iter()
        .map(|(a, b)| (a, b, jaccard_estimate_slice(&signatures[a], &signatures[b])))
        .collect()
}

/// Compute a MinHash signature from a set of feature hashes.
///
/// Each of the [`SIGNATURE_LEN`] slots applies a distinct hash derived from the
/// slot index and keeps the minimum over all features. An empty feature set
/// yields a signature of all `u64::MAX`.
///
/// # Examples
///
/// ```
/// use speccheck_cluster_core::{minhash, SIGNATURE_LEN};
/// let sig = minhash(&[1, 2, 3]);
/// assert_eq!(sig.len(), SIGNATURE_LEN);
/// ```
#[must_use]
pub fn minhash(features: &[u64]) -> Signature {
    let mut sig = [u64::MAX; SIGNATURE_LEN];
    sig.copy_from_slice(&minhash_n(features, SIGNATURE_LEN));
    sig
}

/// Estimate the Jaccard resemblance of two signatures.
///
/// Returns the fraction of signature slots whose minimum hashes agree, an
/// unbiased estimator of the Jaccard similarity of the underlying feature sets.
#[must_use]
pub fn jaccard_estimate(a: &Signature, b: &Signature) -> f64 {
    jaccard_estimate_slice(a, b)
}

/// Compute one band hash per LSH band for a signature.
#[must_use]
pub fn band_hashes(sig: &Signature) -> [u64; LSH_BANDS] {
    let mut bands = [0u64; LSH_BANDS];
    bands.copy_from_slice(&band_hashes_n(sig, LSH_BANDS, LSH_ROWS));
    bands
}

/// Generate candidate near-duplicate index pairs via LSH banding.
///
/// Two items become a candidate pair when their signatures collide in at least
/// one band. Pairs are returned once, with the lower index first.
#[must_use]
pub fn candidate_pairs(signatures: &[Signature]) -> Vec<(usize, usize)> {
    let mut buckets: HashMap<(usize, u64), Vec<usize>> = HashMap::new();
    for (idx, sig) in signatures.iter().enumerate() {
        for (band_index, &hash) in band_hashes(sig).iter().enumerate() {
            buckets.entry((band_index, hash)).or_default().push(idx);
        }
    }
    pairs_from_buckets(&buckets)
}

/// Compute candidate near-duplicate edges over item feature sets.
///
/// Returns `(index_a, index_b, estimated_jaccard)` for every LSH candidate
/// pair, where the indices refer into `items`. This is the convenience entry
/// the `cluster-sig` binary exposes to the Go plumbing tier.
#[must_use]
pub fn edges(items: &[Vec<u64>]) -> Vec<(usize, usize, f64)> {
    edges_with_params(items, Params::default())
}

#[cfg(test)]
mod tests {
    use super::*;

    fn empty_sig() -> Signature {
        [u64::MAX; SIGNATURE_LEN]
    }

    #[test]
    fn bands_times_rows_equals_signature_len() {
        assert_eq!(LSH_BANDS * LSH_ROWS, SIGNATURE_LEN);
    }

    #[test]
    fn empty_features_map_to_sentinel_signature() {
        assert_eq!(minhash(&[]), empty_sig());
    }

    #[test]
    fn identical_feature_sets_have_identical_signatures() {
        assert_eq!(minhash(&[10, 20, 30]), minhash(&[30, 20, 10]));
    }

    #[test]
    fn identical_signatures_estimate_full_similarity() {
        let sig = minhash(&[1, 2, 3, 4, 5]);
        assert!((jaccard_estimate(&sig, &sig) - 1.0).abs() < f64::EPSILON);
    }

    #[test]
    fn disjoint_feature_sets_estimate_low_similarity() {
        let a = minhash(&(0..50).collect::<Vec<_>>());
        let b = minhash(&(1000..1050).collect::<Vec<_>>());
        assert!(jaccard_estimate(&a, &b) < 0.2);
    }

    #[test]
    fn overlapping_feature_sets_estimate_partial_similarity() {
        let a = minhash(&(0..100).collect::<Vec<_>>());
        let b = minhash(&(50..150).collect::<Vec<_>>());
        let est = jaccard_estimate(&a, &b);
        // True Jaccard of [0,100) vs [50,150) is 50/150 = 0.333...
        assert!(est > 0.15 && est < 0.55, "estimate {est} off true 0.33");
    }

    #[test]
    fn near_duplicates_become_candidate_pairs() {
        let a = minhash(&(0..100).collect::<Vec<_>>());
        let b = minhash(&(0..99).collect::<Vec<_>>());
        let c = minhash(&(5000..5100).collect::<Vec<_>>());
        let pairs = candidate_pairs(&[a, b, c]);
        assert!(pairs.contains(&(0, 1)), "near-duplicate 0,1 missing");
        assert!(!pairs.contains(&(0, 2)), "disjoint 0,2 should not pair");
    }

    #[test]
    fn candidate_pairs_are_unique_and_ordered() {
        let sig = minhash(&[1, 2, 3]);
        let pairs = candidate_pairs(&[sig, sig, sig]);
        let mut seen = pairs.clone();
        seen.sort_unstable();
        seen.dedup();
        assert_eq!(pairs.len(), seen.len(), "duplicate pairs emitted");
        assert!(pairs.iter().all(|(i, j)| i < j), "pairs not ordered");
    }

    #[test]
    fn three_identical_signatures_yield_full_triangle() {
        let sig = minhash(&[1, 2, 3]);
        assert_eq!(
            candidate_pairs(&[sig, sig, sig]),
            vec![(0, 1), (0, 2), (1, 2)]
        );
    }

    // Known-answer tests pin the exact arithmetic of the hash family and the
    // band fold so any change to splitmix64 / band_hashes is caught (otherwise
    // a degraded-but-deterministic mixer still satisfies the tolerance tests).
    const KAT_MINHASH_123: [u64; SIGNATURE_LEN] = [
        627405149472732430,
        9716232063330790915,
        10842689389309339473,
        2554043094958247610,
        5770386275058218278,
        2611768881034074630,
        4277054828538873003,
        4414019431610648415,
        442399275926196888,
        7104948020671887413,
        2529172461435132903,
        843275233814327891,
        7843009614526483068,
        2580124196104974148,
        8927932038644220605,
        5229082311376246125,
        11944016719584946225,
        1786386980972013327,
        1913676695018047512,
        805193982743340818,
        11380572344919828150,
        1318788036811295783,
        908159537603057813,
        7584338614275265995,
        4531590142992240191,
        7098559380638070358,
        9113147628932808391,
        8840153444787388881,
        4287825436090356189,
        9885695101241211724,
        1662269552329397664,
        3490508663684026923,
        1737418872434937676,
        9983298437379732002,
        727640795419094573,
        2327067990810434981,
        11765064258975027138,
        3939271528463997911,
        17152034362837730594,
        7468939089367879646,
        10111254818219316320,
        1545731474603320865,
        8238092213399105094,
        2509306271463647521,
        9614914375464037224,
        312257112221475782,
        1955688525992766100,
        8438124702452051208,
        1534192284164717417,
        4752434869926836787,
        4030810215327158890,
        477937635441374671,
        42083249088691913,
        92002473841942793,
        4961044071534166971,
        4697240025511671966,
        5834499230673494937,
        42918972269023573,
        1886315571545565313,
        2251474586131587739,
        3230550899847219506,
        821782182278964366,
        4843612331300247641,
        635684046065552471,
    ];

    const KAT_BANDS_123: [u64; LSH_BANDS] = [
        10236671902439797954,
        11615306003381371775,
        13458626224344852992,
        15170059524342824686,
        6459680291862497131,
        12983671981850680546,
        12602077903383488233,
        16843427820418667936,
    ];

    #[test]
    fn minhash_known_answer() {
        assert_eq!(minhash(&[1, 2, 3]), KAT_MINHASH_123);
    }

    #[test]
    fn band_hashes_known_answer() {
        assert_eq!(band_hashes(&KAT_MINHASH_123), KAT_BANDS_123);
    }

    #[test]
    fn jaccard_estimate_is_exact_fraction() {
        let a = minhash(&(0..100).collect::<Vec<_>>());
        let b = minhash(&(0..99).collect::<Vec<_>>());
        // 63 of 64 slots agree → 0.984375, an exact binary fraction.
        assert!((jaccard_estimate(&a, &b) - 0.984375).abs() < f64::EPSILON);
    }

    #[test]
    fn edges_link_near_duplicates_with_similarity() {
        let items = vec![
            (0..100).collect::<Vec<_>>(),
            (0..99).collect::<Vec<_>>(),
            (5000..5100).collect::<Vec<_>>(),
        ];
        let e = edges(&items);
        assert!(
            e.iter().any(|&(a, b, s)| a == 0 && b == 1 && s > 0.8),
            "near-duplicate edge 0-1 missing or weak: {e:?}"
        );
        assert!(
            !e.iter().any(|&(a, b, _)| (a == 0 || a == 1) && b == 2),
            "disjoint item 2 should not link"
        );
    }

    #[test]
    fn params_default_is_valid() {
        assert!(Params::default().is_valid());
    }

    #[test]
    fn params_invalid_geometry_detected() {
        assert!(!Params {
            signature_len: 64,
            bands: 8,
            rows: 7
        }
        .is_valid());
        assert!(!Params {
            signature_len: 0,
            bands: 0,
            rows: 0
        }
        .is_valid());
    }

    #[test]
    fn minhash_n_default_matches_const() {
        assert_eq!(
            minhash_n(&[1, 2, 3], SIGNATURE_LEN),
            minhash(&[1, 2, 3]).to_vec()
        );
    }

    #[test]
    fn edges_with_default_params_match_const_edges() {
        let items = vec![(0..100).collect::<Vec<_>>(), (0..99).collect::<Vec<_>>()];
        assert_eq!(edges_with_params(&items, Params::default()), edges(&items));
    }

    #[test]
    fn edges_with_smaller_signature_still_links_near_duplicates() {
        let items = vec![
            (0..120).collect::<Vec<_>>(),
            (0..120).collect::<Vec<_>>(),
            (9000..9120).collect::<Vec<_>>(),
        ];
        let params = Params {
            signature_len: 32,
            bands: 4,
            rows: 8,
        };
        let e = edges_with_params(&items, params);
        assert!(
            e.iter().any(|&(a, b, s)| a == 0 && b == 1 && s > 0.9),
            "identical items 0,1 should link strongly: {e:?}"
        );
        assert!(
            !e.iter().any(|&(_, b, _)| b == 2),
            "disjoint item should not link"
        );
    }

    #[test]
    fn edges_with_invalid_params_falls_back_to_default() {
        let items = vec![(0..100).collect::<Vec<_>>(), (0..100).collect::<Vec<_>>()];
        let bad = Params {
            signature_len: 10,
            bands: 3,
            rows: 4,
        }; // 3*4 != 10
        assert_eq!(edges_with_params(&items, bad), edges(&items));
    }
}
