"""The semantic catalog: registry of tables, entities, dimensions, joins, metrics.

The catalog is the single source of truth the compiler validates
against. ``validate()`` checks referential integrity of the catalog
itself: every entity's table exists, every metric/dimension column
exists on its entity's table, every join references real entities and
key columns, and derived metrics reference real, non-derived metrics
on the same entity.
"""
from __future__ import annotations

from typing import Iterable

from .errors import (CatalogValidationError, UnknownDimensionError,
                     UnknownEntityError, UnknownMetricError)
from .models import (Dimension, Entity, Join, Metric, MetricStatus,
                     SourceTable, Tier)


class SemanticCatalog:
    def __init__(self) -> None:
        self._tables: dict[str, SourceTable] = {}
        self._entities: dict[str, Entity] = {}
        self._dimensions: dict[str, Dimension] = {}
        self._joins: dict[str, Join] = {}
        self._metrics: dict[str, Metric] = {}

    # -- registration -----------------------------------------------------
    def add_table(self, table: SourceTable) -> None:
        self._tables[table.name] = table

    def add_entity(self, entity: Entity) -> None:
        self._entities[entity.name] = entity

    def add_dimension(self, dimension: Dimension) -> None:
        self._dimensions[dimension.name] = dimension

    def add_join(self, join: Join) -> None:
        self._joins[join.name] = join

    def add_metric(self, metric: Metric) -> None:
        self._metrics[metric.name] = metric

    def add_metrics(self, metrics: Iterable[Metric]) -> None:
        for metric in metrics:
            self.add_metric(metric)

    # -- lookups ----------------------------------------------------------
    @property
    def tables(self) -> dict[str, SourceTable]:
        return dict(self._tables)

    @property
    def entities(self) -> dict[str, Entity]:
        return dict(self._entities)

    @property
    def dimensions(self) -> dict[str, Dimension]:
        return dict(self._dimensions)

    @property
    def joins(self) -> dict[str, Join]:
        return dict(self._joins)

    @property
    def metrics(self) -> dict[str, Metric]:
        return dict(self._metrics)

    def get_table(self, name: str) -> SourceTable:
        try:
            return self._tables[name]
        except KeyError as exc:
            raise CatalogValidationError(f"unknown source table: {name}") from exc

    def get_entity(self, name: str) -> Entity:
        try:
            return self._entities[name]
        except KeyError as exc:
            raise UnknownEntityError(f"unknown entity: {name}") from exc

    def get_dimension(self, name: str) -> Dimension:
        try:
            return self._dimensions[name]
        except KeyError as exc:
            raise UnknownDimensionError(
                f"unknown dimension: {name} (known: {sorted(self._dimensions)})") from exc

    def get_metric(self, name: str) -> Metric:
        try:
            return self._metrics[name]
        except KeyError as exc:
            raise UnknownMetricError(
                f"unknown metric: {name} (known: {sorted(self._metrics)})") from exc

    def has_metric(self, name: str) -> bool:
        return name in self._metrics

    def list_metrics(self, *, status: MetricStatus | None = None,
                     tier: Tier | None = None, owner: str | None = None,
                     tag: str | None = None) -> list[Metric]:
        out = sorted(self._metrics.values(), key=lambda m: m.name)
        if status is not None:
            out = [m for m in out if m.status == status]
        if tier is not None:
            out = [m for m in out if m.tier == tier]
        if owner is not None:
            out = [m for m in out if m.owner == owner]
        if tag is not None:
            out = [m for m in out if tag in m.tags]
        return out

    def list_dimensions(self) -> list[Dimension]:
        return sorted(self._dimensions.values(), key=lambda d: d.name)

    # -- validation -------------------------------------------------------
    def validate(self) -> list[str]:
        """Return a list of catalog problems (empty means valid)."""
        problems: list[str] = []
        for entity in self._entities.values():
            table = self._tables.get(entity.table)
            if table is None:
                problems.append(f"entity {entity.name}: unknown table {entity.table}")
            elif entity.primary_key not in table.columns:
                problems.append(
                    f"entity {entity.name}: primary key {entity.primary_key} "
                    f"not on table {entity.table}")
        for dim in self._dimensions.values():
            entity = self._entities.get(dim.entity)
            if entity is None:
                problems.append(f"dimension {dim.name}: unknown entity {dim.entity}")
            elif dim.column not in self._tables[entity.table].columns:
                problems.append(
                    f"dimension {dim.name}: column {dim.column} not on {entity.table}")
        for join in self._joins.values():
            for side, ent_name, key in (
                    ("left", join.left_entity, join.left_key),
                    ("right", join.right_entity, join.right_key)):
                entity = self._entities.get(ent_name)
                if entity is None:
                    problems.append(f"join {join.name}: unknown {side} entity {ent_name}")
                elif key not in self._tables[entity.table].columns:
                    problems.append(
                        f"join {join.name}: {side} key {key} not on {entity.table}")
            if join.join_type not in ("left", "inner"):
                problems.append(f"join {join.name}: unsupported join_type {join.join_type}")
        for metric in self._metrics.values():
            entity = self._entities.get(metric.entity)
            if entity is None:
                problems.append(f"metric {metric.name}: unknown entity {metric.entity}")
                continue
            if metric.is_derived:
                for part_name in (metric.numerator, metric.denominator):
                    part = self._metrics.get(part_name or "")
                    if part is None:
                        problems.append(
                            f"metric {metric.name}: unknown part {part_name}")
                    elif part.is_derived:
                        problems.append(
                            f"metric {metric.name}: part {part_name} is itself derived")
                    elif part.entity != metric.entity:
                        problems.append(
                            f"metric {metric.name}: part {part_name} is on a "
                            f"different entity ({part.entity})")
            elif metric.measure_column is None:
                problems.append(f"metric {metric.name}: no measure column and not derived")
            elif metric.measure_column not in self._tables[entity.table].columns:
                problems.append(
                    f"metric {metric.name}: column {metric.measure_column} "
                    f"not on {entity.table}")
        return problems

    def assert_valid(self) -> None:
        problems = self.validate()
        if problems:
            raise CatalogValidationError("; ".join(problems))

    def to_dict(self) -> dict:
        return {
            "tables": [t.to_dict() for t in sorted(self._tables.values(), key=lambda t: t.name)],
            "entities": [e.to_dict() for e in sorted(self._entities.values(), key=lambda e: e.name)],
            "dimensions": [d.to_dict() for d in self.list_dimensions()],
            "joins": [j.to_dict() for j in sorted(self._joins.values(), key=lambda j: j.name)],
            "metrics": [m.to_dict() for m in self.list_metrics()],
        }
