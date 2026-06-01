class SoundService {
  private moveSounds: HTMLAudioElement[] = [];
  private attackSounds: HTMLAudioElement[] = [];

  constructor() {
    this.moveSounds = [
      new Audio("/assets/sfx/move/stepdirt_1.wav"),
      new Audio("/assets/sfx/move/stepdirt_2.wav"),
      new Audio("/assets/sfx/move/stepdirt_3.wav"),
      new Audio("/assets/sfx/move/stepdirt_4.wav"),
      new Audio("/assets/sfx/move/stepdirt_5.wav"),
      new Audio("/assets/sfx/move/stepdirt_6.wav"),
      new Audio("/assets/sfx/move/stepdirt_7.wav"),
      new Audio("/assets/sfx/move/stepdirt_8.wav"),
    ];

    this.attackSounds = [
      new Audio("/assets/sfx/rifle-gunshot/freesound_community-rifle-gunshot-99749.mp3"),
    ];

    this.moveSounds.forEach((s) => (s.volume = 0.35));
    this.attackSounds.forEach((s) => (s.volume = 0.45));
  }

  playMove() {
    const sound =
      this.moveSounds[Math.floor(Math.random() * this.moveSounds.length)];

    sound.cloneNode().play().catch(() => {});
  }

  playAttack() {
    const sound =
      this.attackSounds[Math.floor(Math.random() * this.attackSounds.length)];

    sound.cloneNode().play().catch(() => {});
  }
}

export const soundService = new SoundService();