export function hexToCoords(hex) {
  if (typeof hex === "string" && /^[A-Z]\d+$/.test(hex)) {
    return [
      hex.charCodeAt(0) - 65,
      parseInt(hex.slice(1), 10) - 1
    ];
  }

  if (typeof hex === "string") {
    const m = hex.match(/-?\d+/g);
    if (m && m.length >= 2) {
      return [parseInt(m[0], 10), parseInt(m[1], 10)];
    }
  }

  if (Array.isArray(hex)) return hex;
  return null;
}

export function hexToLabel(hex) {
  const c = hexToCoords(hex);
  if (!c) return "?";
  return `${String.fromCharCode(65 + c[0])}${c[1] + 1}`;
}