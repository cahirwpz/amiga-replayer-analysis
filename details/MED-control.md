# MED instrument control

This review covers the four-channel replay source, version 7.0, used by the
[MED card](../players/MED.md). It traces control behavior, without testing song
modules. Labels below belong to `data/annot/MED.yaml`.

## Control structures

Two command lists coordinate several smaller processes. Their positions and
working state belong to each voice.

| Structure       | Form                                                            | Advances                         | Evidence                                          |
| --------------- | --------------------------------------------------------------- | -------------------------------- | ------------------------------------------------- |
| Volume list     | Commands: values, waits, jumps, setters                         | At its own execution interval    | `data/annot/MED.yaml:SynthTick`, `:VolumeOpcodes` |
| Wave list       | Commands: waveform choices, waits, jumps, setters               | At its own execution interval    | `:WaveListTick`, `:WaveOpcodes`                   |
| Volume envelope | Waveform read as 128 volume values; once or looping             | Each volume-list activation      | `:VolEnvelopeStep`, `:VolEnvOnce`, `:VolEnvLoop`  |
| Synth arpeggio  | Inline note-offset list, looping                                | Every tick                       | `:ArpeggioStart`, `:SynthArpeggio`                |
| Synth vibrato   | Table-driven oscillator; default sine or an instrument waveform | Every tick when depth is nonzero | `:VibratoWave`, `:SynthVibrato`                   |
| Volume slide    | Arithmetic accumulator, clamped to 0–64                         | Each volume-list activation      | `:SynthTick`                                      |
| Pitch slide     | Accumulated period offset                                       | Each wave-list activation        | `:WaveListTick`                                   |

The command lists have jumps but no conditional branches or calls. Their
`commands` classification fits the repository vocabulary. The envelope has its
own pointer, count, and restart address. It is an additional stream missing from
the card. `:VolumeOpcodes`, `:WaveOpcodes`, `:VolEnvelopeStep`.

## Timing and jumps

The volume list runs before the wave list. Each has both an execution counter
and a wait counter. Waits count list activations, not raw ticks. Speed commands
change the reload value; the current execution counter has already been loaded.
`:SynthTick`, `:VolSpeed`, `:VolWait`, `:WaveSpeed`, `:WaveWait`.

Slides and envelope playback run before the wait check. End commands retain the
list position while these processes continue. Arpeggio and vibrato also keep
running when list execution is skipped. `:VolEnvelopeStep`, `:VolListEnd`,
`:WaveListTick`, `:WaveListEnd`, `:SynthArpeggio`.

| Event             | Changes                                                     | Preserves                                         | Earliest destination execution                           |
| ----------------- | ----------------------------------------------------------- | ------------------------------------------------- | -------------------------------------------------------- |
| Volume jumps wave | Wave position; clears wave wait                             | Wave execution counter and modulation state       | Same tick, if wave execution is due                      |
| Wave jumps volume | Volume position; clears volume wait                         | Volume execution counter and envelope state       | A later tick when volume execution is due                |
| Hold expires      | Volume position becomes the decay value; clears volume wait | Execution counter, envelope, slides and wave list | Same tick, if volume execution is due                    |
| Pattern command E | Wave position                                               | Existing wave wait and execution counter          | Normal wave execution boundary, after any remaining wait |

Evidence: `:VolJumpWaveList`, `:WaveJumpVolList`, `:SynthRelease`,
`:CmdWaveListPos`, `:DoFX`.

A cross-list jump redirects command execution without restarting the
destination's clock or generators. This distinction is missing from the card's
interaction table.

## Pitch and volume

The wave list's `$FC` starts an arpeggio from the following bytes. The command
reader skips those bytes and their negative terminator. A separate reader loops
over the offsets every tick. Waveform changes therefore need not follow the
arpeggio's rhythm. `:ArpeggioStart`, `:SynthArpeggio`.

Pattern arpeggio is a second mechanism. It cycles through two offsets and the
base note over three ticks. Its period correction is applied after the synth
arpeggio, vibrato, and slide. The two arpeggios can therefore affect the same
output. `:ArpeggioTick`, `:UpdatePerVol`.

Synth arpeggio replaces the base period used for that tick. Pattern portamento
changes `trk_prevper`, which this replacement bypasses while synth arpeggio is
active. Pattern vibrato still adds its correction afterwards. `:PortamentoTick`,
`:SynthArpeggio`, `:UpdatePerVol`.

On a volume activation, the slide runs first. An active envelope then overwrites
its result. A direct volume-list value can overwrite the envelope result again.
`:SynthTick`, `:VolEnvelopeStep`, `:ReadVolumeList`.

The resulting synth volume scales the track's current note volume; track/master
scaling follows. `:WaveListTick`, `:UpdatePerVol`.

The envelope maps signed waveform bytes to volume values 0–63. It reads 128
bytes. Synth vibrato uses 32 table positions with fractional phase advancement.
Both reuse waveform data, but they traverse it differently. `:VolEnvelopeStep`,
`:SynthVibrato`.

## Note lifecycle

A normal synth note resets list positions, execution counters, waits, arpeggio,
slides, envelope playback, and vibrato state. Command E can preserve the
selected wave-list entry point. The reset does not assign a new synth volume;
the volume list must establish it. `:StartSynthNote`, `:hSn2`.

Synth-to-synth notes keep the hardware channel running while control state
restarts. Hybrid notes use the sample-start path and then initialize the same
list machinery. `:KeepSynthChannel`, `:StartSynthNote`.

Hold counts ticks. Looking ahead to an instrument-only row adds one row's ticks;
a note with portamento command 3 can also extend it. For samples, decay selects
a fade rate. For synths and hybrids, it selects a volume-list release address.
`:PlayRowNotes`, `:ExtendHold`, `:HoldAndFade`, `:SynthRelease`.

Explicit note-off is a hard stop. It clears synth playback and disables the
channel. It does not enter the release address. `:CmdNoteOff`, `:ChannelOff`.
