from __future__ import annotations

from typing import Any

from anki.decks import DeckCollapseScope, DeckId
from fastapi import APIRouter, Depends, HTTPException
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
