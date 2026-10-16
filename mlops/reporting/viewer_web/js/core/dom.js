export function el(id) {
  return document.getElementById(id);
}

export function esc(v) {
  return String((v === undefined || v === null) ? "" : v).replace(/[&<>\"']/g, (c) => (
    { "&": "&amp;", "<": "&lt;", ">": "&gt;", "\"": "&quot;", "'": "&#39;" }[c]
  ));
}

export function fmtDate(iso) {
  const s = String(iso || "");
  if (!s) return "";
  const d = new Date(s);
  return Number.isNaN(d.getTime()) ? s : d.toLocaleString();
}
