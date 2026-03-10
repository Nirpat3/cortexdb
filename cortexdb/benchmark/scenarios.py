"""
Built-in Benchmark Scenarios — Pre-defined tests for each CortexDB subsystem.

Scenarios cover: read cascade, write fan-out, cache performance,
vector search, graph traversal, streaming, and compliance operations.
"""

import uuid
import time
import json
import random
import hashlib
from typing import Any, Dict, List


class ScenarioRegistry:
    """Factory for built-in benchmark scenarios targeting live engines."""

    def __init__(self, db=None, engines: Dict[str, Any] = None):
        self.db = db
        self.engines = engines or {}
        self._test_tenant = f"bench-{uuid.uuid4().hex[:8]}"
        self._test_data = self._generate_test_data()

    def _generate_test_data(self) -> Dict:
        """Pre-generate test data for benchmarks."""
        customers = []
        for i in range(100):
            customers.append({
                "id": str(uuid.uuid4()),
                "email": f"bench-{i}@test.cortexdb.io",
                "name": f"Benchmark User {i}",
                "tenant_id": self._test_tenant,
            })
        events = []
        for c in customers[:20]:
            for j in range(10):
                events.append({
                    "customer_id": c["id"],
                    "event_type": random.choice(["page_view", "purchase", "login", "search"]),
                    "properties": {"page": f"/product/{j}", "value": random.uniform(1, 500)},
                })
        vectors = [[random.uniform(-1, 1) for _ in range(384)] for _ in range(50)]
        return {"customers": customers, "events": events, "vectors": vectors}

    def get_all_scenarios(self) -> List[Dict]:
        """Return all available benchmark scenarios."""
        scenarios = [
            self.relational_insert(),
            self.relational_select(),
            self.relational_join(),
            self.cache_r0_hit(),
            self.cache_r1_redis(),
            self.cache_miss_fallback(),
            self.write_fanout(),
            self.vector_insert(),
            self.vector_search(),
            self.graph_create_edge(),
            self.stream_publish(),
            self.ledger_commit(),
            self.cortexql_parse(),
            self.amygdala_check(),
            self.encryption_roundtrip(),
            self.compliance_audit_log(),
        ]
        return [s for s in scenarios if s is not None]

    def get_quick_scenarios(self) -> List[Dict]:
        """Return a fast subset for quick health benchmarks."""
        return [
            self.relational_insert(),
            self.relational_select(),
            self.cache_r0_hit(),
            self.cortexql_parse(),
            self.amygdala_check(),
        ]

    # ── RelationalCore (PostgreSQL) ──

    def relational_insert(self) -> Dict:
        async def _run():
            pool = self.engines.get("relational")
            if not pool:
                return
            uid = uuid.uuid4().hex[:12]
            async with pool.acquire() as conn:
                await conn.execute(
                    "INSERT INTO benchmark_scratch (id, data, created_at) "
                    "VALUES ($1, $2, NOW()) ON CONFLICT (id) DO UPDATE SET data = $2",
                    uid, json.dumps({"bench": True, "ts": time.time()})
                )
        return {"name": "relational_insert", "func": _run, "iterations": 2000, "warmup": 100}

    def relational_select(self) -> Dict:
        async def _run():
            pool = self.engines.get("relational")
            if not pool:
                return
            async with pool.acquire() as conn:
                await conn.fetch(
                    "SELECT id, data FROM benchmark_scratch ORDER BY created_at DESC LIMIT 10"
                )
        return {"name": "relational_select", "func": _run, "iterations": 5000, "warmup": 200}

    def relational_join(self) -> Dict:
        async def _run():
            pool = self.engines.get("relational")
            if not pool:
                return
            async with pool.acquire() as conn:
                await conn.fetch(
                    "SELECT c.id, c.email, COUNT(e.id) as event_count "
                    "FROM customers c LEFT JOIN customer_events e ON c.id = e.customer_id "
                    "WHERE c.tenant_id = $1 GROUP BY c.id, c.email LIMIT 20",
                    self._test_tenant
                )
        return {"name": "relational_join", "func": _run, "iterations": 1000, "warmup": 50}

    # ── Cache Tiers ──

    def cache_r0_hit(self) -> Dict:
        """Test R0 in-process cache (dict lookup)."""
        cache = {}
        for i in range(1000):
            cache[f"key-{i}"] = {"data": f"value-{i}", "ts": time.time()}

        async def _run():
            key = f"key-{random.randint(0, 999)}"
            _ = cache.get(key)
        return {"name": "cache_r0_hit", "func": _run, "iterations": 50000, "warmup": 500}

    def cache_r1_redis(self) -> Dict:
        async def _run():
            redis = self.engines.get("memory")
            if not redis:
                return
            key = f"bench:{random.randint(0, 999)}"
            await redis.set(key, "benchmark-value", ex=60)
            await redis.get(key)
        return {"name": "cache_r1_redis", "func": _run, "iterations": 5000, "warmup": 200}

    def cache_miss_fallback(self) -> Dict:
        """Test full read cascade miss path (R0 → R1 → R3)."""
        cache_r0 = {}

        async def _run():
            key = f"miss-{uuid.uuid4().hex[:8]}"
            result = cache_r0.get(key)
            if not result:
                redis = self.engines.get("memory")
                if redis:
                    result = await redis.get(f"bench:{key}")
                if not result:
                    pool = self.engines.get("relational")
                    if pool:
                        async with pool.acquire() as conn:
                            result = await conn.fetchrow(
                                "SELECT data FROM benchmark_scratch WHERE id = $1", key
                            )
        return {"name": "cache_miss_fallback", "func": _run, "iterations": 2000, "warmup": 50}

    # ── Write Fan-Out ──

    def write_fanout(self) -> Dict:
        async def _run():
            pool = self.engines.get("relational")
            redis = self.engines.get("memory")
            uid = uuid.uuid4().hex[:12]
            data = json.dumps({"fanout": True, "ts": time.time()})

            tasks = []
            if pool:
                async def _pg():
                    async with pool.acquire() as conn:
                        await conn.execute(
                            "INSERT INTO benchmark_scratch (id, data, created_at) "
                            "VALUES ($1, $2, NOW()) ON CONFLICT (id) DO UPDATE SET data = $2",
                            uid, data
                        )
                tasks.append(_pg())
            if redis:
                tasks.append(redis.set(f"bench:fanout:{uid}", data, ex=300))

            if tasks:
                await asyncio.gather(*tasks)
            # Cache invalidation
            if redis:
                await redis.delete(f"bench:cache:{uid}")

        import asyncio
        return {"name": "write_fanout", "func": _run, "iterations": 2000, "warmup": 100}

    # ── VectorCore (Qdrant) ──

    def vector_insert(self) -> Dict:
        async def _run():
            qdrant = self.engines.get("vector")
            if not qdrant:
                return
            from qdrant_client.models import PointStruct
            point = PointStruct(
                id=uuid.uuid4().hex,
                vector=self._test_data["vectors"][random.randint(0, 49)],
                payload={"bench": True, "tenant": self._test_tenant},
            )
            await qdrant.upsert(
                collection_name="benchmark_vectors", points=[point]
            )
        return {"name": "vector_insert", "func": _run, "iterations": 500, "warmup": 20}

    def vector_search(self) -> Dict:
        async def _run():
            qdrant = self.engines.get("vector")
            if not qdrant:
                return
            query_vec = self._test_data["vectors"][random.randint(0, 49)]
            await qdrant.search(
                collection_name="benchmark_vectors",
                query_vector=query_vec,
                limit=10,
            )
        return {"name": "vector_search", "func": _run, "iterations": 1000, "warmup": 50}

    # ── GraphCore (AGE) ──

    def graph_create_edge(self) -> Dict:
        async def _run():
            pool = self.engines.get("relational")
            if not pool:
                return
            async with pool.acquire() as conn:
                try:
                    await conn.execute(
                        "SELECT * FROM cypher('cortexgraph', $$ "
                        "CREATE (a:BenchNode {id: $id1})-[:BENCH_EDGE {weight: $w}]->"
                        "(b:BenchNode {id: $id2}) RETURN a, b "
                        "$$, $1) AS (a agtype, b agtype)",
                        json.dumps({
                            "id1": uuid.uuid4().hex[:8],
                            "id2": uuid.uuid4().hex[:8],
                            "w": random.uniform(0, 1)
                        })
                    )
                except Exception:
                    pass
        return {"name": "graph_create_edge", "func": _run, "iterations": 500, "warmup": 20}

    # ── StreamCore (Redis Streams) ──

    def stream_publish(self) -> Dict:
        async def _run():
            redis = self.engines.get("stream")
            if not redis:
                redis = self.engines.get("memory")
            if not redis:
                return
            await redis.xadd(
                "bench:events",
                {"type": "benchmark", "ts": str(time.time()), "data": "test-payload"},
                maxlen=10000,
            )
        return {"name": "stream_publish", "func": _run, "iterations": 5000, "warmup": 200}

    # ── ImmutableCore (Ledger) ──

    def ledger_commit(self) -> Dict:
        async def _run():
            pool = self.engines.get("relational")
            if not pool:
                return
            entry = json.dumps({"action": "bench_tx", "ts": time.time()})
            prev_hash = hashlib.sha256(b"benchmark").hexdigest()
            entry_hash = hashlib.sha256(entry.encode()).hexdigest()
            async with pool.acquire() as conn:
                await conn.execute(
                    "INSERT INTO benchmark_ledger (entry_hash, prev_hash, data, created_at) "
                    "VALUES ($1, $2, $3, NOW())",
                    entry_hash, prev_hash, entry
                )
        return {"name": "ledger_commit", "func": _run, "iterations": 1000, "warmup": 50}

    # ── CortexQL Parser ──

    def cortexql_parse(self) -> Dict:
        queries = [
            "SELECT * FROM customers WHERE email = 'test@test.com'",
            "FIND SIMILAR TO 'premium customer' IN customers LIMIT 10",
            "INSERT INTO events (type, data) VALUES ('click', '{\"page\": \"/home\"}')",
            "TRAVERSE FROM customer_123 DEPTH 3 WHERE type = 'purchased'",
            "SUBSCRIBE TO events WHERE type = 'purchase'",
        ]

        async def _run():
            if self.db and hasattr(self.db, "router"):
                q = queries[random.randint(0, len(queries) - 1)]
                try:
                    self.db.router.classify(q)
                except Exception:
                    pass
            else:
                # Simulate parse cost
                q = queries[random.randint(0, len(queries) - 1)]
                q.upper().split()
        return {"name": "cortexql_parse", "func": _run, "iterations": 10000, "warmup": 500}

    # ── Amygdala (Threat Detection) ──

    def amygdala_check(self) -> Dict:
        safe_queries = [
            "SELECT name FROM customers WHERE id = $1",
            "INSERT INTO events (type) VALUES ('click')",
            "UPDATE profiles SET score = 85 WHERE customer_id = $1",
        ]
        attack_queries = [
            "SELECT * FROM users WHERE id = 1 OR 1=1--",
            "'; DROP TABLE customers;--",
            "SELECT * FROM users UNION SELECT password FROM admin",
        ]

        async def _run():
            if self.db and hasattr(self.db, "amygdala"):
                q = random.choice(safe_queries + attack_queries)
                try:
                    self.db.amygdala.check(q)
                except Exception:
                    pass
            else:
                q = random.choice(safe_queries)
                for pattern in ["OR 1=1", "DROP TABLE", "UNION SELECT", "'; --"]:
                    if pattern.lower() in q.lower():
                        break
        return {"name": "amygdala_check", "func": _run, "iterations": 20000, "warmup": 1000}

    # ── Compliance ──

    def encryption_roundtrip(self) -> Dict:
        """AES-256-GCM encrypt + decrypt cycle."""
        async def _run():
            try:
                from cryptography.hazmat.primitives.ciphers.aead import AESGCM
                import os
                key = AESGCM.generate_key(bit_length=256)
                aead = AESGCM(key)
                nonce = os.urandom(12)
                plaintext = b"SSN:123-45-6789|CC:4111111111111111|DOB:1990-01-01"
                ct = aead.encrypt(nonce, plaintext, None)
                pt = aead.decrypt(nonce, ct, None)
                assert pt == plaintext
            except ImportError:
                import os
                data = os.urandom(50)
                key = os.urandom(32)
                _ = bytes(a ^ b for a, b in zip(data, key * 2))
        return {"name": "encryption_roundtrip", "func": _run, "iterations": 5000, "warmup": 200}

    def compliance_audit_log(self) -> Dict:
        async def _run():
            pool = self.engines.get("relational")
            if not pool:
                return
            async with pool.acquire() as conn:
                await conn.execute(
                    "INSERT INTO benchmark_audit (event_type, tenant_id, details, created_at) "
                    "VALUES ($1, $2, $3, NOW())",
                    "DATA_READ", self._test_tenant,
                    json.dumps({"table": "customers", "bench": True})
                )
        return {"name": "compliance_audit_log", "func": _run, "iterations": 2000, "warmup": 100}
