"""Prepare raw caption files for scoring.

YouTube auto-captions arrive as WebVTT or SRT with timestamps, cue
metadata, and a rolling-window overlap (the tail of cue N is the head of
cue N+1). Scoring those bytes as-is dilutes coverage and can split a
phonetic substitution across a cue boundary. Strip the chrome, collapse
the overlap, then score the remaining words.
"""

from __future__ import annotations

import html
import re

TS_LINE = re.compile(
    r"^\s*(\d{1,2}:)?\d{1,2}:\d{2}([.,]\d{1,3})?\s*-->\s*"
    r"(\d{1,2}:)?\d{1,2}:\d{2}([.,]\d{1,3})?"
)
LEADING_TS = re.compile(
    r"^\s*[\[\(]?\s*(\d{1,2}:)?\d{1,2}:\d{2}([.,]\d{1,3})?\s*[\]\)]?\s+"
)
INLINE_TAG = re.compile(r"<[^>]+>")
CUE_SETTINGS = re.compile(r"\b(align|position|size|line):\S+", re.I)
MUSIC = re.compile(r"\[(music|applause|laughter|inaudible|silence)[^\]]*\]", re.I)
HEADER = (
    "WEBVTT",
    "NOTE ",
    "NOTE\t",
    "STYLE",
    "REGION",
    "KIND:",
    "LANGUAGE:",
)


def looks_like_captions(text: str) -> bool:
    if text.lstrip().upper().startswith("WEBVTT"):
        return True
    return TS_LINE.search(text) is not None


def extract_cue_text(text: str) -> list[str]:
    """Return caption payload lines with timestamps and metadata removed."""
    out: list[str] = []
    for raw in text.splitlines():
        s = raw.strip()
        if not s:
            continue
        if s.upper().startswith(HEADER):
            continue
        if TS_LINE.match(s):
            continue
        if s.isdigit():
            continue
        if CUE_SETTINGS.search(s) and "-->" in s:
            continue
        s = LEADING_TS.sub("", s)
        s = INLINE_TAG.sub("", s)
        s = MUSIC.sub("", s)
        s = html.unescape(s).strip()
        if s:
            out.append(s)
    return out


def dedupe_rolling(lines: list[str]) -> list[str]:
    """Collapse YouTube auto-caption overlap.

    Cues often appear twice: as the second line of cue N and the first
    line of cue N+1. Consecutive cues also share a word-level suffix /
    prefix. Both have to go or a term is counted twice and a
    substitution can straddle a cue cut.
    """
    result: list[str] = []
    for line in lines:
        if result and line == result[-1]:
            continue
        if result:
            prev_words = result[-1].split()
            cur_words = line.split()
            max_k = min(len(prev_words), len(cur_words), 12)
            overlap = 0
            for k in range(max_k, 0, -1):
                if prev_words[-k:] == cur_words[:k]:
                    overlap = k
                    break
            if overlap:
                line = " ".join(cur_words[overlap:])
                if not line:
                    continue
        result.append(line)
    return result


def prepare_transcript(text: str) -> str:
    """Return scoreable prose. Caption files are cleaned; plain text passes through."""
    if not looks_like_captions(text):
        return text
    lines = dedupe_rolling(extract_cue_text(text))
    return re.sub(r"\s+", " ", " ".join(lines)).strip()
