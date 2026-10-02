# Voice mixing

Software mixing plays more voices than Paula's four channels. The CPU adds
several voices into a buffer, and one channel plays it.

## Voice mixing

A mixer reads each voice's sample at the voice's own pitch. It writes the sum of
the bytes to a buffer, at the mix rate. It must keep the sum within one byte and
apply each voice's volume.

- [Mugician II](../players/MugicianII.md): voices 3–6 are mixed into channel 0.
  The user sets the mix rate. `specs/mugician_ii.py:MixVoices`
  - A table read applies each voice's volume.
  - A second table read clips the sum to one byte.
- [TFMX 7V](../players/TFMX-7V.md): voices 4–7 are mixed into channel 3. Tables
  clip the sum, as on Mugician II. `specs/tfmx_7v.py:FakeChannel`
  - Each mixed voice writes a shadow, so the instrument programs run unchanged.
  - Channel 3's audio interrupt runs the whole replay.
- [Art Of Noise 8V](../players/ArtOfNoise-8V.md): each channel plays two voices.
  The mix rate is fixed at about 14.2 kHz. `specs/art_of_noise_8v.py:MixPair`
  - Each byte is multiplied by its voice's volume / 128 before the add.
- [Musicline Editor](../players/MusiclineEditor.md): in 8-channel mode, voices n
  and n + 4 share channel n. `specs/musicline.py:Play8Channels`
  - `MIX_PERIOD` fixes the mix rate.
  - A volume table halves each voice.
- [Oktalyzer](../players/Oktalyzer.md): the song marks each channel single or
  mixed. `specs/oktalyzer.py:PickHigher`
  - Samples for mixed tracks hold 7 bits, so two of them never overflow.
  - Both tracks of a mixed channel share one volume.
  - Replay 2 plays the buffer at the higher note's period. It resamples only the
    lower track.
- [MusicMaker 8V](../players/MusicMaker-8V.md): the replay halves every sample
  byte at load. `specs/music_maker_8v.py:VolumeTable`
  - The louder voice sets the channel volume.
  - A table scales the quieter voice by the ratio of the two volumes.
  - The channel plays at the higher voice's period.
- [Face The Music](../players/FaceTheMusic.md): two tracks share each channel.
  `specs/face_the_music.py:MixPair`
  - Only the quieter track goes through a volume table.
  - Nothing clips the sum, so a loud pair wraps around.

## Mixer code written at run time

A mixer's inner loop steps through a sample by a fraction per output byte. Code
written for one pair of periods needs no step arithmetic at run time.

- [MusicMaker 8V](../players/MusicMaker-8V.md): on a 68000, the fast mixer
  writes its own step instructions. It writes them for each pair of periods.
  `specs/music_maker_8v.py:PickMixer`
  - From the 68020 on, every channel uses the slow mixer instead.

## Chunk pitch shift

The audio interrupt plays a long sample in short chunks. Between chunks, the
replay moves its read pointer by its own step. Pitch and playback speed then
change independently.

- [Voodoo Supreme Synthesizer](../players/VoodooSupremeSynthesizer.md): each
  chunk is 128 bytes. `specs/voodoo_supreme_synthesizer.py:ChunkStep`
  - The step can be 128 × period ÷ the base note's period.
  - Then the sample moves at the base note's speed at every pitch.
  - It costs one audio interrupt per chunk and voice.

## Compared

- Volume: Mugician II, TFMX 7V and Art Of Noise 8V scale every voice. Oktalyzer
  gives a pair one volume. MusicMaker 8V and Face The Music scale the quieter
  voice only.
- Overflow: Mugician II and TFMX 7V clip the sum. Oktalyzer and MusicMaker 8V
  halve the samples first. Face The Music lets the sum wrap around.
- Mix rate: three players play at the higher note's period. That voice needs no
  resampling. They are Oktalyzer's replay 2, MusicMaker 8V and Face The Music.
- CPU: Mugician II needs 272 cycles per mixed byte, and TFMX 7V 268. Wanted
  Team's versions need 211 and 254. Both counts come from the source comments.
