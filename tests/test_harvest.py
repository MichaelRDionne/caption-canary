"""Harvest screens polish and PII and keeps recoverable specialist misses."""

import json
from pathlib import Path

from captioncanary.harvest import harvest, read_jsonl


def _write(path: Path, raw: str, corrected: str) -> None:
    path.write_text(json.dumps({"raw": raw, "corrected": corrected}) + "\n")


def test_keeps_specialist_misspelling(tmp_path: Path):
    src = tmp_path / "pairs.jsonl"
    _write(src, "started on escatalopram ten milligrams", "started on escitalopram 10 mg")
    cands = harvest(read_jsonl(src))
    assert any(c.raw == "escatalopram" and c.fixed == "escitalopram" for c in cands)


def test_drops_unit_polish(tmp_path: Path):
    src = tmp_path / "pairs.jsonl"
    _write(src, "give five milligrams at night", "give 5 mg at night")
    cands = harvest(read_jsonl(src))
    assert not any(c.fixed in {"mg", "milligrams"} for c in cands)


def test_drops_hyphen_polish(tmp_path: Path):
    src = tmp_path / "pairs.jsonl"
    _write(src, "schedule a follow up next week", "schedule a follow-up next week")
    cands = harvest(read_jsonl(src))
    assert cands == []


def test_drops_email_and_name(tmp_path: Path):
    src = tmp_path / "pairs.jsonl"
    _write(
        src,
        "email jane doe at jane@example.com about escatalopram",
        "email Jane Doe at jane@example.com about escitalopram",
    )
    cands = harvest(read_jsonl(src))
    assert cands == []


def test_skips_already_known_pair(tmp_path: Path):
    src = tmp_path / "pairs.jsonl"
    _write(src, "preservation of the theme", "perseveration of the theme")
    known = {("preservation", "perseveration")}
    cands = harvest(read_jsonl(src), known=known)
    assert cands == []
