"""Unit tests for database.py core components: Amygdala (P1.2), R0 TTLCache (P1.1), Degradation (P2.6)."""

import time
import pytest
from unittest.mock import MagicMock, AsyncMock


class TestAmygdala:
    """Test Amygdala alert-only security model (P1.2)."""

    def setup_method(self):
        from cortexdb.core.database import Amygdala
        self.amygdala = Amygdala(strict_mode=False)

    def test_clean_query_allowed(self):
        verdict = self.amygdala.assess("SELECT * FROM agents WHERE id = $1")
        assert verdict.allowed is True
        assert verdict.threat_score == 0.0

    def test_injection_pattern_alerts_but_allows(self):
        """Injection patterns should alert but NOT block."""
        verdict = self.amygdala.assess("SELECT * FROM users WHERE 1=1")
        assert verdict.allowed is True  # Alert only, not blocked
        assert len(verdict.threats_detected) > 0
        assert self.amygdala._alerts_total > 0

    def test_code_execution_blocked(self):
        verdict = self.amygdala.assess("eval('malicious code')")
        assert verdict.allowed is False

    def test_os_system_blocked(self):
        verdict = self.amygdala.assess("os.system('rm -rf /')")
        assert verdict.allowed is False

    def test_protected_table_dml_blocked(self):
        verdict = self.amygdala.assess("DELETE FROM COMPLIANCE_AUDIT_LOG WHERE id = 1")
        assert verdict.allowed is False

    def test_protected_table_select_allowed(self):
        verdict = self.amygdala.assess("SELECT * FROM COMPLIANCE_AUDIT_LOG")
        assert verdict.allowed is True

    def test_excessive_quotes_blocked(self):
        verdict = self.amygdala.assess("'" * 20 + "some query")
        assert verdict.allowed is False

    def test_strict_mode_blocks_embedded_values(self):
        from cortexdb.core.database import Amygdala
        strict = Amygdala(strict_mode=True)
        verdict = strict.assess("SELECT * FROM users WHERE name = 'bob'")
        assert verdict.allowed is False
        assert any("STRICT_MODE" in t for t in verdict.threats_detected)

    def test_strict_mode_allows_parameterized(self):
        from cortexdb.core.database import Amygdala
        strict = Amygdala(strict_mode=True)
        verdict = strict.assess("SELECT * FROM users WHERE name = $1")
        assert verdict.allowed is True

    def test_latency_sub_millisecond(self):
        verdict = self.amygdala.assess("SELECT 1")
        assert verdict.latency_us < 1000  # < 1ms

    def test_stats(self):
        self.amygdala.assess("SELECT 1")
        self.amygdala.assess("eval('bad')")
        stats = self.amygdala.stats
        assert stats["checks_total"] == 2
        assert stats["blocks_total"] == 1

    def test_union_select_alerts(self):
        verdict = self.amygdala.assess("SELECT id FROM users UNION SELECT password FROM admins")
        assert verdict.allowed is True  # Alert only
        assert len(verdict.threats_detected) > 0


class TestR0TTLCache:
    """Test R0 process-local cache uses TTLCache (P1.1)."""

    def test_r0_is_ttlcache(self):
        from cachetools import TTLCache
        from cortexdb.core.database import ReadCascade
        engines = {"relational": MagicMock()}
        rc = ReadCascade(engines)
        assert isinstance(rc._r0_cache, TTLCache)

    def test_r0_maxsize(self):
        from cortexdb.core.database import ReadCascade
        engines = {"relational": MagicMock()}
        rc = ReadCascade(engines)
        assert rc._r0_cache.maxsize == 10000

    def test_r0_ttl(self):
        from cortexdb.core.database import ReadCascade
        engines = {"relational": MagicMock()}
        rc = ReadCascade(engines)
        assert rc._r0_cache.ttl == 300

    def test_r0_set_get(self):
        from cortexdb.core.database import ReadCascade
        engines = {"relational": MagicMock()}
        rc = ReadCascade(engines)
        rc._r0_set("key1", {"data": "value"})
        assert rc._r0_cache.get("key1") == {"data": "value"}

    def test_r0_eviction_by_maxsize(self):
        from cachetools import TTLCache
        # Small cache to test eviction
        cache = TTLCache(maxsize=3, ttl=300)
        cache["a"] = 1
        cache["b"] = 2
        cache["c"] = 3
        cache["d"] = 4  # Should evict "a"
        assert "a" not in cache
        assert "d" in cache
