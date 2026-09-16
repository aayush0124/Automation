# OpenMontage — evaluation for the content pipeline

**Date:** 2026-09-16
**Question asked:** would installing OpenMontage help our systems?
**Scope of this note:** the content pipeline — Instagram Reels, Shorts, the Remotion
video work, @AIwithAayush and @political.roaster.
**Outcome:** worth a paid trial on one real video. Not worth adopting wholesale yet,
and it does nothing at all for the carousel side of the pipeline.

Nothing was installed. This is a read of the source, not a deployment.

---

## What it actually is

[calesthio/OpenMontage](https://github.com/calesthio/OpenMontage) — an open-source
"agentic video production system." You clone it into a repo, open that repo in an AI
coding assistant, and describe the video you want in plain language. The agent runs
research, scripting, asset generation, voiceover, editing and final render.

It is not a library you `pip install` and import. There is no `openmontage` package on
PyPI or npm — both 404. The unit of installation is the repo itself, and the thing that
"runs" it is the coding assistant reading its instruction files.

What's in the box, counted from a fresh clone rather than from the README:

| | |
|---|---|
| Pipelines | 13 (`pipeline_defs/*.yaml`) |
| Tool scripts | 167 Python files under `tools/` |
| Skill files | 157 under `skills/`, plus mirrored copies in `.claude/` and `.agents/` |
| Clone size | 162 MB before `npm install` |
| License | AGPLv3 |
| Composition engine | Remotion |

The README's "12 pipelines, 100+ tools, 700+ files" is in the right neighbourhood; the
700 counts the duplicated per-assistant skill directories.

## What it would cost to stand up

Prerequisites are Python 3.10+, FFmpeg, Node 18+, and a coding assistant. Setup is
`git clone` then `make setup`, which builds a venv, pip-installs, runs `npm install`
inside `remotion-composer`, adds `piper-tts`, and copies `.env.example` to `.env`.

Running costs are genuinely low, and the free floor is real:

- **$0 tier works.** Pexels + Pixabay for stock, Google TTS (1M chars/month free),
  ElevenLabs (10K chars/month free), and Piper for fully offline TTS. You can produce
  finished video without paying anyone.
- **Paid tier is cheap per unit.** ~$0.03–0.05 per generated image. The project's own
  worked examples: a 60-second animated short at **$1.33**, a 50-second vertical film
  at **~$4**.

Those numbers are the project's claims about its own demos, not something I verified.
Treat them as the optimistic end.

## Where it fits our pipeline — and where it doesn't

**It does not help the carousels.** OpenMontage is video, end to end. The
@AIwithAayush and @political.roaster carousel skills render 1080×1350 PNG slides.
There is zero overlap. If the hope was that this lifts the whole content operation,
it doesn't — it lifts one lane.

**The real fit is Reels and Shorts from long-form source.** Two pipelines matter:

- `clip-factory` — takes a webinar, stream, or long interview and produces N
  independent short clips cut for social. This is the one worth trying. It's the piece
  we don't currently have, and it's the part of short-form production that is pure
  grind.
- `podcast-repurpose` — audio or video podcast into audiogram clips, caption-led cuts,
  and quote cards.

Also present and plausibly relevant: `talking-head`, `animated-explainer`,
`avatar-spokesperson`, `localization-dub`. Vertical 9:16 is handled across the
pipelines, not bolted on — the scene and compose directors reference it directly.

**It partly collides with what we already run.** OpenMontage composes with Remotion,
which is exactly what the existing Remotion video editor setup does, with brand
enforcement (the dark background, the purple and blue accents, the Hinglish tone)
already baked in. OpenMontage brings no knowledge of that brand. So adopting it whole
means either rebuilding the brand rules inside its skill files or running two Remotion
setups side by side. Neither is free.

**Hindi and Hinglish are supported but not a strength.** Indic languages appear in the
provider docs, the transcription options, and a `video-translate` skill. Nothing
suggests it handles Hinglish code-switching well, and that is the register most of our
content lives in. Assume the script still gets written by us.

## What I'd flag before anyone runs `make setup`

1. **It ships 150+ agent instruction files that your assistant will read as
   directives.** That is the mechanism — it is how the thing works — but it is also a
   large prompt-injection surface in a repo that takes community pull requests. If it
   goes anywhere, it goes in its own repo, not next to anything that matters.
2. **The pipelines are marked `stability: beta`.** Not a footnote — it's in the YAML of
   the ones we'd actually use, `clip-factory` and `podcast-repurpose` included.
3. **The project is about six months old.** Created March 2026, ~59.5k stars, 325 open
   issues. The star count reflects attention, not maturity. A repo that trends this hard
   this fast has not yet been through a boring year.
4. **AGPLv3.** Irrelevant for producing videos and posting them — that's just using the
   software. It becomes relevant the moment anyone wants to wrap it in a hosted service
   for other people. Worth knowing now rather than later.
5. **Budgets default to $1.00 per pipeline run** with up to 3 revisions per stage. Cheap
   per run; less cheap across a week of iteration where most runs get thrown away.

## Recommendation

Do a scoped trial, not an adoption.

1. Stand it up in **its own repo**, never inside `Automation`. This repo's entire
   premise is offline, zero-dependency, no network calls. OpenMontage is the exact
   inverse, and merging them would break the one guarantee that makes this tool worth
   having.
2. Run the **free tier only** for the first pass — Pexels, Pixabay, Google TTS. No
   cards, no keys beyond the free ones.
3. Give it **one honest job**: a long recording we already have, through
   `clip-factory`, to Reels. Judge the clips against what we'd have cut by hand.
4. Decide on that evidence. If the clips are usable, the next question is whether to
   port our brand rules into its skills or keep it as a separate, rougher lane for
   repurposing only.

The honest summary: this is a well-built and unusually complete project, and the
clip-extraction pipeline is the one thing in it we don't already have some version of.
That's enough to justify an afternoon. It is not enough to justify rebuilding the
content pipeline around it.
