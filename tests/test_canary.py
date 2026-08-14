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
    assert find_near_misses(FLUENT_NONSENSE, "seizure threshold") == "see sure threshold"
    # First-letter waiver: ratio is high enough that the letter rule would
    # have dropped this.
    assert find_near_misses(FLUENT_NONSENSE, "rechallenge") == "free challenge"


def test_weaker_substitutions_are_not_invented():
    # These are real caption failures in the fixture. Sequence similarity
    # is below the 0.75 cut, so the canary reports them as missing, not as
    # recovered spans. Do not lower the cut to chase them.
    assert find_near_misses(FLUENT_NONSENSE, "agranulocytosis") is None
    assert find_near_misses(FLUENT_NONSENSE, "myocarditis") is None
    assert find_near_misses(FLUENT_NONSENSE, "neutrophil") is None
    assert find_near_misses(FLUENT_NONSENSE, "sialorrhea") is None
    # "situation" / "titration" is 0.78 but first letters disagree and
    # the ratio is under the 0.90 waiver.
    assert find_near_misses(FLUENT_NONSENSE, "titration") is None


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


VTT_FLUENT_NONSENSE = """WEBVTT

00:00:00.000 --> 00:00:03.000
Today we cover close a pin.

00:00:02.000 --> 00:00:05.500
close a pin. The feared risks are

00:00:04.000 --> 00:00:08.000
The feared risks are a granular site process
"""


def test_vtt_rolling_overlap_is_collapsed_then_scored():
    from captioncanary.clean import prepare_transcript

    cleaned = prepare_transcript(VTT_FLUENT_NONSENSE)
    assert cleaned.count("close a pin") == 1
    assert cleaned.count("The feared risks are") == 1
    assert "WEBVTT" not in cleaned
    assert "-->" not in cleaned

    r = score_transcript(VTT_FLUENT_NONSENSE, PSYCHOPHARM_TERMS)
    assert r.verdict == "failed"
    assert r.near_misses["clozapine"] == "close a pin"


def test_plain_text_is_not_rewritten():
    from captioncanary.clean import prepare_transcript

    assert prepare_transcript(GOOD) == GOOD


def test_substring_is_not_a_hit():
    # "pine" sits inside "clozapine"; a bare-substring check would count it.
    r = score_transcript(GOOD, ["pine", "cardio"])
    assert r.found == []

