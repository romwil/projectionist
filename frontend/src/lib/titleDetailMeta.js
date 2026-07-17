import { exploreCountryPath, exploreDecadePath, exploreLanguagePath } from "./browseLinks.js";
import { formatLanguageName, languageFacetKey } from "./languageNames.js";

export function decadeLabel(year) {
  if (!year || year < 1000) return null;
  return `${Math.floor(year / 10) * 10}s`;
}

export function decadeBrowsePath(year) {
  const label = decadeLabel(year);
  return label ? exploreDecadePath(label) : null;
}

export function languageBrowseMeta(code) {
  const key = languageFacetKey(code);
  if (!key) return null;
  return {
    label: formatLanguageName(code),
    path: exploreLanguagePath(key),
  };
}

export function countryBrowsePath(country) {
  return exploreCountryPath(country);
}
