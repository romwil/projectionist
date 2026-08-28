const MUTE_KEY = "projectionist.sync_chime_muted";

export function isSyncChimeMuted() {
  try {
    return localStorage.getItem(MUTE_KEY) === "true";
  } catch {
    return false;
  }
}

export function setSyncChimeMuted(muted) {
  try {
    localStorage.setItem(MUTE_KEY, muted ? "true" : "false");
  } catch {
    // localStorage unavailable
  }
}

export function playSyncChime() {
  if (isSyncChimeMuted()) return;
  try {
    const ctx = new AudioContext();
    const oscillator = ctx.createOscillator();
    const gain = ctx.createGain();
    oscillator.type = "sine";
    oscillator.frequency.value = 880;
    gain.gain.setValueAtTime(0.07, ctx.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.28);
    oscillator.connect(gain);
    gain.connect(ctx.destination);
    oscillator.start(ctx.currentTime);
    oscillator.stop(ctx.currentTime + 0.28);
    oscillator.onended = () => {
      ctx.close().catch(() => {});
    };
  } catch {
    // Web Audio unavailable
  }
}
