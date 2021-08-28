from setuptools import setup
from Cython.Build import cythonize

setup(ext_modules=cythonize("src/SuperDuperMetroid/BPSPatch/BPS_Patcher.pyx", annotate=True))
