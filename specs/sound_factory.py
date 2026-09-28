"""Soundfactory 1.0's replay (Profiteam), from the Soundfactory editor.
Soundfactory_v2.asm, Wanted Team's adaptation.

Card: players/SoundFactory.md. Level 2: the control flow runs. Each
CamelCase function is a new name in data/annot/SoundFactory.yaml; each
CamelCase class is in its `types:`.

There are no patterns and no rows. A song gives each voice its own
stream of bytes: notes with their own lengths, and opcodes. Streams call,
jump and loop, each with its own stack. The streams sync through one
shared counter: one voice counts it up, another waits for a value.

Instruments live inside the streams. When a stream passes an instrument's
bytes, the player registers it under its number. Effect opcodes write
into the current instrument, so every voice that plays it changes too.

Two wave effects rebuild a short wave into a per-voice buffer: phasing
mixes the wave with a shifted copy, and a filter smooths it. Each sweeps
its parameter between two limits. A buffer holds 256 bytes; a longer
wave runs into the next voice's buffer, which this model leaves out.
"""

from collections.abc import Callable
from dataclasses import dataclass, field

from hardware import paula
from hardware.amiga import DEFAULT_LATCH, Amiga

VOICES = 4
SONGS = 16
INSTRUMENTS = 32
MASKS = 4  # header: a module size long, then one voice mask per song
SONG_TABLE = 0x14  # four stream offsets per song, 16 bytes each
BUFFER_SIZE = 256  # WaveBuffers: bytes per voice
FULL = 0x40  # envelope level for full volume
LEGATO = 0x8000  # a note length's bit 15: no envelope restart
EARLY_STOP_PERIOD = 0x1AD  # EarlyStop acts on this period and above
FIRST_OPCODE = 0x80  # stream bytes below are notes
WAIT = 0x80  # OpWait's byte: the next event does not stop DMA early
EMPTY = paula.Sample(bytes(4))  # EmptyWord

# Instrument flags: byte 8 of the instrument
ONE_SHOT = 0x01  # no loop: silence after one pass; loop: release plays the tail
VIBRATO = 0x02
OCTAVE_FLIP = 0x04
PHASING = 0x08
PORTAMENTO = 0x10
HOLD = 0x20  # no release at half the note's length
TREMOLO = 0x40
FILTER = 0x80

# Envelope phases
ATTACK, DECAY, SUSTAIN, RELEASE = range(4)

# The loop step after a note or a release, two ticks later
NOTE_STARTED, RELEASED = 1, 2

# WavePeriods: octave 0 periods for a wave of one word and one cycle
WAVE_PERIODS = (
    *(0xD5C8, 0xC9C8, 0xBE75, 0xB3C4, 0xA9AD, 0xA027),
    *(0x972A, 0x8EAE, 0x86AC, 0x7F1D, 0x77FB, 0x7124),
)
# SampleRatios: 2 ** (-n / 12) / 2, as 16-bit fractions
SAMPLE_RATIOS = (
    *(0x8000, 0x78D1, 0x7209, 0x6BA3, 0x6598, 0x5FE5),
    *(0x5A83, 0x556E, 0x50A3, 0x4C1C, 0x47D7, 0x43CF),
)


# --- What the composer edits -------------------------------------------


@dataclass
class Instrument:
    """Defined inside a stream, from its opcode byte on. Opcodes of any
    voice write these fields: the module's bytes are the only copy."""

    length: int  # +4: words
    rate: int  # +6: base period of a sample; 0: a wave, tuned by length
    flags: int  # +8
    tremolo_speed: int  # +9
    tremolo_step: int  # +10
    tremolo_limit: int  # +11
    slide_step: int  # +12: word
    slide_speed: int  # +14
    flip_speed: int  # +15
    vibrato_delay: int  # +16
    vibrato_speed: int  # +17
    vibrato_step: int  # +18
    vibrato_depth: int  # +19
    attack: int  # +20: ticks
    decay: int  # +21: ticks
    sustain: int  # +22: level, 0 to 64
    release: int  # +23: ticks, from any sustain level
    phase_min: int  # +24
    phase_max: int  # +25
    phase_speed: int  # +26
    phase_step: int  # +27
    cycles: int  # +28: wave cycles in the sample
    octave: int  # +29: the octave where `rate` holds
    filter_from: int  # +30: width
    filter_to: int  # +31
    filter_speed: int  # +32; +33 is unused
    loop_start: int  # +34: words
    loop_end: int  # +36: words
    data: bytes  # +38

    @property
    def looped(self) -> bool:
        return bool(self.loop_start or self.loop_end)


def word(data: bytes, at: int) -> int:
    return data[at] << 8 | data[at + 1]


def long(data: bytes, at: int) -> int:
    return word(data, at) << 16 | word(data, at + 2)


def parse_instrument(data: bytes, at: int) -> Instrument:
    b = data[at:]
    return Instrument(
        length=word(b, 4), rate=word(b, 6), flags=b[8],
        tremolo_speed=b[9], tremolo_step=b[10], tremolo_limit=b[11],
        slide_step=word(b, 12), slide_speed=b[14], flip_speed=b[15],
        vibrato_delay=b[16], vibrato_speed=b[17],
        vibrato_step=b[18], vibrato_depth=b[19],
        attack=b[20], decay=b[21], sustain=b[22], release=b[23],
        phase_min=b[24], phase_max=b[25], phase_speed=b[26], phase_step=b[27],
        cycles=b[28], octave=b[29],
        filter_from=b[30], filter_to=b[31], filter_speed=b[32],
        loop_start=word(b, 34), loop_end=word(b, 36),
        data=b[38 : 38 + 2 * word(b, 4)],
    )  # fmt: skip


DEFAULT = parse_instrument(  # DefaultInstrument: one word, quiet
    bytes.fromhex(
        "8400ffff0001" + "00" * 14 + "0100401e000000000100013202000000000000649c"
    ),
    0,
)


# --- Player state ------------------------------------------------------


@dataclass
class Voice:
    channel: paula.Channel
    number: int
    start: int = 0  # the stream's first byte
    pos: int = 0
    stack: list[int] = field(default_factory=list)  # Stacks: 80 bytes per voice
    duration: int = 1  # ticks to the next event
    instrument: int = 0
    volume: int = 0  # 0: full; else a factor of 256
    detune: int = 0  # added to the period, 0 to 255
    transpose: int = 0
    note: int = 0
    period: int = 0
    last_period: int = 0  # the period written last tick
    loop_step: int = 0  # NOTE_STARTED or RELEASED; acts two ticks later
    loop_next: int = 0
    tremolo_count: int = 0
    tremolo_step: int = 0
    tremolo_level: int = 0  # 0: full; else a factor of 256
    slide_period: int = 0
    slide_count: int = 0
    flip_count: int = 0
    flipped: bool = False  # the period is halved
    vibrato_delay: int = 0
    vibrato_count: int = 0
    vibrato_offset: int = 0
    vibrato_step: int = 0
    vibrato_left: int = 0
    phase: int = SUSTAIN  # the envelope's
    level: int = 0  # the envelope's, 0 to 64
    acc: int = 0  # the envelope's step fraction
    hold_left: int = 0  # ticks to the release: half the note's length
    phase_count: int = 0
    phase_step: int = 0
    phase_offset: int = 0
    filter_count: int = 0
    filter_width: int = 0
    filter_dir: int = 1
    buffer: bytearray = field(default_factory=lambda: bytearray(BUFFER_SIZE))


@dataclass
class Module:  # State
    amiga: Amiga
    data: bytes
    voices: list[Voice] = field(default_factory=list)
    instruments: list[Instrument] = field(default_factory=list)  # InstrumentTable
    defined: dict[int, Instrument] = field(default_factory=dict)  # by stream address
    active: int = 0  # voice mask; OpStop clears a bit
    dma_mask: int = 0  # the song's voice mask
    signal: int = 0  # the shared counter
    fade_in: bool = False
    fade_out: bool = False
    fade_level: int = 0  # 0: full; else a factor of 256
    fade_speed: int = 0  # quarter steps per tick
    fade_frac: int = 0
    new_notes: int = 0  # voices whose DMA goes on after this tick
    audio_filter: bool = True


# --- Start -------------------------------------------------------------


def new_module(data: bytes, amiga: Amiga) -> Module:
    """DeliTracker calls Play by its own timer."""
    module = Module(amiga, data)
    module.voices = [Voice(c, n) for n, c in enumerate(amiga.paula.channels)]
    amiga.timer.on_underflow = lambda: Play(module)
    amiga.timer.set_latch(DEFAULT_LATCH)
    return module


def InitSong(module: Module, number: int) -> None:
    """Songs count from 1. Envelopes and effects carry over."""
    n = (number - 1) % SONGS
    module.active = module.dma_mask = module.data[MASKS + n]
    for voice in module.voices:
        at = SONG_TABLE + 16 * n + 4 * voice.number
        voice.start = voice.pos = long(module.data, at)
        voice.duration, voice.stack = 1, []
        voice.instrument = voice.volume = voice.detune = voice.transpose = 0
        voice.loop_next = 0
        voice.channel.disable()
    module.instruments = [DEFAULT] * INSTRUMENTS
    module.fade_in = module.fade_out = False
    module.fade_level = module.fade_frac = module.signal = module.new_notes = 0
    module.audio_filter = True


def StopSong(module: Module) -> None:
    """The end of a fade-out, or the game's stop: all voices off."""
    module.active = 0
    module.fade_in = module.fade_out = False
    for voice in module.voices:
        voice.channel.disable()
        voice.channel.set_volume(0)


def FadeOut(module: Module, speed: int) -> None:
    """A game entry point, and OpFadeOut's action."""
    module.fade_speed, module.fade_frac = speed, 0
    module.fade_in, module.fade_out = False, True


# --- Tick --------------------------------------------------------------


def Play(module: Module) -> None:
    """The fade, then voices 3 to 0. Then DMA on for new notes, after a
    wait of about eight lines."""
    if (module.fade_in or module.fade_out) and not Fade(module):
        StopSong(module)
        return
    module.new_notes = 0
    for voice in reversed(module.voices):
        if module.active >> voice.number & 1:
            PlayVoice(module, voice)
    for voice in module.voices:
        if (module.new_notes & module.dma_mask) >> voice.number & 1:
            voice.channel.enable()


def Fade(module: Module) -> bool:
    """Moves the master level by `speed` / 4 per tick. False: a fade-out
    reached 0. A fade-in that passes 255 ends at full."""
    total = module.fade_frac + module.fade_speed
    module.fade_frac, step = total & 3, (total & 0xFF) >> 2
    level = module.fade_level
    if module.fade_in:
        if level + step > 0xFF:
            module.fade_in, module.fade_level = False, 0
            return True
        module.fade_level = level + step
        return True
    if level == 0:  # full: the fade-out starts from 256
        module.fade_level = -step & 0xFF
        return True
    if level - step <= 0:
        return False
    module.fade_level = level - step
    return True


def PlayVoice(module: Module, voice: Voice) -> None:
    """A tick that reads the stream runs no effects."""
    voice.duration = (voice.duration - 1) & 0xFFFF
    if voice.duration == 0:
        ReadStream(module, voice)
        return
    if voice.duration == 1:
        EarlyStop(module, voice)
    VoiceEffects(module, voice)


def EarlyStop(module: Module, voice: Voice) -> None:
    """One tick before the next event, DMA goes off, unless that event
    is a wait or a legato note. Only for periods of 429 and above."""
    if voice.last_period < EARLY_STOP_PERIOD:
        return
    byte = module.data[voice.pos]
    if byte == WAIT:
        return
    if byte < FIRST_OPCODE and module.data[voice.pos + 1] & 0x80:
        return
    voice.channel.disable()


def ReadStream(module: Module, voice: Voice) -> None:
    """Opcodes go on until one ends the tick: a note, a wait or a rest.
    A note of length 0 sets its pitch and reads on."""
    while True:
        byte = read_byte(module, voice)
        if byte < FIRST_OPCODE:
            if not NoteOn(module, voice, byte):
                return
            continue
        if not OPCODES[byte & 0x7F](module, voice):
            return


def NoteOn(module: Module, voice: Voice, byte: int) -> bool:
    """A note byte, then a length word. True: length 0, read on.
    A legato note keeps the envelope. The DMA goes on after all voices."""
    inst = instrument(module, voice)
    voice.channel.disable()
    voice.note = (byte + voice.transpose) & 0x7F
    if inst.flags & PORTAMENTO:
        voice.slide_period, voice.slide_count = voice.period, 1
    voice.period = NotePeriod(inst, voice.note)
    length = read_word(module, voice)
    if not length & ~LEGATO:
        return True
    voice.duration = length & ~LEGATO
    voice.hold_left = voice.duration >> 1
    voice.loop_step = NOTE_STARTED
    start_effects(voice, inst)
    if not length & LEGATO:
        start_envelope(voice, inst)
    wave: paula.Memory = inst.data
    if inst.flags & PHASING:
        voice.phase_count, voice.phase_step = inst.phase_speed, inst.phase_step
        voice.phase_offset = inst.phase_min
        BuildPhasing(voice, inst)
        wave = voice.buffer
    if inst.flags & FILTER:
        voice.filter_count, voice.filter_width = inst.filter_speed, inst.filter_from
        voice.filter_dir = 1
        BuildFilter(voice, inst)
        wave = voice.buffer
    words = inst.loop_end if inst.looped else inst.length
    voice.channel.queue(paula.Sample(wave, 0, words))
    WriteVoice(module, voice, inst)
    module.new_notes |= 1 << voice.number
    return False


def start_effects(voice: Voice, inst: Instrument) -> None:
    if inst.flags & OCTAVE_FLIP:
        voice.flipped, voice.flip_count = False, inst.flip_speed
    if inst.flags & VIBRATO:
        voice.vibrato_delay = inst.vibrato_delay
        if not voice.vibrato_delay:
            voice.vibrato_step, voice.vibrato_offset = inst.vibrato_step, 0
            voice.vibrato_count = inst.vibrato_speed
            voice.vibrato_left = inst.vibrato_depth
    if inst.flags & TREMOLO:
        voice.tremolo_count, voice.tremolo_level = 1, 0
        voice.tremolo_step = -inst.tremolo_step & 0xFF


def start_envelope(voice: Voice, inst: Instrument) -> None:
    """From 0 with an attack; else from full with a decay; else at the
    sustain level."""
    voice.acc = 0
    if inst.attack:
        voice.phase, voice.level = ATTACK, 0
    elif inst.decay and inst.sustain != FULL:
        voice.phase, voice.level = DECAY, FULL
    else:
        voice.phase, voice.level = SUSTAIN, inst.sustain


def NotePeriod(inst: Instrument, note: int) -> int:
    """A wave's period divides by its length in words and multiplies by
    its cycles: any wave plays in tune. A sample's `rate` holds in its
    base octave; other octaves shift it."""
    octave, semitone = divmod(note, 12)
    if not inst.rate:
        period = WAVE_PERIODS[semitone] * inst.cycles
        period = period // inst.length & 0xFFFF
        return (period >> octave << 1) & 0xFFFF
    period = inst.rate * SAMPLE_RATIOS[semitone] * 2 >> 16
    shift = inst.octave - octave
    return (period << shift if shift > 0 else period >> -shift) & 0xFFFF


def VoiceEffects(module: Module, voice: Voice) -> None:
    """Two ticks after a note, the loop starts. Two ticks after a
    release, a one-shot sample ends."""
    inst = instrument(module, voice)
    if voice.loop_next == RELEASED:
        voice.channel.queue(EMPTY)
    elif voice.loop_next == NOTE_STARTED:
        if inst.looped:
            start, end = 2 * inst.loop_start, 2 * inst.loop_end
            voice.channel.queue(paula.Sample(inst.data[start:end]))
        elif inst.flags & ONE_SHOT:
            voice.channel.queue(EMPTY)
    voice.loop_next, voice.loop_step = voice.loop_step, 0
    Tremolo(voice, inst)
    Portamento(voice, inst)
    OctaveFlip(voice, inst)
    Vibrato(voice, inst)
    EnvelopeTick(voice, inst)
    WaveEffects(voice, inst)
    WriteVoice(module, voice, inst)


def Tremolo(voice: Voice, inst: Instrument) -> None:
    """The level turns when it reaches the limit or less."""
    if not inst.flags & TREMOLO:
        return
    voice.tremolo_count = (voice.tremolo_count - 1) & 0xFF
    if voice.tremolo_count:
        return
    voice.tremolo_count = inst.tremolo_speed
    voice.tremolo_level = (voice.tremolo_level + voice.tremolo_step) & 0xFF
    if voice.tremolo_level <= inst.tremolo_limit:
        voice.tremolo_step = -voice.tremolo_step & 0xFF


def Portamento(voice: Voice, inst: Instrument) -> None:
    """From the last note's period to this note's, one step every
    `slide_speed` ticks."""
    if not inst.flags & PORTAMENTO or voice.slide_period == voice.period:
        return
    voice.slide_count = (voice.slide_count - 1) & 0xFF
    if voice.slide_count:
        return
    voice.slide_count = inst.slide_speed
    if voice.period < voice.slide_period:
        voice.slide_period = max(voice.slide_period - inst.slide_step, voice.period)
    else:
        voice.slide_period = min(voice.slide_period + inst.slide_step, voice.period)


def OctaveFlip(voice: Voice, inst: Instrument) -> None:
    """Every `flip_speed` ticks the pitch jumps an octave up or back."""
    if not inst.flags & OCTAVE_FLIP:
        return
    voice.flip_count = (voice.flip_count - 1) & 0xFF
    if not voice.flip_count:
        voice.flip_count = inst.flip_speed
        voice.flipped = not voice.flipped


def Vibrato(voice: Voice, inst: Instrument) -> None:
    """A triangle: `depth` steps one way, then `2 * depth` steps back."""
    if not inst.flags & VIBRATO:
        return
    if voice.vibrato_delay:
        voice.vibrato_delay -= 1
        if not voice.vibrato_delay:
            voice.vibrato_count, voice.vibrato_offset = 1, 0
            voice.vibrato_step = inst.vibrato_step
            voice.vibrato_left = inst.vibrato_depth
        return
    voice.vibrato_count = (voice.vibrato_count - 1) & 0xFF
    if voice.vibrato_count:
        return
    voice.vibrato_count = inst.vibrato_speed
    voice.vibrato_offset += signed(voice.vibrato_step)
    voice.vibrato_left = (voice.vibrato_left - 1) & 0xFF
    if not voice.vibrato_left:
        voice.vibrato_left = 2 * inst.vibrato_depth & 0xFF
        voice.vibrato_step = -voice.vibrato_step & 0xFF


def EnvelopeTick(voice: Voice, inst: Instrument) -> None:
    """Each phase takes its parameter in ticks, whatever the levels:
    each tick adds the distance to a fraction, and each whole parameter
    in it is one level step."""
    if voice.phase == RELEASE:
        if voice.level:
            Release(voice, inst)
        return
    if not inst.flags & HOLD and AutoRelease(voice, inst):
        return
    if voice.phase == DECAY:
        Decay(voice, inst)
    elif voice.phase == ATTACK:
        Attack(voice, inst)


def AutoRelease(voice: Voice, inst: Instrument) -> bool:
    """The release starts at half the note's length. A one-shot sample
    with a loop then plays on to its end. True: the envelope waits."""
    if voice.hold_left:
        voice.hold_left -= 1
        if voice.hold_left:
            return False
    if voice.phase != SUSTAIN:
        return False
    voice.phase, voice.acc = RELEASE, 0
    if inst.flags & ONE_SHOT and inst.looped:
        voice.channel.length = inst.length - inst.loop_start
        voice.loop_step = RELEASED
    return True


def Release(voice: Voice, inst: Instrument) -> None:
    """Adds half the sustain level each tick: the release takes twice
    `release` ticks from any sustain level."""
    total = voice.acc + max(inst.sustain >> 1, 1)
    voice.acc = total & 0xFF
    if total <= 0xFF and voice.acc < inst.release:
        return
    while True:
        voice.acc = (voice.acc - inst.release) & 0xFF
        voice.level -= 1
        if not voice.level or voice.acc < inst.release:
            return


def Decay(voice: Voice, inst: Instrument) -> None:
    """Down from full to the sustain level. The fraction's overflow is
    lost here."""
    voice.acc = (voice.acc + FULL - inst.sustain) & 0xFF
    while voice.acc >= inst.decay:
        voice.acc = (voice.acc - inst.decay) & 0xFF
        voice.level -= 1
        if not voice.level:
            break
    if inst.sustain >= voice.level:
        voice.phase = SUSTAIN


def Attack(voice: Voice, inst: Instrument) -> None:
    """Up to full with a decay, else up to the sustain level. Nothing
    stops the level past its target: it must land on it."""
    target = FULL if inst.decay else inst.sustain
    total = voice.acc + target
    voice.acc, carry = total & 0xFF, total > 0xFF
    while inst.attack and (carry or voice.acc >= inst.attack):
        voice.acc = (voice.acc - inst.attack) & 0xFF
        voice.level = (voice.level + 1) & 0xFF
        carry = False
    if voice.level != target:
        return
    if not inst.decay:
        voice.phase = SUSTAIN
        return
    voice.acc = 0
    voice.phase = DECAY if inst.sustain != FULL else SUSTAIN


def WaveEffects(voice: Voice, inst: Instrument) -> None:
    """Phasing moves its offset, and the filter its width, each at its
    own speed. When one moves, the buffer is rebuilt; the channel plays
    it on, changed."""
    moved = False
    if inst.flags & PHASING:
        voice.phase_count = (voice.phase_count - 1) & 0xFF
        if not voice.phase_count:
            voice.phase_count = inst.phase_speed
            offset = voice.phase_offset + signed(voice.phase_step)
            voice.phase_offset = offset & 0xFF
            if not inst.phase_min < offset < inst.phase_max:
                voice.phase_step = -voice.phase_step & 0xFF
            moved = True
    if inst.flags & FILTER:
        voice.filter_count = (voice.filter_count - 1) & 0xFF
        if not voice.filter_count:
            voice.filter_count = inst.filter_speed
            voice.filter_width = (voice.filter_width + voice.filter_dir) & 0xFF
            if voice.filter_width in (inst.filter_from, inst.filter_to):
                voice.filter_dir = -voice.filter_dir
            moved = True
    if moved and inst.flags & PHASING:
        BuildPhasing(voice, inst)
    if moved and inst.flags & FILTER:
        BuildFilter(voice, inst)


def WriteVoice(module: Module, voice: Voice, inst: Instrument) -> None:
    """Volume: the envelope level, scaled by tremolo, the voice's volume
    and the fade. Period: the note or the slide, then vibrato, octave
    flip and detune."""
    volume = voice.level
    for factor in (
        voice.tremolo_level if inst.flags & TREMOLO else 0,
        voice.volume,
        module.fade_level if module.fade_in or module.fade_out else 0,
    ):
        if factor:
            volume = volume * factor >> 8
    voice.channel.set_volume(volume)
    period = voice.slide_period if inst.flags & PORTAMENTO else voice.period
    if inst.flags & VIBRATO and not voice.vibrato_delay:
        period += voice.vibrato_offset
    if inst.flags & OCTAVE_FLIP and voice.flipped:
        period >>= 1
    period = (period + voice.detune) & 0xFFFF
    voice.channel.period = voice.last_period = period


# --- Wave effects ------------------------------------------------------


def BuildPhasing(voice: Voice, inst: Instrument) -> None:
    """Each byte is the mean of the wave's byte and the byte `offset`
    places before it."""
    wave, size = inst.data, 2 * inst.length
    for n in range(size):
        mixed = signed(wave[n]) + signed(wave[(n - voice.phase_offset) % size])
        voice.buffer[n] = mixed >> 1 & 0xFF


def BuildFilter(voice: Voice, inst: Instrument) -> None:
    """A low-pass filter: the mean of `width` bytes, taken every `width`
    bytes, with straight lines between the means. With phasing on, it
    works in place on the phasing buffer. Width 1 copies the wave."""
    size, width = 2 * inst.length, voice.filter_width
    source = voice.buffer if inst.flags & PHASING else bytearray(inst.data)
    if width == 1:
        if not inst.flags & PHASING:
            voice.buffer[:size] = source[:size]
        return
    pos, wrapped = width >> 1, False
    mean = window_mean(source, 0, width, size)
    while not wrapped:
        last, mean = mean, window_mean(source, (width >> 1) + pos, width, size)
        rise, error = abs(mean - last), 0
        sign = 1 if mean >= last else -1
        for _ in range(width):
            voice.buffer[pos] = last & 0xFF
            error += rise
            while error >= width:
                error -= width
                last += sign
            pos += 1
            if pos >= size:
                pos, wrapped = pos - size, True


def window_mean(data: bytearray, start: int, width: int, size: int) -> int:
    """Signed division, rounded toward 0, as DIVS does."""
    total = sum(signed(data[(start + n) % size]) for n in range(width))
    return int(total / width)


# --- Opcodes -----------------------------------------------------------
# Each returns True when the stream reads on in this tick.

Opcode = Callable[[Module, Voice], bool]


def OpWait(module: Module, voice: Voice) -> bool:
    """A word of ticks. The note sounds on."""
    voice.duration = read_word(module, voice)
    return False


def OpRest(module: Module, voice: Voice) -> bool:
    """A word of ticks, with DMA off."""
    voice.duration = read_word(module, voice)
    voice.channel.disable()
    return False


def OpVolume(module: Module, voice: Voice) -> bool:
    voice.volume = read_byte(module, voice)
    return True


def OpDetune(module: Module, voice: Voice) -> bool:
    voice.detune = read_byte(module, voice)
    return True


def OpInstrument(module: Module, voice: Voice) -> bool:
    voice.instrument = read_byte(module, voice)
    return True


def OpDefineInstrument(module: Module, voice: Voice) -> bool:
    """A number, then a word: the definition's size in words, from
    this opcode on. The stream skips the rest. Passing it again keeps
    what opcodes wrote."""
    number = read_byte(module, voice)
    at = voice.pos - 2
    if at not in module.defined:
        module.defined[at] = parse_instrument(module.data, at)
    module.instruments[number] = module.defined[at]
    voice.pos = at + 2 * read_word(module, voice)
    return True


def OpReturn(module: Module, voice: Voice) -> bool:
    voice.pos = voice.stack.pop()
    return True


def OpCall(module: Module, voice: Voice) -> bool:
    """A long offset from after itself."""
    offset = read_long(module, voice)
    voice.stack.append(voice.pos)
    voice.pos += offset
    return True


def OpJump(module: Module, voice: Voice) -> bool:
    """A long offset from after itself."""
    voice.pos += read_long(module, voice)
    return True


def OpLoopStart(module: Module, voice: Voice) -> bool:
    """A count; 0 means 256. Loops nest on the stack."""
    count = read_byte(module, voice)
    voice.stack += [count, voice.pos]
    return True


def OpLoopEnd(module: Module, voice: Voice) -> bool:
    mark, count = voice.stack.pop(), (voice.stack.pop() - 1) & 0xFF
    if count:
        voice.pos = mark
        voice.stack += [count, mark]
    return True


def OpFadeOut(module: Module, voice: Voice) -> bool:
    """A speed. At 0, the song stops."""
    FadeOut(module, read_byte(module, voice))
    return True


def OpNop(module: Module, voice: Voice) -> bool:
    return True


def OpSignal(module: Module, voice: Voice) -> bool:
    """Counts the shared counter up."""
    module.signal = (module.signal + 1) & 0xFF
    return True


def OpRestart(module: Module, voice: Voice) -> bool:
    """Back to the stream's start."""
    voice.pos = voice.start
    return True


def OpStop(module: Module, voice: Voice) -> bool:
    """The voice ends for this song."""
    voice.channel.disable()
    voice.channel.set_volume(0)
    module.active &= ~(1 << voice.number)
    return False


def OpFadeIn(module: Module, voice: Voice) -> bool:
    """A speed."""
    module.fade_speed = read_byte(module, voice)
    module.fade_in, module.fade_out, module.fade_frac = True, False, 0
    module.fade_level = module.fade_level or 1
    return True


def OpAdsr(module: Module, voice: Voice) -> bool:
    """Attack, decay, sustain, then a byte: 0 holds; else the
    release follows."""
    inst = instrument(module, voice)
    inst.attack, inst.decay, inst.sustain = read_bytes(module, voice, 3)
    if not read_byte(module, voice):
        inst.flags |= HOLD
        return True
    inst.flags &= ~HOLD
    inst.release = read_byte(module, voice)
    return True


def OpOneShotOn(module: Module, voice: Voice) -> bool:
    instrument(module, voice).flags |= ONE_SHOT
    return True


def OpOneShotOff(module: Module, voice: Voice) -> bool:
    instrument(module, voice).flags &= ~ONE_SHOT
    return True


def OpVibrato(module: Module, voice: Voice) -> bool:
    """0 turns it off; else delay, speed, step and depth."""
    inst = instrument(module, voice)
    if switch(module, voice, inst, VIBRATO):
        values = read_bytes(module, voice, 4)
        inst.vibrato_delay, inst.vibrato_speed = values[0], values[1]
        inst.vibrato_step, inst.vibrato_depth = values[2], values[3]
    return True


def OpOctaveFlip(module: Module, voice: Voice) -> bool:
    """0 turns it off; else a speed."""
    inst = instrument(module, voice)
    if switch(module, voice, inst, OCTAVE_FLIP):
        inst.flip_speed = read_byte(module, voice)
    return True


def OpPhasing(module: Module, voice: Voice) -> bool:
    """0 turns it off; else the offset's limits, speed and step."""
    inst = instrument(module, voice)
    if switch(module, voice, inst, PHASING):
        values = read_bytes(module, voice, 4)
        inst.phase_min, inst.phase_max = values[0], values[1]
        inst.phase_speed, inst.phase_step = values[2], values[3]
    return True


def OpPortamento(module: Module, voice: Voice) -> bool:
    """0 turns it off; else a speed, then a step word."""
    inst = instrument(module, voice)
    if switch(module, voice, inst, PORTAMENTO):
        inst.slide_speed = read_byte(module, voice)
        inst.slide_step = read_word(module, voice)
    return True


def OpTremolo(module: Module, voice: Voice) -> bool:
    """0 turns it off; else speed, step and limit."""
    inst = instrument(module, voice)
    if switch(module, voice, inst, TREMOLO):
        values = read_bytes(module, voice, 3)
        inst.tremolo_speed, inst.tremolo_step, inst.tremolo_limit = values
    return True


def OpFilter(module: Module, voice: Voice) -> bool:
    """0 turns it off; else the width's limits and speed."""
    inst = instrument(module, voice)
    if switch(module, voice, inst, FILTER):
        values = read_bytes(module, voice, 3)
        inst.filter_from, inst.filter_to, inst.filter_speed = values
    return True


def OpAudioFilter(module: Module, voice: Voice) -> bool:
    """0 turns Amiga's audio filter off."""
    module.audio_filter = bool(read_byte(module, voice))
    return True


def OpWaitSignal(module: Module, voice: Voice) -> bool:
    """A value. Until the shared counter holds it, the voice tries
    again every tick."""
    if read_byte(module, voice) == module.signal:
        return True
    voice.pos -= 2
    voice.duration = 1
    return False


def OpTranspose(module: Module, voice: Voice) -> bool:
    """Added to each note byte."""
    voice.transpose = read_byte(module, voice)
    return True


OPCODES: tuple[Opcode, ...] = (  # OpcodeTable, from FIRST_OPCODE
    OpWait,  # $80
    OpVolume,  # $81
    OpDetune,  # $82
    OpInstrument,  # $83
    OpDefineInstrument,  # $84
    OpReturn,  # $85
    OpCall,  # $86
    OpJump,  # $87
    OpLoopStart,  # $88
    OpLoopEnd,  # $89
    OpFadeOut,  # $8a
    OpNop,  # $8b
    OpSignal,  # $8c
    OpRestart,  # $8d
    OpStop,  # $8e
    OpFadeIn,  # $8f
    OpAdsr,  # $90
    OpOneShotOn,  # $91
    OpOneShotOff,  # $92
    OpVibrato,  # $93
    OpOctaveFlip,  # $94
    OpPhasing,  # $95
    OpPortamento,  # $96
    OpTremolo,  # $97
    OpFilter,  # $98
    OpRest,  # $99
    OpAudioFilter,  # $9a
    OpWaitSignal,  # $9b
    OpTranspose,  # $9c
)


# --- Helpers -----------------------------------------------------------


def instrument(module: Module, voice: Voice) -> Instrument:
    return module.instruments[voice.instrument % INSTRUMENTS]


def switch(module: Module, voice: Voice, inst: Instrument, flag: int) -> bool:
    """A 0 byte clears the instrument's flag; else it sets it. True: set."""
    if read_byte(module, voice):
        inst.flags |= flag
        return True
    inst.flags &= ~flag
    return False


def read_byte(module: Module, voice: Voice) -> int:
    voice.pos += 1
    return module.data[voice.pos - 1]


def read_bytes(module: Module, voice: Voice, count: int) -> tuple[int, ...]:
    return tuple(read_byte(module, voice) for _ in range(count))


def read_word(module: Module, voice: Voice) -> int:
    return read_byte(module, voice) << 8 | read_byte(module, voice)


def read_long(module: Module, voice: Voice) -> int:
    value = read_word(module, voice) << 16 | read_word(module, voice)
    return value - (1 << 32) if value & 1 << 31 else value


def signed(byte: int) -> int:
    return byte - 0x100 if byte & 0x80 else byte
