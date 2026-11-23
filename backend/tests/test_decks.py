from __future__ import annotations

from tests.conftest import Client


def _names(client: Client) -> list[str]:
    return [d["name"] for d in client.get("/api/decks/names").json()]


def test_create_deck(client: Client) -> None:
    res = client.post("/api/decks", json={"name": "  Spanish  "})
    assert res.status_code == 200, res.text
    deck = res.json()
    assert deck["name"] == "Spanish"
    assert "Spanish" in _names(client)
    tree = client.get("/api/decks").json()["decks"]
    assert any(d["id"] == deck["id"] for d in tree)


def test_create_subdeck_creates_parent(client: Client) -> None:
    res = client.post("/api/decks", json={"name": "Languages :: French"})
    assert res.json()["name"] == "Languages::French"
    tree = client.get("/api/decks").json()["decks"]
    parent = next(d for d in tree if d["name"] == "Languages")
    assert [c["name"] for c in parent["children"]] == ["French"]
    assert parent["collapsed"] is False  # expanded so the new subdeck is visible

    # Even if the parent was collapsed, adding a subdeck opens it.
    client.post(f"/api/decks/{parent['id']}/collapse", json={"collapsed": True})
    client.post("/api/decks", json={"name": "Languages::German"})
    tree = client.get("/api/decks").json()["decks"]
    parent = next(d for d in tree if d["name"] == "Languages")
    assert parent["collapsed"] is False
    assert [c["name"] for c in parent["children"]] == ["French", "German"]


def test_duplicate_name_is_a_conflict(client: Client) -> None:
    first = client.post("/api/decks", json={"name": "Biology"}).json()
    res = client.post("/api/decks", json={"name": "biology"})
    assert res.status_code == 409
    assert res.json()["id"] == first["id"] and res.json()["name"] == "Biology"


def test_empty_names_rejected(client: Client) -> None:
    for name in ["", "   ", "A::::B", "::Lead", "Trail::"]:
        assert client.post("/api/decks", json={"name": name}).status_code == 400, name
    assert not any("blank" in n for n in _names(client))


def test_new_deck_can_receive_cards(client: Client) -> None:
    deck = client.post("/api/decks", json={"name": "Chemistry"}).json()
    types = {t["name"]: t["id"] for t in client.get("/api/notetypes").json()}
    res = client.post(
        "/api/notes",
        json={"notetype_id": types["Basic"], "deck_id": deck["id"], "fields": ["H2O", "water"]},
    )
    assert res.status_code == 200
    tree = client.get("/api/decks").json()["decks"]
    assert next(d for d in tree if d["id"] == deck["id"])["new"] == 1
