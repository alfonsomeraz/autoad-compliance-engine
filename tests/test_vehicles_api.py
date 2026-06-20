"""GET /vehicles + static UI serving tests."""

from __future__ import annotations


def test_lists_seeded_vehicles(client, civic):
    resp = client.get("/vehicles")
    assert resp.status_code == 200
    body = resp.json()
    vehicle = next(v for v in body if v["id"] == civic.id)
    assert vehicle["model"] == "Civic"
    assert vehicle["trim"] == "Sport"
    assert "dealer_price" in vehicle


def test_ui_index_is_served(client):
    resp = client.get("/ui/")
    assert resp.status_code == 200
    assert "AutoAd Compliance" in resp.text


def test_root_redirects_to_ui(client):
    resp = client.get("/", follow_redirects=False)
    assert resp.status_code in (307, 308)
    assert resp.headers["location"].startswith("/ui")
