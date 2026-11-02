import type { Ref, RefCallback } from "react";

/**
 * Combine multiple refs (ref objects and/or callback refs) into one
 * callback ref for a single DOM node — e.g. a drawer that needs both
 * `useAnchoredPopover`'s panel ref and `useFocusTrap`'s container ref.
 *
 * Written as a small utility (rather than assigning `ref.current = node`
 * inline at the JSX call site) so the mutation lives in one obviously-safe
 * place instead of looking like a direct write to a hook's return value.
 */
export function mergeRefs<T>(...refs: Array<Ref<T> | undefined | null>): RefCallback<T> {
  return (node: T) => {
    for (const ref of refs) {
      if (!ref) continue;
      if (typeof ref === "function") {
        ref(node);
      } else {
        (ref as { current: T | null }).current = node;
      }
    }
  };
}
