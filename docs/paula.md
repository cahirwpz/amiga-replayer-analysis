# Paula in one page

Paula is the Amiga sound chip. This page lists only the facts that shape
replayer design.

Full, cited reference: `docs/paula.md` in the ghostown-spookytown-2 repo.

## What a channel has

Four channels. Each has a sample pointer, a length, a period and a volume.

| Register | Meaning                                            |
| -------- | -------------------------------------------------- |
| AUDxLC   | Sample start. Copied to the pointer at each wrap.  |
| AUDxLEN  | Sample length in words.                            |
| AUDxPER  | Pitch as a clock divider: rate = 3546895 / period. |
| AUDxVOL  | Volume 0–64, linear.                               |

## Facts and what they force

| Fact                                                | Consequence for replayers                       |
| --------------------------------------------------- | ----------------------------------------------- |
| A channel always loops.                             | One-shot sounds need a short silent loop.       |
| New pointer applies at the next wrap.               | Set loop start just after the note starts.      |
| DMA start takes the pointer up to a scanline later. | Replayers wait before writing the loop pointer. |
| First word after DMA start is dropped.              | Audio starts on the second word.                |
| Period minimum is about 124.                        | Top rate is about 28.6 kHz per channel.         |
| Samples are 8-bit, word-aligned, even length.       | Formats store lengths in words.                 |
| No mixer, only four voices.                         | More voices need CPU mixing into a buffer.      |
| Interrupt at DMA start and at each wrap.            | Enables sample chaining and streaming.          |
| Stereo is fixed: 0 and 3 left, 1 and 2 right.       | No panning. Formats assign parts to channels.   |

## Rarely used

**Attach modes** let one channel modulate the next one's volume or period. It
costs a whole voice. No known game uses it.

**Volume changes** are cheap CPU writes. Replayers do envelopes and tremolo in
software, once per tick.
