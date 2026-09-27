# Paula in one page

Paula is the Amiga sound chip. This page lists only the facts that shape
replayer design. The model is [`specs/paula.py`](../specs/paula.py).

## A channel

Paula has four channels. Each has a sample pointer, a length, a period and a
volume. `specs/paula.py:Channel`

- A channel always loops. A one-shot sound needs a short silent loop.
- A new pointer applies at the next wrap. Replayers set the loop just after the
  note starts.
- DMA start takes up to a scanline. Replayers wait before they write the loop
  pointer.
- Stereo is fixed: channels 0 and 3 left, 1 and 2 right. There is no panning.
- Volume writes are cheap. Replayers run envelopes and tremolo in software.

## Tricks

| Trick         | What it gives                            | Cost                      | Model          |
| ------------- | ---------------------------------------- | ------------------------- | -------------- |
| Loop counting | Waits in sample passes                   | One interrupt per wrap    | `:LoopCounter` |
| Loop counting | Sample chaining                          | One interrupt per wrap    | `:LoopCounter` |
| Mixing        | More than four voices                    | CPU time per output byte  | `:MixBuffer`   |
| Attach modes  | One channel modulates the next one       | A whole voice             | `:Attach`      |
| CIA timer     | Any tick rate, so the score sets a tempo | A timer and its interrupt | `:Timer`       |

No known game uses attach modes.
