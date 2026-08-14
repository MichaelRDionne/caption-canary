"""Harvest candidate substitutions from paired raw / corrected transcripts.

Input is pairs of text — whatever wrote the raw side, whatever cleaned it.
Output is short (raw_span, corrected_term) candidates the matcher can
defend, with polish, PII, and already-known pairs screened out.

This module never keeps the surrounding utterance. Review the candidates
before they become fixtures.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path

from .core import _squash, find_near_misses

EMAIL = re.compile(r"[a-z0-9._%+\-]+@[a-z0-9.\-]+\.[a-z]{2,}", re.I)
PHONE = re.compile(r"\b\d{3}[-.\s]?\d{3}[-.\s]?\d{4}\b")
DATE = re.compile(r"\b\d{1,2}/\d{1,2}/\d{2,4}\b")
NAMEY = re.compile(r"\b[A-Z][a-z]{2,} [A-Z][a-z]{2,}\b")
UNIT = {
    "mg",
    "mcg",
    "ml",
    "l",
    "milligram",
    "milligrams",
    "microgram",
    "micrograms",
}

TOKEN = re.compile(r"[A-Za-z][A-Za-z0-9''\-]*")


@dataclass(frozen=True)
class Candidate:
    raw: str
    fixed: str
    count: int
    ratio: float


def tokens(text: str) -> list[str]:
    return TOKEN.findall(text or "")


def load_patterns(path: Path | None) -> list[re.Pattern[str]]:
    if path is None:
        return []
    out: list[re.Pattern[str]] = []
    for line in path.read_text().splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        out.append(re.compile(s, re.I))
    return out


def load_known(paths: list[Path]) -> set[tuple[str, str]]:
    """Exact (raw, fixed) pairs already locked in tests or a previous harvest."""
    known: set[tuple[str, str]] = set()
    for path in paths:
        text = path.read_text()
        for m in re.finditer(
            r"find_near_misses\(\s*\"([^\"]+)\"\s*,\s*\"([^\"]+)\"\s*\)",
            text,
        ):
            known.add((m.group(1).lower(), m.group(2).lower()))
        for m in re.finditer(
            r"near_misses\[\"([^\"]+)\"\]\s*==\s*\"([^\"]+)\"",
            text,
        ):
            known.add((m.group(2).lower(), m.group(1).lower()))
        # harvest review lines:  3  r=0.88  'seroquil' -> seroquel
        for m in re.finditer(
            r"""\d+\s+r=0\.\d+\s+'([^']+)'\s+->\s+(\S+)""",
            text,
        ):
            known.add((m.group(1).lower(), m.group(2).lower()))
    return known


def _is_polish(raw: str, fixed: str) -> bool:
    a, b = raw.lower().replace("-", " "), fixed.lower().replace("-", " ")
    if a == b:
        return True
    if a.replace(" ", "") == b.replace(" ", ""):
        return True
    ra, rb = set(a.split()), set(b.split())
    if ra <= UNIT or rb <= UNIT:
        return True
    return False


def _blocked(text: str, extra: list[re.Pattern[str]]) -> bool:
    if EMAIL.search(text) or PHONE.search(text) or DATE.search(text):
        return True
    if NAMEY.search(text):
        return True
    return any(p.search(text) for p in extra)


SPECIAL = re.compile(
    r"(ine|pram|pine|done|zine|ate|ide|ium|osis|ism|olol|apine)$",
    re.I,
)


def pair_from_texts(raw: str, fixed: str) -> list[tuple[str, str]]:
    """Token-diff one utterance. Return (raw_span, fixed_span) hunks."""
    ta, tb = tokens(raw), tokens(fixed)
    if not ta or not tb:
        return []
    sm = SequenceMatcher(None, [t.lower() for t in ta], [t.lower() for t in tb])
    out: list[tuple[str, str]] = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            continue
        a = " ".join(ta[i1:i2]).strip()
        b = " ".join(tb[j1:j2]).strip()
        if a and b:
            out.append((a.lower(), b.lower()))
    return out


def _term(fixed: str) -> str | None:
    words = [w for w in fixed.split() if len(_squash(w)) >= 6]
    if not words:
        return None
    return max(words, key=lambda w: len(_squash(w)))


def _trivial_morph(raw: str, term: str) -> bool:
    sa, sb = _squash(raw), _squash(term)
    if sa.rstrip("s") == sb.rstrip("s"):
        return True
    if sa + "ly" == sb or sb + "ly" == sa:
        return True
    if sa + "ed" == sb or sa + "d" == sb:
        return True
    return False


def _specialist(term: str, raw: str) -> bool:
    if len(raw.split()) >= 2:
        return True
    if len(_squash(term)) >= 10:
        return True
    return bool(SPECIAL.search(term))


def accept(
    raw: str,
    fixed: str,
    extra: list[re.Pattern[str]],
) -> tuple[str, str, float] | None:
    if _blocked(raw, extra) or _blocked(fixed, extra):
        return None
    if _is_polish(raw, fixed):
        return None
    term = _term(fixed)
    if term is None or _trivial_morph(raw, term) or not _specialist(term, raw):
        return None
    if len(raw.split()) > 5:
        return None
    probe = find_near_misses(raw, term)
    if probe is None:
        return None
    if _is_polish(probe, term) or _trivial_morph(probe, term):
        return None
    ratio = SequenceMatcher(None, _squash(probe), _squash(term)).ratio()
    if ratio < 0.75:
        return None
    return probe.lower(), term.lower(), ratio


def harvest(
    pairs: list[tuple[str, str]],
    blocklist: Path | None = None,
    known: set[tuple[str, str]] | None = None,
    min_count: int = 1,
) -> list[Candidate]:
    extra = load_patterns(blocklist)
    known = known or set()
    counts: Counter[tuple[str, str]] = Counter()
    ratios: dict[tuple[str, str], float] = {}
    for raw, fixed in pairs:
        if _blocked(raw, extra) or _blocked(fixed, extra):
            continue
        for a, b in pair_from_texts(raw, fixed):
            hit = accept(a, b, extra)
            if hit is None:
                continue
            raw_span, term, ratio = hit
            key = (raw_span, term)
            if key in known:
                continue
            counts[key] += 1
            ratios[key] = max(ratios.get(key, 0.0), ratio)
    out = [
        Candidate(raw=a, fixed=b, count=n, ratio=round(ratios[(a, b)], 2))
        for (a, b), n in counts.items()
        if n >= min_count
    ]
    out.sort(key=lambda c: (-c.count, -c.ratio, c.fixed))
    return out


def read_jsonl(path: Path) -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        obj = json.loads(line)
        raw = obj.get("raw") or obj.get("asr") or ""
        fixed = obj.get("corrected") or obj.get("fixed") or obj.get("formatted") or ""
        if raw and fixed:
            rows.append((raw, fixed))
    return rows


def format_candidates(cands: list[Candidate]) -> str:
    lines = ["# raw -> fixed  (count, ratio)", ""]
    for c in cands:
        lines.append(f"{c.count:4}  r={c.ratio:.2f}  {c.raw!r:35} -> {c.fixed}")
    lines.append("")
    lines.append(f"# {len(cands)} candidates. Review before adding as fixtures.")
    return "\n".join(lines)
