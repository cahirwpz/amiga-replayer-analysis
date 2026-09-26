# TFMX Pro volume and pitch control

The equations cover normal value ranges in the replay code. They omit byte
overflow and describe Paula register values, not perceived pitch from changing
waveforms. `table(n)` means a note-to-period lookup. A higher period means a
lower pitch.

For comparison, see [Tim Follin's controllers](TimFollin-control.md).

The macro is a program. Vibrato, portamento and envelope are state machines. The
pitch riff is a separate table walker. `data/annot/TFMX-Pro.yaml:RunMacro`
`:Vibrato` `:Portamento` `:Envelope` `:RiffPlay`

## Volume

The macro and envelope share one mutable volume byte, `v`. The pattern's note
volume, `b`, is 0–15. `:NoteToVoice`

```text
Macro volume commands:
  v = absolute_volume
  v = 3 * b + argument          for the relative-to-note-volume command

Envelope, on a due update:
  v = move_towards(v, target, envelope_step)

Fade output:
  core_volume = floor(v * F / 64)    for an ordinary music voice with F < 64
              = v                  when fade is bypassed

Host wrapper:
  H = floor(master_volume * side_balance / 64)
  output_volume = enabled * floor((core_volume & 127) * H / 64)
```

The relative command starts from note volume, not current volume. Envelope
phases need macro commands that set new targets. There is no automatic
four-phase envelope. `:maddvolume` `:msetvolume` `:menvelope` `:Envelope`

Fade is bypassed when its byte has bit 6 set, or the voice's priority countdown
is nonnegative. The shared fade counter advances once per voice visit, not once
per tick. Four visits can therefore apply different fade levels within one tick.
`:VoicesTick` `:Fade`

The wrapper applies master volume, side balance and voice muting after the core
fade. `:SetVolume` `:ChangeVolume`

A riff echo replaces another voice's volume with `floor(5 * v / 8)`. Its effect
depends on whether that voice has already run this tick. `:RiffEcho`

## Pitch

The macro normally computes a base period, `B`:

```text
n = (selected_note + macro_note_offset) & 63
B = floor(table(n) * (256 + pattern_detune + macro_detune) / 256)
```

The selected note can be the current note, previous note or zero for an absolute
note. A macro can instead set `B` directly. `:mputnote` `:msetperiod`

There is no single additive pitch equation. The ordered writes are:

```text
1. Macro pitch command:
     set B
     if portamento is inactive: P = B

2. Vibrato:
     h = h + signed_rate
     if portamento is inactive: P = floor(B * (2048 + h) / 2048)

3. Portamento, on a due update:
     G = floor(G * (256 + c) / 256)    if G < B
     G = floor(G * (256 - c) / 256)    if G > B
     stop at B when the step reaches or crosses it
     P = G & 2047

4. Riff, when it emits a note:
     B = floor(table((note + riff_offset) & 63) * (256 + pattern_detune) / 256)
     if portamento is inactive: P = B
```

`h` is vibrato's accumulated period factor. `G` is portamento's current period.
`c` is its step factor. Both effects have direction or timing state. `:Vibrato`
`:Portamento`

Vibrato state keeps advancing during portamento, but writes no period.
Portamento is proportional in period space, unlike Tim Follin's semitone steps.
`:Vibrato` `:Portamento`

A riff period can replace vibrato on its note ticks. During portamento, the
ordinary riff updates its target but does not advance past that note. The random
riff path can still advance its step. `:RiffPlay` `:RiffRandom`

Modulation can be paused by the macro's DMA-on setting. A stopped macro does not
itself stop these controllers. `:mdmaon` `:modulations` `:mstop`

These are the normal per-voice paths. Macro chip-register writes can bypass
them. The adapted DMA-off handler also contains an extra volume write.
`:WriteChipReg` `:mdmaoff`
