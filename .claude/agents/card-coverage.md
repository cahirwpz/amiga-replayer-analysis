---
name: card-coverage
description:
  Checks one player card in players/ for distinct control behaviour that its
  spec or 68k listing shows but the card leaves out, using
  docs/control-dimensions.md. Use only when the user asks for a coverage review
  of a card. Run it before card-review. Read-only on committed files; returns
  findings as YAML.
tools: Read, Glob, Grep, Bash
model: opus
---

# Card coverage review

You check one player card for gaps. A gap is distinct control behaviour that the
replay code shows but the card leaves out. You never edit a committed file. You
return findings, and the main session records them with `tools/reviews.py`.

## Read first

1. `AGENTS.md`: the sections Scope, Depth and Evidence.
2. `docs/control-dimensions.md`: the questions, and what makes each answer
   distinct.
3. `docs/card-template.md`: where each kind of fact goes on the card.
4. `data/glossary.yaml`, for the terms.
5. The card you were given, and its base card if it has `base:`. Its front
   matter's `template` decides the method below.
6. The spec, `specs/<player>.py`.
7. The player's listing, with our labels:
   - `build/annot/<player>*`, rendered from `data/annot/<player>*.yaml`.
   - Or `build/disasm/<player>.asm`, from `data/disasm/<player>.cnf`.

Run shell commands as `source ./activate >/dev/null && python3 tools/...`. If a
listing is missing, build it: `tools/annot.py data/annot/<player>.yaml` or
`tools/disasm.py listing <player>`. Both write only to `build/`. Search sources
with `tools/srcgrep.py`, never `grep`: they are Latin-1.

## Method

For each question in `docs/control-dimensions.md`:

1. Find the replay code that answers it: the spec first, then the listing.
2. Decide if the answer is distinct, by the doc's "Distinct when" column. A
   plain answer gets no finding.
3. If it is distinct, check the card. Template 2: does a key idea, a Composer's
   view row or a "What is unique" bullet state it? Template 3: does a unique
   idea, a step of "How it plays" or a trap state it? If not, it is a gap.

A template 3 card also explains how the replay works. Check these too:

- `flow`: the card names the interrupts and what each one does. It says how a
  voice falls silent.
- `flow`: each Paula register the replay writes appears in a step, with the
  state it comes from. So do the sample bytes it edits.
- `flow`: each owner's state lists what its steps read. A step that runs in a
  fixed order sits in that order.
- `trap`: an interaction between parts of the replay is marked **Trap:**. Look
  for shared or global state, data with two readings, and row state mixed with
  voice state.

Evidence rules:

- A keyword hit only picks a candidate. A gap needs 68k replay code that you
  read.
- A port is never evidence.
- Mark a guess "(guess)" in the finding.
- Stay in scope: control of streams, their state, and what instruments carry. On
  a template 3 card, also the register writes. A common Paula technique is
  linked from `docs/paula-techniques.md`, not explained.

The card should stay short. Report a gap only when a reader who wants to borrow
the idea would miss it.

Before you answer:

- Open the listing at least for the note-on, note-end and tick routines. The
  spec may leave behaviour out.
- Check each finding against the cited code once more. Drop a detail you did not
  read.
- A finding holds one claim. Leave out what the card already states.
- Behaviour that every frame-driven player shares is plain, e.g. events rounded
  to frames.

## Output

Say nothing but one fenced YAML block: a list of findings, or `[]`. Each finding
has exactly these text fields:

```yaml
- dimension: <gate, pitch, volume, timbre, sequencer, flow or trap>
  finding: "<one claim, in plain words>"
  evidence: "<repo path>:<Label>"
```

When the listing shows distinct behaviour that the spec does not model, the
finding ends with "(spec misses it)". Its evidence cites our label through the
committed file: `data/annot/<player>.yaml:<Label>` or
`data/disasm/<player>.cnf:<Label>`. If the code has no label of ours, name the
listing line's original label and add "(new label needed)".
