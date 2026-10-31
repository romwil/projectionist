import { useEffect, useState } from "react";
import { saveReview } from "../../api/client";
import { StarRatingPicker, formatStarsLabel } from "../ReviewPromptCard";

/**
 * UX-012/PRD-007 — ask for a rating right on the movie end card, not on
 * every pause. One tap persists via `saveReview`; an existing `user_stars`
 * pre-selects so re-rating the same movie doesn't start at zero.
 */
type EndCardRatingPromptProps = {
  detail?: {
    title?: string;
    rating_key?: string | number | null;
    plex_rating_key?: string | number | null;
    tmdb_id?: string | number | null;
    tvdb_id?: string | number | null;
    user_stars?: number | null;
  } | null;
  onSkip?: () => void;
};

export default function EndCardRatingPrompt({ detail, onSkip }: EndCardRatingPromptProps) {
  const [stars, setStars] = useState(
    Number(detail?.user_stars) > 0 ? Number(detail?.user_stars) : 0,
  );
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [plexConflict, setPlexConflict] = useState<any | null>(null);
  const [savedStars, setSavedStars] = useState<number | null>(null);

  useEffect(() => {
    setStars(Number(detail?.user_stars) > 0 ? Number(detail?.user_stars) : 0);
    setSavedStars(null);
    setError("");
    setPlexConflict(null);
  }, [detail?.rating_key, detail?.tmdb_id, detail?.user_stars]);

  async function handleSave(replacePlexRating = false) {
    if (!stars || saving) return;
    setSaving(true);
    setError("");
    try {
      await saveReview({
        stars,
        title: detail?.title,
        media_type: "movie",
        rating_key: detail?.rating_key || detail?.plex_rating_key || null,
        tmdb_id: detail?.tmdb_id || null,
        tvdb_id: detail?.tvdb_id || null,
        prompted_by: "end_card",
        replace_plex_rating: replacePlexRating,
      });
      setPlexConflict(null);
      setSavedStars(stars);
    } catch (err: any) {
      if (err?.code === "plex_rating_conflict") {
        setPlexConflict(err.conflict);
        setSaving(false);
        return;
      }
      setError(err?.message || "Could not save rating");
    } finally {
      setSaving(false);
    }
  }

  if (savedStars) {
    return (
      <p
        className="theater-end-rating-saved"
        role="status"
        data-testid="library-end-card-rating-saved"
      >
        Saved {formatStarsLabel(savedStars)}★ for {detail?.title || "this title"}.
      </p>
    );
  }

  return (
    <div className="theater-end-rating" data-testid="library-end-card-rating">
      <StarRatingPicker
        value={stars}
        onChange={setStars}
        disabled={saving}
        label={`Rate ${detail?.title || "this title"}`}
        compact
      />
      {plexConflict ? (
        <div className="review-plex-conflict" data-testid="review-plex-conflict">
          <p>Plex has {formatStarsLabel(plexConflict.plex_stars)}★ — keep or replace?</p>
          <div className="theater-resume-actions">
            <button
              type="button"
              className="title-cta title-cta-ghost"
              disabled={saving}
              onClick={() => {
                setPlexConflict(null);
                onSkip?.();
              }}
            >
              Keep Plex rating
            </button>
            <button
              type="button"
              className="title-cta title-cta-primary"
              disabled={saving}
              onClick={() => handleSave(true)}
            >
              Replace on Plex
            </button>
          </div>
        </div>
      ) : (
        <div className="theater-resume-actions">
          <button
            type="button"
            className="title-cta title-cta-primary"
            data-testid="library-end-card-rate-save"
            disabled={!stars || saving}
            onClick={() => handleSave(false)}
          >
            {saving ? "Saving…" : "Save rating"}
          </button>
          <button
            type="button"
            className="title-cta title-cta-ghost"
            data-testid="library-end-card-rate-skip"
            disabled={saving}
            onClick={onSkip}
          >
            Skip
          </button>
        </div>
      )}
      {error ? (
        <p className="status status-error" data-testid="library-end-card-rating-error">
          {error}
        </p>
      ) : null}
    </div>
  );
}
