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


# Renaming and deleting
##########################################################################


def _tree(client: Client) -> list[dict]:
    return client.get("/api/decks").json()["decks"]


def _find(decks: list[dict], full_name: str) -> dict | None:
    for deck in decks:
        if deck["full_name"] == full_name:
            return deck
        if found := _find(deck["children"], full_name):
            return found
    return None


def _add_card(client: Client, deck_id: int, front: str) -> None:
    types = {t["name"]: t["id"] for t in client.get("/api/notetypes").json()}
    res = client.post(
        "/api/notes", json={"notetype_id": types["Basic"], "deck_id": deck_id, "fields": [front, "x"]}
    )
    assert res.status_code == 200, res.text


def test_tree_has_full_names(client: Client) -> None:
    client.post("/api/decks", json={"name": "Languages::French::Verbs"})
    verbs = _find(_tree(client), "Languages::French::Verbs")
    assert verbs and verbs["name"] == "Verbs"


def test_rename_deck_keeps_cards_and_subdecks(client: Client) -> None:
    deck = client.post("/api/decks", json={"name": "Spansh"}).json()
    sub = client.post("/api/decks", json={"name": "Spansh::Verbs"}).json()
    _add_card(client, deck["id"], "hola")
    res = client.put(f"/api/decks/{deck['id']}", json={"name": "  Spanish "})
    assert res.status_code == 200, res.text
    assert res.json() == {"id": deck["id"], "name": "Spanish", "changed": True}
    tree = _tree(client)
    assert _find(tree, "Spansh") is None
    assert _find(tree, "Spanish")["new"] == 1
    assert _find(tree, "Spanish::Verbs")["id"] == sub["id"]


def test_rename_can_move_deck_under_a_parent(client: Client) -> None:
    deck = client.post("/api/decks", json={"name": "Verbs"}).json()
    parent = client.post("/api/decks", json={"name": "German"}).json()
    client.post(f"/api/decks/{parent['id']}/collapse", json={"collapsed": True})
    res = client.put(f"/api/decks/{deck['id']}", json={"name": "German :: Verbs"})
    assert res.json()["name"] == "German::Verbs"
    german = _find(_tree(client), "German")
    assert german["collapsed"] is False  # opened so the moved deck is visible
    assert [c["id"] for c in german["children"]] == [deck["id"]]
    # A brand-new parent is created too.
    client.put(f"/api/decks/{deck['id']}", json={"name": "Languages::German::Verbs"})
    assert _find(_tree(client), "Languages::German::Verbs")["id"] == deck["id"]


def test_rename_conflicts_and_case_change(client: Client) -> None:
    taken = client.post("/api/decks", json={"name": "Maths"}).json()
    deck = client.post("/api/decks", json={"name": "physics"}).json()
    res = client.put(f"/api/decks/{deck['id']}", json={"name": "maths"})
    assert res.status_code == 409  # Anki itself would quietly rename it to "maths+"
    assert res.json()["id"] == taken["id"]
    assert client.put(f"/api/decks/{deck['id']}", json={"name": "Physics"}).json()["name"] == "Physics"
    unchanged = client.put(f"/api/decks/{deck['id']}", json={"name": "Physics"})
    assert unchanged.status_code == 200 and unchanged.json()["name"] == "Physics"


def test_rename_rejects_bad_names(client: Client) -> None:
    deck = client.post("/api/decks", json={"name": "Topic"}).json()
    client.post("/api/decks", json={"name": "Topic::Sub"})
    for name in ["", "  ", "A::::B", "Trail::"]:
        assert client.put(f"/api/decks/{deck['id']}", json={"name": name}).status_code == 400, name
    inside = client.put(f"/api/decks/{deck['id']}", json={"name": "topic::Sub::Topic"})
    assert inside.status_code == 400 and "inside" in inside.json()["detail"]
    assert client.put("/api/decks/999999", json={"name": "X"}).status_code == 404
    assert _find(_tree(client), "Topic::Sub")


def test_delete_deck_removes_subdecks_and_cards(client: Client) -> None:
    deck = client.post("/api/decks", json={"name": "History"}).json()
    sub = client.post("/api/decks", json={"name": "History::Rome"}).json()
    keep = client.post("/api/decks", json={"name": "Keep"}).json()
    _add_card(client, deck["id"], "1066")
    _add_card(client, sub["id"], "753 BC")
    _add_card(client, keep["id"], "stays")

    info = client.get(f"/api/decks/{deck['id']}").json()
    assert info == {"id": deck["id"], "name": "History", "filtered": False, "subdecks": 1, "cards": 2}

    res = client.delete(f"/api/decks/{deck['id']}")
    assert res.status_code == 200, res.text
    assert res.json()["cards_deleted"] == 2
    tree = _tree(client)
    assert _find(tree, "History") is None and _find(tree, "History::Rome") is None
    assert _find(tree, "Keep")["new"] == 1
    assert client.get("/api/search", params={"q": "1066"}).json()["notes"] == []
    assert len(client.get("/api/search", params={"q": "stays"}).json()["notes"]) == 1
    assert client.delete(f"/api/decks/{deck['id']}").status_code == 404
    assert client.get(f"/api/decks/{deck['id']}").status_code == 404


def test_deleting_the_last_used_deck_for_adding(client: Client) -> None:
    deck = client.post("/api/decks", json={"name": "Temp"}).json()
    _add_card(client, deck["id"], "temp card")  # makes it the deck new cards default to
    client.delete(f"/api/decks/{deck['id']}")
    fallback = client.get("/api/add/defaults").json()["deck_id"]
    assert fallback != deck["id"]
    assert any(d["id"] == fallback for d in client.get("/api/decks/names").json())


def test_delete_and_rename_need_csrf_header(client: Client) -> None:
    deck = client.post("/api/decks", json={"name": "Guarded"}).json()
    headers = {"X-Requested-With": ""}
    assert client.delete(f"/api/decks/{deck['id']}", headers=headers).status_code == 403
    assert client.put(f"/api/decks/{deck['id']}", json={"name": "X"}, headers=headers).status_code == 403
    assert _find(_tree(client), "Guarded")


def test_filtered_decks_rename_and_delete(client: Client) -> None:
    home = client.post("/api/decks", json={"name": "Home"}).json()
    for i in range(3):
        _add_card(client, home["id"], f"card {i}")
    with client.app.state.cm.use() as col:  # type: ignore[attr-defined]
        filtered = col.sched.get_or_create_filtered_deck(deck_id=0)
        filtered.name = "Cram"
        filtered.config.search_terms[0].search = "deck:Home"
        cram_id = col.sched.add_or_update_filtered_deck(filtered).id

    info = client.get(f"/api/decks/{cram_id}").json()
    assert info["filtered"] is True and info["cards"] == 3
    # A filtered deck can't hold subdecks.
    res = client.put(f"/api/decks/{home['id']}", json={"name": "Cram::Home"})
    assert res.status_code == 400 and "Filtered" in res.json()["detail"]
    assert client.put(f"/api/decks/{cram_id}", json={"name": "Cram now"}).json()["name"] == "Cram now"

    # Deleting it sends the cards back home rather than deleting them.
    assert client.delete(f"/api/decks/{cram_id}").json()["cards_deleted"] == 0
    tree = _tree(client)
    assert _find(tree, "Cram now") is None
    assert _find(tree, "Home")["new"] == 3


# Moving (drag and drop)
##########################################################################


def _move(client: Client, deck_id: int, parent_id: int | None):  # type: ignore[no-untyped-def]
    return client.post(f"/api/decks/{deck_id}/move", json={"parent_id": parent_id})


def test_move_deck_into_another(client: Client) -> None:
    verbs = client.post("/api/decks", json={"name": "Verbs"}).json()
    irregular = client.post("/api/decks", json={"name": "Verbs::Irregular"}).json()
    _add_card(client, irregular["id"], "ser")
    spanish = client.post("/api/decks", json={"name": "Spanish"}).json()
    client.post(f"/api/decks/{spanish['id']}/collapse", json={"collapsed": True})

    res = _move(client, verbs["id"], spanish["id"])
    assert res.status_code == 200, res.text
    assert res.json() == {"id": verbs["id"], "name": "Spanish::Verbs", "changed": True}
    tree = _tree(client)
    assert _find(tree, "Spanish")["collapsed"] is False  # opened so the moved deck shows
    assert _find(tree, "Spanish::Verbs::Irregular")["id"] == irregular["id"]
    assert _find(tree, "Spanish::Verbs::Irregular")["new"] == 1
    assert _find(tree, "Verbs") is None

    # Dropping it on the deck it's already in changes nothing.
    again = _move(client, verbs["id"], spanish["id"])
    assert again.status_code == 200 and again.json()["changed"] is False


def test_move_deck_to_top_level(client: Client) -> None:
    deep = client.post("/api/decks", json={"name": "A::B::Deep"}).json()
    res = _move(client, deep["id"], None)
    assert res.json()["name"] == "Deep"
    tree = _tree(client)
    assert _find(tree, "Deep")["id"] == deep["id"] and _find(tree, "A::B")
    assert _move(client, deep["id"], None).json()["changed"] is False


def test_move_rejections(client: Client) -> None:
    top = client.post("/api/decks", json={"name": "Top"}).json()
    child = client.post("/api/decks", json={"name": "Top::Child"}).json()
    other = client.post("/api/decks", json={"name": "Other"}).json()
    client.post("/api/decks", json={"name": "Other::child"})

    # Into itself or one of its own subdecks
    assert _move(client, top["id"], top["id"]).status_code == 400
    assert _move(client, top["id"], child["id"]).status_code == 400
    # A deck with that name is already there (names are case-insensitive)
    conflict = _move(client, child["id"], other["id"])
    assert conflict.status_code == 409 and conflict.json()["name"] == "Other::child"
    # Missing decks
    assert _move(client, 999999, top["id"]).status_code == 404
    assert _move(client, top["id"], 999999).status_code == 404
    assert _find(_tree(client), "Top::Child")

    _add_card(client, other["id"], "for the filtered deck")
    with client.app.state.cm.use() as col:  # type: ignore[attr-defined]
        filtered = col.sched.get_or_create_filtered_deck(deck_id=0)
        filtered.name = "Cram"
        filtered.config.search_terms[0].search = "deck:Other"
        cram_id = col.sched.add_or_update_filtered_deck(filtered).id
    res = _move(client, top["id"], cram_id)
    assert res.status_code == 400 and "Filtered" in res.json()["detail"]
