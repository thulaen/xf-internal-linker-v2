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
]

setup(
    name="xf_linker_extensions",
    version="0.1.0",
    ext_modules=ext_modules,
    cmdclass={"build_ext": build_ext},
)
