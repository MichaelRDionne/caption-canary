# caption-canary

Catch AI transcripts that failed *silently* — the ones that read fluently and
are wrong.

When speech-to-text mangles specialist audio, it doesn't crash or garble. It
substitutes: the hard technical words get replaced by ordinary words that sound
the same, and the result reads like a normal sentence. This tool checks a
transcript for the vocabulary its topic says should be there, and raises the
alarm when it isn't.

## The failure mode

Automatic captions on specialist content don't crash. On a psychopharmacology
lecture they cheerfully produce:

> "Today we cover **close a pin**. The feared risks are **a granular site
> process** and **my old card artist**…"

for audio that said *clozapine*, *agranulocytosis*, and *myocarditis*. The
output is grammatical, confident, and useless — and because it's fluent,
nothing downstream flags it. I hit this pulling lecture transcripts for study
notes: the caption engine had quietly replaced most of the clinical vocabulary
with phonetic soundalikes, and every summary built on top of it inherited the
garbage.

## The canary

Specialist content predicts its own vocabulary. A transcript of a clozapine
lecture that contains almost no clozapine-lecture words is broken, no matter
how clean it reads:

```
$ python -m captioncanary transcript.vtt terms.txt
FAILED: only 0% of expected terms present; phonetic substitutions detected:
{'clozapine': 'close a pin', 'seizure threshold': 'see sure threshold'}
— transcript is likely fluent nonsense for this topic
```

Two checks:

1. **Vocabulary coverage** — fraction of expected domain terms present.
   Under 50% → suspicious; under 20% → failed. Conservative on purpose.
2. **Phonetic-substitution detection** — the signature of silent caption
   failure is that a term's letter material survives, split across adjacent
   common words. Positional string comparison misses this ("closeapin" vs
   "clozapine" differs at 6 of 9 positions), so the matcher uses sequence
   similarity over squashed word runs and recovers the garbled span when
   the letter skeleton is close enough (`clozapine` → `close a pin`,
   `seizure threshold` → `see sure threshold`). Weaker soundalikes stay
   in the missing list; the canary does not invent a span it cannot defend.

WebVTT and SRT are first-class input. YouTube auto-captions overlap: the
tail of cue N is the head of cue N+1. The tool strips timestamps and
collapses that overlap before it scores, so a substitution is not split
across a cue cut and a term is not counted twice.

Comparison mode scores two transcripts of the same audio (platform captions
vs a local Whisper run) and reports whether the coverage gap is big enough to
mean one of them silently failed:

```
$ python -m captioncanary autocaptions.txt terms.txt --compare whisper.txt
```

## Why this matters beyond captions

This is a general pattern for AI-output QC: **fluency is not evidence of
correctness, and the absence of expected domain signal is a measurable red
flag.** The same trick — score generated output against the vocabulary its
context predicts — applies to summaries, extractions, and translations.

Companion essay: **[When Not to Use a Model](https://github.com/MichaelRDionne/MichaelRDionne/blob/main/when-not-to-use-a-model.md)** — this tool is the third of three cases on when a deterministic check beats a better model.

## Run it

```bash
python -m captioncanary examples/fluent-nonsense.vtt examples/clozapine-lecture-terms.txt
pip install pytest && python -m pytest tests/ -v
```

## 🪨 in caveman

<p align="center"><img src="assets/caveman.svg" width="120" alt="caveman"></p>

*(for when above too many word)*

ROBOT LISTEN. ROBOT WRITE DOWN WHAT HEAR. WORDS COME OUT SMOOTH.<br>
SMOOTH NOT MEAN RIGHT — ROBOT SWAP HARD WORD FOR EASY WORD THAT SOUND SAME. SNEAKY.

THIS TOOL = CANARY. CANARY KNOW WHAT WORD BELONG.<br>
RIGHT WORD GONE, FAKE WORD SNEAK IN → CANARY SING. CANARY QUIET → PROBABLY FINE.

EYEBALL TIRED. EYEBALL TRUST SMOOTH.<br>
CANARY NOT TRUST SMOOTH — CANARY LISTEN FOR WORD THAT SHOULD BE THERE. NOT THERE = DANGER.

🪨 Caveman voice borrowed, with thanks, from **[caveman](https://github.com/JuliusBrussee/caveman)** by [Julius Brussee](https://github.com/JuliusBrussee) — a Claude Code skill that makes agents talk like this to cut ~75% of output tokens. Credit to him for the style; go star it.

## License

No dependencies beyond the standard library. Test fixtures are synthetic
reconstructions of the failure mode. MIT license.
