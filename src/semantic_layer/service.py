"""Service layer and FastAPI app factory.

``SemanticService`` holds the framework-free logic (catalog views,
compile, query with cache, lineage, governance) so it is testable
without a web stack. ``create_app`` wraps it in FastAPI, imported
lazily inside the factory — importing this module never requires
FastAPI to be installed.

    GET  /health                  liveness
    GET  /catalog                 full semantic model
    GET  /metrics                 metrics (filter: ?status= ?tier= ?owner= ?tag=)
    GET  /metrics/{name}          one metric + its lineage
    GET  /dimensions              dimensions
    POST /compile                 request -> generated SQL (no execution)
    POST /query                   request -> rows (cached, TTL)
    GET  /lineage/{metric}        metric lineage
    GET  /governance              governance audit report
    GET  /cache/stats             cache hit/miss/freshness stats
"""
from __future__ import annotations

from typing import Any

from .cache import QueryCache
from .catalog import SemanticCatalog
from .compiler import compile_query
from .definitions import build_default_catalog
from .executor import SemanticExecutor, build_connection
from .governance import audit_catalog
from .lineage import metric_lineage, query_lineage
from .models import MetricStatus, QueryRequest, Tier


class SemanticService:
    def __init__(self, catalog: SemanticCatalog | None = None,
                 cache: QueryCache | None = None) -> None:
        self.catalog = catalog or build_default_catalog()
        self.cache = cache if cache is not None else QueryCache()
        self.executor = SemanticExecutor(self.catalog, build_connection(),
                                         cache=self.cache)

    def list_metrics(self, **filters: Any) -> list[dict]:
        status = MetricStatus(filters["status"]) if filters.get("status") else None
        tier = Tier(filters["tier"]) if filters.get("tier") else None
        return [m.to_dict() for m in self.catalog.list_metrics(
            status=status, tier=tier, owner=filters.get("owner"),
            tag=filters.get("tag"))]

    def compile(self, request: QueryRequest) -> dict:
        return compile_query(self.catalog, request).to_dict()

    def query(self, request: QueryRequest) -> dict:
        return self.executor.query(request).to_dict()

    def lineage(self, metric_name: str) -> dict:
        return metric_lineage(self.catalog, metric_name).to_dict()

    def query_lineage(self, request: QueryRequest) -> dict:
        return query_lineage(self.catalog, request)

    def governance_report(self) -> dict:
        return audit_catalog(self.catalog).to_dict()


def create_app(service: SemanticService | None = None):  # type: ignore[no-untyped-def]
    try:
        from fastapi import FastAPI, HTTPException
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("install the api extra: pip install -e '.[api]'") from exc

    from .errors import SemanticLayerError

    svc = service or SemanticService()
    app = FastAPI(title="Semantic Layer Metrics Platform", version="0.1.0")

    def _handle(fn):  # type: ignore[no-untyped-def]
        try:
            return fn()
        except SemanticLayerError as exc:
            status = 404 if "unknown" in str(exc) else 422
            raise HTTPException(status_code=status, detail=str(exc)) from exc

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/catalog")
    def catalog() -> dict:
        return svc.catalog.to_dict()

    @app.get("/metrics")
    def metrics(status: str | None = None, tier: str | None = None,
                owner: str | None = None, tag: str | None = None) -> dict:
        return _handle(lambda: {"metrics": svc.list_metrics(
            status=status, tier=tier, owner=owner, tag=tag)})

    @app.get("/metrics/{name}")
    def one_metric(name: str) -> dict:
        return _handle(lambda: {
            "metric": svc.catalog.get_metric(name).to_dict(),
            "lineage": svc.lineage(name)})

    @app.get("/dimensions")
    def dimensions() -> dict:
        return {"dimensions": [d.to_dict() for d in svc.catalog.list_dimensions()]}

    @app.post("/compile")
    def compile_endpoint(req: dict) -> dict:
        return _handle(lambda: svc.compile(QueryRequest.from_dict(req)))

    @app.post("/query")
    def query_endpoint(req: dict) -> dict:
        return _handle(lambda: svc.query(QueryRequest.from_dict(req)))

    @app.get("/lineage/{metric}")
    def lineage_endpoint(metric: str) -> dict:
        return _handle(lambda: svc.lineage(metric))

    @app.get("/governance")
    def governance() -> dict:
        return svc.governance_report()

    @app.get("/cache/stats")
    def cache_stats() -> dict:
        return svc.cache.stats.to_dict()

    return app
