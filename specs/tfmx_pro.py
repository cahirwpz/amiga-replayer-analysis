"""TFMX Pro four-voice replay: TFMX Pro_v5.asm.

Card: players/TFMX-Pro.md. Level 2: the control flow runs; leaf math is a
stub. Each CamelCase function is a label in data/annot/TFMX-Pro.yaml; each
CamelCase class is in its `types:`. Comments name the replay's fields.

The source is Wanted Team's EaglePlayer adaptation. It adds a "DMA wait"
mode that busy-waits instead of deferring DMA changes. This spec follows
the original "VBI wait" path, the default. The adaptation's volume fix in
the DMA-off opcode is left out.
"""

from collections.abc import Callable
from dataclasses import dataclass, field

from hardware import paula
from hardware.amiga import Amiga
from specs.controls import Program, StateMachine

TRACKS = 8
VOICES = 4
NOTE_MASK = 0x3F  # 64 notes
NOTE_WAIT = 0x7F  # pattern bytes $7f-$bf: a note, then a wait
PORTAMENTO_NOTE = 0xC0  # pattern bytes $c0-$ef: a portamento note
FIRST_PATTERN_OPCODE = 0xF0
TRACK_OFF = 0xFE  # position word: stop the voice named in the low byte
TRACK_HOLD = 0x80  # position words from here keep the running pattern
TRACK_IDLE = 0x90  # track pattern bytes from here: the track reads nothing
POSITION_SPECIAL = 0xEFFE  # a position that holds a command, not 8 tracks
FULL_VOLUME = 0x40  # fade level 64, and bit 6: fade does not scale
FLUSH_PERIOD = 9  # the shortest period, so a stopped channel ends its word
LOW_MEMORY = 0x80000  # byte checks address $80000 + offset, in 512 KB
LOW_MEMORY_MASK = 0x7FFFF
RANDOM_ADD = 0x4335
IMS_BUFFERS = 4  # ims_doffs: voice n's buffer is at 4 + $100 × n
IMS_BUFFER = 0x100  # bytes per voice's IMS buffer


# --- What the composer edits -------------------------------------------

Statement = bytes  # 4 bytes: opcode or note, then 3 argument bytes


def word(s: Statement) -> int:
    """Bytes 2 and 3, the argument of most opcodes."""
    return s[2] << 8 | s[3]


def signed_word(s: Statement) -> int:
    value = word(s)
    return value - 0x10000 if value & 0x8000 else value


def long(s: Statement) -> int:
    """Bytes 1 to 3: an offset into the sample file."""
    return s[1] << 16 | word(s)


@dataclass
class Score:  # the module's header: database, pattnbase, macrobase
    positions: list[bytes]  # 16 bytes: per track, pattern byte and transpose
    patterns: list[list[Statement]]
    macros: list[list[Statement]]  # shared by all voices; opcodes rewrite them
    samples: bytearray  # one sample file; IMS buffers live in its first KB
    first: int  # fstep
    last: int  # lstep
    speed: int  # ticks per row, minus one
    mutes: list[bool]  # per track


@dataclass
class SoundEffect:  # fxbase: 8 bytes per effect
    note: Statement  # its voice nibble is replaced
    voice: int
    priority: int  # bit 7: no repeat while it plays
    ticks: int  # priocount: how long it locks the voice


# --- Track and voice state ---------------------------------------------


@dataclass
class Track(Program):  # CHfield2: patterns, padress, pstep, pawait
    pattern: int = TRACK_IDLE  # the pattern byte; TRACK_IDLE and up: off
    transpose: int = 0
    statements: list[Statement] = field(default_factory=list)
    loop_count: int = 0  # ploopcount
    returns: tuple[list[Statement], int] | None = None  # psubadr, psubstep


@dataclass
class Macro(Program):  # madress, mstep, mawait
    statements: list[Statement] = field(default_factory=list)
    running: bool = False  # mstatus
    loop_count: int = 0  # mloopcount; WaitNoteOff counts in it too
    returns: tuple[list[Statement], int] | None = None  # msubadr, msubstep
    skip_seen: bool = False  # mskipflag
    no_yield: bool = False  # nwait clear: the next yield does not end the tick
    loop_waits: int = 0  # irwait: sample passes to wait


@dataclass
class Sweep(StateMachine):  # mabcount1, mabcount2, mabadd
    left: int = 0  # 0: off
    length: int = 0
    step: int = 0  # bytes per tick; the sign flips every `length` ticks


@dataclass
class Swing(StateMachine):  # ims_mod1add, ims_mod1len, ims_mod1len2
    """An add per tick whose sign turns every `length` ticks."""

    add: int = 0
    left: int = 0
    length: int = 0  # 0: it never turns

    def tick(self) -> int:
        """This tick's add; then counts, and may turn."""
        add = self.add
        self.left = (self.left - 1) & 0xFFFF
        if self.left == 0:
            self.left = self.length
            if self.length:
                self.add = -self.add
        return add


@dataclass
class Ims(StateMachine):  # ims_ fields: interference modulation synthesis
    length: int = 0  # ims_dlen: bytes to build, minus one; 0 off
    source: int = 0  # ims_sstart: offset in the sample file
    mask: int = 0  # ims_slen: source offsets wrap with it; 2^n - 1
    step: int = 0  # ims_mod1: source bytes per output byte, 16.16
    step_change: int = 0  # ims_mod2: added to the step per byte, 16.16
    step_swing: Swing = field(default_factory=Swing)
    change_swing: Swing = field(default_factory=Swing)
    delta: int = 0  # ims_delta: 8.8; the high byte limits each change
    delta_swing: Swing = field(default_factory=Swing)  # ims_fspeed, ims_flen
    last: int = 0  # ims_deltaold: the last output byte, signed
    mirror: bool = False  # ims_dolby: negated copy into the next buffer
    buffer: int = 0  # ims_doffs: this voice's buffer in the sample file


@dataclass
class Vibrato(StateMachine):  # vibsize1, vibsize2, vibrate, vibperiod
    size: int = 0  # ticks per direction; 0 off
    left: int = 0
    rate: int = 0  # signed; added to `offset` each tick
    offset: int = 0  # the period factor is (2048 + offset) / 2048


@dataclass
class Portamento(StateMachine):  # potime, pospeed, pocount, poperiod
    rate: int = 0  # the period factor is (256 +- rate) / 256; 0 off
    speed: int = 0  # ticks per step
    count: int = 0
    period: int = 0  # the gliding period; the target is base_period


@dataclass
class Envelope(StateMachine):  # envelope, envcount, envspeed, envolume
    delay: int = 0  # ticks between steps, plus one; 0 off
    count: int = 0
    step: int = 0
    target: int = 0


@dataclass
class Riff(StateMachine):  # riffstats, riffsteps, riffspeed, riffrandm
    state: int = 0  # riffstats: 0 off, 1 start, -1 playing
    macro: int = 0  # riffmacro: its bytes are the riff
    notes: bytes = b""  # riffadres
    step: int = 0  # riffsteps
    speed: int = 0  # ticks per riff step
    count: int = 0
    random: bool = False  # riffrandm bit 0
    echo: bool = False  # riffrandm bit 1
    no_rests: bool = False  # riffrandm bit 2
    mask: int = 0  # riffAND: random steps are masked with it
    trigger: bool = False  # rifftrigg: a riff-triggered wait is pending


@dataclass
class Voice:  # Synthfield: one per Paula channel
    channel: paula.Channel
    next: "Voice | None" = None  # channadd: riff echo and IMS mirror target
    macro: Macro = field(default_factory=Macro)
    effects: int = 0  # modstatus: <0 paused, 0 wait one tick, >0 run
    key_down: bool = False  # keyflag
    note: int = 0  # basenote low byte
    last_note: int = 0  # basenote high byte
    note_volume: int = 0  # basevol: the pattern's 0..15
    detune: int = 0  # detunes: the pattern's, signed
    volume: int = 0  # the voice's volume byte
    base_period: int = 0  # baseperiod: vibrato centre, portamento target
    period: int = 0  # written to Paula at the end of the tick
    start: int = 0  # sbegin: offset in the sample file
    length: int = 0  # samplen, in words
    sweep: Sweep = field(default_factory=Sweep)
    ims: Ims = field(default_factory=Ims)
    vibrato: Vibrato = field(default_factory=Vibrato)
    portamento: Portamento = field(default_factory=Portamento)
    envelope: Envelope = field(default_factory=Envelope)
    riff: Riff = field(default_factory=Riff)
    priority: int = 0  # a sound effect locks the voice while nonzero
    next_priority: int = 0  # priority2
    priority_ticks: int = -1  # priocount: the lock's ticks left
    effect_note: Statement | None = None  # fxnote: plays at the next tick
    last_effect: int = -1  # oldfx
    dma_on: bool = False  # this voice's bit in dmaconhelp
    dma_off_next: bool = False  # this voice's bit in dmaconhelp+2


@dataclass
class Fade(StateMachine):  # fadevol, fadeend, fadeadd, fadecount1/2
    level: int = FULL_VOLUME
    target: int = FULL_VOLUME
    step: int = 0  # +1, -1, or 0 off
    count: int = 0
    speed: int = 0  # visits per step
    running: bool = False  # info_fade: a new fade waits for this one


@dataclass
class Module:  # CHfield0: song state; CHfield2: tracks
    score: Score
    voices: list[Voice]
    tracks: list[Track]
    amiga: Amiga
    effects: list[SoundEffect] = field(default_factory=list)
    playing: bool = True  # allon
    position: int = 0  # cstep
    position_loops: int = 0  # tloopcount: 0 first visit, -1 done
    speed: int = 0
    count: int = 0  # scount
    new_position: bool = False  # newstep: rerun every track this row
    custom: bool = False  # track 7 plays a game pattern; positions skip it
    fade: Fade = field(default_factory=Fade)
    random: int = 0
    flags: list[int] = field(default_factory=lambda: [0] * 4)  # info_flags


# --- Tick ---------------------------------------------------------------


def PlayTick(module: Module) -> None:
    """The timer interrupt. Voices first, then the tracks, then Paula.

    A note from a track starts its macro at the next tick. Periods and
    DMA-on bits are collected and written last. A deferred DMA off waits
    for the next tick's start; it sets the shortest period so the channel
    ends its word before the macro restarts it.
    """
    for voice in module.voices:
        if voice.dma_off_next:
            voice.dma_off_next = False
            voice.channel.disable()
            voice.channel.period = FLUSH_PERIOD
    if not module.playing:
        return
    VoicesTick(module)
    Sequencer(module)
    for voice in module.voices:
        voice.channel.period = voice.period
    for voice in module.voices:
        if voice.dma_on:
            voice.dma_on = False
            voice.channel.enable()


def VoicesTick(module: Module) -> None:
    for voice in module.voices:
        VoiceTick(module, voice)


def VoiceTick(module: Module, voice: Voice) -> None:
    """Counts down a sound effect's lock, plays a pending effect note,
    then runs the macro, the effects and the fade."""
    if voice.priority_ticks >= 0:
        voice.priority_ticks -= 1
    else:
        voice.priority = voice.next_priority = 0
    if voice.effect_note is not None:
        note, voice.effect_note = voice.effect_note, None
        voice.priority = 0
        NoteToVoice(module, note)
        voice.priority = voice.next_priority
    RunMacro(module, voice)
    ModulationTick(module, voice)


# --- Tracks and positions ----------------------------------------------


def Sequencer(module: Module) -> None:
    """A row starts every speed + 1 ticks."""
    module.count -= 1
    if module.count >= 0:
        return
    module.count = module.speed
    PlayTracks(module)


def PlayTracks(module: Module) -> None:
    """Each track reads until a wait. A pattern end on any track moves
    every track to the next position, then the row starts again."""
    while True:
        module.new_position = False
        for track in module.tracks:
            TrackStart(module, track)
            if module.new_position:
                break
        else:
            return


def TrackStart(module: Module, track: Track) -> None:
    number = module.tracks.index(track)
    if track.pattern >= TRACK_IDLE:
        if track.pattern == TRACK_OFF:
            track.pattern = 0xFF
            if not module.score.mutes[number]:
                StopVoice(module, track.transpose)
        return
    if track.wait:
        track.wait -= 1
        return
    ReadPattern(module, track)


def ReadPattern(module: Module, track: Track) -> None:
    """Notes $00-$7e and $c0-$ef read on; $7f-$bf and a wait end the row."""
    number = module.tracks.index(track)
    while True:
        s = bytearray(track.statements[track.pos])
        if s[0] >= FIRST_PATTERN_OPCODE:
            if not PatternOpcode(module, track, bytes(s)):
                return
            continue
        TrackNote(module, track, s, muted=module.score.mutes[number])
        track.pos += 1
        if NOTE_WAIT <= s[0] < PORTAMENTO_NOTE:
            return


def TrackNote(module: Module, track: Track, s: bytearray, muted: bool) -> None:
    """Adds the track's transpose. A waiting note takes its wait from the
    detune byte, so it plays without detune."""
    if NOTE_WAIT <= s[0] < PORTAMENTO_NOTE:
        track.wait, s[3] = s[3], 0
    note = (s[0] + track.transpose) & 0xFF
    s[0] = note if s[0] >= PORTAMENTO_NOTE else note & NOTE_MASK
    if not muted:
        NoteToVoice(module, bytes(s))


PatternHandler = Callable[[Module, Track, Statement], bool]  # True: read on


def PatternOpcode(module: Module, track: Track, s: Statement) -> bool:
    handler = PATTERN_OPCODES.get(s[0])
    if handler is None:  # $ff: no operation
        track.pos += 1
        return True
    return handler(module, track, s)


def PatternEnd(module: Module, track: Track, s: Statement) -> bool:
    """$f0. Every track moves to the next position."""
    track.pattern = 0xFF
    if module.position == module.score.last:
        module.position = module.score.first  # the song ends and loops
    else:
        module.position += 1
    NewPosition(module)
    module.new_position = True
    return False


def PatternLoop(module: Module, track: Track, s: Statement) -> bool:
    """$f1. Byte 1 repeats; word: the step to jump to."""
    if track.loop_count == 0:
        track.loop_count = s[1]
        track.pos = word(s)
        return True
    track.loop_count -= 1
    track.pos = word(s) if track.loop_count else track.pos + 1
    return True


def PatternGoto(module: Module, track: Track, s: Statement) -> bool:
    """$f2. Byte 1: pattern; word: step."""
    track.pattern = s[1]
    track.statements = module.score.patterns[s[1]]
    track.pos = word(s)
    return True


def PatternWait(module: Module, track: Track, s: Statement) -> bool:
    """$f3. Byte 1: rows to wait."""
    track.wait = s[1]
    track.pos += 1
    return False


def PatternStop(module: Module, track: Track, s: Statement) -> bool:
    """$f4. The track reads nothing until the next position."""
    track.pattern = 0xFF
    return False


def EndCustomPattern(module: Module, track: Track, s: Statement) -> bool:
    """$fe. Positions set track 7 again."""
    module.custom = False
    return PatternStop(module, track, s)


def PatternNoteOff(module: Module, track: Track, s: Statement) -> bool:
    """$f5. Byte 1 gets the transpose, like a note; the voice's key goes up."""
    changed = bytes([s[0], (s[1] + track.transpose) & 0xFF, s[2], s[3]])
    return PatternToVoice(module, track, changed)


def PatternToVoice(module: Module, track: Track, s: Statement) -> bool:
    """$f5 note-off, $f6 vibrato, $f7 envelope, $fc sound effect lock."""
    if not module.score.mutes[module.tracks.index(track)]:
        NoteToVoice(module, s)
    track.pos += 1
    return True


def PatternCall(module: Module, track: Track, s: Statement) -> bool:
    """$f8. Saves the return on this track."""
    track.returns = (track.statements, track.pos)
    return PatternGoto(module, track, s)


def PatternReturn(module: Module, track: Track, s: Statement) -> bool:
    """$f9. Reads the return of track 0, not of this track, and writes it
    to track 0. So a call returns only on track 0."""
    first = module.tracks[0]
    assert first.returns is not None
    first.statements, first.pos = first.returns
    track.pos += 1
    return True


def PatternFade(module: Module, track: Track, s: Statement) -> bool:
    """$fa. Byte 1: visits per step; byte 3: target level."""
    start_fade(module.fade, s[1], s[3])
    track.pos += 1
    return True


def StartOtherTrack(module: Module, track: Track, s: Statement) -> bool:
    """$fb. Byte 1: pattern; byte 2: track; byte 3: its transpose."""
    other = module.tracks[s[2] & 7]
    other.pattern, other.transpose = s[1], s[3]
    other.statements = module.score.patterns[s[1] & 0x7F]
    other.pos = other.wait = other.loop_count = 0
    track.pos += 1
    return True


def PatternSendFlag(module: Module, track: Track, s: Statement) -> bool:
    """$fd. Sets a word the game reads."""
    module.flags[s[1] & 3] = word(s)
    track.pos += 1
    return True


PATTERN_OPCODES: dict[int, PatternHandler] = {
    0xF0: PatternEnd,
    0xF1: PatternLoop,
    0xF2: PatternGoto,
    0xF3: PatternWait,
    0xF4: PatternStop,
    0xF5: PatternNoteOff,
    0xF6: PatternToVoice,
    0xF7: PatternToVoice,
    0xF8: PatternCall,
    0xF9: PatternReturn,
    0xFA: PatternFade,
    0xFB: StartOtherTrack,
    0xFC: PatternToVoice,
    0xFD: PatternSendFlag,
    0xFE: EndCustomPattern,
}


def NewPosition(module: Module) -> None:
    """A position holds a word per track, or a special command."""
    while True:
        position = module.score.positions[module.position]
        if int.from_bytes(position[:2], "big") != POSITION_SPECIAL:
            SetTracks(module, position)
            return
        if not PositionSpecials(module, position):
            return


def SetTracks(module: Module, position: bytes) -> None:
    """High byte: pattern; low byte: transpose. From TRACK_HOLD on, the
    running pattern goes on with the new byte pair."""
    for number, track in enumerate(module.tracks):
        if number == TRACKS - 1 and module.custom:
            return
        track.pattern, track.transpose = position[2 * number : 2 * number + 2]
        if track.pattern < TRACK_HOLD:
            track.statements = module.score.patterns[track.pattern]
            track.pos = track.wait = track.loop_count = 0


def PositionSpecials(module: Module, position: bytes) -> bool:
    """$effe, then a command word. True: read the next position."""
    command = int.from_bytes(position[2:4], "big")
    handler = POSITION_COMMANDS.get(command, StopSong)
    return handler(module, position)


def StopSong(module: Module, position: bytes) -> bool:
    module.playing = False
    return False


def LoopSong(module: Module, position: bytes) -> bool:
    """Word 2: the position to jump to; word 3: how often, 0 forever."""
    target = int.from_bytes(position[4:6], "big")
    if module.position_loops == 0:
        module.position_loops = -1  # skipped on the first visit
        module.position += 1
        return True
    if module.position_loops < 0:
        module.position_loops = int.from_bytes(position[6:8], "big") - 1
    else:
        module.position_loops -= 1
    module.position = target
    return True


def SetSpeed(module: Module, position: bytes) -> bool:
    """Word 2: ticks per row; word 3: a new timer rate, if set."""
    module.speed = module.count = int.from_bytes(position[4:6], "big")
    module.position += 1
    return True


def FadeSong(module: Module, position: bytes) -> bool:
    module.position += 1
    start_fade(module.fade, position[5], position[7])
    return True


POSITION_COMMANDS: dict[int, Callable[[Module, bytes], bool]] = {
    0: StopSong,
    1: LoopSong,
    2: SetSpeed,
    3: FadeSong,  # set7freq falls through to the fade
    4: FadeSong,
}


# --- A note reaches a voice ---------------------------------------------


def NoteToVoice(module: Module, s: Statement) -> None:
    """The low nibble of byte 2 names the voice. A note restarts the
    voice's macro. It keeps every effect, the volume and the sample."""
    voice = module.voices[s[2] & 0x0F]
    if s[0] == 0xFC:
        voice.priority, voice.priority_ticks = s[1], s[3]
        return
    if voice.priority:
        return  # a sound effect holds the voice
    if s[0] == 0xF7:
        voice.envelope = Envelope((s[2] >> 4) + 1, (s[2] >> 4) + 1, s[1], s[3])
    elif s[0] == 0xF6:
        size = s[1] & 0xFE
        voice.vibrato = Vibrato(size, size >> 1, signed(s[3]), 0)
    elif s[0] == 0xF5:
        voice.key_down = False
    elif s[0] >= PORTAMENTO_NOTE - 1:
        PortaNote(voice, s)
    else:
        start_macro(module, voice, s)


def start_macro(module: Module, voice: Voice, s: Statement) -> None:
    voice.detune = signed(s[3])
    voice.note_volume = s[2] >> 4
    voice.last_note, voice.note = voice.note, s[0]
    macro, statements = voice.macro, module.score.macros[s[1]]
    if statements is not macro.statements:
        macro.skip_seen = False
    macro.statements, macro.running = statements, True
    macro.pos = macro.wait = macro.loop_count = macro.loop_waits = 0
    voice.effects = 0
    voice.key_down = True
    voice.channel.irq_enabled = False


def PortaNote(voice: Voice, s: Statement) -> None:
    """Byte 1: ticks per step; byte 3: rate. The target has no detune."""
    if not voice.portamento.rate:
        voice.portamento.period = voice.base_period
    voice.portamento.speed, voice.portamento.count = s[1], 1
    voice.portamento.rate = s[3]
    voice.note = s[0] & NOTE_MASK
    voice.base_period = note_period(voice.note)


def StopVoice(module: Module, number: int) -> None:
    """A position's $fe: stops the macro, IMS and riff; DMA off at once."""
    voice = module.voices[number & 0x0F]
    if voice.priority:
        return
    voice.channel.irq_enabled = False
    voice.channel.disable()
    voice.macro.running = False
    voice.ims.length = 0
    voice.riff.state = 0


def PlaySoundEffect(module: Module, number: int) -> None:
    """Called by the game. A new effect needs a priority at least as high,
    or the old lock must be over. An effect marked no-repeat does not
    restart itself."""
    effect = module.effects[number]
    voice = module.voices[effect.voice]
    priority = effect.priority & 0x7F
    if priority < voice.next_priority and voice.priority_ticks >= 0:
        return
    if (
        number == voice.last_effect
        and voice.priority_ticks >= 0
        and effect.priority & 0x80
    ):
        return
    note = bytearray(effect.note)
    note[2] = note[2] & 0xF0 | effect.voice
    voice.effect_note = bytes(note)
    voice.next_priority = priority
    voice.priority_ticks = effect.ticks
    voice.last_effect = number


def PlayCustomPattern(module: Module, pattern: int, transpose: int) -> None:
    """Called by the game: track 7 plays a pattern; positions skip it."""
    module.custom = True
    track = module.tracks[TRACKS - 1]
    track.pattern, track.transpose = pattern, transpose
    track.statements = module.score.patterns[pattern]
    track.pos = track.wait = track.loop_count = 0


# --- Macros -------------------------------------------------------------


def RunMacro(module: Module, voice: Voice) -> None:
    """Runs statements until one ends the tick: a wait, a note, a stop."""
    macro = voice.macro
    if not macro.running:
        return
    if macro.wait:
        macro.wait -= 1
        return
    MacroStep(module, voice)


def MacroStep(module: Module, voice: Voice) -> None:
    macro = voice.macro
    while True:
        s = macro.statements[macro.pos]
        handler = MACRO_OPCODES[s[0]] if s[0] < len(MACRO_OPCODES) else None
        if handler is None:
            if EndMacroTick(voice):
                return
            continue
        if not handler(module, voice, s):
            return


def EndMacroTick(voice: Voice) -> bool:
    """A wait or a note ends the tick. Once after a deferred DMA off, the
    macro reads on instead, so it can restart the sample in that tick.
    True: the tick ends."""
    macro = voice.macro
    macro.pos += 1
    if macro.no_yield:
        macro.no_yield = False
        return False
    return True


def MacroNext(module: Module, voice: Voice, s: Statement) -> bool:
    """$2a, and the common "read on"."""
    voice.macro.pos += 1
    return True


MacroHandler = Callable[[Module, Voice, Statement], bool]  # True: read on


def DmaOffAndReset(module: Module, voice: Voice, s: Statement) -> bool:
    """$00. Clears envelope, vibrato, portamento, riff and IMS, then $13."""
    voice.envelope.delay = voice.vibrato.size = voice.portamento.rate = 0
    voice.riff.state = voice.ims.length = 0
    return DmaOff(module, voice, s)


def DmaOff(module: Module, voice: Voice, s: Statement) -> bool:
    """$13. Byte 1 = 0: off at once. Else off at the next tick's start;
    this tick ends."""
    voice.macro.pos += 1
    if s[1] == 0:
        voice.channel.disable()
        return True
    voice.dma_off_next = True
    voice.macro.no_yield = True
    return False


def DmaOn(module: Module, voice: Voice, s: Statement) -> bool:
    """$01. On at the end of the tick. Byte 1 sets the effects state:
    negative pauses them, 0 skips one tick. Clears a sample-pass wait."""
    voice.channel.irq_enabled = voice.channel.irq_requested = False
    voice.effects = signed(s[1])
    voice.dma_on = True
    voice.macro.pos += 1
    return True


def SetStart(module: Module, voice: Voice, s: Statement) -> bool:
    """$02. The channel takes it at its next loop. Stops the sweep."""
    voice.sweep.left = 0
    voice.start = long(s)
    queue_region(module, voice)
    voice.macro.pos += 1
    return True


def SetLength(module: Module, voice: Voice, s: Statement) -> bool:
    """$03. In words."""
    voice.length = word(s)
    queue_region(module, voice)
    voice.macro.pos += 1
    return True


def MacroWait(module: Module, voice: Voice, s: Statement) -> bool:
    """$04. Waits `word` ticks. With byte 1 bit 0, it is a sync point
    with the riff instead: the first pass sets the trigger and reads on;
    a later pass waits until a riff byte with bit 7 clears it."""
    if s[1] & 1:
        if voice.riff.trigger:
            return False  # retried next tick
        voice.riff.trigger = True
        voice.macro.pos += 1
        return True
    voice.macro.wait = word(s)
    return not EndMacroTick(voice)


def MacroLoop(module: Module, voice: Voice, s: Statement) -> bool:
    """$05. Byte 1: repeats; word: the step to jump to."""
    macro = voice.macro
    if macro.loop_count == 0:
        macro.loop_count, macro.pos = s[1], word(s)
        return True
    macro.loop_count -= 1
    macro.pos = word(s) if macro.loop_count else macro.pos + 1
    return True


def MacroGoto(module: Module, voice: Voice, s: Statement) -> bool:
    """$06. Byte 1: macro; word: step."""
    macro = voice.macro
    macro.statements = module.score.macros[s[1] & 0x7F]
    macro.pos = word(s)
    macro.loop_count, macro.skip_seen = 0, False
    return True


def MacroStop(module: Module, voice: Voice, s: Statement) -> bool:
    """$07. The macro stops until the next note; effects run on."""
    voice.macro.running = False
    return False


def AddNote(module: Module, voice: Voice, s: Statement) -> bool:
    """$08. Byte 1 is added to the note."""
    PutNote(voice, s, voice.note)
    return not EndMacroTick(voice)


def SetNote(module: Module, voice: Voice, s: Statement) -> bool:
    """$09. Byte 1 is the note."""
    PutNote(voice, s, 0)
    return not EndMacroTick(voice)


def LastNote(module: Module, voice: Voice, s: Statement) -> bool:
    """$1f. Byte 1 is added to the voice's previous note."""
    PutNote(voice, s, voice.last_note)
    return not EndMacroTick(voice)


def PutNote(voice: Voice, s: Statement, note: int) -> None:
    """The word is a detune added to the pattern's. While portamento runs,
    the period becomes its target only."""
    n = (s[1] + note) & NOTE_MASK
    voice.base_period = detuned(note_period(n), voice.detune + signed_word(s))
    if not voice.portamento.rate:
        voice.period = voice.base_period


def ClearEffects(module: Module, voice: Voice, s: Statement) -> bool:
    """$0a. Riff, IMS, sweep, envelope, vibrato and portamento off."""
    voice.riff.state = voice.ims.length = voice.sweep.left = 0
    voice.envelope.delay = voice.vibrato.size = voice.portamento.rate = 0
    voice.macro.pos += 1
    return True


def MacroPortamento(module: Module, voice: Voice, s: Statement) -> bool:
    """$0b. Byte 1: ticks per step; word: rate. A later note sets the
    target; the glide starts from the current period."""
    if not voice.portamento.rate:
        voice.portamento.period = voice.base_period
    voice.portamento.speed, voice.portamento.count = s[1], 1
    voice.portamento.rate = word(s)
    voice.macro.pos += 1
    return True


def MacroVibrato(module: Module, voice: Voice, s: Statement) -> bool:
    """$0c. Byte 1: ticks per sweep; byte 3: rate. Without portamento, it
    resets the period to its centre."""
    voice.vibrato.size, voice.vibrato.left = s[1], s[1] >> 1
    voice.vibrato.rate = signed(s[3])
    if not voice.portamento.rate:
        voice.period = voice.base_period
        voice.vibrato.offset = 0
    voice.macro.pos += 1
    return True


def NoteVolume(module: Module, voice: Voice, s: Statement) -> bool:
    """$0d. Volume = 3 × the pattern's note volume + byte 3. With byte 2
    = $fe, it also sets the note: byte 1 added to the current one."""
    if s[2] == 0xFE:
        PutNote(voice, bytes([s[0], s[1], 0, 0]), voice.note)
    voice.volume = (3 * voice.note_volume + s[3]) & 0xFF
    voice.macro.pos += 1
    return True


def MacroVolume(module: Module, voice: Voice, s: Statement) -> bool:
    """$0e. Volume = byte 3. Byte 2 = $fe sets the note too, as in $0d."""
    if s[2] == 0xFE:
        PutNote(voice, bytes([s[0], s[1], 0, 0]), voice.note)
    voice.volume = s[3]
    voice.macro.pos += 1
    return True


def MacroEnvelope(module: Module, voice: Voice, s: Statement) -> bool:
    """$0f. Byte 1: step; byte 2: ticks between steps, 0 off; byte 3:
    target. It stops at the target: a phase per opcode."""
    voice.envelope = Envelope(s[2], s[2], s[1], s[3])
    voice.macro.pos += 1
    return True


def LoopWhileKey(module: Module, voice: Voice, s: Statement) -> bool:
    """$10. Loops like $05 while the key is down."""
    if not voice.key_down:
        voice.macro.pos += 1
        return True
    return MacroLoop(module, voice, s)


def AddStart(module: Module, voice: Voice, s: Statement) -> bool:
    """$11. Word: signed bytes added to the start. Byte 1 > 0 repeats the
    add every tick, and the direction flips every byte-1 ticks."""
    voice.sweep = Sweep(s[1], s[1], signed_word(s))
    voice.start += voice.sweep.step
    if voice.ims.length:
        voice.ims.source = voice.start
    else:
        queue_region(module, voice)
    voice.macro.pos += 1
    return True


def AddLength(module: Module, voice: Voice, s: Statement) -> bool:
    """$12. With IMS on, it sets the source mask instead."""
    voice.length = (voice.length + word(s)) & 0xFFFF
    if voice.ims.length:
        voice.ims.mask = voice.length
    else:
        queue_region(module, voice)
    voice.macro.pos += 1
    return True


def WaitNoteOff(module: Module, voice: Voice, s: Statement) -> bool:
    """$14. Waits while the key is down, at most byte-3 ticks; 0 has no
    limit. Effects run on."""
    macro = voice.macro
    if not voice.key_down:
        macro.pos += 1
        return True
    if macro.loop_count == 0:
        macro.loop_count = s[3]
        return False
    macro.loop_count -= 1
    if macro.loop_count == 0:
        macro.pos += 1
        return True
    return False


def MacroCall(module: Module, voice: Voice, s: Statement) -> bool:
    """$15. One return slot."""
    voice.macro.returns = (voice.macro.statements, voice.macro.pos)
    return MacroGoto(module, voice, s)


def MacroReturn(module: Module, voice: Voice, s: Statement) -> bool:
    """$16."""
    assert voice.macro.returns is not None
    voice.macro.statements, voice.macro.pos = voice.macro.returns
    voice.macro.pos += 1
    return True


def SetPeriod(module: Module, voice: Voice, s: Statement) -> bool:
    """$17. The word is the period."""
    voice.base_period = word(s)
    if not voice.portamento.rate:
        voice.period = voice.base_period
    voice.macro.pos += 1
    return True


def SampleLoop(module: Module, voice: Voice, s: Statement) -> bool:
    """$18. Moves the start on by `long` bytes and shortens the length to
    match. The channel takes it after this pass: an attack, then a loop."""
    voice.start += long(s)
    voice.length -= long(s) // 2
    queue_region(module, voice)
    voice.macro.pos += 1
    return True


def SetSilence(module: Module, voice: Voice, s: Statement) -> bool:
    """$19. One word at the sample file's start, cleared at init."""
    voice.sweep.left = 0
    voice.start, voice.length = 0, 1
    queue_region(module, voice)
    voice.macro.pos += 1
    return True


def WaitLoops(module: Module, voice: Voice, s: Statement) -> bool:
    """$1a. Stops the macro; the channel interrupt restarts it after
    word + 1 sample passes."""
    voice.macro.loop_waits = word(s)
    voice.macro.running = False
    voice.channel.on_irq(lambda channel: CountLoopIrq(voice))
    return not EndMacroTick(voice)


def CountLoopIrq(voice: Voice) -> None:
    """The audio interrupt: one sample pass."""
    voice.macro.loop_waits -= 1
    if voice.macro.loop_waits < 0:
        voice.macro.running = True
        voice.channel.irq_enabled = False


def StartRiff(module: Module, voice: Voice, s: Statement) -> bool:
    """$1b. Byte 1: the macro whose bytes are the riff; byte 2: ticks per
    step; byte 3: flags. The first step plays at once. RiffTick's exit is
    the fade code, so the fade counter moves once more."""
    voice.riff = Riff(
        state=1,
        macro=s[1],
        speed=s[2],
        count=1,
        random=bool(s[3] & 1),
        echo=bool(s[3] & 2),
        no_rests=bool(s[3] & 4),
        mask=voice.riff.mask,
    )
    RiffTick(module, voice)
    FadeTick(module, voice)
    voice.riff.trigger = True
    voice.macro.pos += 1
    return True


def SplitByNote(module: Module, voice: Voice, s: Statement) -> bool:
    """$1c. Jumps to step `word` if the note is above byte 1."""
    voice.macro.pos = word(s) if voice.note > s[1] else voice.macro.pos + 1
    return True


def SplitByVolume(module: Module, voice: Voice, s: Statement) -> bool:
    """$1d. Jumps to step `word` if the volume is above byte 1."""
    voice.macro.pos = word(s) if voice.volume > s[1] else voice.macro.pos + 1
    return True


def RiffMask(module: Module, voice: Voice, s: Statement) -> bool:
    """$1e. Random riff steps are masked with byte 1."""
    voice.riff.mask = s[1]
    voice.macro.pos += 1
    return True


def SendFlag(module: Module, voice: Voice, s: Statement) -> bool:
    """$20. Sets a word the game reads."""
    module.flags[s[1] & 3] = word(s)
    voice.macro.pos += 1
    return True


def PlayOtherVoice(module: Module, voice: Voice, s: Statement) -> bool:
    """$21. Plays this voice's note on the voice in byte 2. Byte 1: macro;
    byte 3: detune. This voice's note volume is ORed into byte 2."""
    note = bytes([voice.note, s[1], s[2] | voice.note_volume << 4, s[3]])
    NoteToVoice(module, note)
    voice.macro.pos += 1
    return True


def ImsSource(module: Module, voice: Voice, s: Statement) -> bool:
    """$22. Bytes 1-3: the source offset. The channel plays the voice's
    buffer from now on. Stops the sweep."""
    voice.sweep.left = 0
    voice.ims.source = voice.start = long(s)
    queue_ims(module, voice, 2 * voice.channel.length)
    voice.macro.pos += 1
    return True


def ImsLength(module: Module, voice: Voice, s: Statement) -> bool:
    """$23. Byte 1: bytes to build, 0 for 256; this is the loop that
    Paula plays. Word: the source mask."""
    size = s[1] or IMS_BUFFER
    queue_ims(module, voice, size)
    voice.ims.length = (size - 1) & 0xFF
    voice.ims.mask = voice.length = word(s)
    voice.macro.pos += 1
    return True


def ImsSetStep(module: Module, voice: Voice, s: Statement) -> bool:
    """$24. Bytes 1-3: source bytes per output byte, in 16.8 bits."""
    voice.ims.step = long(s) << 8
    voice.macro.pos += 1
    return True


def ImsSweepStep(module: Module, voice: Voice, s: Statement) -> bool:
    """$25. Word: added to the step each tick; byte 1: ticks per turn."""
    voice.ims.step_swing = Swing(signed_word(s), s[1], s[1])
    voice.macro.pos += 1
    return True


def ImsSetStepChange(module: Module, voice: Voice, s: Statement) -> bool:
    """$26. Bytes 1-3: added to the step per byte, in 16.16 bits. The
    wave's pitch then bends within one buffer."""
    voice.ims.step_change = long(s)
    voice.macro.pos += 1
    return True


def ImsSweepStepChange(module: Module, voice: Voice, s: Statement) -> bool:
    """$27. Like $25, for the step change."""
    voice.ims.change_swing = Swing(signed_word(s), s[1], s[1])
    voice.macro.pos += 1
    return True


def ImsFilter(module: Module, voice: Voice, s: Statement) -> bool:
    """$28. Byte 3: the largest change between output bytes, 0 off.
    Byte 2: its change per tick, in 1/16. Byte 1: ticks per turn."""
    voice.ims.delta = s[3] << 8
    voice.ims.delta_swing = Swing(signed(s[2]) << 4, s[1], s[1])
    voice.macro.pos += 1
    return True


def ImsOff(module: Module, voice: Voice, s: Statement) -> bool:
    """$29. Byte 1 > 0 also clears the steps, swings and filter; byte 3
    then sets the mirror."""
    ims = voice.ims
    ims.length = 0
    if s[1]:
        ims.step = ims.step_change = ims.delta = 0
        ims.step_swing, ims.change_swing, ims.delta_swing = Swing(), Swing(), Swing()
        ims.mirror = bool(s[3])
    voice.macro.pos += 1
    return True


def CheckByteTrap(module: Module, voice: Voice, s: Statement) -> bool:
    """$2b. If a low-memory byte is not byte 1, it writes a random byte to
    low memory (guess: against cracked copies)."""
    voice.macro.pos += 1
    return True  # memory writes are not modelled


def SetByte(module: Module, voice: Voice, s: Statement) -> bool:
    """$2c. Writes byte 1 to $80000 + signed word, in 512 KB."""
    voice.macro.pos += 1
    return True


def CheckByte(module: Module, voice: Voice, s: Statement) -> bool:
    """$2d. Skips the next statement if that byte equals byte 1."""
    voice.macro.pos += 1
    return True  # the memory read is not modelled


def WriteChipReg(module: Module, voice: Voice, s: Statement) -> bool:
    """$2e. Writes the word to the custom chip register at byte 1 × 2."""
    voice.macro.pos += 1
    return True


def CopyToMacro(module: Module, voice: Voice, s: Statement) -> bool:
    """$2f. Copies the next statement into macro byte 1 at step `word`,
    then skips it. Every voice that plays that macro sees the change."""
    macro = voice.macro
    target = module.score.macros[s[1] & 0x7F]
    target[word(s)] = macro.statements[macro.pos + 1]
    macro.pos += 2
    return True


def SkipFirstPass(module: Module, voice: Voice, s: Statement) -> bool:
    """$30. Reads on the first time; later jumps to step `word`. A note
    that starts the same macro again keeps this state."""
    macro = voice.macro
    if not macro.skip_seen:
        macro.skip_seen = True
        macro.pos += 1
    else:
        macro.pos = word(s)
    return True


def NoteOffOtherVoice(module: Module, voice: Voice, s: Statement) -> bool:
    """$31. The key goes up on the voice in byte 2."""
    NoteToVoice(module, bytes([0xF5, s[1], s[2], s[3]]))
    voice.macro.pos += 1
    return True


def AddToMacro(module: Module, voice: Voice, s: Statement) -> bool:
    """$32. Adds the word to the macro word byte-1 words from here."""
    edit_macro(voice, s[1], lambda old: (old + word(s)) & 0xFFFF)
    voice.macro.pos += 1
    return True


def AndToMacro(module: Module, voice: Voice, s: Statement) -> bool:
    """$33. ANDs the word into it."""
    edit_macro(voice, s[1], lambda old: old & word(s))
    voice.macro.pos += 1
    return True


MACRO_OPCODES: list[MacroHandler | None] = [
    DmaOffAndReset,  # $00
    DmaOn,
    SetStart,
    SetLength,
    MacroWait,  # $04
    MacroLoop,
    MacroGoto,
    MacroStop,
    AddNote,  # $08
    SetNote,
    ClearEffects,
    MacroPortamento,
    MacroVibrato,  # $0c
    NoteVolume,
    MacroVolume,
    MacroEnvelope,
    LoopWhileKey,  # $10
    AddStart,
    AddLength,
    DmaOff,
    WaitNoteOff,  # $14
    MacroCall,
    MacroReturn,
    SetPeriod,
    SampleLoop,  # $18
    SetSilence,
    WaitLoops,
    StartRiff,
    SplitByNote,  # $1c
    SplitByVolume,
    RiffMask,
    LastNote,
    SendFlag,  # $20
    PlayOtherVoice,
    ImsSource,
    ImsLength,
    ImsSetStep,  # $24
    ImsSweepStep,
    ImsSetStepChange,
    ImsSweepStepChange,
    ImsFilter,  # $28
    ImsOff,
    MacroNext,
    CheckByteTrap,
    SetByte,  # $2c
    CheckByte,
    WriteChipReg,
    CopyToMacro,
    SkipFirstPass,  # $30
    NoteOffOtherVoice,
    AddToMacro,
    AndToMacro,
]  # MacroOpcodes; from $34 on, EndMacroTick


# --- Effects, every tick ------------------------------------------------


def ModulationTick(module: Module, voice: Voice) -> None:
    """Runs even while the macro waits or has stopped. After a note or a
    $01 with byte 1 = 0, the effects skip one tick. Fade runs always."""
    if voice.effects == 0:
        voice.effects = 1
    elif voice.effects > 0:
        SweepTick(module, voice)
        ImsTick(module, voice)
        VibratoTick(voice)
        PortamentoTick(voice)
        EnvelopeTick(voice)
        RiffTick(module, voice)
    FadeTick(module, voice)


def SweepTick(module: Module, voice: Voice) -> None:
    """The start moves every tick; with IMS on, the source moves."""
    sweep = voice.sweep
    if not sweep.left:
        return
    voice.start += sweep.step
    if voice.ims.length:
        voice.ims.source = voice.start
    else:
        queue_region(module, voice)
    sweep.left -= 1
    if sweep.left == 0:
        sweep.left, sweep.step = sweep.length, -sweep.step


def ImsTick(module: Module, voice: Voice) -> None:
    """Rebuilds the voice's buffer from the source, every tick.

    The read position restarts at 0 each tick, and Paula replays the
    buffer many times per tick. So each pass restarts the source: a hard
    sync. The step sets how much of the source fits in one pass; the
    step change bends it within the pass. A delta limits how far each
    output byte moves from the last, like a slew-rate filter.
    """
    ims = voice.ims
    if not ims.length:
        return
    memory = module.score.samples
    step, position, out = ims.step, 0, ims.last
    limit = ims.delta >> 8
    for i in range(ims.length + 1):
        step = (step + ims.step_change) & 0xFFFFFFFF
        position = (position + step) & 0xFFFFFFFF
        position = position & 0xFFFF | ((position >> 16) & ims.mask) << 16
        byte = signed(memory[ims.source + (position >> 16)])
        out = towards(out, byte, limit) if limit else byte
        memory[ims.buffer + i] = out & 0xFF
        if ims.mirror:  # voice 3's copy lands past the four buffers
            memory[ims.buffer + IMS_BUFFER + i] = -out & 0xFF
    ims.last = out
    if limit:  # a delta swept down to 0 stays off
        ims.delta = (ims.delta + ims.delta_swing.tick()) & 0xFFFF
    ims.step = (ims.step + ims.step_swing.tick()) & 0xFFFFFFFF
    ims.step_change = (ims.step_change + ims.change_swing.tick()) & 0xFFFFFFFF


def VibratoTick(voice: Voice) -> None:
    """A triangle: the offset moves by `rate` each tick, and the rate
    flips every `size` ticks. While portamento runs, it writes nothing,
    but its state moves on."""
    vibrato = voice.vibrato
    if not vibrato.size:
        return
    vibrato.offset += vibrato.rate
    period = voice.base_period
    if vibrato.offset:
        period = period * (2048 + vibrato.offset) // 2048
    if not voice.portamento.rate:
        voice.period = period
    vibrato.left -= 1
    if vibrato.left == 0:
        vibrato.left, vibrato.rate = vibrato.size, -vibrato.rate


def PortamentoTick(voice: Voice) -> None:
    """Every `speed` ticks, the period moves towards base_period by the
    factor (256 +- rate) / 256. It stops at the target."""
    glide = voice.portamento
    if not glide.rate:
        return
    glide.count -= 1
    if glide.count:
        return
    glide.count = glide.speed
    target, period = voice.base_period, glide.period
    if period > target:
        period = period * (256 - glide.rate) >> 8
        done = period <= target
    elif period < target:
        period = period * (256 + glide.rate) >> 8
        done = period >= target
    else:
        done = True
    if done:
        glide.rate, period = 0, target
    glide.period = voice.period = period & 0x7FF


def EnvelopeTick(voice: Voice) -> None:
    """Every `delay` + 1 ticks, the volume moves by `step` towards the
    target. At the target, the envelope stops."""
    envelope = voice.envelope
    if not envelope.delay:
        return
    if envelope.count:
        envelope.count -= 1
        return
    envelope.count = envelope.delay
    if envelope.target > voice.volume:
        voice.volume += envelope.step
        done = voice.volume >= envelope.target
    else:
        voice.volume -= envelope.step
        done = voice.volume < 0 or voice.volume <= envelope.target
    if done:
        voice.volume, envelope.delay = envelope.target, 0


def RiffTick(module: Module, voice: Voice) -> None:
    """Every `speed` ticks, the next byte of a macro is a note offset.

    A 0 byte ends the riff; it restarts at step 0. A byte whose note is 0
    jumps to a random step. Bit 7 of a byte releases a riff-triggered
    macro wait. While portamento runs, the riff sets only its target and
    stays on this step. With `random`, see RiffRandom. With `echo`, see
    RiffEcho.
    """
    riff = voice.riff
    if not riff.state:
        return
    if riff.state > 0:
        riff.notes = bytes(b for s in module.score.macros[riff.macro] for b in s)
        riff.step, riff.state = 0, -1
        if riff.random:
            RiffJump(module, riff)
    riff.count -= 1
    if riff.count:
        RiffEcho(voice)
        return
    riff.count = riff.speed
    while (byte := riff.notes[riff.step]) == 0:
        if riff.step == 0:
            return
        riff.step = 0
    n = (byte + voice.note) & NOTE_MASK
    if n == 0:
        RiffJump(module, riff)
        return
    period = detuned(note_period(n), voice.detune)
    if riff.random:
        RiffRandom(module, voice, byte, period)
        return
    voice.base_period = period
    if voice.portamento.rate:
        return
    voice.period = period
    if byte & 0x80:
        riff.trigger = False
    riff.step += 1


def RiffRandom(module: Module, voice: Voice, byte: int, period: int) -> None:
    """On every fourth step, a note is dropped about 1 time in 16, unless
    `no_rests`. After a byte with bit 6, the riff jumps to a random step
    about 249 times in 256. The step advances during portamento."""
    riff = voice.riff
    Randomize(module)
    rest = not riff.no_rests and riff.step % 4 == 0 and module.random & 0xFF <= 16
    if not rest:
        if byte & 0x80:
            riff.trigger = False
        voice.base_period = period
        if not voice.portamento.rate:
            voice.period = period
    riff.step += 1
    if byte & 0x40:
        Randomize(module)
        if module.random >> 8 > 6:
            RiffJump(module, riff)


def RiffJump(module: Module, riff: Riff) -> None:
    Randomize(module)
    riff.step = module.random & 0xFF & riff.mask


def RiffEcho(voice: Voice) -> None:
    """At 3/8 of a step, the next voice takes this voice's period and
    5/8 of its volume, even during its own portamento."""
    riff, other = voice.riff, voice.next
    if not riff.echo or other is None or riff.count != riff.speed * 3 // 8:
        return
    other.volume = voice.volume * 5 // 8
    if other.base_period != voice.base_period:
        other.base_period = other.period = voice.base_period


def FadeTick(module: Module, voice: Voice) -> None:
    """Runs once per voice visit, so the shared counter moves four times
    per tick. Voices in one tick can get different levels. A sound
    effect's voice and a level with bit 6 set are not scaled."""
    fade = module.fade
    if fade.step:
        fade.count -= 1
        if fade.count == 0:
            fade.count = fade.speed
            fade.level += fade.step
            if fade.level == fade.target:
                fade.step, fade.running = 0, False
    volume = voice.volume
    if voice.priority_ticks < 0 and not fade.level & FULL_VOLUME:
        volume = volume * 4 * fade.level >> 8
    voice.channel.set_volume(volume)


def start_fade(fade: Fade, speed: int, target: int) -> None:
    """A new fade waits until the running one ends. Speed 0: at once."""
    if fade.running:
        return
    fade.running, fade.target = True, target
    fade.count = fade.speed = speed
    if speed and fade.level != target:
        fade.step = 1 if fade.level < target else -1
        return
    if not speed:
        fade.level = target
    fade.step, fade.running = 0, False


def Randomize(module: Module) -> None:
    """XORs the beam position in, then adds a constant."""
    beam = 0  # VHPOSR, not modelled
    module.random = ((module.random ^ beam) + RANDOM_ADD) & 0xFFFF


# --- Helpers -----------------------------------------------------------


def signed(byte: int) -> int:
    return byte - 256 if byte >= 0x80 else byte


def detuned(period: int, detune: int) -> int:
    """(256 + detune) / 256; detune 0 leaves the period exact."""
    return period * (256 + detune) >> 8 if detune else period


TOP_OCTAVE = (214, 202, 191, 180, 170, 160, 151, 143, 135, 127, 120, 113)
PERIODS = (  # nottab: 64 notes; only four octaves differ
    *(1710, 1614, 1524, 1438, 1357, 1281, 1209, 1141, 1077, 1017, 960, 908),
    *(856, 810, 764, 720, 680, 642, 606, 571, 539, 509, 480, 454),
    *(428, 404, 381, 360, 340, 320, 303, 286, 270, 254, 240, 227),
    *TOP_OCTAVE,
    *TOP_OCTAVE,  # notes 48-63 repeat the top octave: no higher notes
    *TOP_OCTAVE[:4],
)


def note_period(note: int) -> int:
    """nottab. The top two entries, 120 and 113, are below paula.MIN_PERIOD."""
    return PERIODS[note & NOTE_MASK]


def towards(last: int, byte: int, limit: int) -> int:
    """Moves from the last output byte towards `byte` by at most `limit`.
    An overflow past a signed byte takes `byte` at once."""
    if byte > last:
        moved = last + limit
        return byte if moved > 127 or byte <= moved else moved
    if byte < last:
        moved = last - limit
        return byte if moved < -128 or byte >= moved else moved
    return byte


def queue_ims(module: Module, voice: Voice, size: int) -> None:
    """The channel plays the voice's buffer. The model's Paula copies it;
    the real one reads the buffer while ImsTick rewrites it."""
    start = voice.ims.buffer
    region = module.score.samples[start : start + size]
    voice.channel.queue(paula.Sample(bytes(region)))


def queue_region(module: Module, voice: Voice) -> None:
    """Writes AUDxLC and AUDxLEN; the channel takes them at its next loop."""
    start = voice.start
    region = module.score.samples[start : start + 2 * voice.length]
    voice.channel.queue(paula.Sample(bytes(region)))


def edit_macro(voice: Voice, words: int, change: Callable[[int], int]) -> None:
    """Edits the word `words` words after this statement's start."""
    macro = voice.macro
    at = macro.pos * 4 + words * 2
    flat = bytearray(b for s in macro.statements for b in s)
    flat[at : at + 2] = change(int.from_bytes(flat[at : at + 2], "big")).to_bytes(
        2, "big"
    )
    macro.statements[:] = [bytes(flat[i : i + 4]) for i in range(0, len(flat), 4)]
