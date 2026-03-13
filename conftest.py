# Root conftest — ensures src/cortexdb/ is imported instead of cortexdb/cortexdb/
import sys
import os

_src = os.path.abspath(os.path.join(os.path.dirname(__file__), "src"))
_root = os.path.abspath(os.path.dirname(__file__))


def pytest_configure(config):
    """Earliest pytest hook — fix sys.path before any test collection."""
    # Remove rootdir from sys.path (it contains cortexdb/ that shadows src/cortexdb/)
    sys.path[:] = [p for p in sys.path if os.path.abspath(p or ".") != _root]
    sys.path.insert(0, _src)
    # Purge any cortexdb modules loaded from the wrong location
    for key in list(sys.modules):
        if key == "cortexdb" or key.startswith("cortexdb."):
            mod = sys.modules[key]
            if hasattr(mod, "__file__") and mod.__file__ and "/src/" not in (mod.__file__ or ""):
                del sys.modules[key]
