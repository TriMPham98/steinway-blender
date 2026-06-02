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
    """Drain all pending messages -> list of (note:int, pressed:bool). Non-blocking."""
    events = []
    for msg in port.iter_pending():
        if msg.type == "note_on":
            events.append((msg.note, msg.velocity > 0))   # velocity 0 == note off
        elif msg.type == "note_off":
            events.append((msg.note, False))
    return events
