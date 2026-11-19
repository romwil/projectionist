/**
 * EXP-013: the user's landing page after sign-in / at "/".
 *
 * Explore is the product default home. An unset or legacy "auto" preference
 * resolves to Explore. A user who explicitly picked "chat" or "explore" always
 * gets that choice — including Chat when no language model is configured
 * (Chat then shows the missing-provider honesty note).
 */

import { ROUTES } from "./backNav.js";

export type DefaultPagePreference = "auto" | "chat" | "explore";

export function resolveDefaultHome({
  defaultPage,
}: {
  defaultPage?: string | null;
  /** @deprecated EXP-013: ignored; Explore is home regardless of LLM. Kept for call-site compatibility. */
  llmConfigured?: boolean;
} = {}): string {
  const pref = String(defaultPage || "auto").trim().toLowerCase();
  if (pref === "chat") return ROUTES.chat;
  if (pref === "explore") return ROUTES.explore;
  // "auto" (unset / legacy): Explore is the product default.
  return ROUTES.explore;
}
