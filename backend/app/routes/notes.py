"""Adding and editing notes. Both go through the same field/deck checks so the two stay
consistent as features are added."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from anki.collection import Collection
from anki.decks import DeckId
from anki.models import NotetypeDict, NotetypeId
from anki.notes import Note, NoteFieldsCheckResult, NoteId
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from ..auth import require_user
from ..collection import CollectionManager
from ..deps import get_cm, media_base

router = APIRouter(prefix="/api", dependencies=[Depends(require_user)])

IMAGE_OCCLUSION_KIND = 6
CLOZE_TYPE = 1


def is_editable(model: NotetypeDict | None) -> bool:
    """Image occlusion needs its own editor; not supported yet."""
    return bool(model) and model.get("originalStockKind") != IMAGE_OCCLUSION_KIND  # type: ignore[union-attr]


def notetype_info(model: NotetypeDict) -> dict[str, Any]:
    return {
        "id": model["id"],
        "name": model["name"],
        "is_cloze": model["type"] == CLOZE_TYPE,
        "fields": [{"name": f["name"], "sticky": bool(f.get("sticky"))} for f in model["flds"]],
    }


@router.get("/notetypes")
def notetypes(cm: CollectionManager = Depends(get_cm)) -> list[dict]:
    with cm.use() as col:
        models = (col.models.get(NotetypeId(e.id)) for e in col.models.all_names_and_ids())
        return [notetype_info(m) for m in models if m and is_editable(m)]


@router.get("/add/defaults")
def add_defaults(request: Request, cm: CollectionManager = Depends(get_cm)) -> dict:
    with cm.use() as col:
        defaults = col.defaults_for_adding(current_review_card=None)
        return {
            "notetype_id": defaults.notetype_id,
            "deck_id": defaults.deck_id,
            # For previewing pasted images in the editor.
            "media_base": media_base(request),
        }


@router.get("/notetypes/{notetype_id}/default-deck")
def default_deck(notetype_id: int, cm: CollectionManager = Depends(get_cm)) -> dict:
    """Deck to switch to when this note type is picked, if the user's preferences say so."""
    with cm.use() as col:
        return {"deck_id": col.default_deck_for_notetype(NotetypeId(notetype_id))}


# Shared checks
##########################################################################

ERRORS = {
    NoteFieldsCheckResult.EMPTY: "The first field is empty.",
    NoteFieldsCheckResult.NOTETYPE_NOT_CLOZE: (
        "Cloze deletions only work with a Cloze note type."
    ),
    NoteFieldsCheckResult.FIELD_NOT_CLOZE: (
        "Cloze deletions only work in the Cloze note type's cloze fields."
    ),
}
WARNINGS = {
    NoteFieldsCheckResult.DUPLICATE: ("duplicate", "A note with this first field already exists."),
    NoteFieldsCheckResult.MISSING_CLOZE: (
        "missing_cloze",
        "There are no cloze deletions, e.g. {{c1::answer}}, so the card will be empty.",
    ),
}


def _set_content(col: Collection, note: Note, fields: list[str], tags: str) -> None:
    if len(fields) != len(note.fields):
        raise HTTPException(400, "Wrong number of fields for this note type.")
    for index, value in enumerate(fields):
        note.fields[index] = value
    note.tags = col.tags.split(tags)


def _check_fields(note: Note, *, force: bool, adding: bool) -> JSONResponse | None:
    """Raises on problems that can't be saved; returns a 409 asking for confirmation on
    ones that can (resend with force=true)."""
    state = note.fields_check()
    if state in ERRORS:
        raise HTTPException(400, ERRORS[state])
    if state == NoteFieldsCheckResult.DUPLICATE and not adding:
        return None  # Editing a note never needs a duplicate warning.
    if state in WARNINGS and not force:
        code, message = WARNINGS[state]
        return JSONResponse({"detail": message, "warning": code}, status_code=409)
    return None


def _target_deck(col: Collection, deck_id: int) -> DeckId:
    deck = col.decks.get(DeckId(deck_id), default=False)
    if not deck:
        raise HTTPException(404, "Deck not found.")
    if deck.get("dyn"):
        raise HTTPException(400, "Cards can't be put in a filtered deck.")
    return DeckId(deck_id)


# Adding
##########################################################################


class NewNote(BaseModel):
    notetype_id: int
    deck_id: int
    fields: list[str]
    tags: str = ""
    # Add even if it is a duplicate or a cloze note without cloze deletions.
    force: bool = False


@router.post("/notes", response_model=None)
def add_note(body: NewNote, cm: CollectionManager = Depends(get_cm)) -> dict | JSONResponse:
    with cm.use() as col:
        model = col.models.get(NotetypeId(body.notetype_id))
        if not model:
            raise HTTPException(404, "Note type not found.")
        deck_id = _target_deck(col, body.deck_id)
        note = col.new_note(model)
        _set_content(col, note, body.fields, body.tags)
        if confirm := _check_fields(note, force=body.force, adding=True):
            return confirm
        changes = col.add_note(note, deck_id)
    cm.mark_modified()
    return {"note_id": note.id, "card_count": changes.count}


# Editing
##########################################################################


def _version(note: Note) -> str:
    """Fingerprint of the note's content, to detect edits made elsewhere meanwhile.
    (note.mod only has one-second resolution.)"""
    data = json.dumps([list(note.fields), sorted(note.tags), note.mod], ensure_ascii=False)
    return hashlib.sha256(data.encode()).hexdigest()[:20]


def _card_decks(col: Collection, note: Note) -> set[int]:
    """Home decks of the note's cards (the original deck for cards in a filtered deck)."""
    return {int(card.odid or card.did) for card in note.cards()}


@router.get("/notes/{note_id}/edit")
def edit_note_data(note_id: int, request: Request, cm: CollectionManager = Depends(get_cm)) -> dict:
    """Everything the editor needs to edit an existing note, with raw field HTML."""
    with cm.use() as col:
        note = col.get_note(NoteId(note_id))
        model = note.note_type()
        if not model or not is_editable(model):
            raise HTTPException(400, "Image occlusion notes can't be edited here yet.")
        decks = _card_decks(col, note)
        return {
            "id": note.id,
            "version": _version(note),
            "notetype": notetype_info(model),
            # None when the cards are spread over several decks.
            "deck_id": next(iter(decks)) if len(decks) == 1 else None,
            "deck_names": sorted(col.decks.name(DeckId(d)) for d in decks),
            "fields": list(note.fields),
            "tags": " ".join(note.tags),
            "media_base": media_base(request),
        }


class NoteUpdate(BaseModel):
    fields: list[str]
    tags: str = ""
    # Move all of the note's cards to this deck; None leaves them where they are.
    deck_id: int | None = None
    # The "version" from the edit data, to catch changes synced in meanwhile.
    version: str | None = None
    force: bool = False


@router.put("/notes/{note_id}", response_model=None)
def update_note(
    note_id: int, body: NoteUpdate, cm: CollectionManager = Depends(get_cm)
) -> dict | JSONResponse:
    with cm.use() as col:
        note = col.get_note(NoteId(note_id))
        if not is_editable(note.note_type()):
            raise HTTPException(400, "Image occlusion notes can't be edited here yet.")
        if body.version is not None and _version(note) != body.version:
            raise HTTPException(
                409,
                "This note was changed somewhere else (probably synced from another "
                "device). Close the editor and open it again to get the latest version.",
            )
        deck_id = _target_deck(col, body.deck_id) if body.deck_id is not None else None
        _set_content(col, note, body.fields, body.tags)
        if confirm := _check_fields(note, force=body.force, adding=False):
            return confirm

        col.update_note(note)
        moved = 0
        if deck_id is not None:
            to_move = [c.id for c in note.cards() if (c.odid or c.did) != deck_id]
            if to_move:
                moved = col.set_deck(to_move, deck_id).count
        note.load()
    cm.mark_modified()
    return {"note_id": note.id, "version": _version(note), "cards_moved": moved}


@router.get("/tags")
def tags(cm: CollectionManager = Depends(get_cm)) -> list[str]:
    with cm.use() as col:
        return sorted(col.tags.all(), key=str.lower)
