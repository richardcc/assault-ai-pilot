export function setupPlaybackControls({
  playBtn,
  pauseBtn,
  nextBtn,
  prevBtn,
  onNext,
  onPrev,
  interval = 800
}) {
  let playing = false;
  let timer = null;

  playBtn.onclick = () => {
    if (!playing) {
      playing = true;
      timer = setInterval(onNext, interval);
    }
  };

  pauseBtn.onclick = () => {
    playing = false;
    if (timer) clearInterval(timer);
  };

  nextBtn.onclick = onNext;
  prevBtn.onclick = onPrev;
}
