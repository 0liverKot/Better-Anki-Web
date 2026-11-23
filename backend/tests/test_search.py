from __future__ import annotations

from tests.conftest import Client, add_basic


def _deck(client: Client, name: str) -> int:
    """Create a deck by adding to it through the backend, returning its id."""
    cm = client.app.state.cm  # type: ignore[attr-defined]
    with cm.use() as col:
        return col.decks.id(name)


def _add_to(client: Client, deck_id: int, front: str, back: str, notetype: str = "Basic") -> int:
    types = {t["name"]: t["id"] for t in client.get("/api/notetypes").json()}
    res = client.post(
        "/api/notes",
        json={"notetype_id": types[notetype], "deck_id": deck_id, "fields": [front, back]},
    )
    assert res.status_code == 200, res.text
    return res.json()["note_id"]


def test_plain_words_match_front_or_back(client: Client) -> None:
    add_basic(client, "hablar", "to <b>speak</b>")
    add_basic(client, "comer", "to eat")

    by_front = client.get("/api/search", params={"q": "HABLAR"}).json()
    assert by_front["total"] == 1
    note = by_front["notes"][0]
    assert note["fields"][0] == {"name": "Front", "text": "hablar"}
    assert note["fields"][1]["text"] == "to speak"  # HTML stripped

    by_back = client.get("/api/search", params={"q": "speak"}).json()
    assert [n["id"] for n in by_back["notes"]] == [note["id"]]

    # Partial words match too, like in Anki.
    assert client.get("/api/search", params={"q": "spea"}).json()["total"] == 1
    assert client.get("/api/search", params={"q": "to"}).json()["total"] == 2
    assert client.get("/api/search", params={"q": "zebra"}).json()["total"] == 0


def test_deck_filter_includes_subdecks(client: Client) -> None:
    spanish = _deck(client, "Spanish")
    verbs = _deck(client, "Spanish::Verbs")
    biology = _deck(client, "Biology")
    _add_to(client, spanish, "la casa", "the house")
    _add_to(client, verbs, "la vivir", "to live")
    _add_to(client, biology, "la célula", "the cell")

    everywhere = client.get("/api/search", params={"q": "la"}).json()
    assert everywhere["total"] == 3
    in_spanish = client.get("/api/search", params={"q": "la", "deck_id": spanish}).json()
    assert in_spanish["total"] == 2
    in_verbs = client.get("/api/search", params={"q": "la", "deck_id": verbs}).json()
    assert [n["decks"] for n in in_verbs["notes"]] == [["Spanish::Verbs"]]

    # Empty query lists the whole deck (or everything), newest first.
    whole_deck = client.get("/api/search", params={"deck_id": biology}).json()
    assert whole_deck["total"] == 1
    all_notes = client.get("/api/search").json()
    assert [n["fields"][0]["text"] for n in all_notes["notes"]] == ["la célula", "la vivir", "la casa"]

    assert client.get("/api/search", params={"deck_id": 999}).status_code == 404


def test_anki_syntax_and_invalid_syntax_fallback(client: Client) -> None:
    add_basic(client, "f(x) = x + 1", "linear", tags="maths")
    add_basic(client, "other", "thing")

    assert client.get("/api/search", params={"q": "tag:maths"}).json()["total"] == 1
    assert client.get("/api/search", params={"q": "front:other"}).json()["total"] == 1

    # An unbalanced bracket isn't valid Anki syntax: it's searched as plain text instead.
    res = client.get("/api/search", params={"q": "f(x"}).json()
    assert res["total"] == 1
    assert res["syntax_note"] and "bracket" in res["syntax_note"]


def test_paging(client: Client) -> None:
    for i in range(5):
        add_basic(client, f"word {i}")
    first = client.get("/api/search", params={"q": "word", "limit": 2}).json()
    second = client.get("/api/search", params={"q": "word", "limit": 2, "offset": 2}).json()
    assert first["total"] == second["total"] == 5
    assert len(first["notes"]) == len(second["notes"]) == 2
    assert not {n["id"] for n in first["notes"]} & {n["id"] for n in second["notes"]}


def test_note_detail_preview(client: Client) -> None:
    add_basic(client, "hola", "hello", notetype="Basic (and reversed card)")
    note_id = client.get("/api/search", params={"q": "hola"}).json()["notes"][0]["id"]

    detail = client.get(f"/api/notes/{note_id}").json()
    assert detail["note"]["fields"][0]["text"] == "hola"
    assert [c["name"] for c in detail["cards"]] == ["Card 1", "Card 2"]
    card = detail["cards"][0]
    assert "hola" in card["question"] and "hello" in card["answer"]
    assert card["state"] == "new" and card["due_in_days"] is None
    assert detail["media_base"].startswith("/media/")

    assert client.get("/api/notes/123").status_code == 404


def test_type_answer_preview_shows_expected(client: Client) -> None:
    add_basic(client, "cat?", "el gato", notetype="Basic (type in the answer)")
    note_id = client.get("/api/search", params={"q": "gato"}).json()["notes"][0]["id"]
    card = client.get(f"/api/notes/{note_id}").json()["cards"][0]
    assert "el gato" in card["answer"]
    assert "[[type:" not in card["answer"] and "typeMissed" not in card["answer"]


def test_snippets_separate_lines_and_list_items(client: Client) -> None:
    add_basic(client, "Fruit<div><ul><li>apple</li><li>banana</li></ul></div>", "one<br>two")
    note = client.get("/api/search", params={"q": "banana"}).json()["notes"][0]
    assert note["fields"][0]["text"] == "Fruit apple banana"
    assert note["fields"][1]["text"] == "one two"
