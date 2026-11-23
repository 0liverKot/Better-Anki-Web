from __future__ import annotations

from typing import Any

from anki.collection import Collection
from anki.decks import DeckCollapseScope, DeckId
from anki.errors import BackendError
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from ..auth import require_user
from ..collection import CollectionManager
from ..deps import get_cm

router = APIRouter(prefix="/api/decks", dependencies=[Depends(require_user)])


def _node(node: Any, parent: str = "") -> dict[str, Any]:
    full_name = f"{parent}::{node.name}" if parent else node.name
    return {
        "id": node.deck_id,
        "name": node.name,
        "full_name": full_name,
        "new": node.new_count,
        "learn": node.learn_count,
        "review": node.review_count,
        "collapsed": node.collapsed,
        "filtered": node.filtered,
        "children": [_node(child, full_name) for child in node.children],
    }


@router.get("")
def deck_tree(cm: CollectionManager = Depends(get_cm)) -> dict:
    with cm.use() as col:
        root = col.sched.deck_due_tree()
        return {
            "decks": [_node(child) for child in root.children],
            "current_deck_id": col.decks.get_current_id(),
        }


@router.get("/names")
def deck_names(cm: CollectionManager = Depends(get_cm)) -> list[dict]:
    """Decks new cards can be added to (filtered decks excluded)."""
    with cm.use() as col:
        # Hide an empty "Default" deck like desktop does, unless it's the only deck.
        decks = col.decks.all_names_and_ids(include_filtered=False, skip_empty_default=True)
        if not decks:
            decks = col.decks.all_names_and_ids(include_filtered=False)
        return [{"id": d.id, "name": d.name} for d in decks]


class DeckNameBody(BaseModel):
    # "Parent::Child" is a subdeck (the parent is created if it doesn't exist yet).
    name: str


def _clean_name(raw: str) -> str:
    # Anki would quietly turn empty parts ("A::::B", "Spanish::") into decks named "blank".
    parts = [part.strip() for part in raw.split("::")]
    if not all(parts):
        raise HTTPException(400, "Enter a deck name. For a subdeck use Parent::Child.")
    return "::".join(parts)


def _conflict(col: Collection, existing: DeckId) -> JSONResponse:
    name = col.decks.name(existing)
    return JSONResponse(
        {"detail": f'A deck called "{name}" already exists.', "id": existing, "name": name},
        status_code=409,
    )


def _expand_parents(col: Collection, deck_id: DeckId) -> str:
    """Expand the parents of a deck so it's visible in the tree; returns its full name."""
    full_name = col.decks.name(deck_id)
    parts = full_name.split("::")
    for depth in range(1, len(parts)):
        if parent_id := col.decks.id_for_name("::".join(parts[:depth])):
            col.decks.set_collapsed(parent_id, False, DeckCollapseScope.REVIEWER)
    return full_name


def _get_deck(col: Collection, deck_id: int) -> dict[str, Any]:
    deck = col.decks.get(DeckId(deck_id), default=False)
    if not deck:
        raise HTTPException(404, "Deck not found.")
    return deck


@router.post("", response_model=None)
def create_deck(body: DeckNameBody, cm: CollectionManager = Depends(get_cm)) -> dict | JSONResponse:
    name = _clean_name(body.name)
    with cm.use() as col:
        # Deck names are case-insensitive in Anki.
        if existing := col.decks.id_for_name(name):
            return _conflict(col, existing)
        try:
            deck_id = col.decks.add_normal_deck_with_name(name).id
        except BackendError as err:  # e.g. a filtered deck can't have subdecks
            raise HTTPException(400, str(err) or "That deck name can't be used.") from err
        # Anki creates decks collapsed; expand the parents so the new subdeck shows up.
        created = {"id": deck_id, "name": _expand_parents(col, DeckId(deck_id))}
    cm.mark_modified()
    return created


@router.get("/{deck_id}")
def deck_info(deck_id: int, cm: CollectionManager = Depends(get_cm)) -> dict:
    """What deleting this deck would remove (shown before asking to confirm)."""
    with cm.use() as col:
        deck = _get_deck(col, deck_id)
        ids = col.decks.deck_and_child_ids(DeckId(deck_id))
        return {
            "id": deck_id,
            "name": deck["name"],
            "filtered": bool(deck["dyn"]),
            "subdecks": len(ids) - 1,
            # Includes cards from these decks that are currently in a filtered deck.
            "cards": col.decks.card_count(ids, include_subdecks=False),
        }


@router.put("/{deck_id}", response_model=None)
def rename_deck(
    deck_id: int, body: DeckNameBody, cm: CollectionManager = Depends(get_cm)
) -> dict | JSONResponse:
    """Rename a deck; a "Parent::Child" name moves it (and its subdecks) under Parent."""
    name = _clean_name(body.name)
    with cm.use() as col:
        current = _get_deck(col, deck_id)["name"]
        if name == current:
            return {"id": deck_id, "name": current}
        # Anki would quietly add "+" to a name that's taken; renaming "spanish" to
        # "Spanish" is fine though.
        if (existing := col.decks.id_for_name(name)) and existing != deck_id:
            return _conflict(col, existing)
        if name.casefold().startswith(current.casefold() + "::"):
            raise HTTPException(400, "A deck can't be moved inside one of its own subdecks.")
        try:
            col.decks.rename(DeckId(deck_id), name)
        except BackendError as err:  # e.g. moving it under a filtered deck
            raise HTTPException(400, str(err) or "That deck name can't be used.") from err
        renamed = {"id": deck_id, "name": _expand_parents(col, DeckId(deck_id))}
    cm.mark_modified()
    return renamed


@router.delete("/{deck_id}")
def delete_deck(deck_id: int, cm: CollectionManager = Depends(get_cm)) -> dict:
    """Delete a deck with its subdecks and their cards. A filtered deck's cards go back
    to their original decks instead."""
    with cm.use() as col:
        name = _get_deck(col, deck_id)["name"]
        deleted = col.decks.remove([DeckId(deck_id)]).count
    cm.mark_modified()
    return {"id": deck_id, "name": name, "cards_deleted": deleted}


class CollapseBody(BaseModel):
    collapsed: bool


@router.post("/{deck_id}/collapse")
def collapse(deck_id: int, body: CollapseBody, cm: CollectionManager = Depends(get_cm)) -> dict:
    with cm.use() as col:
        _get_deck(col, deck_id)
        col.decks.set_collapsed(DeckId(deck_id), body.collapsed, DeckCollapseScope.REVIEWER)
    cm.mark_modified()
    return {"ok": True}
