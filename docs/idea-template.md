# Technique family template

A family page compares one group of techniques across players. Its families and
their idea slugs are in [`data/ideas.yaml`](../data/ideas.yaml). Copy into
`ideas/<family>.md`; angle brackets mark placeholders.

```markdown
# <Family title>

<Two sentences: what the family does, and why it is cheap or expressive.>

## <Idea name, in plain words>

<One or two sentences: the technique itself, in glossary terms.>

- [<Player>](../players/<Player>.md): <how this player does it, or what
  differs.> `specs/<spec>.py:<Label>`

## Compared

- <A real contrast between players.>
```

## Rules

- The reader knows ProTracker replays, Paula and synth basics. A page has at
  most 600 words.
- Write as a technical writer: name the state, the data and what it changes. Use
  glossary terms in their defined meaning.
- One `##` per idea slug of the family, in the order of `data/ideas.yaml`.
- One bullet per player. It sums up the card, links it and repeats no other
  bullet. A spec label, from the repo root, ends it.
- Link [`paula-techniques.md`](paula-techniques.md) instead of explaining a
  Paula technique.
- **Compared** holds only real contrasts. Skip it when there is none.
- Facts come from the cards and their specs. A page adds no new claim.
