# Player card template

Copy into `players/<name>.md`; angle brackets mark placeholders. Add `spec` to
the player in [`data/players.yaml`](../data/players.yaml). Then run
`tools/cards.py --write players/<name>.md` to fill Context.

```markdown
---
player: <binary name in ext/uade/players>
template: 2
ideas: [<idea slug>]
---

# <Player name>

<One sentence: what makes it different.>

## Context

## Key ideas

- <Idea.> `:<Label>`
  - Enables: <what it makes possible>.
  - Costs: <limits or memory; CPU only when it is expensive>.

## Composer's view

<What the composer edits. Name the format's own terms once, in code.>

| Aspect   | Answer                                | Source                 |
| -------- | ------------------------------------- | ---------------------- |
| Notation | <what the editor shows>               | <(manual) or `:Label`> |
| Cost     | <a musical figure, and what it takes> | <…>                    |

## What is unique

- <One rule no common tracker has.> `:<Label>`

## Open questions

- <What reading did not settle.>
```

## Goals

A card lets a reader:

- borrow an idea for a new player
- see how a composer writes for the player
- find the routine in the spec that shows the details

## Card and spec

- The spec, `specs/<player>.py`, is the model: state, routines and their order.
  [`tools/specs.py`](../tools/specs.py) checks it.
- The card says what makes the player unique. It holds no code and nothing the
  spec already holds.
- Each `:<Label>` names a function or class in the spec.

## Sections

- **Context** is generated from [`data/players.yaml`](../data/players.yaml),
  which also holds manual links. Mark manual citations "(manual)".
- **Key ideas**: each bullet gives the idea, what it enables and what it costs.
  Rate CPU only when it is medium or high, with a reason.
- **Composer's view**: prose, then Notation and Cost rows. A source is
  "(manual)" or spec labels. Format notes feed the spec; cite its label.
- **What is unique**: one flat list, no `###`. Each bullet is one rule on
  timing, sound or sequencing, with its label. Leave out what every tracker
  does.

## Delta cards

A version with a distinct idea may share most of its model with the family's
card. Its delta card has `base: <player>`, naming that card. It may skip
Composer's view.

## Rules

- Paula mechanics go to [`paula.md`](paula.md) and
  [`hardware/paula.py`](../hardware/paula.py). When a Paula feature is the idea,
  keep a key idea and link there.
- Game sound effects appear only as a distinct key idea.
- Skip Open questions when there is nothing to say.
- Tables skip the card's word limit.
- One fact per table cell, never `;`. Repeat the first column for more.

## Template 1

Cards without `template: 2` follow the old template until they are migrated. Git
history has its text; `tools/cards.py` still checks it.
