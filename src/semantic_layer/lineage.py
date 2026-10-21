"""Lineage: metric -> measure columns -> source tables, and query-level lineage.

Lineage is derived from the same compiled query consumers run, so it
cannot drift from reality the way hand-maintained lineage diagrams do.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .catalog import SemanticCatalog
from .compiler import compile_query
from .models import QueryRequest


@dataclass
class MetricLineage:
    metric: str
    entity: str
    source_tables: list[str] = field(default_factory=list)
    source_columns: list[str] = field(default_factory=list)
    depends_on_metrics: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"metric": self.metric, "entity": self.entity,
                "source_tables": self.source_tables,
                "source_columns": self.source_columns,
                "depends_on_metrics": self.depends_on_metrics}


def metric_lineage(catalog: SemanticCatalog, metric_name: str) -> MetricLineage:
    metric = catalog.get_metric(metric_name)
    entity = catalog.get_entity(metric.entity)
    if metric.is_derived:
        deps = [metric.numerator or "", metric.denominator or ""]
        tables: set[str] = set()
        columns: set[str] = set()
        for dep in deps:
            sub = metric_lineage(catalog, dep)
            tables.update(sub.source_tables)
            columns.update(sub.source_columns)
        return MetricLineage(metric=metric_name, entity=metric.entity,
                             source_tables=sorted(tables),
                             source_columns=sorted(columns),
                             depends_on_metrics=deps)
    return MetricLineage(
        metric=metric_name, entity=metric.entity,
        source_tables=[entity.table],
        source_columns=[f"{entity.table}.{metric.measure_column}"],
        depends_on_metrics=[])


def query_lineage(catalog: SemanticCatalog, request: QueryRequest) -> dict:
    """Lineage for a full query: metrics, dimensions, filters, joins."""
    compiled = compile_query(catalog, request)
    metric_nodes = [metric_lineage(catalog, name).to_dict()
                    for name in request.metrics]
    dimension_columns = []
    for name in list(request.dimensions) + [f.field for f in request.filters]:
        dim = catalog.get_dimension(name)
        table = catalog.get_entity(dim.entity).table
        dimension_columns.append(f"{table}.{dim.column}")
    return {
        "metrics": metric_nodes,
        "dimension_columns": sorted(set(dimension_columns)),
        "source_tables": list(compiled.source_tables),
        "source_columns": list(compiled.source_columns),
        "joins_used": list(compiled.joins_used),
    }


def downstream_metrics(catalog: SemanticCatalog, metric_name: str) -> list[str]:
    """Derived metrics that (transitively) depend on ``metric_name``."""
    catalog.get_metric(metric_name)  # validates existence
    found: list[str] = []
    for metric in catalog.list_metrics():
        if not metric.is_derived:
            continue
        seen: set[str] = set()
        stack = [metric.numerator or "", metric.denominator or ""]
        while stack:
            current = stack.pop()
            if current in seen:
                continue
            seen.add(current)
            part = catalog.get_metric(current) if catalog.has_metric(current) else None
            if part is not None and part.is_derived:
                stack.extend([part.numerator or "", part.denominator or ""])
        if metric_name in seen:
            found.append(metric.name)
    return sorted(found)
