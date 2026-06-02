"""Thin wrapper over ``mido`` for live MIDI input.

No bpy here. ``mido`` and the ``rtmidi`` backend are imported lazily so the rest
of the add-on (and the headless model build) work even before the backend wheel
is installed.
"""


def backend_available():
    """True if the python-rtmidi backend can be imported."""
    try:
        import rtmidi  # noqa: F401
        return True
    except Exception:
        return False


def list_input_ports():
    """Names of available MIDI input ports (empty list on any failure)."""
    try:
        import mido
        return list(mido.get_input_names())
    except Exception:
        return []


def find_default_port(names=None):
    """Pick the most likely piano port (P-515 / digital piano) from `names`."""
    names = list_input_ports() if names is None else names
    for needle in ("p-515", "p515", "digital piano", "usb-midi", "midi"):
        for name in names:
            if needle in name.lower():
                return name
    return names[0] if names else ""


def open_input(name):
    """Open a MIDI input port by name. Raises on failure."""
    import mido
    return mido.open_input(name)


def drain(port):
    """Drain pending messages -> list of tagged events. Non-blocking.

    ('note', note:int, pressed:bool)  note on/off (velocity 0 counts as off)
    ('sustain', on:bool)              CC64 damper pedal crossing the 64 threshold
    """
    events = []
    for msg in port.iter_pending():
        if msg.type == "note_on":
            events.append(("note", msg.note, msg.velocity > 0))
        elif msg.type == "note_off":
            events.append(("note", msg.note, False))
        elif msg.type == "control_change" and msg.control == 64:
            events.append(("sustain", msg.value >= 64))
    return events
