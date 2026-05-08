from setuptools import setup
from pybind11.setup_helpers import Pybind11Extension, build_ext
import sys

ext_modules = [
    Pybind11Extension(
        "l2norm",
        ["l2norm.cpp"],
        extra_compile_args=["-O3", "-march=native"]
        if sys.platform != "win32"
        else ["/O2", "/arch:AVX2"],
    ),
    Pybind11Extension(
        "scoring",
        ["scoring.cpp"],
        extra_compile_args=["-O3", "-std=c++17", "-march=native"]
        if sys.platform != "win32"
        else ["/O2", "/std:c++17", "/arch:AVX2"],
        libraries=["tbb"] if sys.platform != "win32" else [],
    ),
    Pybind11Extension(
        "texttok",
        ["texttok.cpp"],
        extra_compile_args=["-O3", "-std=c++17"]
        if sys.platform != "win32"
        else ["/O2", "/std:c++17"],
    ),
    Pybind11Extension(
        "simsearch",
        ["simsearch.cpp"],
        extra_compile_args=["-O3", "-std=c++17", "-march=native"]
        if sys.platform != "win32"
        else ["/O2", "/std:c++17", "/arch:AVX2"],
        libraries=["tbb"] if sys.platform != "win32" else [],
    ),
    Pybind11Extension(
        "pagerank",
        ["pagerank.cpp"],
        extra_compile_args=["-O3", "-std=c++17", "-march=native"]
        if sys.platform != "win32"
        else ["/O2", "/std:c++17", "/arch:AVX2"],
    ),
    Pybind11Extension(
        "phrasematch",
        ["phrasematch.cpp"],
        extra_compile_args=["-O3", "-std=c++17", "-march=native"]
        if sys.platform != "win32"
        else ["/O2", "/std:c++17", "/arch:AVX2"],
    ),
    Pybind11Extension(
        "fieldrel",
        ["fieldrel.cpp"],
        extra_compile_args=["-O3", "-std=c++17", "-march=native"]
        if sys.platform != "win32"
        else ["/O2", "/std:c++17", "/arch:AVX2"],
    ),
    Pybind11Extension(
        "rareterm",
        ["rareterm.cpp"],
        extra_compile_args=["-O3", "-std=c++17"]
        if sys.platform != "win32"
        else ["/O2", "/std:c++17"],
    ),
    Pybind11Extension(
        "linkparse",
        ["linkparse.cpp"],
        extra_compile_args=["-O3", "-std=c++17"]
        if sys.platform != "win32"
        else ["/O2", "/std:c++17"],
    ),
    Pybind11Extension(
        "feedrerank",
        ["feedrerank.cpp"],
        extra_compile_args=["-O3", "-std=c++17", "-march=native"]
        if sys.platform != "win32"
        else ["/O2", "/std:c++17", "/arch:AVX2"],
        libraries=["tbb"] if sys.platform != "win32" else [],
    ),
    Pybind11Extension(
        "anchor_diversity",
        ["anchor_diversity.cpp"],
        extra_compile_args=["-O3", "-std=c++17"]
        if sys.platform != "win32"
        else ["/O2", "/std:c++17"],
    ),
    # ── Anti-garbage anchor signals (3 algos, plan PR-Anchor) ─────
    # Each sits in its own extension per the one-kernel-per-.cpp
    # pattern. All three are tiny — well under the 64 MB RAM /
    # 64 MB disk caps the plan called for.
    Pybind11Extension(
        "generic_anchor_matcher",
        ["generic_anchor_matcher.cpp"],
        extra_compile_args=["-O3", "-std=c++17"]
        if sys.platform != "win32"
        else ["/O2", "/std:c++17"],
    ),
    Pybind11Extension(
        "anchor_descriptiveness",
        ["anchor_descriptiveness.cpp"],
        extra_compile_args=["-O3", "-std=c++17"]
        if sys.platform != "win32"
        else ["/O2", "/std:c++17"],
    ),
    Pybind11Extension(
        "anchor_self_information",
        ["anchor_self_information.cpp"],
        extra_compile_args=["-O3", "-std=c++17", "-march=native"]
        if sys.platform != "win32"
        else ["/O2", "/std:c++17", "/arch:AVX2"],
    ),
    Pybind11Extension(
        "pixie_walk",
        ["pixie_walk.cpp"],
        extra_compile_args=["-O3", "-std=c++17", "-march=native"]
        if sys.platform != "win32"
        else ["/O2", "/std:c++17", "/arch:AVX2"],
    ),
    Pybind11Extension(
        "quantemb",
        ["quantemb.cpp"],
        extra_compile_args=["-O3", "-std=c++17", "-march=native"]
        if sys.platform != "win32"
        else ["/O2", "/std:c++17", "/arch:AVX2"],
    ),
    Pybind11Extension(
        "passagesim",
        ["passagesim.cpp"],
        extra_compile_args=["-O3", "-std=c++17", "-march=native"]
        if sys.platform != "win32"
        else ["/O2", "/std:c++17", "/arch:AVX2"],
    ),
    Pybind11Extension(
        "ivf_index",
        ["ivf_index.cpp"],
        extra_compile_args=["-O3", "-std=c++17", "-march=native"]
        if sys.platform != "win32"
        else ["/O2", "/std:c++17", "/arch:AVX2"],
    ),
    Pybind11Extension(
        "counting_bloom",
        ["counting_bloom.cpp"],
        extra_compile_args=["-O3", "-std=c++17"]
        if sys.platform != "win32"
        else ["/O2", "/std:c++17"],
    ),
    Pybind11Extension(
        "compressed_bloom",
        ["compressed_bloom.cpp"],
        extra_compile_args=["-O3", "-std=c++17"]
        if sys.platform != "win32"
        else ["/O2", "/std:c++17"],
    ),
    Pybind11Extension(
        "count_min_sketch",
        ["count_min_sketch.cpp"],
        extra_compile_args=["-O3", "-std=c++17"]
        if sys.platform != "win32"
        else ["/O2", "/std:c++17"],
    ),
    # FR-250: outbound rate limiter for GSC, GA4, Matomo, XenForo, WordPress.
    # Spec: docs/specs/fr250-api-rate-limiter.md
    Pybind11Extension(
        "api_rate_limiter",
        ["api_rate_limiter.cpp"],
        extra_compile_args=["-O3", "-std=c++17"]
        if sys.platform != "win32"
        else ["/O2", "/std:c++17"],
    ),
]


setup(
    name="xf_linker_extensions",
    version="0.1.0",
    ext_modules=ext_modules,
    cmdclass={"build_ext": build_ext},
)
