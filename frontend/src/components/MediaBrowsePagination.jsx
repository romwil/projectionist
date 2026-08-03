export default function MediaBrowsePagination({
  summary,
  pageSize,
  pageSizes,
  onPageSizeChange,
  hasPrevious,
  hasNext,
  onPrevious,
  onNext,
  testIdPrefix = "media-browse",
  testIdSuffix = "",
}) {
  if (!summary) return null;

  return (
    <nav
      className="media-browse-pagination"
      aria-label="Results pagination"
      data-testid={`${testIdPrefix}-pagination${testIdSuffix}`}
    >
      <p
        className="media-browse-pagination-summary"
        data-testid={`${testIdPrefix}-page-summary${testIdSuffix}`}
      >
        {summary}
      </p>
      <div className="media-browse-pagination-controls">
        {pageSizes?.length ? (
          <label className="media-browse-pagination-size">
            <span>Per page</span>
            <select
              value={String(pageSize)}
              data-testid={`${testIdPrefix}-page-size${testIdSuffix}`}
              onChange={(event) => {
                const raw = event.target.value;
                onPageSizeChange?.(raw === "all" ? "all" : Number(raw));
              }}
            >
              {pageSizes.map((size) => (
                <option key={String(size)} value={String(size)}>
                  {String(size).toLowerCase() === "all" ? "All" : size}
                </option>
              ))}
            </select>
          </label>
        ) : null}
        <div className="media-browse-pagination-nav">
          <button
            type="button"
            className="ghost"
            data-testid={`${testIdPrefix}-prev${testIdSuffix}`}
            disabled={!hasPrevious}
            onClick={onPrevious}
          >
            Previous
          </button>
          <button
            type="button"
            className="ghost"
            data-testid={`${testIdPrefix}-next${testIdSuffix}`}
            disabled={!hasNext}
            onClick={onNext}
          >
            Next
          </button>
        </div>
      </div>
    </nav>
  );
}
