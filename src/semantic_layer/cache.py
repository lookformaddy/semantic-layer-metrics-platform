"""Query-result cache with TTL freshness and explicit invalidation.

The cache key is the compiled SQL plus its bound parameters — i.e.
the exact query, not the surface request — so two differently-shaped
requests that compile to the same SQL share an entry, and two that
differ in a filter value never collide. An entry is *fresh* until its
TTL expires; stale entries are misses, counted separately so operators
can see freshness pressure.
"""
from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from .models import CompiledQuery


def cache_key(compiled: CompiledQuery) -> str:
    payload = json.dumps({"sql": compiled.sql, "params": list(compiled.params)},
                         sort_keys=True, default=str)
    return hashlib.sha256(payload.encode()).hexdigest()[:24]


@dataclass
class CacheEntry:
    key: str
    value: Any
    stored_at: float
    ttl_seconds: float

    def is_fresh(self, now: float) -> bool:
        return now - self.stored_at < self.ttl_seconds

    def age_seconds(self, now: float) -> float:
        return now - self.stored_at


@dataclass
class CacheStats:
    hits: int = 0
    misses: int = 0
    stale_misses: int = 0
    puts: int = 0
    evictions: int = 0

    def to_dict(self) -> dict:
        total = self.hits + self.misses
        return {"hits": self.hits, "misses": self.misses,
                "stale_misses": self.stale_misses, "puts": self.puts,
                "evictions": self.evictions,
                "hit_rate": round(self.hits / total, 4) if total else 0.0}


@dataclass
class QueryCache:
    ttl_seconds: float = 300.0
    max_entries: int = 128
    clock: Callable[[], float] = time.monotonic
    _entries: dict[str, CacheEntry] = field(default_factory=dict)
    stats: CacheStats = field(default_factory=CacheStats)

    def get(self, compiled: CompiledQuery) -> Any | None:
        key = cache_key(compiled)
        entry = self._entries.get(key)
        if entry is None:
            self.stats.misses += 1
            return None
        now = self.clock()
        if not entry.is_fresh(now):
            self.stats.misses += 1
            self.stats.stale_misses += 1
            return None
        self.stats.hits += 1
        return entry.value

    def put(self, compiled: CompiledQuery, value: Any,
            ttl_seconds: float | None = None) -> str:
        key = cache_key(compiled)
        if key not in self._entries and len(self._entries) >= self.max_entries:
            oldest = min(self._entries.values(), key=lambda e: e.stored_at)
            del self._entries[oldest.key]
            self.stats.evictions += 1
        self._entries[key] = CacheEntry(
            key=key, value=value, stored_at=self.clock(),
            ttl_seconds=self.ttl_seconds if ttl_seconds is None else ttl_seconds)
        self.stats.puts += 1
        return key

    def invalidate(self, compiled: CompiledQuery) -> bool:
        return self._entries.pop(cache_key(compiled), None) is not None

    def clear(self) -> None:
        self._entries.clear()

    def __len__(self) -> int:
        return len(self._entries)
