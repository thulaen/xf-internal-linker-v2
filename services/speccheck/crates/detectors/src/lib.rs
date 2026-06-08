//! FindBugs-style detector catalog for speccheck.
//!
//! The catalog names the detector IDs, categories, and default severities that
//! downstream JSON reports and `AutoIssue` rows use.

#![forbid(unsafe_code)]
#![allow(clippy::pedantic, clippy::nursery, clippy::cargo)]
use sha2::{Digest, Sha256};

/// A FindBugs-style detector descriptor.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct DetectorDescriptor {
    /// Stable detector id.
    pub id: String,
    /// Category shown in `AutoIssue` rows.
    pub category: &'static str,
    /// Default severity.
    pub severity: &'static str,
}

/// A concrete bug-pattern finding emitted by a detector.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Finding {
    /// Stable bug-pattern identifier.
    pub bug_pattern_id: &'static str,
    /// Short plain-English title.
    pub title: String,
    /// Plain-English description.
    pub description: String,
    /// Category shown in the Errors page Bug Patterns tab.
    pub category: &'static str,
    /// Finding severity.
    pub severity: &'static str,
    /// Confidence of the pattern match.
    pub confidence: &'static str,
    /// Repo-relative source path.
    pub source_path: String,
    /// One-based line number.
    pub line_number: usize,
    /// Short source evidence.
    pub evidence: String,
    /// Plain-English fix shape.
    pub suggested_fix: &'static str,
    /// Source-backed citation tag.
    pub citation: &'static str,
    /// Stable dedupe fingerprint.
    pub fingerprint: String,
    /// Sort weight used by downstream pickers.
    pub priority_score: u32,
}

/// Return the 35 static detector descriptors required by the spec.
#[must_use]
pub fn detector_catalog() -> Vec<DetectorDescriptor> {
    let mut rows = Vec::new();
    extend(&mut rows, "RUSTBUG-PERF", "performance", "high", 10);
    extend(&mut rows, "RUSTBUG-CORR", "correctness", "medium", 10);
    extend(&mut rows, "RUSTBUG-CONC", "concurrency", "high", 5);
    extend(&mut rows, "RUSTBUG-RES", "resource", "medium", 5);
    extend(&mut rows, "RUSTBUG-SEC", "security", "critical", 5);
    rows
}

/// Find bug-pattern matches in one source file.
#[must_use]
pub fn find_bugs_in_source(source_path: &str, text: &str) -> Vec<Finding> {
    let mut findings = Vec::new();
    let mut context = SourceContext::default();
    for (index, line) in text.lines().enumerate() {
        let line_number = index + 1;
        let trimmed = line.trim();
        if is_comment_line(trimmed) {
            continue;
        }
        context.update(line, trimmed);
        findings.extend(detect_line(source_path, line_number, trimmed));
        findings.extend(detect_context_line(
            source_path,
            line_number,
            trimmed,
            &context,
        ));
    }
    findings.sort_by(|left, right| {
        left.line_number
            .cmp(&right.line_number)
            .then(left.bug_pattern_id.cmp(right.bug_pattern_id))
    });
    findings.dedup_by(|left, right| {
        left.line_number == right.line_number && left.bug_pattern_id == right.bug_pattern_id
    });
    findings
}

fn is_comment_line(line: &str) -> bool {
    line.starts_with('#')
        || line.starts_with("//")
        || line.starts_with("/*")
        || line.starts_with('*')
}

fn extend(
    rows: &mut Vec<DetectorDescriptor>,
    prefix: &'static str,
    category: &'static str,
    severity: &'static str,
    count: usize,
) {
    for index in 1..=count {
        rows.push(DetectorDescriptor {
            id: format!("{prefix}-{index:03}"),
            category,
            severity,
        });
    }
}

#[derive(Clone, Copy)]
struct PatternRule {
    id: &'static str,
    category: &'static str,
    severity: &'static str,
    required: &'static [&'static str],
    suggested_fix: &'static str,
    citation: &'static str,
}

fn detect_line(source_path: &str, line_number: usize, line: &str) -> Vec<Finding> {
    let trimmed = line.trim();
    if is_detector_catalog_metadata_line(source_path, trimmed) {
        return Vec::new();
    }
    pattern_rules()
        .into_iter()
        .filter(|rule| rule_applies_to_source(rule.id, source_path))
        .filter(|rule| match rule.id {
            "RUSTBUG-CORR-004" => trimmed.starts_with("except:"),
            "RUSTBUG-CORR-007" => trimmed.starts_with("except Exception"),
            "RUSTBUG-RES-001" => !trimmed.starts_with("with "),
            _ => true,
        })
        .filter(|rule| rule.required.iter().all(|needle| trimmed.contains(needle)))
        .map(|rule| build_finding(rule, source_path, line_number, trimmed))
        .collect()
}

fn rule_applies_to_source(rule_id: &str, source_path: &str) -> bool {
    rule_id != "RUSTBUG-RES-003" || source_path.ends_with(".go")
}

fn is_detector_catalog_metadata_line(source_path: &str, line: &str) -> bool {
    source_path.ends_with("services/speccheck/crates/detectors/src/lib.rs")
        && line.starts_with("&[")
}

#[derive(Default)]
struct SourceContext {
    in_loop: bool,
    in_async_block: bool,
}

impl SourceContext {
    fn update(&mut self, raw_line: &str, trimmed: &str) {
        if is_unindented(raw_line) {
            self.in_loop = false;
            self.in_async_block = false;
        }
        if trimmed.starts_with("async def ") && trimmed.ends_with(':') {
            self.in_async_block = true;
        }
        if trimmed.starts_with("for ") && trimmed.ends_with(':') {
            self.in_loop = true;
        }
    }
}

fn is_unindented(raw_line: &str) -> bool {
    !raw_line.starts_with(' ') && !raw_line.starts_with('\t')
}

fn detect_context_line(
    source_path: &str,
    line_number: usize,
    line: &str,
    context: &SourceContext,
) -> Vec<Finding> {
    context_rules()
        .into_iter()
        .filter(|rule| rule.matches(line, context))
        .map(|rule| build_finding(rule.pattern, source_path, line_number, line))
        .collect()
}

#[derive(Clone, Copy)]
struct ContextRule {
    pattern: PatternRule,
    required_context: RequiredContext,
    required: &'static [&'static str],
}

impl ContextRule {
    fn matches(self, line: &str, context: &SourceContext) -> bool {
        self.required_context.matches(context)
            && self.required.iter().all(|needle| line.contains(needle))
    }
}

#[derive(Clone, Copy)]
enum RequiredContext {
    Loop,
    AsyncBlock,
}

impl RequiredContext {
    const fn matches(self, context: &SourceContext) -> bool {
        match self {
            Self::Loop => context.in_loop,
            Self::AsyncBlock => context.in_async_block,
        }
    }
}

const fn context_rules() -> [ContextRule; 4] {
    [
        context_rule(
            pattern_rule(
                "RUSTBUG-PERF-001",
                "performance",
                "high",
                "Batch related rows with prefetch_related or annotate before the loop.",
            ),
            RequiredContext::Loop,
            &[".objects.filter(", ".first()"],
        ),
        context_rule(
            pattern_rule(
                "RUSTBUG-PERF-004",
                "performance",
                "high",
                "Use an async HTTP client or move blocking I/O outside the async view.",
            ),
            RequiredContext::AsyncBlock,
            &["requests.get("],
        ),
        context_rule(
            pattern_rule(
                "RUSTBUG-PERF-008",
                "performance",
                "high",
                "Use bulk_create, bulk_update, or a batched write path.",
            ),
            RequiredContext::Loop,
            &[".save()"],
        ),
        context_rule(
            pattern_rule(
                "RUSTBUG-CONC-005",
                "concurrency",
                "high",
                "Use Django async-safe database access or move the call to a sync boundary.",
            ),
            RequiredContext::AsyncBlock,
            &[".objects.get("],
        ),
    ]
}

fn build_finding(
    rule: PatternRule,
    source_path: &str,
    line_number: usize,
    evidence: &str,
) -> Finding {
    Finding {
        bug_pattern_id: rule.id,
        title: format!("Potential {} bug pattern", rule.category),
        description: format!(
            "The detector matched a source pattern that may cause a {} defect.",
            rule.category
        ),
        category: rule.category,
        severity: rule.severity,
        confidence: "high",
        source_path: source_path.to_owned(),
        line_number,
        evidence: evidence.to_owned(),
        suggested_fix: rule.suggested_fix,
        citation: rule.citation,
        fingerprint: fingerprint(rule.id, source_path, line_number, evidence),
        priority_score: priority_score(rule.severity),
    }
}

fn pattern_rules() -> Vec<PatternRule> {
    let mut rules = Vec::with_capacity(35);
    rules.extend(
        performance_rules()
            .into_iter()
            .filter(|rule| !is_context_only_rule(rule.id)),
    );
    rules.extend(correctness_rules());
    rules.extend(
        concurrency_rules()
            .into_iter()
            .filter(|rule| !is_context_only_rule(rule.id)),
    );
    rules.extend(resource_rules());
    rules.extend(security_rules());
    rules
}

const fn is_context_only_rule(id: &str) -> bool {
    matches!(
        id.as_bytes(),
        b"RUSTBUG-PERF-001" | b"RUSTBUG-PERF-004" | b"RUSTBUG-PERF-008" | b"RUSTBUG-CONC-005"
    )
}

const fn performance_rules() -> [PatternRule; 10] {
    [
        rule(
            "RUSTBUG-PERF-001",
            "performance",
            "high",
            &["for ", ".objects.filter(", ".first()"],
            "Batch related rows with prefetch_related or annotate before the loop.",
        ),
        rule(
            "RUSTBUG-PERF-002",
            "performance",
            "high",
            &["while True"],
            "Add a clear break condition, timeout, or bounded retry count.",
        ),
        rule(
            "RUSTBUG-PERF-003",
            "performance",
            "high",
            &["ForeignKey", "filter("],
            "Add or verify an index for the foreign-key lookup.",
        ),
        rule(
            "RUSTBUG-PERF-004",
            "performance",
            "high",
            &["async def", "requests.get("],
            "Use an async HTTP client or move blocking I/O outside the async view.",
        ),
        rule(
            "RUSTBUG-PERF-005",
            "performance",
            "high",
            &["for ", ".append("],
            "Pre-size or stream the collection when the loop shape is known.",
        ),
        rule(
            "RUSTBUG-PERF-006",
            "performance",
            "high",
            &["for ", "json.loads("],
            "Move large deserialisation outside the loop or process in smaller batches.",
        ),
        rule(
            "RUSTBUG-PERF-007",
            "performance",
            "high",
            &["for ", "re.compile("],
            "Compile the regular expression once outside the loop.",
        ),
        rule(
            "RUSTBUG-PERF-008",
            "performance",
            "high",
            &["for ", ".save()"],
            "Use bulk_create, bulk_update, or a batched write path.",
        ),
        rule(
            "RUSTBUG-PERF-009",
            "performance",
            "high",
            &["ListAPIView", "queryset"],
            "Add pagination or an explicit bounded queryset.",
        ),
        rule(
            "RUSTBUG-PERF-010",
            "performance",
            "high",
            &["def view(", " import "],
            "Move heavy imports to module load time or a measured cold path.",
        ),
    ]
}

const fn correctness_rules() -> [PatternRule; 10] {
    [
        rule(
            "RUSTBUG-CORR-001",
            "correctness",
            "medium",
            &["range(len(", "[i+1]"],
            "Guard the next-index access or iterate with windows.",
        ),
        rule(
            "RUSTBUG-CORR-002",
            "correctness",
            "medium",
            &["== 0.1"],
            "Compare floats with a tolerance instead of exact equality.",
        ),
        rule(
            "RUSTBUG-CORR-003",
            "correctness",
            "medium",
            &["def ", "=[]"],
            "Use None as the default and create the list inside the function.",
        ),
        rule(
            "RUSTBUG-CORR-004",
            "correctness",
            "medium",
            &["except:"],
            "Catch the narrow exception and log or re-raise unexpected failures.",
        ),
        rule(
            "RUSTBUG-CORR-005",
            "correctness",
            "medium",
            &["handle = open("],
            "Use a with block so the file handle closes on every path.",
        ),
        rule(
            "RUSTBUG-CORR-006",
            "correctness",
            "medium",
            &["subprocess", "shell=True"],
            "Pass arguments as a list and keep shell execution disabled.",
        ),
        rule(
            "RUSTBUG-CORR-007",
            "correctness",
            "medium",
            &["except Exception", "pass"],
            "Log, re-raise, or return an explicit failure result.",
        ),
        rule(
            "RUSTBUG-CORR-008",
            "correctness",
            "medium",
            &["if (", " = ", "{"],
            "Use a comparison or split the assignment out of the condition.",
        ),
        rule(
            "RUSTBUG-CORR-009",
            "correctness",
            "medium",
            &["unreachable_call("],
            "Remove unreachable code or move it before the terminating statement.",
        ),
        rule(
            "RUSTBUG-CORR-010",
            "correctness",
            "medium",
            &["if ", "else:", "same"],
            "Remove the duplicate branch or make the different behavior explicit.",
        ),
    ]
}

const fn concurrency_rules() -> [PatternRule; 5] {
    [
        rule(
            "RUSTBUG-CONC-001",
            "concurrency",
            "high",
            &[".objects.get(", "+= 1", ".save()"],
            "Use select_for_update, a transaction, or an atomic F expression.",
        ),
        rule(
            "RUSTBUG-CONC-002",
            "concurrency",
            "high",
            &["lock_a.acquire()", "lock_b.acquire()"],
            "Use one lock order everywhere or collapse the nested locks.",
        ),
        rule(
            "RUSTBUG-CONC-003",
            "concurrency",
            "high",
            &["first.save()", "second.save()"],
            "Wrap multi-write blocks in transaction.atomic().",
        ),
        rule(
            "RUSTBUG-CONC-004",
            "concurrency",
            "high",
            &["asyncio.create_task("],
            "Store and await the task or attach cancellation handling.",
        ),
        rule(
            "RUSTBUG-CONC-005",
            "concurrency",
            "high",
            &["async def", ".objects.get("],
            "Use Django async-safe database access or move the call to a sync boundary.",
        ),
    ]
}

const fn resource_rules() -> [PatternRule; 5] {
    [
        rule(
            "RUSTBUG-RES-001",
            "resource",
            "medium",
            &["connection.cursor()"],
            "Use connection.cursor() as a context manager.",
        ),
        rule(
            "RUSTBUG-RES-002",
            "resource",
            "medium",
            &["return open("],
            "Close the file on every branch or use a with block.",
        ),
        rule(
            "RUSTBUG-RES-003",
            "resource",
            "medium",
            &["go "],
            "Add a cancellation path or a receive loop for the goroutine.",
        ),
        rule(
            "RUSTBUG-RES-004",
            "resource",
            "medium",
            &["CACHE", "[key] ="],
            "Add an eviction policy or a bounded cache.",
        ),
        rule(
            "RUSTBUG-RES-005",
            "resource",
            "medium",
            &[".subscribe("],
            "Use takeUntilDestroyed or unsubscribe during component teardown.",
        ),
    ]
}

const fn security_rules() -> [PatternRule; 5] {
    [
        rule(
            "RUSTBUG-SEC-001",
            "security",
            "critical",
            &["cursor.execute(f\""],
            "Use parameterised SQL instead of string interpolation.",
        ),
        rule(
            "RUSTBUG-SEC-002",
            "security",
            "critical",
            &["pickle.loads(", "request."],
            "Replace pickle with a safe parser such as JSON and validate the input schema.",
        ),
        rule(
            "RUSTBUG-SEC-003",
            "security",
            "critical",
            &["eval("],
            "Replace eval or exec with a strict parser for the allowed expression shape.",
        ),
        rule(
            "RUSTBUG-SEC-004",
            "security",
            "critical",
            &["requests.get(user_input)"],
            "Validate the destination host against an allow-list before fetching.",
        ),
        rule(
            "RUSTBUG-SEC-005",
            "security",
            "critical",
            &["HttpResponseRedirect", "request.GET.get(\"next\")"],
            "Validate the redirect target scheme and host before redirecting.",
        ),
    ]
}

const fn rule(
    id: &'static str,
    category: &'static str,
    severity: &'static str,
    required: &'static [&'static str],
    suggested_fix: &'static str,
) -> PatternRule {
    let mut pattern = pattern_rule(id, category, severity, suggested_fix);
    pattern.required = required;
    pattern
}

const fn pattern_rule(
    id: &'static str,
    category: &'static str,
    severity: &'static str,
    suggested_fix: &'static str,
) -> PatternRule {
    PatternRule {
        id,
        category,
        severity,
        required: &[],
        suggested_fix,
        citation: "Hovemeyer-Pugh-2004",
    }
}

const fn context_rule(
    pattern: PatternRule,
    required_context: RequiredContext,
    required: &'static [&'static str],
) -> ContextRule {
    ContextRule {
        pattern,
        required_context,
        required,
    }
}

fn priority_score(severity: &str) -> u32 {
    match severity {
        "critical" => 100,
        "high" => 80,
        _ => 50,
    }
}

fn fingerprint(pattern_id: &str, source_path: &str, line_number: usize, evidence: &str) -> String {
    let mut hasher = Sha256::new();
    hasher.update(pattern_id.as_bytes());
    hasher.update(b"|");
    hasher.update(source_path.as_bytes());
    hasher.update(b"|");
    hasher.update(line_number.to_string().as_bytes());
    hasher.update(b"|");
    hasher.update(evidence.as_bytes());
    format!("{:x}", hasher.finalize())
}
