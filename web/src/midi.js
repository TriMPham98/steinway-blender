/**
 * Port of extension/steinway_midi_piano/midi.py — Web MIDI API backend.
 */

const PORT_NEEDLES = ["p-515", "p515", "digital piano", "usb-midi", "midi"];

export function backendAvailable() {
  return typeof navigator !== "undefined" && !!navigator.requestMIDIAccess;
}

/** @param {MIDIAccess} access @returns {string[]} */
export function listInputPorts(access) {
  const names = [];
  for (const input of access.inputs.values()) {
    if (input.name) names.push(input.name);
  }
  return names.sort();
}

/** @param {string[]} [names] */
export function findDefaultPort(names) {
  const list = names ?? [];
  for (const needle of PORT_NEEDLES) {
    for (const name of list) {
      if (name.toLowerCase().includes(needle)) return name;
    }
  }
  return list[0] ?? "";
}

/**
 * Parse one MIDIMessage into tagged events (mirrors midi.drain).
 * @returns {Array<['note', number, number] | ['sustain', boolean]>}
 */
export function parseMidiMessage(event) {
  const data = event.data;
  if (!data || data.length < 2) return [];
  const status = data[0] & 0xf0;
  const a = data[1];
  const b = data.length > 2 ? data[2] : 0;

  if (status === 0x90) {
    return [["note", a, b]];
  }
  if (status === 0x80) {
    return [["note", a, 0]];
  }
  if (status === 0xb0 && a === 64) {
    return [["sustain", b >= 64]];
  }
  return [];
}

/** @param {MIDIAccess} access @param {string} name */
export function getInputByName(access, name) {
  for (const input of access.inputs.values()) {
    if (input.name === name) return input;
  }
  return null;
}