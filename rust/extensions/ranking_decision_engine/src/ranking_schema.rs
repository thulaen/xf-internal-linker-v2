//! Typed records for the Rust `RankingDecisionEngine` boundary.

use pyo3::prelude::*;

pub const ENGINE_VERSION: &str = "ranking_decision_engine/0.1.0";
pub const DEFAULT_MEMORY_BYTES: u64 = 2 * 1024 * 1024 * 1024;

#[allow(clippy::new_without_default)]
#[pyclass(module = "ranking_decision_engine")]
#[derive(Clone, Debug)]
pub struct FeatureVector {
    #[pyo3(get)]
    pub semantic: f32,
    #[pyo3(get)]
    pub keyword: f32,
    #[pyo3(get)]
    pub node: f32,
    #[pyo3(get)]
    pub quality: f32,
}

#[pymethods]
impl FeatureVector {
    #[new]
    #[must_use]
    pub const fn new(semantic: f32, keyword: f32, node: f32, quality: f32) -> Self {
        Self {
            semantic,
            keyword,
            node,
            quality,
        }
    }
}

#[allow(clippy::new_without_default)]
#[pyclass(module = "ranking_decision_engine")]
#[derive(Clone, Debug)]
pub struct CandidateInput {
    #[pyo3(get)]
    pub candidate_id: String,
    #[pyo3(get)]
    pub destination_id: String,
    #[pyo3(get)]
    pub host_id: String,
    #[pyo3(get)]
    pub features: FeatureVector,
}

#[pymethods]
impl CandidateInput {
    #[new]
    #[must_use]
    pub const fn new(
        candidate_id: String,
        destination_id: String,
        host_id: String,
        features: FeatureVector,
    ) -> Self {
        Self {
            candidate_id,
            destination_id,
            host_id,
            features,
        }
    }
}

#[allow(clippy::new_without_default)]
#[pyclass(module = "ranking_decision_engine")]
#[derive(Clone, Debug)]
pub struct WeightProfile {
    #[pyo3(get)]
    pub version: String,
    #[pyo3(get)]
    pub w_semantic: f32,
    #[pyo3(get)]
    pub w_keyword: f32,
    #[pyo3(get)]
    pub w_node: f32,
    #[pyo3(get)]
    pub w_quality: f32,
}

#[pymethods]
impl WeightProfile {
    #[new]
    #[must_use]
    pub const fn new(
        version: String,
        w_semantic: f32,
        w_keyword: f32,
        w_node: f32,
        w_quality: f32,
    ) -> Self {
        Self {
            version,
            w_semantic,
            w_keyword,
            w_node,
            w_quality,
        }
    }
}

impl WeightProfile {
    #[must_use]
    pub const fn values(&self) -> [(&'static str, f32); 4] {
        [
            ("semantic", self.w_semantic),
            ("keyword", self.w_keyword),
            ("node", self.w_node),
            ("quality", self.w_quality),
        ]
    }

    #[must_use]
    pub fn sum(&self) -> f32 {
        self.w_semantic + self.w_keyword + self.w_node + self.w_quality
    }
}

#[allow(clippy::new_without_default)]
#[pyclass(module = "ranking_decision_engine")]
#[derive(Clone, Debug)]
pub struct MemoryBudget {
    #[pyo3(get)]
    pub max_bytes: u64,
}

#[pymethods]
impl MemoryBudget {
    #[new]
    #[must_use]
    pub const fn new(max_bytes: u64) -> Self {
        Self { max_bytes }
    }

    #[staticmethod]
    #[must_use]
    pub const fn default_2gb() -> Self {
        Self {
            max_bytes: DEFAULT_MEMORY_BYTES,
        }
    }
}

#[allow(clippy::new_without_default)]
#[pyclass(module = "ranking_decision_engine")]
#[derive(Clone, Debug)]
pub struct RankingPolicy {
    #[pyo3(get)]
    pub top_n: usize,
    #[pyo3(get)]
    pub memory_budget: MemoryBudget,
}

#[pymethods]
impl RankingPolicy {
    #[new]
    #[must_use]
    pub const fn new(top_n: usize, memory_budget: MemoryBudget) -> Self {
        Self {
            top_n,
            memory_budget,
        }
    }
}

#[allow(clippy::new_without_default)]
#[pyclass(module = "ranking_decision_engine")]
#[derive(Clone, Debug)]
pub struct RankingRequest {
    #[pyo3(get)]
    pub candidates: Vec<CandidateInput>,
    #[pyo3(get)]
    pub profile: WeightProfile,
    #[pyo3(get)]
    pub policy: RankingPolicy,
}

#[pymethods]
impl RankingRequest {
    #[new]
    #[must_use]
    pub const fn new(
        candidates: Vec<CandidateInput>,
        profile: WeightProfile,
        policy: RankingPolicy,
    ) -> Self {
        Self {
            candidates,
            profile,
            policy,
        }
    }
}

#[allow(clippy::new_without_default)]
#[pyclass(module = "ranking_decision_engine")]
#[derive(Clone, Debug)]
pub struct ProfileValidationRequest {
    #[pyo3(get)]
    pub candidate: WeightProfile,
    #[pyo3(get)]
    pub baseline: WeightProfile,
    #[pyo3(get)]
    pub max_movement: f32,
}

#[pymethods]
impl ProfileValidationRequest {
    #[new]
    #[must_use]
    pub const fn new(candidate: WeightProfile, baseline: WeightProfile, max_movement: f32) -> Self {
        Self {
            candidate,
            baseline,
            max_movement,
        }
    }
}

#[allow(clippy::new_without_default)]
#[pyclass(module = "ranking_decision_engine")]
#[derive(Clone, Debug)]
pub struct MemoryEstimateRequest {
    #[pyo3(get)]
    pub candidate_count: usize,
    #[pyo3(get)]
    pub memory_budget: MemoryBudget,
}

#[pymethods]
impl MemoryEstimateRequest {
    #[new]
    #[must_use]
    pub const fn new(candidate_count: usize, memory_budget: MemoryBudget) -> Self {
        Self {
            candidate_count,
            memory_budget,
        }
    }
}

#[allow(clippy::new_without_default)]
#[pyclass(module = "ranking_decision_engine")]
#[derive(Clone, Debug)]
pub struct Contribution {
    #[pyo3(get)]
    pub name: String,
    #[pyo3(get)]
    pub value: f32,
}

impl Contribution {
    #[must_use]
    pub fn new(name: &str, value: f32) -> Self {
        Self {
            name: String::from(name),
            value,
        }
    }
}

#[allow(clippy::new_without_default)]
#[pyclass(module = "ranking_decision_engine")]
#[derive(Clone, Debug)]
pub struct ScoredCandidate {
    #[pyo3(get)]
    pub candidate_id: String,
    #[pyo3(get)]
    pub destination_id: String,
    #[pyo3(get)]
    pub decision_id: String,
    #[pyo3(get)]
    pub score_semantic: f32,
    #[pyo3(get)]
    pub score_keyword: f32,
    #[pyo3(get)]
    pub score_node: f32,
    #[pyo3(get)]
    pub score_quality: f32,
    #[pyo3(get)]
    pub score_final: f32,
    #[pyo3(get)]
    pub contributions: Vec<Contribution>,
    #[pyo3(get)]
    pub explanation: String,
    #[pyo3(get)]
    pub engine_version: String,
}

#[allow(clippy::new_without_default)]
#[pyclass(module = "ranking_decision_engine")]
#[derive(Clone, Debug)]
pub struct RankedBatch {
    #[pyo3(get)]
    pub status: String,
    #[pyo3(get)]
    pub reason: String,
    #[pyo3(get)]
    pub estimated_bytes: u64,
    #[pyo3(get)]
    pub candidates: Vec<ScoredCandidate>,
    #[pyo3(get)]
    pub engine_version: String,
}

impl RankedBatch {
    #[must_use]
    pub fn blocked(reason: &str, estimated_bytes: u64) -> Self {
        Self {
            status: String::from("blocked"),
            reason: String::from(reason),
            estimated_bytes,
            candidates: Vec::new(),
            engine_version: String::from(ENGINE_VERSION),
        }
    }

    #[must_use]
    pub fn ready(candidates: Vec<ScoredCandidate>, estimated_bytes: u64) -> Self {
        Self {
            status: String::from("ready"),
            reason: String::from("within budget"),
            estimated_bytes,
            candidates,
            engine_version: String::from(ENGINE_VERSION),
        }
    }
}

#[allow(clippy::new_without_default)]
#[pyclass(module = "ranking_decision_engine")]
#[derive(Clone, Debug)]
pub struct MemoryEstimate {
    #[pyo3(get)]
    pub allowed: bool,
    #[pyo3(get)]
    pub estimated_bytes: u64,
    #[pyo3(get)]
    pub max_bytes: u64,
    #[pyo3(get)]
    pub reason: String,
}

#[allow(clippy::new_without_default)]
#[pyclass(module = "ranking_decision_engine")]
#[derive(Clone, Debug)]
pub struct GovernanceVerdict {
    #[pyo3(get)]
    pub verdict: String,
    #[pyo3(get)]
    pub reason_code: String,
    #[pyo3(get)]
    pub message: String,
}

impl GovernanceVerdict {
    #[must_use]
    pub fn new(verdict: &str, reason_code: &str, message: &str) -> Self {
        Self {
            verdict: String::from(verdict),
            reason_code: String::from(reason_code),
            message: String::from(message),
        }
    }
}
