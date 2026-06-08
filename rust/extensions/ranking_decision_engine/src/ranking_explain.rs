//! Explanation lookup for the latest ranked batch.

use std::collections::HashMap;
use std::sync::{Mutex, MutexGuard, OnceLock};

use crate::ranking_schema::ScoredCandidate;

static EXPLANATIONS: OnceLock<Mutex<HashMap<String, String>>> = OnceLock::new();

pub fn remember_explanations(candidates: &[ScoredCandidate]) {
    let mut cache = lock_explanation_cache();
    cache.clear();
    for candidate in candidates {
        cache.insert(candidate.decision_id.clone(), candidate.explanation.clone());
    }
}

pub fn clear_explanations() {
    lock_explanation_cache().clear();
}

#[must_use]
pub fn explain(decision_id: &str) -> Option<String> {
    lock_explanation_cache().get(decision_id).cloned()
}

#[must_use]
fn explanation_cache() -> &'static Mutex<HashMap<String, String>> {
    EXPLANATIONS.get_or_init(|| Mutex::new(HashMap::new()))
}

fn lock_explanation_cache() -> MutexGuard<'static, HashMap<String, String>> {
    match explanation_cache().lock() {
        Ok(cache) => cache,
        Err(poisoned) => poisoned.into_inner(),
    }
}
