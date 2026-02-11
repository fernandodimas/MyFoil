import json


def test_library_paged_contract(client):
    """Ensure /api/library/paged returns items both in envelope and as top-level fields"""
    resp = client.get("/api/library/paged?page=1&per_page=10")
    assert resp.status_code == 200
    data = resp.get_json()

    # Envelope form
    assert "code" in data and data["code"] == "SUCCESS"
    assert "data" in data
    assert isinstance(data["data"].get("items", []), list)

    # Top-level shortcuts
    assert isinstance(data.get("items", []), list)
    assert isinstance(data.get("pagination", {}), dict)

    # pagination sanity
    pagination = data.get("pagination") or data["data"].get("pagination")
    assert pagination is not None
    assert "total_items" in pagination
