"""Benchmarks for the hardware-profile auto-tuner (plan Part 8a, FR-233).

Three input sizes satisfy the mandatory-benchmark rule by exercising the
recommender at every currently-supported vector dimension: 1024 (BGE-M3),
1536 (OpenAI text-embedding-3-small), 3072 (OpenAI text-embedding-3-large).
"""

from __future__ import annotations


def _import_hp():
    from apps.pipeline.services.hardware_profile import (
        HardwareProfile,
        recommended_batch_size,
    )

    return HardwareProfile, recommended_batch_size


def _sample_profile(HardwareProfile):
    # A realistic mid-range workstation so the recommender actually exercises
    # the clamp logic rather than bottoming out at the minimum.
    return HardwareProfile(
        ram_gb=32.0,
        cpu_cores=16,
        vram_gb=8.0,
        has_cuda=True,
        tier="high",
    )


def test_bench_batch_size_small_dim(benchmark):
    HardwareProfile, recommended_batch_size = _import_hp()
    profile = _sample_profile(HardwareProfile)
    benchmark(recommended_batch_size, dimension=1024, profile=profile)


def test_bench_batch_size_medium_dim(benchmark):
    HardwareProfile, recommended_batch_size = _import_hp()
    profile = _sample_profile(HardwareProfile)
    benchmark(recommended_batch_size, dimension=1536, profile=profile)


def test_bench_batch_size_large_dim(benchmark):
    HardwareProfile, recommended_batch_size = _import_hp()
    profile = _sample_profile(HardwareProfile)
    benchmark(recommended_batch_size, dimension=3072, profile=profile)
