"""
Bloom Filter for CortexDB R1 Negative Cache.

Prevents unnecessary Redis lookups for keys that definitely don't exist.
Resets on process restart (acceptable — it's a negative cache optimization).

Parameters: size=1M bits, 7 hash functions → ~1% false positive at 100k entries.
"""

import mmh3
from bitarray import bitarray


class BloomFilter:
    """Memory-efficient probabilistic set membership test."""

    def __init__(self, size: int = 1_000_000, num_hashes: int = 7):
        self._size = size
        self._num_hashes = num_hashes
        self._bits = bitarray(size)
        self._bits.setall(0)
        self._count = 0

    def _get_positions(self, key: str) -> list:
        """Generate bit positions for a key using double hashing."""
        h1 = mmh3.hash(key, seed=0) % self._size
        h2 = mmh3.hash(key, seed=42) % self._size
        return [(h1 + i * h2) % self._size for i in range(self._num_hashes)]

    def add(self, key: str):
        """Add a key to the filter."""
        for pos in self._get_positions(key):
            self._bits[pos] = 1
        self._count += 1

    def might_contain(self, key: str) -> bool:
        """Check if a key might be in the filter.

        Returns:
            False = definitely not present (safe to skip lookup)
            True  = possibly present (must check Redis)
        """
        return all(self._bits[pos] for pos in self._get_positions(key))

    def reset(self):
        """Clear the filter (e.g., after cache flush)."""
        self._bits.setall(0)
        self._count = 0

    @property
    def stats(self) -> dict:
        set_bits = self._bits.count(1)
        fill_ratio = set_bits / self._size if self._size > 0 else 0
        return {
            "size_bits": self._size,
            "num_hashes": self._num_hashes,
            "items_added": self._count,
            "fill_ratio": round(fill_ratio, 4),
            "memory_kb": round(self._size / 8 / 1024, 1),
        }
