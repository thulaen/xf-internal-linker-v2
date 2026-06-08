//! Host fingerprint seed tests.

#[test]
fn test_when_host_facts_are_provided_then_seed_is_stable() {
    let seed = speccheck_host_fingerprint::fingerprint_seed("cpu", 8, 32, "linux");

    assert_eq!(seed, "cpu|8|32|linux");
}
