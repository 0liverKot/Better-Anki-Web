from __future__ import annotations

from anki.decks import DeckId
from anki.models import NotetypeId
from anki.notes import NoteFieldsCheckResult
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from ..auth import require_user
from ..collection import CollectionManager
from ..deps import get_cm, media_base

router = APIRouter(prefix="/api", dependencies=[Depends(require_user)])

IMAGE_OCCLUSION_KIND = 6
CLOZE_TYPE = 1


@router.get("/notetypes")
def notetypes(cm: CollectionManager = Depends(get_cm)) -> list[dict]:
    with cm.use() as col:
        result = []
        for entry in col.models.all_names_and_ids():
            model = col.models.get(NotetypeId(entry.id))
            if not model or model.get("originalStockKind") == IMAGE_OCCLUSION_KIND:
                # Image occlusion needs its own editor; not supported yet.
                continue
            result.append(
                {
                    "id": model["id"],
                    "name": model["name"],
                    "is_cloze": model["type"] == CLOZE_TYPE,
                    "fields": [
                        {"name": f["name"], "sticky": bool(f.get("sticky"))}
                        for f in model["flds"]
                    ],
                }
            )
        return result


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


class NewNote(BaseModel):
    notetype_id: int
    deck_id: int
    fields: list[str]
    tags: str = ""
    # Add even if it is a duplicate or a cloze note without cloze deletions.
    force: bool = False


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
        "There are no cloze deletions yet, e.g. {{c1::answer}}. A card with no cloze is "
        "added as an empty card.",
    ),
}


@router.post("/notes", response_model=None)
def add_note(body: NewNote, cm: CollectionManager = Depends(get_cm)) -> dict | JSONResponse:
    with cm.use() as col:
        model = col.models.get(NotetypeId(body.notetype_id))
        if not model:
            raise HTTPException(404, "Note type not found.")
        if len(body.fields) != len(model["flds"]):
            raise HTTPException(400, "Wrong number of fields for this note type.")
        deck = col.decks.get(DeckId(body.deck_id), default=False)
        if not deck:
            raise HTTPException(404, "Deck not found.")
        if deck.get("dyn"):
            raise HTTPException(400, "Cards can't be added to a filtered deck.")

        note = col.new_note(model)
        for index, value in enumerate(body.fields):
            note.fields[index] = value
        note.tags = col.tags.split(body.tags)

        state = note.fields_check()
        if state in ERRORS:
            raise HTTPException(400, ERRORS[state])
        if state in WARNINGS and not body.force:
            code, message = WARNINGS[state]
            return JSONResponse({"detail": message, "warning": code}, status_code=409)

        changes = col.add_note(note, DeckId(body.deck_id))
    cm.mark_modified()
    return {"note_id": note.id, "card_count": changes.count}


@router.get("/tags")
def tags(cm: CollectionManager = Depends(get_cm)) -> list[str]:
    with cm.use() as col:
        return sorted(col.tags.all(), key=str.lower)
