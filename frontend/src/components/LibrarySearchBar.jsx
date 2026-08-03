const DEFAULT_PLACEHOLDER = "Search your library by title or plot…";
const DEFAULT_ARIA_LABEL = "Search your library";

/**
 * Hero library search bar shared by Explore (navigate to /search) and Search (progressive on-page).
 */
export default function LibrarySearchBar({
  value,
  onChange,
  onSubmit,
  placeholder = DEFAULT_PLACEHOLDER,
  ariaLabel = DEFAULT_ARIA_LABEL,
  testId = "library-search",
  inputTestId,
  submitTestId,
  className = "",
}) {
  const formClass = ["explore-search", className].filter(Boolean).join(" ");

  return (
    <form className={formClass} data-testid={testId} role="search" onSubmit={onSubmit}>
      <label className="library-search library-search--hero">
        <span className="material-symbols-outlined" aria-hidden="true">
          search
        </span>
        <input
          type="search"
          value={value}
          onChange={onChange}
          placeholder={placeholder}
          aria-label={ariaLabel}
          data-testid={inputTestId || `${testId}-input`}
        />
      </label>
      <button
        type="submit"
        className="explore-search-submit"
        data-testid={submitTestId || `${testId}-submit`}
      >
        Search
      </button>
    </form>
  );
}
