// =================================================
// REPLAY LOADER (minimal, replay-only)
// =================================================

window.loadReplay = async function loadReplay(replayId) {
  const url = `/public/replays/${replayId}.json`;

  try {
    const response = await fetch(url);
    if (!response.ok) {
      throw new Error(`Failed to load replay: ${replayId}`);
    }

    const replayData = await response.json();
    return replayData;
  } catch (err) {
    console.error("Replay loading error:", err);
    throw err;
  }
};