import { titleLineParts } from "../lib/titleLine.js";

type TitleYearItem = { title?: unknown; year?: unknown } | null;

type TitleYearTextProps = {
  item?: TitleYearItem;
  fallback?: string;
  yearClassName?: string;
};

/**
 * Title and year as one wrapping line. Year is muted but stays in the same
 * inline flow so a long title wraps as `… Left (2009)`, not year alone.
 */
export default function TitleYearText({
  item,
  fallback = "Untitled",
  yearClassName = "title-line-year",
}: TitleYearTextProps) {
  const { title, year } = titleLineParts(item, { fallback });
  if (!year) return title;
  return (
    <>
      {title}
      {"\u00A0"}
      <span className={yearClassName}>({year})</span>
    </>
  );
}
