import { useState } from "react";
import { saveReview } from "../api/client";

type ReviewFields = {
  plex_stars?: number;
  stars?: number;
  title?: string;
  media_type?: string;
  rating_key?: string | number;
  tmdb_id?: string | number;
  tvdb_id?: string | number;
  review_text?: string;
};

type ReviewConflictPayload = {
  review?: ReviewFields;
  plex_stars?: number;
  submitted_stars?: number;
};

type ReviewConflictBannerProps = {
  payload?: ReviewConflictPayload | null;
  sessionId?: string;
  onResolved?: (action: "keep" | "replace", payload?: ReviewConflictPayload | null) => void | Promise<void>;
  disabled?: boolean;
};

function errorMessage(err: unknown) {
  return err instanceof Error ? (err as { message?: string }).message : "message" in (err as object) ? String((err as { message: unknown }).message) : String(err);
}

export default function ReviewConflictBanner({
  payload,
  sessionId,
  onResolved,
  disabled = false,
}: ReviewConflictBannerProps) {
  const review = payload?.review || {};
  const plexStars = payload?.plex_stars ?? review.plex_stars;
  const submittedStars = payload?.submitted_stars ?? review.stars;
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [resolved, setResolved] = useState(false);

  if (resolved || plexStars == null) return null;

  async function handleKeep() {
    setResolved(true);
    await onResolved?.("keep", payload);
  }

  async function handleReplace() {
    if (saving || disabled) return;
    setSaving(true);
    setError("");
    try {
      await saveReview({
        stars: submittedStars,
        title: review.title,
        media_type: review.media_type,
        rating_key: review.rating_key,
        tmdb_id: review.tmdb_id,
        tvdb_id: review.tvdb_id,
        review_text: review.review_text,
        session_id: sessionId,
        replace_plex_rating: true,
      });
      setResolved(true);
      await onResolved?.("replace", payload);
    } catch (err: any) {
      setError(errorMessage(err) || "Could not replace Plex rating");
    } finally {
      setSaving(false);
    }
  }

  const titleSuffix = review.title ? ` (${review.title})` : "";

  return (
    <div className="review-plex-conflict" data-testid="review-plex-conflict">
      <p>
        Plex has {plexStars}★{titleSuffix} — keep or replace?
      </p>
      {error ? <p className="review-prompt-error">{error}</p> : null}
      <div className="review-prompt-actions">
        <button
          type="button"
          className="ghost"
          data-testid="review-keep-plex-rating"
          disabled={saving || disabled}
          onClick={handleKeep}
        >
          Keep Plex rating
        </button>
        <button
          type="button"
          className="primary"
          data-testid="review-replace-plex-rating"
          disabled={saving || disabled}
          onClick={handleReplace}
        >
          {saving ? "Replacing…" : "Replace on Plex"}
        </button>
      </div>
    </div>
  );
}

export function plexRatingConflictBlock(conflict: ReviewConflictPayload) {
  return {
    type: "plex_rating_conflict",
    content: "",
    payload: conflict,
  };
}
