"""ImmutableCore - Brain Region: Declarative Memory (Permanent, Tamper-Evident)
Append-only ledger with SHA-256 hash chain.
For MVP: file-based. Upgrade path: Hyperledger Fabric.
REPLACES: Hyperledger (for MVP/Growth)"""

import hashlib
import json
import os
import time
from typing import Any, Dict, List, Optional
from cortexdb.engines import BaseEngine


class ImmutableEngine(BaseEngine):
    def __init__(self, config: Dict):
        super().__init__()
        self.path = config.get("path", "./data/immutable")
        self._chain: List[Dict] = []
        self._prev_hash: Optional[str] = None

    async def connect(self):
        os.makedirs(self.path, exist_ok=True)
        ledger_file = os.path.join(self.path, "ledger.jsonl")
        if os.path.exists(ledger_file):
            with open(ledger_file, "r") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        entry = json.loads(line)
                        self._chain.append(entry)
                        self._prev_hash = entry.get("hash")

    async def close(self):
        pass

    async def health(self) -> Dict:
        return {
            "engine": "File-based Hash Chain (upgrade: Hyperledger Fabric)",
            "brain_region": "Declarative Memory",
            "entries": len(self._chain),
            "chain_intact": await self.verify_chain(),
        }

    async def append(self, entry_type: str, payload: Dict, actor: str = "system") -> Dict:
        """Append immutable entry with hash chain"""
        entry = {
            "sequence": len(self._chain) + 1,
            "type": entry_type,
            "payload": payload,
            "actor": actor,
            "timestamp": time.time(),
            "prev_hash": self._prev_hash,
        }
        hash_input = (
            f"{self._prev_hash or 'GENESIS'}|{entry_type}|"
            f"{json.dumps(payload, sort_keys=True, default=str)}|{entry['timestamp']}"
        )
        entry["hash"] = hashlib.sha256(hash_input.encode()).hexdigest()
        self._chain.append(entry)
        self._prev_hash = entry["hash"]

        ledger_file = os.path.join(self.path, "ledger.jsonl")
        with open(ledger_file, "a") as f:
            f.write(json.dumps(entry, default=str) + "\n")
        return entry

    async def verify_chain(self) -> bool:
        """Verify entire hash chain integrity"""
        prev = None
        for entry in self._chain:
            hash_input = (
                f"{prev or 'GENESIS'}|{entry['type']}|"
                f"{json.dumps(entry['payload'], sort_keys=True, default=str)}|{entry['timestamp']}"
            )
            expected = hashlib.sha256(hash_input.encode()).hexdigest()
            if entry["hash"] != expected:
                return False
            prev = entry["hash"]
        return True

    async def write(self, data_type: str, payload: Dict, actor: str = "system") -> Any:
        return await self.append(data_type, payload, actor)
