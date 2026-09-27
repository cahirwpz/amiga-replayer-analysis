# Player card template

Copy into `players/<name>.md`. Angle brackets mark placeholders. Then run
`tools/cards.py --write players/<name>.md` to fill Context.

````markdown
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
  - Costs: <limits, memory, CPU>.

## Composer's view

```python
@dataclass
class Score:                           # what the composer edits
    <field>: <type>                    # <reuse: an index; variation: a shift>
```

| Aspect   | Answer                                | Source                 |
| -------- | ------------------------------------- | ---------------------- |
| Notation | <what the editor shows>               | <(manual) or `:Label`> |
| Cost     | <a musical figure, and what it takes> | <…>                    |

## Timing

| Stream | Scope   | Carries        | Control      | Advances by |
| ------ | ------- | -------------- | ------------ | ----------- |
| <name> | <scope> | <what it sets> | <vocabulary> | <word>      |

| Aspect  | Value   | Label      |
| ------- | ------- | ---------- |
| Time    | <words> | `:<Label>` |
| Unit    | <words> | `:<Label>` |
| Routing | <words> | `:<Label>` |
| Reuse   | <words> | `:<Label>` |
| Tempo   | <words> | `:<Label>` |

```python
def on_note(voice: Voice, note: Note, instrument: Instrument) -> None:
    <what a note-on restarts, keeps and stops>   # <Label>

def on_release(voice: Voice) -> None:  # <Label>: <what triggers it>
    <where control goes>
```

## Sound

### <Output>

```python
def <output>(voice: Voice) -> int:    # <Label>
    return voice.<controller> + voice.<controller>   # add, scale or override
```

| Controller | Kind   | Advances by | Owner   | Set by    | Label      |
| ---------- | ------ | ----------- | ------- | --------- | ---------- |
| <name>     | <kind> | <word>      | <owner> | <streams> | `:<Label>` |

## Instrument

```python
@dataclass
class Instrument:
    <field>: <type>                    # <meaning>
```

| Question               | Answer |
| ---------------------- | ------ |
| Survives the last note | <…>    |
| Track overrides        | <…>    |

## Interactions

```python
def on_<event>(voice: Voice, arg: int) -> None:  # <Label>
    voice.<target>.<field> = arg       # <when the target next runs>
```

## Open questions

- <What reading did not settle.>
````

## Goals

A card lets a reader:

- borrow an idea for a new player
- rebuild the control model
- see how a composer writes for the player

## Sections

- **Context** is generated from [`data/players.yaml`](../data/players.yaml),
  which also holds manual links. Mark manual citations "(manual)".
- **Key ideas**: each bullet gives the idea, what it enables and what it costs.
  CPU is low, medium or high, with a reason.
- **Composer's view**: a `Score` dataclass shows reuse and variation. Then
  Notation and Cost rows. Name the format's own terms once, in code.
- **Timing**: when a sound plays. Two tables, streams and Sequencer aspects,
  then lifecycle handlers.
- **Sound**: how a sound plays, one `###` per output: code, then a table. The
  full order goes to `details/`.
- **Instrument**: a dataclass of what it stores, then three questions.
- **Interactions**: events that cross between controllers or voices.

## Tables

- Lifecycle handlers, as far as they apply: note-on, legato, release, hard stop,
  program end. `on_note` is required.
- A stream may appear in Timing and, as a controller, in Sound.
- A controller that writes two outputs appears under each.
- Kind, Owner and Advances by take words from the glossary.
- Set by names streams or controllers on the card, or `instrument`.
- With `allocated` routing, add bullets below the Sequencer table. Say which
  voice is taken or stolen.

## Code

- Write Python-like code. Use the tables' names, in snake case.
- Comments name labels. Name every constant on the state page.
- All code and the state page must pass `mypy --strict` as one module. A `...`
  body is a stub.
- Each Sound controller must be a name in the code.

## Detail pages

- `details/<player>-state.md` declares voice state, controllers and helpers.
- The full order of writes goes to `details/<player>-control.md`.
- Add more `details/<player>-<topic>.md` pages when a topic needs them. Link
  each from the section it deepens.

## Delta cards

A version with a distinct idea may share most of its model with the family's
card. Its delta card has `base: <player>`, naming that card.

- It may skip Composer's view, Timing and Instrument.
- Sound lists only the outputs that change.
- Its tables may name the base card's streams and controllers.

## Rules

- Paula mechanics, e.g. DMA writes, go to [`paula.md`](paula.md). When a Paula
  feature is the idea, keep a key idea and link there.
- Game sound effects appear only as a distinct key idea.
- Skip Interactions and Open questions when there is nothing to say.
- Tables and code skip the card's word limit.
- One fact per table cell, never `;`. Repeat the first column for more.

## Template 1

Cards without `template: 2` follow the old template until they are migrated. Git
history has its text; `tools/cards.py` still checks it.
