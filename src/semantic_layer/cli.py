"""Command-line interface.

    semantic-layer demo                       run the end-to-end demo
    semantic-layer metrics [--status S]       list metrics
    semantic-layer compile --metrics a,b --dimensions x,y [--filter f=v]
    semantic-layer query --metrics a,b --dimensions x,y [--filter f=v]
    semantic-layer lineage <metric>           print metric lineage
    semantic-layer serve [--port N]           run the FastAPI service (api extra)
"""
from __future__ import annotations

import argparse
import json

from .compiler import compile_query
from .definitions import build_default_catalog
from .demo import run_demo
from .lineage import metric_lineage
from .models import Filter, QueryRequest
from .service import SemanticService


def _split(value: str | None) -> list[str]:
    return [v.strip() for v in value.split(",") if v.strip()] if value else []


def _request_from_args(args: argparse.Namespace) -> QueryRequest:
    filters = []
    for raw in getattr(args, "filter", []) or []:
        field_name, _, value = raw.partition("=")
        filters.append(Filter(field_name.strip(), "=", value.strip()))
    return QueryRequest(metrics=_split(args.metrics),
                        dimensions=_split(args.dimensions), filters=filters,
                        allow_draft=args.allow_draft,
                        allow_deprecated=args.allow_deprecated,
                        allow_fanout=args.allow_fanout,
                        limit=args.limit)


def _add_query_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--metrics", required=True, help="comma-separated metric names")
    parser.add_argument("--dimensions", default="", help="comma-separated dimension names")
    parser.add_argument("--filter", action="append", default=[],
                        help="dimension=value (repeatable)")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--allow-draft", action="store_true")
    parser.add_argument("--allow-deprecated", action="store_true")
    parser.add_argument("--allow-fanout", action="store_true")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="semantic-layer", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("demo", help="run the end-to-end demo")

    metrics_cmd = sub.add_parser("metrics", help="list metrics")
    metrics_cmd.add_argument("--status", default=None)

    compile_cmd = sub.add_parser("compile", help="compile a query to SQL")
    _add_query_args(compile_cmd)

    query_cmd = sub.add_parser("query", help="compile and run a query")
    _add_query_args(query_cmd)

    lineage_cmd = sub.add_parser("lineage", help="print lineage for a metric")
    lineage_cmd.add_argument("metric")

    serve = sub.add_parser("serve", help="run the FastAPI service")
    serve.add_argument("--host", default="0.0.0.0")
    serve.add_argument("--port", type=int, default=8000)

    args = parser.parse_args(argv)

    if args.command == "demo":
        print(json.dumps(run_demo(), indent=2, default=str))
        return 0
    if args.command == "metrics":
        service = SemanticService()
        print(json.dumps(service.list_metrics(status=args.status), indent=2))
        return 0
    if args.command == "compile":
        catalog = build_default_catalog()
        print(json.dumps(compile_query(catalog, _request_from_args(args)).to_dict(),
                         indent=2, default=str))
        return 0
    if args.command == "query":
        service = SemanticService()
        print(json.dumps(service.query(_request_from_args(args)), indent=2, default=str))
        return 0
    if args.command == "lineage":
        catalog = build_default_catalog()
        print(json.dumps(metric_lineage(catalog, args.metric).to_dict(), indent=2))
        return 0
    # serve
    import uvicorn  # pragma: no cover
    from .service import create_app  # pragma: no cover
    uvicorn.run(create_app(), host=args.host, port=args.port)  # pragma: no cover
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
