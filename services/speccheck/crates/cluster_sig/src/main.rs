//! `cluster-sig` — the Rust speed-tier binary the Go `clusterd` service shells
//! out to. Reads `{"items":[[u64,...],...]}` from stdin, computes candidate
//! near-duplicate edges via `speccheck_cluster_core::edges`, and writes
//! `{"edges":[{"a":i,"b":j,"sim":f},...]}` to stdout.

#![forbid(unsafe_code)]
#![allow(clippy::pedantic, clippy::nursery, clippy::cargo)]
use std::io::{self, Read, Write};

use serde::{Deserialize, Serialize};
use speccheck_cluster_core::{edges_with_params, Params};

#[derive(Deserialize)]
struct Input {
    items: Vec<Vec<u64>>,
    #[serde(default)]
    signature_len: Option<usize>,
    #[serde(default)]
    bands: Option<usize>,
    #[serde(default)]
    rows: Option<usize>,
}

#[derive(Serialize)]
struct OutEdge {
    a: usize,
    b: usize,
    sim: f64,
}

#[derive(Serialize)]
struct Output {
    edges: Vec<OutEdge>,
}

fn run(raw: &str) -> Result<String, serde_json::Error> {
    let input: Input = serde_json::from_str(raw)?;
    let defaults = Params::default();
    let params = Params {
        signature_len: input.signature_len.unwrap_or(defaults.signature_len),
        bands: input.bands.unwrap_or(defaults.bands),
        rows: input.rows.unwrap_or(defaults.rows),
    };
    let computed = edges_with_params(&input.items, params);
    let out = Output {
        edges: computed
            .into_iter()
            .map(|(a, b, sim)| OutEdge { a, b, sim })
            .collect(),
    };
    serde_json::to_string(&out)
}

fn main() -> io::Result<()> {
    let mut raw = String::new();
    io::stdin().read_to_string(&mut raw)?;
    let rendered = run(&raw).map_err(|e| io::Error::new(io::ErrorKind::InvalidData, e))?;
    io::stdout().write_all(rendered.as_bytes())?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::run;

    #[test]
    fn run_emits_edges_for_near_duplicates() {
        // Two large, highly-overlapping feature sets reliably collide under
        // LSH; a disjoint third set does not. (Tiny sets with 8-row bands rarely
        // collide even at moderate similarity, so use sets big enough to band.)
        let mut shared: Vec<u64> = (0..120).collect();
        let near = shared.clone();
        let far: Vec<u64> = (9000..9120).collect();
        shared.truncate(120);
        let input = format!(
            r#"{{"items":[{},{},{}]}}"#,
            as_json(&shared),
            as_json(&near),
            as_json(&far)
        );
        let out = run(&input).expect("valid input");
        assert!(
            out.contains("\"a\":0"),
            "expected an edge from item 0: {out}"
        );
        assert!(out.starts_with("{\"edges\":"));
    }

    fn as_json(values: &[u64]) -> String {
        let parts: Vec<String> = values.iter().map(ToString::to_string).collect();
        format!("[{}]", parts.join(","))
    }

    #[test]
    fn run_rejects_malformed_json() {
        assert!(run("not json").is_err());
    }

    #[test]
    fn run_accepts_custom_params() {
        let big = as_json(&(0..120).collect::<Vec<u64>>());
        let input = format!(r#"{{"items":[{big},{big}],"signature_len":32,"bands":4,"rows":8}}"#);
        let out = run(&input).expect("valid input with custom params");
        assert!(
            out.contains("\"a\":0"),
            "expected an edge with custom params: {out}"
        );
    }

    #[test]
    fn run_defaults_params_when_absent() {
        let big = as_json(&(0..120).collect::<Vec<u64>>());
        let input = format!(r#"{{"items":[{big},{big}]}}"#);
        assert!(run(&input).is_ok(), "params are optional");
    }
}
