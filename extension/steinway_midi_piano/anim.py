"""Note -> key-rotation state machine (velocity-driven spring-damper).

Pure bpy, main thread only (bpy is not thread-safe). No MIDI imports here so it
can be exercised headlessly with synthetic events (see scripts/selftest.py).

Each key is a damped spring driven toward 0 (up) or 1 (down, at the key bed). A
note-on injects a downward velocity scaled by how hard it was struck, so hard
notes snap down fast and soft notes ease in -- but every note still travels the
full ``press_angle`` (speed-only dynamics). The applied rotation is
``pos * press_angle`` about local +X (tips the key's front edge down); a hard
clamp at ``pos == 1`` gives a crisp key-bed bottom-out.
"""

import math
from dataclasses import dataclass, field

import bpy  # noqa: F401  (used via objects passed in note_map)

SETTLE = 1e-3        # snap + stop animating once pos error and |vel| are below this
PEDAL_ANGLE = math.radians(5.0)   # how far the sustain pedal tips when pressed
_SUBSTEP = 0.005     # fixed integrator sub-step (s) -- keeps the spring stable
_MAX_DT = 0.05       # clamp frame dt so a hitch can't blow the integrator up
_RELEASE_DAMP = 0.8  # release damping as a fraction of critical (<1 = snappier)


@dataclass
class Feel:
    """Tunable key/pedal motion parameters (see :func:`feel_from_props`).

    The attack is intentionally light-damped so the strike velocity *carries* the
    key down (hard = fast, soft = slow); the release uses a stiffer, lightly
    under-damped spring for a snappy return to rest.
    """
    stiffness: float = 240.0          # attack spring pull (strike velocity carries it)
    press_damping: float = 6.0        # low: keeps the descent velocity-driven
    release_stiffness: float = 2500.0 # stiffer return -> snappy key release
    velocity_gain: float = 30.0       # downward kick (1/s) at a full-velocity strike
    gamma: float = 0.6                # perceptual curve on MIDI velocity: (v/127)**gamma
    pedal_rate: float = 12.0          # sustain-pedal ease rate (1/s)


DEFAULT_FEEL = Feel()


def feel_from_props(props):
    """Map the panel knobs onto a :class:`Feel`.

    ``snappiness`` scales spring stiffness (faster descent + return);
    ``velocity_sensitivity`` scales the strike kick (dynamic range).
    """
    snap = max(getattr(props, "snappiness", 1.0), 0.05)
    sens = getattr(props, "velocity_sensitivity", 1.0)
    return Feel(
        stiffness=DEFAULT_FEEL.stiffness * snap,
        press_damping=DEFAULT_FEEL.press_damping,
        release_stiffness=DEFAULT_FEEL.release_stiffness * snap,
        velocity_gain=DEFAULT_FEEL.velocity_gain * sens,
        gamma=DEFAULT_FEEL.gamma,
        pedal_rate=DEFAULT_FEEL.pedal_rate,
    )


@dataclass
class LiveState:
    note_map: dict                                   # midi note -> bpy object
    feel: Feel = field(default_factory=lambda: DEFAULT_FEEL)
    pos: dict = field(default_factory=dict)          # note -> press depth 0..1
    vel: dict = field(default_factory=dict)          # note -> depth velocity (1/s)
    target: dict = field(default_factory=dict)       # note -> 0.0 (up) or 1.0 (down)
    active: set = field(default_factory=set)         # notes still moving
    pedal_obj: object = None            # the sustain-pedal object to tilt (or None)
    pedal_target: float = 0.0
    pedal_current: float = 0.0
    pedal_active: bool = False


def find_pedal():
    """The object tagged as the sustain pedal (steinway_role), or None."""
    for obj in bpy.data.objects:
        if obj.get("steinway_role") == "sustain_pedal":
            return obj
    return None


def build_note_map():
    """Map every object carrying a ``midi_note`` property by its note number."""
    out = {}
    for obj in bpy.data.objects:
        note = obj.get("midi_note")
        if note is not None:
            out[int(note)] = obj
    return out


def _strike_speed(feel, velocity):
    """Downward kick (1/s) imparted by a note-on of the given MIDI velocity."""
    v = min(max(velocity, 0), 127) / 127.0
    return (v ** feel.gamma) * feel.velocity_gain


def set_note(state, note, velocity):
    """Note-on (velocity > 0) or note-off (velocity == 0).

    A harder strike injects a larger downward kick so the key drops faster; the
    key always travels full depth. The sustain pedal does not hold keys down
    (real damper/hammer action comes later).
    """
    if note not in state.note_map:
        return
    if velocity > 0:
        state.target[note] = 1.0
        kick = _strike_speed(state.feel, velocity)
        state.vel[note] = max(state.vel.get(note, 0.0), kick)
    else:
        state.target[note] = 0.0
    state.active.add(note)


def set_sustain(state, on):
    """Sustain pedal (CC64): tip the pedal object down (on) or up. Keys are not
    affected for now - real damper behavior is planned with the hammer action."""
    state.pedal_target = 1.0 if on else 0.0
    state.pedal_active = True


def ease_step(state, press_angle, dt):
    """Advance every animating key one frame of length ``dt`` seconds.

    Integrates a damped spring (sub-stepped for stability) toward each key's
    target, clamping hard at the key bed. Returns True while anything still moves.
    """
    feel = state.feel
    dt = min(max(dt, 0.0), _MAX_DT)
    if dt <= 0.0:
        return bool(state.active) or state.pedal_active
    n = max(1, math.ceil(dt / _SUBSTEP))
    h = dt / n
    press_k, press_c = feel.stiffness, feel.press_damping
    release_k = feel.release_stiffness
    release_c = 2.0 * math.sqrt(release_k) * _RELEASE_DAMP   # stiff + snappy return

    for note in list(state.active):
        obj = state.note_map.get(note)
        if obj is None:
            state.active.discard(note)
            continue
        pos = state.pos.get(note, 0.0)
        vel = state.vel.get(note, 0.0)
        tgt = state.target.get(note, 0.0)
        if tgt > 0.5:                       # attack: light damping, velocity carries
            k, c = press_k, press_c
        else:                               # release: stiff, snappy return to rest
            k, c = release_k, release_c
        for _ in range(n):
            vel += (k * (tgt - pos) - c * vel) * h
            pos += vel * h
            if pos >= 1.0:
                pos, vel = 1.0, min(vel, 0.0)   # crisp key-bed stop
            elif pos <= 0.0:
                pos, vel = 0.0, max(vel, 0.0)   # rest
        if abs(tgt - pos) <= SETTLE and abs(vel) <= SETTLE:
            pos, vel = tgt, 0.0
            state.active.discard(note)
        state.pos[note] = pos
        state.vel[note] = vel
        obj.rotation_euler.x = pos * press_angle

    # Sustain pedal: simple dt-aware ease (no velocity).
    if state.pedal_active and state.pedal_obj is not None:
        rate = min(max(feel.pedal_rate * dt, 0.0), 1.0)
        cur = state.pedal_current + (state.pedal_target - state.pedal_current) * rate
        if abs(state.pedal_target - cur) <= SETTLE:
            cur = state.pedal_target
            state.pedal_active = False
        state.pedal_current = cur
        state.pedal_obj.rotation_euler.x = cur * PEDAL_ANGLE

    return bool(state.active) or state.pedal_active


def reset(state):
    """Flatten every key (and the pedal) and clear animation state (used on stop)."""
    for obj in state.note_map.values():
        obj.rotation_euler.x = 0.0
    if state.pedal_obj is not None:
        state.pedal_obj.rotation_euler.x = 0.0
    state.pos.clear()
    state.vel.clear()
    state.target.clear()
    state.active.clear()
    state.pedal_target = 0.0
    state.pedal_current = 0.0
    state.pedal_active = False
