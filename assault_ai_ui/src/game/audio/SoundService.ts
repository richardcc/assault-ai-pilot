class SoundService {
  private moveSounds: HTMLAudioElement[] = [];

  constructor() {
    this.moveSounds = [
      new Audio("/public/assets/sfx/move/stepdirt_1.wav"),
      new Audio("/public/assets/sfx/move/stepdirt_2.wav"),
      new Audio("/public/assets/sfx/move/stepdirt_3.wav"),
      new Audio("/public/assets/sfx/move/stepdirt_4.wav"),
      new Audio("/public/assets/sfx/move/stepdirt_5.wav"),
      new Audio("/public/assets/sfx/move/stepdirt_6.wav"),
      new Audio("/public/assets/sfx/move/stepdirt_7.wav"),
      new Audio("/public/assets/sfx/move/stepdirt_8.wav"),
    ];

    this.moveSounds.forEach(s => (s.volume = 0.35));
  }

  playMove() {
    const sound =
      this.moveSounds[Math.floor(Math.random() * this.moveSounds.length)];

    sound.cloneNode().play().catch(() => {});
  }
}

export const soundService = new SoundService();