"""Questions straight from the student's own notes, with no AI needed.

Every question is built from one sentence in the material and keeps that sentence
as its source, so it is grounded by construction. Three forms:

* definition ("Which term is being described?") from sentences like "X is ...",
* fill-in-the-blank, multiple choice (distractors are other key terms from the notes),
* fill-in-the-blank, typed answer (harder: no choices).

Topics are sections of the material, each named after its most distinctive term,
so readiness by topic still means something. Answers are graded by normalized
string match with a small typo allowance, and the grading method says so.
"""

from __future__ import annotations

import hashlib
import math
import random
import re
from collections import Counter
from difflib import SequenceMatcher
from typing import Any, Literal

from pydantic import BaseModel, Field

from .ingest.pdf import Extraction

STOP = set(
    """a about above after again against all also am an and any are as at be because been before being below between both but by can
could did do does doing down during each either else even every few for from further had has have having he her here hers him his
how however i if in into is it its itself just less like made make many may me might more most much must my no nor not now of off
often on once one only or other our out over own per rather same she should since so some such than that the their them then there
these they this those through thus to too under until up upon us use used uses using very via was we were what when where whether
which while who whom whose why will with within without would yet you your example examples called called also first second third
following figure table page chapter section note notes slide lecture week unit part shown given another each new way ways thing things
different important several various certain number numbers based case cases form forms type types kind kinds result results value values
time times state states set sets point points term terms define defined definition means refers refer known""".split()
)
DEF_RE = re.compile(
    r"^(?:the |an? )?([A-Za-z][A-Za-z0-9\-' ]{2,48}?)\s+(?:is|are|was|were|refers to|is called|is defined as|means|describes)\s+(.{12,})$",
    re.I,
)
WORD_RE = re.compile(r"[A-Za-z][A-Za-z\-']{3,}")

MIN_QUESTIONS = 3
MAX_PER_TOPIC = 8
MAX_TOPICS = 5


class RecallTemplate(BaseModel):
    kind: Literal["recall"] = "recall"
    id: str
    topic: str
    difficulty: int = Field(ge=1, le=3)
    form: Literal["mcq", "short"]
    prompt: str
    answer: str
    accept: list[str] = Field(default_factory=list)
    choices: list[str] = Field(default_factory=list)  # mcq only; includes the answer
    quote: str
    pages: list[int]


def is_recall(body: str) -> bool:
    return '"kind":"recall"' in body.replace(" ", "")[:40]


# ------------------------------------------------------------------ text


HEADING_RE = re.compile(r"^[A-Z0-9][^.!?]{2,60}$")


MARKUP_RE = re.compile(r"^(?:#{1,6}\s+|>\s*|(?:[-*+•▪●◦]|\d{1,2}[.)])\s+)")
BULLET_RE = re.compile(r"^(?:[-*+•▪●◦]|\d{1,2}[.)])\s+")


def _clean_line(line: str) -> tuple[str, bool, bool]:
    """(text, was a markdown heading, was a list item) with markdown stripped."""
    raw = line.strip().replace("\u00ad", "")
    md_heading = bool(re.match(r"^#{1,6}\s+", raw))
    bullet = bool(BULLET_RE.match(raw))
    text = MARKUP_RE.sub("", raw)
    text = re.sub(r"(\*\*|__|`)", "", text).strip()
    return text, md_heading, bullet


def _sentences(extraction: Extraction) -> list[tuple[str, int, str | None]]:
    """(sentence, page, heading it sits under). Short lines with no full stop are headings,
    and so is any markdown "# Heading" line. List items count as their own paragraphs."""
    out: list[tuple[str, int, str | None]] = []
    heading: str | None = None

    def flush(para: list[str], page_no: int) -> None:
        text = re.sub(r"\s+", " ", " ".join(para)).strip()
        for sent in re.split(r"(?<=[.!?])\s+(?=[A-Z0-9\"(])|\s*[•▪●◦]\s*", text):
            sent = sent.strip(" -–•\"'")
            words = sent.split()
            numbers = len(re.findall(r"\d+(?:[.,]\d+)?", sent))
            if 7 <= len(words) <= 45 and numbers <= 1 and not re.match(r"^\d+[.)]\s", sent) and sum(c.isalpha() for c in sent) / max(1, len(sent)) > 0.6:
                out.append((sent, page_no, heading))

    for page in extraction.pages:
        para: list[str] = []
        for raw in [*page.text.splitlines(), ""]:
            line, md_heading, bullet = _clean_line(raw)
            ends_sentence = not para or re.search(r"[.!?:;]$", para[-1]) is not None
            is_heading = bool(line) and len(line.split()) <= 8 and (
                md_heading or (HEADING_RE.match(line) is not None and ends_sentence and not bullet)
            )
            if is_heading:
                flush(para, page.number)
                para = []
                heading = line.rstrip(":").strip()
                continue
            if line and bullet and para:
                flush(para, page.number)
                para = []
            if line:
                para.append(line)
                continue
            flush(para, page.number)
            para = []
    seen: set[str] = set()
    return [x for x in out if not (x[0].lower() in seen or seen.add(x[0].lower()))]


NUMBER_WORDS = {"three", "four", "five", "seven", "eight", "nine", "hundred", "thousand", "million", "several", "across", "active", "positive", "negative"}
NOUN_SUFFIX = re.compile(r"(tion|sion|sis|ment|ism|ity|ance|ence|ase|ogy|ness|ship|ium|ology|ysis)$")
DETERMINER_RE = re.compile(r"\b(?:the|a|an|its|their|of|each|this|these|those|his|her|our|your)\s+([a-z][a-z\-']{3,})(?:\s+([a-z][a-z\-']{3,}))?", re.I)


def _nouns(sentences: list[tuple[str, int, str | None]]) -> set[str]:
    """Words that act as nouns somewhere in the notes: after a determiner, as a defined term, or by suffix."""
    nouns: set[str] = set()
    for s, _, _ in sentences:
        for m in DETERMINER_RE.finditer(s):
            first = m.group(1).lower()
            if first not in STOP and first not in NUMBER_WORDS:
                nouns.add(first)
        d = DEF_RE.match(s)
        if d:
            nouns.update(w for w in _content_words(d.group(1)))
        nouns.update(w for w in _content_words(s) if NOUN_SUFFIX.search(w))
    return nouns


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def _content_words(text: str) -> list[str]:
    return [w.lower() for w in WORD_RE.findall(text) if w.lower() not in STOP]


def _terms(sentences: list[tuple[str, int, str | None]], nouns: set[str]) -> Counter[str]:
    """Candidate answers: nouns, and two-word noun phrases ("active site") that repeat."""
    counts: Counter[str] = Counter()
    bigrams: Counter[str] = Counter()
    for s, _, _ in sentences:
        words = _content_words(s)
        counts.update({w for w in words if w in nouns})
        bigrams.update({f"{a} {b}" for a, b in zip(words, words[1:], strict=False) if b in nouns and f"{a} {b}" in s.lower()})
    for d in (DEF_RE.match(s) for s, _, _ in sentences):
        if d and len(d.group(1).split()) <= 4:
            bigrams[d.group(1).strip().lower()] += 2
    counts.update({b: c for b, c in bigrams.items() if c >= 2})
    return counts


# ------------------------------------------------------------------ building


def _choices(answer: str, pool: list[str], rng: random.Random) -> list[str]:
    a = _norm(answer)
    same_shape = [t for t in pool if _norm(t) != a and a not in _norm(t) and _norm(t) not in a and (" " in t) == (" " in answer)]
    others = [t for t in pool if _norm(t) != a and a not in _norm(t) and _norm(t) not in a and t not in same_shape]

    def unique(items: list[str]) -> list[str]:
        seen = {_stem(a)}
        return [t for t in items if not (_stem(_norm(t)) in seen or seen.add(_stem(_norm(t))))]

    same_shape, others = unique(same_shape), unique(others)
    picks = rng.sample(same_shape, min(3, len(same_shape)))
    picks = unique(picks)
    if len(picks) < 3:
        picks += rng.sample(others, min(3 - len(picks), len(others)))
    if len(picks) < 3:
        return []
    options = [*picks, answer]
    rng.shuffle(options)
    return options


def _blank(sentence: str, term: str) -> str | None:
    m = re.search(rf"(?<![A-Za-z]){re.escape(term)}(?![A-Za-z])", sentence, re.I)
    if not m:
        return None
    return sentence[: m.start()] + "_____" + sentence[m.end() :]


def _sections(sentences: list[tuple[str, int, str | None]]) -> list[list[tuple[str, int, str | None]]]:
    headings = list(dict.fromkeys(h for _, _, h in sentences if h))
    if 2 <= len(headings) <= 12:
        groups = [[x for x in sentences if x[2] == h] for h in headings]
        groups = [g for g in groups if len(g) >= 2]
        if len(groups) >= 2:
            return groups[:8]
    n = max(1, min(MAX_TOPICS, len(sentences) // 6))
    size = math.ceil(len(sentences) / n)
    return [sentences[i : i + size] for i in range(0, len(sentences), size)]


def _section_name(section: list[tuple[str, int, str | None]], doc_counts: Counter[str], used: set[str], use_headings: bool) -> str:
    heads = {h for _, _, h in section if h}
    if len(heads) == 1 and use_headings:
        head = heads.pop()
        if head not in used:
            used.add(head)
            return head[:48]
    local: Counter[str] = Counter()
    for s, _, _ in section:
        low = s.lower()
        local.update({t for t in doc_counts if t in low and len(t) >= 4})
    total = sum(doc_counts.values())

    def score(t: str) -> float:
        return local[t] * math.log(1 + total / (1 + doc_counts[t])) * (2.2 if " " in t else 1)

    for t in sorted(local, key=lambda t: (-score(t), t)):
        if t not in used and not any(t in u or u in t for u in used):
            used.add(t)
            return t.replace("-", " ").title()
    pages = sorted({p for _, p, _ in section})
    return f"Pages {pages[0]}–{pages[-1]}" if len(pages) > 1 else f"Page {pages[0]}"


def build(course_id: str, extraction: Extraction, seed_text: str = "") -> tuple[list[dict[str, Any]], list[str]]:
    """Returns ([{key, name, description, templates: [RecallTemplate]}], rejection reasons)."""
    rng = random.Random(int(hashlib.sha1((seed_text or course_id).encode()).hexdigest()[:8], 16))
    sentences = _sentences(extraction)
    if not sentences:
        return [], ["no readable sentences in the material"]
    nouns = _nouns(sentences)
    counts = _terms(sentences, nouns)
    pool = [t for t, c in counts.most_common(400) if len(t) >= 4 and (" " in t or (t in nouns and (c >= 2 or NOUN_SUFFIX.search(t))))]
    distinctive = [t for t, c in counts.most_common(400) if c >= 2 or " " in t]
    topics: list[dict[str, Any]] = []
    rejected: list[str] = []
    used_names: set[str] = set()
    use_headings = len({h for _, _, h in sentences if h}) >= 2
    for si, section in enumerate(_sections(sentences)):
        key = f"r{si}"
        templates: list[RecallTemplate] = []
        for s, page, _ in section:
            if len(templates) >= MAX_PER_TOPIC:
                break
            tid = f"{course_id}:{key}:{len(templates)}"
            d = DEF_RE.match(s)
            if d and _content_words(d.group(1)) and len(d.group(1).split()) <= 5:
                term = d.group(1).strip()
                desc = d.group(2).rstrip(".")
                if _norm(term) in _norm(desc):
                    rejected.append("definition repeats its own term")
                    continue
                choices = _choices(term, pool, rng)
                if choices:
                    templates.append(
                        RecallTemplate(
                            id=tid,
                            topic=key,
                            difficulty=2,
                            form="mcq",
                            prompt=f"Which term is being described? “{desc}.”",
                            answer=term,
                            choices=choices,
                            quote=s,
                            pages=[page],
                        )
                    )
                    continue
            # Fill in the blank: the most distinctive term in the sentence that repeats elsewhere in the notes.
            lowered = s.lower()
            candidates = [t for t in distinctive if t in lowered and len(t) >= 5]
            candidates.sort(key=lambda t: (counts[t] > 12, -len(t.split()), counts[t]))
            term = next((t for t in candidates if _blank(s, t)), None)
            if not term:
                rejected.append("no key term to ask about")
                continue
            prompt = _blank(s, term)
            if prompt is None or _norm(term) in _norm(prompt):
                rejected.append("answer still visible in the question")
                continue
            exact = re.search(rf"(?<![A-Za-z]){re.escape(term)}(?![A-Za-z])", s, re.I)
            answer = exact.group(0) if exact else term
            hard = len(templates) % 3 == 2
            choices = [] if hard else _choices(answer, pool, rng)
            if choices:
                templates.append(
                    RecallTemplate(
                        id=tid, topic=key, difficulty=1, form="mcq", prompt=f"Fill in the blank: {prompt}", answer=answer, choices=choices, quote=s, pages=[page]
                    )
                )
            else:
                templates.append(
                    RecallTemplate(id=tid, topic=key, difficulty=3, form="short", prompt=f"Fill in the blank: {prompt}", answer=answer, quote=s, pages=[page])
                )
        if templates:
            name = _section_name(section, counts, used_names, use_headings)
            pages = sorted({p for _, p, _ in section})
            topics.append(
                {
                    "key": key,
                    "name": name,
                    "description": f"From pages {pages[0]}–{pages[-1]} of your notes" if len(pages) > 1 else f"From page {pages[0]}",
                    "templates": templates,
                }
            )
    if sum(len(t["templates"]) for t in topics) < MIN_QUESTIONS:
        return [], [*rejected, "too little text to build questions from"]
    return topics, rejected


def boss_name(course_name: str, topics: list[dict[str, Any]]) -> str:
    core = topics[0]["name"] if topics and not topics[0]["name"].startswith("Page") else course_name.split(",")[0].strip()
    titles = ["The {} Warden", "{} Golem", "The {} Hydra", "Keeper of {}", "The {} Sentinel"]
    pick = int(hashlib.sha1(course_name.encode()).hexdigest()[:4], 16) % len(titles)
    return titles[pick].format(core)[:60]


# ------------------------------------------------------------------ grading


class RecallGrade(BaseModel):
    correct: bool
    method: str
    detail: str = ""


def _stem(text: str) -> str:
    """Rough singular form, enough to treat "enzymes"/"enzyme" and "leaves"/"leave" as the same word."""

    def one(w: str) -> str:
        if len(w) <= 3 or w.endswith("ss"):
            return w
        if w.endswith("ies"):
            return w[:-3] + "y"
        if re.search(r"(s|x|z|ch|sh)es$", w):
            return w[:-2]
        return w[:-1] if w.endswith("s") else w

    return " ".join(one(w) for w in text.split())


def grade(task: dict[str, Any], answer: str, given: str) -> RecallGrade:
    a, g = _norm(answer), _norm(given)
    if task.get("form") == "mcq":
        return RecallGrade(correct=g == a, method="matching the sentence in your notes")
    accept = [a, *[_norm(x) for x in task.get("accept", [])]]
    if g in accept:
        return RecallGrade(correct=True, method="an exact match with your notes")
    if any(_stem(g) == _stem(x) for x in accept):
        return RecallGrade(correct=True, method="a match with your notes (singular or plural)")
    close = max(SequenceMatcher(None, g, x).ratio() for x in accept)
    if (len(a) >= 5 and close >= 0.85) or (len(a) >= 4 and close >= 0.75 and abs(len(a) - len(g)) <= 1):
        return RecallGrade(correct=True, method="a near-match with your notes (small typo allowed)")
    return RecallGrade(correct=False, method="comparing with the sentence in your notes")
