"""End-to-end offline demo.

Defines nothing new — it exercises the shipped catalog end to end:
compile revenue by region, run it, show the cache serving the repeat,
show lineage, show governance, and show the draft/deprecated gates
and the fan-out guard refusing a dangerous query.
"""
from __future__ import annotations

from typing import Any

from .compiler import compile_query
from .definitions import build_default_catalog
from .errors import SemanticLayerError
from .governance import audit_catalog
from .lineage import metric_lineage, query_lineage
from .models import Filter, QueryRequest
from .service import SemanticService


def run_demo() -> dict[str, Any]:
    catalog = build_default_catalog()
    service = SemanticService(catalog=catalog)

    request = QueryRequest(
        metrics=["total_revenue", "order_count", "unique_customers"],
        dimensions=["customer_region"],
        filters=[Filter("order_status", "=", "completed")],
        order_by=["-total_revenue"])
    compiled = compile_query(catalog, request)
    first = service.query(request)
    second = service.query(request)  # cache hit

    ratio = service.query(QueryRequest(
        metrics=["discount_rate"], dimensions=["order_channel"]))

    gates: dict[str, str] = {}
    for name, req in (
            ("draft_blocked", QueryRequest(metrics=["repeat_order_share"])),
            ("deprecated_blocked", QueryRequest(metrics=["legacy_gross_sales"])),
            ("fanout_blocked", QueryRequest(
                metrics=["customer_count"], dimensions=["order_status"]))):
        try:
            compile_query(catalog, req)
            gates[name] = "NOT BLOCKED (unexpected)"
        except SemanticLayerError as exc:
            gates[name] = str(exc)

    return {
        "compiled_sql": compiled.sql,
        "revenue_by_region": first["rows"],
        "second_query_from_cache": second["from_cache"],
        "discount_rate_by_channel": ratio["rows"],
        "lineage_total_revenue": metric_lineage(catalog, "total_revenue").to_dict(),
        "query_lineage": query_lineage(catalog, request),
        "governance_ok": audit_catalog(catalog).ok,
        "gates": gates,
        "cache_stats": service.cache.stats.to_dict(),
        "certified_metrics": [m.name for m in catalog.list_metrics()
                              if m.status.value == "certified"],
    }
