# Paula in one page

Paula is the Amiga sound chip. This page lists only the facts that shape
replayer design. The model is [`hardware/paula.py`](../hardware/paula.py), timed
by [`hardware/amiga.py`](../hardware/amiga.py).

## A channel

Paula has four independent channels. Each has a sample pointer, a length, a
period and a volume. `hardware/paula.py:Channel`

- A channel always loops. A one-shot sound needs a short silent loop.
- A new pointer applies at the next reload. The reload comes with the fetch of
  the last word.
- The audio interrupt comes at DMA start and at each reload. All four channels
  share one CPU interrupt; its handler tests which channel asked.
- After DMA off, a channel finishes its word, up to two periods. DMA on before
  then does not restart the note.
- DMA start takes up to a scanline. A pointer written before then replaces the
  start, and the note plays from its loop point.
- Stereo is fixed: channels 0 and 3 left, 1 and 2 right. There is no panning.
- Volume writes are cheap. Replayers run envelopes and tremolo in software.

So replayers wait twice: before DMA on, and before they write the loop. ptplayer
6.4 waits 576 CIA counts each time, with a one-shot CIA timer.

## Tricks

| Trick         | What it gives                               | Cost                      | Model                       |
| ------------- | ------------------------------------------- | ------------------------- | --------------------------- |
| Loop counting | Waits in sample passes                      | One interrupt per reload  | —                           |
| Loop counting | Sample chaining                             | One interrupt per reload  | —                           |
| Mixing        | More than four voices                       | CPU time per output byte  | —                           |
| Attach modes  | One channel modulates the next one          | A whole voice             | `:Attach`                   |
| CIA timer     | Any tick rate, so the score sets a tempo    | A timer and its interrupt | `hardware/cia.py:CiaTimer`  |
| Stop signal   | DMA on waits only until the channel is idle | A busy-wait per note      | `hardware/paula.py:Channel` |

With its INTREQ bit clear, a stopped channel plays one more word and requests an
interrupt. A write to AUDxDAT does the same from idle. The CPU can wait for that
request, as [Digital Sonix & Chrome](../players/DigitalSonixChrome.md) does.

## Attach modes

No known game uses attach modes. One demo uses period modulation. Two sources
disagree, and neither is real hardware.

| Question                       | Hardware manual  | WinUAE             |
| ------------------------------ | ---------------- | ------------------ |
| Is a period modulator silent?  | Yes              | No: its words play |
| Can one channel modulate both? | Yes, alternating | No: one mode only  |
