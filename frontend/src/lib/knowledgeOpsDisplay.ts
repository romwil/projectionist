import { taskDisplayName } from "./scheduledTasks.js";
import type {JsonObject, JsParam} from "../api/types";

/** Owner-facing names for internal knowledge activity codes. */
export const KNOWLEDGE_EVENT_LABELS: Record<string, any> = {
  bad_neighbor_match: "Marked not similar",
  coverage_deficit: "Missing plot knowledge found",
  metadata_demand: "More title details requested",
  unmapped_token: "Unrecognized genre/tag name",
};

export const KNOWLEDGE_GAP_LABELS: Record<string, any> = {
  embedding: "Plot similarity",
  metadata: "Title details",
  motif: "Plot patterns",
  synopsis: "Full synopsis",
  theme_keyword: "Themes from tags",
};

export function knowledgeEventDisplayName(eventType: string) {
  if (!eventType) return "Library activity";
  return KNOWLEDGE_EVENT_LABELS[eventType] || String(eventType).replaceAll("_", " ");
}

export function knowledgeGapDisplayName(gapType: JsParam) {
  if (!gapType) return "";
  return KNOWLEDGE_GAP_LABELS[gapType] || String(gapType).replaceAll("_", " ");
}

export function knowledgeTaskDisplayName(taskName: JsParam) {
  return taskDisplayName(taskName);
}
