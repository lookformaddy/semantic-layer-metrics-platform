"""Execution against a deterministic synthetic dataset in sqlite (stdlib).

The synthetic generator is seeded, so every run — demo, tests, CI —
sees byte-identical source data and metric values are reproducible.
The executor itself only needs a sqlite connection; pointing it at a
real warehouse is a connection swap, not a compiler change.
"""
from __future__ import annotations

import random
import sqlite3
from dataclasses import dataclass, field
from typing import Any

from .cache import QueryCache
from .catalog import SemanticCatalog
from .compiler import compile_query
from .models import CompiledQuery, QueryRequest

REGIONS = ("north", "south", "east", "west")
SEGMENTS = ("consumer", "small_business", "enterprise")
CHANNELS = ("online", "store", "partner")
STATUSES = ("completed", "completed", "completed", "refunded")
CATEGORIES = ("apparel", "electronics", "home", "grocery")


@dataclass
class SyntheticDataset:
    customers: list[dict[str, Any]] = field(default_factory=list)
    products: list[dict[str, Any]] = field(default_factory=list)
    orders: list[dict[str, Any]] = field(default_factory=list)


def generate_dataset(seed: int = 42, n_customers: int = 40,
                     n_products: int = 12, n_orders: int = 240) -> SyntheticDataset:
    rng = random.Random(seed)
    customers = [{
        "customer_id": f"C{1000 + i}",
        "customer_name": f"Customer {i + 1}",
        "region": REGIONS[i % len(REGIONS)],
        "segment": SEGMENTS[i % len(SEGMENTS)],
        "signup_date": f"2025-{(i % 12) + 1:02d}-{(i % 27) + 1:02d}",
    } for i in range(n_customers)]
    products = [{
        "product_id": f"P{200 + i}",
        "product_name": f"Product {i + 1}",
        "category": CATEGORIES[i % len(CATEGORIES)],
        "unit_cost": round(5.0 + rng.random() * 90.0, 2),
    } for i in range(n_products)]
    orders = []
    for i in range(n_orders):
        amount = round(20.0 + rng.random() * 480.0, 2)
        orders.append({
            "order_id": f"O{5000 + i}",
            "customer_id": customers[rng.randrange(n_customers)]["customer_id"],
            "product_id": products[rng.randrange(n_products)]["product_id"],
            "order_date": f"2026-{(i % 9) + 1:02d}-{(i % 27) + 1:02d}",
            "status": STATUSES[rng.randrange(len(STATUSES))],
            "channel": CHANNELS[rng.randrange(len(CHANNELS))],
            "amount": amount,
            "discount_amount": round(amount * rng.choice((0.0, 0.0, 0.05, 0.1)), 2),
            "quantity": rng.randrange(1, 6),
        })
    return SyntheticDataset(customers=customers, products=products, orders=orders)


def build_connection(dataset: SyntheticDataset | None = None) -> sqlite3.Connection:
    data = dataset or generate_dataset()
    # check_same_thread=False: the FastAPI surface serves queries from
    # worker threads against this one in-memory dataset.
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE customers (customer_id TEXT, customer_name TEXT,
            region TEXT, segment TEXT, signup_date TEXT);
        CREATE TABLE products (product_id TEXT, product_name TEXT,
            category TEXT, unit_cost REAL);
        CREATE TABLE orders (order_id TEXT, customer_id TEXT, product_id TEXT,
            order_date TEXT, status TEXT, channel TEXT, amount REAL,
            discount_amount REAL, quantity INTEGER);
        """)
    conn.executemany("INSERT INTO customers VALUES (:customer_id, :customer_name,"
                     " :region, :segment, :signup_date)", data.customers)
    conn.executemany("INSERT INTO products VALUES (:product_id, :product_name,"
                     " :category, :unit_cost)", data.products)
    conn.executemany("INSERT INTO orders VALUES (:order_id, :customer_id,"
                     " :product_id, :order_date, :status, :channel, :amount,"
                     " :discount_amount, :quantity)", data.orders)
    conn.commit()
    return conn


@dataclass
class QueryResult:
    rows: list[dict[str, Any]]
    compiled: CompiledQuery
    from_cache: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {"rows": self.rows, "row_count": len(self.rows),
                "sql": self.compiled.sql, "from_cache": self.from_cache}


class SemanticExecutor:
    """Compiles, optionally caches, and runs queries on a connection."""

    def __init__(self, catalog: SemanticCatalog,
                 connection: sqlite3.Connection,
                 cache: QueryCache | None = None) -> None:
        self.catalog = catalog
        self.connection = connection
        self.cache = cache

    def execute_compiled(self, compiled: CompiledQuery) -> list[dict[str, Any]]:
        cursor = self.connection.execute(compiled.sql, compiled.params)
        return [dict(row) for row in cursor.fetchall()]

    def query(self, request: QueryRequest) -> QueryResult:
        compiled = compile_query(self.catalog, request)
        if self.cache is not None:
            cached = self.cache.get(compiled)
            if cached is not None:
                return QueryResult(rows=cached, compiled=compiled, from_cache=True)
        rows = self.execute_compiled(compiled)
        if self.cache is not None:
            self.cache.put(compiled, rows)
        return QueryResult(rows=rows, compiled=compiled, from_cache=False)
