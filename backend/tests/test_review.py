from __future__ import annotations

from tests.conftest import Client, add_basic


def _deck_id(client: Client) -> int:
    return client.get("/api/add/defaults").json()["deck_id"]


def test_deck_tree_counts(client: Client) -> None:
    add_basic(client, "one")
    add_basic(client, "two")
    decks = client.get("/api/decks").json()["decks"]
    default = next(d for d in decks if d["id"] == _deck_id(client))
    assert default["new"] == 2


def test_review_answer_and_undo(client: Client) -> None:
    add_basic(client, "What is <b>2+2</b>?", "4")
    deck_id = _deck_id(client)

    first = client.get(f"/api/review/{deck_id}/next").json()
    card = first["card"]
    assert first["counts"] == {"new": 1, "learning": 0, "review": 0}
    assert card["queue"] == "new"
    assert "What is <b>2+2</b>?" in card["question"]
    assert "4" in card["answer"]
    assert len(card["buttons"]) == 4
    assert all("⁨" not in label for label in card["buttons"])
    assert first["media_base"].startswith("/media/")

    after = client.post(
        "/api/review/answer",
        json={"deck_id": deck_id, "card_id": card["id"], "rating": 3, "time_taken_ms": 4200},
    ).json()
    # "Good" on a new card moves it into learning.
    assert after["counts"]["new"] == 0
    assert after["undo"]

    undone = client.post("/api/review/undo", json={"deck_id": deck_id}).json()
    assert undone["card"]["id"] == card["id"]
    assert undone["counts"]["new"] == 1


def test_answer_stale_card_conflicts(client: Client) -> None:
    add_basic(client, "a")
    deck_id = _deck_id(client)
    card = client.get(f"/api/review/{deck_id}/next").json()["card"]
    response = client.post(
        "/api/review/answer",
        json={"deck_id": deck_id, "card_id": card["id"] + 999, "rating": 3, "time_taken_ms": 1},
    )
    assert response.status_code == 409


def test_empty_queue(client: Client) -> None:
    payload = client.get(f"/api/review/{_deck_id(client)}/next").json()
    assert payload["card"] is None


def test_sound_tags_become_play_buttons(client: Client) -> None:
    add_basic(client, "Listen [sound:hello world.mp3]", "[sound:clip.mp4]")
    card = client.get(f"/api/review/{_deck_id(client)}/next").json()["card"]
    assert 'data-av="q:0"' in card["question"]
    assert card["av"]["q"] == [{"kind": "audio", "file": "hello world.mp3"}]
    assert '<video class="baw-video" data-av="a:0" src="clip.mp4"' in card["answer"]


def test_type_in_answer(client: Client) -> None:
    add_basic(client, "Capital of France?", "Paris", notetype="Basic (type in the answer)")
    card = client.get(f"/api/review/{_deck_id(client)}/next").json()["card"]
    assert card["type_answer"] is True
    assert card["answer"] is None
    assert 'id="typeans"' in card["question"]

    answer = client.post(
        "/api/review/type-answer", json={"card_id": card["id"], "typed": "Pari"}
    ).json()["answer"]
    assert "typeGood" in answer and "typeMissed" in answer
    assert "[[type:" not in answer


def test_collapse_deck(client: Client) -> None:
    deck_id = _deck_id(client)
    assert client.post(f"/api/decks/{deck_id}/collapse", json={"collapsed": True}).status_code == 200
    assert client.post("/api/decks/12345/collapse", json={"collapsed": True}).status_code == 404
