import pytest

from semantic_layer.compiler import compile_query
from semantic_layer.errors import (CatalogValidationError, FanOutError,
                                   InvalidQueryError, NoJoinPathError,
                                   UnknownDimensionError, UnknownMetricError)
from semantic_layer.models import (Aggregation, Filter, Metric, MetricStatus,
                                   QueryRequest, Tier)


def test_unknown_metric(catalog):
    with pytest.raises(UnknownMetricError):
        compile_query(catalog, QueryRequest(metrics=["nope"]))


def test_unknown_dimension(catalog):
    with pytest.raises(UnknownDimensionError):
        compile_query(catalog, QueryRequest(
            metrics=["total_revenue"], dimensions=["nope"]))


def test_unknown_filter_field(catalog):
    with pytest.raises(UnknownDimensionError):
        compile_query(catalog, QueryRequest(
            metrics=["total_revenue"], filters=[Filter("nope", "=", 1)]))


def test_empty_metrics_rejected(catalog):
    with pytest.raises(InvalidQueryError):
        compile_query(catalog, QueryRequest(metrics=[]))


def test_duplicate_metrics_rejected(catalog):
    with pytest.raises(InvalidQueryError):
        compile_query(catalog, QueryRequest(
            metrics=["total_revenue", "total_revenue"]))


def test_mixed_base_entities_rejected(catalog):
    with pytest.raises(InvalidQueryError):
        compile_query(catalog, QueryRequest(
            metrics=["total_revenue", "customer_count"]))


def test_bad_operator_rejected(catalog):
    with pytest.raises(InvalidQueryError):
        compile_query(catalog, QueryRequest(
            metrics=["total_revenue"],
            filters=[Filter("order_status", "; DROP", "x")]))


def test_in_filter_needs_list(catalog):
    with pytest.raises(InvalidQueryError):
        compile_query(catalog, QueryRequest(
            metrics=["total_revenue"],
            filters=[Filter("order_status", "in", "completed")]))


def test_bad_limit_rejected(catalog):
    with pytest.raises(InvalidQueryError):
        compile_query(catalog, QueryRequest(metrics=["total_revenue"], limit=0))
    with pytest.raises(InvalidQueryError):
        compile_query(catalog, QueryRequest(metrics=["total_revenue"], limit=99999))


def test_order_by_unrequested_rejected(catalog):
    with pytest.raises(InvalidQueryError):
        compile_query(catalog, QueryRequest(
            metrics=["total_revenue"], order_by=["order_count"]))


def test_fanout_guard_blocks_count_over_one_to_many(catalog):
    # customer_count is on the customer entity; order_status requires
    # traversing to orders in the one-to-many direction.
    with pytest.raises(FanOutError):
        compile_query(catalog, QueryRequest(
            metrics=["customer_count"], dimensions=["order_status"]))


def test_fanout_allowed_with_opt_in(catalog):
    compiled = compile_query(catalog, QueryRequest(
        metrics=["customer_count"], dimensions=["order_status"],
        allow_fanout=True))
    assert "orders AS t_order" in compiled.sql


def test_fanout_safe_for_count_distinct(catalog):
    # A distinct count on the customer entity survives the fan-out join.
    catalog.add_metric(Metric(
        "distinct_ordering_customers", "customer", Aggregation.COUNT_DISTINCT,
        "customer_id", owner="data-platform", tier=Tier.SILVER,
        status=MetricStatus.CERTIFIED))
    compiled = compile_query(catalog, QueryRequest(
        metrics=["distinct_ordering_customers"], dimensions=["order_status"]))
    assert "COUNT(DISTINCT" in compiled.sql


def test_no_join_path(catalog):
    from semantic_layer.models import Dimension, Entity, SourceTable
    catalog.add_table(SourceTable("islands", ("island_id", "island_name")))
    catalog.add_entity(Entity("island", "islands", "island_id"))
    catalog.add_dimension(Dimension("island_name", "island", "island_name"))
    with pytest.raises(NoJoinPathError):
        compile_query(catalog, QueryRequest(
            metrics=["total_revenue"], dimensions=["island_name"]))


def test_catalog_validation_catches_bad_column(catalog):
    catalog.add_metric(Metric("broken", "order", Aggregation.SUM, "no_such_col",
                              owner="x"))
    problems = catalog.validate()
    assert any("broken" in p for p in problems)
    with pytest.raises(CatalogValidationError):
        catalog.assert_valid()
