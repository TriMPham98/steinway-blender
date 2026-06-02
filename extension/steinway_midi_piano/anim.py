"""Note -> key-rotation state machine.

Pure bpy, main thread only (bpy is not thread-safe). No MIDI imports here so it
can be exercised headlessly with synthetic events (see scripts/selftest.py).

Each key stores a normalized press value in ``current`` (0 = up, 1 = fully down)
that eases toward ``targets`` every tick; the rotation applied is
``current * press_angle`` about local +X, which tips the key's front edge down.
"""

from dataclasses import dataclass, field

import bpy  # noqa: F401  (used via objects passed in note_map)

SETTLE = 1e-3   # below this, snap to target and stop animating the key


@dataclass
class LiveState:
    note_map: dict                      # midi note -> bpy object
    targets: dict = field(default_factory=dict)
    current: dict = field(default_factory=dict)
    active: set = field(default_factory=set)


def build_note_map():
    """Map every object carrying a ``midi_note`` property by its note number."""
    out = {}
    for obj in bpy.data.objects:
        note = obj.get("midi_note")
        if note is not None:
            out[int(note)] = obj
    return out


def set_note(state, note, pressed):
    """Register a note-on (pressed=True) or note-off (pressed=False)."""
    if note not in state.note_map:
        return
    state.targets[note] = 1.0 if pressed else 0.0
    state.active.add(note)


def ease_step(state, press_angle, smoothing):
    """Advance every animating key one tick. Returns True while any key moves."""
    smoothing = min(max(smoothing, 0.01), 1.0)
    for note in list(state.active):
        obj = state.note_map.get(note)
        if obj is None:
            state.active.discard(note)
            continue
        cur = state.current.get(note, 0.0)
        tgt = state.targets.get(note, 0.0)
        cur += (tgt - cur) * smoothing
        if abs(tgt - cur) <= SETTLE:
            cur = tgt
            state.active.discard(note)
        state.current[note] = cur
        obj.rotation_euler.x = cur * press_angle
    return bool(state.active)


def reset(state):
    """Flatten every key and clear animation state (used on stop)."""
    for obj in state.note_map.values():
        obj.rotation_euler.x = 0.0
    state.targets.clear()
    state.current.clear()
    state.active.clear()
