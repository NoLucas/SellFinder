from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health() -> None:
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["model_backend"] == "mock"


def test_predictions_single_item() -> None:
    payload = {
        "items": [
            {
                "item_id": "sku-1",
                "category": "electronics/laptop",
                "price": 1000,
                "condition": "good",
                "days_listed": 10,
            }
        ]
    }
    resp = client.post("/api/v1/predictions", json=payload)
    assert resp.status_code == 200
    body = resp.json()
    assert body["is_mock"] is True
    assert body["model_version"]
    assert len(body["predictions"]) == 1

    prediction = body["predictions"][0]
    assert prediction["item_id"] == "sku-1"
    assert 0 <= prediction["sell_probability"] <= 1
    assert prediction["recommended_price"] > 0
    assert prediction["estimated_days_to_sell"] >= 0


def test_predictions_requires_at_least_one_item() -> None:
    resp = client.post("/api/v1/predictions", json={"items": []})
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "validation_error"


def test_predictions_rejects_invalid_condition() -> None:
    payload = {
        "items": [
            {
                "item_id": "sku-2",
                "category": "furniture/chair",
                "price": 50,
                "condition": "brand_new",
            }
        ]
    }
    resp = client.post("/api/v1/predictions", json=payload)
    assert resp.status_code == 422
