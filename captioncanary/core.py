"""Detect fluent-but-wrong machine transcripts via domain-vocabulary scoring.

The failure mode this targets: automatic captions on specialist content
(medical lectures, technical talks) don't fail loudly — they fail FLUENTLY,
substituting real domain terms with phonetically similar common words
("clozapine" -> "close a pin", "akathisia" -> "a cat is here"). The transcript
reads fine and is wrong, and nothing warns you.

The canary: specialist content predictably contains its own vocabulary. Score
the transcript against a domain term list; a fluent transcript of a
psychopharmacology lecture that contains almost no psychopharmacology terms
is a red flag regardless of how clean it reads.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .clean import prepare_transcript


@dataclass
class CanaryReport:
    verdict: str  # "ok" | "suspicious" | "failed"
    coverage: float  # fraction of expected terms found (0-1)
    found: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    near_misses: dict[str, str] = field(default_factory=dict)  # term -> lookalike found
    detail: str = ""


def _normalize(text: str) -> str:
    return re.sub(r"[^a-z0-9\s]", " ", text.lower())


def _squash(term: str) -> str:
    """Collapse a term to its letter skeleton: 'close a pin' -> 'closeapin'."""
    return re.sub(r"[^a-z0-9]", "", term.lower())


def find_near_misses(text: str, term: str, window: int = 4) -> str | None:
    """Look for the term's letter skeleton split across adjacent common words —
    the classic phonetic-substitution signature ('clozapine' -> 'close a pin').

    Returns the matching word run, or None.
    """
    from difflib import SequenceMatcher

    target = _squash(term)
    words = _normalize(text).split()
    best_span, best_ratio = None, 0.0
    for i in range(len(words)):
        run = ""
        for j in range(i, min(i + window, len(words))):
            run += words[j]
            if len(run) < len(target) - 2:
                continue
            if len(run) > len(target) + 2:
                break
            # Phonetic substitutions keep most of the letter material but not
            # letter positions ("closeapin" vs "clozapine" differs at 6 of 9
            # positions), so positional comparison fails — sequence similarity
            # is the right measure. First letter must agree to cut noise,
            # except at very high similarity ("free challenge" / "rechallenge"
            # is 0.92 and the letter rule would drop it).
            ratio = SequenceMatcher(None, run, target).ratio()
            if run[0] != target[0] and ratio < 0.90:
                continue
            span = " ".join(words[i : j + 1])
            if ratio >= 0.75 and span != term.lower() and ratio > best_ratio:
                best_span, best_ratio = span, ratio
    return best_span


def score_transcript(
    transcript: str,
    expected_terms: list[str],
    ok_threshold: float = 0.5,
    fail_threshold: float = 0.2,
) -> CanaryReport:
    """Score a transcript against the vocabulary its topic predicts.

    Thresholds are deliberately conservative defaults: a lecture transcript
    that contains under half its expected vocabulary deserves a human look,
    and one under 20% should not be trusted at all.
    """
    if not expected_terms:
        raise ValueError("expected_terms must be non-empty")

    transcript = prepare_transcript(transcript)
    norm = _normalize(transcript)
    found, missing, near = [], [], {}
    for term in expected_terms:
        needle = _normalize(term).strip()
        present = bool(needle) and re.search(
            r"\b" + re.escape(needle) + r"s?\b", norm
        )
        if present:
            found.append(term)
        else:
            missing.append(term)
            lookalike = find_near_misses(transcript, term)
            if lookalike:
                near[term] = lookalike

    coverage = len(found) / len(expected_terms)

    if coverage >= ok_threshold and not near:
        verdict, detail = "ok", "expected vocabulary present"
    elif coverage < fail_threshold or (near and coverage < ok_threshold):
        verdict = "failed"
        detail = (
            f"only {coverage:.0%} of expected terms present"
            + (f"; phonetic substitutions detected: {near}" if near else "")
            + " — transcript is likely fluent nonsense for this topic"
        )
    else:
        verdict = "suspicious"
        detail = (
            f"{coverage:.0%} coverage"
            + (f"; possible substitutions: {near}" if near else "")
            + " — spot-check before trusting"
        )

    return CanaryReport(
        verdict=verdict,
        coverage=round(coverage, 3),
        found=found,
        missing=missing,
        near_misses=near,
        detail=detail,
    )


def compare_transcripts(
    transcript_a: str, transcript_b: str, expected_terms: list[str]
) -> dict:
    """Compare two transcripts of the same audio (e.g., platform auto-captions
    vs a local Whisper run). The one with materially higher vocabulary
    coverage wins; a large gap is itself evidence the loser failed silently."""
    a = score_transcript(transcript_a, expected_terms)
    b = score_transcript(transcript_b, expected_terms)
    gap = abs(a.coverage - b.coverage)
    preferred = "a" if a.coverage >= b.coverage else "b"
    return {
        "a": a,
        "b": b,
        "preferred": preferred,
        "coverage_gap": round(gap, 3),
        "gap_significant": gap >= 0.25,
    }
