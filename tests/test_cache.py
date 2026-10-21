from semantic_layer.cache import QueryCache, cache_key
from semantic_layer.compiler import compile_query
from semantic_layer.models import Filter, QueryRequest


class FakeClock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


def _compiled(catalog, **kwargs):
    return compile_query(catalog, QueryRequest(metrics=["total_revenue"], **kwargs))


def test_put_get_round_trip(catalog):
    cache = QueryCache(clock=FakeClock())
    compiled = _compiled(catalog)
    cache.put(compiled, [{"total_revenue": 1.0}])
    assert cache.get(compiled) == [{"total_revenue": 1.0}]
    assert cache.stats.hits == 1


def test_miss_for_unseen_query(catalog):
    cache = QueryCache(clock=FakeClock())
    assert cache.get(_compiled(catalog)) is None
    assert cache.stats.misses == 1


def test_different_filter_value_different_key(catalog):
    a = _compiled(catalog, filters=[Filter("order_status", "=", "completed")])
    b = _compiled(catalog, filters=[Filter("order_status", "=", "refunded")])
    assert cache_key(a) != cache_key(b)
    cache = QueryCache(clock=FakeClock())
    cache.put(a, ["a"])
    assert cache.get(b) is None


def test_same_query_same_key(catalog):
    assert cache_key(_compiled(catalog)) == cache_key(_compiled(catalog))


def test_ttl_expiry_is_stale_miss(catalog):
    clock = FakeClock()
    cache = QueryCache(ttl_seconds=60, clock=clock)
    compiled = _compiled(catalog)
    cache.put(compiled, ["x"])
    clock.now += 59
    assert cache.get(compiled) == ["x"]
    clock.now += 2
    assert cache.get(compiled) is None
    assert cache.stats.stale_misses == 1


def test_per_put_ttl_override(catalog):
    clock = FakeClock()
    cache = QueryCache(ttl_seconds=300, clock=clock)
    compiled = _compiled(catalog)
    cache.put(compiled, ["x"], ttl_seconds=5)
    clock.now += 10
    assert cache.get(compiled) is None


def test_invalidate_and_clear(catalog):
    cache = QueryCache(clock=FakeClock())
    compiled = _compiled(catalog)
    cache.put(compiled, ["x"])
    assert cache.invalidate(compiled) is True
    assert cache.invalidate(compiled) is False
    cache.put(compiled, ["x"])
    cache.clear()
    assert len(cache) == 0


def test_eviction_at_capacity(catalog):
    cache = QueryCache(max_entries=2, clock=FakeClock())
    reqs = [QueryRequest(metrics=[m]) for m in
            ("total_revenue", "order_count", "total_quantity")]
    for req in reqs:
        cache.put(compile_query(catalog, req), ["x"])
    assert len(cache) == 2
    assert cache.stats.evictions == 1
