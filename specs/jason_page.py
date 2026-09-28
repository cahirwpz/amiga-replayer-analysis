"""Graftgold's replay from ViroCop AGA (1995), in the format that Jason
Page made. Jason Page_v5.s, Wanted Team's adaptation. It holds three
replays: Realms (1991), Empire Soccer 94, and ViroCop. This model reads
ViroCop's, the latest. Empire Soccer's has the same design.

Card: players/JasonPage.md. Level 2: the control flow runs. Each
CamelCase function is a new name in data/annot/JasonPage.yaml; each
CamelCase class is in its `types:`.

Each voice has its own position list and its own row length. A pattern
note does not play a sample: it asks for an instrument program. The
same request serves the game's sound effects. A table gives each program
a priority; a request below the voice's priority is dropped, notes
included.

The game steers the song. It can write a position that the song takes at
its next branch marker, save the song's place in one of four slots and
restore it later, and fade the master volume.

A program is a list of word opcodes that runs every tick. It sets the
sample, its length and the pitch, loops, and waits. It can move the
sample's loop window every tick, copy one wave over another, and morph a
wave towards another.
"""

from collections.abc import Callable
from dataclasses import dataclass, field

from hardware import paula
from hardware.amiga import DEFAULT_LATCH, Amiga

VOICES = 4
SLOTS = 4
MAX_SAMPLES = 32
WAVE_SIZE = 128  # bytes that OpCopyWave and OpMorph touch
NONE = 0xFFFF  # a word slot that is free or done
FREE = 0xFF  # a byte slot that is free
HIGHEST_NOTE = 0x54
SLIDE_TO_NOTE = 0x77  # a pattern program number: the note slides to its pitch
FIRST_TIE = 0x78  # program numbers from here: the note only sets the pitch

# Position markers: the high byte of a position word
SONG_END, LOOP, GAME_LOOP, GAME_PASS = 0xFF, 0xFE, 0xFC, 0xFD

# Pattern bytes: below FIRST_PROGRAM a row length, below REST a program
FIRST_PROGRAM, REST, CEILING, SLIDE, PATTERN_END = 0x80, 0xF9, 0xFC, 0xFE, 0xFF

# Header: word offsets from byte 2 on; each names a table or a base
SAMPLES, PROGRAM_TABLE, PROGRAM_BASE, SPEEDS, PRIORITIES = range(5)
LIST_TABLES, LIST_BASES = 5, 13  # eight each; voices use the first four
PATTERN_TABLE, PATTERN_BASE, SAMPLES_END = 21, 22, 23

# StartSong's command word
SONG_MASK = 0x0F
SAVE, RESTORE = 0x80, 0x40

# PeriodTable: notes 0 to 84
PERIODS = (
    *(0x6B0, 0x650, 0x5F4, 0x5A0, 0x54C, 0x500, 0x4B8, 0x474, 0x434, 0x3F8),
    *(0x3C0, 0x38A, 0x358, 0x328, 0x2FA, 0x2D0, 0x2A6, 0x280, 0x25C, 0x23A),
    *(0x21A, 0x1FC, 0x1E0, 0x1C5, 0x1AC, 0x194, 0x17D, 0x168, 0x153, 0x140),
    *(0x12E, 0x11D, 0x10D, 0xFE, 0xF0, 0xE2, 0xD6, 0xCA, 0xBE, 0xB4, 0xA9),
    *(0xA0, 0x97, 0x8E, 0x86, 0x7F, 0x78, 0x71, 0x6B, 0x65, 0x5F, 0x5A, 0x54),
    *(0x50, 0x4B, 0x47, 0x43, 0x3F, 0x3C, 0x38, 0x35, 0x32, 0x2F, 0x2D, 0x2A),
    *(0x28, 0x25, 0x23, 0x21, 0x1F, 0x1E, 0x1C, 0x1A, 0x19, 0x17, 0x16, 0x15),
    *(0x14, 0x12, 0x11, 0x10, 15, 15, 14),
)

# IdleProgram: volume 0, no envelope, then a loop of yields
IDLE = bytes.fromhex("000f00000013000000000000000000060000001200070000")


# --- Player state ------------------------------------------------------


@dataclass
class Voice:  # 98 bytes at VoiceTable
    channel: paula.Channel
    number: int
    program: int = 0  # 0: the pattern's program number
    code: bytes = IDLE  # 2: the running program's word stream
    pc: int = 0
    wait: int = 0  # 6: ticks
    depth: int = 0  # 8: the next loop slot
    current: int = 0  # 10: the innermost loop slot
    counts: list[int] = field(default_factory=lambda: [0] * 4)  # 12
    returns: list[int] = field(default_factory=lambda: [0] * 4)  # 20
    vibrato_length: int = 0  # 36
    vibrato_count: int = 0  # 38
    vibrato_step: int = 0  # 40
    period: int = 0  # 42
    slide: int = 0  # 44: signed step
    volume: int = 0  # 46: word; the high byte counts
    slide_target: int = 0  # 48
    pattern_ceiling: int = NONE  # 50: set by the pattern
    ceiling: int = NONE  # 52: applied by the program
    wave: int = 0  # 54: sample start, for OpMorph
    start: int = 0  # 58: loop window, bytes into sample memory
    length: int = 0  # 62: words
    offset: int = 0  # 66: bytes; 0: the channel is not written
    delay: int = 0  # 70: ticks before the requested program starts
    request: int = FREE  # 71: the requested program
    priority: int = 0  # 72
    attack: int = NONE  # 74: high byte step, low byte ticks
    decay: int = NONE  # 76
    sustain: int = NONE  # 78: ticks
    release: int = NONE  # 80: step
    level: int = 0  # 82
    position: int = 0  # 84: index into the voice's position list
    row: int = 0  # 86: index into the pattern
    transpose: int = 0  # 87
    note: int = 0  # 88
    row_count: int = 0  # 90
    row_length: int = 0  # 91: rows per note, minus 1


@dataclass
class SaveSlot:  # SaveSlots: 17 words each
    places: list[tuple[int, int, int, int, int]] = field(default_factory=list)
    song: int = NONE


@dataclass
class Module:  # ModuleBase
    amiga: Amiga
    data: bytes
    samples: bytearray  # the sample file; programs write into it
    header: list[int] = field(default_factory=list)  # 24 word offsets
    sample_pointers: list[int] = field(default_factory=list)  # SamplePointers
    lists: list[int] = field(default_factory=lambda: [0] * VOICES)  # this song's
    voices: list[Voice] = field(default_factory=list)
    song: int = NONE  # SongNumber; NONE: stopped
    speed: int = 0
    row_counter: int = 0
    game_jump: int = NONE  # GameJump: a position the game asks for
    jump_now: int = NONE  # JumpNow: game_jump, read once per row
    voice_programs: list[int] = field(default_factory=lambda: [NONE] * VOICES)
    master: int = 0  # MasterVolume
    fade_step: int = 0
    fade_target: int = 0
    slots: list[SaveSlot] = field(
        default_factory=lambda: [SaveSlot() for _ in range(SLOTS)]
    )
    audio_filter: bool = False


# --- Start -------------------------------------------------------------


def new_module(data: bytes, samples: bytearray, amiga: Amiga) -> Module:
    """DeliTracker calls Play by its own timer."""
    module = Module(amiga, data, samples)
    module.voices = [Voice(c, n) for n, c in enumerate(amiga.paula.channels)]
    InitModule(module)
    amiga.timer.on_underflow = lambda: Play(module)
    amiga.timer.set_latch(DEFAULT_LATCH)
    return module


def InitModule(module: Module) -> None:
    """The header is a list of word offsets. Each voice has its own
    table of position lists, one per song."""
    module.header = [word(module.data, 2 + 2 * n) for n in range(24)]
    FindSamples(module, module.header[SAMPLES], module.header[SAMPLES_END])
    ResetChannels(module)


def FindSamples(module: Module, first: int, end: int) -> None:
    """The table holds sample lengths; the samples follow each other."""
    count = min((end - first) // 4, MAX_SAMPLES)
    at, module.sample_pointers = 0, []
    for n in range(count):
        module.sample_pointers.append(at)
        at += long(module.data, first + 4 * n)


def StartSong(module: Module, command: int) -> None:
    """The game's song call. Bits 0-3: song. Bits 4-5: save slot. Bit 6:
    restore that slot. Bit 7: save the running song there first. Bits
    8-15: the first position. Song 0 with bit 7 only saves and stops."""
    if command & SAVE:
        SaveSong(module, command)
        module.song = NONE
        command &= SONG_MASK  # so the song starts at position 0
        if not command:
            ResetChannels(module)
            return
    elif command & RESTORE:
        song = RestoreSong(module, command)
        if song == NONE:
            return
        SetSong(module, song)
        ResetChannels(module)
        return
    SetSong(module, command)
    for voice in module.voices:
        voice.code, voice.pc = IDLE, 0
        voice.position = command >> 8
        voice.row = voice.transpose = voice.note = 0
        voice.row_count = voice.row_length = voice.priority = 0
        voice.request, voice.pattern_ceiling = FREE, NONE
    ResetChannels(module)


def SetSong(module: Module, command: int) -> None:
    """Clears the game's jump request."""
    module.game_jump = NONE
    module.song = song = command & SONG_MASK
    module.speed = header_word(module, SPEEDS, 2 * song) & 0xFF
    module.row_counter = 0
    for v in range(VOICES):
        index = header_word(module, LIST_TABLES + v, 2 * song)
        module.lists[v] = module.header[LIST_BASES + v] + index


def SaveSong(module: Module, command: int) -> None:
    """Each voice's place: position, pattern index and transpose,
    program number, row counter and row length."""
    slot = module.slots[command >> 4 & 3]
    slot.places = [
        (v.position, v.row, v.transpose, v.program, v.row_count << 8 | v.row_length)
        for v in module.voices
    ]
    slot.song = module.song


def RestoreSong(module: Module, command: int) -> int:
    """Returns the saved song. Each voice waits in the idle program for
    its next note. The replay means to clear each voice's priority and
    request here, but writes those bytes past the slot's entry instead:
    into later slots, and from slot 1 on into SamplePointers. This model
    leaves them as they are."""
    slot = module.slots[command >> 4 & 3]
    for voice, place in zip(module.voices, slot.places):
        voice.position, voice.row, voice.transpose, voice.program, rows = place
        voice.row_count, voice.row_length = rows >> 8, rows & 0xFF
        voice.code, voice.pc = IDLE, 0
    module.song = slot.song
    return slot.song


def ResetChannels(module: Module) -> None:
    for voice in module.voices:
        voice.channel.set_volume(0)
    module.audio_filter = False


def StopSong(module: Module) -> None:
    module.song = NONE
    module.fade_step = module.fade_target = module.master = 0
    module.voice_programs = [NONE] * VOICES
    for voice in module.voices:
        StartProgram(module, voice, NONE)


def FadeTo(module: Module, target: int, step: int) -> None:
    """A game entry point. The start calls it with 255 and 255: full at
    once."""
    module.fade_target, module.fade_step = target & 0xFF, step & 0xFF


def RequestProgram(module: Module, request: int, number: int) -> bool:
    """A game entry point for sound effects, and the path of every
    pattern note. Low byte: program; high byte: ticks of delay. False:
    the voice plays a program of higher priority."""
    if request & 0xFF == FREE:
        return False
    voice = module.voices[number]
    priority = header_word(module, PRIORITIES, 2 * request & 0xFF) & 0xFF
    if priority < voice.priority:
        return False
    voice.priority = priority
    voice.delay, voice.request = request >> 8 & 0xFF, request & 0xFF
    return True


# --- Tick --------------------------------------------------------------


def Play(module: Module) -> None:
    Sequencer(module)
    TickVoices(module)


def Sequencer(module: Module) -> None:
    """A row every `speed` + 1 ticks. Each voice reads when its own row
    counter runs out: its notes last `row_length` + 1 rows."""
    if module.song == NONE:
        return
    module.row_counter -= 1
    if module.row_counter >= 0:
        return
    module.row_counter = module.speed
    module.jump_now = module.game_jump
    for voice in module.voices:
        voice.row_count = (voice.row_count - 1) & 0xFF
        if voice.row_count < 0x80:
            continue
        voice.row_count = voice.row_length
        if not ReadPosition(module, voice):
            return


def ReadPosition(module: Module, voice: Voice) -> bool:
    """A position word: a pattern and a transpose, or a marker and a
    target. False: the song ended."""
    while True:
        entry = word(module.data, module.lists[voice.number] + 2 * voice.position)
        mark, voice.transpose = entry >> 8, entry & 0xFF
        if mark == SONG_END:
            module.song = NONE
            return False
        if mark == LOOP:
            voice.position = voice.transpose
            continue
        if mark == GAME_LOOP:
            BranchLoop(module, voice)
            continue
        if mark == GAME_PASS:
            BranchPass(module, voice)
            continue
        if ReadPattern(module, voice, mark):
            return True


def BranchLoop(module: Module, voice: Voice) -> None:
    """Loops to its target, or takes the game's position. Every voice
    that reaches a marker in the same row takes it."""
    if module.jump_now == NONE:
        voice.position = voice.transpose
        return
    module.game_jump = NONE
    voice.position = module.jump_now & 0xFF


def BranchPass(module: Module, voice: Voice) -> None:
    """Plays on, or takes the game's position."""
    if module.jump_now == NONE:
        voice.position += 1
        return
    module.game_jump = NONE
    voice.position = module.jump_now & 0xFF


def ReadPattern(module: Module, voice: Voice, number: int) -> bool:
    """Bytes until a note, a rest or a command. False: the pattern ended
    and the voice reads its next position."""
    data = module.data
    at = module.header[PATTERN_BASE] + header_word(module, PATTERN_TABLE, 2 * number)
    while True:
        byte = data[at + voice.row]
        if byte < 0x40:
            voice.row = (voice.row + 1 + NotePeriod(module, voice, byte, at)) & 0xFF
            return True
        if byte < FIRST_PROGRAM:
            voice.row_length = voice.row_count = byte & 0x3F
        elif byte < REST:
            voice.program = byte & 0x7F
        elif byte == PATTERN_END:
            voice.row, voice.position = 0, voice.position + 1
            return False
        elif byte == SLIDE:
            voice.slide = signed_word(word(data, at + voice.row + 1))
            voice.slide_target = NONE if voice.slide >= 0 else 0
            voice.row = (voice.row + 3) & 0xFF
            return True
        elif byte == CEILING:
            voice.pattern_ceiling = data[at + voice.row + 1] << 8
            voice.row = (voice.row + 2) & 0xFF
            return True
        else:  # REST, and the other bytes from it up
            voice.row = (voice.row + 1) & 0xFF
            return True
        voice.row = (voice.row + 1) & 0xFF


def NotePeriod(module: Module, voice: Voice, note: int, at: int) -> int:
    """A note first asks for the voice's program. If the request fails,
    the note is lost. SLIDE_TO_NOTE slides to the note instead; from
    FIRST_TIE up, a program only sets its pitch. Returns the extra bytes read."""
    requested = voice.program < SLIDE_TO_NOTE
    if requested and not RequestProgram(module, voice.program, voice.number):
        return 0
    n = (note + voice.transpose) & 0xFF
    if n < 0x80 and n >= HIGHEST_NOTE:
        n = HIGHEST_NOTE
    voice.note = n
    period = PERIODS[(2 * n & 0xFF) >> 1]
    if voice.program != SLIDE_TO_NOTE:
        voice.period = period
        return 0
    NoteSlide(module, voice, period, module.data[at + voice.row + 1])
    return 1


def NoteSlide(module: Module, voice: Voice, target: int, speed: int) -> None:
    voice.slide_target = target
    voice.slide = speed if target >= voice.period else -speed


def TickVoices(module: Module) -> None:
    """The master fade, then per voice: a pending program, the program,
    vibrato and slide, the envelope. Then all four channels."""
    master_fade(module)
    for voice in module.voices:
        PendingProgram(module, voice)
        if voice.wait:
            voice.wait -= 1
        if not voice.wait:
            RunProgram(module, voice)
        VibratoSlide(voice)
        EnvelopeTick(voice)
    for voice in module.voices:
        WriteChannel(module, voice)


def master_fade(module: Module) -> None:
    """Moves `step` per tick; at or past the target, it stops there."""
    if not module.fade_step:
        return
    value, target = module.master, module.fade_target
    if value < target:
        value += module.fade_step
        done = value >= target
    else:
        value -= module.fade_step
        done = value <= target
    if done:
        value, module.fade_step = target, 0
    module.master = value


def PendingProgram(module: Module, voice: Voice) -> None:
    """A request starts after its delay."""
    if voice.delay:
        voice.delay -= 1
        return
    if voice.request != FREE:
        StartProgram(module, voice, voice.request)


def StartProgram(module: Module, voice: Voice, number: int) -> None:
    """Stops the channel and clears the voice's effects. The game can
    read each voice's program in VoicePrograms."""
    Silence(voice)
    voice.channel.disable()
    voice.wait = voice.volume = voice.depth = voice.current = 0
    voice.vibrato_length = voice.vibrato_count = voice.vibrato_step = 0
    voice.slide = 0
    voice.request, voice.ceiling = FREE, NONE
    module.voice_programs[voice.number] = number
    if number == NONE:
        voice.priority = 0
        voice.code, voice.pc = IDLE, 0
        return
    offset = header_word(module, PROGRAM_TABLE, 2 * (number & 0xFF))
    voice.code, voice.pc = module.data, module.header[PROGRAM_BASE] + offset
    voice.offset = 0xFFFFFFFF


def RunProgram(module: Module, voice: Voice) -> None:
    """Opcodes until one yields."""
    while True:
        op = read_word(voice) & 0xFF
        if OPCODES[op](module, voice):
            return


def VibratoSlide(voice: Voice) -> None:
    """Vibrato is a triangle on the period. A slide stops at its target
    but stays on."""
    if voice.vibrato_step:
        voice.period = (voice.period + signed_word(voice.vibrato_step)) & 0xFFFF
        if voice.vibrato_count:
            voice.vibrato_count -= 1
        else:
            voice.vibrato_count = voice.vibrato_length
            voice.vibrato_step = -voice.vibrato_step & 0xFFFF
    if not voice.slide:
        return
    period = (voice.period + voice.slide) & 0xFFFF
    if voice.slide > 0:
        period = min(period, voice.slide_target)
    else:
        period = max(period, voice.slide_target)
    voice.period = period


def EnvelopeTick(voice: Voice) -> None:
    """Attack and decay add or subtract their high byte, times 256, for
    their low byte + 1 ticks. Sustain counts ticks and caps the volume
    at the ceiling. Release subtracts its word down to 0. The level sets
    the volume."""
    level = voice.level
    if voice.attack & 0xFF != FREE:
        voice.attack = voice.attack & 0xFF00 | (voice.attack - 1) & 0xFF
        level += voice.attack & 0xFF00
        if level > 0xFFFF:
            level, voice.attack = 0xFF00, NONE
    elif voice.decay & 0xFF != FREE:
        voice.decay = voice.decay & 0xFF00 | (voice.decay - 1) & 0xFF
        level -= voice.decay & 0xFF00
        if level < 0:
            level, voice.decay = 0, NONE
    elif voice.sustain != NONE:
        voice.sustain -= 1
        if voice.ceiling >= voice.volume:
            return
        level = voice.ceiling
    elif voice.release != NONE:
        level -= voice.release
        if level < 0:
            level, voice.release = 0, NONE
    else:
        return
    voice.level = voice.volume = level


def WriteChannel(module: Module, voice: Voice) -> None:
    """The volume's high byte, capped by the master volume. With a
    window, the loop's start, length and the period, every tick: the
    channel takes them at its next loop."""
    volume = min(voice.volume >> 8 & 0xFF, module.master) >> 2
    voice.channel.set_volume(volume)
    if not voice.offset:
        return
    at = (voice.start + 2 * voice.length - voice.offset) & 0xFFFFFFFF
    window = memoryview(module.samples)[at : at + 2 * voice.length]
    voice.channel.queue(paula.Sample(window))
    voice.channel.period = voice.period


def Silence(voice: Voice) -> None:
    voice.volume = voice.offset = 0
    voice.attack = voice.decay = voice.sustain = voice.release = NONE
    voice.channel.set_volume(0)


# --- Program opcodes ---------------------------------------------------
# Each returns True when the program yields for this tick.

Opcode = Callable[[Module, Voice], bool]


def OpEnd(module: Module, voice: Voice) -> bool:
    """0: frees the voice. A note of any priority may take it."""
    voice.code, voice.pc, voice.priority = IDLE, 0, 0
    OpStop(module, voice)
    module.voice_programs[voice.number] = NONE
    return True


def OpYield(module: Module, voice: Voice) -> bool:
    """1 and 18: ends this tick."""
    return True


def OpSample(module: Module, voice: Voice) -> bool:
    """2: a sample number. It is also OpMorph's wave."""
    voice.start = voice.wave = module.sample_pointers[read_word(voice)]
    return False


def OpLength(module: Module, voice: Voice) -> bool:
    """3: bytes."""
    voice.offset = read_word(voice)
    voice.length = voice.offset >> 1
    return False


def OpLengthLong(module: Module, voice: Voice) -> bool:
    """4: bytes, as a long."""
    voice.offset = read_word(voice) << 16 | read_word(voice)
    if voice.offset:
        voice.length = (voice.offset & 0xFFFF) >> 1
    return False


def OpWait(module: Module, voice: Voice) -> bool:
    """5: ticks."""
    voice.wait = read_word(voice)
    return True


def OpLoopStart(module: Module, voice: Voice) -> bool:
    """6: a count; 0 loops forever. Four slots, reused in turn."""
    voice.current = voice.depth
    voice.counts[voice.depth] = read_word(voice)
    voice.returns[voice.depth] = voice.pc
    voice.depth = (voice.depth + 1) & 3
    return False


def OpLoopEnd(module: Module, voice: Voice) -> bool:
    """7: a count of N plays the body N times. Leaving the outer slot
    does not free it."""
    n = voice.current
    if voice.counts[n]:
        voice.counts[n] -= 1
        if not voice.counts[n]:
            if n:
                voice.depth, voice.current = voice.depth - 1, n - 1
            return False
    voice.pc = voice.returns[n]
    return False


def OpMoveStart(module: Module, voice: Voice) -> bool:
    """8: a long added to the window's start."""
    voice.start += signed_long(read_word(voice) << 16 | read_word(voice))
    return False


def OpAddLength(module: Module, voice: Voice) -> bool:
    """9: bytes added to the window's length."""
    voice.length += signed_word(read_word(voice)) >> 1
    return False


def OpAddOffset(module: Module, voice: Voice) -> bool:
    """10: a long added to the window's offset. The start moves back."""
    voice.offset += signed_long(read_word(voice) << 16 | read_word(voice))
    return False


def OpAddPeriod(module: Module, voice: Voice) -> bool:
    """11."""
    voice.period = (voice.period + read_word(voice)) & 0xFFFF
    return False


def OpAddVolume(module: Module, voice: Voice) -> bool:
    """12."""
    voice.volume = (voice.volume + read_word(voice)) & 0xFFFF
    return False


def OpVibrato(module: Module, voice: Voice) -> bool:
    """13: high byte step, low byte length. It starts half-way."""
    value = read_word(voice)
    voice.vibrato_step, voice.vibrato_length = value >> 8, value & 0xFF
    voice.vibrato_count = voice.vibrato_length >> 1
    return False


def OpPeriod(module: Module, voice: Voice) -> bool:
    """14."""
    voice.period = read_word(voice)
    return False


def OpVolume(module: Module, voice: Voice) -> bool:
    """15: a word; the high byte counts."""
    voice.volume = read_word(voice)
    return False


def OpDmaOn(module: Module, voice: Voice) -> bool:
    """16: the program starts the sound itself."""
    voice.channel.enable()
    return False


def OpStop(module: Module, voice: Voice) -> bool:
    """17: silence, DMA off, and yield."""
    Silence(voice)
    voice.channel.disable()
    return True


def OpAdsr(module: Module, voice: Voice) -> bool:
    """19: attack, decay, sustain and release words. The level starts
    at 0."""
    voice.attack, voice.decay = read_word(voice), read_word(voice)
    voice.sustain, voice.release = read_word(voice), read_word(voice)
    voice.level = 0
    return False


def OpNote(module: Module, voice: Voice) -> bool:
    """20: a note number, without transpose."""
    voice.note = read_word(voice) & 0xFF
    voice.period = PERIODS[voice.note]
    return False


def OpNoteOffset(module: Module, voice: Voice) -> bool:
    """21: an offset from the last note; the note stays. Chains of these
    play an arpeggio."""
    voice.period = PERIODS[(voice.note + read_word(voice)) & 0xFFFF]
    return False


def OpCopyWave(module: Module, voice: Voice) -> bool:
    """22: two sample numbers in one word: copies 128 bytes from the
    first to the second."""
    value = read_word(voice)
    source = module.sample_pointers[value >> 8]
    target = module.sample_pointers[value & 0xFF]
    wave = module.samples[source : source + WAVE_SIZE]
    module.samples[target : target + WAVE_SIZE] = wave
    return False


def OpMorph(module: Module, voice: Voice) -> bool:
    """23: a sample number. Each of 128 bytes of the voice's wave moves
    one step towards that sample's byte. Bytes compare unsigned, so a
    byte that crosses 0 sweeps through +127 and -128."""
    goal = module.sample_pointers[read_word(voice)]
    wave = voice.wave
    for n in range(WAVE_SIZE):
        have, want = module.samples[wave + n], module.samples[goal + n]
        if have > want:
            module.samples[wave + n] = have - 1
        elif have < want:
            module.samples[wave + n] = have + 1
    return False


def OpCeiling(module: Module, voice: Voice) -> bool:
    """24: the pattern's last CEILING value caps the volume during
    sustain."""
    voice.ceiling = voice.pattern_ceiling
    return False


OPCODES: tuple[Opcode, ...] = (  # ProgramOpcodes
    OpEnd, OpYield, OpSample, OpLength, OpLengthLong, OpWait, OpLoopStart,
    OpLoopEnd, OpMoveStart, OpAddLength, OpAddOffset, OpAddPeriod,
    OpAddVolume, OpVibrato, OpPeriod, OpVolume, OpDmaOn, OpStop, OpYield,
    OpAdsr, OpNote, OpNoteOffset, OpCopyWave, OpMorph, OpCeiling,
)  # fmt: skip


# --- Helpers -----------------------------------------------------------


def read_word(voice: Voice) -> int:
    voice.pc += 2
    return word(voice.code, voice.pc - 2)


def word(data: bytes, at: int) -> int:
    return data[at] << 8 | data[at + 1]


def long(data: bytes, at: int) -> int:
    return word(data, at) << 16 | word(data, at + 2)


def header_word(module: Module, entry: int, offset: int) -> int:
    """A word of the table that header entry `entry` names."""
    return word(module.data, module.header[entry] + offset)


def signed_word(value: int) -> int:
    return value - 0x10000 if value & 0x8000 else value


def signed_long(value: int) -> int:
    return value - (1 << 32) if value & 1 << 31 else value
