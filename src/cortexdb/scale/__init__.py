"""CortexDB Scale Module - Petabyte-Scale Horizontal Infrastructure

Citus sharding, read replica routing, AI indexing, fast data rendering.
"""

from cortexdb.scale.sharding import CitusShardManager, ShardStrategy
from cortexdb.scale.replication import ReplicaRouter, ReadWriteSplit
from cortexdb.scale.ai_index import AIIndexManager, IndexType
from cortexdb.scale.rendering import DataRenderer, RenderFormat

__all__ = [
    "CitusShardManager", "ShardStrategy",
    "ReplicaRouter", "ReadWriteSplit",
    "AIIndexManager", "IndexType",
    "DataRenderer", "RenderFormat",
]
