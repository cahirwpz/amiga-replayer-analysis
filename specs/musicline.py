"""Musicline Editor's replay (Musicline, 1995): mlineplayer102.asm, the
DeliTracker player. The authors' own source, under the LGPL.

Card: players/MusiclineEditor.md. Level 2: the control flow runs; the
8-channel mixer's fixed-point steps are simplified. Each CamelCase
function is a new name in data/annot/MusiclineEditor.yaml; each CamelCase
class is in its `types:`.

Each channel has its own list of parts, with its own speed and groove.
A part row holds a note, an instrument and five effect words. An
instrument names a sample or a wave. A wave is stored in five sizes, 256
down to 16 bytes; the instrument picks one.

Five wave effects run in a chain every tick, each into its own buffer:
transform, phase, mix, resonance and filter. A sweep drives each one.
Its "init" flag lets the sweep run on across notes of one instrument;
its "step" flag moves it once per note instead of every tick. Each tick
the chain starts again from the plain wave.

In 8-channel mode, each Paula channel plays a buffer that the CPU mixes
from two voices. The audio interrupt then sets the tick.

Not modelled: part effects other than those below, pitch and volume
slides, the ProTracker-style effects, instrument glide, the arpeggio
table's slide commands, the loop sweep's step and init modes, and the
copy of the last wave buffer into chip memory.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from hardware import paula
from hardware.amiga import Amiga, Priority
from hardware.cia import E_DIVIDER

RAW = Path(__file__).resolve().parent.parent / (
    "ext/uade/amigasrc/players/other/musicline_editor/raw"
)


def raw_words(name: str) -> tuple[int, ...]:
    data = (RAW / name).read_bytes()
    return tuple(data[n] << 8 | data[n + 1] for n in range(0, len(data), 2))


PITCHES = raw_words("mlpalpitchtable32.raw")  # PalPitchTable
LFO_WAVES = b"".join(  # Sine, DownRamp, SawTooth, Square: 128 bytes each
    (RAW / name).read_bytes()
    for name in ("MlSinus.raw", "MlDownRamp.raw", "MlSawTooth.raw", "MlSquare.raw")
)
FILTER_LIST = raw_words("FilterList.raw")
RES_FILTER_LIST = raw_words("resfilterlist.raw")
RESONANCE_LIST = raw_words("resonancelist.raw")
RESONANCE_AMP_LIST = raw_words("resonanceamplist.raw")

ROWS = 128  # rows per part, and steps per arpeggio table
ROW_SIZE = 12  # note, instrument, five effect words
EFFECTS = 5
PART_END = 61  # a note byte: the part ends
ARP_END, ARP_JUMP = 61, 62
STEP = 32  # pitch units per semitone
TOP_NOTE = 5 * 12 * STEP
MIN_PERIOD, MAX_PERIOD = 106, 3591
MIN_TEMPO = 0x20  # FxSpeedAll: smaller arguments set the speed
FULL = 64 * 16  # volumes are 1/16 steps
TEMPO_BASE = 1773448  # CIA timer latch = TEMPO_BASE / tempo; 125 gives 50 Hz
MIX_PERIOD = 126  # 8-channel mode: each Paula channel's period
CCK_HZ = 3546895
WAVE_OFFSETS = {256: 0, 128: 256, 64: 384, 32: 448, 16: 480}  # the five copies
WAVE_SHIFTS = {256: 1, 128: 2, 64: 3, 32: 4, 16: 5}  # sweep value to bytes
DMA_WAIT_MIN = 100  # E clock counts before the new samples start
DMA_LOOP_WAIT = 150  # E clock counts before the loop pointers follow
SILENCE = (bytearray(2), 0)  # ZeroSample

# Instrument flags: Effects1
ADSR, VIBRATO, TREMOLO, ARPEGGIO, LOOP, LOOPSTOP, WSLOOP = 0, 1, 2, 3, 4, 5, 7
# Effects2
TRANSFORM, PHASE, MIX, RESONANCE, FILTER = 0, 1, 2, 3, 4
# EnvTraPhaFilBits
HOLD_SUSTAIN, TRA_INIT, TRA_STEP, PHA_INIT, PHA_STEP, PHA_FILL = 0, 1, 2, 3, 4, 5
FIL_INIT, FIL_STEP = 6, 7
# MixResLooBits
MIX_INIT, MIX_STEP, MIX_BUFF, MIX_ONE_WAY, RES_INIT, RES_STEP = 0, 1, 2, 3, 4, 5

# Phase types: how much of the plain wave is mixed in
QUICK, HIGH, MED, LOW = 0, 1, 2, 3

Wave = tuple[bytearray, int]  # memory and a byte offset: a pointer


# --- What the composer edits -------------------------------------------


@dataclass
class Sample:
    """A sample, or a wave in five sizes: 256, 128, 64, 32 and 16 bytes,
    one after another. An instrument holds its own view of a sample,
    with its own start, end and loop, in the same layout."""

    kind: int  # 0: sample; 1-5: wave of 16 to 256 bytes
    data: bytearray
    start: int = 0  # bytes into data
    length: int = 0  # words
    loop: int = 0  # bytes into data
    loop_length: int = 0  # words; 0: no loop
    finetune: int = 0
    semitone: int = 0


@dataclass
class SweepSetup:  # one block per wave effect
    start: int = 0
    repeat: int = 0
    repeat_end: int = 0
    speed: int = 0
    turns: int = 0  # passes, 0: endless; in step mode, the step size
    delay: int = 0


@dataclass
class LoopSetup:
    start: int = 0  # words into the sample
    repeat: int = 0
    repeat_end: int = 0
    length: int = 0  # words
    step: int = 0
    wait: int = 0  # ticks between steps
    delay: int = 0
    turns: int = 0


@dataclass
class LfoSetup:  # vibrato; the same for tremolo
    direction: int = 0
    wave: int = 0  # sine, down ramp, saw tooth, square
    speed: int = 0
    delay: int = 0
    attack_speed: int = 0
    attack: int = 0  # ticks until the full depth
    depth: int = 0


@dataclass
class Instrument:
    sample_number: int
    sample: Sample  # the instrument's own view
    volume: int = 64
    keep_transpose: bool = False  # follow the position's transpose
    effects1: int = 0
    effects2: int = 0
    bits1: int = 0  # EnvTraPhaFilBits
    bits2: int = 0  # MixResLooBits
    envelope: list[int] = field(default_factory=lambda: [0] * 12)  # lengths,
    # speeds and target volumes: attack, decay, sustain, release
    vibrato: LfoSetup = field(default_factory=LfoSetup)
    tremolo: LfoSetup = field(default_factory=LfoSetup)
    arp_table: int = 0
    arp_speed: int = 1
    arp_groove: int = 0
    transform_waves: list[int] = field(default_factory=lambda: [0] * 5)
    transform: SweepSetup = field(default_factory=SweepSetup)
    phase: SweepSetup = field(default_factory=SweepSetup)
    phase_type: int = QUICK
    mix: SweepSetup = field(default_factory=SweepSetup)
    mix_wave: int = 0  # 0: the wave itself
    resonance: SweepSetup = field(default_factory=SweepSetup)
    resonance_amp: int = 0
    filter: SweepSetup = field(default_factory=SweepSetup)
    filter_type: int = 0  # 0: low-pass; else resonant
    boost: int = 0  # MixResFilBoost: bit 0 filter, 1 resonance, 2 mix
    loop: LoopSetup = field(default_factory=LoopSetup)


@dataclass
class Tune:
    tempo: int
    speed: int
    groove: int
    eight: bool  # PlayMode: 8 channels
    lists: list[list[int]]  # one position list per channel


@dataclass
class Module:
    amiga: Amiga
    tune: Tune
    parts: dict[int, bytes]  # 128 rows of 12 bytes, unpacked
    arpeggios: dict[int, bytes]  # steps of 6 bytes
    instruments: dict[int, Instrument]
    samples: dict[int, Sample]
    channels: list["Channel"] = field(default_factory=list)
    master: int = FULL
    speed: int = 0  # the tune's; each part change restores it
    groove: int = 0
    stopped: bool = False
    mix_length: int = 0  # 8-channel mode: bytes per tick
    buffers: list[bytearray] = field(default_factory=list)


# --- Player state ------------------------------------------------------


@dataclass
class Sweep:
    counter: int = 0
    speed: int = 0
    repeat: int = 0
    repeat_end: int = 0
    turns: int = 0  # -1: done
    delay: int = 0
    step: bool = False
    init: bool = False
    saved: int = 0  # the value in use
    drift: int = 0  # step mode: added each tick
    last: int = -1  # the last note's instrument


@dataclass
class LoopSweep:
    base: Wave = SILENCE
    counter: int = 0
    saved: int = 0
    step: int = 0
    repeat: int = 0
    repeat_end: int = 0
    length: int = 1
    wait: int = 0
    wait_count: int = 0
    delay: int = 0
    turns: int = 0


@dataclass
class Lfo:  # vibrato; the same for tremolo
    count: int = 0
    speed: int = 0
    depth: int = 0
    delay: int = 0
    attack_speed: int = 0
    attack: int = 0
    full: int = 0
    wave: int = 0
    direction: int = 0


@dataclass
class Channel:
    output: paula.Channel
    number: int
    off: bool = False  # VoiceOff: the list ended
    muted: bool = False  # ChannelOff
    speed: int = 0
    groove: int = 0
    speed_count: int = 1
    groove_phase: bool = False
    tune_pos: int = 0
    part_pos: int = 0
    jump_count: int = 0
    part_jump_count: int = 0
    tune_wait: int = 0
    transpose: int = 0  # pitch units
    # this row
    note: int = 0  # PartNote
    inst_number: int = 0  # PartInst
    effects: list[tuple[int, int]] = field(default_factory=list)
    # instrument
    inst: Instrument | None = None
    old_inst: int = 0
    wave_number: int = 0
    old_wave_number: int = 0
    wave_override: Sample | None = None  # WaveSample, or an arpeggio step
    is_wave: int = 0  # WaveOrSample
    start: Wave = SILENCE  # WsPointer
    length: int = 1
    loop: Wave = SILENCE  # WsRepPointer: the chain's output
    loop_org: Wave = SILENCE  # WsRepPtrOrg: the plain loop
    loop_length: int = 1
    effects1: int = 0
    effects2: int = 0
    bits1: int = 0
    bits2: int = 0
    new_note: bool = False  # Play bit 0
    hold_override: bool = False  # Effects1 bit 6: HoldSustain given
    # volume, in 1/16 steps
    volume1: int = 0
    volume2: int = 0
    volume3: int = 0
    vol_set: int | None = None
    channel_volume: int = FULL
    adsr: list[int] = field(default_factory=lambda: [0] * 12)
    adsr_volume: int = 0
    # pitch, in pitch units
    pitch: int = 0  # the note, in pitch units
    semitone: int = 0
    finetune: int = 0
    vibrato_offset: int = 0
    period: int = 0
    # arpeggio
    arp_on: bool = False
    arp_list: int | None = None  # ArpeggioList's table
    arp_pitch_set: bool = False  # the table set this row's pitch
    arp_wait: bool = False  # ArpWait: the note waits for a step with a note
    arp_pos: int = 0
    arp_count: int = 0
    arp_groove_phase: bool = False
    arp_base: int = 0
    arp_fixed: bool = False  # a fixed note: no transpose
    vibrato: Lfo = field(default_factory=Lfo)
    tremolo: Lfo = field(default_factory=Lfo)
    # wave effects
    transform: Sweep = field(default_factory=Sweep)
    phase: Sweep = field(default_factory=Sweep)
    mix: Sweep = field(default_factory=Sweep)
    resonance: Sweep = field(default_factory=Sweep)
    filter: Sweep = field(default_factory=Sweep)
    res_last: int = 0
    res_last_init: bool = False
    fil_last: int = 0
    fil_last_init: bool = False
    buffers: dict[str, bytearray] = field(default_factory=dict)
    loop_sweep: LoopSweep = field(default_factory=LoopSweep)
    # 8-channel mixer
    mix_pos: int = 0  # 16.16 bytes into the playing part
    mix_part: tuple[bytearray, int, int] = (bytearray(2), 0, 1)
    mix_ended: bool = True


# --- Start -------------------------------------------------------------


def new_module(module: Module) -> Module:
    """4 channels: CIA-B timer A runs PlayMusic at the tune's tempo.
    8 channels: Paula's channel 0 interrupt runs it, once per buffer."""
    count = 8 if module.tune.eight else 4
    paulas = module.amiga.paula.channels
    module.channels = [Channel(paulas[n % 4], n) for n in range(count)]
    module.speed, module.groove = module.tune.speed, module.tune.groove
    for ch in module.channels:
        ch.speed, ch.groove = module.speed, module.groove
        ch.buffers = {k: bytearray(256) for k in ("tra", "pha", "mix", "res", "fil")}
    if module.tune.eight:
        StartAudioInt(module)
    else:
        StartTimerInt(module)
    return module


def StartTimerInt(module: Module) -> None:
    module.amiga.timer.on_underflow = lambda: PlayMusic(module)
    module.amiga.timer.set_latch(TEMPO_BASE // module.tune.tempo)
    module.amiga.timer.start()


def StartAudioInt(module: Module) -> None:
    """The buffer lasts one tick: its length follows the tempo."""
    rate = CCK_HZ // MIX_PERIOD
    module.mix_length = (rate * 125 // (module.tune.tempo * 50)) & ~1
    module.buffers = [bytearray(module.mix_length) for _ in range(4)]
    for n, channel in enumerate(module.amiga.paula.channels):
        channel.period = MIX_PERIOD
        channel.set_volume(64)
        channel.play(paula.Sample(module.buffers[n]))
    module.amiga.paula.channels[0].on_irq(lambda _: PlayMusic(module))


# --- Tick --------------------------------------------------------------


def PlayMusic(module: Module) -> None:
    """Rows, then effects, then periods and volumes, then new notes."""
    if module.stopped:
        return
    PlayTune(module)
    for ch in module.channels:
        PlayEffects(module, ch)
    PerCalc(module)
    PerVolPlay(module)
    if module.tune.eight:
        Play8Channels(module)
    else:
        DmaPlay(module)


def PerCalc(module: Module) -> None:
    for ch in module.channels:
        NotePeriod(ch)


def PlayTune(module: Module) -> None:
    for ch in module.channels:
        PlayVoice(module, ch)


def PlayVoice(module: Module, ch: Channel) -> None:
    """A row every `speed` ticks; with a groove, rows alternate between
    `speed` and `groove` ticks. A position word is a part and a
    transpose, or a command: end, jump or wait."""
    if ch.off:
        return
    ch.speed_count = (ch.speed_count - 1) & 0xFF
    if ch.speed_count:
        return
    ch.groove_phase = not ch.groove_phase
    use_groove = ch.groove_phase and ch.groove
    ch.speed_count = ch.groove if use_groove else ch.speed
    positions = module.tune.lists[ch.number]
    for _ in range(256):  # a guard against endless jumps
        entry = positions[ch.tune_pos]
        target, low = entry >> 8, entry & 0x1F
        command = entry >> 6 & 3 if entry & 0x20 else 0
        if command == 1:
            ch.off = True
            return
        if command == 2:
            tune_jump(ch, target, low)
            continue
        if command == 3:
            if tune_wait(ch, target, low):
                continue
            return
        number = target | (entry << 2 & 0x300)
        if read_part(module, ch, module.parts[number], (low - 16) * STEP):
            continue
        return


def tune_jump(ch: Channel, target: int, count: int) -> None:
    """Jumps only go back. A count of 0 loops forever."""
    if ch.jump_count:
        ch.jump_count -= 1
        ch.tune_pos = target if ch.jump_count else ch.tune_pos + 1
    elif target >= ch.tune_pos:
        ch.tune_pos += 1
    else:
        ch.jump_count, ch.tune_pos = count, target


def tune_wait(ch: Channel, rows: int, speed: int) -> bool:
    """Waits `rows` rows. True: read on."""
    if ch.tune_wait:
        ch.tune_wait -= 1
        if ch.tune_wait:
            return False
        ch.tune_pos += 1
        return True
    ch.tune_wait = rows
    if not rows:
        ch.tune_pos += 1
        return True
    ch.note = 0
    if speed:
        ch.speed = ch.speed_count = speed
    return False


def read_part(module: Module, ch: Channel, part: bytes, transpose: int) -> bool:
    """Reads rows until a note row. True: the part ended; read the next
    position. Part jumps also only go back. An empty part stops the
    song."""
    while True:
        row = ch.part_pos
        ch.part_pos = (ch.part_pos + 1) & (ROWS - 1)
        if not ch.part_pos:
            ch.tune_pos += 1
            ch.speed, ch.groove = module.speed, module.groove
        data = part[ROW_SIZE * row : ROW_SIZE * (row + 1)]
        note, inst = data[0], data[1]
        if note == PART_END:
            if row == 0:
                module.stopped = True
                return False
            ch.part_pos = 0
            ch.speed, ch.groove = module.speed, module.groove
            ch.speed_count = ch.speed
            ch.tune_pos += 1
            return True
        if note & 0x80:
            target = note & 0x7F
            if ch.part_jump_count:
                ch.part_jump_count -= 1
                if ch.part_jump_count:
                    ch.part_pos = target
            elif target < row:
                ch.part_jump_count, ch.part_pos = inst, target
            continue
        ch.note, ch.inst_number = note, inst
        ch.effects = [(data[2 + 2 * n], data[3 + 2 * n]) for n in range(EFFECTS)]
        if note:
            ch.transpose = transpose
        CheckInst(module, ch)
        return False


def CheckInst(module: Module, ch: Channel) -> None:
    """A new instrument number clears the arpeggio."""
    number = ch.inst_number
    if number and number in module.instruments:
        ch.inst = module.instruments[number]
        if number != ch.old_inst:
            ch.arp_on, ch.arp_list, ch.old_inst = False, None, number
    PlayPartFx(module, ch)
    PlayArpg(module, ch)
    PlayInst(module, ch)


def PlayPartFx(module: Module, ch: Channel) -> None:
    """Five effect words per row. Unmodelled numbers do nothing here."""
    ch.vol_set, ch.hold_override, ch.wave_override = None, False, None
    ch.arp_pitch_set = False
    for number, arg in ch.effects:
        handler = PART_EFFECTS.get(number)
        if handler is not None:
            handler(module, ch, arg)


def PlayArpg(module: Module, ch: Channel) -> None:
    """A note with an instrument starts its arpeggio table, or the table
    that ArpeggioList named. The first step plays at once."""
    inst = ch.inst
    if not ch.note or inst is None:
        return
    ch.arp_wait = False
    if ch.arp_list is None and not ch.arp_on:
        if not inst.effects1 >> ARPEGGIO & 1:
            return
        ch.arp_on = True
    if not ch.inst_number:
        return
    ch.arp_pos, ch.arp_count, ch.arp_base = 0, inst.arp_speed, ch.note
    arp_step(module, ch, inst, first=True)


def ArpeggioPlay(module: Module, ch: Channel) -> None:
    """Steps every `arp_speed` ticks, alternating with `arp_groove`."""
    inst = ch.inst
    if inst is None or not (ch.arp_on or ch.arp_list is not None):
        return
    ch.arp_count = (ch.arp_count - 1) & 0xFF
    if ch.arp_count:
        return
    ch.arp_groove_phase = not ch.arp_groove_phase
    grooved = ch.arp_groove_phase and inst.arp_groove
    ch.arp_count = inst.arp_groove if grooved else inst.arp_speed
    arp_step(module, ch, inst)


def arp_step(
    module: Module, ch: Channel, inst: Instrument, first: bool = False
) -> None:
    """A step: a note, a wave and two commands. A negative note adds to
    the row's note; a positive one is fixed. Each step may pick its own
    wave, sample or not. A first step without a note holds back the
    note-on: ArpeggioWait. Steps without a note then pass, until one with a
    note starts the instrument."""
    number = ch.arp_list if ch.arp_list is not None else inst.arp_table
    table = module.arpeggios.get(number)
    if table is None:
        return
    for _ in range(ROWS):
        at = 6 * ch.arp_pos
        ch.arp_pos = (ch.arp_pos + 1) & (ROWS - 1)
        note = table[at]
        if not note and (first or ch.arp_wait):
            ch.arp_wait = True
            return
        if note == ARP_END:
            ch.arp_on, ch.arp_list = False, None
            return
        if note != ARP_JUMP:
            break
        ch.arp_pos = table[at + 1]
    else:
        return
    wave = table[at + 1]
    ch.wave_number = wave or inst.sample_number
    if wave in module.samples:
        ch.wave_override = module.samples[wave]
    for command, arg in (
        (table[at + 2], table[at + 3]),
        (table[at + 4], table[at + 5]),
    ):
        if command == 3:  # set the volume
            ch.volume1 = ch.volume2 = ch.volume3 = arg << 4
    if not note:
        return
    ch.arp_fixed = note < 0x80
    if not ch.arp_fixed:
        note = (note + PART_END + ch.arp_base) & 0xFF
    ch.pitch, ch.arp_pitch_set = signed_byte(note) * STEP, True
    if ch.arp_wait:
        ch.arp_wait = False
        PlayInst(module, ch)


def PlayInst(module: Module, ch: Channel) -> None:
    """With an instrument number: the sample or wave and the volume.
    With a note: the pitch, then InstPlay starts the instrument's
    effects. A note without an instrument number changes only the pitch.
    A waiting arpeggio holds all of this back. An instrument with a
    slide speed glides: each note after its first slides from the
    current pitch to the new note (not modelled)."""
    inst = ch.inst
    if inst is None or ch.arp_wait:
        return
    source = ch.wave_override or inst.sample
    if ch.inst_number and ch.note:
        if ch.wave_override is None:
            ch.wave_number = inst.sample_number
        if not inst.keep_transpose:
            ch.transpose = 0
        bits1 = inst.bits1
        if ch.hold_override:
            bits1 = bits1 & ~1 | ch.bits1 & 1
        ch.bits1, ch.bits2 = bits1, inst.bits2
        ch.effects1, ch.effects2 = inst.effects1, inst.effects2
        ch.is_wave = source.kind
        if source.kind:
            FixWaveLength(ch, source, inst.sample.kind or source.kind)
        else:
            set_sample(ch, source, bool(inst.effects1 >> WSLOOP & 1))
    if ch.inst_number:
        ch.volume1 = inst.volume << 4
    volume = ch.vol_set if ch.vol_set is not None else ch.volume1
    ch.volume1 = ch.volume2 = ch.volume3 = volume
    if not ch.note:
        return
    if not ch.arp_pitch_set:
        ch.pitch = ch.note * STEP
    ch.semitone, ch.finetune = source.semitone * STEP, source.finetune
    ch.vibrato_offset = 0
    if ch.inst_number:
        InstPlay(ch, inst)


def set_sample(ch: Channel, source: Sample, looped: bool) -> None:
    """Without the loop flag, the loop is one silent word."""
    ch.start, ch.length = (source.data, source.start), source.length
    if looped and source.loop_length:
        ch.loop, ch.loop_length = (source.data, source.loop), source.loop_length
    else:
        ch.loop, ch.loop_length = SILENCE, 1
    ch.loop_org = ch.loop


def FixWaveLength(ch: Channel, source: Sample, kind: int) -> None:
    """Kind 1-5 picks the 16- to 256-byte copy. A wave loops whole."""
    size = 8 << min(kind, 5)
    at = source.start + WAVE_OFFSETS[size]
    ch.start = ch.loop = ch.loop_org = (source.data, at)
    ch.length = ch.loop_length = size // 2


def InstPlay(ch: Channel, inst: Instrument) -> None:
    """Starts the instrument's vibrato, tremolo, envelope, wave effects
    and sample loop sweep."""
    ch.new_note = True
    if ch.effects1 >> VIBRATO & 1:
        ch.vibrato = lfo_start(inst.vibrato)
    if ch.effects1 >> TREMOLO & 1:
        ch.tremolo = lfo_start(inst.tremolo)
    if ch.effects1 >> ADSR & 1:
        ch.adsr, ch.adsr_volume = list(inst.envelope), 0
    b1, b2, number = ch.bits1, ch.bits2, ch.inst_number
    if ch.effects2 >> PHASE & 1:
        sweep_start(
            ch.phase, inst.phase, b1 >> PHA_STEP & 1, b1 >> PHA_INIT & 1, number
        )
    if ch.effects2 >> RESONANCE & 1:
        restarted = sweep_start(
            ch.resonance, inst.resonance, b2 >> RES_STEP & 1, b2 >> RES_INIT & 1, number
        )
        ch.res_last_init = ch.res_last_init or restarted
    if ch.effects2 >> FILTER & 1:
        restarted = sweep_start(
            ch.filter, inst.filter, b1 >> FIL_STEP & 1, b1 >> FIL_INIT & 1, number
        )
        ch.fil_last_init = ch.fil_last_init or restarted
    if ch.effects2 >> MIX & 1:
        sweep_start(ch.mix, inst.mix, b2 >> MIX_STEP & 1, b2 >> MIX_INIT & 1, number)
    if ch.effects2 >> TRANSFORM & 1:
        sweep_start(
            ch.transform, inst.transform, b1 >> TRA_STEP & 1, b1 >> TRA_INIT & 1, number
        )
    if ch.effects1 >> LOOP & 1:
        loop_start(ch, inst)
    CheckWaveSize(ch)


def CheckWaveSize(ch: Channel) -> None:
    """Wave effects need a loop of 16 to 256 bytes, a power of 2."""
    if 2 * ch.loop_length not in WAVE_OFFSETS:
        ch.effects2 = 0


def lfo_start(setup: LfoSetup) -> Lfo:
    return Lfo(
        speed=setup.speed, delay=setup.delay, attack_speed=setup.attack_speed,
        attack=setup.attack, full=setup.depth, wave=setup.wave,
        direction=setup.direction,
    )  # fmt: skip


def sweep_start(
    sweep: Sweep, setup: SweepSetup, step: int, init: int, inst: int
) -> bool:
    """With "init" or "step", a note of the same instrument keeps the
    sweep where it is. True: the sweep started again."""
    sweep.step, sweep.init = bool(step), bool(init)
    if step:
        sweep.drift, sweep.turns = setup.turns, 0
    else:
        sweep.turns = setup.turns
    if step or init:
        last, sweep.last = sweep.last, inst
        if last == inst:
            sweep.delay = setup.delay
            return False
    else:
        sweep.last = -1
    sweep.counter, sweep.speed = setup.start, setup.speed
    sweep.repeat, sweep.repeat_end = setup.repeat, setup.repeat_end
    if setup.start > setup.repeat:
        sweep.speed = -sweep.speed
    sweep.delay = setup.delay
    return True


def loop_start(ch: Channel, inst: Instrument) -> None:
    """Only for a sample with a loop length. The window starts at
    `start`, `length` words long."""
    setup, sample = inst.loop, inst.sample
    if sample.kind or not setup.length:
        ch.effects1 &= ~(1 << LOOP)
        return
    ls = ch.loop_sweep
    ls.base = (sample.data, sample.start)
    ls.counter = ls.saved = setup.start
    ls.step = -setup.step if setup.start > setup.repeat else setup.step
    ls.repeat, ls.repeat_end, ls.length = setup.repeat, setup.repeat_end, setup.length
    ls.wait, ls.wait_count, ls.delay, ls.turns = setup.wait, 0, setup.delay, setup.turns
    data, at = ls.base
    ch.start = ch.loop = ch.loop_org = (data, at + 2 * setup.start)
    ch.length = ch.loop_length = setup.length


# --- Effects, every tick -----------------------------------------------


def PlayEffects(module: Module, ch: Channel) -> None:
    """On a note's first tick, only the envelope, the loop sweep and the
    wave effects run. The chain starts from the plain loop each tick."""
    ch.loop = ch.loop_org
    if not ch.new_note:
        ArpeggioPlay(module, ch)
        VibratoPlay(ch)
        TremoloPlay(ch)
    AdsrPlay(ch)
    MoveLoop(ch)
    TransformPlay(module, ch)
    PhasePlay(ch)
    MixPlay(module, ch)
    ResonancePlay(ch)
    FilterPlay(ch)
    looping = ch.effects1 >> LOOP & 1
    if not ch.new_note and looping and not module.tune.eight:
        data, at = ch.loop
        ch.output.queue(paula.Sample(data, at, ch.loop_sweep.length))
        ch.loop_length = ch.loop_sweep.length
    ch.note = 0


def AdsrPlay(ch: Channel) -> None:
    """Each phase lasts its length in ticks and adds its speed; at its
    end the volume jumps to the phase's target. Held, the sustain stays
    until the hold ends."""
    if not ch.effects1 >> ADSR & 1:
        return
    env = ch.adsr
    phase = next((n for n in range(3) if env[n]), None)
    held = ch.bits1 >> HOLD_SUSTAIN & 1
    if phase is None and not held and env[3]:
        phase = 3
    if phase is None:
        level = env[10 if held else 11]
    else:
        ch.adsr_volume = (ch.adsr_volume + env[4 + phase]) & 0xFFFF
        level = ch.adsr_volume >> 8
        env[phase] -= 1
        if not env[phase]:
            level = env[8 + phase]
    ch.volume3 = level * ch.volume2 >> 6


def VibratoPlay(ch: Channel) -> None:
    """A table wave on the pitch, after a delay. The depth grows during
    its attack. The offset is in pitch units: the same interval at any
    pitch."""
    if not ch.effects1 >> VIBRATO & 1:
        return
    offset = lfo_value(ch.vibrato, 4)
    if offset is not None:
        ch.vibrato_offset = offset + 1 if offset < 0 else offset


def TremoloPlay(ch: Channel) -> None:
    if not ch.effects1 >> TREMOLO & 1:
        return
    offset = lfo_value(ch.tremolo, 1)
    if offset is None:
        return
    if offset < 0:
        offset += 16
    volume = clamp(ch.volume1 + offset, 0, FULL) if ch.volume1 else 0
    ch.volume2 = ch.volume3 = volume


def lfo_value(lfo: Lfo, shift: int) -> int | None:
    """None: the delay runs."""
    if lfo.delay:
        lfo.delay -= 1
        return None
    if lfo.attack:
        lfo.depth += lfo.attack_speed
        lfo.attack -= 1
        if not lfo.attack:
            lfo.depth = lfo.full
    else:
        lfo.depth = lfo.full
    value = signed_byte(LFO_WAVES[lfo.wave * 128 + (lfo.count >> 2)])
    value = value if lfo.direction else -value
    lfo.count = (lfo.count + lfo.speed) & 0x1FF
    return value * (lfo.depth >> 8) >> shift


def MoveLoop(ch: Channel) -> None:
    """A sample's loop window sweeps through the sample, bouncing
    between two points, one step every `wait` + 1 ticks. After its
    turns, it may stop the sound."""
    if not ch.effects1 >> LOOP & 1:
        return
    ls = ch.loop_sweep
    ls.delay -= 1
    if ls.delay < 0:
        ls.delay = 0
        if ls.wait:
            ls.wait_count -= 1
            if ls.wait_count >= 0:
                return
            ls.wait_count = ls.wait
        ls.saved = ls.counter
        LoopCounter(ls)
    data, at = ls.base
    ch.loop = ch.loop_org = (data, at + 2 * ls.saved)
    if ls.turns < 0 and ch.effects1 >> LOOPSTOP & 1:
        ch.effects1 &= ~(1 << LOOP)
        ch.output.queue(paula.Sample(bytes(2)))


def LoopCounter(ls: LoopSweep) -> None:
    """The same bounce as Counter, in words."""
    ls.counter, ls.step, ls.turns = bounce(
        ls.counter, ls.step, ls.repeat, ls.repeat_end, ls.turns
    )


def Counter(sweep: Sweep) -> None:
    """Moves by `speed` between `repeat` and `repeat_end`. A move past
    an end is not made: the sweep turns there. After `turns` passes it
    stops; 0 turns never stops."""
    if not sweep.step and sweep.delay:
        sweep.delay -= 1
        return
    sweep.counter, sweep.speed, sweep.turns = bounce(
        sweep.counter, sweep.speed, sweep.repeat, sweep.repeat_end, sweep.turns
    )


def bounce(value: int, speed: int, a: int, b: int, turns: int) -> tuple[int, int, int]:
    """Only the end in the direction of travel is checked."""
    if turns < 0:
        return value, speed, turns
    low, high = (a, b) if a < b else (b, a)
    moved = value + speed
    if (speed < 0 and moved >= low) or (speed >= 0 and moved <= high):
        return moved, speed, turns
    if turns:
        turns = turns - 1 or -1
    return value, -speed, turns


def OneWayCounter(sweep: Sweep) -> None:
    """Mix's other counter: it wraps at 512 instead of turning."""
    if not sweep.step and sweep.delay:
        sweep.delay -= 1
        return
    sweep.counter = (sweep.counter + sweep.speed) & 0x1FF


def sweep_tick(ch: Channel, sweep: Sweep, one_way: bool = False, sign: int = 1) -> int:
    """The value a wave effect uses this tick. Without "step", the sweep
    moves every tick. With it, a note takes the sweep's value, which then
    drifts by the step size each tick."""
    advance = OneWayCounter if one_way else Counter
    if not sweep.step or ch.note:
        sweep.saved = sweep.counter
        advance(sweep)
    elif sweep.init:
        advance(sweep)
    if not sweep.step:
        return sweep.saved
    if sweep.delay:
        sweep.delay -= 1
        return sweep.saved
    drift = sign * signed_byte(sweep.drift & 0xFF)
    low, high = (2, 512) if sign < 0 else (0, 510)
    moved = sweep.saved + drift
    sweep.saved = max(moved, low) if drift < 0 else min(moved, high)
    return sweep.saved


def TransformPlay(module: Module, ch: Channel) -> None:
    """Crossfades along a chain of up to six waves: the instrument's,
    then five more. The sweep's value picks the pair and the blend."""
    if not ch.effects2 >> TRANSFORM & 1 or ch.inst is None:
        return
    size = 2 * ch.loop_length
    index, blend = SelectTraWave(sweep_tick(ch, ch.transform) >> 1, 256)
    chain = [ch.inst.sample_number, *ch.inst.transform_waves]
    if index + 1 >= len(chain) or not chain[index] or not chain[index + 1]:
        return
    first = ch.loop if index == 0 else wave_at(module, chain[index], size)
    second = wave_at(module, chain[index + 1], size)
    out = ch.buffers["tra"]
    for n in range(size):
        a = signed_byte(first[0][first[1] + n])
        b = signed_byte(second[0][second[1] + n])
        out[n] = (a + ((b - a) * blend >> 8)) & 0xFF
    set_output(ch, out)


def SelectTraWave(value: int, span: int) -> tuple[int, int]:
    """Up to five whole spans pass; returns the pair index and the rest."""
    index = 0
    while index < 5 and value - span > 0:
        value, index = value - span, index + 1
    return index, value


def PhasePlay(ch: Channel) -> None:
    """Squeezes the whole wave into the first part of the cycle; the
    sweep sets that part's length. The rest holds the last value, or
    repeats the squeezed part. The type mixes in the plain wave."""
    if not ch.effects2 >> PHASE & 1 or ch.inst is None:
        return
    size = 2 * ch.loop_length
    shift = WAVE_SHIFTS[size]
    part = (sweep_tick(ch, ch.phase, sign=-1) + (1 << shift) - 1) >> shift
    data, at = ch.loop
    plain = [signed_byte(data[at + n]) for n in range(size)]
    out = ch.buffers["pha"]
    if not 0 < part < size:
        out[:size] = data[at : at + size]
        set_output(ch, out)
        return
    squeezed = [plain[(k + 1) * size // part - 1] for k in range(part)]
    fill = ch.bits1 >> PHA_FILL & 1
    for n in range(size):
        s = squeezed[n % part] if n < part or fill else squeezed[-1]
        out[n] = phase_mix(plain[n], s, ch.inst.phase_type) & 0xFF
    set_output(ch, out)


def phase_mix(plain: int, squeezed: int, kind: int) -> int:
    """Quick: squeezed only. High: 1:3. Med: 1:1. Low: 3:1."""
    if kind == HIGH:
        return (plain + 3 * squeezed) >> 2
    if kind == MED:
        return (plain + squeezed) >> 1
    if kind == LOW:
        return (3 * plain + squeezed) >> 2
    return squeezed


def MixPlay(module: Module, ch: Channel) -> None:
    """Adds a copy rotated by the sweep's value: another wave, the wave
    itself, or the mix buffer, which feeds back. The sum is halved,
    unless boosted."""
    if not ch.effects2 >> MIX & 1 or ch.inst is None:
        return
    size = 2 * ch.loop_length
    one_way = bool(ch.bits2 >> MIX_ONE_WAY & 1)
    offset = sweep_tick(ch, ch.mix, one_way) >> WAVE_SHIFTS[size]
    data, at = ch.loop
    out = ch.buffers["mix"]
    if ch.bits2 >> MIX_BUFF & 1:
        other: Wave = (out, 0)
    elif ch.inst.mix_wave:
        other = wave_at(module, ch.inst.mix_wave, size)
    else:
        other = ch.loop
    shift = 0 if ch.inst.boost & 4 else 1
    for n in range(size):
        b = signed_byte(other[0][other[1] + (n + offset) % size])
        out[n] = (signed_byte(data[at + n]) + b) >> shift & 0xFF
    set_output(ch, out)


def ResonancePlay(ch: Channel) -> None:
    """A two-pole filter with feedback, run over the wave; its state
    carries over to the next tick. The sweep picks the frequency; the
    instrument's amount sets the damping."""
    if not ch.effects2 >> RESONANCE & 1 or ch.inst is None:
        return
    size = 2 * ch.loop_length
    value = sweep_tick(ch, ch.resonance) & ~1
    data, at = ch.loop
    last = ch.res_last
    if ch.res_last_init:
        ch.res_last_init = False
        last = signed_byte(data[at + size - 1]) >> 2
    y = s16(last << 7)
    frequency = RESONANCE_LIST[value >> 1]
    damping = (0x8000 - RESONANCE_AMP_LIST[ch.inst.resonance_amp]) * 0xE666 >> 16
    shift = 6 if ch.inst.boost & 2 else 7
    velocity, out = 0, ch.buffers["res"]
    for n in range(size):
        x = s16((signed_byte(data[at + n]) << 5) - y)
        velocity = s16(velocity + s16(int((x << 7) / frequency)))
        y = s16(y + velocity)
        out[n] = (y >> shift) & 0xFF
        velocity = s16(velocity * damping * 2 >> 16)
    ch.res_last = signed_byte(out[size - 1])
    set_output(ch, out)


def FilterPlay(ch: Channel) -> None:
    """A low-pass filter over the wave, or a resonant one; the sweep
    picks the cutoff. Its state carries over to the next tick."""
    if not ch.effects2 >> FILTER & 1 or ch.inst is None:
        return
    size = 2 * ch.loop_length
    value = sweep_tick(ch, ch.filter) & ~1
    data, at = ch.loop
    resonant = bool(ch.inst.filter_type)
    last = ch.fil_last
    if ch.fil_last_init:
        ch.fil_last_init = False
        last = signed_byte(data[at + size - 1]) >> (1 if resonant else 0)
    y = s16(last << 7)
    cutoff = (RES_FILTER_LIST if resonant else FILTER_LIST)[value >> 1]
    if resonant:
        damping = (0x8000 - cutoff) * 0xE666 >> 16
    else:  # muls #$f000: a small negative factor
        damping = s16((0x8000 - cutoff) * -0x1000 >> 16)
    cutoff >>= 1
    gain = 6 if resonant else 7
    shift = 6 if ch.inst.boost & 1 else 7
    velocity, out = 0, ch.buffers["fil"]
    for n in range(size):
        x = s16((signed_byte(data[at + n]) << gain) - y)
        velocity = s16(velocity + s16(x * cutoff * 4 >> 16))
        y = s16(y + velocity)
        out[n] = (y >> shift) & 0xFF
        velocity = s16(velocity * damping * 2 >> 16)
    ch.fil_last = signed_byte(out[size - 1])
    set_output(ch, out)


# --- Output ------------------------------------------------------------


def NotePeriod(ch: Channel) -> None:
    """All pitch sums are in pitch units, 32 per semitone; one table
    lookup gives the period. The replay reads before the table below
    note 0; this model clamps there."""
    pitch = ch.pitch + ch.vibrato_offset + ch.semitone + ch.finetune
    if not ch.arp_fixed:
        pitch += ch.transpose
    ch.period = clamp(PITCHES[clamp(pitch, 0, TOP_NOTE)], MIN_PERIOD, MAX_PERIOD)


def PerVolPlay(module: Module) -> None:
    """4 channels: channels without a new note get period and volume."""
    if module.tune.eight:
        return
    for ch in module.channels:
        if ch.new_note:
            continue
        ch.output.period = ch.period
        if not ch.muted:
            ch.output.set_volume(output_volume(module, ch))


def DmaPlay(module: Module) -> None:
    """New notes stop their channels, except a wave note on the same
    wave: that wave plays on, with no restart. A CIA timer, not a busy
    loop, waits for the channels to stop. Its wait is the longest old
    period, in E clock counts."""
    restart, wait = [], DMA_WAIT_MIN
    for ch in module.channels:
        if not ch.new_note:
            continue
        same_wave = ch.is_wave and ch.wave_number == ch.old_wave_number
        ch.old_wave_number = ch.wave_number
        if same_wave:
            continue
        restart.append(ch)
        wait = max(wait, ch.output.period)
        ch.output.disable()
    module.amiga.after(
        wait * E_DIVIDER, Priority.INTERRUPT, lambda: DmaStart(module, restart)
    )


def DmaStart(module: Module, restart: list[Channel]) -> None:
    """Every new note gets its start, volume and period; stopped
    channels get DMA on. The loop follows 150 counts later."""
    for ch in module.channels:
        if not ch.new_note:
            continue
        ch.new_note = False
        if not ch.muted:
            ch.output.set_volume(output_volume(module, ch))
        ch.output.queue(view(ch.start, ch.length))
        ch.output.period = ch.period
    for ch in restart:
        ch.output.enable()
    module.amiga.after(
        DMA_LOOP_WAIT * E_DIVIDER, Priority.INTERRUPT, lambda: DmaLoop(restart)
    )


def DmaLoop(restart: list[Channel]) -> None:
    for ch in restart:
        ch.output.queue(view(ch.loop, ch.loop_length))


def Play8Channels(module: Module) -> None:
    """Each Paula channel plays one buffer: voices 1-4 write it, voices
    5-8 add to it."""
    for n, buffer in enumerate(module.buffers):
        MixVoice(module, module.channels[n], buffer, add=False)
        MixVoice(module, module.channels[n + 4], buffer, add=True)


def MixVoice(module: Module, ch: Channel, buffer: bytearray, add: bool) -> None:
    """A new note restarts the voice's read position. The volume table
    holds each voice at half range, so two voices add without overflow."""
    if ch.new_note:
        ch.new_note = False
        data, at = ch.start
        ch.mix_part, ch.mix_pos, ch.mix_ended = (data, at, 2 * ch.length), 0, False
    volume = 0 if ch.muted else output_volume(module, ch)
    (MixAdd if add else MixMove)(ch, buffer, volume)


def MixMove(ch: Channel, buffer: bytearray, volume: int) -> None:
    for n in range(len(buffer)):
        buffer[n] = mix_byte(ch, volume)


def MixAdd(ch: Channel, buffer: bytearray, volume: int) -> None:
    for n in range(len(buffer)):
        buffer[n] = (buffer[n] + mix_byte(ch, volume)) & 0xFF


def mix_byte(ch: Channel, volume: int) -> int:
    """Resamples at MIX_PERIOD / period. At the end of the part, the
    loop follows, or silence."""
    if ch.mix_ended or not ch.period:
        return 0
    data, at, size = ch.mix_part
    index = ch.mix_pos >> 16
    if index >= size:
        if not (ch.effects1 >> LOOP & 1 or ch.effects1 >> WSLOOP & 1):
            ch.mix_ended = True
            return 0
        data, at = ch.loop
        ch.mix_part, index, ch.mix_pos = (data, at, 2 * ch.loop_length), 0, 0
    ch.mix_pos += (MIX_PERIOD << 16) // ch.period
    return half_volume(signed_byte(data[at + index]), volume)


def half_volume(value: int, volume: int) -> int:
    """VolumeTables: value * volume / 64 / 2, each step toward 0."""
    return trunc(trunc(value * volume, 64), 2) & 0xFF


# --- Part effects ------------------------------------------------------

PartEffect = Callable[[Module, Channel, int], None]


def FxVolume(module: Module, ch: Channel, arg: int) -> None:
    """This note's volume, 0 to 64."""
    ch.vol_set = arg << 4


def FxChannelVol(module: Module, ch: Channel, arg: int) -> None:
    """The channel's volume, a second factor."""
    ch.channel_volume = arg << 4


def FxMasterVol(module: Module, ch: Channel, arg: int) -> None:
    """The third factor, for all channels."""
    module.master = arg << 4


def FxSpeedPart(module: Module, ch: Channel, arg: int) -> None:
    """This channel's speed, up to 31."""
    if arg:
        ch.speed = min(arg, 0x1F)
        if not ch.groove or not ch.groove_phase:
            ch.speed_count = ch.speed


def FxGroovePart(module: Module, ch: Channel, arg: int) -> None:
    """This channel's groove: every other row lasts `groove` ticks."""
    if arg:
        ch.groove = min(arg, 0x1F)
        if ch.groove_phase:
            ch.speed_count = ch.groove


def FxSpeedAll(module: Module, ch: Channel, arg: int) -> None:
    """Below MIN_TEMPO, the speed of all channels; from it, the tempo."""
    if not arg:
        return
    if arg >= MIN_TEMPO:
        module.amiga.timer.set_latch(TEMPO_BASE // arg)
        return
    module.speed = arg
    for other in module.channels:
        other.speed = arg


def FxGrooveAll(module: Module, ch: Channel, arg: int) -> None:
    """The groove of all channels."""
    if arg:
        module.groove = arg & 0x1F
        for other in module.channels:
            other.groove = module.groove


def FxArpeggioList(module: Module, ch: Channel, arg: int) -> None:
    """Plays another arpeggio table, until it ends or the
    instrument changes."""
    ch.arp_list = arg


def FxHoldSustain(module: Module, ch: Channel, arg: int) -> None:
    """1 holds the envelope's sustain, 0 lets it go."""
    ch.hold_override = True
    ch.bits1 = ch.bits1 & ~1 | (1 if arg else 0)


def FxWaveSample(module: Module, ch: Channel, arg: int) -> None:
    """This note plays another sample or wave."""
    if arg in module.samples:
        ch.wave_override = module.samples[arg]


def FxInitInstrument(module: Module, ch: Channel, arg: int) -> None:
    """The wave effects start again, even on the same instrument."""
    for sweep in (ch.phase, ch.resonance, ch.filter, ch.transform, ch.mix):
        sweep.last = -1


PART_EFFECTS: dict[int, PartEffect] = {  # FX_JumpTable, the modelled part
    0x10: FxVolume, 0x20: FxChannelVol, 0x30: FxMasterVol,
    0x40: FxSpeedPart, 0x41: FxGroovePart, 0x42: FxSpeedAll,
    0x43: FxGrooveAll, 0x44: FxArpeggioList, 0x46: FxHoldSustain,
    0x4A: FxWaveSample, 0x4B: FxInitInstrument,
}  # fmt: skip


# --- Helpers -----------------------------------------------------------


def output_volume(module: Module, ch: Channel) -> int:
    """Three factors in 1/16 steps, down to Paula's 0 to 64."""
    return (ch.volume3 * ch.channel_volume >> 10) * module.master >> 14


def wave_at(module: Module, number: int, size: int) -> Wave:
    """The copy of `size` bytes of wave `number`."""
    wave = module.samples[number]
    return wave.data, wave.loop + WAVE_OFFSETS[size]


def set_output(ch: Channel, buffer: bytearray) -> None:
    """The next effect in the chain reads this buffer; the channel plays
    the last one. The plain loop stays in `loop_org`."""
    ch.loop = (buffer, 0)
    if ch.is_wave or ch.effects1 >> LOOP & 1:
        ch.start = ch.loop


def view(wave: Wave, words: int) -> paula.Sample:
    """A live view: effects rewrite the buffer while it plays."""
    data, at = wave
    return paula.Sample(data, at, words)


def clamp(value: int, low: int, high: int) -> int:
    return max(low, min(value, high))


def trunc(value: int, divisor: int) -> int:
    return int(value / divisor)


def signed_byte(value: int) -> int:
    return value - 0x100 if value & 0x80 else value


def s16(value: int) -> int:
    value &= 0xFFFF
    return value - 0x10000 if value & 0x8000 else value
