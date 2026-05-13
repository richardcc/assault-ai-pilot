// =================================================
// COMBAT DICE ANIMATOR (SAFE & DETERMINISTIC)
// - No sprite swapping
// - No dataset assumptions
// - CSS-only animation
// =================================================

window.animateCombatDice = function animateCombatDice(
  container,
  finalDice = [],
  duration = 600
) {
  if (!container) return;

  const diceImgs = Array.from(container.querySelectorAll(".combat-die"));
  if (!diceImgs.length) return;

  // Start roll animation
  diceImgs.forEach(img => {
    img.classList.remove("hit", "critical");
    img.classList.add("rolling");
  });

  // Stop roll after duration
  setTimeout(() => {
    diceImgs.forEach((img, i) => {
      img.classList.remove("rolling");

      const die = finalDice[i];
      if (!die || !die.faces) return;

      const faces = die.faces.join("+");

      if (faces.includes("CRITICAL")) {
        img.classList.add("critical");
      } else if (faces.includes("DAMAGE")) {
        img.classList.add("hit");
      }
    });
  }, duration);
};