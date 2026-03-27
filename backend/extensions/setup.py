from setuptools import setup, Extension
from pybind11.setup_helpers import Pybind11Extension, build_ext
import sys

ext_modules = [
    Pybind11Extension(
        "l2norm",
        ["l2norm.cpp"],
        extra_compile_args=["-O3", "-march=native"] if sys.platform != "win32" else ["/O2", "/arch:AVX2"],
    ),
    Pybind11Extension(
        "strpool",
        ["strpool.cpp"],
        extra_compile_args=["-O3"] if sys.platform != "win32" else ["/O2"],
    ),
    Pybind11Extension(
        "scoring",
        ["scoring.cpp"],
        extra_compile_args=["-O3", "-std=c++17"] if sys.platform != "win32" else ["/O2", "/std:c++17"],
        libraries=["tbb"] if sys.platform != "win32" else [],
    ),
    Pybind11Extension(
        "inv_index",
        ["inv_index.cpp"],
        extra_compile_args=["-O3"] if sys.platform != "win32" else ["/O2"],
    ),
]

setup(
    name="xf_linker_extensions",
    version="0.1.0",
    ext_modules=ext_modules,
    cmdclass={"build_ext": build_ext},
)
