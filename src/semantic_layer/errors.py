"""Typed errors for the semantic layer.

Every validation failure is a specific exception so API and CLI layers
can map them to precise status codes instead of string matching.
"""
from __future__ import annotations


class SemanticLayerError(Exception):
    """Base class for all semantic-layer errors."""


class UnknownMetricError(SemanticLayerError):
    """A requested metric is not in the catalog."""


class UnknownDimensionError(SemanticLayerError):
    """A requested dimension or filter field is not in the catalog."""


class UnknownEntityError(SemanticLayerError):
    """A referenced entity is not in the catalog."""


class CatalogValidationError(SemanticLayerError):
    """The catalog itself is inconsistent (bad join, missing column...)."""


class GovernanceError(SemanticLayerError):
    """A metric or query violates governance policy."""


class DeprecatedMetricError(GovernanceError):
    """A deprecated metric was queried without explicit opt-in."""


class DraftMetricError(GovernanceError):
    """A draft (uncertified) metric was queried without explicit opt-in."""


class FanOutError(SemanticLayerError):
    """A join path would fan out rows and inflate the requested measures."""


class NoJoinPathError(SemanticLayerError):
    """No join path connects the metric's entity to a dimension's entity."""


class InvalidQueryError(SemanticLayerError):
    """The query request itself is malformed (bad operator, limit, sort...)."""
