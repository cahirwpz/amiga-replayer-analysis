"""Art Of Noise's 8-voice replay: ArtofNoise8.s, the author's replay 1.6
(1993-94) and his 8-channel mixer (1995), adapted for UADE in 2006.
Bastian Spiegel (Twice/Lego) released the sources as freeware.

Card: players/ArtOfNoise-8V.md. Level 2: the control flow runs; the
mixer's 16.16 steps are exact, its cycle counts are not modelled. Each
CamelCase function is a new name in data/annot/ArtOfNoise-8V.yaml; each
CamelCase class is in its `types:`.

A row holds one 4-byte cell per voice: note, instrument, command and
argument, as in a ProTracker cell. The two top bits of the instrument
byte and of the command byte pick one of 16 arpeggio tables.

An instrument plays a sample or a wave. A synth wave is one long sample
of equal parts, the format's `partwave`. The note starts on the first
part. Every N ticks the loop start moves one part on, through the wave,
then between two loop parts: forward, backwards or ping-pong. The mixer
takes a new loop start at the end of the playing part, so the step never
clicks.

The CIA timer runs the replay. The replay writes each voice's start,
length, period and volume into a shadow, and hands the shadow to the
mixer. Each Paula channel plays two voices. Its audio interrupt mixes
the next 128 bytes for that pair, apart from the tick.

Not modelled: the E commands, the commands that combine a slide with
another command, the sample offset command, pattern loops and delays,
the filter, the period table's other 15 fine tunes, and the switches
that the 4-voice replay uses for long samples and for clicks.
"""

from collections.abc import Callable
from dataclasses import dataclass, field

from hardware import paula
from hardware.amiga import Amiga

VOICES = 8
ROWS = 64
CELL = 4  # note, instrument, command, argument
PATTERN_SIZE = ROWS * VOICES * CELL
INSTRUMENTS = 61
INSTRUMENT_SIZE = 32
WAVES = 64
ARPEGGIO_SIZE = 4  # bytes per arpeggio table
ARPEGGIO_STEPS = 8  # a voice's list: 7 notes and an end mark
LAST_NOTE = 60  # notes 1 to 60, five octaves; higher notes are pauses
MIN_PERIOD = 103
SPEED = 6  # ticks per row at start
TEMPO = 125  # at start: 50 ticks per second
TIMER_BASE = 1773447  # CIA counts per second × 5 / 2: latch = this / tempo
MAX_SPEED = 32  # a speed argument above this is a tempo
MAX_TEMPO = 200
FULL_VOLUME = 64
ENVELOPE_TOP = 127

# Mixer
MIX_PERIOD = 250  # every channel plays its buffer at this period
MIX_BUFFER = 128  # bytes a channel's audio interrupt mixes
SILENT_LOOP = 2  # bytes: a loop this short or shorter ends the voice

# Instrument kinds
SAMPLE, SYNTH = 0, 1

# Scan modes at the loop's end
FORWARD, BACKWARDS, PING_PONG = 0, 1, 2

# Shadow flags, from the voice's new-wave flag
NEW_LOOP = 1  # the mixer takes the loop at the end of the playing part
NEW_START = 2  # the mixer restarts the voice

# Commands, by the cell's command byte; letters are the tracker's
ARPEGGIO = 0x00
PORTAMENTO_UP = 0x01
PORTAMENTO_DOWN = 0x02
TONE_SLIDE = 0x03
VIBRATO = 0x04
VOLUME_SLIDE = 0x0A
SET_VOLUME = 0x0C
SET_SPEED = 0x0F
SYNTH_CONTROL = 17  # h: bit 4 keeps the wave and scan, bit 0 the envelope
WAVE_SPEED = 18  # i
ARPEGGIO_SPEED = 19  # j
SYNTH_DRUMS = 26  # q
TRACK_VOLUME = 29  # t
WAVE_HOLD = 30  # u: low nibble keeps the scan, high nibble freezes it
EXTERNAL_EVENT = 33  # x
ROW_TICK_COMMANDS = {PORTAMENTO_UP, PORTAMENTO_DOWN, TONE_SLIDE, VIBRATO, VOLUME_SLIDE}
KEEP_WAVE, KEEP_ENVELOPE = 0x10, 0x01  # SYNTH_CONTROL's bits
SLIDE_COMMANDS = {TONE_SLIDE}  # and two combined slides, not modelled

PERIODS = (  # fine tune 0: notes 1 to 60
    *(3424, 3232, 3048, 2880, 2712, 2560, 2416, 2280, 2152, 2032, 1920, 1812),
    *(1712, 1616, 1524, 1440, 1356, 1280, 1208, 1140, 1076, 1016, 960, 906),
    *(856, 808, 762, 720, 678, 640, 604, 570, 538, 508, 480, 453),
    *(428, 404, 381, 360, 339, 320, 302, 285, 269, 254, 240, 226),
    *(214, 202, 190, 180, 170, 160, 151, 143, 135, 127, 120, 113),
)

VIBRATO_SINE = bytes(  # half a cycle, 32 steps; the sign flips per half
    (0, 24, 49, 74, 97, 120, 141, 161, 180, 197, 212, 224, 235, 244, 250, 253)
    + (255, 253, 250, 244, 235, 224, 212, 197, 180, 161, 141, 120, 97, 74, 49, 24)
)
VIBRATO_RAMP = bytes([255, *range(248, 0, -8)])
VIBRATO_SQUARE = bytes([255] * 32)
VIBRATO_WAVES = (VIBRATO_SINE, VIBRATO_RAMP, VIBRATO_SQUARE)
VIBRATO_OFF = 3  # an instrument's vibrato wave: none


# --- What the composer edits -------------------------------------------


@dataclass
class Instrument:  # 32 bytes in the INST chunk
    kind: int  # +0: SAMPLE or SYNTH
    volume: int  # +1: 0 to 64
    fine_tune: int  # +2
    wave: int  # +3: one of 64 waves
    # SAMPLE: words
    start: int = 0  # +4
    length: int = 0  # +8
    loop_start: int = 0  # +12
    loop_length: int = 0  # +16: 0, no loop
    # SYNTH
    part_words: int = 0  # +4: words per part
    vibrato: int = 0  # +10: speed and depth, as the vibrato command
    vibrato_delay: int = 0  # +11: ticks
    vibrato_wave: int = 0  # +12: sine, ramp, square, or VIBRATO_OFF
    scan_speed: int = 0  # +13: ticks per part
    scan_parts: int = 0  # +14: parts in the first pass
    scan_loop: int = 0  # +15: the loop's first part
    scan_loop_parts: int = 0  # +16
    scan_mode: int = FORWARD  # +17
    # Both: the envelope, from 0 to 127
    attack_start: int = 0  # +28
    attack_step: int = 0  # +29: 0, no envelope
    decay_end: int = 0  # +30
    decay_step: int = 0  # +31


@dataclass
class Score:
    positions: bytes  # PLST: a pattern number per position
    last_position: int  # INFO byte 1
    restart: int  # INFO byte 2
    patterns: bytes  # PATT: PATTERN_SIZE bytes each
    arpeggios: bytes  # ARPG: 16 tables
    instruments: list[Instrument]
    waves: list[bytes]  # WAVE, cut by the lengths in WLEN


# --- Replay state --------------------------------------------------------


@dataclass
class Voice:
    number: int
    new: int = 0  # NEW_START, NEW_LOOP, both or none
    last_note: int = 0
    instrument: Instrument | None = None
    synth: bool = False
    wave: bytes = b""
    start: int = 0  # bytes into `wave`
    length: int = 0  # words
    loop: int = 0  # bytes into `wave`
    loop_length: int = 0  # words
    volume: int = 0
    track_volume: int = FULL_VOLUME
    period: int = 0  # from the arpeggio; vibrato adds to it
    slide: int = 0  # added to the period
    slide_speed: int = 0
    sliding: bool = False
    command: int = 0
    arg: int = 0
    arpeggio: list[int] = field(default_factory=lambda: [0])  # period indices; -1 ends
    arpeggio_at: int = 0
    arpeggio_speed: int = 0
    arpeggio_count: int = 0
    # Scan: byte offsets into the wave
    scan_at: int = 0
    scan_end: int = 0
    scan_loop: int = 0
    scan_loop_end: int = 0
    scan_step: int = 0  # bytes per step; negative runs backwards
    scan_count: int = 0
    scan_speed: int = 0
    scan_mode: int = FORWARD
    scan_keep: int = 0  # WAVE_HOLD's low nibble
    scan_frozen: int = 0  # WAVE_HOLD's high nibble
    # Envelope
    level: int = ENVELOPE_TOP
    envelope: int = 0  # 0 off, 1 attack, 2 decay
    attack_step: int = 0
    decay_step: int = 0
    decay_end: int = 0
    # Vibrato
    vibrato_on: bool = False
    vibrato_continuous: bool = False
    vibrato_delay: int = -1
    vibrato_speed: int = 0
    vibrato_depth: int = 0
    vibrato_wave: int = 0
    vibrato_negative: bool = False
    vibrato_at: int = 0
    vibrato_done: bool = False


@dataclass
class Shadow:  # 16 bytes per voice: what the mixer takes
    wave: bytes = b""
    start: int = 0
    length: int = 0  # words
    period: int = 0
    flags: int = 0
    volume: int = 0
    loop_wave: bytes = b""  # a new sample instrument's, while the old one plays
    loop: int = 0
    loop_length: int = 0  # words


@dataclass
class MixVoice:
    wave: bytes = b""
    start: int = 0
    at: int = 0  # 16.16 bytes into the playing part
    size: int = 0  # bytes in the playing part
    loop_wave: bytes = b""
    loop: int = 0
    loop_size: int = 0
    step: int = 0  # 16.16 bytes per mixed byte
    volume: int = 0
    playing: bool = False


@dataclass
class Module:
    score: Score
    amiga: Amiga
    voices: list[Voice] = field(default_factory=list)
    shadows: list[Shadow] = field(default_factory=list)
    mixed: list[MixVoice] = field(default_factory=list)
    volume_table: list[bytes] = field(default_factory=list)  # 65 × 256
    buffers: list[tuple[bytearray, bytearray]] = field(default_factory=list)
    speed: int = SPEED
    tempo: int = TEMPO
    tick: int = 0
    position: int = 0
    row: int = 0
    event: int = 0  # EXTERNAL_EVENT's argument, for the game or demo
    on_song_end: Callable[[], None] | None = None


# --- Start -------------------------------------------------------------


def load_module(data: bytes) -> Score:
    """Chunks: a 4-byte name and a length, at any even offset."""

    def chunk(name: bytes) -> int:
        at = 0
        while data[at : at + 4] != name:
            at += 2
            if at >= len(data):
                raise ValueError(f"no {name!r} chunk")
        return at + 8

    info, plst, patt = chunk(b"INFO"), chunk(b"PLST"), chunk(b"PATT")
    inst, wlen, wave = chunk(b"INST"), chunk(b"WLEN"), chunk(b"WAVE")
    arpg = chunk(b"ARPG")
    instruments = [
        read_instrument(
            data[inst + n * INSTRUMENT_SIZE : inst + (n + 1) * INSTRUMENT_SIZE]
        )
        for n in range(INSTRUMENTS)
    ]
    waves, at = [], wave
    for n in range(WAVES):
        size = int.from_bytes(data[wlen + 4 * n : wlen + 4 * n + 4], "big")
        waves.append(data[at : at + size])
        at += size
    last = data[info + 1]
    return Score(
        positions=data[plst : plst + last],
        last_position=last,
        restart=data[info + 2],
        patterns=data[patt:],
        arpeggios=data[arpg : arpg + 16 * ARPEGGIO_SIZE],
        instruments=instruments,
        waves=waves,
    )


def read_instrument(raw: bytes) -> Instrument:
    def long(at: int) -> int:
        return int.from_bytes(raw[at : at + 4], "big")

    inst = Instrument(raw[0], raw[1], raw[2], raw[3])
    if inst.kind == SAMPLE:
        inst.start, inst.length = long(4), long(8)
        inst.loop_start, inst.loop_length = long(12), long(16)
    else:
        inst.part_words = raw[4]
        inst.vibrato, inst.vibrato_delay, inst.vibrato_wave = raw[10], raw[11], raw[12]
        inst.scan_speed, inst.scan_parts = raw[13], raw[14]
        inst.scan_loop, inst.scan_loop_parts, inst.scan_mode = raw[15], raw[16], raw[17]
    inst.attack_start, inst.attack_step = raw[28], raw[29]
    inst.decay_end, inst.decay_step = raw[30], raw[31]
    return inst


def Init(score: Score, amiga: Amiga) -> Module:
    """The CIA timer runs Play. Each Paula channel plays a 128-byte
    buffer at MIX_PERIOD, and its audio interrupt runs MixInterrupt.
    Channel 3 starts on channel 2's buffer (bug): it plays it once."""
    module = Module(score, amiga)
    module.voices = [Voice(n) for n in range(VOICES)]
    module.shadows = [Shadow() for _ in range(VOICES)]
    module.mixed = [MixVoice() for _ in range(VOICES)]
    module.buffers = [(bytearray(MIX_BUFFER), bytearray(MIX_BUFFER)) for _ in range(4)]
    MixInit(module)
    for n, channel in enumerate(amiga.paula.channels):
        first = module.buffers[min(n, 2)][0]
        channel.period = MIX_PERIOD
        channel.set_volume(FULL_VOLUME)
        channel.on_irq(lambda ch: MixInterrupt(module, ch))
        channel.play(paula.Sample(first))
    amiga.timer.on_underflow = lambda: Play(module)
    set_tempo(module, TEMPO)
    amiga.timer.start()
    return module


def set_tempo(module: Module, tempo: int) -> None:
    module.tempo = tempo
    module.amiga.timer.set_latch(TIMER_BASE // tempo)


# --- Tick --------------------------------------------------------------


def Play(module: Module) -> None:
    """A row every `speed` ticks, then every voice's effects, then the
    shadow, then the mixer takes it."""
    module.tick += 1
    if module.speed and module.tick >= module.speed:
        module.tick = 0
        PlayNewStep(module)
    PlayEffects(module)
    StartMixVoices(module)


def PlayNewStep(module: Module) -> None:
    score = module.score
    pattern = score.positions[module.position]
    row = pattern * PATTERN_SIZE + module.row * VOICES * CELL
    for voice in module.voices:
        at = row + voice.number * CELL
        ReadCell(module, voice, score.patterns[at : at + CELL])
    module.row += 1
    if module.row < ROWS:
        return
    module.row = 0
    module.position += 1
    if module.position >= score.last_position:
        module.position = score.restart
        if module.on_song_end:
            module.on_song_end()


def PlayEffects(module: Module) -> None:
    """Effects for all eight voices, then their shadows: first period,
    volume and start, then the loop."""
    for voice in module.voices:
        EffectsTick(module, voice)
    for voice, shadow in zip(module.voices, module.shadows):
        WriteShadow(voice, shadow)
    for voice, shadow in zip(module.voices, module.shadows):
        WriteShadowLoop(voice, shadow)


def ReadCell(module: Module, voice: Voice, cell: bytes) -> None:
    """Without an instrument number, a note replays the last instrument
    and keeps the volume. With a tone slide, the note only sets the
    slide's target. An instrument number without a note keeps the note:
    a new sample instrument then changes only the loop. A row with no
    note still picks a new arpeggio for the last note."""
    note, number = cell[0] & 0x3F, cell[1] & 0x3F
    voice.command, voice.arg = cell[2] & 0x3F, cell[3]
    sliding = voice.command in SLIDE_COMMANDS
    if not number:
        inst = voice.instrument
        if inst is None:
            return
        if note and not sliding:
            start_note(module, voice, inst, note)
    else:
        inst = module.score.instruments[number - 1]
        if not note:
            if inst.kind == SAMPLE and inst is not voice.instrument:
                voice.instrument = inst
                voice.new = NEW_LOOP
                StartSample(module, voice, inst, restart=False)
        elif not (inst is voice.instrument and sliding):
            voice.instrument = inst
            start_note(module, voice, inst, note)
        voice.volume = inst.volume
    if not note:
        note = voice.last_note
        if not note or note > LAST_NOTE:
            return
    else:
        voice.sliding = False
        voice.last_note = note
        if note > LAST_NOTE:
            return
    PickArpeggio(module, voice, cell, note)


def start_note(module: Module, voice: Voice, inst: Instrument, note: int) -> None:
    voice.vibrato_continuous = False
    InitEnvelope(voice, inst)
    if inst.kind == SYNTH:
        StartSynth(module, voice, inst, note)
    else:
        StartSample(module, voice, inst, restart=True)


def StartSynth(module: Module, voice: Voice, inst: Instrument, note: int) -> None:
    """The same wave as before plays on: no restart. With the scan held,
    the scan runs on too. Otherwise the scan starts again from the
    first part, and the loop is the first loop part. The step counter
    starts full: the first step comes one tick later, at any speed."""
    voice.synth = True
    if not note:
        return
    voice.slide = 0
    control = voice.arg if voice.command == SYNTH_CONTROL else 0
    if not control & KEEP_WAVE:
        voice.new = NEW_START | NEW_LOOP
        wave = module.score.waves[inst.wave]
        if wave is voice.wave:
            voice.new = 0
            if voice.scan_keep:
                start_vibrato(voice, inst)
                return
        voice.wave = wave
        if not voice.scan_frozen:
            part = 2 * inst.part_words
            voice.start, voice.length = 0, inst.part_words
            voice.loop_length = inst.part_words
            voice.scan_at, voice.scan_step = 0, part
            voice.scan_end = inst.scan_parts * part
            voice.scan_loop = voice.loop = inst.scan_loop * part
            voice.scan_loop_end = (inst.scan_loop + inst.scan_loop_parts) * part
            voice.scan_count = voice.scan_speed = inst.scan_speed
            voice.scan_mode = inst.scan_mode
    start_vibrato(voice, inst)


def start_vibrato(voice: Voice, inst: Instrument) -> None:
    """A synth instrument's own vibrato starts after its delay and runs
    for the whole note."""
    voice.vibrato_on = False
    if inst.vibrato_wave == VIBRATO_OFF:
        voice.vibrato_delay = -2
        return
    voice.vibrato_delay = inst.vibrato_delay
    if not inst.vibrato:
        voice.vibrato_delay = -2
        return
    vibrato_parameters(voice, inst.vibrato)
    voice.vibrato_wave = inst.vibrato_wave
    voice.vibrato_continuous = True


def StartSample(module: Module, voice: Voice, inst: Instrument, restart: bool) -> None:
    """A sample plays to its loop's end, then loops. Without a loop, the
    loop is one silent word; the mixer then stops the voice."""
    if restart:
        voice.synth = False
        voice.vibrato_delay = -2
        voice.new = NEW_START | NEW_LOOP
        voice.slide = 0
    voice.wave = module.score.waves[inst.wave]
    voice.start = 2 * inst.start
    if inst.loop_length:
        voice.loop, voice.loop_length = 2 * inst.loop_start, inst.loop_length
        voice.length = inst.loop_start + inst.loop_length
    else:
        voice.loop, voice.loop_length = len(voice.wave), 1
        voice.length = inst.length


def PickArpeggio(module: Module, voice: Voice, cell: bytes, note: int) -> None:
    """The cell's spare bits pick an arpeggio table. Its first byte holds
    the count and the first offset, then two offsets per byte, in
    semitones up. An empty table holds the note. ARPEGGIO with an
    argument overrides the table, as in ProTracker. A tone slide aims at
    the new note."""
    table = (cell[2] >> 6) << 2 | (cell[1] >> 6)
    base = note - 1
    if voice.command == TONE_SLIDE and cell[0] & 0x3F:
        voice.sliding = True
        voice.slide += voice.period - PERIODS[base]
    if len(voice.arpeggio) < 2 or voice.arpeggio[1] < 0:
        voice.arpeggio_at = voice.arpeggio_count = 0
    if voice.command == ARPEGGIO and voice.arg:
        voice.arpeggio = [base, base + (voice.arg >> 4), base + (voice.arg & 0x0F), -1]
        return
    raw = module.score.arpeggios[table * ARPEGGIO_SIZE : (table + 1) * ARPEGGIO_SIZE]
    count = raw[0] >> 4
    if not count:
        voice.arpeggio_at = 0
        voice.arpeggio_count = voice.arpeggio_speed - 1
        voice.arpeggio = [base, -1]
        return
    offsets = [raw[0] & 0x0F]
    for byte in raw[1:]:
        offsets += [byte >> 4, byte & 0x0F]
    voice.arpeggio = [base + n for n in offsets[: min(count, ARPEGGIO_STEPS - 1)]] + [
        -1
    ]


def InitEnvelope(voice: Voice, inst: Instrument) -> None:
    """An attack to 127, then a decay to the end level. SYNTH_CONTROL's
    bit 0 keeps the running envelope."""
    if voice.command == SYNTH_CONTROL and voice.arg & KEEP_ENVELOPE:
        return
    if not inst.attack_step:
        voice.level, voice.envelope = ENVELOPE_TOP, 0
        return
    voice.level, voice.envelope = inst.attack_start, 1
    voice.attack_step, voice.decay_step = inst.attack_step, inst.decay_step
    voice.decay_end = inst.decay_end


# --- Every tick, per voice ---------------------------------------------


def EffectsTick(module: Module, voice: Voice) -> None:
    """The arpeggio steps every `arpeggio speed` ticks; each step sets
    the period. Then the command, then SynthTick. Slides and vibrato
    skip the row's first tick. Past note 60 an arpeggio reads the next
    fine tune's low notes (bug); here it stays on note 60."""
    if not voice.vibrato_continuous:
        voice.vibrato_on = False
    voice.arpeggio_count += 1
    if voice.arpeggio_count >= voice.arpeggio_speed:
        voice.arpeggio_count = 0
        if voice.arpeggio[voice.arpeggio_at] < 0:
            voice.arpeggio_at = 0
        index = voice.arpeggio[voice.arpeggio_at]
        voice.period = PERIODS[min(index, LAST_NOTE - 1)]
        voice.arpeggio_at = (voice.arpeggio_at + 1) % len(voice.arpeggio)
    command, arg = voice.command, voice.arg
    if not (module.tick == 0 and command in ROW_TICK_COMMANDS):
        handler = COMMANDS.get(command)
        if handler:
            handler(module, voice, arg)
    SynthTick(voice)


def SynthTick(voice: Voice) -> None:
    """Every `scan speed` ticks the loop moves one part. At the end of
    the first pass, or of the loop, the scan mode decides: back to the
    loop's first part, from its last part backwards, or turn. The loop
    changes, not the playing part: the mixer takes it at the part's end.
    The envelope runs for samples and waves alike."""
    voice.vibrato_done = False
    if voice.new:
        vibrato_tick(voice)
        return
    if voice.synth and voice.wave and not voice.scan_frozen:
        voice.scan_count += 1
        if voice.scan_count >= voice.scan_speed:
            voice.scan_count = 0
            scan_step(voice)
            voice.new = NEW_LOOP
            voice.loop = voice.scan_at
    if voice.envelope == 1:
        voice.level += voice.attack_step
        if voice.level > ENVELOPE_TOP:
            voice.level, voice.envelope = ENVELOPE_TOP, 2
    elif voice.envelope == 2:
        voice.level -= voice.decay_step
        if voice.level <= voice.decay_end:
            voice.level, voice.envelope = voice.decay_end, 0
    if voice.vibrato_delay == -1:
        voice.vibrato_on = True
    elif voice.vibrato_delay > -1:
        voice.vibrato_delay -= 1
    vibrato_tick(voice)


def scan_step(voice: Voice) -> None:
    voice.scan_at += voice.scan_step
    if voice.scan_step < 0:
        if voice.scan_at >= voice.scan_loop:
            return
    elif voice.scan_at < voice.scan_end:
        return
    if voice.scan_mode == FORWARD:
        voice.scan_at, voice.scan_end = voice.scan_loop, voice.scan_loop_end
    elif voice.scan_mode == BACKWARDS:
        voice.scan_at = voice.scan_loop_end
        voice.scan_step = -abs(voice.scan_step)
        voice.scan_at += voice.scan_step
    else:
        voice.scan_end = voice.scan_loop_end
        voice.scan_at -= voice.scan_step
        voice.scan_step = -voice.scan_step


def vibrato_tick(voice: Voice) -> None:
    if voice.vibrato_on:
        VibratoTick(voice)


def VibratoTick(voice: Voice) -> None:
    """Once per tick. The offset adds to the period that the arpeggio
    last set; without an arpeggio step in between, offsets add up."""
    if voice.vibrato_done:
        return
    voice.vibrato_done = True
    table = VIBRATO_WAVES[min(voice.vibrato_wave, 2)]
    offset = table[voice.vibrato_at] * voice.vibrato_depth >> 7
    voice.period += -offset if voice.vibrato_negative else offset
    voice.vibrato_at += voice.vibrato_speed
    if voice.vibrato_at & 0x20:
        voice.vibrato_at &= 0x1F
        voice.vibrato_negative = not voice.vibrato_negative


def vibrato_parameters(voice: Voice, arg: int) -> None:
    if arg >> 4:
        voice.vibrato_speed = arg >> 4
    if arg & 0x0F:
        voice.vibrato_depth = arg & 0x0F


# --- Commands ----------------------------------------------------------


def CmdPortamentoUp(module: Module, voice: Voice, arg: int) -> None:
    voice.slide -= arg


def CmdPortamentoDown(module: Module, voice: Voice, arg: int) -> None:
    voice.slide += arg


def CmdToneSlide(module: Module, voice: Voice, arg: int) -> None:
    """The slide shrinks toward 0: the period reaches the new note."""
    if arg:
        voice.slide_speed = arg
    if not voice.sliding or not voice.slide:
        return
    if voice.slide > 0:
        voice.slide = max(voice.slide - voice.slide_speed, 0)
    else:
        voice.slide = min(voice.slide + voice.slide_speed, 0)


def CmdVibrato(module: Module, voice: Voice, arg: int) -> None:
    voice.vibrato_on = True
    vibrato_parameters(voice, arg)


def CmdVolumeSlide(module: Module, voice: Voice, arg: int) -> None:
    """With an up nibble, the down nibble counts for nothing."""
    up, down = arg >> 4, arg & 0x0F
    if not up:
        voice.volume = max(voice.volume - down, 0)
    voice.volume = min(voice.volume + up, FULL_VOLUME)


def CmdSetVolume(module: Module, voice: Voice, arg: int) -> None:
    voice.volume = arg


def CmdSetSpeed(module: Module, voice: Voice, arg: int) -> None:
    """Up to MAX_SPEED: ticks per row. Up to MAX_TEMPO: the tempo. 0 ends
    the song."""
    if not arg:
        module.speed = 0
        if module.on_song_end:
            module.on_song_end()
        set_tempo(module, TEMPO)
    elif arg <= MAX_SPEED:
        module.speed = arg
    elif arg <= MAX_TEMPO:
        set_tempo(module, arg)


def CmdWaveSpeed(module: Module, voice: Voice, arg: int) -> None:
    """The high nibble: ticks per scan step, for the playing note."""
    voice.scan_speed = arg >> 4


def CmdArpeggioSpeed(module: Module, voice: Voice, arg: int) -> None:
    if arg & 0x0F:
        voice.arpeggio_speed = arg & 0x0F


def CmdSynthDrums(module: Module, voice: Voice, arg: int) -> None:
    """One command for a drum: the pitch falls by 8 × the high nibble per
    tick, and the volume by the low nibble."""
    voice.slide += (arg >> 4) * 8
    CmdVolumeSlide(module, voice, arg & 0x0F)


def CmdTrackVolume(module: Module, voice: Voice, arg: int) -> None:
    """A second volume per voice, over all its notes."""
    voice.track_volume = arg


def CmdWaveHold(module: Module, voice: Voice, arg: int) -> None:
    """Low nibble: later notes on the same wave keep the scan. High
    nibble: the scan stops where it is."""
    voice.scan_keep, voice.scan_frozen = arg & 0x0F, arg >> 4


def CmdExternalEvent(module: Module, voice: Voice, arg: int) -> None:
    """On the row's tick only: a byte for the game or demo to read."""
    if module.tick == 0:
        module.event = arg


COMMANDS: dict[int, Callable[[Module, Voice, int], None]] = {
    PORTAMENTO_UP: CmdPortamentoUp,
    PORTAMENTO_DOWN: CmdPortamentoDown,
    TONE_SLIDE: CmdToneSlide,
    VIBRATO: CmdVibrato,
    VOLUME_SLIDE: CmdVolumeSlide,
    SET_VOLUME: CmdSetVolume,
    SET_SPEED: CmdSetSpeed,
    WAVE_SPEED: CmdWaveSpeed,
    ARPEGGIO_SPEED: CmdArpeggioSpeed,
    SYNTH_DRUMS: CmdSynthDrums,
    TRACK_VOLUME: CmdTrackVolume,
    WAVE_HOLD: CmdWaveHold,
    EXTERNAL_EVENT: CmdExternalEvent,
}


# --- Output ------------------------------------------------------------


def WriteShadow(voice: Voice, shadow: Shadow) -> None:
    """Period, volume and start, every tick. Volume is the note's volume
    × the envelope / 64 × the track volume / 64. The envelope reaches
    127, so it can double a quiet note; the mixer caps the result at 64.
    The file's unused 4-voice routine halves the level first."""
    shadow.period = max(voice.period + voice.slide, MIN_PERIOD)
    shadow.flags = voice.new
    volume = voice.volume * voice.level >> 6
    shadow.volume = volume * voice.track_volume >> 6
    shadow.wave, shadow.start, shadow.length = voice.wave, voice.start, voice.length


def WriteShadowLoop(voice: Voice, shadow: Shadow) -> None:
    shadow.loop_wave = voice.wave
    shadow.loop, shadow.loop_length = voice.loop, voice.loop_length
    voice.new = 0


# --- Mixer -------------------------------------------------------------


def MixInit(module: Module) -> None:
    """A table per volume, 0 to 64: each signed byte × volume / 128. Two
    voices at half range add without overflow."""
    module.volume_table = [
        bytes(((b - 256 if b > 127 else b) * volume >> 7) & 0xFF for b in range(256))
        for volume in range(FULL_VOLUME + 1)
    ]


def StartMixVoices(module: Module) -> None:
    for shadow, mixed in zip(module.shadows, module.mixed):
        StartMixVoice(shadow, mixed)


def StartMixVoice(shadow: Shadow, mixed: MixVoice) -> None:
    """NEW_START restarts the voice. NEW_LOOP changes only the loop: the
    playing part ends first. The step is MIX_PERIOD / period, in 16.16."""
    if shadow.flags & NEW_START:
        mixed.wave, mixed.start, mixed.at = shadow.wave, shadow.start, 0
        mixed.size, mixed.playing = 2 * shadow.length, True
    if shadow.flags & NEW_LOOP:
        mixed.loop_wave = shadow.loop_wave
        mixed.loop, mixed.loop_size = shadow.loop, 2 * shadow.loop_length
    mixed.volume = min(shadow.volume, FULL_VOLUME)
    if shadow.period:
        mixed.step = (MIX_PERIOD << 16) // shadow.period
    shadow.flags = 0


def MixInterrupt(module: Module, channel: paula.Channel) -> None:
    """Paula has just started the buffer queued last time. Queue the
    other buffer and fill it now: voices 2n and 2n+1 into channel n.
    It plays next, so a change reaches the output within two buffer lengths."""
    n = channel.number
    work, playing = module.buffers[n]
    module.buffers[n] = (playing, work)
    channel.queue(paula.Sample(work))
    MixPair(module, module.mixed[2 * n], module.mixed[2 * n + 1], work)


def MixPair(module: Module, a: MixVoice, b: MixVoice, out: bytearray) -> None:
    """Both voices are resampled; neither plays at its own rate. The
    source counts about 104 cycles per output byte and recommends a
    68020. No interpolation: a linear pass is in the source, commented
    out."""
    for n in range(MIX_BUFFER):
        out[n] = (mix_byte(module, a) + mix_byte(module, b)) & 0xFF


def mix_byte(module: Module, voice: MixVoice) -> int:
    """At the part's end, the loop follows. A loop of SILENT_LOOP bytes
    or less stops the voice."""
    if not voice.playing:
        return 0
    index = voice.at >> 16
    if index >= voice.size:
        voice.wave, voice.start = voice.loop_wave, voice.loop
        voice.size, voice.at = voice.loop_size, 0
        if voice.size <= SILENT_LOOP:
            voice.playing = False
            return 0
        index = 0
    byte = (
        voice.wave[voice.start + index] if voice.start + index < len(voice.wave) else 0
    )
    voice.at += voice.step
    return module.volume_table[voice.volume][byte]
