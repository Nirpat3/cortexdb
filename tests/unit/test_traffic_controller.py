"""Unit tests for TrafficController (P2.7)."""

import pytest
from unittest.mock import MagicMock
from cortexdb.core.traffic_controller import TrafficController, TrafficState


class TestTrafficController:
    def test_initial_state_healthy(self):
        tc = TrafficController(db=MagicMock(), circuits=None)
        assert tc._state == TrafficState.HEALTHY

    def test_degraded_when_db_degraded(self):
        db = MagicMock()
        db._degraded_mode = True
        tc = TrafficController(db=db, circuits=None)
        tc._last_check = 0  # Force recalculation
        tc._recalculate_state()
        assert tc._state == TrafficState.DEGRADED

    def test_critical_when_many_circuits_open(self):
        db = MagicMock()
        db._degraded_mode = False
        tc = TrafficController(db=db, circuits=None)
        circuits = MagicMock()
        circuits.get_all_states.return_value = {
            "relational": {"state": "open"},
            "memory": {"state": "open"},
            "vector": {"state": "open"},
        }
        tc._circuits = circuits
        tc._last_check = 0
        tc._recalculate_state()
        assert tc._state == TrafficState.CRITICAL

    def test_healthy_when_all_closed(self):
        db = MagicMock()
        db._degraded_mode = False
        db.engines = {"relational": 1, "memory": 1, "vector": 1,
                      "stream": 1, "temporal": 1, "graph": 1, "immutable": 1}
        tc = TrafficController(db=db, circuits=None)
        circuits = MagicMock()
        circuits.get_all_states.return_value = {
            "relational": {"state": "closed"},
            "memory": {"state": "closed"},
        }
        tc._circuits = circuits
        tc._last_check = 0
        tc._recalculate_state()
        assert tc._state == TrafficState.HEALTHY

    def test_should_accept_all_when_healthy(self):
        db = MagicMock()
        db._degraded_mode = False
        db.engines = {f"e{i}": 1 for i in range(7)}
        tc = TrafficController(db=db, circuits=None)
        tc._state = TrafficState.HEALTHY
        accept, code, retry = tc.should_accept("/v1/query", "GET")
        assert accept is True
        accept, code, retry = tc.should_accept("/v1/write", "POST")
        assert accept is True

    def test_should_reject_writes_when_degraded(self):
        tc = TrafficController(db=MagicMock(), circuits=None)
        tc._state = TrafficState.DEGRADED
        tc._check_interval = 9999  # Prevent recalculation
        accept, code, retry = tc.should_accept("/v1/query", "GET")
        assert accept is True
        accept, code, retry = tc.should_accept("/v1/write", "POST")
        assert accept is False
        assert code == 503

    def test_should_reject_all_when_critical(self):
        db = MagicMock()
        db._degraded_mode = False
        db.engines = {}  # No engines = critical
        tc = TrafficController(db=db, circuits=None)
        tc._state = TrafficState.CRITICAL
        tc._check_interval = 9999
        accept, code, retry = tc.should_accept("/v1/query", "GET")
        assert accept is False
        accept, code, retry = tc.should_accept("/v1/write", "POST")
        assert accept is False

    def test_health_endpoints_always_accepted(self):
        tc = TrafficController(db=MagicMock(), circuits=None)
        tc._state = TrafficState.CRITICAL
        accept, code, retry = tc.should_accept("/health", "GET")
        assert accept is True
        accept, code, retry = tc.should_accept("/health/live", "GET")
        assert accept is True

    def test_get_status(self):
        db = MagicMock()
        db._degraded_mode = False
        db.engines = {f"e{i}": 1 for i in range(7)}
        tc = TrafficController(db=db, circuits=None)
        status = tc.get_status()
        assert status["state"] == TrafficState.HEALTHY
        assert "rejected_total" in status
