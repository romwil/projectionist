import { useRouteAnnounce } from "../hooks/useRouteAnnounce";

/**
 * A11Y-004: visually-hidden `aria-live="polite"` region that announces the
 * new page title after every navigation ("Help · Projectionist"), for SR
 * users on pages whose `<h1>` focus-move (see `useRouteAnnounce`) lands
 * before the heading text itself is otherwise read.
 */
export default function RouteAnnouncer() {
  const announcement = useRouteAnnounce();
  return (
    <div role="status" aria-live="polite" data-testid="route-announcer" className="sr-only">
      {announcement}
    </div>
  );
}
