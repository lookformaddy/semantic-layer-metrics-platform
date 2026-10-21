"""Semantic Layer Metrics Platform.

Metrics defined once as code — measures, dimensions, entities and
joins — compiled deterministically to SQL, governed (owners, tiers,
certified vs draft, deprecation), cached with TTL freshness, and
traced with lineage from metric to source table and column.
"""

from .cache import QueryCache, cache_key
from .catalog import SemanticCatalog
from .compiler import compile_query
from .definitions import build_default_catalog
from .executor import SemanticExecutor, build_connection, generate_dataset
from .governance import audit_catalog, certify, deprecate
from .lineage import downstream_metrics, metric_lineage, query_lineage
from .models import (Aggregation, CompiledQuery, Dimension, Entity, Filter,
                     Join, Metric, MetricStatus, QueryRequest, Tier)
from .registry import MetricRegistry

__version__ = "0.1.0"

__all__ = [
    "Aggregation", "CompiledQuery", "Dimension", "Entity", "Filter", "Join",
    "Metric", "MetricStatus", "QueryRequest", "Tier",
    "MetricRegistry", "QueryCache", "SemanticCatalog", "SemanticExecutor",
    "audit_catalog", "build_connection", "build_default_catalog", "cache_key",
    "certify", "compile_query", "deprecate", "downstream_metrics",
    "generate_dataset", "metric_lineage", "query_lineage",
]
