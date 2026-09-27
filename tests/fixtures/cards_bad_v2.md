---
player: MED
template: 2
ideas: [volume-list]
control: { sequencer: commands, instrument: commands }
---

# Cards fixture, template 2

## Context

| Fact   | Value |
| ------ | ----- |
| Player | stale |

## Composer's view

```python
@dataclass
class Score:
    tune: Melody
```

| Aspect   | Answer | Source |
| -------- | ------ | ------ |
| Notation | grid; rows | `:plr_loop2` |

## Key ideas

- Sections are out of order.

## Timing

| Stream   | Scope  | Carries | Control  | Advances by |
| -------- | ------ | ------- | -------- | ----------- |
| Sequence | galaxy | notes   | teleport | often       |

| Aspect | Value | Label |
| ------ | ----- | ----- |
| Time   | grid  | x     |

| Odd | Table |
| --- | ----- |
| a   | b     |

| Event     | Trigger | Changes | Keeps running | Label |
| --------- | ------- | ------ | ------------- | ----- |
| hard stop | x       | x      | x             | x     |
| release   | x       | x      | x             | x     |
| birth     | x       | x      | x             | x     |

## Sound

### Colour

| Controller | Kind  | Advances by | Owner  | Set by | Label |
| ---------- | ----- | ----------- | ------ | ------ | ----- |
| Wobble     | magic | often       | nobody | Ghost  | x     |

## Instrument

| Question | Answer |
| -------- | ------ |
| Stores   | x      |

## Interactions

```python
def on_jump(voice arg):
    pass
```

| From   | To      | Event | Destination runs |
| ------ | ------- | ----- | ---------------- |
| Wobble | nowhere | x     | someday          |

## Extra
