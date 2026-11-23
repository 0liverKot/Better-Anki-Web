from __future__ import annotations

import time
from typing import Any

from anki.cards import Card, CardId
from anki.collection import Collection
from anki.decks import DeckId
from anki.scheduler.v3 import CardAnswer
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from ..auth import require_user
from ..collection import CollectionManager
from ..deps import get_cm, media_base
from ..rendering import render_card

router = APIRouter(prefix="/api/review", dependencies=[Depends(require_user)])

QUEUE_NAMES = {0: "new", 1: "learning", 2: "review"}
RATINGS = {1: CardAnswer.AGAIN, 2: CardAnswer.HARD, 3: CardAnswer.GOOD, 4: CardAnswer.EASY}
# describe_next_states wraps numbers in Unicode bidi isolates; browsers show them as boxes.
BIDI_ISOLATES = str.maketrans("", "", "⁦⁧⁨⁩")


def _select_deck(col: Collection, deck_id: int) -> None:
    if not col.decks.get(DeckId(deck_id), default=False):
        raise HTTPException(404, "Deck not found.")
    if col.decks.get_current_id() != deck_id:
        col.decks.select(DeckId(deck_id))


def _next_payload(col: Collection, request: Request) -> dict[str, Any]:
    queued = col.sched.get_queued_cards()
    deck_id = col.decks.get_current_id()
    payload: dict[str, Any] = {
        "deck": {"id": deck_id, "name": col.decks.name(deck_id)},
        "counts": {
            "new": queued.new_count,
            "learning": queued.learning_count,
            "review": queued.review_count,
        },
        "media_base": media_base(request),
        "undo": col.undo_status().undo or None,
        "card": None,
    }
    if not queued.cards:
        return payload

    top = queued.cards[0]
    card = Card(col, backend_card=top.card)
    rendered = render_card(col, card)
    payload["card"] = {
        "id": card.id,
        "note_id": card.nid,
        "ord": card.ord,
        "queue": QUEUE_NAMES.get(top.queue, "review"),
        "deck_name": col.decks.name(card.current_deck_id()),
        "question": rendered.question,
        # With type-in-the-answer, fetch the answer via /type-answer once typed.
        "answer": None if rendered.type_answer else rendered.answer(col),
        "type_answer": rendered.type_answer is not None,
        "css": rendered.css,
        "av": {"q": rendered.question_av, "a": rendered.answer_av},
        "autoplay": bool(card.autoplay()),
        "replay_question": bool(card.replay_question_audio_on_answer_side()),
        "buttons": [
            label.translate(BIDI_ISOLATES)
            for label in col.sched.describe_next_states(top.states)
        ],
        "flag": card.user_flag(),
    }
    return payload


def _top_card(col: Collection, card_id: int) -> Any:
    queued = col.sched.get_queued_cards()
    if not queued.cards or queued.cards[0].card.id != card_id:
        # The queue changed underneath us (e.g. a sync pulled in reviews from another
        # device). The client should fetch the next card again.
        raise HTTPException(409, "This card is no longer next in the queue.")
    return queued.cards[0]


@router.get("/{deck_id}/next")
def next_card(deck_id: int, request: Request, cm: CollectionManager = Depends(get_cm)) -> dict:
    with cm.use() as col:
        _select_deck(col, deck_id)
        return _next_payload(col, request)


class AnswerBody(BaseModel):
    deck_id: int
    card_id: int
    rating: int = Field(ge=1, le=4)
    time_taken_ms: int = Field(ge=0)


@router.post("/answer")
def answer(body: AnswerBody, request: Request, cm: CollectionManager = Depends(get_cm)) -> dict:
    with cm.use() as col:
        _select_deck(col, body.deck_id)
        top = _top_card(col, body.card_id)
        card = Card(col, backend_card=top.card)
        # The backend caps the time using the deck's "maximum answer seconds" option.
        card.timer_started = time.time() - body.time_taken_ms / 1000
        col.sched.answer_card(
            col.sched.build_answer(card=card, states=top.states, rating=RATINGS[body.rating])
        )
        cm.mark_modified()
        return _next_payload(col, request)


class DeckBody(BaseModel):
    deck_id: int


@router.post("/undo")
def undo(body: DeckBody, request: Request, cm: CollectionManager = Depends(get_cm)) -> dict:
    with cm.use() as col:
        name = col.undo_status().undo
        if not name:
            raise HTTPException(400, "Nothing to undo.")
        col.undo()
        cm.mark_modified()
        _select_deck(col, body.deck_id)
        payload = _next_payload(col, request)
        payload["undone"] = name
        return payload


class TypedBody(BaseModel):
    card_id: int
    typed: str = ""


@router.post("/type-answer")
def type_answer(body: TypedBody, cm: CollectionManager = Depends(get_cm)) -> dict:
    with cm.use() as col:
        try:
            card = col.get_card(CardId(body.card_id))
        except Exception as err:
            raise HTTPException(404, "Card not found.") from err
        rendered = render_card(col, card)
        return {"answer": rendered.answer(col, body.typed)}
