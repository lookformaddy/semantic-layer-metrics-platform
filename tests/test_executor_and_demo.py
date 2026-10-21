import pytest

from semantic_layer.cache import QueryCache
from semantic_layer.cli import main as cli_main
from semantic_layer.demo import run_demo
from semantic_layer.executor import (SemanticExecutor, build_connection,
                                     generate_dataset)
from semantic_layer.models import Filter, QueryRequest
from semantic_layer.registry import MetricRegistry


@pytest.fixture()
def executor(catalog):
    return SemanticExecutor(catalog, build_connection())


def test_dataset_is_deterministic():
    a = generate_dataset(seed=7)
    b = generate_dataset(seed=7)
    assert a.orders == b.orders
    assert len(a.orders) == 240
    assert generate_dataset(seed=8).orders != a.orders


def test_total_revenue_matches_raw_sql(catalog, executor):
    result = executor.query(QueryRequest(metrics=["total_revenue"]))
    raw = build_connection().execute("SELECT SUM(amount) FROM orders").fetchone()[0]
    assert result.rows[0]["total_revenue"] == pytest.approx(raw)
    assert result.from_cache is False


def test_revenue_by_region_sums_to_total(catalog, executor):
    by_region = executor.query(QueryRequest(
        metrics=["total_revenue"], dimensions=["customer_region"])).rows
    total = executor.query(QueryRequest(metrics=["total_revenue"])).rows[0]
    assert len(by_region) == 4
    assert sum(r["total_revenue"] for r in by_region) == pytest.approx(
        total["total_revenue"])


def test_filtered_query_completed_only(catalog, executor):
    rows = executor.query(QueryRequest(
        metrics=["order_count"],
        filters=[Filter("order_status", "=", "completed")])).rows
    raw = build_connection().execute(
        "SELECT COUNT(*) FROM orders WHERE status='completed'").fetchone()[0]
    assert rows[0]["order_count"] == raw


def test_discount_rate_between_zero_and_one(catalog, executor):
    rows = executor.query(QueryRequest(metrics=["discount_rate"])).rows
    assert 0.0 <= rows[0]["discount_rate"] <= 1.0


def test_executor_cache_second_query_hits(catalog):
    cache = QueryCache()
    executor = SemanticExecutor(catalog, build_connection(), cache=cache)
    req = QueryRequest(metrics=["order_count"])
    first = executor.query(req)
    second = executor.query(req)
    assert first.from_cache is False
    assert second.from_cache is True
    assert first.rows == second.rows
    assert cache.stats.hits == 1


def test_demo_report_shape():
    report = run_demo()
    assert report["second_query_from_cache"] is True
    assert report["governance_ok"] is True
    assert len(report["revenue_by_region"]) == 4
    assert "total_revenue" in report["compiled_sql"]
    assert report["gates"]["draft_blocked"]
    assert "deprecated" in report["gates"]["deprecated_blocked"]
    assert "fan out" in report["gates"]["fanout_blocked"]


def test_registry_search_and_facets(catalog):
    registry = MetricRegistry(catalog)
    assert registry.get("total_revenue").name == "total_revenue"
    assert len(registry.certified()) == 8
    assert [m.name for m in registry.deprecated()] == ["legacy_gross_sales"]
    assert registry.search("discount")
    assert registry.by_owner("data-platform")
    assert registry.by_tier(registry.get("total_revenue").tier)


def test_query_request_from_dict_round_trip():
    req = QueryRequest.from_dict({
        "metrics": ["total_revenue"], "dimensions": ["customer_region"],
        "filters": [{"field": "order_status", "operator": "=", "value": "completed"}],
        "limit": 3})
    assert req.metrics == ["total_revenue"]
    assert req.filters[0].field == "order_status"
    assert req.to_dict()["limit"] == 3


def test_cli_metrics_and_compile(capsys):
    assert cli_main(["metrics"]) == 0
    assert "total_revenue" in capsys.readouterr().out
    assert cli_main(["compile", "--metrics", "total_revenue",
                     "--dimensions", "customer_region"]) == 0
    assert "SUM(t_order.amount)" in capsys.readouterr().out


def test_cli_demo_and_lineage(capsys):
    assert cli_main(["demo"]) == 0
    assert "revenue_by_region" in capsys.readouterr().out
    assert cli_main(["lineage", "discount_rate"]) == 0
    assert "total_discount" in capsys.readouterr().out
