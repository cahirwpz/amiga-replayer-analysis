"""Fred Editor's replay, from Fuzzball (1991). The replay ships inside
each module; this model reads data/module/Fred/fred.ingame1. The three
Fuzzball modules share the same 2 kB of replay code and tables.

Card: players/Fred.md. Level 2: the control flow runs. Each CamelCase
function is a LABEL in data/disasm/Fred.cnf; each CamelCase class is in
the `types:` of data/annot/Fred.yaml.

The module starts with four `jmp`: InitSong, Play, StopSong and
StartFade. Tracks, songs and speeds follow the code; patterns,
instruments and samples come after them.

Each voice has its own track: a list of pattern offsets. A pattern is a
byte stream: a note lasts one row, and a wait byte adds rows. An
instrument is a sample or a 64-byte wave that the replay builds in the
voice's own buffer. A pulse instrument writes one byte per step, so the
edge of a square wave moves between two positions. A morph instrument
adds a scaled table of deltas to a 32-byte wave, so the wave morphs
back and forth. Each note restarts a timed ADSR, an arpeggio table and a
delayed vibrato.

The period table is David Whittaker's, byte for byte, and Vibrato takes
the same steps as his (see specs/david_whittaker.py).

Left out: the host's timer; DeliTracker calls Play once per tick.
"""

from dataclasses import dataclass, field

from hardware import paula
from hardware.amiga import DEFAULT_LATCH, Amiga

VOICES = 4
TUNE_SHIFT = 10  # period = table × tune >> 10
INSTRUMENT_SIZE = 64
VOICE_SIZE = 128
WAVE = 64  # the voice's wave buffer: 64 bytes at offset 64
MORPH_BYTES = 32  # a morph wave: 32 bytes, then 32 words of deltas
SILENT_WORDS = 50  # SilentWords
FADE_START = 0x1000  # FadeVolume at InitSong: full volume
NOTE_MAX = 0x7F
GAP_LIMIT = 0xA0  # CountDown: next bytes from here on, taken as signed, keep DMA on

# Stream commands; bytes above REST are waits
PATTERN_END, PORTAMENTO, SPEED, INSTRUMENT, REST = range(0x80, 0x85)
TRACK_END = 0xFFFF  # a track word: the song ends
TRACK_JUMP = 0x8000  # a track word with this bit: go to the position below it

# Instrument kinds; a morph is a `blend` in Fred Editor
SAMPLE, PULSE, MORPH = 0, 1, 2

# Restart flags, a byte of the instrument (`synchro` in Fred Editor)
PULSE_COUNTED = 1 << 0  # the pulse stops after `pulse_turns` turns
PULSE_RESTART = 1 << 1  # each note restarts the pulse
MORPH_COUNTED = 1 << 2  # the morph stops after `morph_turns` turns
MORPH_RESTART = 1 << 3  # each note restarts the morph

# Envelope phases
ATTACK, DECAY, SUSTAIN, RELEASE, DONE = range(5)


# --- Player state ------------------------------------------------------


@dataclass
class Instrument:  # InstrumentsAt: 64 bytes each
    start: int = 0  # 0: bytes into the module
    loop: int = 0  # 4: added in bytes; 0: silence after one pass; <0: all of it loops
    length: int = 0  # 6: words
    tune: int = 0  # 8: period factor, in 1024ths
    vibrato_delay: int = 0  # 10: ticks
    vibrato_speed: int = 0  # 12
    vibrato_depth: int = 0  # 13
    level: int = 0  # 14: scales the envelope
    attack_speed: int = 0  # 15
    attack_level: int = 0  # 16
    decay_speed: int = 0  # 17
    decay_level: int = 0  # 18
    sustain_ticks: int = 0  # 19
    release_speed: int = 0  # 20
    release_level: int = 0  # 21
    arpeggio: bytes = bytes(16)  # 22: signed note offsets
    arpeggio_speed: int = 0  # 38: ticks per step
    kind: int = SAMPLE  # 39
    pulse_low: int = 0  # 40: the byte below the edge
    pulse_high: int = 0  # 41: the byte above the edge
    pulse_speed: int = 0  # 42: ticks per step
    pulse_from: int = 0  # 43: the edge's lowest position
    pulse_to: int = 0  # 44: its highest position
    pulse_delay: int = 0  # 45: ticks
    flags: int = 0  # 46: restart flags
    morph_shift: int = 0  # 47: the morph has 1 << shift steps
    morph_delay: int = 0  # 48: ticks
    pulse_turns: int = 0  # 49
    morph_turns: int = 0  # 50
    arpeggio_length: int = 0  # 51


@dataclass
class Voice:  # Voices: 128 bytes each
    channel: paula.Channel
    track: int = 0  # 0: bytes into the module
    pos: int = 0  # 8: the stream
    instrument: Instrument = field(default_factory=Instrument)  # 12
    vibrato_delay: int = 0  # 16
    vibrato_speed: int = 0  # 18
    vibrato_depth: int = 0  # 19
    vibrato_value: int = 0  # 20
    portamento_on: bool = False  # 21
    portamento_delay: int = 0  # 22: ticks
    note: int = 0  # 25
    target_period: int = 0  # 26
    period: int = 0  # 28: after arpeggio and portamento
    looped: bool = True  # 30: QueueLoop ran for this note
    ticks: int = 1  # 32
    vibrato_growing: bool = True  # 34, bit 7
    vibrato_adding: bool = True  # 34, bit 0
    target_note: int = 0  # 35
    start_period: int = 0  # 36: 0 until the glide's note starts
    delta: int = 0  # 38: target period - start period
    step: int = 0  # 40
    duration: int = 0  # 42: ticks
    volume: int = 0  # 44
    phase: int = ATTACK  # 45
    sustain: int = 0  # 46: ticks
    arpeggio_pos: int = 0  # 47
    arpeggio_ticks: int = 0  # 48
    pulse_pos: int = 0  # 49
    pulse_delay: int = 0  # 50
    pulse_down: bool = False  # 51, bit 2
    pulse_ticks: int = 0  # 52
    morph_step: int = 1  # 54
    morph_down: bool = False  # 56
    morph_delay: int = 0  # 57
    position: int = 0  # 58: bytes into the track
    pulse_turns: int = 0  # 60
    morph_turns: int = 0  # 61
    wave: bytearray = field(default_factory=lambda: bytearray(WAVE))  # 64


@dataclass
class Module:  # the module is the replay: code, tables, songs and samples
    amiga: Amiga
    data: bytearray
    # offsets of the labels in data/disasm/Fred.cnf; the same in all three modules
    voice_mask: int = 0x10  # VoiceMask: a bit per voice that may start notes
    period_table: int = 0x804  # PeriodTable: from 8192 down, a word per note
    last_song: int = 0x895  # LastSong
    song_speeds: int = 0x897  # SongSpeeds
    instruments_at: int = 0x8A2  # InstrumentsAt: a long offset to them
    patterns_at: int = 0x8A6  # PatternsAt: a long offset to them
    tracks: int = 0xB0E  # Tracks: per song, a word per voice
    voices: list[Voice] = field(default_factory=list)
    silent: paula.Sample = paula.Sample(bytes(2 * SILENT_WORDS))  # SilentWords
    stopped: bool = True  # Stopped
    fading: bool = False  # Fading
    fade_volume: int = FADE_START  # FadeVolume
    fade_speed: int = 0  # FadeSpeed
    song: int = 0  # Song
    speed: int = 6  # Speed: ticks per row


# --- Start -------------------------------------------------------------


def new_module(module: Module, song: int) -> Module:
    """DeliTracker calls Play by its own timer."""
    module.voices = [Voice(c) for c in module.amiga.paula.channels]
    InitSong(module, song)
    module.amiga.timer.on_underflow = lambda: Play(module)
    module.amiga.timer.set_latch(DEFAULT_LATCH)
    return module


def InitSong(module: Module, song: int) -> None:
    """d0: the song. Past LastSong it stops. Each voice starts at its
    track's first pattern."""
    data = module.data
    if song > data[module.last_song]:
        StopSong(module)
        return
    module.song = song
    module.speed = data[module.song_speeds + song]
    patterns = long(data, module.patterns_at)
    for n, voice in enumerate(module.voices):
        voice.ticks, voice.position, voice.looped = 1, 0, True
        voice.track = module.tracks + word(data, module.tracks + 8 * song + 2 * n)
        voice.pos = patterns + word(data, voice.track)
    module.stopped, module.fading = False, False
    module.fade_volume = FADE_START


def StartFade(module: Module, speed: int) -> None:
    """d0: subtracted from FadeVolume each time Volume runs."""
    module.fade_speed = speed & 0xFF
    module.fading = True


def StopSong(module: Module) -> None:
    module.stopped = True
    for voice in module.voices:
        voice.channel.disable()


# --- Tick --------------------------------------------------------------


def Play(module: Module) -> None:
    """Voices 3 down to 0. SongEnd and the end of a fade return at once."""
    if module.stopped:
        return
    for voice in reversed(module.voices):
        if not VoiceTick(module, voice):
            return


def VoiceTick(module: Module, voice: Voice) -> bool:
    """False: the song stopped. Returns here after each pattern end."""
    while True:
        QueueLoop(module, voice)
        outcome = CountDown(module, voice)
        if outcome == "next position":
            if not NextPosition(module, voice):
                return False
            continue
        if outcome == "effects":
            return Arpeggio(module, voice)
        return True


def QueueLoop(module: Module, voice: Voice) -> None:
    """The tick after a note: the loop from its offset, or silence, or
    nothing, so the whole sample loops. The offset is added in bytes but
    taken from the length in words. A wave instrument loops its buffer
    from the start."""
    if voice.looped:
        return
    voice.looped = True
    instrument = voice.instrument
    if not instrument.loop:
        voice.channel.queue(module.silent)
    elif instrument.loop > 0:
        words = instrument.length - instrument.loop
        if instrument.kind != SAMPLE:
            voice.channel.queue(paula.Sample(voice.wave, 0, words))
        else:
            voice.channel.queue(chip(module, instrument.start + instrument.loop, words))


def CountDown(module: Module, voice: Voice) -> str:
    """At 0, the next event. One tick before, DMA goes off, unless the
    next byte is a wait: a wait after a note ties it. The compare is
    signed, so notes below 32 also keep DMA on."""
    voice.ticks -= 1
    if not voice.ticks:
        return ReadStream(module, voice)
    if voice.ticks == 1 and not keeps_dma(module.data[voice.pos]):
        voice.channel.disable()
    return "effects"


def ReadStream(module: Module, voice: Voice) -> str:
    """Commands until a note, a wait, REST or the pattern's end. An
    INSTRUMENT command before a note restarts its pulse or morph."""
    data = module.data
    changed = False
    while True:
        byte = data[voice.pos]
        voice.pos += 1
        if byte <= NOTE_MAX:
            NoteOn(module, voice, byte, changed)
            return StartDma(module, voice)
        if byte == INSTRUMENT:
            SetInstrument(module, voice)
            changed = True
        elif byte == SPEED:
            SetSpeed(module, voice)
        elif byte == PORTAMENTO:
            SetPortamento(module, voice)
        elif byte == REST:
            Rest(module, voice)
            return "next voice"
        elif byte == PATTERN_END:
            return "next position"
        else:
            voice.ticks = (-byte & 0xFF) * module.speed
            return "effects"


def SetInstrument(module: Module, voice: Voice) -> None:
    number = module.data[voice.pos]
    voice.pos += 1
    at = long(module.data, module.instruments_at) + INSTRUMENT_SIZE * number
    voice.instrument = read_instrument(module.data, at)


def SetSpeed(module: Module, voice: Voice) -> None:
    """Ticks per row, for all voices."""
    module.speed = module.data[voice.pos]
    voice.pos += 1


def SetPortamento(module: Module, voice: Voice) -> None:
    """Three bytes: the glide's length in rows, the target note and a
    delay in rows. The next note glides from its own period to the
    target's, in a straight line."""
    data = module.data
    voice.duration = data[voice.pos] * module.speed
    voice.target_note = data[voice.pos + 1]
    voice.target_period = note_period(module, voice.instrument, voice.target_note)
    voice.start_period = 0
    voice.portamento_delay = data[voice.pos + 2] * module.speed
    voice.portamento_on = True
    voice.pos += 3


def Rest(module: Module, voice: Voice) -> None:
    """REST: DMA off for one row. Effects skip this tick."""
    voice.channel.disable()
    voice.ticks = module.speed
    voice.looped = True


def NextPosition(module: Module, voice: Voice) -> bool:
    """The next word of the voice's track: a pattern offset, a jump to
    a position in the track, or TRACK_END. False: the song ended."""
    data = module.data
    at = voice.position + 2
    while True:
        value = word(data, voice.track + at)
        if value == TRACK_END:
            SongEnd(module)
            return False
        if not value & TRACK_JUMP:
            break
        at = value & ~TRACK_JUMP
    voice.position = at
    voice.pos = long(data, module.patterns_at) + value
    voice.ticks = 1
    return True


def SongEnd(module: Module) -> None:
    """All volumes to 0 and DMA off. The song does not loop by itself;
    a track loops with a jump."""
    module.stopped = True
    for voice in module.voices:
        voice.channel.set_volume(0)
        voice.channel.disable()


def NoteOn(module: Module, voice: Voice, note: int, changed: bool) -> None:
    """The note lasts one row; wait bytes after it add rows. It restarts
    the arpeggio, vibrato and envelope. The volume starts at 0."""
    instrument = voice.instrument
    voice.note = note
    voice.arpeggio_pos, voice.arpeggio_ticks = 0, instrument.arpeggio_speed
    voice.vibrato_delay = instrument.vibrato_delay
    voice.vibrato_speed = instrument.vibrato_speed
    voice.vibrato_depth = instrument.vibrato_depth
    voice.vibrato_growing = voice.vibrato_adding = True
    voice.vibrato_value = 0
    if instrument.kind == PULSE and (changed or instrument.flags & PULSE_RESTART):
        PulseInit(voice)
    elif instrument.kind == MORPH and (changed or instrument.flags & MORPH_RESTART):
        MorphInit(module, voice)
    voice.ticks = module.speed
    if instrument.kind != SAMPLE:
        voice.channel.queue(paula.Sample(voice.wave, 0, instrument.length))
    else:
        voice.channel.queue(chip(module, instrument.start, instrument.length))
    voice.volume, voice.phase = 0, ATTACK
    voice.channel.set_volume(0)
    voice.sustain = instrument.sustain_ticks
    voice.period = note_period(module, instrument, note)
    voice.channel.period = voice.period
    if voice.portamento_on and not voice.start_period:
        voice.delta = voice.target_period - voice.period
        voice.step, voice.start_period = 1, voice.period


def StartDma(module: Module, voice: Voice) -> str:
    """VoiceMask keeps a voice silent; then effects skip the note's tick."""
    if not module.data[module.voice_mask] >> voice.channel.number & 1:
        return "next voice"
    voice.channel.enable()
    voice.looped = False
    return "effects"


def Arpeggio(module: Module, voice: Voice) -> bool:
    """Effects run only while the channel's DMA is on: the replay reads
    DMACONR. The note plus the arpeggio offset sets the period; the
    table steps every `arpeggio_speed` ticks and wraps at its length."""
    if not voice.channel.dma:
        return True
    instrument = voice.instrument
    note = (voice.note + instrument.arpeggio[voice.arpeggio_pos]) & 0xFF
    voice.arpeggio_ticks = (voice.arpeggio_ticks - 1) & 0xFF
    if not voice.arpeggio_ticks:
        voice.arpeggio_ticks = instrument.arpeggio_speed
        voice.arpeggio_pos += 1
        if voice.arpeggio_pos == instrument.arpeggio_length:
            voice.arpeggio_pos = 0
    voice.period = note_period(module, instrument, note)
    Portamento(voice)
    Vibrato(voice)
    Envelope(voice)
    if not Volume(module, voice):
        return False
    Synth(module, voice)
    return True


def Portamento(voice: Voice) -> None:
    """After the delay: period + step × delta / duration. So the glide
    rides on top of the arpeggio. At its end, the note becomes the
    target note."""
    if not voice.portamento_on:
        return
    if voice.portamento_delay:
        voice.portamento_delay -= 1
        return
    voice.period += int(voice.step * voice.delta / voice.duration)
    voice.step += 1
    if voice.step > voice.duration:
        voice.note = voice.target_note
        voice.portamento_on = False


def Vibrato(voice: Voice) -> None:
    """After a delay, a triangle: the offset grows by `speed` to the
    depth, falls to 0, then does the same below the note. The offset is
    in period units, so its interval depends on the note."""
    period = voice.period
    if voice.vibrato_delay:
        voice.vibrato_delay -= 1
    else:
        if voice.vibrato_growing:
            voice.vibrato_value = (voice.vibrato_value + voice.vibrato_speed) & 0xFF
            if voice.vibrato_value == voice.vibrato_depth:
                voice.vibrato_growing = False
        else:
            voice.vibrato_value = (voice.vibrato_value - voice.vibrato_speed) & 0xFF
            if not voice.vibrato_value:
                voice.vibrato_growing = True
        if not voice.vibrato_value:
            voice.vibrato_adding = not voice.vibrato_adding
        value = signed_byte(voice.vibrato_value)
        period += value if voice.vibrato_adding else -value
    voice.channel.period = period & 0xFFFF


def Envelope(voice: Voice) -> None:
    """A timed ADSR: sustain lasts a fixed number of ticks, then the
    release starts. The note's length does not end the sustain."""
    if voice.phase == ATTACK:
        Attack(voice)
    elif voice.phase == DECAY:
        Decay(voice)
    elif voice.phase == SUSTAIN:
        Sustain(voice)
    elif voice.phase == RELEASE:
        Release(voice)


def Attack(voice: Voice) -> None:
    """The sum is compared as a word, so a large speed cannot wrap."""
    instrument = voice.instrument
    volume = voice.volume + instrument.attack_speed  # a word: no wrap
    voice.volume = volume & 0xFF
    if volume >= instrument.attack_level:
        voice.volume, voice.phase = instrument.attack_level, DECAY


def Decay(voice: Voice) -> None:
    instrument = voice.instrument
    volume = voice.volume - instrument.decay_speed
    voice.volume = volume & 0xFF
    if volume <= instrument.decay_level:
        voice.volume, voice.phase = instrument.decay_level, SUSTAIN


def Sustain(voice: Voice) -> None:
    if not voice.sustain:
        voice.phase = RELEASE
    else:
        voice.sustain -= 1


def Release(voice: Voice) -> None:
    instrument = voice.instrument
    volume = voice.volume - instrument.release_speed
    voice.volume = volume & 0xFF
    if volume <= instrument.release_level:
        voice.volume, voice.phase = instrument.release_level, DONE


def Volume(module: Module, voice: Voice) -> bool:
    """volume × (level × fade >> 12) >> 9. During a fade, each voice
    that runs its effects lowers FadeVolume, so four playing voices fade
    four times as fast. At 0 the song stops: False."""
    if module.fading:
        module.fade_volume -= module.fade_speed
        if module.fade_volume < 0:
            module.fade_volume = 0
            module.stopped = True
            return False
    scale = voice.instrument.level * module.fade_volume >> 12
    voice.channel.set_volume(voice.volume * scale >> 9)
    return True


def Synth(module: Module, voice: Voice) -> None:
    kind = voice.instrument.kind
    if kind == SAMPLE:
        return
    if kind == MORPH:
        Morph(module, voice)
    else:
        Pulse(voice)


def Pulse(voice: Voice) -> None:
    """After the delay, one step every `pulse_speed` ticks. With
    PULSE_COUNTED, it stops after `pulse_turns` turns."""
    if voice.pulse_delay:
        voice.pulse_delay -= 1
        return
    if voice.pulse_ticks:
        voice.pulse_ticks -= 1
        return
    instrument = voice.instrument
    if instrument.flags & PULSE_COUNTED and not voice.pulse_turns:
        return
    voice.pulse_ticks = instrument.pulse_speed
    if voice.pulse_down:
        PulseDown(voice)
    else:
        PulseUp(voice)


def PulseUp(voice: Voice) -> None:
    """Writes the low byte at the edge and moves it up. Past `pulse_to`
    it turns."""
    instrument = voice.instrument
    if voice.pulse_pos <= instrument.pulse_to:
        voice.wave[voice.pulse_pos] = instrument.pulse_low
        voice.pulse_pos += 1
        return
    voice.pulse_down = True
    voice.pulse_turns = (voice.pulse_turns - 1) & 0xFF
    voice.pulse_pos -= 1
    PulseDown(voice)


def PulseDown(voice: Voice) -> None:
    """Writes the high byte at the edge and moves it down. Below
    `pulse_from` it turns."""
    instrument = voice.instrument
    if voice.pulse_pos >= instrument.pulse_from:
        voice.wave[voice.pulse_pos] = instrument.pulse_high
        voice.pulse_pos -= 1
        return
    voice.pulse_down = False
    voice.pulse_turns = (voice.pulse_turns - 1) & 0xFF
    voice.pulse_pos += 1
    PulseUp(voice)


def Morph(module: Module, voice: Voice) -> None:
    """After the delay, one step every tick."""
    if voice.morph_delay:
        voice.morph_delay -= 1
        return
    MorphStep(module, voice)


def MorphStep(module: Module, voice: Voice) -> None:
    """The step walks from 1 to 1 << shift and back. At each end it
    turns. With MORPH_COUNTED, it stops after `morph_turns` turns."""
    instrument = voice.instrument
    while True:
        if instrument.flags & MORPH_COUNTED and not voice.morph_turns:
            return
        top = 1 << instrument.morph_shift
        end = 1 if voice.morph_down else top
        if voice.morph_step != end:
            break
        voice.morph_down = not voice.morph_down
        voice.morph_turns = (voice.morph_turns - 1) & 0xFF
    voice.morph_step += -1 if voice.morph_down else 1
    MorphWrite(module, voice)


def MorphWrite(module: Module, voice: Voice) -> None:
    """wave[i] = source[i] + step × delta[i] >> shift, for 32 bytes. The
    deltas are signed words after the source's 32 bytes."""
    instrument = voice.instrument
    data = module.data
    deltas = instrument.start + MORPH_BYTES
    for i in range(MORPH_BYTES):
        delta = signed_word(word(data, deltas + 2 * i))
        value = (voice.morph_step * delta & 0xFFFFFFFF) >> instrument.morph_shift
        voice.wave[i] = (data[instrument.start + i] + value) & 0xFF


def PulseInit(voice: Voice) -> None:
    """The wave: `pulse_from` low bytes, then high bytes up to the
    instrument's length. The edge starts at `pulse_from`."""
    instrument = voice.instrument
    voice.pulse_turns = instrument.pulse_turns
    voice.pulse_delay = instrument.pulse_delay
    voice.pulse_ticks = instrument.pulse_speed
    voice.pulse_down = False
    voice.pulse_pos = instrument.pulse_from
    size = 2 * instrument.length & 0xFF
    for i in range(size):
        voice.wave[i] = (
            instrument.pulse_low if i < instrument.pulse_from else instrument.pulse_high
        )


def MorphInit(module: Module, voice: Voice) -> None:
    """Copies the source's 32 bytes into the voice's wave."""
    instrument = voice.instrument
    voice.morph_down, voice.morph_step = False, 1
    voice.morph_turns = instrument.morph_turns
    voice.morph_delay = instrument.morph_delay
    voice.wave[:MORPH_BYTES] = module.data[
        instrument.start : instrument.start + MORPH_BYTES
    ]


# --- Helpers -----------------------------------------------------------


def keeps_dma(byte: int) -> bool:
    """CountDown's signed compare of the next byte with GAP_LIMIT."""
    return (byte - GAP_LIMIT) & 0xFF < 0x80


def note_period(module: Module, instrument: Instrument, note: int) -> int:
    table = word(module.data, module.period_table + 2 * note)
    return table * instrument.tune >> TUNE_SHIFT & 0xFFFF


def chip(module: Module, start: int, words: int) -> paula.Sample:
    return paula.Sample(module.data, start & ~1, words)


def read_instrument(data: bytes | bytearray, at: int) -> Instrument:
    r = data[at : at + INSTRUMENT_SIZE]
    return Instrument(
        long(r, 0), signed_word(word(r, 4)), word(r, 6), word(r, 8),
        r[10], r[12], r[13], r[14], r[15], r[16], r[17], r[18], r[19],
        r[20], r[21], bytes(r[22:38]), r[38], r[39], r[40], r[41], r[42],
        r[43], r[44], r[45], r[46], r[47], r[48], r[49], r[50], r[51],
    )  # fmt: skip


def signed_byte(value: int) -> int:
    return value - 0x100 if value & 0x80 else value


def signed_word(value: int) -> int:
    return value - 0x10000 if value & 0x8000 else value


def word(data: bytes | bytearray, at: int) -> int:
    return data[at] << 8 | data[at + 1]


def long(data: bytes | bytearray, at: int) -> int:
    return word(data, at) << 16 | word(data, at + 2)
