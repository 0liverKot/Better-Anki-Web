from __future__ import annotations

from tests.conftest import Client, add_basic


def test_notetypes_exclude_image_occlusion(client: Client) -> None:
    names = [t["name"] for t in client.get("/api/notetypes").json()]
    assert "Basic" in names and "Cloze" in names
    assert "Image Occlusion" not in names


def test_deck_names_include_default(client: Client) -> None:
    decks = client.get("/api/decks/names").json()
    assert any(d["name"] == "Default" for d in decks)


def test_add_basic_note(client: Client) -> None:
    result = add_basic(client, "front", "back", tags="spanish verbs")
    assert result["card_count"] == 1
    assert client.get("/api/tags").json() == ["spanish", "verbs"]


def test_reversed_note_makes_two_cards(client: Client) -> None:
    result = add_basic(client, "hola", "hello", notetype="Basic (and reversed card)")
    assert result["card_count"] == 2


def test_empty_first_field_rejected(client: Client) -> None:
    defaults = client.get("/api/add/defaults").json()
    response = client.post(
        "/api/notes",
        json={"notetype_id": defaults["notetype_id"], "deck_id": defaults["deck_id"], "fields": ["", "x"]},
    )
    assert response.status_code == 400


def test_duplicate_needs_confirmation(client: Client) -> None:
    add_basic(client, "same")
    defaults = client.get("/api/add/defaults").json()
    body = {"notetype_id": defaults["notetype_id"], "deck_id": defaults["deck_id"], "fields": ["same", "y"]}
    response = client.post("/api/notes", json=body)
    assert response.status_code == 409
    assert response.json()["warning"] == "duplicate"
    assert client.post("/api/notes", json={**body, "force": True}).status_code == 200


def test_cloze(client: Client) -> None:
    result = add_basic(
        client, "", notetype="Cloze", fields=["{{c1::Paris}} is the capital of {{c2::France}}", ""]
    )
    assert result["card_count"] == 2


def test_cloze_in_basic_rejected(client: Client) -> None:
    defaults = client.get("/api/add/defaults").json()
    types = {t["name"]: t["id"] for t in client.get("/api/notetypes").json()}
    response = client.post(
        "/api/notes",
        json={"notetype_id": types["Basic"], "deck_id": defaults["deck_id"], "fields": ["{{c1::x}}", ""]},
    )
    assert response.status_code == 400


def test_media_upload_and_serve(client: Client) -> None:
    uploaded = client.post(
        "/api/media", files={"file": ("my pic.png", b"\x89PNG\r\n\x1a\nfake", "image/png")}
    ).json()
    name = uploaded["filename"]
    base = client.get("/api/review/1/next").json()["media_base"]

    response = client.get(f"{base}{name}")
    assert response.status_code == 200
    assert response.content.startswith(b"\x89PNG")
    assert response.headers["content-security-policy"] == "sandbox"

    assert client.get(f"/media/wrongtoken/{name}").status_code == 404
    assert client.get(f"{base}..%2Fcollection.anki2").status_code == 404
    assert client.get(f"{base}missing.png").status_code == 404
