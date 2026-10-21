"""Core typed models: tables, entities, dimensions, joins, metrics, queries.

Definitions are code, not free-form SQL. A metric names an entity, a
measure column and an aggregation; a dimension names an entity and a
column. Because nothing is raw SQL, the compiler can validate every
identifier against the catalog whitelist before generating anything.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Aggregation(str, Enum):
    SUM = "sum"
    COUNT = "count"
    COUNT_DISTINCT = "count_distinct"
    AVG = "avg"
    MIN = "min"
    MAX = "max"


class MetricStatus(str, Enum):
    CERTIFIED = "certified"
    DRAFT = "draft"
    DEPRECATED = "deprecated"


class Tier(str, Enum):
    GOLD = "gold"
    SILVER = "silver"
    BRONZE = "bronze"


class Cardinality(str, Enum):
    ONE_TO_ONE = "one_to_one"
    MANY_TO_ONE = "many_to_one"
    ONE_TO_MANY = "one_to_many"
    MANY_TO_MANY = "many_to_many"

    def reversed(self) -> "Cardinality":
        return {
            Cardinality.ONE_TO_ONE: Cardinality.ONE_TO_ONE,
            Cardinality.MANY_TO_ONE: Cardinality.ONE_TO_MANY,
            Cardinality.ONE_TO_MANY: Cardinality.MANY_TO_ONE,
            Cardinality.MANY_TO_MANY: Cardinality.MANY_TO_MANY,
        }[self]

    @property
    def fans_out(self) -> bool:
        """True when traversing in this direction multiplies base rows."""
        return self in (Cardinality.ONE_TO_MANY, Cardinality.MANY_TO_MANY)


@dataclass(frozen=True)
class SourceTable:
    name: str
    columns: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "columns": list(self.columns)}


@dataclass(frozen=True)
class Entity:
    name: str
    table: str
    primary_key: str
    description: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "table": self.table,
                "primary_key": self.primary_key, "description": self.description}


@dataclass(frozen=True)
class Dimension:
    name: str
    entity: str
    column: str
    data_type: str = "string"
    description: str = ""
    is_time: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "entity": self.entity, "column": self.column,
                "data_type": self.data_type, "description": self.description,
                "is_time": self.is_time}


@dataclass(frozen=True)
class Join:
    """A declared join between two entities on key columns."""

    name: str
    left_entity: str
    right_entity: str
    left_key: str
    right_key: str
    cardinality: Cardinality = Cardinality.MANY_TO_ONE
    join_type: str = "left"

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "left_entity": self.left_entity,
                "right_entity": self.right_entity, "left_key": self.left_key,
                "right_key": self.right_key,
                "cardinality": self.cardinality.value, "join_type": self.join_type}


@dataclass(frozen=True)
class Metric:
    name: str
    entity: str
    aggregation: Aggregation
    measure_column: str | None = None
    label: str = ""
    description: str = ""
    owner: str = ""
    tier: Tier = Tier.BRONZE
    status: MetricStatus = MetricStatus.DRAFT
    tags: tuple[str, ...] = ()
    # Derived (ratio) metrics: numerator / denominator metric names.
    numerator: str | None = None
    denominator: str | None = None
    replaced_by: str | None = None

    @property
    def is_derived(self) -> bool:
        return self.numerator is not None and self.denominator is not None

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "entity": self.entity,
                "aggregation": self.aggregation.value,
                "measure_column": self.measure_column,
                "label": self.label or self.name, "description": self.description,
                "owner": self.owner, "tier": self.tier.value,
                "status": self.status.value, "tags": list(self.tags),
                "numerator": self.numerator, "denominator": self.denominator,
                "replaced_by": self.replaced_by, "is_derived": self.is_derived}


@dataclass(frozen=True)
class Filter:
    field: str  # a dimension name
    operator: str = "="
    value: Any = None

    ALLOWED_OPERATORS = ("=", "!=", ">", ">=", "<", "<=", "in", "not_in", "like")

    def to_dict(self) -> dict[str, Any]:
        return {"field": self.field, "operator": self.operator, "value": self.value}


@dataclass
class QueryRequest:
    metrics: list[str]
    dimensions: list[str] = field(default_factory=list)
    filters: list[Filter] = field(default_factory=list)
    order_by: list[str] = field(default_factory=list)  # names, optional -prefix for DESC
    limit: int | None = None
    allow_draft: bool = False
    allow_deprecated: bool = False
    allow_fanout: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {"metrics": list(self.metrics), "dimensions": list(self.dimensions),
                "filters": [f.to_dict() for f in self.filters],
                "order_by": list(self.order_by), "limit": self.limit,
                "allow_draft": self.allow_draft,
                "allow_deprecated": self.allow_deprecated,
                "allow_fanout": self.allow_fanout}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "QueryRequest":
        return cls(
            metrics=list(data.get("metrics", [])),
            dimensions=list(data.get("dimensions", [])),
            filters=[Filter(field=str(f["field"]), operator=str(f.get("operator", "=")),
                            value=f.get("value")) for f in data.get("filters", [])],
            order_by=list(data.get("order_by", [])),
            limit=data.get("limit"),
            allow_draft=bool(data.get("allow_draft", False)),
            allow_deprecated=bool(data.get("allow_deprecated", False)),
            allow_fanout=bool(data.get("allow_fanout", False)),
        )


@dataclass(frozen=True)
class CompiledQuery:
    sql: str
    params: tuple[Any, ...]
    metrics: tuple[str, ...]
    dimensions: tuple[str, ...]
    joins_used: tuple[str, ...]
    source_tables: tuple[str, ...]
    source_columns: tuple[str, ...]  # "table.column" strings, sorted

    def to_dict(self) -> dict[str, Any]:
        return {"sql": self.sql, "params": list(self.params),
                "metrics": list(self.metrics), "dimensions": list(self.dimensions),
                "joins_used": list(self.joins_used),
                "source_tables": list(self.source_tables),
                "source_columns": list(self.source_columns)}
