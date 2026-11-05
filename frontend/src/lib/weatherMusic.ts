/**
 * Weather Channel music bed: every file in the owner's folder, shuffled.
 *
 * - No repeat until the rest have played, then reshuffle (no back-to-back repeat
 *   across the reshuffle when there is more than one file).
 * - A voiceover fades the bed to silence over ~1.5s; when it ends the next track
 *   fades in over the same span. One file fades back into itself from the start.
 * - A track that ends on its own between voiceovers crossfades to the next.
 * - No files: nothing plays. The voice still does.
 */

export const MUSIC_FADE_MS = 1_500;
export const MUSIC_BED_VOLUME = 0.35;

export type MusicTrack = { id: string; url: string; title?: string };

export type AudioLike = {
  src: string;
  volume: number;
  currentTime: number;
  duration: number;
  paused: boolean;
  play: () => Promise<void> | void;
  pause: () => void;
};

export type ShuffleBag = { order: string[]; index: number };

function shuffled(ids: string[], rng: () => number): string[] {
  const out = [...ids];
  for (let i = out.length - 1; i > 0; i -= 1) {
    const j = Math.floor(rng() * (i + 1));
    [out[i], out[j]] = [out[j], out[i]];
  }
  return out;
}

export function createShuffleBag(ids: string[], rng: () => number = Math.random): ShuffleBag {
  return { order: shuffled(ids, rng), index: 0 };
}

export function drawFromBag(
  bag: ShuffleBag,
  ids: string[],
  rng: () => number = Math.random,
): { id: string | null; bag: ShuffleBag } {
  if (!ids.length) return { id: null, bag };
  let next = bag;
  if (next.index >= next.order.length || next.order.length !== ids.length) {
    const previous = bag.order[bag.index - 1];
    let order = shuffled(ids, rng);
    if (ids.length > 1 && order[0] === previous) order = [...order.slice(1), order[0]];
    next = { order, index: 0 };
  }
  return { id: next.order[next.index], bag: { ...next, index: next.index + 1 } };
}

export function fadeVolume(from: number, to: number, elapsedMs: number, durationMs = MUSIC_FADE_MS): number {
  if (durationMs <= 0 || elapsedMs >= durationMs) return to;
  const t = Math.max(0, elapsedMs) / durationMs;
  return from + (to - from) * t;
}

type Fade = { deck: number; from: number; to: number; start: number; pauseAtEnd: boolean };

export class WeatherMusicBed {
  readonly decks: [AudioLike, AudioLike];
  readonly tracks: MusicTrack[];
  readonly history: string[] = [];
  private bag: ShuffleBag = { order: [], index: 0 };
  private active = 0;
  private fades: Fade[] = [];
  private ducked = false;
  private crossfading = false;
  private rng: () => number;
  private bedVolume: number;
  private fadeMs: number;

  constructor(opts: {
    tracks: MusicTrack[];
    createAudio: () => AudioLike;
    rng?: () => number;
    bedVolume?: number;
    fadeMs?: number;
  }) {
    this.tracks = opts.tracks.filter((t) => t && t.id && t.url);
    this.decks = [opts.createAudio(), opts.createAudio()];
    this.rng = opts.rng || Math.random;
    this.bedVolume = opts.bedVolume ?? MUSIC_BED_VOLUME;
    this.fadeMs = opts.fadeMs ?? MUSIC_FADE_MS;
    for (const deck of this.decks) deck.volume = 0;
  }

  get hasMusic(): boolean {
    return this.tracks.length > 0;
  }

  get isDucked(): boolean {
    return this.ducked;
  }

  get activeDeck(): AudioLike {
    return this.decks[this.active];
  }

  private load(deckIndex: number): string | null {
    const ids = this.tracks.map((t) => t.id);
    const drawn = drawFromBag(this.bag, ids, this.rng);
    this.bag = drawn.bag;
    const track = this.tracks.find((t) => t.id === drawn.id);
    if (!track) return null;
    const deck = this.decks[deckIndex];
    deck.src = track.url;
    deck.currentTime = 0;
    deck.volume = 0;
    this.history.push(track.id);
    const started = deck.play();
    if (started && typeof (started as Promise<void>).catch === "function") (started as Promise<void>).catch(() => {});
    return track.id;
  }

  private fade(deck: number, to: number, now: number, pauseAtEnd = false) {
    this.fades = this.fades.filter((f) => f.deck !== deck);
    this.fades.push({ deck, from: this.decks[deck].volume, to, start: now, pauseAtEnd });
  }

  start(now: number): void {
    if (!this.hasMusic || this.history.length) return;
    this.load(this.active);
    this.fade(this.active, this.bedVolume, now);
  }

  /** Voice begins: bed fades to silence, then pauses. */
  voiceStart(now: number): void {
    this.ducked = true;
    if (!this.hasMusic) return;
    this.crossfading = false;
    this.decks.forEach((deck, index) => {
      if (!deck.paused || deck.volume > 0) this.fade(index, 0, now, true);
    });
  }

  /** Voice ends: the next track (the same file when there is only one) fades in. */
  voiceEnd(now: number): void {
    this.ducked = false;
    if (!this.hasMusic) return;
    this.active = 1 - this.active;
    this.load(this.active);
    this.fade(this.active, this.bedVolume, now);
  }

  tick(now: number): void {
    const remaining: Fade[] = [];
    for (const fade of this.fades) {
      const deck = this.decks[fade.deck];
      const elapsed = now - fade.start;
      deck.volume = Math.max(0, Math.min(1, fadeVolume(fade.from, fade.to, elapsed, this.fadeMs)));
      if (elapsed >= this.fadeMs) {
        if (fade.pauseAtEnd && fade.to === 0) deck.pause();
      } else {
        remaining.push(fade);
      }
    }
    this.fades = remaining;
    if (this.crossfading && !this.fades.some((f) => f.deck !== this.active)) this.crossfading = false;
    if (!this.hasMusic || this.ducked || this.crossfading) return;
    const deck = this.decks[this.active];
    const left = Number(deck.duration) - Number(deck.currentTime);
    if (Number.isFinite(left) && deck.duration > 0 && left * 1000 <= this.fadeMs) {
      this.crossfading = true;
      const outgoing = this.active;
      this.fade(outgoing, 0, now, true);
      this.active = 1 - this.active;
      this.load(this.active);
      this.fade(this.active, this.bedVolume, now);
    }
  }

  /** The browser blocked autoplay; a tap retries the bed. */
  resume(): void {
    if (this.ducked) return;
    const deck = this.decks[this.active];
    const started = deck.play();
    if (started && typeof (started as Promise<void>).catch === "function") (started as Promise<void>).catch(() => {});
  }

  stop(): void {
    this.fades = [];
    for (const deck of this.decks) {
      deck.pause();
      deck.src = "";
    }
  }
}
