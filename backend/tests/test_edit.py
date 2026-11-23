from __future__ import annotations

from tests.conftest import Client, add_basic


def _deck(client: Client, name: str) -> int:
    with client.app.state.cm.use() as col:  # type: ignore[attr-defined]
        return col.decks.id(name)


def _note_id(client: Client, query: str) -> int:
    return client.get("/api/search", params={"q": query}).json()["notes"][0]["id"]


def test_edit_data_has_raw_html(client: Client) -> None:
    add_basic(client, "hola <b>amigo</b>", "hello", tags="spanish greetings")
    nid = _note_id(client, "amigo")
    data = client.get(f"/api/notes/{nid}/edit").json()
    assert data["fields"] == ["hola <b>amigo</b>", "hello"]
    assert data["tags"] == "greetings spanish"
    assert data["notetype"]["name"] == "Basic"
    assert data["deck_id"] == client.get("/api/add/defaults").json()["deck_id"]
    assert data["media_base"].startswith("/media/")
    assert isinstance(data["version"], str)


def test_edit_fields_tags_and_deck(client: Client) -> None:
    add_basic(client, "hola", "helo", notetype="Basic (and reversed card)")
    nid = _note_id(client, "hola")
    data = client.get(f"/api/notes/{nid}/edit").json()
    spanish = _deck(client, "Spanish")

    res = client.put(
        f"/api/notes/{nid}",
        json={"fields": ["hola", "hello"], "tags": "fixed", "deck_id": spanish, "version": data["version"]},
    )
    assert res.status_code == 200, res.text
    assert res.json()["cards_moved"] == 2

    detail = client.get(f"/api/notes/{nid}").json()
    assert detail["note"]["fields"][1]["text"] == "hello"
    assert detail["note"]["tags"] == ["fixed"]
    assert {c["deck"] for c in detail["cards"]} == {"Spanish"}
    # Searching finds the corrected text, not the old one.
    assert client.get("/api/search", params={"q": "helo"}).json()["total"] == 0


def test_edit_without_deck_keeps_cards_in_place(client: Client) -> None:
    add_basic(client, "uno", "one")
    nid = _note_id(client, "uno")
    res = client.put(f"/api/notes/{nid}", json={"fields": ["uno", "1"], "tags": ""})
    assert res.json()["cards_moved"] == 0


def test_edit_rejects_stale_version(client: Client) -> None:
    add_basic(client, "dos", "two")
    nid = _note_id(client, "dos")
    version = client.get(f"/api/notes/{nid}/edit").json()["version"]
    with client.app.state.cm.use() as col:  # type: ignore[attr-defined]
        note = col.get_note(nid)
        note["Back"] = "changed on another device"
        col.update_note(note)
    res = client.put(f"/api/notes/{nid}", json={"fields": ["dos", "2"], "version": version})
    assert res.status_code == 409
    assert "changed somewhere else" in res.json()["detail"]


def test_edit_validation_matches_adding(client: Client) -> None:
    add_basic(client, "tres", "three")
    add_basic(client, "cuatro", "four")
    nid = _note_id(client, "tres")
    # Same checks as adding: an empty first field is refused...
    assert client.put(f"/api/notes/{nid}", json={"fields": ["", "x"]}).status_code == 400
    assert client.put(f"/api/notes/{nid}", json={"fields": ["a"]}).status_code == 400
    # ...but becoming a duplicate of another note is fine when editing.
    assert client.put(f"/api/notes/{nid}", json={"fields": ["cuatro", "x"]}).status_code == 200
    # Filtered decks and unknown decks are refused.
    assert client.put(f"/api/notes/{nid}", json={"fields": ["x", "y"], "deck_id": 999}).status_code == 404


def test_edit_cloze_missing_needs_confirmation(client: Client) -> None:
    add_basic(client, "", notetype="Cloze", fields=["{{c1::Paris}} is in France", ""])
    nid = _note_id(client, "Paris")
    body = {"fields": ["Paris is in France", ""]}
    res = client.put(f"/api/notes/{nid}", json=body)
    assert res.status_code == 409 and res.json()["warning"] == "missing_cloze"
    assert client.put(f"/api/notes/{nid}", json={**body, "force": True}).status_code == 200


def test_preview_says_editable(client: Client) -> None:
    add_basic(client, "cinco", "five")
    nid = _note_id(client, "cinco")
    assert client.get(f"/api/notes/{nid}").json()["note"]["editable"] is True
