"""MED four-channel replay, version 7.0: common/proplayer.a.

Card: players/MED.md. Level 2: the control flow runs; leaf math is a stub.
Each CamelCase function is a label in data/annot/MED.yaml; each CamelCase
class is in its `types:`. Comments name the replay's `trk_` fields.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum, auto

from specs import paula
from specs.controls import CommandList, Mode, StateMachine, TableWalker

NEVER = -1  # hold_left: the key is never released
MAX_VOLUME = 64  # volumes run 0..MAX_VOLUME
LIST_LENGTH = 128  # bytes per volume or wave list
FIRST_OPCODE = 0x80  # list bytes from here on are opcodes
WAVE_COUNT = 64  # waveforms per synth sound
ENVELOPE_LENGTH = 128  # bytes an envelope reads from a waveform
VIBRATO_STEPS = 32  # waveform bytes synth vibrato reads
MIN_SYNTH_PERIOD = 113  # synth periods are clamped here
FINETUNE = range(-8, 8)
CMD_PORTAMENTO = 3  # pattern command that keeps a hold
CMD_WAVE_LIST_POS = 0x0E
CMD_MISC = 0x0F  # argument 0xFF: note-off
CMD_LOOP = 0x16
NOTE_OFF = 0xFF
TRACK_VOLUME_BITS = 8  # track_volume is a fixed-point factor


# --- What the composer edits -------------------------------------------


@dataclass
class Command:
    number: int  # e.g. CMD_PORTAMENTO
    argument: int


@dataclass
class Row:  # MED: `line`
    note: int | None
    instrument: int | None  # without a note: the hold goes on
    commands: list[Command]  # one per command page


@dataclass
class Pattern:  # MED: `block`
    tracks: list[list[Row]]  # one track per voice; own row count


@dataclass
class Sample(paula.Sample):  # InstrHdr
    repeat: range = range(0)  # the looped part


@dataclass
class SynthSound:  # SynthInstr
    hybrid: bool  # waves[0] is a Sample
    volume_list: bytes  # up to LIST_LENGTH; from FIRST_OPCODE: opcodes
    wave_list: bytes  # up to LIST_LENGTH; from FIRST_OPCODE: opcodes
    volume_speed: int  # ticks per volume-list visit
    wave_speed: int  # ticks per wave-list visit
    waves: list[paula.Sample]  # up to WAVE_COUNT, played in place


class Kind(Enum):  # trk_synthtype: 0 none or sample, 1 synth, -1 hybrid
    NONE = auto()
    SAMPLE = auto()
    SYNTH = auto()
    HYBRID = auto()


@dataclass
class Instrument:  # MMD0sample, InstrExt
    volume: int  # 0..MAX_VOLUME: the note volume
    transpose: int  # semitones added to each note
    hold: int  # ticks the key stays down; 0: forever
    decay: int  # synth: release position; sample: fade speed
    finetune: int  # in FINETUNE
    sound: Sample | SynthSound

    def kind(self) -> Kind:
        if isinstance(self.sound, Sample):
            return Kind.SAMPLE
        return Kind.HYBRID if self.sound.hybrid else Kind.SYNTH


@dataclass
class Score:  # MMD0song
    patterns: list[Pattern]
    position_lists: list[list[int]]  # PlaySeq: pattern numbers
    sections: list[int]  # position-list numbers; may repeat
    play_transpose: int  # shifts every note
    ticks_per_row: int  # tempo2
    tempo: int
    track_volumes: list[int]
    instruments: list[Instrument]


# --- Voice state -------------------------------------------------------


@dataclass
class Vibrato(StateMachine):  # trk_synvibdep, trk_synthvibspd, trk_synviboffs
    depth: int = 0  # 0: off
    speed: int = 0
    phase: int = 0  # 16 phase units per waveform byte
    wave: bytes = b""  # trk_synvibwf: sine, or an instrument waveform


@dataclass
class Portamento(StateMachine):  # trk_porttrgper, trk_prevportspd
    target: int = 0
    speed: int = 0


@dataclass
class Voice:  # track data; track n plays on channel n
    channel: paula.Channel
    kind: Kind = Kind.NONE
    instrument: Instrument | None = None  # trk_previnstra: the last one given
    note: int = 0  # trk_prevnote2: the synth's note number
    period: int = 0  # trk_prevper: the Pattern's period
    note_volume: int = 0  # trk_prevvol
    track_volume: int = 0  # trk_trackvol: master and track volume
    hold: int = 0  # trk_inithold: the instrument's hold
    hold_left: int = NEVER  # trk_noteoffcnt
    decay: int = 0  # trk_decay
    fade_speed: int = 0  # trk_fadespd
    command_e: bool = False  # trk_miscflags bit 0
    volume_list: CommandList = field(default_factory=CommandList)  # trk_volcmd
    wave_list: CommandList = field(default_factory=CommandList)  # trk_wfcmd
    synth_volume: int = 0  # trk_synvol
    output_volume: int | None = None  # trk_tempvol: None is -1, use note_volume
    volume_slide: int = 0  # trk_volchgspd: 0 is off
    envelope: TableWalker = field(default_factory=TableWalker)  # trk_envptr
    pitch_slide: int = 0  # trk_perchg: the summed offset
    pitch_slide_speed: int = 0  # trk_wfchgspd
    synth_arpeggio: TableWalker = field(default_factory=TableWalker)  # trk_arpgoffs
    synth_vibrato: Vibrato = field(default_factory=Vibrato)
    pattern_portamento: Portamento = field(default_factory=Portamento)
    pattern_vibrato: int = 0  # trk_vibradjust; command 13 too
    pattern_arpeggio: int = 0  # trk_arpadjust


@dataclass
class Module:  # MMD0: the playback position lives in the module
    score: Score
    voices: list[Voice]
    counter: int = 0  # mmd_counter: ticks into the row
    section: int = 0  # mmd_psecnum
    position: int = 0  # mmd_pseqnum
    pattern: int = 0  # mmd_pblock
    row: int = 0  # mmd_pline


# --- Tick and row ------------------------------------------------------


def PlayTick(module: Module) -> None:
    """The timer interrupt. A row starts when the tick counter wraps.

    In BPM mode, only every fourth interrupt runs; see SetTempo.
    """
    module.counter += 1
    if module.counter >= module.score.ticks_per_row:
        module.counter = 0
        rows = current_rows(module)
        for voice, row in zip(module.voices, rows):
            read_row(voice, row, module.score)
        DoPreFX(module, rows)
        PlayRowNotes(module, rows)
        AdvSngPtr(module)
    DoFX(module)


def read_row(voice: Voice, row: Row, score: Score) -> None:
    """plr_loop0: an instrument number loads its settings, with or
    without a note. A note without one plays the last instrument."""
    if row.instrument is None:
        return
    instrument = score.instruments[row.instrument]
    voice.instrument = instrument
    voice.note_volume = instrument.volume
    voice.hold = instrument.hold
    voice.decay = instrument.decay
    voice.command_e = False


def PlayRowNotes(module: Module, rows: list[Row]) -> None:
    for voice, row in zip(module.voices, rows):
        if row.note is None or voice.instrument is None:
            continue
        voice.hold_left = voice.hold or NEVER  # hold 0: never released
        PlayNote(voice, row.note, voice.instrument, module.score)


def PlayNote(voice: Voice, note: int, instrument: Instrument, score: Score) -> None:
    note = AddTransposes(note, instrument, score)
    if not KeepSynthChannel(voice, instrument):
        voice.channel.stop()
    voice.fade_speed = 0
    sound = instrument.sound
    if isinstance(sound, SynthSound):
        StartSynthNote(voice, note, instrument, sound)
    else:
        voice.kind = Kind.SAMPLE
        voice.period = note_period(fold_octaves(note), instrument.finetune)
        play_sample(voice.channel, sound)


def AddTransposes(note: int, instrument: Instrument, score: Score) -> int:
    return note + score.play_transpose + instrument.transpose


def KeepSynthChannel(voice: Voice, instrument: Instrument) -> bool:
    """A synth after a synth skips the channel stop: the wave runs on."""
    return voice.kind == Kind.SYNTH and instrument.kind() == Kind.SYNTH


def StartSynthNote(
    voice: Voice, note: int, instrument: Instrument, sound: SynthSound
) -> None:
    """Resets both lists and all synth modulation. It sets no synth
    volume: the volume list must set one."""
    voice.note = note
    if sound.hybrid:
        voice.kind = Kind.HYBRID
        voice.period = note_period(fold_octaves(note), instrument.finetune)
        voice.channel.play(sound.waves[0])
    else:
        voice.kind = Kind.SYNTH
        voice.period = synth_period(note, instrument.finetune)
    voice.synth_arpeggio.mode = Mode.OFF
    voice.volume_list = CommandList(speed=sound.volume_speed)
    wave_pos = voice.wave_list.pos if voice.command_e else 0
    voice.wave_list = CommandList(pos=wave_pos, speed=sound.wave_speed)
    voice.volume_slide = 0
    voice.pitch_slide = voice.pitch_slide_speed = 0
    voice.envelope.mode = Mode.OFF
    voice.synth_vibrato = Vibrato(wave=SINE)


def AdvSngPtr(module: Module) -> None:
    """Steps to the next row; at a pattern end, to the next position.
    Then looks ahead for rows that extend a hold."""
    module.row += 1
    if module.row >= pattern_length(module):
        module.row = 0
        NextPlaySeq(module)
    ExtendHold(module)


def NextPlaySeq(module: Module) -> None:
    """Next position in the position list; at its end, the next section."""
    score = module.score
    module.position += 1
    if module.position >= len(score.position_lists[section_list(module)]):
        module.position = 0
        NextSection(module)
    module.pattern = score.position_lists[section_list(module)][module.position]


def NextSection(module: Module) -> None:
    """After the last section, the song starts again and signals its end."""
    module.section = (module.section + 1) % len(module.score.sections)


def ExtendHold(module: Module) -> None:
    """MED has no key-up. The key stays down while the next row has an
    instrument number without a note, or a note with portamento."""
    for voice, row in zip(module.voices, current_rows(module)):
        if voice.hold_left == NEVER:
            continue
        if row.note is None:
            keep = row.instrument is not None
        else:
            keep = bool(row.commands) and row.commands[0].number == CMD_PORTAMENTO
        if keep:
            voice.hold_left += module.score.ticks_per_row


# --- Pattern commands --------------------------------------------------


def DoPreFX(module: Module, rows: list[Row]) -> None:
    """Commands that act before the row's notes start."""
    for voice, row in zip(module.voices, rows):
        for command in row.commands:
            if command.number == CMD_WAVE_LIST_POS:
                CmdWaveListPos(voice, command.argument)
            elif command.number == CMD_MISC and command.argument == NOTE_OFF:
                CmdNoteOff(voice)
            elif command.number == CMD_LOOP:
                CmdLoop(module, command.argument)


def CmdWaveListPos(voice: Voice, pos: int) -> None:
    """Command E. A note on this row keeps this start; the wait stays."""
    voice.wave_list.pos = pos
    voice.command_e = True


def CmdNoteOff(voice: Voice) -> None:
    """A hard stop. It skips the volume list's release part."""
    ChannelOff(voice)


def ChannelOff(voice: Voice) -> None:
    voice.kind = Kind.NONE
    voice.channel.stop()


def CmdLoop(module: Module, count: int) -> None: ...  # 0: set loop row; n: repeat


def SetTempo(module: Module, tempo: int) -> None: ...  # CIA timer rate


def DoFX(module: Module) -> None:
    """Every tick: hold and fade, then each command page, then output."""
    for voice in module.voices:
        HoldAndFade(voice)
    for page in range(command_pages(module)):
        for voice, row in zip(module.voices, fx_rows(module)):
            if page < len(row.commands):
                ChannelFX(voice, row.commands[page], module.counter)
    for voice in module.voices:
        UpdatePerVol(voice)


def ChannelFX(voice: Voice, command: Command, tick: int) -> None:
    """Tick commands, like ProTracker's."""
    handler = TICK_COMMANDS.get(command.number)
    if handler is not None:
        handler(voice, command.argument, tick)


def ArpeggioTick(voice: Voice, arg: int, tick: int) -> None: ...  # 3-tick cycle


def PortamentoTick(voice: Voice, arg: int, tick: int) -> None: ...  # moves period


def VibratoTick(voice: Voice, arg: int, tick: int) -> None: ...  # sets pattern_vibrato


TICK_COMMANDS: dict[int, Callable[[Voice, int, int], None]] = {
    0x00: ArpeggioTick,
    0x03: PortamentoTick,
    0x04: VibratoTick,
}


# --- Hold and release --------------------------------------------------


def HoldAndFade(voice: Voice) -> None:
    if voice.hold_left != NEVER:
        voice.hold_left -= 1
        if voice.hold_left == NEVER:
            SynthRelease(voice)
    if voice.fade_speed:  # samples only
        voice.note_volume -= voice.fade_speed
        if voice.note_volume < 0:
            voice.note_volume, voice.fade_speed = 0, 0


def SynthRelease(voice: Voice) -> None:
    """Hold is over. A synth jumps its volume list to the decay position."""
    if voice.kind in (Kind.SYNTH, Kind.HYBRID):
        voice.volume_list.jump(voice.decay)
    elif voice.decay:
        voice.fade_speed = voice.decay
    else:
        voice.channel.stop()


# --- Output ------------------------------------------------------------


def UpdatePerVol(voice: Voice) -> None:
    """Writes period and volume. Pattern vibrato and arpeggio apply last."""
    period = voice.period  # PortamentoTick moves it
    if voice.kind in (Kind.SYNTH, Kind.HYBRID):
        period = SynthTick(voice)
    period += voice.pattern_vibrato - voice.pattern_arpeggio
    voice.pattern_vibrato = voice.pattern_arpeggio = 0
    voice.channel.period = period
    volume = voice.note_volume
    if voice.output_volume is not None:
        volume = voice.output_volume
    voice.output_volume = None
    voice.channel.volume = volume * voice.track_volume >> TRACK_VOLUME_BITS


def SynthTick(voice: Voice) -> int:
    """Once per tick for a synth or hybrid voice; returns its period.

    The volume list runs before the wave list. Each has its own speed.
    """
    sound = synth_sound(voice)
    if voice.volume_list.due():
        if voice.volume_slide:
            voice.synth_volume = clamp(
                voice.synth_volume + voice.volume_slide, 0, MAX_VOLUME
            )
        VolEnvelopeStep(voice)
        if not voice.volume_list.waiting():
            ReadVolumeList(voice, sound)
    voice.output_volume = voice.synth_volume * voice.note_volume // MAX_VOLUME
    period = WaveListTick(voice, sound)
    period = SynthArpeggio(voice, period)
    period = SynthVibrato(voice, period)
    return max(period + voice.pitch_slide, MIN_SYNTH_PERIOD)


def VolEnvelopeStep(voice: Voice) -> None:
    """An active envelope overwrites the slide's result."""
    byte = voice.envelope.step()
    if byte is not None:
        voice.synth_volume = ((byte + 128) & 0xFF) >> 2  # signed byte to 0..63


def WaveListTick(voice: Voice, sound: SynthSound) -> int:
    """The pitch slide steps on each visit, even while the list waits."""
    if voice.wave_list.due():
        voice.pitch_slide += voice.pitch_slide_speed
        if not voice.wave_list.waiting():
            ReadWaveList(voice, sound)
    return voice.period


def SynthArpeggio(voice: Voice, period: int) -> int:
    """Every tick. It replaces the period, so pattern portamento has no
    effect while it runs."""
    offset = voice.synth_arpeggio.step()
    if offset is None:
        return period
    return table_period(voice, voice.note + offset)


def SynthVibrato(voice: Voice, period: int) -> int:
    vibrato = voice.synth_vibrato
    if not vibrato.depth:
        return period
    byte = vibrato.wave[vibrato.phase >> 4 & VIBRATO_STEPS - 1]
    vibrato.phase += vibrato.speed
    return period + signed(byte) * vibrato.depth // 256


# --- Volume list -------------------------------------------------------

ListOpcode = Callable[[Voice, SynthSound, int], bool]  # True: read on
# VOLUME_OPCODES and WAVE_OPCODES are VolumeOpcodes and WaveOpcodes.


def ReadVolumeList(voice: Voice, sound: SynthSound) -> None:
    """Reads bytes until a value or an opcode ends the visit."""
    cursor = voice.volume_list
    while True:
        byte = sound.volume_list[cursor.pos]
        if byte < FIRST_OPCODE:
            voice.synth_volume = byte  # overwrites slide and envelope
            cursor.pos += 1
            return
        arg = sound.volume_list[cursor.pos + 1]
        opcode = VOLUME_OPCODES.get(byte)
        if opcode is None:
            cursor.pos += 1  # unused opcode: ends the visit
            return
        if not opcode(voice, sound, arg):
            return


def VolSpeed(voice: Voice, sound: SynthSound, arg: int) -> bool:
    """The new speed applies after the current count."""
    voice.volume_list.speed = arg
    voice.volume_list.pos += 2
    return True


def VolWait(voice: Voice, sound: SynthSound, arg: int) -> bool:
    voice.volume_list.wait = arg  # counts visits, not ticks
    voice.volume_list.pos += 2
    return False


def VolSlideDown(voice: Voice, sound: SynthSound, arg: int) -> bool:
    voice.volume_slide = -arg
    voice.volume_list.pos += 2
    return True


def VolSlideUp(voice: Voice, sound: SynthSound, arg: int) -> bool:
    voice.volume_slide = arg
    voice.volume_list.pos += 2
    return True


def VolEnvOnce(voice: Voice, sound: SynthSound, arg: int) -> bool:
    """A waveform, read as volumes, once. 128 visits long."""
    voice.envelope = envelope_from(sound.waves[arg], Mode.ONCE)
    voice.volume_list.pos += 2
    return True


def VolEnvLoop(voice: Voice, sound: SynthSound, arg: int) -> bool:
    voice.envelope = envelope_from(sound.waves[arg], Mode.LOOP)
    voice.volume_list.pos += 2
    return True


def VolEnvOff(voice: Voice, sound: SynthSound, arg: int) -> bool:
    voice.envelope.mode = Mode.OFF
    voice.volume_list.pos += 1
    return True


def VolJumpWaveList(voice: Voice, sound: SynthSound, arg: int) -> bool:
    """The wave list acts at its next visit; its counter runs on."""
    voice.wave_list.jump(arg)
    voice.volume_list.pos += 2
    return True


def VolJump(voice: Voice, sound: SynthSound, arg: int) -> bool:
    voice.volume_list.pos = arg
    return True


def VolListEnd(voice: Voice, sound: SynthSound, arg: int) -> bool:
    """Parks the list on itself. Slide and envelope run on."""
    return False


VOLUME_OPCODES: dict[int, ListOpcode] = {
    0xF0: VolSpeed,
    0xF1: VolWait,
    0xF2: VolSlideDown,
    0xF3: VolSlideUp,
    0xF4: VolEnvOnce,
    0xF5: VolEnvLoop,
    0xF6: VolEnvOff,
    0xFA: VolJumpWaveList,
    0xFB: VolListEnd,
    0xFE: VolJump,
    0xFF: VolListEnd,
}


# --- Wave list ---------------------------------------------------------


def ReadWaveList(voice: Voice, sound: SynthSound) -> None:
    """Reads bytes until a waveform or an opcode ends the visit."""
    cursor = voice.wave_list
    while True:
        byte = sound.wave_list[cursor.pos]
        if byte < FIRST_OPCODE:
            voice.channel.repeat(sound.waves[byte])  # in place, at the next wrap
            cursor.pos += 1
            return
        arg = sound.wave_list[cursor.pos + 1]
        opcode = WAVE_OPCODES.get(byte)
        if opcode is None:
            cursor.pos += 1
            return
        if not opcode(voice, sound, arg):
            return


def WaveSpeed(voice: Voice, sound: SynthSound, arg: int) -> bool:
    voice.wave_list.speed = arg
    voice.wave_list.pos += 2
    return True


def WaveWait(voice: Voice, sound: SynthSound, arg: int) -> bool:
    voice.wave_list.wait = arg
    voice.wave_list.pos += 2
    return False


def PitchSlideDown(voice: Voice, sound: SynthSound, arg: int) -> bool:
    voice.pitch_slide_speed = arg  # a larger period sounds lower
    voice.wave_list.pos += 2
    return True


def PitchSlideUp(voice: Voice, sound: SynthSound, arg: int) -> bool:
    voice.pitch_slide_speed = -arg
    voice.wave_list.pos += 2
    return True


def VibratoDepth(voice: Voice, sound: SynthSound, arg: int) -> bool:
    voice.synth_vibrato.depth = arg
    voice.wave_list.pos += 2
    return True


def VibratoSpeed(voice: Voice, sound: SynthSound, arg: int) -> bool:
    voice.synth_vibrato.speed = arg + 1
    voice.wave_list.pos += 2
    return True


def PitchReset(voice: Voice, sound: SynthSound, arg: int) -> bool:
    voice.pitch_slide = 0
    voice.wave_list.pos += 1
    return True


def VibratoWave(voice: Voice, sound: SynthSound, arg: int) -> bool:
    """A waveform becomes the vibrato shape."""
    voice.synth_vibrato.wave = sound.waves[arg].data
    voice.wave_list.pos += 2
    return True


def WaveJumpVolList(voice: Voice, sound: SynthSound, arg: int) -> bool:
    """The volume list acts at its next visit; its counter runs on."""
    voice.volume_list.jump(arg)
    voice.wave_list.pos += 2
    return True


def ArpeggioStart(voice: Voice, sound: SynthSound, arg: int) -> bool:
    """The bytes after the opcode, up to a negative byte, are note offsets.
    The arpeggio loops over them every tick, apart from the list."""
    start = voice.wave_list.pos + 1
    end = start
    while sound.wave_list[end] < FIRST_OPCODE:
        end += 1
    voice.synth_arpeggio = TableWalker(sound.wave_list[start:end], 0, Mode.LOOP)
    voice.wave_list.pos = end + 1
    return True


def skip_opcode(voice: Voice, sound: SynthSound, arg: int) -> bool:
    voice.wave_list.pos += 1
    return True


def WaveJump(voice: Voice, sound: SynthSound, arg: int) -> bool:
    voice.wave_list.pos = arg
    return True


def WaveListEnd(voice: Voice, sound: SynthSound, arg: int) -> bool:
    """Parks the list on itself. Pitch slide, arpeggio and vibrato run on."""
    return False


WAVE_OPCODES: dict[int, ListOpcode] = {
    0xF0: WaveSpeed,
    0xF1: WaveWait,
    0xF2: PitchSlideDown,
    0xF3: PitchSlideUp,
    0xF4: VibratoDepth,
    0xF5: VibratoSpeed,
    0xF6: PitchReset,
    0xF7: VibratoWave,
    0xFA: WaveJumpVolList,
    0xFB: WaveListEnd,
    0xFC: ArpeggioStart,
    0xFD: skip_opcode,
    0xFE: WaveJump,
    0xFF: WaveListEnd,
}


# --- Helpers -----------------------------------------------------------

SINE = bytes(
    b & 0xFF  # sinetable: 32 steps of a signed sine
    for b in (0, 25, 49, 71, 90, 106, 117, 125, 127, 125, 117, 106, 90, 71, 49, 25)
    + (0, -25, -49, -71, -90, -106, -117, -125, -127, -125, -117, -106, -90, -71)
    + (-49, -25)
)


def clamp(value: int, low: int, high: int) -> int:
    return max(low, min(value, high))


def signed(byte: int) -> int:
    return byte - 256 if byte >= 0x80 else byte


def envelope_from(wave: paula.Sample, mode: Mode) -> TableWalker:
    return TableWalker(wave.data[:ENVELOPE_LENGTH], 0, mode)


def synth_sound(voice: Voice) -> SynthSound:
    assert voice.instrument is not None
    sound = voice.instrument.sound
    assert isinstance(sound, SynthSound)
    return sound


def play_sample(channel: paula.Channel, sample: Sample) -> None:
    channel.play(sample)
    channel.repeat(paula.Sample(sample.data[sample.repeat.start : sample.repeat.stop]))


def fold_octaves(note: int) -> int: ...  # octave up or down into 0..62


def note_period(note: int, finetune: int) -> int: ...  # the period table


def synth_period(note: int, finetune: int) -> int: ...  # two octaves lower


def table_period(voice: Voice, note: int) -> int: ...  # trk_periodtbl


def current_rows(module: Module) -> list[Row]: ...  # one row per track


def fx_rows(module: Module) -> list[Row]: ...  # the row the commands came from


def pattern_length(module: Module) -> int: ...


def command_pages(module: Module) -> int: ...


def section_list(module: Module) -> int:
    return module.score.sections[module.section]
