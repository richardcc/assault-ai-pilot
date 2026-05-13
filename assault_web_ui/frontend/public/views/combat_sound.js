// =================================================
// COMBAT SOUND EFFECTS
// =================================================

let combatGunshotAudio = null;

window.playCombatGunshot = function playCombatGunshot() {
  if (!combatGunshotAudio) {
    combatGunshotAudio = new Audio(
      "/public/assets/sfx/rifle-gunshot/freesound_community-rifle-gunshot-99749.mp3"
    );
    combatGunshotAudio.volume = 0.5; // ajusta a gusto
  }

  // Reiniciar por si se reproduce seguido
  combatGunshotAudio.currentTime = 0;
  combatGunshotAudio.play().catch(() => {
    // Ignorar errores de autoplay / focus
  });
};
``