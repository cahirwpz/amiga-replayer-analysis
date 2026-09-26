# Tim Follin volume and pitch control

The equations cover normal value ranges in the replay code. They omit byte
overflow and describe Paula register values, not perceived pitch from changing
waveforms. `table(n)` means a note-to-period lookup. A higher period means a
lower pitch.

For comparison, see [TFMX Pro's controllers](TFMX-Pro-control.md).

The track sets persistent parameters for state machines. There is no instrument
program or independent pitch table walker. `data/annot/TimFollin.yaml:ReadTrack`
`:CmdEnvelope` `:CmdVibrato`

## Volume

The envelope owns one volume byte, `e`. On a due update, attack adds the
configured step; decay subtracts it; hold does nothing. Attack changes phase at
exactly 63.

Decay holds when the previous level equals sustain, or subtraction produces a
negative byte. It does not clamp to the sustain target. `:Envelope`

```text
e_next = e + step     during an attack update
       = e - step     during a decay update
       = e           otherwise

volume = e_next                      if the global cap byte F is zero
       = min(e_next, floor(F / 4))    otherwise
```

Nothing in this player starts the global cap countdown. Its tick routine only
reduces a nonzero value. `:Tick` `:SetVolume`

Subsong 13 has an override: another voice field plus one replaces this result.
Nothing here sets the fields that activate it. `:SetVolume`

A note can reset the envelope after the tick's volume write. That reset reaches
the output on the following tick. Track end instead writes zero directly.
`:PlayNote` `:CmdEnd`

There is no velocity multiplier, tremolo controller or instrument volume
property. The track supplies the envelope's start level, sustain, rates and
restart flag. `:CmdEnvelope` `:CmdEnvelopeStep` `:CmdEnvelopeRestart`

## Pitch

Let `n` be the current note index, `q` its portamento target, and `P` the stored
period. The controllers run before the track reads its next note. `:VoiceTick`
`:NoteTimer`

```text
1. Vibrato, once its delay ends:
     P = P + direction * vibrato_step

2. Trill, only when vibrato is disabled or still delayed:
     on a due step: n = n +/- interval; P = table(n)
     a due trill step skips portamento for this visit

3. Portamento, if not skipped:
     n = move_towards(n, q, semitones_per_tick)
     if n moved: P = table(n)

4. A track note, if due:
     q = note + transpose                 if portamento is enabled
     n = note + transpose                 otherwise
     P = table(n)
```

The one-note no-transpose command bypasses that addition. `:PlayNote`

Vibrato adds in period units, not semitones. A portamento step replaces that
changed period with a fresh lookup. Portamento therefore suppresses vibrato's
output while moving. After the target is reached, it stops rewriting the period.
`:Vibrato` `:Portamento`

Trill changes the stored note index, not a separate offset. Ordinary track notes
can also express an arpeggio; there is no separate arpeggio stream. `:Trill`
`:PlayNote`
