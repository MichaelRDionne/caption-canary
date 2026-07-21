"""Ground-truth tests: a faithful transcript, a fluent-nonsense transcript,
and the phonetic-substitution detector that separates them."""

import pytest

from captioncanary.core import compare_transcripts, find_near_misses, score_transcript

PSYCHOPHARM_TERMS = [
    "clozapine", "agranulocytosis", "myocarditis", "titration",
    "neutrophil", "rechallenge", "sialorrhea", "seizure threshold",
]

# What a decent transcript of a clozapine lecture contains.
GOOD = """
Today we cover clozapine. The feared risks are agranulocytosis and
myocarditis, which is why slow titration matters and why we monitor the
absolute neutrophil count weekly. Rechallenge after neutropenia is a
specialist decision. Sialorrhea is common and manageable, and remember
clozapine lowers the seizure threshold in a dose-dependent way.
"""

# What auto-captions actually produce on the same audio: fluent, grammatical,
# and wrong everywhere the domain vocabulary appears.
FLUENT_NONSENSE = """
Today we cover close a pin. The feared risks are a granular site process and
my old card artist, which is why slow situation matters and why we monitor
the absolute new profile count weekly. Free challenge after new to peanut is
a specialist decision. See a lorry a is common and manageable, and remember
close a pin lowers the see sure threshold in a dose dependent way.
"""


def test_good_transcript_passes():
    r = score_transcript(GOOD, PSYCHOPHARM_TERMS)
    assert r.verdict == "ok"
    assert r.coverage == 1.0
    assert not r.near_misses


def test_fluent_nonsense_fails():
    r = score_transcript(FLUENT_NONSENSE, PSYCHOPHARM_TERMS)
    assert r.verdict == "failed"
    assert r.coverage <= 0.2
    assert "fluent nonsense" in r.detail


def test_phonetic_substitution_detected():
    # The signature failure: the term's letters survive, split across words.
    assert find_near_misses(FLUENT_NONSENSE, "clozapine") == "close a pin"


def test_exact_term_is_not_a_near_miss():
    assert find_near_misses(GOOD, "clozapine") is None


def test_partial_transcript_is_suspicious():
    partial = "We discussed clozapine, titration, and sialorrhea today."
    r = score_transcript(partial, PSYCHOPHARM_TERMS)
    assert r.verdict == "suspicious"
    assert 0.2 < r.coverage < 0.5


def test_compare_prefers_whisper_over_bad_captions():
    cmp = compare_transcripts(FLUENT_NONSENSE, GOOD, PSYCHOPHARM_TERMS)
    assert cmp["preferred"] == "b"
    assert cmp["gap_significant"]


def test_empty_terms_rejected():
    with pytest.raises(ValueError):
        score_transcript(GOOD, [])
