# Pitch and volume units

These players compute pitch and volume in their own units. They convert to
Paula's period and volume only at the end.

## Log pitch

Pitch is a note number in fine steps, not a period. A log table turns it into
the period.

- [MaxTrax](../players/MaxTrax.md): note, pitch bend, portamento and tuning are
  summed in 1/256 semitones. A table of 257 words maps the sum to the period.
  `specs/maxtrax.py:CalcNote`

## Log volume table

Equal log steps sound like equal changes in loudness. Paula's volume is linear.
A table maps each log step to a Paula volume.

- [Jochen Hippel ST](../players/Jochen_Hippel_ST.md): the emulated sound chip
  has 16 log volume steps. A table maps them to Paula volume.
  `specs/jochen_hippel_st.py:EmuChannel`

## Period scaled vibrato

A vibrato that adds a fixed amount to the period is wider on high notes. Adding
a share of the period gives the same interval on every note.

- [Paul Robotham](../players/PaulRobotham.md): vibrato adds a share of the
  period. `specs/paul_robotham.py:Vibrato`
- [Rob Hubbard](../players/RobHubbard.md): the share is a whole number. On short
  periods, the vibrato gets coarse. `specs/rob_hubbard.py:Vibrato`

## Semitone portamento

Portamento moves the note index, not the period. The pitch steps in whole
semitones and never slides smoothly.

- [Tim Follin](../players/TimFollin.md): a track command sets the voice's
  portamento, as it sets vibrato and trill. `specs/tim_follin.py:Portamento`

## Glide to fit

A portamento computes its rate from the note's length. It then ends exactly as
the note ends.

- [Synth Dream](../players/SynthDream.md): the portamento has no target. It runs
  to the event's end. `specs/synth_dream.py:GlideToFit`

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

- [David Whittaker](../players/DavidWhittaker.md): music keeps writing the
  shadow while a sound effect holds the channel. Paula gets the shadow when the
  effect ends. `specs/david_whittaker.py:Shadow`
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
- MaxTrax steps 1/256 semitone. Synth Dream scales the period in steps of 1/400
  semitone. `specs/synth_dream.py:Glide`
