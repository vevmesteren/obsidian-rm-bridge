"""Legacy setup.py shim — enables `pip install -e .` on older pip/setuptools
that don't support PEP 660 (build_editable hook). All config lives in
pyproject.toml; this just delegates to setuptools.
"""
from setuptools import setup

setup()