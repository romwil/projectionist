/** Shown when a Plex tone-map transcode would run without a hardware transcoder. */
export const PREPARE_FOR_SCREEN = "This title needs preparing for this screen";

export function offersCopy(message: string): boolean {
  return String(message || "").trim() === PREPARE_FOR_SCREEN;
}
