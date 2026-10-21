# Architecture — Semantic Layer Metrics Platform

## Component view

```
  definitions ───▶ │  Catalog / Registry  │  tables · entities ·
  (code, not SQL)  │  validation          │  dimensions · joins · metrics
                   └──────────┬───────────┘
                              │ validated model
                              ▼
  QueryRequest ──▶ ┌────────────────────┐      ┌──────────────────┐
  metrics + dims   │  Governance gate    │─────▶│  Compiler         │
  + filters        │  draft / deprecated │      │  join planning    │
                   └────────────────────┘      │  fan-out guard    │
                                               │  deterministic SQL│
                                               └────────┬─────────┘
                              ┌─────────────────────────┼───────────────────┐
                              ▼                         ▼                   ▼
                     ┌──────────────┐          ┌──────────────┐   ┌──────────────┐
                     │  Executor     │          │  TTL cache    │   │  Lineage      │
                     │  sqlite over  │          │  key = SQL +  │   │  metric ->    │
                     │  synthetic    │          │  params, TTL  │   │  tables/cols  │
                     │  data         │          │  freshness    │   │  + joins      │
                     └──────────────┘          └──────────────┘   └──────────────┘
                              │
                              ▼
                 FastAPI / CLI: /metrics /compile /query
                                /lineage /governance /cache/stats
```

## Data flow, step by step

1. **Define.** A metric is code: an entity, a measure column, an
   aggregation, plus governance metadata (owner, tier, status, tags).
   A dimension is an entity + column. A join is two entities, their
   key columns, and a cardinality. No definition contains SQL.
2. **Validate the catalog.** Referential integrity is checked at build
   time: entities point at real tables, measures and dimensions point
   at real columns, joins point at real key columns, and derived
   (ratio) metrics point at real, non-derived metrics on the same
   entity.
3. **Gate on governance.** Draft metrics need `allow_draft`;
   deprecated metrics need `allow_deprecated` (and the error names
   the replacement). Certification itself is gated: a metric cannot
   be certified without an owner, a description, and gold/silver tier.
4. **Plan joins.** Breadth-first search over the declared join graph
   from the metrics' base entity to every entity the dimensions and
   filters need, neighbours visited in name order. No path is an
   error, never a silent cross join.
5. **Guard fan-out.** If a traversed join multiplies base rows
   (one-to-many or many-to-many in the traversal direction), SUM /
   AVG / COUNT measures would be inflated. The compiler refuses —
   unless every metric is `COUNT_DISTINCT`, which is fan-out-safe,
   or the caller explicitly passes `allow_fanout`.
6. **Generate SQL deterministically.** Select items follow request
   order, joins follow BFS order, values are always bound parameters.
   Identifiers come only from the catalog whitelist, so request input
   can never inject SQL. Same request → byte-identical SQL, which is
   what makes the cache key and golden-SQL tests meaningful.
7. **Execute and cache.** Results are cached under a hash of the
   compiled SQL + parameters with a TTL. A repeat inside the TTL is a
   hit; after it, the entry is a *stale miss* — counted separately,
   because freshness pressure is an operational signal.
8. **Trace lineage.** Metric lineage (measure column → table, derived
   metrics → their parts) and query lineage (all source tables and
   columns, joins used) are derived from the compiled query itself,
   so lineage cannot drift from what actually ran.

## Key decisions

### Why definitions as code, not YAML files or raw SQL strings?

Code gives type checking, refactoring, and unit tests for free, and
— decisively — a compiler can validate every identifier against a
whitelist. A raw-SQL metric definition is an injection surface and a
lineage dead end; a column reference is neither.

### Why refuse fan-out instead of silently deduplicating?

Some engines paper over fan-out with symmetric aggregates. That is
the right production answer for some workloads, but silently changing
a measure's semantics is worse than refusing the query and saying
why. The guard makes the trade-off explicit: distinct-count metrics
pass, an intentional `allow_fanout` passes, everything else stops.

### Why is the cache key the compiled SQL, not the request?

Two differently-shaped requests that compile to the same SQL are the
same query and should share an entry; two requests differing only in
a filter value compile to the same SQL *shape* but different
parameters, and must not collide. SQL + params is exactly the
identity that matters.

### Why sqlite and synthetic data?

The platform's value is in definition, compilation, governance and
lineage — none of which need a warehouse. A seeded generator makes
metric values reproducible in tests and CI, and the executor is a
thin seam: swapping the sqlite connection for a warehouse connection
changes nothing upstream.

### Why derived metrics are ratios of simple metrics only

`discount_rate = total_discount / total_revenue` covers the common
ratio case while keeping expansion trivially checkable: both parts
must exist, be non-derived, and share the derived metric's entity.
Arbitrary expression trees are the documented next step, behind the
same validation.

## Failure modes and what the platform does

| Failure | Behaviour |
|---|---|
| Unknown metric / dimension / filter field | Specific typed error naming what is known |
| Draft metric queried by default | `DraftMetricError`; requires explicit opt-in |
| Deprecated metric queried by default | `DeprecatedMetricError` naming the replacement |
| Join would fan out a SUM/COUNT | `FanOutError` naming the join; distinct-only or opt-in passes |
| Dimension on an unreachable entity | `NoJoinPathError`; never a cross join |
| Metrics from two base entities in one query | `InvalidQueryError` (one base entity per query) |
| Bad operator, bad limit, ordering by an unrequested field | `InvalidQueryError` before any SQL is built |
| Catalog references a missing column/table | `CatalogValidationError` at build time |
| Stale cache entry | Treated as a miss, counted as a stale miss, recomputed |

## Scaling notes (what production adds)

- **Warehouse execution** behind the executor seam (Snowflake /
  BigQuery / DuckDB), with the sqlite path kept for tests and samples.
- **Time dimensions with grains** (day/week/month truncation) and
  cumulative / window metrics, as new aggregation kinds behind the
  same `Metric` shape.
- **Access control per metric** (row- and metric-level) enforced at
  the governance gate, where policy already lives.
- **A shared remote cache** with invalidation events on source-table
  refresh, replacing the in-process TTL cache.
- **Catalog versioning**: definitions are code, so the catalog ships
  through the same review and release process as the services that
  consume it.
