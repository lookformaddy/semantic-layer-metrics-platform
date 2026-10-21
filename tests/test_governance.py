import pytest

from semantic_layer.compiler import compile_query
from semantic_layer.errors import (DeprecatedMetricError, DraftMetricError,
                                   GovernanceError)
from semantic_layer.governance import (audit_catalog, assert_queryable,
                                       certify, check_metric, deprecate)
from semantic_layer.models import (Aggregation, Metric, MetricStatus,
                                   QueryRequest, Tier)


def test_default_catalog_passes_audit(catalog):
    report = audit_catalog(catalog)
    assert report.ok, report.to_dict()


def test_draft_metric_blocked_by_default(catalog):
    with pytest.raises(DraftMetricError):
        compile_query(catalog, QueryRequest(metrics=["repeat_order_share"]))


def test_draft_metric_allowed_with_opt_in(catalog):
    compiled = compile_query(catalog, QueryRequest(
        metrics=["repeat_order_share"], allow_draft=True))
    assert "repeat_order_share" in compiled.sql


def test_deprecated_metric_blocked_and_names_replacement(catalog):
    with pytest.raises(DeprecatedMetricError) as excinfo:
        compile_query(catalog, QueryRequest(metrics=["legacy_gross_sales"]))
    assert "total_revenue" in str(excinfo.value)


def test_deprecated_metric_allowed_with_opt_in(catalog):
    compiled = compile_query(catalog, QueryRequest(
        metrics=["legacy_gross_sales"], allow_deprecated=True))
    assert "legacy_gross_sales" in compiled.sql


def test_assert_queryable_certified_passes(catalog):
    assert_queryable(catalog.get_metric("total_revenue"))  # no raise


def test_certified_without_owner_flagged():
    metric = Metric("m", "order", Aggregation.SUM, "amount",
                    status=MetricStatus.CERTIFIED, tier=Tier.GOLD,
                    description="d")
    rules = {i.rule for i in check_metric(metric)}
    assert "owner_required" in rules


def test_certified_bronze_flagged():
    metric = Metric("m", "order", Aggregation.SUM, "amount", owner="o",
                    status=MetricStatus.CERTIFIED, tier=Tier.BRONZE,
                    description="d")
    rules = {i.rule for i in check_metric(metric)}
    assert "certified_needs_tier" in rules


def test_deprecated_without_replacement_flagged():
    metric = Metric("m", "order", Aggregation.SUM, "amount", owner="o",
                    status=MetricStatus.DEPRECATED)
    rules = {i.rule for i in check_metric(metric)}
    assert "deprecation_needs_replacement" in rules


def test_certify_refuses_unowned_draft():
    metric = Metric("m", "order", Aggregation.SUM, "amount",
                    status=MetricStatus.DRAFT, tier=Tier.GOLD, description="d")
    with pytest.raises(GovernanceError):
        certify(metric)


def test_certify_succeeds_when_rules_met():
    metric = Metric("m", "order", Aggregation.SUM, "amount", owner="o",
                    status=MetricStatus.DRAFT, tier=Tier.GOLD, description="d")
    assert certify(metric).status == MetricStatus.CERTIFIED


def test_deprecate_sets_replacement():
    metric = Metric("m", "order", Aggregation.SUM, "amount", owner="o",
                    status=MetricStatus.CERTIFIED, tier=Tier.GOLD, description="d")
    out = deprecate(metric, replaced_by="total_revenue")
    assert out.status == MetricStatus.DEPRECATED
    assert out.replaced_by == "total_revenue"
    with pytest.raises(GovernanceError):
        deprecate(metric, replaced_by="")


def test_catalog_filters(catalog):
    certified = catalog.list_metrics(status=MetricStatus.CERTIFIED)
    assert len(certified) == 8
    assert all(m.status == MetricStatus.CERTIFIED for m in certified)
    gold = catalog.list_metrics(tier=Tier.GOLD)
    assert {m.name for m in gold} == {
        "total_revenue", "order_count", "unique_customers"}
    assert catalog.list_metrics(tag="revenue")
    assert catalog.list_metrics(owner="nobody") == []
