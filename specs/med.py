"""MED four-channel replay, version 7.0: common/proplayer.a.

Card: players/MED.md. Level 2: the control flow runs; leaf math is a stub.
Each CamelCase function is a new name in data/annot/MED.yaml; each CamelCase
class is in its `types:`. Comments name the replay's `trk_` fields.
"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from enum import Enum, auto

from hardware import paula
from hardware.amiga import Amiga, Priority
from specs.controls import CommandList, Mode, TableWalker

NEVER = -1  # hold_left: the key is never released
MAX_VOLUME = 64  # volumes run 0..MAX_VOLUME
LIST_LENGTH = 128  # bytes per volume or wave list
FIRST_OPCODE = 0x80  # list bytes from here on are opcodes
WAVE_COUNT = 64  # waveforms per synth sound
ENVELOPE_LENGTH = 128  # bytes an envelope reads from a waveform
VIBRATO_STEPS = 32  # waveform bytes synth vibrato reads
FINETUNE = range(-8, 8)
CMD_PORTAMENTO = 3  # pattern command that keeps a hold
CMD_WAVE_LIST_POS = 0x0E
CMD_MISC = 0x0F  # argument 0xFF: note-off
CMD_LOOP = 0x16
NOTE_OFF = 0xFF
TRACK_VOLUME_BITS = 8  # track_volume is a fixed-point factor
TIMER_DIV = 470000  # TimerDivisor, PAL: latch = TIMER_DIV / tempo
BPM_DIV = 3546895 // 2  # BpmDivisor, PAL
SOUNDTRACKER_LATCHES = (  # SoundTrackerTempos: tempos 1..10
    *(2417, 4833, 7250, 9666, 12083),
    *(14500, 16916, 19332, 21436, 24163),
)
POLL_CCK = 25  # one WaitOneLine poll on a 68000: about 50 CPU cycles (estimate)
STOP_WAIT_CCK = 161 * POLL_CCK  # before DMA on: 161 polls, synth build
LOOP_WAIT_CCK = 81 * POLL_CCK  # before the loop write: 81 polls


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
    pages: int = 1  # command pages: BlockInfo's page table, plus 1


class Sample(paula.Sample):  # InstrHdr
    def __init__(self, memory: paula.Memory, repeat: range = range(0)):
        super().__init__(memory)
        self.repeat = repeat  # the looped part


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
    tempo: int  # deftempo
    bpm_mode: bool  # flags2 bit 5
    lines_per_beat: int  # flags2 bits 0-4, plus 1
    track_volumes: list[int]
    instruments: list[Instrument]
    st_slides: bool = False  # flags bit 5: slides skip a row's first tick


# --- Voice state -------------------------------------------------------


@dataclass
class Vibrato:  # trk_synvibdep, trk_synthvibspd, trk_synviboffs
    depth: int = 0  # 0: off
    speed: int = 0
    phase: int = 0  # 16 phase units per waveform byte
    wave: Sequence[int] = b""  # trk_synvibwf: sine, or an instrument waveform


@dataclass
class Portamento:  # trk_porttrgper, trk_prevportspd
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
    row_vibrato: Vibrato = field(default_factory=lambda: Vibrato(wave=SINE))
    # trk_vibrsz, trk_vibrspd, trk_vibroffs: 4 phase units per sine byte
    pattern_vibrato: int = 0  # trk_vibradjust; command 13 too
    pattern_arpeggio: int = 0  # trk_arpadjust
    row_note: int = 0  # trk_prevnote: the track's last note, 1-based
    periods: tuple[int, ...] = ()  # trk_periodtbl: set by the last note
    no_play: bool = False  # trk_fxtype: a command holds this row's note
    start: bool = False  # this channel's bit in DmaOnMask
    loop: paula.Sample | None = None  # trk_sampleptr, trk_samplelen


@dataclass
class Module:  # MMD0: the playback position lives in the module
    score: Score
    voices: list[Voice]
    amiga: Amiga  # MED plays by the CIA timer it got from the CIA resource
    counter: int = 0  # TickCounter: ticks into the row
    section: int = 0  # PlaySection
    position: int = 0  # PlayPosition
    pattern: int = 0  # PlayPattern
    row: int = 0  # PlayRow
    fx_pattern: int = 0  # FxPattern: the row whose commands run
    fx_row: int = 0
    loop_row: int = 0  # LoopRow: one loop for the whole song
    loop_count: int = 0  # LoopCount
    next_row: int = 0  # JumpRow: a jump's row + 1; 0 none


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
    StartDMA(module)


def read_row(voice: Voice, row: Row, score: Score) -> None:
    """ReadRowLoop: an instrument number loads its settings, with or
    without a note. A note without one plays the last instrument."""
    voice.no_play = False
    if row.note:
        voice.row_note = row.note
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
        if not row.note or voice.instrument is None or voice.no_play:
            continue
        voice.hold_left = voice.hold or NEVER  # hold 0: never released
        PlayNote(voice, row.note, voice.instrument, module.score)


def PlayNote(voice: Voice, note: int, instrument: Instrument, score: Score) -> None:
    note = AddTransposes(note, instrument, score) - 1  # notes are 1-based
    if not KeepSynthChannel(voice, instrument):
        voice.channel.disable()
    voice.fade_speed = 0
    voice.row_vibrato.phase = 0
    sound = instrument.sound
    if isinstance(sound, SynthSound):
        StartSynthNote(voice, note, instrument, sound)
    else:
        voice.kind = Kind.SAMPLE
        voice.periods = period_table(instrument.finetune)
        voice.period = voice.periods[fold_octaves(note)]
        queue_sample(voice, sound)


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
        voice.periods = period_table(instrument.finetune)
        voice.period = voice.periods[fold_octaves(note)]
        queue_sample(voice, sound.waves[0])
    else:
        voice.kind = Kind.SYNTH
        voice.periods = synth_table(instrument.finetune)  # 2 octaves lower
        voice.period = voice.periods[note]  # no octave folding
        voice.start = True  # the wave list queues the first waveform
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
    module.fx_pattern, module.fx_row = module.pattern, module.row
    if module.next_row:
        module.row, module.next_row = module.next_row - 1, 0
    else:
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
            elif command.number == CMD_PORTAMENTO:
                SetPortamento(module, voice, row, command.argument)


def SetPortamento(module: Module, voice: Voice, row: Row, speed: int) -> None:
    """Command 3 on a row: its note becomes the target and does not play.
    The target comes from the table of the voice's last note, with no
    octave folding. Speed 0 keeps the old speed."""
    voice.no_play = True
    if row.note:
        transpose = voice.instrument.transpose if voice.instrument else 0
        note = row.note - 1 + module.score.play_transpose + transpose
        if not voice.periods or note < 0:
            return
        voice.pattern_portamento.target = voice.periods[note]
    if speed:
        voice.pattern_portamento.speed = speed


def CmdWaveListPos(voice: Voice, pos: int) -> None:
    """Command E. A note on this row keeps this start; the wait stays."""
    voice.wave_list.pos = pos
    voice.command_e = True


def CmdNoteOff(voice: Voice) -> None:
    """A hard stop. It skips the volume list's release part."""
    ChannelOff(voice)


def ChannelOff(voice: Voice) -> None:
    voice.kind = Kind.NONE
    voice.channel.disable()


def CmdLoop(module: Module, count: int) -> None:
    """Command 16. 0 marks this row. n jumps back to the mark n times,
    then plays on. One loop serves the whole song, not each track."""
    if count == 0:
        module.loop_row = module.row
        return
    if module.loop_count:
        module.loop_count -= 1
        if module.loop_count == 0:
            return
    else:
        module.loop_count = count
    module.next_row = module.loop_row + 1


def SetTempo(module: Module, tempo: int) -> None:
    """Sets the timer latch. While the timer runs, the new tempo takes
    effect at the next underflow."""
    module.amiga.timer.set_latch(tempo_latch(module.score, tempo))


def start_timer(module: Module) -> None:
    """PlayModule: set the default tempo, then start the timer."""
    SetTempo(module, module.score.tempo)
    module.amiga.timer.start()


def new_module(score: Score, amiga: Amiga) -> Module:
    """Track n plays on channel n; the CIA timer runs PlayTick."""
    voices = [Voice(channel) for channel in amiga.paula.channels]
    module = Module(score, voices, amiga)
    amiga.timer.on_underflow = lambda: PlayTick(module)
    return module


def tempo_latch(score: Score, tempo: int) -> int:
    if score.bpm_mode:
        return BPM_DIV // (tempo * score.lines_per_beat)
    if tempo <= len(SOUNDTRACKER_LATCHES):
        return SOUNDTRACKER_LATCHES[tempo - 1]  # SoundTracker tempos
    return TIMER_DIV // tempo


def DoFX(module: Module) -> None:
    """Every tick: hold and fade, then each command page, then output."""
    for voice in module.voices:
        HoldAndFade(voice)
    for page in range(command_pages(module)):
        for voice, row in zip(module.voices, fx_rows(module)):
            if page < len(row.commands):
                ChannelFX(module, voice, row.commands[page], module.counter)
    for voice in module.voices:
        UpdatePerVol(voice)


def StartDMA(module: Module) -> None:
    """After each tick: wait, set the DMACON bits, wait, write the loops.

    Each wait polls the beam position until it changes, a set number of
    times. The first lets stopped channels finish their word and go idle,
    so DMA on restarts them. The second lets the start reload pass before
    the loop write. On a 68000 both last far longer than the one line a
    start takes. A faster CPU polls faster, so the waits shrink. The
    replay's own comment says "sometimes double wait time is required".
    """
    starting = [voice for voice in module.voices if voice.start]

    def dma_on() -> None:
        for voice in starting:
            voice.start = False
            voice.channel.enable()
        module.amiga.after(LOOP_WAIT_CCK, Priority.CPU, write_loops)

    def write_loops() -> None:
        for voice in starting:
            if voice.loop is not None:
                voice.channel.queue(voice.loop)

    if starting:
        module.amiga.after(STOP_WAIT_CCK, Priority.CPU, dma_on)


def ChannelFX(module: Module, voice: Voice, command: Command, tick: int) -> None:
    """Tick commands, like ProTracker's. `tick` counts from 0 in a row."""
    handler = TICK_COMMANDS.get(command.number)
    if handler is not None:
        handler(module, voice, command.argument, tick)


def ArpeggioTick(module: Module, voice: Voice, arg: int, tick: int) -> None:
    """Command 0. A 3-tick cycle: + high nibble, + low nibble, + 0. So a
    row starts on the high note, unlike ProTracker. The offset is the
    period difference from the track's last note, in its table."""
    if not arg or not voice.periods:
        return
    offset = (arg >> 4, arg & 0x0F, 0)[tick % 3]
    transpose = voice.instrument.transpose if voice.instrument else 0
    base = voice.row_note - 1 + module.score.play_transpose + transpose
    voice.pattern_arpeggio = voice.periods[base] - voice.periods[base + offset]


def PortamentoTick(module: Module, voice: Voice, arg: int, tick: int) -> None:
    """Command 3. The period moves towards SetPortamento's target by
    `speed` per tick and stops there. With SoundTracker slides, a row's
    first tick is skipped."""
    glide = voice.pattern_portamento
    if tick == 0 and module.score.st_slides or not glide.target:
        return
    if voice.period > glide.target:
        period = voice.period - glide.speed
        reached = period <= glide.target
    else:
        period = voice.period + glide.speed
        reached = period >= glide.target
    if reached:
        period, glide.target = glide.target, 0
    voice.period = period


def VibratoTick(module: Module, voice: Voice, arg: int, tick: int) -> None:
    """Command 4. On a row's first tick, the low nibble sets the depth and
    the high nibble the speed; 0 keeps the old one. Every tick, sine ×
    depth / 32 goes to the period. A note restarts the phase."""
    vibrato = voice.row_vibrato
    if tick == 0 and arg:
        if arg & 0x0F:
            vibrato.depth = arg & 0x0F
        if arg & 0xF0:
            vibrato.speed = arg >> 3 & 0x3E
    byte = vibrato.wave[vibrato.phase >> 2 & VIBRATO_STEPS - 1]
    voice.pattern_vibrato = signed(byte) * vibrato.depth >> 5
    vibrato.phase = (vibrato.phase + vibrato.speed) & 0xFF


TICK_COMMANDS: dict[int, Callable[[Module, Voice, int, int], None]] = {
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
        voice.channel.disable()


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
    voice.channel.set_volume(volume * voice.track_volume >> TRACK_VOLUME_BITS)


def SynthTick(voice: Voice) -> int:
    """Once per tick for a synth or hybrid voice; returns its period.

    The volume list runs before the wave list. Each has its own speed.
    The replay means to clamp the period at 113, but its `moveq #113`
    writes the wrong register, so no clamp happens.
    """
    sound = synth_sound(voice)
    if voice.volume_list.due():
        if voice.volume_slide:
            voice.synth_volume = clamp(
                voice.synth_volume + voice.volume_slide, 0, MAX_VOLUME
            )
        VolEnvelopeStep(voice)
        if not waiting(voice.volume_list):
            ReadVolumeList(voice, sound)
    voice.output_volume = voice.synth_volume * voice.note_volume // MAX_VOLUME
    period = WaveListTick(voice, sound)
    period = SynthArpeggio(voice, period)
    period = SynthVibrato(voice, period)
    return period + voice.pitch_slide


def waiting(commands: CommandList) -> bool:
    """Count one visit off a wait; True while the wait lasts.

    A wait counts visits, not ticks. A jump from elsewhere clears the
    wait but not the counter, so the target acts at its next visit.
    """
    if commands.wait == 0:
        return False
    commands.wait -= 1
    return commands.wait > 0


def VolEnvelopeStep(voice: Voice) -> None:
    """An active envelope overwrites the slide's result."""
    byte = voice.envelope.step()
    if byte is not None:
        voice.synth_volume = ((byte + 128) & 0xFF) >> 2  # signed byte to 0..63


def WaveListTick(voice: Voice, sound: SynthSound) -> int:
    """The pitch slide steps on each visit, even while the list waits."""
    if voice.wave_list.due():
        voice.pitch_slide += voice.pitch_slide_speed
        if not waiting(voice.wave_list):
            ReadWaveList(voice, sound)
    return voice.period


def SynthArpeggio(voice: Voice, period: int) -> int:
    """Every tick. It replaces the period, so pattern portamento has no
    effect while it runs."""
    offset = voice.synth_arpeggio.step()
    if offset is None:
        return period
    return voice.periods[voice.note + offset]


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
            voice.channel.queue(sound.waves[byte])  # in place, at the next reload
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
    voice.synth_vibrato.wave = sound.waves[arg]
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

SINE: bytes = bytes(
    b & 0xFF  # SineTable: 32 steps of a signed sine
    for b in (0, 25, 49, 71, 90, 106, 117, 125, 127, 125, 117, 106, 90, 71, 49, 25)
    + (0, -25, -49, -71, -90, -106, -117, -125, -127, -125, -117, -106, -90, -71)
    + (-49, -25)
)


def clamp(value: int, low: int, high: int) -> int:
    return max(low, min(value, high))


def signed(byte: int) -> int:
    return byte - 256 if byte >= 0x80 else byte


def envelope_from(wave: paula.Sample, mode: Mode) -> TableWalker:
    return TableWalker(wave[:ENVELOPE_LENGTH], 0, mode)


def synth_sound(voice: Voice) -> SynthSound:
    assert voice.instrument is not None
    sound = voice.instrument.sound
    assert isinstance(sound, SynthSound)
    return sound


def queue_sample(voice: Voice, sample: paula.Sample) -> None:
    """Writes AUDxLC and AUDxLEN; StartDMA starts the channel later."""
    voice.channel.queue(sample)
    voice.loop = None
    if isinstance(sample, Sample):
        voice.loop = paula.Sample(sample[sample.repeat.start : sample.repeat.stop])
    voice.start = True


PERIODS: dict[
    int, tuple[int, ...]
] = {  # PeriodsMinus8 to Periods7: 24 synth-only, 36 notes
    -8: (  # PeriodsMinus8
        *(3628, 3424, 3232, 3051, 2880, 2718, 2565, 2421, 2285, 2157, 2036, 1922),
        *(1814, 1712, 1616, 1525, 1440, 1359, 1283, 1211, 1143, 1079, 1018, 961),
        *(907, 856, 808, 762, 720, 678, 640, 604, 570, 538, 508, 480),
        *(453, 428, 404, 381, 360, 339, 320, 302, 285, 269, 254, 240),
        *(226, 214, 202, 190, 180, 170, 160, 151, 143, 135, 127, 120),
    ),
    -7: (  # PeriodsMinus7
        *(3588, 3387, 3197, 3017, 2848, 2688, 2537, 2395, 2260, 2133, 2014, 1901),
        *(1794, 1693, 1598, 1509, 1424, 1344, 1269, 1197, 1130, 1067, 1007, 950),
        *(900, 850, 802, 757, 715, 675, 636, 601, 567, 535, 505, 477),
        *(450, 425, 401, 379, 357, 337, 318, 300, 284, 268, 253, 238),
        *(225, 212, 200, 189, 179, 169, 159, 150, 142, 134, 126, 119),
    ),
    -6: (  # PeriodsMinus6
        *(3576, 3375, 3186, 3007, 2838, 2679, 2529, 2387, 2253, 2126, 2007, 1894),
        *(1788, 1688, 1593, 1504, 1419, 1339, 1264, 1193, 1126, 1063, 1003, 947),
        *(894, 844, 796, 752, 709, 670, 632, 597, 563, 532, 502, 474),
        *(447, 422, 398, 376, 355, 335, 316, 298, 282, 266, 251, 237),
        *(223, 211, 199, 188, 177, 167, 158, 149, 141, 133, 125, 118),
    ),
    -5: (  # PeriodsMinus5
        *(3548, 3349, 3161, 2984, 2816, 2658, 2509, 2368, 2235, 2110, 1991, 1879),
        *(1774, 1674, 1580, 1492, 1408, 1329, 1254, 1184, 1118, 1055, 996, 940),
        *(887, 838, 791, 746, 704, 665, 628, 592, 559, 528, 498, 470),
        *(444, 419, 395, 373, 352, 332, 314, 296, 280, 264, 249, 235),
        *(222, 209, 198, 187, 176, 166, 157, 148, 140, 132, 125, 118),
    ),
    -4: (  # PeriodsMinus4
        *(3524, 3326, 3140, 2963, 2797, 2640, 2492, 2352, 2220, 2095, 1978, 1867),
        *(1762, 1663, 1570, 1482, 1399, 1320, 1246, 1176, 1110, 1048, 989, 933),
        *(881, 832, 785, 741, 699, 660, 623, 588, 555, 524, 494, 467),
        *(441, 416, 392, 370, 350, 330, 312, 294, 278, 262, 247, 233),
        *(220, 208, 196, 185, 175, 165, 156, 147, 139, 131, 123, 117),
    ),
    -3: (  # PeriodsMinus3
        *(3500, 3304, 3118, 2943, 2778, 2622, 2475, 2336, 2205, 2081, 1964, 1854),
        *(1750, 1652, 1559, 1472, 1389, 1311, 1237, 1168, 1102, 1041, 982, 927),
        *(875, 826, 779, 736, 694, 655, 619, 584, 551, 520, 491, 463),
        *(437, 413, 390, 368, 347, 328, 309, 292, 276, 260, 245, 232),
        *(219, 206, 195, 184, 174, 164, 155, 146, 138, 130, 123, 116),
    ),
    -2: (  # PeriodsMinus2
        *(3472, 3277, 3093, 2920, 2756, 2601, 2455, 2317, 2187, 2064, 1949, 1839),
        *(1736, 1639, 1547, 1460, 1378, 1301, 1228, 1159, 1094, 1032, 974, 920),
        *(868, 820, 774, 730, 689, 651, 614, 580, 547, 516, 487, 460),
        *(434, 410, 387, 365, 345, 325, 307, 290, 274, 258, 244, 230),
        *(217, 205, 193, 183, 172, 163, 154, 145, 137, 129, 122, 115),
    ),
    -1: (  # PeriodsMinus1
        *(3448, 3254, 3072, 2899, 2737, 2583, 2438, 2301, 2172, 2050, 1935, 1827),
        *(1724, 1627, 1536, 1450, 1368, 1292, 1219, 1151, 1086, 1025, 968, 913),
        *(862, 814, 768, 725, 684, 646, 610, 575, 543, 513, 484, 457),
        *(431, 407, 384, 363, 342, 323, 305, 288, 272, 256, 242, 228),
        *(216, 203, 192, 181, 171, 161, 152, 144, 136, 128, 121, 114),
    ),
    0: (  # Periods0
        *(3424, 3232, 3048, 2880, 2712, 2560, 2416, 2280, 2152, 2032, 1920, 1812),
        *(1712, 1616, 1524, 1440, 1356, 1280, 1208, 1140, 1076, 1016, 960, 906),
        *(856, 808, 762, 720, 678, 640, 604, 570, 538, 508, 480, 453),
        *(428, 404, 381, 360, 339, 320, 302, 285, 269, 254, 240, 226),
        *(214, 202, 190, 180, 170, 160, 151, 143, 135, 127, 120, 113),
    ),
    1: (  # Periods1
        *(3400, 3209, 3029, 2859, 2699, 2547, 2404, 2269, 2142, 2022, 1908, 1801),
        *(1700, 1605, 1515, 1430, 1349, 1274, 1202, 1135, 1071, 1011, 954, 901),
        *(850, 802, 757, 715, 674, 637, 601, 567, 535, 505, 477, 450),
        *(425, 401, 379, 357, 337, 318, 300, 284, 268, 253, 239, 225),
        *(213, 201, 189, 179, 169, 159, 150, 142, 134, 126, 119, 113),
    ),
    2: (  # Periods2
        *(3376, 3187, 3008, 2839, 2680, 2529, 2387, 2253, 2127, 2007, 1895, 1788),
        *(1688, 1593, 1504, 1419, 1340, 1265, 1194, 1127, 1063, 1004, 947, 894),
        *(844, 796, 752, 709, 670, 632, 597, 563, 532, 502, 474, 447),
        *(422, 398, 376, 355, 335, 316, 298, 282, 266, 251, 237, 224),
        *(211, 199, 188, 177, 167, 158, 149, 141, 133, 125, 118, 112),
    ),
    3: (  # Periods3
        *(3352, 3164, 2986, 2819, 2660, 2511, 2370, 2237, 2112, 1993, 1881, 1776),
        *(1676, 1582, 1493, 1409, 1330, 1256, 1185, 1119, 1056, 997, 941, 888),
        *(838, 791, 746, 704, 665, 628, 592, 559, 528, 498, 470, 444),
        *(419, 395, 373, 352, 332, 314, 296, 280, 264, 249, 235, 222),
        *(209, 198, 187, 176, 166, 157, 148, 140, 132, 125, 118, 111),
    ),
    4: (  # Periods4
        *(3328, 3141, 2965, 2799, 2641, 2493, 2353, 2221, 2097, 1979, 1868, 1763),
        *(1664, 1571, 1482, 1399, 1321, 1247, 1177, 1111, 1048, 989, 934, 881),
        *(832, 785, 741, 699, 660, 623, 588, 555, 524, 495, 467, 441),
        *(416, 392, 370, 350, 330, 312, 294, 278, 262, 247, 233, 220),
        *(208, 196, 185, 175, 165, 156, 147, 139, 131, 124, 117, 110),
    ),
    5: (  # Periods5
        *(3304, 3119, 2944, 2778, 2622, 2475, 2336, 2205, 2081, 1965, 1854, 1750),
        *(1652, 1559, 1472, 1389, 1311, 1238, 1168, 1103, 1041, 982, 927, 875),
        *(826, 779, 736, 694, 655, 619, 584, 551, 520, 491, 463, 437),
        *(413, 390, 368, 347, 328, 309, 292, 276, 260, 245, 232, 219),
        *(206, 195, 184, 174, 164, 155, 146, 138, 130, 123, 116, 109),
    ),
    6: (  # Periods6
        *(3280, 3096, 2922, 2758, 2603, 2457, 2319, 2189, 2066, 1950, 1841, 1738),
        *(1640, 1548, 1461, 1379, 1302, 1229, 1160, 1095, 1033, 975, 920, 869),
        *(820, 774, 730, 689, 651, 614, 580, 547, 516, 487, 460, 434),
        *(410, 387, 365, 345, 325, 307, 290, 274, 258, 244, 230, 217),
        *(205, 193, 183, 172, 163, 154, 145, 137, 129, 122, 115, 109),
    ),
    7: (  # Periods7
        *(3256, 3073, 2901, 2738, 2584, 2439, 2302, 2173, 2051, 1936, 1827, 1725),
        *(1628, 1537, 1450, 1369, 1292, 1220, 1151, 1087, 1026, 968, 914, 862),
        *(814, 768, 725, 684, 646, 610, 575, 543, 513, 484, 457, 431),
        *(407, 384, 363, 342, 323, 305, 288, 272, 256, 242, 228, 216),
        *(204, 192, 181, 171, 161, 152, 144, 136, 128, 121, 114, 108),
    ),
}


def full_table(finetune: int) -> tuple[int, ...]:
    """96 periods: 24 synth-only, 3 octaves, then the top octave 3 times
    more. Notes above the third octave do not rise."""
    periods = PERIODS[finetune]
    return periods + periods[-12:] * 3


def period_table(finetune: int) -> tuple[int, ...]:
    """PeriodTables: a sample's table, by finetune."""
    return full_table(finetune)[24:]


def synth_table(finetune: int) -> tuple[int, ...]:
    """A synth's table starts 48 bytes earlier: two octaves lower."""
    return full_table(finetune)


def fold_octaves(note: int) -> int:
    """An octave up until the note is 0 or more; one octave down if it is
    above 62. Only once: a note above 74 stays too high."""
    while note < 0:
        note += 12
    return note - 12 if note > 62 else note


def current_rows(module: Module) -> list[Row]:
    pattern = module.score.patterns[module.pattern]
    return [track[module.row] for track in pattern.tracks]


def fx_rows(module: Module) -> list[Row]:
    """The row just played: its commands run on every tick of it."""
    pattern = module.score.patterns[module.fx_pattern]
    return [track[module.fx_row] for track in pattern.tracks]


def pattern_length(module: Module) -> int:
    return len(module.score.patterns[module.pattern].tracks[0])


def command_pages(module: Module) -> int:
    return module.score.patterns[module.fx_pattern].pages


def section_list(module: Module) -> int:
    return module.score.sections[module.section]
