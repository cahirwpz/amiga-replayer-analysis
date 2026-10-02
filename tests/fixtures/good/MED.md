---
player: MED
template: 3
ideas: [volume-list, wave-list]
---

# MED

A synth sound runs a volume list and a wave list that jump into each other.

## Unique ideas

- Two command lists per instrument, each at its own speed. `:SynthTick`
  - Limits: 128 bytes per list.

## How it plays

The host's tick drives everything. `:PlayTick`

### Voice

A voice holds its lists and their positions. `:Voice`

1. The volume list writes `AUDxVOL`. `:SynthTick`
   - **Trap:** a jump cancels the other list's wait. `:VolJumpWaveList`

## Open questions

- Which songs use the jumps between lists?
