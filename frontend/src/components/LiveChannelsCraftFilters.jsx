import { emptyFilterGroup, withSelectedOption } from "../lib/liveChannelsCraft.js";

/**
 * DNF craft filter editor: groups of AND conditions, OR'd together.
 */
export default function LiveChannelsCraftFilters({
  groups,
  onChange,
  filterOptions = {},
  exclusionCollectionName = "NoLive",
  testIdPrefix = "live-channels-craft",
  open = false,
}) {
  const rows = Array.isArray(groups) && groups.length ? groups : [emptyFilterGroup()];

  function updateGroup(index, patch) {
    const next = rows.map((row, i) => (i === index ? { ...row, ...patch } : row));
    onChange(next);
  }

  function addGroup() {
    onChange([...rows, emptyFilterGroup()]);
  }

  function removeGroup(index) {
    if (rows.length <= 1) {
      onChange([emptyFilterGroup()]);
      return;
    }
    onChange(rows.filter((_, i) => i !== index));
  }

  const hasAny = rows.some(
    (g) =>
      g.genres?.[0] || g.decade || g.theme || g.motif || g.content_rating,
  );

  return (
    <details
      className="live-channels-craft-filters live-channels-advanced"
      data-testid={`${testIdPrefix}-filters`}
      open={open || hasAny || undefined}
    >
      <summary>Narrow the pool</summary>
      <p className="wizard-note">
        Each block is an AND stack (genre ∩ decade ∩ motif…). Add another block to
        OR an alternate pool — e.g. Horror ∩ 1970s <strong>or</strong> Sci-Fi ∩ Space.
        Titles in the “{exclusionCollectionName}” Plex collection are skipped.
      </p>
      {rows.map((group, index) => {
        const genreOpts = withSelectedOption(
          filterOptions.genres,
          group.genres?.[0],
        );
        const decadeOpts = withSelectedOption(
          filterOptions.decades,
          group.decade,
          group.decade ? { label: `${group.decade}s` } : undefined,
        );
        const themeOpts = withSelectedOption(filterOptions.themes, group.theme);
        const motifOpts = withSelectedOption(filterOptions.motifs, group.motif);
        const ratingOpts = withSelectedOption(
          filterOptions.content_ratings,
          group.content_rating,
        );
        return (
          <div
            key={`filter-group-${index}`}
            className="live-channels-filter-group"
            data-testid={`${testIdPrefix}-filter-group-${index}`}
          >
            {index > 0 ? (
              <p className="wizard-note live-channels-filter-or" aria-hidden="true">
                — OR —
              </p>
            ) : null}
            <div className="live-channels-filter-group-header">
              <span className="wizard-note">
                Pool {index + 1}
                {rows.length > 1 ? " (AND)" : ""}
              </span>
              {rows.length > 1 ? (
                <button
                  type="button"
                  className="ghost"
                  data-testid={`${testIdPrefix}-filter-remove-${index}`}
                  onClick={() => removeGroup(index)}
                >
                  Remove pool
                </button>
              ) : null}
            </div>
            <label>
              Genre
              <select
                data-testid={`${testIdPrefix}-genre-${index}`}
                value={group.genres?.[0] || ""}
                onChange={(event) =>
                  updateGroup(index, {
                    genres: event.target.value ? [event.target.value] : [],
                  })
                }
              >
                <option value="">Any genre</option>
                {genreOpts.map((row) => (
                  <option key={row.value} value={row.value}>
                    {row.label}
                    {row.count ? ` (${row.count})` : ""}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Decade
              <select
                data-testid={`${testIdPrefix}-decade-${index}`}
                value={
                  group.decade === "" || group.decade == null
                    ? ""
                    : String(group.decade)
                }
                onChange={(event) =>
                  updateGroup(index, { decade: event.target.value })
                }
              >
                <option value="">Any decade</option>
                {decadeOpts.map((row) => (
                  <option key={row.value} value={String(row.value)}>
                    {row.label}
                    {row.count ? ` (${row.count})` : ""}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Motif
              <select
                data-testid={`${testIdPrefix}-motif-filter-${index}`}
                value={group.motif || ""}
                onChange={(event) =>
                  updateGroup(index, { motif: event.target.value })
                }
              >
                <option value="">Any motif</option>
                {motifOpts.map((row) => (
                  <option key={row.value} value={row.value}>
                    {row.label}
                    {row.count ? ` (${row.count})` : ""}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Theme
              <select
                data-testid={`${testIdPrefix}-theme-${index}`}
                value={group.theme || ""}
                onChange={(event) =>
                  updateGroup(index, { theme: event.target.value })
                }
              >
                <option value="">Any theme</option>
                {themeOpts.map((row) => (
                  <option key={row.value} value={row.value}>
                    {row.label}
                    {row.count ? ` (${row.count})` : ""}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Rating
              <select
                data-testid={`${testIdPrefix}-rating-${index}`}
                value={group.content_rating || ""}
                onChange={(event) =>
                  updateGroup(index, { content_rating: event.target.value })
                }
              >
                <option value="">Any rating</option>
                {ratingOpts.map((row) => (
                  <option key={row.value} value={row.value}>
                    {row.label}
                    {row.count ? ` (${row.count})` : ""}
                  </option>
                ))}
              </select>
            </label>
          </div>
        );
      })}
      <div className="wizard-actions">
        <button
          type="button"
          className="ghost"
          data-testid={`${testIdPrefix}-filter-add-or`}
          onClick={addGroup}
        >
          Add alternate pool (OR)
        </button>
      </div>
    </details>
  );
}
