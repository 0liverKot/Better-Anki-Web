"""Turns Anki's rendered card text into HTML a browser can display.

Mirrors what desktop's reviewer does to the template output: media filenames are
URL-escaped, [anki:play:..] references become play buttons, and [[type:Field]] becomes
a text box (question) or a comparison against the expected answer (answer).
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

from anki.cards import Card
from anki.collection import Collection
from anki.sound import AVTag, SoundOrVideoTag, TTSTag

AV_REF_RE = re.compile(r"\[anki:play:(q|a):(\d+)\]")
TYPE_RE = re.compile(r"\[\[type:(.+?)\]\]")
VIDEO_EXTS = {"mp4", "webm", "mov", "mkv", "ogv", "avi", "m4v", "mpg", "mpeg", "3gp"}

PLAY_ICON = (
    '<svg class="playImage" viewBox="0 0 64 64" version="1.1">'
    '<circle cx="32" cy="32" r="29"/>'
    '<path d="M56.502,32.301l-37.502,20.101l0.329,-40.804l37.173,20.703Z"/></svg>'
)


@dataclass
class TypeAnswer:
    expected: str
    combining: bool
    font: str
    size: int


@dataclass
class RenderedCard:
    question: str
    css: str
    question_av: list[dict[str, Any]]
    answer_av: list[dict[str, Any]]
    type_answer: TypeAnswer | None
    raw_answer: str
    q_tags: list[AVTag]
    a_tags: list[AVTag]

    def answer(self, col: Collection, typed: str = "") -> str:
        text = _answer_type_filter(col, self.raw_answer, self.type_answer, typed)
        return _for_display(col, text, self.q_tags, self.a_tags)


def render_card(col: Collection, card: Card) -> RenderedCard:
    out = card.render_output(reload=True)
    type_answer, question = _question_type_filter(col, card, out.question_text)
    return RenderedCard(
        question=_for_display(col, question, out.question_av_tags, out.answer_av_tags),
        css=out.css,
        question_av=[_av_to_dict(t) for t in out.question_av_tags],
        answer_av=[_av_to_dict(t) for t in out.answer_av_tags],
        type_answer=type_answer,
        raw_answer=out.answer_text,
        q_tags=out.question_av_tags,
        a_tags=out.answer_av_tags,
    )


# Audio / video
##########################################################################


def _av_to_dict(tag: AVTag) -> dict[str, Any]:
    if isinstance(tag, SoundOrVideoTag):
        return {"kind": "video" if _is_video(tag.filename) else "audio", "file": tag.filename}
    if isinstance(tag, TTSTag):
        return {"kind": "tts", "text": tag.field_text, "lang": tag.lang, "speed": tag.speed}
    return {"kind": "unknown"}


def _is_video(filename: str) -> bool:
    return filename.rsplit(".", 1)[-1].lower() in VIDEO_EXTS if "." in filename else False


def _for_display(col: Collection, text: str, q_tags: list[AVTag], a_tags: list[AVTag]) -> str:
    text = col.media.escape_media_filenames(text)

    def replace(match: re.Match[str]) -> str:
        side, index = match.group(1), int(match.group(2))
        tags = q_tags if side == "q" else a_tags
        if index >= len(tags):
            return ""
        tag = tags[index]
        ref = f"{side}:{index}"
        if isinstance(tag, SoundOrVideoTag) and _is_video(tag.filename):
            src = html.escape(quote(tag.filename))
            return (
                f'<video class="baw-video" data-av="{ref}" src="{src}" controls playsinline '
                'preload="metadata"></video>'
            )
        return (
            f'<a class="replay-button soundLink" href="#" data-av="{ref}" draggable="false">'
            f"{PLAY_ICON}</a>"
        )

    return AV_REF_RE.sub(replace, text)


# Type in the answer
##########################################################################


def _question_type_filter(
    col: Collection, card: Card, text: str
) -> tuple[TypeAnswer | None, str]:
    match = TYPE_RE.search(text)
    if not match:
        return None, text

    field_name = match.group(1)
    cloze_index = None
    combining = True
    if field_name.startswith("cloze:"):
        cloze_index = card.ord + 1
        field_name = field_name.split(":", 1)[1]
    if field_name.startswith("nc:"):
        combining = False
        field_name = field_name.split(":", 1)[1]

    note = card.note()
    for field in card.note_type()["flds"]:
        if field["name"] != field_name:
            continue
        expected = note[field_name]
        if cloze_index:
            expected = col.extract_cloze_for_typing(expected, cloze_index)
        if not expected:
            # Empty field: nothing to type.
            return None, TYPE_RE.sub("", text)
        info = TypeAnswer(
            expected=expected,
            combining=combining,
            font=str(field.get("font") or "Arial"),
            size=int(field.get("size") or 20),
        )
        box = (
            '<center><input type="text" id="typeans" autocomplete="off" autocorrect="off" '
            'autocapitalize="off" spellcheck="false" '
            f'style="font-family: \'{html.escape(info.font)}\'; font-size: {info.size}px;">'
            "</center>"
        )
        return info, TYPE_RE.sub(lambda _m: box, text)

    warning = html.escape(f"(Type answer: unknown field {field_name})")
    return None, TYPE_RE.sub(lambda _m: warning, text)


def _answer_type_filter(
    col: Collection, text: str, info: TypeAnswer | None, typed: str
) -> str:
    if info is None:
        return TYPE_RE.sub("", text)
    without_hr = text.replace("<hr id=answer>", "")
    had_hr = len(without_hr) != len(text)
    comparison = col.compare_answer(info.expected, typed, info.combining)
    block = (
        f'<div style="font-family: \'{html.escape(info.font)}\'; font-size: {info.size}px">'
        f"{comparison}</div>"
    )
    if had_hr:
        block = "<hr id=answer>" + block
    return TYPE_RE.sub(lambda _m: block, without_hr)
