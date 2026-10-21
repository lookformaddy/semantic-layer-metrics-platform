import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402

from semantic_layer.service import create_app  # noqa: E402


@pytest.fixture()
def client():
    return TestClient(create_app())


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_metrics_endpoints(client):
    body = client.get("/metrics").json()
    assert len(body["metrics"]) == 10
    one = client.get("/metrics/total_revenue").json()
    assert one["metric"]["status"] == "certified"
    assert one["lineage"]["source_columns"] == ["orders.amount"]
    assert client.get("/metrics/nope").status_code == 404


def test_compile_and_query_endpoints(client):
    compiled = client.post("/compile", json={"metrics": ["total_revenue"]})
    assert compiled.status_code == 200
    assert "SUM(t_order.amount)" in compiled.json()["sql"]
    result = client.post("/query", json={
        "metrics": ["order_count"], "dimensions": ["customer_region"]})
    assert result.json()["row_count"] == 4
    draft = client.post("/query", json={"metrics": ["repeat_order_share"]})
    assert draft.status_code == 422


def test_lineage_governance_cache_endpoints(client):
    assert client.get("/lineage/discount_rate").json()[
        "depends_on_metrics"] == ["total_discount", "total_revenue"]
    assert client.get("/governance").json()["ok"] is True
    client.post("/query", json={"metrics": ["order_count"]})
    client.post("/query", json={"metrics": ["order_count"]})
    assert client.get("/cache/stats").json()["hits"] >= 1
    dims = client.get("/dimensions").json()["dimensions"]
    assert any(d["name"] == "customer_region" for d in dims)
    assert client.get("/catalog").json()["metrics"]
