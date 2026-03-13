"""
Shared pytest configuration and fixtures for CortexDB tests.
"""

import sys
import os

# The project root contains a cortexdb/ directory (extended modules) that
# shadows src/cortexdb/ (the active source tree). Since pytest adds '' (cwd)
# to sys.path, the wrong package gets imported. Fix: ensure src/ wins.
_src = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, "src"))
_root = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
# Remove entries that would resolve to the shadowing cortexdb/ package
sys.path = [p for p in sys.path if os.path.abspath(p or ".") != _root]
sys.path.insert(0, _src)
# Clear any already-cached wrong import
for _k in list(sys.modules):
    if _k == "cortexdb" or _k.startswith("cortexdb."):
        _mod = sys.modules[_k]
        if hasattr(_mod, "__file__") and _mod.__file__ and _src not in (_mod.__file__ or ""):
            del sys.modules[_k]

import pytest

BASE_URL = "http://localhost:5400"


def pytest_addoption(parser):
    """Add shared CLI options for all test suites."""
    for name, kwargs in [
        ("--cortexdb-url", {"default": BASE_URL, "help": "CortexDB base URL"}),
        ("--benchmark-url", {"default": BASE_URL, "help": "CortexDB base URL for benchmarks"}),
        ("--benchmark-iterations", {"default": 100, "type": int, "help": "Benchmark iterations"}),
        ("--stress-url", {"default": BASE_URL, "help": "CortexDB base URL for stress tests"}),
        ("--pentest-url", {"default": BASE_URL, "help": "CortexDB target URL for pentests"}),
        ("--stress-duration", {"default": 30, "type": int, "help": "Stress test duration in seconds"}),
        ("--stress-rps", {"default": 100, "type": int, "help": "Stress test target RPS"}),
        ("--stress-concurrency", {"default": 50, "type": int, "help": "Stress test concurrency"}),
    ]:
        try:
            parser.addoption(name, **kwargs)
        except ValueError:
            pass  # Already added


@pytest.fixture
def cortexdb_url(request):
    return request.config.getoption("--cortexdb-url", default=BASE_URL)
