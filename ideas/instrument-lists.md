# Instrument lists

An instrument carries short lists or tables that the replay steps through during
a note. A few bytes then shape volume, pitch and wave, tick by tick.

## Volume list

A volume list is a command list whose values set the voice's volume.

- [David Whittaker](../players/DavidWhittaker.md): each note restarts it. Every
  note starts with the same volume shape. `specs/david_whittaker.py:NoteOn`
- [Future Composer 1.4](../players/FutureComposer1.4.md): it steps every N
  ticks, with waits and loops. `specs/future_composer_14.py:VolumeListTick`
- [Jochen Hippel ST](../players/Jochen_Hippel_ST.md): it steps every N ticks.
  `specs/jochen_hippel_st.py:VolumeList`
- [MED](../players/MED.md): it steps at its own interval, set in ticks.
  `specs/med.py:SynthTick`
- [Voodoo Supreme Synthesizer](../players/VoodooSupremeSynthesizer.md): an entry
  sets a level, or adds a delta for N ticks.
  `specs/voodoo_supreme_synthesizer.py:VolumeEnvelope`

## Pitch list

A pitch list is a command list whose values set the voice's pitch. It often
picks the waveform too.

- [David Whittaker](../players/DavidWhittaker.md): a note does not restart it. A
  fast arpeggio carries on across short notes. `specs/david_whittaker.py:NoteOn`
- [Future Composer 1.4](../players/FutureComposer1.4.md): its wave command
  starts the sound. A pattern note only turns DMA off.
  `specs/future_composer_14.py:SetWave`
- [Jochen Hippel ST](../players/Jochen_Hippel_ST.md): its values switch the
  voice between noise and tone. `specs/jochen_hippel_st.py:PitchList`
- [Voodoo Supreme Synthesizer](../players/VoodooSupremeSynthesizer.md): an entry
  adds, subtracts or shifts by an octave.
  `specs/voodoo_supreme_synthesizer.py:PeriodTable`

## Wave list

A wave list is a command list whose values pick the voice's waveform.

- [MED](../players/MED.md): one opcode, followed by note offsets, plays a synth
  arpeggio. `specs/med.py:ArpeggioStart`

## Cross-list jumps

One list sets the position of another list of the same instrument.

- [MED](../players/MED.md): the volume list can move the wave list to a new
  position, and back. A jump has no condition. `specs/med.py:VolJumpWaveList`

## Release jump

The list holds its own release part. The end of the note jumps there, with no
pattern data.

- [MED](../players/MED.md): the volume list jumps there when the gate time ends.
  A hard stop skips it. `specs/med.py:SynthRelease`

## Table walkers

A table walker steps through a table: off, once or looping.

- [SoundMon 2.2](../players/SoundMon2.2.md): a synth note runs four walkers,
  each on its own table. They scale the volume, offset the period and edit the
  wave. `specs/soundmon_22.py:RunWalkers`

## Waveform as table

The bytes of a waveform also serve as a table of values.

- [MED](../players/MED.md): a waveform becomes a volume envelope or a vibrato
  shape. `specs/med.py:VolEnvOnce`
- [Mugician II](../players/MugicianII.md): two more waves set the volume and
  offset the period. `specs/mugician_ii.py:VolumeFromWave`
- [Sonic Arranger](../players/SonicArranger.md): a wave effect reads a second
  wave as its morph target. `specs/sonic_arranger.py:Metamorph`
- [SoundMon 2.2](../players/SoundMon2.2.md): waves and walker tables share one
  pool. Any table can be a wave, and any wave a table.
  `specs/soundmon_22.py:StartSynthNote`

## Run-length tables

Each table entry is a run that can repeat.

- [Synth Dream](../players/SynthDream.md): a run is a count, a repeat number,
  then the values. Every event, a note or a rest, restarts the voice's four
  tables. `specs/synth_dream.py:Runs`

## Performance list

One instrument program sets the wave, the note and commands at each step.

- [AHX](../players/AbyssHighestExperience.md): a step also runs two commands.
  `specs/abyss_highest_experience.py:PerformanceStep`

## Arpeggio tables

A cell picks a stored table of note offsets.

- [Art Of Noise 8V](../players/ArtOfNoise-8V.md): spare bits pick one of 16
  tables of up to 7 offsets. `specs/art_of_noise_8v.py:PickArpeggio`

## Sample envelope

The envelope follows the sample position, not the tick.

- [MusicMaker 8V](../players/MusicMaker-8V.md): one entry covers 40 sample
  bytes. A high note runs through the envelope faster (inference).
  `specs/music_maker_8v.py:HullVolume`

## Sustain rows

The pattern, not the instrument, holds the sustain.

- [Sonic Arranger](../players/SonicArranger.md): `HOLD` stops the volume table
  at its sustain point. Any other row starts the release.
  `specs/sonic_arranger.py:AdsrSustain`

## Note cut

A note cut ends a note at a set tick, before the next note.

- [AHX](../players/AbyssHighestExperience.md): the replay reads the next row
  early to cut the note. An instrument flag turns the cut into a release.
  `specs/abyss_highest_experience.py:HardCut`

## Compared

- The release lives in the list on MED and in the pattern on Sonic Arranger.
