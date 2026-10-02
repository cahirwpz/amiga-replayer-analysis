# Pitch and volume units

These players compute pitch and volume in their own units. They convert to
Paula's period and volume only at the end.

## Log pitch

Pitch is a note number in fine steps, not a period. A log table turns it into
the period.

- [MaxTrax](../players/MaxTrax.md): note, pitch bend, portamento and tuning add
  up in 1/256 semitones. A table of 257 words gives the period.
  `specs/maxtrax.py:CalcNote`

## Log volume table

A volume in log steps sounds even across its range. A table maps each step to
Paula's linear volume.

- [Jochen Hippel ST](../players/Jochen_Hippel_ST.md): a table maps the sound
  chip's 16 log volume steps to Paula volume.
  `specs/jochen_hippel_st.py:EmuChannel`

## Period scaled vibrato

A vibrato that adds a fixed amount to the period is wider on low notes. Adding a
share of the period gives the same interval on every note.

- [Paul Robotham](../players/PaulRobotham.md): vibrato adds a share of the
  period. `specs/paul_robotham.py:Vibrato`
- [Rob Hubbard](../players/RobHubbard.md): the share is a whole number. On short
  periods, the vibrato gets coarse. `specs/rob_hubbard.py:Vibrato`

## Semitone portamento

Portamento moves the note index, not the period. Each step is a whole semitone.

- [Tim Follin](../players/TimFollin.md): portamento is a voice setting from the
  track, like vibrato and trill. `specs/tim_follin.py:Portamento`

## Glide to fit

A portamento computes its rate from the note's length. It then ends exactly as
the note ends.

- [Synth Dream](../players/SynthDream.md): each glide step is a ratio of 1/400
  semitone. `specs/synth_dream.py:GlideToFit`

## Instrument transpose

The song's position list shifts instrument numbers, as it shifts notes. One
pattern can then play with other sounds.

- [Future Composer 1.4](../players/FutureComposer1.4.md): each position
  transposes notes and instrument numbers, per voice.
  `specs/future_composer_14.py:AddInstrTranspose`

## Fixed pitch instruments

The instrument sets the period. A row names only an instrument.

- [Digital Sonix & Chrome](../players/DigitalSonixChrome.md): every pitch of a
  sound takes its own instrument. `specs/digital_sonix_chrome.py:SetFixedPeriod`

## Register shadow

The replay writes a channel's registers to a [shadow](../docs/glossary.md).
Paula gets the shadow later.

- [David Whittaker](../players/DavidWhittaker.md): music writes the shadow while
  a sound effect holds the channel. When the effect ends, the music's note
  sounds on. `specs/david_whittaker.py:Shadow`
- [Jochen Hippel ST](../players/Jochen_Hippel_ST.md): the replay writes a sound
  chip's registers to the shadow. An emulator turns them into Paula writes.
  `specs/jochen_hippel_st.py:Play`

## Sample rate tune

Each sample stores its recording rate. The replay scales the period by it, so a
sample at any rate plays in tune.

- [David Whittaker](../players/DavidWhittaker.md): the tune is the NTSC clock
  divided by the recording rate. `specs/david_whittaker.py:InitSamples`
- [Rob Hubbard](../players/RobHubbard.md): each sample's tune is 3579545 divided
  by its rate. `specs/rob_hubbard.py:InitSamples`

## Compared

- Vibrato depth: Paul Robotham and Rob Hubbard scale it with the period. Future
  Composer 1.4 doubles it for each octave down.
  `specs/future_composer_14.py:VibratoTick`
- Tim Follin's pitch moves by whole semitones. `specs/tim_follin.py:Portamento`
- MaxTrax steps 1/256 semitone. Synth Dream steps 1/400 semitone.
  `specs/synth_dream.py:Glide`
