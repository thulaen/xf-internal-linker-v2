# FR-140 — Fourier Periodicity Strength

## Overview
Some forum content is genuinely periodic (weekly NFL discussion, monthly subscription-day spike) while other content has no detectable cycle. Fourier analysis quantifies the strength of dominant periodicities by computing the power spectrum and locating spectral peaks. FR-140 complements FR-137 (STL, which decomposes a *known* period) by *discovering* the dominant period from data, then scoring how concentrated the spectrum is around that peak. Pages with strong, consistent periodicity get a "predictable" boost; flat-spectrum pages get neutral.

## Academic source
Stoica, P. and Moses, R. *Spectral Analysis of Signals*. Prentice Hall, 2005. ISBN: 978-0131139565. (Foundational reference on periodogram, Welch method, and frequency-domain peak detection.) Also: Welch, P. D. "The use of fast Fourier transform for the estimation of power spectra." *IEEE Transactions on Audio and Electroacoustics*, 15(2), pp. 70–73, 1967. DOI: 10.1109/TAU.1967.1161901.

## Formula
For zero-mean series `x_t, t = 0..n−1`, the Discrete Fourier Transform is

```
X_k = Σ_{t=0..n−1} x_t · exp(−i 2π k t / n),    k = 0..n−1
```

and the periodogram (power spectral density estimate) is

```
P_k = (1/n) · |X_k|²
```

The dominant frequency is `k* = argmax_{k ∈ [1, n/2]} P_k` and the dominant period is `τ* = n / k*`. Periodicity strength is the ratio of dominant peak power to total power:

```
periodicity_strength = P_{k*} / Σ_{k=1..n/2} P_k
```

For Welch's method (more robust): split `x` into K overlapping segments of length L, apply Hann window `w_t = 0.5 (1 − cos(2π t/(L−1)))`, compute periodogram per segment, average:

```
P_k^{Welch} = (1/K) Σ_{j=1..K} P_k^{(j)}
```

Spectral entropy (low entropy = strong single peak):

```
H = − Σ_k p_k ln p_k,    p_k = P_k / Σ_j P_j
H_normalised = H / ln(n/2)
```

## Starting weight preset
```python
"fourier_periodicity.enabled": "true",
"fourier_periodicity.ranking_weight": "0.0",
"fourier_periodicity.welch_segment_length": "64",
"fourier_periodicity.welch_overlap_fraction": "0.5",
"fourier_periodicity.min_observations": "32",
```

## C++ implementation
- File: `backend/extensions/fourier_periodicity.cpp`
- Entry: `FourierResult fourier_periodicity(const double* x, int n, int seg_len, double overlap)`
- Complexity: O(n log n) via FFTW3 or pocketfft. Welch with K segments: O(K · L log L) ≈ O(n log L).
- Thread-safety: FFTW3 plans are reusable but not thread-safe to *create*; create once at module init under mutex, then reuse. SIMD: handled internally by FFT library. Memory: O(n) for the input buffer + O(L) for window and per-segment output.

## Python fallback
`backend/apps/pipeline/services/fourier_periodicity.py::compute_periodicity` (mirrors `scipy.signal.welch`).

## Benchmark plan
| n samples | Python (ms) | C++ target (ms) | Speedup |
|---|---|---|---|
| 256 | 8 | <1 | ≥8x |
| 65,536 | 1,200 | <100 | ≥12x |
| 4,194,304 | 95,000 | <8,000 | ≥11x |

## Diagnostics
UI: numeric "dominant period: 7 days, strength 0.42". Debug fields: `dominant_period_samples`, `dominant_period_days`, `peak_power`, `total_power`, `periodicity_strength`, `spectral_entropy`, `secondary_peak_period`.

## Edge cases & neutral fallback
n < min_observations → neutral 0.5. n not power-of-2 → zero-pad to next power-of-2 (FFTW handles arbitrary sizes but slower for primes). All-zero series → all `P_k = 0`, neutral fallback. Constant series → only `P_0 ≠ 0`; we exclude `k=0` so neutral. NaN values dropped pre-FFT. DC component (mean) subtracted before FFT to remove `k=0` artefact.

## Minimum-data threshold
At least 32 observations (one Welch segment); preferably 4+ segments for stable estimate.

## Budget
Disk: <1 MB  ·  RAM: <8 MB per page (FFT buffers freed after computation; FFTW plans cached)

## Scope boundary vs existing signals
FR-137 (STL) requires the period as input; FR-140 *discovers* the period. FR-141 (ACF) gives autocorrelation at a single lag; FR-140 gives the full spectrum. FR-141 and FR-140 are mathematical duals (Wiener-Khinchin theorem) but expose different practical insights — ACF is interpretable per-lag, FFT is interpretable per-frequency.

## Test plan bullets
- Pure sinusoid `x_t = sin(2π t / 7)` → dominant period exactly 7, strength > 0.95.
- White noise → strength < 0.05, spectral entropy near 1.0.
- Sum of two sinusoids → both peaks in `secondary_peak_period`.
- Constant series → neutral fallback.
- All-zero series → neutral fallback.
- NaN values dropped, no crash.
- Compare against `scipy.signal.welch`: identical peaks within FFT bin resolution.
- DC-component subtraction verified: mean offset does not change dominant frequency.
