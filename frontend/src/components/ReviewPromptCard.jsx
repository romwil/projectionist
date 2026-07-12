import { useState } from "react";

const STAR_STEPS = [0.5, 1, 1.5, 2, 2.5, 3, 3.5, 4, 4.5, 5];

const DEFAULT_NEAR_COMPLETE_TEMPLATE =
  "{curator_name} noticed you're {pct}% through **{title}**. Quick rating while it's fresh?";

export function formatReviewPromptMessage(
  prompt,
  {
    curatorName = "Curator",
    template = DEFAULT_NEAR_COMPLETE_TEMPLATE,
    templateKey = "near_complete",
  } = {},
) {
  const pct = Math.round(prompt.completion_pct || 0);
  const resolvedTemplate = template || DEFAULT_NEAR_COMPLETE_TEMPLATE;
  return resolvedTemplate
    .replaceAll("{curator_name}", curatorName)
    .replaceAll("{title}", prompt.title || "this title")
    .replaceAll("{pct}", String(pct))
    .replaceAll("{template_key}", templateKey);
}

export function formatStarsLabel(stars) {
  const value = Number(stars);
  if (!Number.isFinite(value) || value <= 0) return "";
  return Number.isInteger(value) ? String(value) : value.toFixed(1);
}

export function StarRatingPicker({
  value,
  onChange,
  disabled = false,
  label = "Rate",
  compact = false,
}) {
  const [hover, setHover] = useState(0);
  const display = hover || value || 0;

  return (
    <div
      className={`review-star-picker ${compact ? "compact" : ""}`}
      role="group"
      aria-label={label}
      onMouseLeave={() => setHover(0)}
    >
      {STAR_STEPS.filter((step) => Number.isInteger(step)).map((full) => {
        const half = full - 0.5;
        const fill = display >= full ? "full" : display >= half ? "half" : "empty";
        return (
          <span key={full} className="review-star-unit">
            <button
              type="button"
              className="review-star-half left"
              data-testid={`review-star-${half}`}
              aria-label={`${half} stars`}
              aria-pressed={value === half}
              disabled={disabled}
              onMouseEnter={() => setHover(half)}
              onFocus={() => setHover(half)}
              onClick={() => onChange?.(half)}
            />
            <button
              type="button"
              className={`review-star-button ${fill}`}
              data-testid={`review-star-${full}`}
              aria-label={`${full} star${full === 1 ? "" : "s"}`}
              aria-pressed={value >= full}
              disabled={disabled}
              onMouseEnter={() => setHover(full)}
              onFocus={() => setHover(full)}
              onClick={() => onChange?.(full)}
            >
              ★
            </button>
          </span>
        );
      })}
      {value ? (
        <span className="review-star-value" data-testid="review-star-value">
          {formatStarsLabel(value)}★
        </span>
      ) : null}
    </div>
  );
}

export default function ReviewPromptCard({
  prompt,
  curatorName = "Curator",
  reviewPromptTemplates,
  sessionId,
  onSaved,
  onDismissed,
  disabled = false,
  compact = false,
}) {
  const [stars, setStars] = useState(0);
  const [reviewText, setReviewText] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [plexConflict, setPlexConflict] = useState(null);
  const [saved, setSaved] = useState(false);

  const lead = compact
    ? prompt.title || "Untitled"
    : formatReviewPromptMessage(prompt, {
        curatorName,
        template: reviewPromptTemplates?.near_complete,
      });

  async function handleSave(replacePlexRating = false) {
    if (!stars || saving || disabled) return;
    setSaving(true);
    setError("");
    try {
      await onSaved?.({
        prompt,
        stars,
        review_text: reviewText.trim(),
        session_id: sessionId,
        replace_plex_rating: replacePlexRating,
      });
      setPlexConflict(null);
      setSaving(false);
      setSaved(true);
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

  async function handleKeepPlexRating() {
    setPlexConflict(null);
    setSaving(false);
    if (!String(prompt.id || "").startsWith("slash-rate-") && !String(prompt.id || "").startsWith("viewed-unrated-")) {
      await onDismissed?.(prompt);
    }
  }

  async function handleReplacePlexRating() {
    await handleSave(true);
  }

  async function handleSkip() {
    if (saving || disabled) return;
    setSaving(true);
    setError("");
    setPlexConflict(null);
    try {
      await onDismissed?.(prompt);
    } catch (err) {
      setError(err?.message || "Could not dismiss prompt");
      setSaving(false);
    }
  }

  if (saved) {
    return (
      <div
        className={`review-prompt-card ${compact ? "compact" : ""} saved`}
        data-testid="review-prompt-card"
      >
        <p className="review-prompt-lead">
          {prompt.title} — {formatStarsLabel(stars)}★ saved
        </p>
      </div>
    );
  }

  return (
    <div
      className={`review-prompt-card ${compact ? "compact" : ""}`}
      data-testid="review-prompt-card"
    >
      {compact && prompt.poster_url ? (
        <img className="review-prompt-poster" src={prompt.poster_url} alt="" loading="lazy" />
      ) : null}
      <div className="review-prompt-body">
        <p className="review-prompt-lead">{lead}</p>
        <StarRatingPicker
          value={stars}
          onChange={setStars}
          disabled={saving || disabled}
          label={`Rate ${prompt.title}`}
          compact={compact}
        />
        {!compact ? (
          <textarea
            className="review-prompt-text"
            data-testid="review-prompt-text"
            rows={2}
            placeholder="Optional: what landed or missed?"
            value={reviewText}
            disabled={saving || disabled}
            onChange={(event) => setReviewText(event.target.value)}
          />
        ) : null}
        {plexConflict ? (
          <div className="review-plex-conflict" data-testid="review-plex-conflict">
            <p>Plex has {formatStarsLabel(plexConflict.plex_stars)}★ — keep or replace?</p>
            <div className="review-prompt-actions">
              <button
                type="button"
                className="ghost"
                data-testid="review-keep-plex-rating"
                disabled={saving || disabled}
                onClick={handleKeepPlexRating}
              >
                Keep Plex rating
              </button>
              <button
                type="button"
                className="primary"
                data-testid="review-replace-plex-rating"
                disabled={saving || disabled}
                onClick={handleReplacePlexRating}
              >
                Replace on Plex
              </button>
            </div>
          </div>
        ) : null}
        {error ? <p className="review-prompt-error">{error}</p> : null}
        {!plexConflict ? (
          <div className="review-prompt-actions">
            <button
              type="button"
              className="primary"
              data-testid="review-save-button"
              disabled={!stars || saving || disabled}
              onClick={() => handleSave(false)}
            >
              {saving ? "Saving…" : compact ? "Save" : "Save review"}
            </button>
            <button
              type="button"
              className="ghost"
              data-testid="review-skip-button"
              disabled={saving || disabled}
              onClick={handleSkip}
            >
              Skip
            </button>
          </div>
        ) : null}
      </div>
    </div>
  );
}

export function reviewPromptBlock(prompt, { compact = false } = {}) {
  return {
    type: "review_prompt",
    content: "",
    payload: { prompt, compact },
  };
}

export function reviewBatchBlock(prompts) {
  return {
    type: "review_batch",
    content: "",
    payload: { prompts },
  };
}
