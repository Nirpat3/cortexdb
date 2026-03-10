"""
Shared pytest configuration and fixtures for CortexDB tests.
"""

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
