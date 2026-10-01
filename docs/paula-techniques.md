# Paula techniques

Common ways replayers drive Paula. Cards link here instead of explaining them.
The chip's facts are in [Paula in one page](paula.md).

## Silent loop

A channel always loops. To end a one-shot sample, the replay sets its loop to a
short run of zeros. DMA stays on, and the channel plays silence until the next
note.

Seen in: [SoundMon 2.2](../players/SoundMon2.2.md),
[Art Of Noise 8V](../players/ArtOfNoise-8V.md),
[Digital Sonix & Chrome](../players/DigitalSonixChrome.md).

## Loop by reload

The note start writes the whole sample to `AUDxLC` and `AUDxLEN`. Before the
first reload, the replay writes the loop. Paula takes the loop at the reload,
with no interrupt.

Edge: a loop written before DMA start replaces the start. The note then plays
from its loop point.

Seen in: [SoundMon 2.2](../players/SoundMon2.2.md), at the next tick.

## DMA restart wait

A note restart turns DMA off, waits, writes the sample and turns DMA on. After
DMA off, a channel finishes its word: up to two periods.

A wait shorter than that misses the restart. The old sample then plays on until
its next reload.

| Player                                    | Wait                                             |
| ----------------------------------------- | ------------------------------------------------ |
| [SoundMon 2.2](../players/SoundMon2.2.md) | A busy-wait loop of 647 CCK                      |
| SoundMon 2.2                              | Without a display, it may miss periods above 544 |
| `ptplayer` 6.4                            | A one-shot CIA timer, 576 counts                 |

## Stop signal

DMA on waits only until the channel is idle. The CPU learns that from an
interrupt request.

With its `INTREQ` bit clear, a stopped channel plays one more word and requests
an interrupt. A write to `AUDxDAT` does the same from idle.

Seen in: [Digital Sonix & Chrome](../players/DigitalSonixChrome.md).

## Live wave edits

The CPU rewrites sample bytes while DMA plays them. Edits sound at the next
fetch, with no copy. Voices that play the same bytes hear each other's edits.

Seen in: [SoundMon 2.2](../players/SoundMon2.2.md), [Fred](../players/Fred.md),
[Mugician II](../players/MugicianII.md).

## Loop counting

The audio interrupt comes at each reload. A handler can count sample passes, or
chain the next sample. It costs one interrupt per reload.

## Mixing

The audio interrupt fills the next buffer for several voices per channel. It
costs CPU time per output byte. See [voice mixing](../ideas/voice-mixing.md).

## Attach modes

One channel modulates the next one's period or volume. It costs a whole voice.
See [attach modes](paula.md#attach-modes).

## CIA timer

A CIA timer interrupt runs the tick at any rate. So the score can set a tempo.
Model: `hardware/cia.py:CiaTimer`.
