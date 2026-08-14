"""CLI: python -m captioncanary transcript.txt terms.txt [--compare other.txt]
       python -m captioncanary harvest pairs.jsonl
"""

import argparse
import json
import sys
from pathlib import Path

from .core import compare_transcripts, score_transcript


def _harvest(argv: list[str]) -> int:
    from .harvest import format_candidates, harvest, load_known, read_jsonl

    ap = argparse.ArgumentParser(
        prog="captioncanary harvest",
        description="Screen paired raw/corrected transcripts for addable substitutions.",
    )
    ap.add_argument("pairs", help="JSONL with raw/corrected (or asr/formatted) fields")
    ap.add_argument("--blocklist", type=Path, help="one regex per line, comments ok")
    ap.add_argument(
        "--known",
        type=Path,
        nargs="*",
        default=[],
        help="existing term lists or tests to skip",
    )
    ap.add_argument("--min-count", type=int, default=1)
    ap.add_argument("--json", action="store_true", dest="as_json")
    args = ap.parse_args(argv)

    rows = read_jsonl(Path(args.pairs))
    known = load_known(list(args.known)) if args.known else set()
    cands = harvest(rows, blocklist=args.blocklist, known=known, min_count=args.min_count)
    if args.as_json:
        print(json.dumps(
            [c.__dict__ for c in cands],
            indent=2,
        ))
    else:
        print(format_candidates(cands))
    return 0


def main() -> int:
    if len(sys.argv) > 1 and sys.argv[1] == "harvest":
        return _harvest(sys.argv[2:])

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "transcript",
        help="transcript file: plain text, WebVTT, or SRT",
    )
    ap.add_argument("terms", help="expected domain terms, one per line")
    ap.add_argument("--compare", help="second transcript of the same audio")
    ap.add_argument(
        "--json",
        action="store_true",
        dest="as_json",
        help="print a machine-readable report",
    )
    args = ap.parse_args()

    transcript = Path(args.transcript).read_text()
    terms = [t.strip() for t in Path(args.terms).read_text().splitlines()
             if t.strip() and not t.startswith("#")]

    if args.compare:
        cmp = compare_transcripts(transcript, Path(args.compare).read_text(), terms)
        print(json.dumps({
            "preferred": args.transcript if cmp["preferred"] == "a" else args.compare,
            "coverage_a": cmp["a"].coverage,
            "coverage_b": cmp["b"].coverage,
            "gap_significant": cmp["gap_significant"],
        }, indent=2))
        return 0

    r = score_transcript(transcript, terms)
    if args.as_json:
        print(json.dumps({
            "verdict": r.verdict,
            "coverage": r.coverage,
            "found": r.found,
            "missing": r.missing,
            "near_misses": r.near_misses,
            "detail": r.detail,
        }, indent=2))
    else:
        print(f"{r.verdict.upper()}: {r.detail}")
        if r.near_misses:
            for term, span in r.near_misses.items():
                print(f"  {term!r} likely garbled to {span!r}")
    return 0 if r.verdict == "ok" else 1


if __name__ == "__main__":
    sys.exit(main())
