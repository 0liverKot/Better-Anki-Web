"""Search notes like Anki's browser: the query uses Anki's own search syntax, so plain
words match any field, and "exact phrase", -word, front:x, tag:x, is:due etc. all work."""

from __future__ import annotations

import re
from typing import Any

from anki.cards import Card
from anki.collection import Collection, SearchNode
from anki.decks import DeckId
from anki.errors import SearchError
from anki.notes import NoteId
from anki.utils import ids2str, strip_html_media
from fastapi import APIRouter, Depends, HTTPException, Query, Request

from ..auth import require_user
from ..collection import CollectionManager
from ..deps import get_cm, media_base
from ..rendering import render_card

router = APIRouter(prefix="/api", dependencies=[Depends(require_user)])

SNIPPET_CHARS = 200
BIDI_ISOLATES = str.maketrans("", "", "⁦⁧⁨⁩")
QUEUE_STATES = {
    -3: "buried",
    -2: "buried",
    -1: "suspended",
    0: "new",
    1: "learning",
    2: "review",
    3: "learning",
    4: "preview",
}
CARD_TYPE_REVIEW = 2
CLOZE_TYPE = 1


SOUND_RE = re.compile(r"\[sound:([^\]]+)\]")
SPACE_RE = re.compile(r"\s+")


def _text(html: str, limit: int | None = SNIPPET_CHARS) -> str:
    """Field HTML as one line of plain text (media shown as filenames)."""
    text = SPACE_RE.sub(" ", SOUND_RE.sub(r"\1", strip_html_media(html))).strip()
    if limit and len(text) > limit:
        text = text[: limit - 1].rstrip() + "…"
    return text


def _build_query(col: Collection, text: str, deck_name: str | None) -> tuple[str, str | None]:
    """Returns the Anki search string, plus a note when the text wasn't valid search
    syntax and was searched for as plain text instead."""
    deck = [SearchNode(deck=deck_name)] if deck_name else []
    text = text.strip()
    if not text:
        return col.build_search_string(*(deck or [""])), None
    try:
        return col.build_search_string(text, *deck), None
    except SearchError as err:
        literal = col.build_search_string(SearchNode(literal_text=text), *deck)
        return literal, str(err).translate(BIDI_ISOLATES)


@router.get("/search")
def search(
    q: str = "",
    deck_id: int | None = None,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    cm: CollectionManager = Depends(get_cm),
) -> dict:
    with cm.use() as col:
        deck_name = None
        if deck_id:
            if not col.decks.get(DeckId(deck_id), default=False):
                raise HTTPException(404, "Deck not found.")
            deck_name = col.decks.name(DeckId(deck_id))

        query, syntax_note = _build_query(col, q, deck_name)
        # Note ids are creation timestamps, so this lists the newest notes first.
        note_ids = sorted(col.find_notes(query), reverse=True)
        page = note_ids[offset : offset + limit]

        decks_by_note: dict[int, list[str]] = {}
        cards_by_note: dict[int, int] = {}
        if page:
            rows = col.db.all(
                "select nid, case when odid != 0 then odid else did end, count() "
                f"from cards where nid in {ids2str(page)} group by 1, 2"
            )
            for nid, did, count in rows:
                decks_by_note.setdefault(nid, []).append(col.decks.name(DeckId(did)))
                cards_by_note[nid] = cards_by_note.get(nid, 0) + count

        notes = []
        for nid in page:
            note = col.get_note(NoteId(nid))
            notetype = note.note_type() or {}
            notes.append(
                {
                    "id": nid,
                    "notetype": notetype.get("name", ""),
                    "fields": [
                        {"name": field["name"], "text": _text(note.fields[i])}
                        for i, field in enumerate(notetype.get("flds", []))
                    ],
                    "tags": note.tags,
                    "decks": sorted(decks_by_note.get(nid, [])),
                    "card_count": cards_by_note.get(nid, 0),
                }
            )

        return {
            "query": query,
            "syntax_note": syntax_note,
            "total": len(note_ids),
            "offset": offset,
            "notes": notes,
        }


def _card_info(col: Collection, card: Card) -> dict[str, Any]:
    info: dict[str, Any] = {
        "state": QUEUE_STATES.get(card.queue, "unknown"),
        "due_in_days": None,
        "interval_days": None,
        "reviews": card.reps,
        "lapses": card.lapses,
    }
    if card.type == CARD_TYPE_REVIEW:
        due_day = card.odue if card.odid else card.due
        info["due_in_days"] = due_day - col.sched.today
        info["interval_days"] = card.ivl
    return info


@router.get("/notes/{note_id}")
def note_detail(note_id: int, request: Request, cm: CollectionManager = Depends(get_cm)) -> dict:
    """A note's fields and its cards rendered for preview."""
    with cm.use() as col:
        note = col.get_note(NoteId(note_id))
        notetype = note.note_type() or {}
        is_cloze = notetype.get("type") == CLOZE_TYPE
        cards = []
        for card_id in note.card_ids():
            card = col.get_card(card_id)
            rendered = render_card(col, card)
            cards.append(
                {
                    "id": card.id,
                    "ord": card.ord,
                    "name": f"Cloze {card.ord + 1}" if is_cloze else card.template()["name"],
                    "deck": col.decks.name(DeckId(card.odid or card.did)),
                    "question": rendered.question,
                    "answer": rendered.answer_for_preview(col),
                    "css": rendered.css,
                    "av": {"q": rendered.question_av, "a": rendered.answer_av},
                    "replay_question": bool(card.replay_question_audio_on_answer_side()),
                    **_card_info(col, card),
                }
            )
        return {
            "media_base": media_base(request),
            "note": {
                "id": note.id,
                "notetype": notetype.get("name", ""),
                "tags": note.tags,
                "fields": [
                    {"name": field["name"], "text": _text(note.fields[i], limit=None)}
                    for i, field in enumerate(notetype.get("flds", []))
                ],
            },
            "cards": cards,
        }
