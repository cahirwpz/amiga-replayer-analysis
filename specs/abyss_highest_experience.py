"""AHX's replay: AHX-BinaryPlayer 2.3d-sp3, inside the DeliTracker player
AHX-DeliPlayer 2.3d-sp3 (Dec 98).

Card: players/AbyssHighestExperience.md. Level 2: the control flow runs.
Each CamelCase function is a LABEL in data/disasm/AbyssHighestExperience.cnf;
each CamelCase class is in the `types:` of
data/annot/AbyssHighestExperience.yaml. Comments name the voice fields by
their offsets in a voice record, $e8 bytes each.

There are no samples. At start the player builds 45 waves: 6 triangles,
6 saws, 32 squares and one noise. It then makes 31 low-pass and 31
high-pass copies of all of them. Each voice owns a 640-byte buffer that
Paula loops forever: DMA starts once and never restarts. A note only
refills the buffer with copies of a wave, and sets period and volume.

A track row holds note, instrument, command and argument. A note with an
instrument starts the instrument's program, the `Performance` list: a
step picks a wave and a note and runs two commands. Pulse width and
filter sweep up and down between two limits.

Left out: DeliTracker's hooks, the CIA resource calls, the voice mute
flag at 39 (no code of the player sets it), and the option to skip the
filter copies.
"""

from dataclasses import dataclass, field

from hardware import paula
from hardware.amiga import Amiga

VOICES = 4
VOICE_SIZE = 0xE8
BUFFER_SIZE = 640  # StartChannels: AUDxLEN 320 words, period $88 until a note
NOTES = 60
MIN_PERIOD, MAX_PERIOD = 0x71, 0xD60
FULL = 0x40  # full volume
UNFILTERED = 0x20  # filter position 32: the plain wave
FILTERS = 31  # copies each side of UNFILTERED
FIRST_COEFFICIENT, COEFFICIENT_STEP = 0x19, 9  # MakeFilters: the filter's rate
DEFAULT_SPEED = 6
TICK_RATES = (14209, 7104, 4736, 3552)  # TickRates: CIA latches, 50 to 200 Hz

# Waves: numbers in a Performance step, minus 1
TRIANGLE, SAW, SQUARE, NOISE = 0, 1, 2, 3
FIRST_SQUARE, NOISE_WAVE = 12, 44  # numbers among the 45 waves
NOISE_SIZE = 0x780

PERIODS = (  # PeriodTable: 0 for no note, then 5 octaves
    0,
    *(3424, 3232, 3048, 2880, 2712, 2560, 2416, 2280, 2152, 2032, 1920, 1812),
    *(1712, 1616, 1524, 1440, 1356, 1280, 1208, 1140, 1076, 1016, 960, 906),
    *(856, 808, 762, 720, 678, 640, 604, 570, 538, 508, 480, 453),
    *(428, 404, 381, 360, 339, 320, 302, 285, 269, 254, 240, 226),
    *(214, 202, 190, 180, 170, 160, 151, 143, 135, 127, 120, 113),
)
SINE_QUARTER = (
    0,
    24,
    49,
    74,
    97,
    120,
    141,
    161,
    180,
    197,
    212,
    224,
    235,
    244,
    250,
    253,
)
SINE_TOP = 255

# Track commands, the row's low nibble of byte 1
JUMP_HIGH, SLIDE_UP, SLIDE_DOWN, TONE_SLIDE, FILTER_SET = 0, 1, 2, 3, 4
TONE_SLIDE_VOLUME, HOST_BYTE, SQUARE_SET, VOLUME_SLIDE = 5, 8, 9, 0xA
POSITION_JUMP, SET_VOLUME, PATTERN_BREAK, EXTENDED, SET_SPEED = 0xB, 0xC, 0xD, 0xE, 0xF
FINE_UP, FINE_DOWN, VIBRATO_DEPTH, FINE_VOL_UP, FINE_VOL_DOWN = 1, 2, 4, 0xA, 0xB
CUT, DELAY = 0xC, 0xD

# Performance commands, 3 bits each
(FILTER_POSITION, PITCH_UP, PITCH_DOWN, SQUARE_POSITION,
 TOGGLE_SWEEPS, STEP_JUMP, STEP_VOLUME, STEP_SPEED) = range(8)  # fmt: skip


# --- What the composer edits -------------------------------------------


@dataclass
class Instrument:  # SetInstrument: 22 bytes, then 4 bytes per step
    volume: int  # 0
    wave_length: int  # 1, bits 0-2: wave of 4 << n bytes
    filter_speed: int  # 1 bits 3-7, 12 bit 7, 19 bit 7: 7 bits
    attack_frames: int  # 2
    attack_volume: int  # 3
    decay_frames: int  # 4
    decay_volume: int  # 5
    sustain_frames: int  # 6
    release_frames: int  # 7
    release_volume: int  # 8
    filter_limits: tuple[int, int]  # 12, 19: bits 0-6
    vibrato_delay: int  # 13
    cut_release: bool  # 14, bit 7
    cut_frames: int  # 14, bits 4-6
    vibrato_depth: int  # 14, bits 0-3
    vibrato_speed: int  # 15
    square_limits: tuple[int, int]  # 16, 17
    square_speed: int  # 18
    step_speed: int  # 20
    steps: list[bytes]  # 21: count, then 4 bytes each


@dataclass
class Song:  # InitModule: "THX", revision, then the header
    revision: int  # 3: 0 or 1; 1 adds commands 4xx and Performance 0
    empty_track0: bool  # 6, bit 15: track 0 is not stored
    tick_rate: int  # 6, bits 13-14: TickRates index
    positions: list[list[tuple[int, int]]]  # 8 bytes: track, transpose × 4
    restart: int  # 8
    track_length: int  # 10: rows per track
    tracks: list[bytes]  # 3 bytes per row
    instruments: list[Instrument]  # numbered from 1
    subsongs: list[int]  # 13: count, then first positions


# --- Waves ---------------------------------------------------------------


@dataclass
class Waves:  # MakeWaves: the 45 waves, then the copies
    """`sets[f]` holds all 45 waves through filter position f, 1 to 63.
    Below 32 low-pass, above 32 high-pass; further from 32 is stronger."""

    sets: dict[int, list[bytes]] = field(default_factory=dict)

    def wave(self, position: int, number: int) -> bytes:
        return self.sets[position][number]


def signed(byte: int) -> int:
    return byte - 256 if byte & 0x80 else byte


def MakeWaves() -> Waves:
    """Built once, before any module. The file that ENV:EaglePlayer/ahx
    names can hold all waves; if it loads in full, nothing is built."""
    plain = [MakeTriangle(4 << n) for n in range(6)]
    plain += [make_saw(4 << n) for n in range(6)]
    plain += MakeSquares()
    plain.append(MakeNoise())
    waves = Waves({UNFILTERED: plain})
    MakeFilters(waves, plain)
    return waves


def MakeTriangle(length: int) -> bytes:
    """A rise from 0 to 127 and back over the first half, then the same,
    negated."""
    quarter = length // 4
    step = 128 // quarter
    half = [step * i for i in range(quarter)] + [127]
    half += [128 - step * i for i in range(1, quarter)]
    rest = [-128 if s == 127 else -signed(s & 0xFF) for s in half]
    return bytes(v & 0xFF for v in half + rest)


def make_saw(length: int) -> bytes:
    """From -128 up, 256 / (length - 1) per byte, wrapping as a byte."""
    step = 256 // (length - 1)
    return bytes((-128 + step * i) & 0xFF for i in range(length))


def MakeSquares() -> list[bytes]:
    """32 waves of 128 bytes; wave n ends in 2n high bytes."""
    return [bytes([0x80] * (128 - 2 * n) + [0x7F] * (2 * n)) for n in range(1, 33)]


def MakeNoise() -> bytes:
    """1920 bytes from a fixed seed. A byte is the seed's low byte, or a
    full swing when bit 8 is set."""
    seed, out = 0x41595321, bytearray()
    for _ in range(NOISE_SIZE):
        if not seed & 0x100:
            out.append(seed & 0xFF)
        else:
            out.append(0x80 if seed & 0x8000 else 0x7F)
        seed = ror(seed, 5) ^ 0x9A
        low = seed & 0xFFFF
        seed = ror(seed, 30)
        seed ^= (low + seed) & 0xFFFF
        seed = ror(seed, 3)
    return bytes(out)


def ror(value: int, n: int) -> int:
    return ((value >> n) | (value << (32 - n))) & 0xFFFFFFFF


def MakeFilters(waves: Waves, plain: list[bytes]) -> None:
    """A two-stage filter runs once over each wave. It gives the
    high-pass and the low-pass copy at once. The rate grows by 9 per
    copy, from 25.

    Its start state comes from FilterStartStates: 31 × 45 pairs. They
    equal three warm-up passes over the wave, low 8 bits cleared (checked
    for all 1395 pairs). So a copy loops without a jump at its end."""
    coefficient = FIRST_COEFFICIENT
    for n in range(FILTERS):
        lows, highs = [], []
        for wave in plain:
            low, band = warm_up(wave, coefficient)
            low_pass, high_pass = bytearray(), bytearray()
            for byte in wave:
                high, low, band = filter_step(signed(byte), low, band, coefficient)
                high_pass.append((high >> 16) & 0xFF)
                low_pass.append((band >> 16) & 0xFF)
            lows.append(bytes(low_pass))
            highs.append(bytes(high_pass))
        waves.sets[1 + n] = lows  # position 1 filters most
        waves.sets[UNFILTERED + 1 + n] = highs  # position 33 filters least
        coefficient += COEFFICIENT_STEP


def warm_up(wave: bytes, coefficient: int) -> tuple[int, int]:
    """What FilterStartStates holds, computed."""
    low = band = 0
    for _ in range(3):
        for byte in wave:
            _, low, band = filter_step(signed(byte), low, band, coefficient)
    return low & ~0xFF, band & ~0xFF


def filter_step(sample: int, low: int, band: int, k: int) -> tuple[int, int, int]:
    """16.16 values, each clipped to a signed byte in its high word."""
    high = clip((sample << 16) - low - band)
    low = clip(low + (high >> 8) * k)
    band = clip(band + (low >> 8) * k)
    return high, low, band


def clip(value: int) -> int:
    top = value >> 16
    return 127 << 16 if top > 127 else -128 << 16 if top < -128 else value


# --- Voice state -------------------------------------------------------


@dataclass
class Sweep:  # SquareSweep 63-70, FilterSweep 71-79
    """A position that runs between two limits and turns at each one.
    Started outside the limits, it first runs in without turning."""

    on: bool = False  # 63, 71
    restarted: bool = False  # 64, 72: set by a toggle
    wait: int = 0  # 65, 73
    limits: tuple[int, int] = (0, 0)  # 66-67, 74-75
    position: int = 0  # 68, 76
    sign: int = 1  # 69, 77
    entering: bool = False  # 70, 79

    def move(self) -> None:
        low, high = self.limits
        if self.restarted:
            self.restarted = False
            if self.position <= low:
                self.entering, self.sign = True, 1
            elif self.position >= high:
                self.entering, self.sign = True, -1
        if self.position in (low, high):
            if self.entering:
                self.entering = False
            else:
                self.sign = -self.sign
        self.position += self.sign


@dataclass
class Voice:  # ClearVoice: VOICE_SIZE bytes each
    channel: paula.Channel
    buffer: bytearray  # 92: in chip memory; Paula loops it
    track: int = 0  # 0
    transpose: int = 0  # 1
    next_track: int = 0  # 2: the next position's, for HardCut
    envelope: int = 0  # 4: 8.8 volume
    phase_frames: list[int] = field(default_factory=lambda: [0, 0, 0, 0])  # 6-9
    phase_deltas: list[int] = field(default_factory=lambda: [0, 0, 0])  # 10, 12, 14
    instrument: Instrument | None = None  # 16
    wave: int = TRIANGLE  # 20
    wave_length: int = 0  # 21
    step_note: int = 0  # 22
    track_note: int = 0  # 24
    vibrato_offset: int = 0  # 26
    note_volume: int = 0  # 29
    step_volume: int = FULL  # 31
    track_volume: int = FULL  # 33
    new_wave: bool = False  # 34
    rebuild_square: bool = False  # 35
    skip_square_set: bool = False  # 37: ignore the next Performance 3
    new_period: bool = False  # 38
    fixed_note: bool = False  # 40
    volume_up: int = 0  # 41
    volume_down: int = 0  # 42
    cut_frames: int = 0  # 43
    cut_release: bool = False  # 44
    cut_release_frames: int = 0  # 45
    slide_speed: int = 0  # 46
    slide_offset: int = 0  # 48: period offset
    slide_target: int = 0  # 50
    sliding: bool = False  # 52
    tone_slide: bool = False  # 53
    pitch_speed: int = 0  # 54: Performance slide
    pitch_offset: int = 0  # 56
    pitch_sliding: bool = False  # 58
    vibrato_delay: int = 0  # 59
    vibrato_position: int = 0  # 60
    vibrato_depth: int = 0  # 61
    vibrato_speed: int = 0  # 62
    square: Sweep = field(default_factory=Sweep)
    filter: Sweep = field(default_factory=lambda: Sweep(position=UNFILTERED))
    filter_speed: int = 0  # 78
    pending_filter: int = 0  # 80: from command 4xx, for Performance 0
    step: int = 0  # 81
    step_speed: int = 0  # 82
    step_wait: int = 0  # 83
    delay_wait: int = 0  # 88
    delaying: bool = False  # 89
    cut_wait: int = 0  # 90
    cutting: bool = False  # 91
    source: bytes = b""  # 96: the wave to copy
    period: int = 0  # 100
    volume: int = 0  # 102
    square_wave: bytes = b""  # 104: the resampled square


@dataclass
class Player:  # WorkArea: the global state, then four voice records
    song: Song
    waves: Waves
    amiga: Amiga
    voices: list[Voice] = field(default_factory=list)
    master_volume: int = FULL  # 1: DeliTracker's volume
    host_byte: int = 0  # 0: command 8xx writes it for the host
    song_end: bool = False  # 3
    playing: bool = False  # 4
    speed: int = DEFAULT_SPEED  # 949
    countdown: int = 0  # 944: ticks left in the row
    new_position: bool = False  # 946
    jump: bool = False  # 950
    jump_position: int = 0  # 956
    jump_row: int = 0  # 958
    noise_seed: int = 0  # 960
    sine: list[int] = field(default_factory=list)  # 964: 64 words
    row: int = 0  # 1098
    position: int = 0  # 1100


def StartChannels(amiga: Amiga, waves: Waves, song: Song) -> Player:
    """DMA starts once, on four silent buffers, and never stops while the
    player runs. It also switches the Amiga's audio filter off. The
    vibrato sine is a quarter wave from SineQuarter, mirrored."""
    player = Player(song, waves, amiga)
    for channel in amiga.paula.channels:
        buffer = bytearray(BUFFER_SIZE)
        channel.period = 0x88
        channel.set_volume(0)
        channel.play(paula.Sample(buffer))
        player.voices.append(Voice(channel, buffer))
    half = [*SINE_QUARTER, SINE_TOP, *SINE_QUARTER[:0:-1]]
    player.sine = half + [-v for v in half]
    return player


def InitModule(amiga: Amiga, player: Player) -> None:
    """The header's rate picks the CIA latch: 50, 100, 150 or 200 ticks
    per second."""
    SetTickRate(amiga, player.song.tick_rate, player)


def SetTickRate(amiga: Amiga, rate: int, player: Player) -> None:
    amiga.timer.on_underflow = lambda: PlayTick(player)
    amiga.timer.set_latch(TICK_RATES[rate])
    amiga.timer.start()


def InitSubsong(player: Player, subsong: int) -> None:
    """Subsong 0 starts at position 0; others at their listed position."""
    song = player.song
    player.position = song.subsongs[subsong - 1] if subsong else 0
    player.speed, player.countdown, player.row = DEFAULT_SPEED, 0, 0
    player.new_position, player.song_end, player.playing = True, False, True
    player.jump_position = player.host_byte = 0
    for voice in player.voices:
        ClearVoice(voice)


def ClearVoice(voice: Voice) -> None:
    """All fields to 0 but the buffer; track volume to 64."""
    fresh = Voice(voice.channel, voice.buffer)
    for name in fresh.__dataclass_fields__:
        setattr(voice, name, getattr(fresh, name))


# --- Tick ---------------------------------------------------------------


def PlayTick(player: Player) -> None:
    """Paula first: WriteVoice writes what the last tick computed. Then,
    at a row's start, each voice reads its row. Then one frame per
    voice."""
    if not player.playing:
        return
    for voice in player.voices:
        WriteVoice(player, voice)
    if not player.countdown:
        if player.new_position:
            ReadPosition(player)
        for voice in player.voices:
            ReadRow(player, voice)
        player.countdown = player.speed
    for voice in player.voices:
        VoiceFrame(player, voice)
    AdvanceRow(player)


def ReadPosition(player: Player) -> None:
    """Each voice takes its track and transpose, and the next position's
    track for HardCut. The next position wraps to 0, not to the restart."""
    song = player.song
    here = song.positions[player.position]
    after = song.positions[(player.position + 1) % len(song.positions)]
    for voice, (track, transpose), (next_track, _) in zip(player.voices, here, after):
        voice.track, voice.transpose, voice.next_track = track, transpose, next_track
    player.new_position = False


def AdvanceRow(player: Player) -> None:
    """At the row's end: the next row, or a jump. After the last position
    comes the restart position."""
    player.countdown -= 1
    if player.countdown:
        return
    if not player.jump:
        player.row += 1
        if player.row != player.song.track_length:
            return
        player.jump_position = player.position + 1
    player.jump = False
    player.row, player.jump_row = player.jump_row, 0
    player.position, player.jump_position = player.jump_position, 0
    if player.position == len(player.song.positions):
        player.song_end = True
        player.position = player.song.restart
    player.new_position = True


def row_of(player: Player, track: int, row: int) -> tuple[int, int, int, int]:
    """(note, instrument, command, argument): 6, 6, 4 and 8 bits."""
    song = player.song
    if song.empty_track0 and track == 0:
        return 0, 0, 0, 0
    data = song.tracks[track][3 * row : 3 * row + 3]
    word = data[0] << 8 | data[1]
    return word >> 10, (word >> 4) & 0x3F, word & 0xF, data[2]


def ReadRow(player: Player, voice: Voice) -> None:
    """Commands act first, then the instrument, then the note. A note
    with TONE_SLIDE or TONE_SLIDE_VOLUME slides from the last note instead
    of playing.

    EDx delays the whole row by x ticks: VoiceFrame reads it again. ECx
    cuts the note after x ticks, with no release. Both need x < speed."""
    voice.volume_up = voice.volume_down = 0
    note, number, command, arg = row_of(player, voice.track, player.row)
    high, low = arg >> 4, arg & 0xF
    if command == EXTENDED and high == CUT and low < player.speed:
        voice.cut_wait = low
        if low:
            voice.cutting, voice.cut_release = True, False
    if command == EXTENDED and high == DELAY:
        if voice.delaying:
            voice.delaying = False
        elif low < player.speed:
            voice.delay_wait = low
            if low:
                voice.delaying = True
                return
    song_commands(player, voice, command, arg)
    if number:
        SetInstrument(voice, player.song.instruments[number - 1])
    if command == SQUARE_SET:
        voice.square.position = arg >> (5 - voice.wave_length)
        voice.rebuild_square = voice.skip_square_set = True
    if command == FILTER_SET and player.song.revision:
        if arg < 0x40:
            voice.pending_filter = arg
        else:
            voice.filter.position = arg - 0x40
    read_note(voice, note, command, arg)
    voice_commands(player, voice, command, arg)


def song_commands(player: Player, voice: Voice, command: int, arg: int) -> None:
    """Commands on the song: jumps, speed, the host byte. A position
    jump Bxy is decimal; 0x sets its hundreds."""
    if command == JUMP_HIGH and arg and arg & 0xF <= 9:
        player.jump_position = arg & 0xF
    elif command == HOST_BYTE:
        player.host_byte = arg
    elif command == PATTERN_BREAK:
        player.jump_position = player.position + 1
        player.jump_row = (arg >> 4) * 10 + (arg & 0xF)
        if player.jump_row >= player.song.track_length:
            player.jump_row = 0
        player.jump = True
    elif command == POSITION_JUMP:
        player.jump_position = player.jump_position * 100 + decimal(arg)
        player.jump = True
    elif command == SET_SPEED:
        player.speed = arg
    elif command in (TONE_SLIDE_VOLUME, VOLUME_SLIDE):
        voice.volume_up, voice.volume_down = arg >> 4, arg & 0xF


def decimal(arg: int) -> int:
    return (arg >> 4) * 10 + (arg & 0xF)


def read_note(voice: Voice, note: int, command: int, arg: int) -> None:
    """A tone slide keeps the old note and slides the period offset to
    the new note's. A slide of 0 plays the note."""
    voice.sliding = False
    if command in (TONE_SLIDE, TONE_SLIDE_VOLUME):
        if command == TONE_SLIDE and arg:
            voice.slide_speed = arg
        if not note:
            voice.sliding = voice.tone_slide = True
            return
        distance = period_of(voice.track_note) - period_of(note)
        if distance + voice.slide_offset:
            voice.slide_target = -distance
            voice.sliding = voice.tone_slide = True
            return
    if note:
        voice.track_note, voice.new_period = note, True


def voice_commands(player: Player, voice: Voice, command: int, arg: int) -> None:
    """Slides, fine changes and volumes. Cxx sets the note volume up to
    $40; $50-$90 sets the track volume of all voices; $a0-$e0 of this
    voice."""
    high, low = arg >> 4, arg & 0xF
    if command in (SLIDE_UP, SLIDE_DOWN):
        voice.slide_speed = -arg if command == SLIDE_UP else arg
        voice.sliding, voice.tone_slide = True, False
    elif command == EXTENDED and high in (FINE_UP, FINE_DOWN):
        voice.slide_offset += -low if high == FINE_UP else low
        voice.new_period = True
    elif command == EXTENDED and high == VIBRATO_DEPTH:
        voice.vibrato_depth = low
    elif command == EXTENDED and high == FINE_VOL_UP:
        voice.note_volume = min(voice.note_volume + low, FULL)
    elif command == EXTENDED and high == FINE_VOL_DOWN:
        voice.note_volume = max(voice.note_volume - low, 0)
    elif command == SET_VOLUME:
        if arg <= FULL:
            voice.note_volume = arg
        elif 0x50 <= arg <= 0x90:
            for other in player.voices:
                other.track_volume = arg - 0x50
        elif 0xA0 <= arg <= 0xE0:
            voice.track_volume = arg - 0xA0


def SetInstrument(voice: Voice, inst: Instrument) -> None:
    """Restarts the envelope, vibrato, both sweeps and the Performance
    list. Limits in the instrument are for the longest wave; shorter
    waves scale them down."""
    voice.instrument = inst
    voice.step_volume, voice.envelope = FULL, 0
    voice.slide_speed = voice.slide_offset = voice.slide_target = 0
    phases = [
        (inst.attack_frames, inst.attack_volume, 0),
        (inst.decay_frames, inst.decay_volume, inst.attack_volume),
        (inst.release_frames, inst.release_volume, inst.decay_volume),
    ]
    voice.phase_frames = [inst.attack_frames, inst.decay_frames]
    voice.phase_frames += [inst.sustain_frames, inst.release_frames]
    voice.phase_deltas = [((b - a) << 8) // max(n, 1) for n, b, a in phases]
    voice.wave_length = inst.wave_length
    voice.note_volume = inst.volume
    voice.vibrato_delay, voice.vibrato_position = inst.vibrato_delay, 0
    voice.vibrato_depth, voice.vibrato_speed = inst.vibrato_depth, inst.vibrato_speed
    voice.vibrato_offset = 0
    voice.cut_release, voice.cut_frames = inst.cut_release, inst.cut_frames
    shift = 5 - inst.wave_length
    low, high = sorted(v >> shift for v in inst.square_limits)
    voice.square = Sweep(limits=(low, high))
    voice.skip_square_set = False
    low, high = sorted(inst.filter_limits)
    voice.filter = Sweep(limits=(low, high), position=UNFILTERED)
    voice.filter_speed, voice.pending_filter = inst.filter_speed, 0
    voice.step, voice.step_wait, voice.step_speed = 0, 0, inst.step_speed


# --- Frame ---------------------------------------------------------------


def VoiceFrame(player: Player, voice: Voice) -> None:
    """Every tick, in this order. Each part sets a flag when its output
    changed; WriteVoice acts on the flags at the next tick."""
    HardCut(player, voice)
    note_cut(voice)
    if voice.delaying:
        if voice.delay_wait:
            voice.delay_wait -= 1
        else:
            ReadRow(player, voice)
    Envelope(voice)
    VolumeSlide(voice)
    Portamento(voice)
    Vibrato(player, voice)
    PerformanceStep(player, voice)
    if voice.pitch_sliding:
        voice.pitch_offset -= voice.pitch_speed
        voice.new_period |= voice.pitch_offset != 0
    SquareSweep(voice)
    FilterSweep(voice)
    BuildSquare(player, voice)
    SelectWave(player, voice)
    VoicePeriod(voice)
    VoiceVolume(player, voice)


def HardCut(player: Player, voice: Voice) -> None:
    """The instrument's cut: look at the next row, in the next position
    if needed. If it starts an instrument, cut this note `cut_frames`
    ticks before that row. Checked each tick until such a row is found."""
    if not voice.cut_frames:
        return
    row, track = player.row + 1, voice.track
    if row == player.song.track_length:
        row, track = 0, voice.next_track
    if not row_of(player, track, row)[1]:
        return
    wait = max(player.speed - voice.cut_frames, 0)
    if not voice.cutting:
        voice.cutting, voice.cut_wait = True, wait
        voice.cut_release_frames = player.speed - wait
    voice.cut_frames = 0


def note_cut(voice: Voice) -> None:
    """At the cut: a release over the remaining ticks, if the instrument
    asks for it; else the note volume drops to 0."""
    if not voice.cutting:
        return
    if voice.cut_wait:
        voice.cut_wait -= 1
        return
    voice.cutting = False
    inst = voice.instrument
    if voice.cut_release and inst is not None:
        frames = voice.cut_release_frames or 1
        voice.phase_frames = [0, 0, 0, frames]
        drop = voice.envelope - (inst.release_volume << 8)
        voice.phase_deltas[2] = -int(drop / frames)  # DIVS rounds towards 0
    else:
        voice.note_volume = 0


def Envelope(voice: Voice) -> None:
    """ADSR by frame counts. Attack, decay and release step the volume
    and land on their target; sustain only waits."""
    inst = voice.instrument
    if inst is None:
        return
    targets = (inst.attack_volume, inst.decay_volume, None, inst.release_volume)
    for phase, target in enumerate(targets):
        if not voice.phase_frames[phase]:
            continue
        if target is not None:
            delta = voice.phase_deltas[min(phase, 2)]
            voice.envelope += delta
        voice.phase_frames[phase] -= 1
        if not voice.phase_frames[phase] and target is not None:
            voice.envelope = target << 8
        return


def VolumeSlide(voice: Voice) -> None:
    level = voice.note_volume - voice.volume_down + voice.volume_up
    voice.note_volume = min(max(level, 0), FULL)


def Portamento(voice: Voice) -> None:
    """Moves the period offset by the speed. A tone slide stops at its
    target and turns the speed towards it."""
    if not voice.sliding:
        return
    speed = voice.slide_speed
    if voice.tone_slide:
        gap = voice.slide_offset - voice.slide_target
        if not gap:
            return
        if gap > 0:
            speed = -speed
        if (gap + speed > 0) != (gap > 0):
            voice.slide_offset = voice.slide_target
            voice.new_period = True
            return
    voice.slide_offset += speed
    voice.new_period = True


def Vibrato(player: Player, voice: Voice) -> None:
    """After the delay: sine × depth / 128, added to the period."""
    if not voice.vibrato_depth:
        return
    if voice.vibrato_delay:
        voice.vibrato_delay -= 1
        return
    voice.vibrato_offset = (
        player.sine[voice.vibrato_position] * voice.vibrato_depth
    ) >> 7
    voice.new_period = True
    voice.vibrato_position = (voice.vibrato_position + voice.vibrato_speed) & 0x3F


def PerformanceStep(player: Player, voice: Voice) -> None:
    """Every `step_speed` ticks, one step: 3 bits of command, 3 of
    command, 3 of wave, a fixed flag and 6 bits of note, then the two
    arguments. At the list's end the last step holds; its pitch slide
    stops."""
    inst = voice.instrument
    if inst is None:
        return
    if voice.step == len(inst.steps):
        if voice.step_wait:
            voice.step_wait -= 1
        else:
            voice.pitch_speed = 0
        return
    voice.step_wait -= 1
    if voice.step_wait > 0:
        return
    data = inst.steps[voice.step]
    word = data[0] << 8 | data[1]
    wave = (word >> 7) & 7
    if wave:
        voice.wave, voice.new_wave = wave - 1, True
        voice.pitch_speed = voice.pitch_offset = 0
    voice.pitch_sliding = False
    PerformanceCommand(player, voice, (word >> 10) & 7, data[2])
    PerformanceCommand(player, voice, word >> 13, data[3])
    voice.step += 1  # after a jump too: 5xx goes to step xx, counted from 0
    if note := word & 0x3F:
        voice.step_note, voice.new_period = note, True
        voice.fixed_note = bool(word & 0x40)
    voice.step_wait = voice.step_speed


def PerformanceCommand(player: Player, voice: Voice, command: int, arg: int) -> None:
    """0 sets the filter position, or takes a pending 4xx; revision 1 only.
    4 toggles the square sweep; in revision 1 its low nibble toggles the
    square, its high the filter, and $f starts downwards. 5 jumps to a
    step. 6 sets a volume as Cxx does, with $50-$90 for the step volume."""
    new = player.song.revision
    if command == FILTER_POSITION and new and arg:
        voice.filter.position = voice.pending_filter or arg
        voice.pending_filter, voice.new_wave = 0, True
    elif command in (PITCH_UP, PITCH_DOWN):
        voice.pitch_speed = arg if command == PITCH_UP else -arg
        voice.pitch_sliding = True
    elif command == SQUARE_POSITION:
        if voice.skip_square_set:
            voice.skip_square_set = False
        else:
            voice.square.position = arg >> (5 - voice.wave_length)
    elif command == TOGGLE_SWEEPS:
        if not new or not arg:
            toggle(voice.square, 0)
        else:
            if arg & 0xF:
                toggle(voice.square, arg & 0xF)
            if arg >> 4:
                toggle(voice.filter, arg >> 4)
    elif command == STEP_JUMP:
        voice.step = arg - 1  # PerformanceStep adds 1
    elif command == STEP_VOLUME:
        if arg <= FULL:
            voice.note_volume = arg
        elif 0x50 <= arg <= 0x90:
            voice.step_volume = arg - 0x50
        elif 0xA0 <= arg <= 0xE0:
            voice.track_volume = arg - 0xA0
    elif command == STEP_SPEED:
        voice.step_speed = voice.step_wait = arg


def toggle(sweep: Sweep, nibble: int) -> None:
    sweep.on = not sweep.on
    sweep.restarted = sweep.on
    sweep.sign = -1 if nibble == 0xF else 1


def SquareSweep(voice: Voice) -> None:
    """The pulse width moves one step every `square_speed` ticks, for a
    square wave only."""
    inst = voice.instrument
    if voice.wave != SQUARE or not voice.square.on or inst is None:
        return
    voice.square.wait -= 1
    if voice.square.wait > 0:
        return
    voice.square.move()
    voice.rebuild_square = True
    voice.square.wait = inst.square_speed


def FilterSweep(voice: Voice) -> None:
    """Speeds 0-3 move 5 to 2 steps per tick; from 4 up, one step every
    speed - 3 ticks."""
    if not voice.filter.on:
        return
    voice.filter.wait -= 1
    if voice.filter.wait > 0:
        return
    for _ in range(max(4 - voice.filter_speed, 0) + 1):
        voice.filter.move()
    voice.new_wave = True
    voice.filter.wait = max(voice.filter_speed - 3, 1)


def BuildSquare(player: Player, voice: Voice) -> None:
    """For a square wave, every tick: take square `width` at the filter
    position, and keep every (32 >> length)th byte. A width above 32
    mirrors to 64 - width."""
    if voice.wave != SQUARE and not voice.rebuild_square:
        return
    width = voice.square.position << (5 - voice.wave_length)
    if width > 32:
        width = 64 - width
    number = FIRST_SQUARE + max(width - 1, 0)
    source = player.waves.wave(voice.filter.position, number)
    step = 32 >> voice.wave_length
    voice.square_wave = source[::step][: 4 << voice.wave_length]
    voice.new_wave, voice.rebuild_square = True, False


def SelectWave(player: Player, voice: Voice) -> None:
    """The wave to copy at the next tick: the filter position's copy, of
    4 << length bytes. Noise changes every tick."""
    if voice.wave == NOISE:
        voice.new_wave = True
    if not voice.new_wave:
        return
    if voice.wave == SQUARE:
        voice.source = voice.square_wave
        return
    if voice.wave == NOISE:
        noise = player.waves.wave(voice.filter.position, NOISE_WAVE)
        voice.source = noise[NoiseOffset(player) :]
        return
    number = 6 * voice.wave + voice.wave_length
    voice.source = player.waves.wave(voice.filter.position, number)


def NoiseOffset(player: Player) -> int:
    """An even offset below $500 into the noise, from a new seed each
    tick."""
    seed = player.noise_seed
    offset = seed & 0x4FE
    seed = ror((seed + 0x222B98) & 0xFFFFFFFF, 8)
    seed = ((seed + 0xBEFF3) & 0xFFFFFFFF) ^ 0x4B
    player.noise_seed = (seed - 0x1A4F) & 0xFFFFFFFF
    return offset


def period_of(note: int) -> int:
    """Notes above 60 play note 60. The code has no lower limit; the
    model gives 0 below note 1."""
    return PERIODS[min(note, NOTES)] if note > 0 else 0


def VoicePeriod(voice: Voice) -> None:
    """A fixed note plays the step's note. Else the step's note is added
    to the track note and transpose, and the slide applies. Performance
    slide and vibrato always apply."""
    if voice.fixed_note:
        note, period = voice.step_note, 0
    else:
        note = voice.step_note + voice.transpose + voice.track_note - 1
        period = voice.slide_offset
    period += period_of(min(note, NOTES)) + voice.pitch_offset + voice.vibrato_offset
    voice.period = min(max(period, MIN_PERIOD), MAX_PERIOD)


def VoiceVolume(player: Player, voice: Voice) -> None:
    """Envelope × note × step × track × master volume, each out of 64."""
    level = voice.envelope >> 8
    for factor in (voice.note_volume, voice.step_volume, voice.track_volume):
        level = level * factor >> 6
    voice.volume = level * player.master_volume >> 6


def WriteVoice(player: Player, voice: Voice) -> None:
    """Period if it changed, the buffer if the wave changed, then the
    volume. DMA stays on: the new wave starts wherever Paula is."""
    if voice.new_period:
        voice.channel.period = voice.period
        voice.new_period = False
    if voice.new_wave:
        FillBuffer(voice)
        voice.new_wave = False
    voice.channel.set_volume(voice.volume)


def FillBuffer(voice: Voice) -> None:
    """Copies of the wave fill the 640 bytes: 160 copies of 4 bytes up to
    5 copies of 128. So the wave length picks the octave. Noise fills it
    with 640 bytes at its offset."""
    if voice.wave == NOISE:
        voice.buffer[:] = voice.source[:BUFFER_SIZE]
        return
    length = 4 << voice.wave_length
    wave = voice.source[:length]
    voice.buffer[:] = wave * (BUFFER_SIZE // length)
