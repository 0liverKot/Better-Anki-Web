from __future__ import annotations

from typing import Any

from anki.decks import DeckCollapseScope, DeckId
from anki.errors import BackendError
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from ..auth import require_user
from ..collection import CollectionManager
from ..deps import get_cm

router = APIRouter(prefix="/api/decks", dependencies=[Depends(require_user)])


def _node(node: Any) -> dict[str, Any]:
    return {
        "id": node.deck_id,
        "name": node.name,
        "new": node.new_count,
        "learn": node.learn_count,
        "review": node.review_count,
        "collapsed": node.collapsed,
        "filtered": node.filtered,
        "children": [_node(child) for child in node.children],
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


class NewDeck(BaseModel):
    # "Parent::Child" creates a subdeck (and the parent, if it doesn't exist yet).
    name: str


@router.post("", response_model=None)
def create_deck(body: NewDeck, cm: CollectionManager = Depends(get_cm)) -> dict | JSONResponse:
    name = body.name.strip()
    # Anki would quietly turn empty parts ("A::::B", "Spanish::") into decks named "blank".
    if not name or any(not part.strip() for part in name.split("::")):
        raise HTTPException(400, "Enter a deck name. For a subdeck use Parent::Child.")
    with cm.use() as col:
        # Deck names are case-insensitive in Anki.
        if existing := col.decks.id_for_name(name):
            return JSONResponse(
                {
                    "detail": f'A deck called "{col.decks.name(existing)}" already exists.',
                    "id": existing,
                    "name": col.decks.name(existing),
                },
                status_code=409,
            )
        try:
            deck_id = col.decks.add_normal_deck_with_name(name).id
        except BackendError as err:  # e.g. a filtered deck can't have subdecks
            raise HTTPException(400, str(err) or "That deck name can't be used.") from err
        full_name = col.decks.name(DeckId(deck_id))
        # Anki creates decks collapsed; expand the parents so the new subdeck shows up.
        parts = full_name.split("::")
        for depth in range(1, len(parts)):
            if parent_id := col.decks.id_for_name("::".join(parts[:depth])):
                col.decks.set_collapsed(parent_id, False, DeckCollapseScope.REVIEWER)
        created = {"id": deck_id, "name": full_name}
    cm.mark_modified()
    return created


class CollapseBody(BaseModel):
    collapsed: bool


@router.post("/{deck_id}/collapse")
def collapse(deck_id: int, body: CollapseBody, cm: CollectionManager = Depends(get_cm)) -> dict:
    with cm.use() as col:
        if not col.decks.get(DeckId(deck_id), default=False):
            raise HTTPException(404, "Deck not found.")
        col.decks.set_collapsed(DeckId(deck_id), body.collapsed, DeckCollapseScope.REVIEWER)
    cm.mark_modified()
    return {"ok": True}
