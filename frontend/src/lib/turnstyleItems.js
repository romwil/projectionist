/** Shared display / count helpers for inline cards and turnstyle view. */

export function isDisplayableCard(item) {
  return Boolean(item?.title || item?.tmdb_id || item?.tvdb_id || item?.rating_key);
}

/** Cards shown in turnstyle / expand affordances — displayable only. */
export function filterDisplayableCards(items = []) {
  return (items || []).filter(isDisplayableCard);
}

/** Count used by "Expand N titles…" — must match turnstyle contents. */
export function turnstyleItemCount(items = []) {
  return filterDisplayableCards(items).length;
}
