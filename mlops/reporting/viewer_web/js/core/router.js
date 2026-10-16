export function queryParam(name, fallback = "") {
  const q = new URLSearchParams(window.location.search);
  return q.get(name) || fallback;
}
