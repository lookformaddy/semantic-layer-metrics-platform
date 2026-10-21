"""The compiler: metric + dimension + filter requests -> deterministic SQL.

Deterministic means: same request, byte-identical SQL. Joins are
discovered by breadth-first search over the declared join graph
(neighbours visited in name order), select items follow request order,
and every value is a bound parameter — identifiers only ever come from
the catalog whitelist, never from the request, so there is no string
interpolation of user input into SQL.

Fan-out guard: traversing a join in a direction that multiplies base
rows (one-to-many / many-to-many) inflates SUM/AVG/COUNT measures.
The compiler refuses such queries unless every metric is
COUNT_DISTINCT (fan-out-safe) or the caller passes ``allow_fanout``.
"""
from __future__ import annotations

from collections import deque

from .catalog import SemanticCatalog
from .errors import FanOutError, InvalidQueryError, NoJoinPathError
from .governance import assert_queryable
from .models import (Aggregation, Cardinality, CompiledQuery, Filter, Join,
                     Metric, QueryRequest)

_SQL_AGG = {
    Aggregation.SUM: "SUM", Aggregation.COUNT: "COUNT",
    Aggregation.COUNT_DISTINCT: "COUNT", Aggregation.AVG: "AVG",
    Aggregation.MIN: "MIN", Aggregation.MAX: "MAX",
}
MAX_LIMIT = 10_000


def _alias(entity: str) -> str:
    return f"t_{entity}"


def _aggregate_sql(metric: Metric, catalog: SemanticCatalog) -> str:
    alias = _alias(metric.entity)
    if metric.is_derived:
        num = catalog.get_metric(metric.numerator or "")
        den = catalog.get_metric(metric.denominator or "")
        return (f"CAST({_aggregate_sql(num, catalog)} AS REAL) "
                f"/ NULLIF({_aggregate_sql(den, catalog)}, 0)")
    col = f"{alias}.{metric.measure_column}"
    if metric.aggregation == Aggregation.COUNT_DISTINCT:
        return f"COUNT(DISTINCT {col})"
    return f"{_SQL_AGG[metric.aggregation]}({col})"


def _plan_joins(catalog: SemanticCatalog, base_entity: str,
                needed_entities: set[str]) -> tuple[list[tuple[Join, bool]], list[str]]:
    """BFS from base_entity to every needed entity.

    Returns (steps, entity_order) where each step is (join, forward?)
    — forward means traversed left->right as declared.
    """
    adjacency: dict[str, list[tuple[str, Join, bool]]] = {}
    for join in catalog.joins.values():
        adjacency.setdefault(join.left_entity, []).append((join.right_entity, join, True))
        adjacency.setdefault(join.right_entity, []).append((join.left_entity, join, False))
    for neighbours in adjacency.values():
        neighbours.sort(key=lambda item: item[0])

    parent: dict[str, tuple[str, Join, bool] | None] = {base_entity: None}
    order = [base_entity]
    queue: deque[str] = deque([base_entity])
    while queue:
        current = queue.popleft()
        for nxt, join, forward in adjacency.get(current, []):
            if nxt not in parent:
                parent[nxt] = (current, join, forward)
                order.append(nxt)
                queue.append(nxt)

    steps: list[tuple[Join, bool]] = []
    used_entities: set[str] = set()
    for target in sorted(needed_entities):
        if target == base_entity:
            continue
        if target not in parent:
            raise NoJoinPathError(
                f"no join path from entity {base_entity} to entity {target}")
        node: str | None = target
        while node is not None and node != base_entity:
            prev, join, forward = parent[node]  # type: ignore[misc]
            if join.name not in {j.name for j, _ in steps}:
                steps.append((join, forward))
            used_entities.add(node)
            node = prev
    # Emit joins in BFS discovery order for determinism.
    rank = {name: i for i, name in enumerate(order)}
    steps.sort(key=lambda s: rank[s[0].right_entity if s[1] else s[0].left_entity])
    return steps, order


def _traversal_cardinality(join: Join, forward: bool) -> Cardinality:
    return join.cardinality if forward else join.cardinality.reversed()


def compile_query(catalog: SemanticCatalog, request: QueryRequest) -> CompiledQuery:
    if not request.metrics:
        raise InvalidQueryError("a query needs at least one metric")
    if len(set(request.metrics)) != len(request.metrics):
        raise InvalidQueryError("duplicate metrics in request")
    if len(set(request.dimensions)) != len(request.dimensions):
        raise InvalidQueryError("duplicate dimensions in request")
    if request.limit is not None and not (1 <= request.limit <= MAX_LIMIT):
        raise InvalidQueryError(f"limit must be between 1 and {MAX_LIMIT}")

    metrics = [catalog.get_metric(name) for name in request.metrics]
    for metric in metrics:
        assert_queryable(metric, allow_draft=request.allow_draft,
                         allow_deprecated=request.allow_deprecated)
        # Derived parts are gated by the derived metric's own status.
    base_entities = {m.entity for m in metrics}
    if len(base_entities) != 1:
        raise InvalidQueryError(
            f"metrics must share one base entity, got {sorted(base_entities)}")
    base_entity = metrics[0].entity

    dimensions = [catalog.get_dimension(name) for name in request.dimensions]
    filter_dims = []
    for flt in request.filters:
        if flt.operator not in Filter.ALLOWED_OPERATORS:
            raise InvalidQueryError(f"unsupported filter operator: {flt.operator}")
        if flt.operator in ("in", "not_in") and not isinstance(flt.value, (list, tuple)):
            raise InvalidQueryError(f"operator {flt.operator} needs a list value")
        filter_dims.append(catalog.get_dimension(flt.field))

    needed = {d.entity for d in dimensions} | {d.entity for d in filter_dims}
    steps, _ = _plan_joins(catalog, base_entity, needed)

    # Fan-out guard.
    fanout_steps = [(j, f) for j, f in steps
                    if _traversal_cardinality(j, f).fans_out]
    if fanout_steps and not request.allow_fanout:
        distinct_only = all(
            m.aggregation == Aggregation.COUNT_DISTINCT and not m.is_derived
            for m in metrics)
        if not distinct_only:
            names = ", ".join(j.name for j, _ in fanout_steps)
            raise FanOutError(
                f"join(s) {names} would fan out rows from entity {base_entity} "
                f"and inflate non-distinct measures "
                f"(pass allow_fanout if the duplication is intended)")

    base_table = catalog.get_entity(base_entity).table
    select_parts: list[str] = []
    source_columns: set[str] = set()
    for dim in dimensions:
        table = catalog.get_entity(dim.entity).table
        select_parts.append(f"{_alias(dim.entity)}.{dim.column} AS {dim.name}")
        source_columns.add(f"{table}.{dim.column}")
    for metric in metrics:
        select_parts.append(f"{_aggregate_sql(metric, catalog)} AS {metric.name}")
        parts = [metric] if not metric.is_derived else [
            catalog.get_metric(metric.numerator or ""),
            catalog.get_metric(metric.denominator or "")]
        for part in parts:
            table = catalog.get_entity(part.entity).table
            source_columns.add(f"{table}.{part.measure_column}")

    from_sql = f"{base_table} AS {_alias(base_entity)}"
    join_sql: list[str] = []
    joins_used: list[str] = []
    joined_tables: set[str] = {base_table}
    for join, forward in steps:
        new_entity = join.right_entity if forward else join.left_entity
        new_table = catalog.get_entity(new_entity).table
        left_entity = join.left_entity
        right_entity = join.right_entity
        verb = "LEFT JOIN" if join.join_type == "left" else "INNER JOIN"
        join_sql.append(
            f"{verb} {new_table} AS {_alias(new_entity)} "
            f"ON {_alias(left_entity)}.{join.left_key} = {_alias(right_entity)}.{join.right_key}")
        joins_used.append(join.name)
        joined_tables.add(new_table)
        for ent, key in ((left_entity, join.left_key), (right_entity, join.right_key)):
            source_columns.add(f"{catalog.get_entity(ent).table}.{key}")

    params: list = []
    where_parts: list[str] = []
    for flt, dim in zip(request.filters, filter_dims):
        col = f"{_alias(dim.entity)}.{dim.column}"
        if flt.operator in ("in", "not_in"):
            placeholders = ", ".join("?" for _ in flt.value)
            op = "IN" if flt.operator == "in" else "NOT IN"
            where_parts.append(f"{col} {op} ({placeholders})")
            params.extend(flt.value)
        elif flt.operator == "like":
            where_parts.append(f"{col} LIKE ?")
            params.append(flt.value)
        else:
            where_parts.append(f"{col} {flt.operator} ?")
            params.append(flt.value)

    sql_parts = ["SELECT " + ", ".join(select_parts), f"FROM {from_sql}"]
    sql_parts.extend(join_sql)
    if where_parts:
        sql_parts.append("WHERE " + " AND ".join(where_parts))
    if dimensions:
        group_cols = ", ".join(f"{_alias(d.entity)}.{d.column}" for d in dimensions)
        sql_parts.append(f"GROUP BY {group_cols}")
    if request.order_by:
        order_parts = []
        allowed = set(request.metrics) | set(request.dimensions)
        for item in request.order_by:
            desc = item.startswith("-")
            name = item[1:] if desc else item
            if name not in allowed:
                raise InvalidQueryError(
                    f"cannot order by {name}: not a requested metric or dimension")
            order_parts.append(f"{name} DESC" if desc else f"{name} ASC")
        sql_parts.append("ORDER BY " + ", ".join(order_parts))
    if request.limit is not None:
        sql_parts.append(f"LIMIT {int(request.limit)}")

    return CompiledQuery(
        sql=" ".join(sql_parts), params=tuple(params),
        metrics=tuple(request.metrics), dimensions=tuple(request.dimensions),
        joins_used=tuple(joins_used),
        source_tables=tuple(sorted(joined_tables)),
        source_columns=tuple(sorted(source_columns)))
