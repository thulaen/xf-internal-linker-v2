//! Criterion benchmark for the ASCII tokenizer kernel core.
//!
//! Benchmarks the plain-Rust `tokenize_text_batch_core` over three input sizes,
//! matching the Mandatory Benchmark Rule (3 input sizes per hot path) and
//! `RUST-FIRST.md` Pattern step 5. Each input is a batch of synthetic
//! prose-like strings with punctuation, contractions, and repeats so the
//! tokenizer exercises the separator-skip, lowercase, apostrophe-fold, and
//! stopword-drop paths rather than a trivial single-token string.

use std::collections::HashSet;

use criterion::{criterion_group, criterion_main, BenchmarkId, Criterion};
use texttok::tokenize_text_batch_core;

/// Three representative batch shapes: a small slate, a typical scoring batch,
/// and a large flush. Each entry is `(number_of_texts, words_per_text)`.
const SHAPES: [(usize, usize); 3] = [(16, 32), (128, 64), (512, 96)];

fn stopwords() -> HashSet<String> {
    [
        "the", "a", "and", "of", "to", "in", "is", "it", "don't", "you've",
    ]
    .iter()
    .map(|w| (*w).to_string())
    .collect()
}

fn make_texts(count: usize, words: usize) -> Vec<String> {
    // A small rotating vocabulary with punctuation and contractions so the
    // tokenizer hits every branch (separators, apostrophe fold, stopword drop,
    // duplicate collapse). Deterministic so runs are comparable.
    let vocab = [
        "Hello,",
        "World!",
        "don't",
        "you've",
        "Quick-brown",
        "FOX",
        "the",
        "lazy",
        "Dog.",
        "42",
        "rock'n'roll",
        "café",
    ];
    (0..count)
        .map(|t| {
            let mut s = String::new();
            for w in 0..words {
                if w > 0 {
                    s.push(' ');
                }
                s.push_str(vocab[(t + w) % vocab.len()]);
            }
            s
        })
        .collect()
}

fn bench_tokenize_batch(c: &mut Criterion) {
    let stops = stopwords();
    let mut group = c.benchmark_group("tokenize_text_batch_core");
    for (count, words) in SHAPES {
        let texts = make_texts(count, words);
        group.bench_with_input(
            BenchmarkId::from_parameter(format!("{count}x{words}")),
            &texts,
            |b, texts| {
                b.iter(|| tokenize_text_batch_core(texts, &stops));
            },
        );
    }
    group.finish();
}

criterion_group!(benches, bench_tokenize_batch);
criterion_main!(benches);
