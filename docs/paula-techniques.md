# Paula techniques

Common ways replayers drive Paula. Cards link here instead of explaining them.
The chip's facts are in [Paula in one page](paula.md).

## Short wave loops

A synth voice loops one short waveform, one cycle of the tone per pass. Each
byte plays for one period. The pitch is the clock divided by the period times
the wave's length.

A wave half as long plays an octave higher at the same period. Replayers use
this to stay inside Paula's period range. Edits to the wave change the timbre at
once: see [live wave edits](#live-wave-edits).

Seen in: [Fred](../players/Fred.md),
[Jochen Hippel ST](../players/Jochen_Hippel_ST.md),
[Sonix Music Driver](../players/SonixMusicDriver.md),
[SoundMon 2.2](../players/SoundMon2.2.md).

## Silent loop

A channel always loops. To end a one-shot sample, the replay sets its loop to a
short run of zeros. DMA stays on, and the channel plays silence until the next
note.

Seen in: [Art Of Noise 8V](../players/ArtOfNoise-8V.md),
[David Whittaker](../players/DavidWhittaker.md),
[Digital Sonix & Chrome](../players/DigitalSonixChrome.md),
[Fred](../players/Fred.md), [Jochen Hippel ST](../players/Jochen_Hippel_ST.md),
[MED](../players/MED.md), [MIDI-Loriciel](../players/MIDI-Loriciel.md),
[Mugician II](../players/MugicianII.md),
[Musicline Editor](../players/MusiclineEditor.md),
[Oktalyzer](../players/Oktalyzer.md),
[Paul Robotham](../players/PaulRobotham.md),
[Rob Hubbard](../players/RobHubbard.md),
[Sonic Arranger](../players/SonicArranger.md),
[Sonix Music Driver](../players/SonixMusicDriver.md),
[SoundFactory](../players/SoundFactory.md),
[SoundMon 2.2](../players/SoundMon2.2.md),
[SoundPlayer](../players/SoundPlayer.md).

## Silence by volume

A voice falls silent at volume 0, with DMA still on. The channel keeps fetching
its sample. A later volume write makes it heard again at once, with no restart.

Seen in: [Art Of Noise 8V](../players/ArtOfNoise-8V.md),
[Paul Robotham](../players/PaulRobotham.md),
[Sonix Music Driver](../players/SonixMusicDriver.md),
[Synth Dream](../players/SynthDream.md),
[Voodoo Supreme Synthesizer](../players/VoodooSupremeSynthesizer.md).

## Loop by reload

The note start writes the whole sample to `AUDxLC` and `AUDxLEN`. Before the
first reload, the replay writes the loop. Paula takes the loop at the reload,
with no interrupt.

Edge: a loop written before DMA start replaces the start. The note then plays
from its loop point.

Seen in: [Fred](../players/Fred.md),
[Future Composer 1.4](../players/FutureComposer1.4.md),
[Jason Page](../players/JasonPage.md), [MED](../players/MED.md),
[Mugician II](../players/MugicianII.md), [Oktalyzer](../players/Oktalyzer.md),
[Paul Robotham](../players/PaulRobotham.md),
[Rob Hubbard](../players/RobHubbard.md),
[Sonic Arranger](../players/SonicArranger.md),
[Sonix Music Driver](../players/SonixMusicDriver.md),
[SoundFactory](../players/SoundFactory.md),
[SoundMon 2.2](../players/SoundMon2.2.md),
[Synth Dream](../players/SynthDream.md).

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

Seen in: [David Whittaker](../players/DavidWhittaker.md),
[Future Composer 1.4](../players/FutureComposer1.4.md),
[Jochen Hippel ST](../players/Jochen_Hippel_ST.md), [MED](../players/MED.md),
[Mugician II](../players/MugicianII.md),
[Musicline Editor](../players/MusiclineEditor.md),
[Sonix Music Driver](../players/SonixMusicDriver.md),
[SoundMon 2.2](../players/SoundMon2.2.md).

## Stop signal

DMA on waits only until the channel is idle. The CPU learns that from an
interrupt request.

With its `INTREQ` bit clear, a stopped channel plays one more word and requests
an interrupt. A write to `AUDxDAT` does the same from idle.

Seen in: [Digital Sonix & Chrome](../players/DigitalSonixChrome.md),
[Sonic Arranger](../players/SonicArranger.md).

## Live wave edits

The CPU rewrites sample bytes while DMA plays them. Edits sound at the next
fetch, with no copy. Voices that play the same bytes hear each other's edits.

Seen in: [AHX](../players/AbyssHighestExperience.md),
[Jason Page](../players/JasonPage.md), [Mugician II](../players/MugicianII.md),
[Musicline Editor](../players/MusiclineEditor.md),
[Rob Hubbard](../players/RobHubbard.md),
[SoundMon 2.2](../players/SoundMon2.2.md),
[Synth Dream](../players/SynthDream.md), [Tim Follin](../players/TimFollin.md).

## Loop counting

The audio interrupt comes at each reload. A handler can count sample passes, or
chain the next sample. It costs one interrupt per reload.

Seen in: [Digital Sonix & Chrome](../players/DigitalSonixChrome.md),
[TFMX Pro](../players/TFMX-Pro.md).

## Mixing

The audio interrupt fills the next buffer for several voices per channel. It
costs CPU time per output byte. See [voice mixing](../ideas/voice-mixing.md).

Seen in: [Face The Music](../players/FaceTheMusic.md),
[MusicMaker 8V](../players/MusicMaker-8V.md).

## Attach modes

One channel modulates the next one's period or volume. It costs a whole voice.
See [attach modes](paula.md#attach-modes).

Seen in: [SoundPlayer](../players/SoundPlayer.md).

## Audio filter switch

The [audio filter](glossary.md) has one switch for all four channels. A replay
command sets or flips it. A command on one voice changes the sound of every
voice.

Seen in: [Mugician II](../players/MugicianII.md),
[MusicMaker 8V](../players/MusicMaker-8V.md),
[Paul Robotham](../players/PaulRobotham.md),
[SoundPlayer](../players/SoundPlayer.md).

## CIA timer

A CIA timer interrupt runs the tick at any rate. So the score can set a tempo.
Model: `hardware/cia.py:CiaTimer`.

Seen in: [AHX](../players/AbyssHighestExperience.md),
[Art Of Noise 8V](../players/ArtOfNoise-8V.md),
[Face The Music](../players/FaceTheMusic.md),
[MIDI-Loriciel](../players/MIDI-Loriciel.md),
[Sonic Arranger](../players/SonicArranger.md),
[Sonix Music Driver](../players/SonixMusicDriver.md),
[SoundPlayer](../players/SoundPlayer.md).
