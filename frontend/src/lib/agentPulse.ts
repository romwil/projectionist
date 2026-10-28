import type {JsonObject, JsParam} from "../api/types";
/**
 * Top-bar agent pulse reflects chat/LLM agent state only.
 * Library sync and other background jobs belong in StatusDock — never drive this pulse.
 */

export function resolveAgentPulse({ loading = false, chatError = "" }: JsParam = {}) {
  if (chatError) return "error";
  if (loading) return "thinking";
  return "idle";
}

export function agentPulseTitle(pulse: JsParam, chatError = "") {
  if (pulse === "error") {
    const reason = String(chatError || "").trim();
    if (reason) {
      const brief = reason.length > 120 ? `${reason.slice(0, 117)}...` : reason;
      return `Agent error: ${brief}`;
    }
    return "Agent error";
  }
  if (pulse === "thinking" || pulse === "running") return "Agent thinking";
  return "Agent idle";
}

export function projectionistBrandAriaLabel(pulse: JsParam, chatError = "") {
  return `Projectionist home — ${agentPulseTitle(pulse, chatError)}`;
}
