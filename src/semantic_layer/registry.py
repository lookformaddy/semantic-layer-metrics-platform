"""MetricRegistry: a thin, query-focused facade over SemanticCatalog.

Kept as its own module because in a real deployment the registry is
the published, versioned surface other teams depend on, while the
catalog also holds physical details (tables, joins) they never see.
"""
from __future__ import annotations

from .catalog import SemanticCatalog
from .models import Metric, MetricStatus, Tier


class MetricRegistry:
    def __init__(self, catalog: SemanticCatalog) -> None:
        self._catalog = catalog

    @property
    def catalog(self) -> SemanticCatalog:
        return self._catalog

    def register(self, metric: Metric) -> Metric:
        self._catalog.add_metric(metric)
        return metric

    def get(self, name: str) -> Metric:
        return self._catalog.get_metric(name)

    def certified(self) -> list[Metric]:
        return self._catalog.list_metrics(status=MetricStatus.CERTIFIED)

    def deprecated(self) -> list[Metric]:
        return self._catalog.list_metrics(status=MetricStatus.DEPRECATED)

    def search(self, text: str) -> list[Metric]:
        needle = text.lower()
        return [m for m in self._catalog.list_metrics()
                if needle in m.name.lower()
                or needle in m.description.lower()
                or needle in (m.label or "").lower()
                or any(needle in t.lower() for t in m.tags)]

    def by_owner(self, owner: str) -> list[Metric]:
        return self._catalog.list_metrics(owner=owner)

    def by_tier(self, tier: Tier) -> list[Metric]:
        return self._catalog.list_metrics(tier=tier)
