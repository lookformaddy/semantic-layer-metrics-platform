import pytest

from semantic_layer.compiler import compile_query
from semantic_layer.models import Filter, QueryRequest


def test_simple_metric_no_join(catalog):
    compiled = compile_query(catalog, QueryRequest(metrics=["total_revenue"]))
    assert compiled.sql == (
        "SELECT SUM(t_order.amount) AS total_revenue FROM orders AS t_order")
    assert compiled.params == ()
    assert compiled.joins_used == ()
    assert compiled.source_tables == ("orders",)
    assert compiled.source_columns == ("orders.amount",)


def test_dimension_triggers_many_to_one_join(catalog):
    compiled = compile_query(catalog, QueryRequest(
        metrics=["total_revenue"], dimensions=["customer_region"]))
    assert "LEFT JOIN customers AS t_customer" in compiled.sql
    assert "ON t_order.customer_id = t_customer.customer_id" in compiled.sql
    assert "GROUP BY t_customer.region" in compiled.sql
    assert compiled.joins_used == ("order_customer",)
    assert set(compiled.source_tables) == {"orders", "customers"}
    assert "customers.region" in compiled.source_columns
    assert "orders.customer_id" in compiled.source_columns


def test_two_dimension_entities_two_joins(catalog):
    compiled = compile_query(catalog, QueryRequest(
        metrics=["order_count"],
        dimensions=["customer_region", "product_category"]))
    assert set(compiled.joins_used) == {"order_customer", "order_product"}
    assert "products AS t_product" in compiled.sql


def test_filter_uses_bound_parameter(catalog):
    compiled = compile_query(catalog, QueryRequest(
        metrics=["total_revenue"],
        filters=[Filter("order_status", "=", "completed")]))
    assert "WHERE t_order.status = ?" in compiled.sql
    assert compiled.params == ("completed",)
    assert "completed" not in compiled.sql  # never interpolated


def test_filter_on_joined_dimension_pulls_join(catalog):
    compiled = compile_query(catalog, QueryRequest(
        metrics=["total_revenue"],
        filters=[Filter("customer_region", "=", "north")]))
    assert compiled.joins_used == ("order_customer",)
    assert "WHERE t_customer.region = ?" in compiled.sql


def test_in_filter_expands_placeholders(catalog):
    compiled = compile_query(catalog, QueryRequest(
        metrics=["order_count"],
        filters=[Filter("order_channel", "in", ["online", "store"])]))
    assert "IN (?, ?)" in compiled.sql
    assert compiled.params == ("online", "store")


def test_count_distinct_sql(catalog):
    compiled = compile_query(catalog, QueryRequest(metrics=["unique_customers"]))
    assert "COUNT(DISTINCT t_order.customer_id)" in compiled.sql


def test_derived_ratio_sql(catalog):
    compiled = compile_query(catalog, QueryRequest(metrics=["discount_rate"]))
    assert "CAST(SUM(t_order.discount_amount) AS REAL)" in compiled.sql
    assert "/ NULLIF(SUM(t_order.amount), 0)" in compiled.sql


def test_deterministic_sql(catalog):
    req = QueryRequest(metrics=["total_revenue", "order_count"],
                       dimensions=["customer_region", "product_category"],
                       order_by=["-total_revenue"])
    assert compile_query(catalog, req).sql == compile_query(catalog, req).sql


def test_order_by_and_limit(catalog):
    compiled = compile_query(catalog, QueryRequest(
        metrics=["total_revenue"], dimensions=["customer_region"],
        order_by=["-total_revenue"], limit=5))
    assert compiled.sql.endswith("ORDER BY total_revenue DESC LIMIT 5")


def test_order_by_dimension_asc(catalog):
    compiled = compile_query(catalog, QueryRequest(
        metrics=["total_revenue"], dimensions=["customer_region"],
        order_by=["customer_region"]))
    assert "ORDER BY customer_region ASC" in compiled.sql
