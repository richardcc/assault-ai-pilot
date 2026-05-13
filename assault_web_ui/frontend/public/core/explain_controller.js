document.addEventListener("click", async (e) => {
  if (e.target.id !== "explain-btn") return;

  const payload = window.lastExplainPayload;
  if (!payload) return;

  renderHRLExplanation({
    strategic_intent: {
      explanation: "Analyzing..."
    }
  });

  try {
    const res = await fetch("http://127.0.0.1:8000/api/explain/activation", {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify(payload)
    });

    if (!res.ok) {
      const text = await res.text();
      console.error(text);
      return;
    }

    const data = await res.json();

    renderHRLExplanation({
      strategic_intent: data.strategic_intent
    });

    renderTacticalExplanation({
      tactical_execution: data.tactical_execution
    });

  } catch (err) {
    console.error(err);
  }
});