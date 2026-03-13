"""Unit tests for BloomFilter (P1.5)."""

import pytest
from cortexdb.core.bloom import BloomFilter


class TestBloomFilter:
    def test_add_and_check(self):
        bf = BloomFilter()
        bf.add("hello")
        assert bf.might_contain("hello") is True

    def test_missing_key(self):
        bf = BloomFilter()
        bf.add("hello")
        assert bf.might_contain("world") is False

    def test_multiple_keys(self):
        bf = BloomFilter()
        keys = [f"key_{i}" for i in range(100)]
        for k in keys:
            bf.add(k)
        for k in keys:
            assert bf.might_contain(k) is True

    def test_false_positive_rate(self):
        """Verify FP rate stays below ~2% at 100k entries with 1M bits."""
        bf = BloomFilter(size=1_000_000, num_hashes=7)
        n = 100_000
        for i in range(n):
            bf.add(f"inserted_{i}")

        fps = 0
        test_count = 10_000
        for i in range(test_count):
            if bf.might_contain(f"not_inserted_{i}"):
                fps += 1
        fp_rate = fps / test_count
        assert fp_rate < 0.02, f"False positive rate {fp_rate:.3f} exceeds 2%"

    def test_reset(self):
        bf = BloomFilter()
        bf.add("hello")
        assert bf.might_contain("hello") is True
        bf.reset()
        assert bf.might_contain("hello") is False

    def test_stats(self):
        bf = BloomFilter(size=1000, num_hashes=5)
        bf.add("a")
        bf.add("b")
        stats = bf.stats
        assert stats["size_bits"] == 1000
        assert stats["num_hashes"] == 5
        assert stats["items_added"] == 2

    def test_empty_string(self):
        bf = BloomFilter()
        bf.add("")
        assert bf.might_contain("") is True
        assert bf.might_contain("x") is False
