type QueryRoot = Pick<Document, "getElementById" | "querySelector">;

/**
 * A11Y-008: where "Skip to content" lands. Prefer `#main`; pages that own a
 * `<main>` without the id still get a target instead of a dead link.
 */
export function findMainLandmark(root: QueryRoot | null | undefined): HTMLElement | null {
  if (!root) return null;
  const byId = root.getElementById("main");
  if (byId) return byId as HTMLElement;
  return (root.querySelector("main, [role='main']") as HTMLElement | null) || null;
}
