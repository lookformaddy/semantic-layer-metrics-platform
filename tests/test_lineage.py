import pytest

from semantic_layer.errors import UnknownMetricError
from semantic_layer.lineage import (downstream_metrics, metric_lineage,
                                    query_lineage)
from semantic_layer.models import Filter, QueryRequest


def test_simple_metric_lineage(catalog):
    lineage = metric_lineage(catalog, "total_revenue")
    assert lineage.source_tables == ["orders"]
    assert lineage.source_columns == ["orders.amount"]
    assert lineage.depends_on_metrics == []


def test_derived_metric_lineage_expands_parts(catalog):
    lineage = metric_lineage(catalog, "discount_rate")
    assert set(lineage.depends_on_metrics) == {"total_discount", "total_revenue"}
    assert set(lineage.source_columns) == {"orders.amount", "orders.discount_amount"}
    assert lineage.source_tables == ["orders"]


def test_unknown_metric_lineage_raises(catalog):
    with pytest.raises(UnknownMetricError):
        metric_lineage(catalog, "nope")


def test_downstream_metrics(catalog):
    assert downstream_metrics(catalog, "total_revenue") == ["discount_rate"]
    assert downstream_metrics(catalog, "total_discount") == ["discount_rate"]
    assert downstream_metrics(catalog, "order_count") == []


def test_query_lineage_includes_dimensions_and_joins(catalog):
    lineage = query_lineage(catalog, QueryRequest(
        metrics=["total_revenue"], dimensions=["customer_region"],
        filters=[Filter("order_status", "=", "completed")]))
    assert set(lineage["source_tables"]) == {"orders", "customers"}
    assert lineage["joins_used"] == ["order_customer"]
    assert "customers.region" in lineage["dimension_columns"]
    assert "orders.status" in lineage["dimension_columns"]
    assert "orders.amount" in lineage["source_columns"]


def test_query_lineage_metrics_expanded(catalog):
    lineage = query_lineage(catalog, QueryRequest(metrics=["discount_rate"]))
    assert lineage["metrics"][0]["depends_on_metrics"] == [
        "total_discount", "total_revenue"]
