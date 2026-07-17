import { useEffect, useState } from "react";
import { saveReview } from "../api/client";
import { StarRatingPicker, formatStarsLabel } from "./ReviewPromptCard";

export default function TitleReviewModal({ detail, open, onClose, onSaved }) {
  const [stars, setStars] = useState(0);
  const [reviewText, setReviewText] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [plexConflict, setPlexConflict] = useState(null);
  const [savedStars, setSavedStars] = useState(null);

  useEffect(() => {
    if (!open) return undefined;
    setStars(Number(detail?.user_stars) > 0 ? Number(detail.user_stars) : 0);
    setReviewText("");
    setSaving(false);
    setError("");
    setPlexConflict(null);
    setSavedStars(null);
    function onKey(event) {
      if (event.key === "Escape" && !saving) onClose?.();
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open, detail?.rating_key, detail?.tmdb_id, detail?.user_stars, onClose, saving]);

  if (!open || !detail) return null;

  async function handleSave(replacePlexRating = false) {
    if (!stars || saving) return;
    setSaving(true);
    setError("");
    try {
      const saved = await saveReview({
        stars,
        title: detail.title,
        media_type: detail.media_type === "show" ? "show" : "movie",
        rating_key: detail.rating_key || detail.plex_rating_key || null,
        tmdb_id: detail.tmdb_id || null,
        tvdb_id: detail.tvdb_id || null,
        review_text: reviewText.trim(),
        prompted_by: "title_detail",
        replace_plex_rating: replacePlexRating,
      });
      setPlexConflict(null);
      setSavedStars(stars);
      setSaving(false);
      onSaved?.(saved || { stars, review_text: reviewText.trim() });
    } catch (err) {
      if (err?.code === "plex_rating_conflict") {
        setPlexConflict(err.conflict);
        setSaving(false);
        return;
      }
      setError(err?.message || "Could not save review");
      setSaving(false);
    }
  }

  return (
    <div
      className="recommend-modal-backdrop"
      data-testid="title-review-modal"
      onClick={() => {
        if (!saving) onClose?.();
      }}
    >
      <div
        className="recommend-modal title-review-modal"
        role="dialog"
        aria-modal="true"
        aria-label={`Review ${detail.title}`}
        onClick={(event) => event.stopPropagation()}
      >
        <header className="recommend-modal-header">
          <div>
            <p className="eyebrow">Leave a review</p>
            <h2>
              {detail.title}
              {detail.year ? ` (${detail.year})` : ""}
            </h2>
          </div>
          <button
            type="button"
            className="ghost"
            onClick={() => onClose?.()}
            disabled={saving}
            data-testid="title-review-modal-close"
          >
            Close
          </button>
        </header>

        {savedStars ? (
          <p className="status" data-testid="title-review-saved">
            Saved {formatStarsLabel(savedStars)}★ for {detail.title}.
          </p>
        ) : (
          <>
            <StarRatingPicker
              value={stars}
              onChange={setStars}
              disabled={saving}
              label={`Rate ${detail.title}`}
            />
            <label className="recommend-note-label">
              <span>Optional note</span>
              <textarea
                data-testid="title-review-text"
                value={reviewText}
                maxLength={2000}
                rows={3}
                placeholder="What landed or missed?"
                disabled={saving}
                onChange={(event) => setReviewText(event.target.value)}
              />
            </label>
            {plexConflict ? (
              <div className="review-plex-conflict" data-testid="review-plex-conflict">
                <p>
                  Plex has {formatStarsLabel(plexConflict.plex_stars)}★ — keep or replace?
                </p>
                <div className="recommend-modal-actions">
                  <button
                    type="button"
                    className="ghost"
                    disabled={saving}
                    onClick={() => setPlexConflict(null)}
                  >
                    Keep Plex rating
                  </button>
                  <button
                    type="button"
                    className="primary"
                    disabled={saving}
                    data-testid="title-review-replace-plex"
                    onClick={() => handleSave(true)}
                  >
                    Replace on Plex
                  </button>
                </div>
              </div>
            ) : null}
            {error ? (
              <p className="status status-error" data-testid="title-review-error">
                {error}
              </p>
            ) : null}
            {!plexConflict ? (
              <div className="recommend-modal-actions">
                <button type="button" className="ghost" disabled={saving} onClick={() => onClose?.()}>
                  Cancel
                </button>
                <button
                  type="button"
                  className="primary"
                  data-testid="title-review-save"
                  disabled={!stars || saving}
                  onClick={() => handleSave(false)}
                >
                  {saving ? "Saving…" : "Save review"}
                </button>
              </div>
            ) : null}
          </>
        )}
      </div>
    </div>
  );
}
