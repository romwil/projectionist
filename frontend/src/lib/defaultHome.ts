/**
 * BD-5: the user's landing page after sign-in / at "/".
 *
 * Chat stays the product default. When no language model is configured,
 * an unset preference resolves to Explore instead — chat without a model
 * has nothing useful to say, so Explore (which explains the missing
 * provider, see exploreHonesty.ts) is the honest landing spot.
 *
 * A user who explicitly picked "chat" or "explore" always gets that choice,
 * independent of whether an LLM is configured.
 */

import { ROUTES } from "./backNav.js";

export type DefaultPagePreference = "auto" | "chat" | "explore";

export function resolveDefaultHome({
  defaultPage,
  llmConfigured,
}: {
  defaultPage?: string | null;
  llmConfigured?: boolean;
} = {}): string {
  const pref = String(defaultPage || "auto").trim().toLowerCase();
  if (pref === "chat") return ROUTES.chat;
  if (pref === "explore") return ROUTES.explore;
  // "auto" (unset): chat is the default, unless there is no LLM to chat with.
  return llmConfigured === false ? ROUTES.explore : ROUTES.chat;
}
