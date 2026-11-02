import { useEffect, useState } from "react";
import { listNotifications } from "../api/client";

/**
 * UX-014: the bottom nav's Inbox badge reflects `inboxUnreadCount` — the
 * same figure `App.tsx` keeps for the topbar, re-fetched independently here
 * since the bottom nav mounts outside `App.tsx`'s tree (it has to render on
 * every route, including ones `App.tsx` never does).
 */
export function useInboxUnreadCount({ enabled = true }: { enabled?: boolean } = {}) {
  const [count, setCount] = useState(0);

  useEffect(() => {
    if (!enabled) return;
    let cancelled = false;
    listNotifications({ unread_only: true, limit: 20 })
      .then((data: any) => {
        if (cancelled) return;
        setCount(Number(data?.unread_count) || (data?.items || []).length);
      })
      .catch(() => {
        if (!cancelled) setCount(0);
      });
    return () => {
      cancelled = true;
    };
  }, [enabled]);

  return count;
}
