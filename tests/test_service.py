import pytest

from semantic_layer.models import QueryRequest
from semantic_layer.service import SemanticService


@pytest.fixture()
def service():
    return SemanticService()


def test_service_lists_metrics(service):
    metrics = service.list_metrics()
    assert len(metrics) == 10
    certified = service.list_metrics(status="certified")
    assert len(certified) == 8


def test_service_compile_and_query(service):
    compiled = service.compile(QueryRequest(metrics=["total_revenue"]))
    assert compiled["sql"].startswith("SELECT SUM")
    result = service.query(QueryRequest(
        metrics=["order_count"], dimensions=["order_channel"]))
    assert result["row_count"] == 3
    assert result["from_cache"] is False
    again = service.query(QueryRequest(
        metrics=["order_count"], dimensions=["order_channel"]))
    assert again["from_cache"] is True


def test_service_lineage_and_governance(service):
    lineage = service.lineage("total_revenue")
    assert lineage["source_columns"] == ["orders.amount"]
    assert service.governance_report()["ok"] is True
    query_lin = service.query_lineage(QueryRequest(
        metrics=["total_revenue"], dimensions=["customer_region"]))
    assert query_lin["joins_used"] == ["order_customer"]


