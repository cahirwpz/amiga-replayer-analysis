# Player card template

Copy into `players/<name>.md`; angle brackets mark placeholders. Add `spec` to
the player in [`data/players.yaml`](../data/players.yaml).

```markdown
---
player: <binary name in ext/uade/players>
template: 3
ideas: [<idea slug>]
---

# <Player name>

<One sentence: what makes it different.>

## Unique ideas

- <Idea.> `:<Label>`
  - Limits: <a hard limit of the idea>.

## How it plays

<The interrupts that drive the replay, and what each one does.>

<The order of one tick, in one or two sentences.>

### <Owner: player, voice, walker or table pool>

<The state it holds.> `:<Class>`

1. <A step, in code order: what it writes, from which state.> `:<Label>`
   - **Trap:** <an interaction that a port gets wrong.>

## Open questions

- <What reading did not settle.>
```

## Goals

A card is a message from the replay's author. Its reader knows ProTracker
replays, Paula and synth basics. A card lets the reader:

- borrow an idea for a new player
- see how data and state become register writes, tick by tick
- avoid the traps of a port
- find the routine in the spec that shows the details

[`control-dimensions.md`](control-dimensions.md) lists the control questions a
card answers when the player's answer is distinct. Card reviews run only when
asked: [`tools/reviews.py`](../tools/reviews.py).

## Card and spec

- The spec, `specs/<player>.py`, is the model: state, routines and their order.
  [`tools/specs.py`](../tools/specs.py) checks it.
- The card explains how the player works and what makes it unique. It holds no
  code.
- Each `:<Label>` names a function or class in the spec.

## Sections

- **Unique ideas**: each bullet gives the idea, then its hard limits. Rate CPU
  only when it is medium or high, with a reason.
- **How it plays** starts with the interrupts. Then one `###` per owner of
  state: its state, then what changes it.
- A step names the register or the bytes it writes, and from which state. Steps
  that run in a fixed order are numbered.
- Each card says how a voice falls silent.
- **Trap:** marks an interaction between parts of the replay. It sits under the
  step that causes it.
- Traps come from shared state, data with two readings, or row state mixed with
  voice state.
- **Open questions** cover the replay only, never the editor. Skip the section
  when there is nothing to say.

## Delta cards

A version with a distinct idea may share most of its model with the family's
card. Its delta card has `base: <player>`, naming that card. It covers only what
differs.

## Rules

- A term has one name and one meaning on a card. A card-local term is defined
  once, with its owner's state.
- Common Paula techniques are linked from
  [`paula-techniques.md`](paula-techniques.md), not explained. Chip facts are in
  [`paula.md`](paula.md).
- Game sound effects appear only as a distinct unique idea.
- A card fits two printed pages. `tools/print.py --check` counts them.
- One fact per table cell, never `;`. Repeat the first column for more.
- Template 2 cards keep their older shape until their review rewrites them.
  [`tools/cards.py`](../tools/cards.py) checks both.
