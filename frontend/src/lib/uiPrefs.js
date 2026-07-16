const FONT_SIZES = {
  small: "13px",
  medium: "15px",
  large: "17px",
};

/** Apply the user's preferred base font size via CSS variable on :root. */
export function applyUiFontSize(size) {
  const key = FONT_SIZES[size] ? size : "medium";
  const px = FONT_SIZES[key];
  if (typeof document === "undefined") return key;
  document.documentElement.style.setProperty("--base-font-size", px);
  document.documentElement.dataset.fontSize = key;
  return key;
}

export function normalizeUiFontSize(size) {
  return FONT_SIZES[size] ? size : "medium";
}
