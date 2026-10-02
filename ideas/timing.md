# Timing

These players choose their own clock for the tick, the rows and the note starts.
A cheap clock trick changes the feel of a song, or saves CPU time.

## Fractional tempo

A byte sum skips some ticks. The song then plays at a tempo between two whole
speeds.

- [David Whittaker](../players/DavidWhittaker.md): each tick adds the drop rate,
  `Tempo`, to a byte sum. A carry drops the music's tick.
  `specs/david_whittaker.py:Play`
  - Xenon 2 drops 20 of every 256 ticks. Note lengths differ by one tick.

## Swing

Rows alternate between two lengths in ticks. Even rows and odd rows then sound
uneven, like a shuffle.

- [Mugician II](../players/MugicianII.md): the two nibbles of the speed byte
  give the two row lengths. After each row, the nibbles swap.
  `specs/mugician_ii.py:SwingSpeeds`
- [Musicline Editor](../players/MusiclineEditor.md): each voice has its own
  `speed` and swing. Voices can swing against each other.
  `specs/musicline.py:PlayVoice`

## Tempo-independent rates

The tempo sets the length of a tick. Here, each rate scales with that length.
Envelopes, LFOs and portamento then keep their speed at any tempo.

- [Sonix Music Driver](../players/SonixMusicDriver.md): the tick length is a
  constant divided by the tempo. Every rate step is multiplied by it.
  `specs/sonix_music_driver.py:SetTempo`

## Interrupt clock

The audio interrupts run the replay. No VBL tick and no CIA timer exist.

- [MusicMaker 8V](../players/MusicMaker-8V.md): each mix buffer lasts one tick
  at its channel's period. The tick runs once all four channels have started
  their buffers. `specs/music_maker_8v.py:AudioInterrupt`
  - The replay busy-waits inside the interrupt for the last channel.
    `specs/music_maker_8v.py:WaitAllChannels`

## Timer DMA wait

A [DMA restart wait](../docs/paula-techniques.md#dma-restart-wait) runs on a
timer. The CPU does not busy-wait.

- [Musicline Editor](../players/MusiclineEditor.md): timer B waits the longest
  old period. Then DMA goes on. `specs/musicline.py:DmaPlay`
  - A second timer B interrupt writes each restarted channel's loop. It sets
    `AUDxLC` and `AUDxLEN`. `specs/musicline.py:DmaLoop`

## Stop signal

A note start waits for the channel's interrupt request, a
[stop signal](../docs/paula-techniques.md#stop-signal). The wait ends when the
old word has played.

- [Digital Sonix & Chrome](../players/DigitalSonixChrome.md): the CPU busy-waits
  up to two periods of the old word per note.
  `specs/digital_sonix_chrome.py:WaitAudioIrq`

## Compared

- A DMA restart wait costs CPU time. Musicline Editor hands it to a timer.
  Digital Sonix & Chrome busy-waits for the stop signal.
- Sonix Music Driver runs its tick from a
  [CIA timer](../docs/paula-techniques.md#cia-timer). MusicMaker 8V needs no
  timer. Its buffer lengths set the tick.
