import { useParams } from "react-router-dom";
import LibraryPlayer from "../components/theater/LibraryPlayer.jsx";

/**
 * In-app library theater. The full player is mounted by InAppPlaybackHost so
 * shrink-to-page can keep it alive off this route. Pop-out is its own window
 * and still owns a player here.
 */
export default function LibraryWatchPage({ popout = false }) {
  const { ratingKey } = useParams();
  if (popout) {
    return (
      <div className="watch-theater-shell" data-theater-mode="true" data-testid="watch-theater-shell">
        <LibraryPlayer key={ratingKey || ""} ratingKey={ratingKey} popout />
      </div>
    );
  }
  return <div className="watch-theater-shell" data-theater-mode="true" data-testid="watch-theater-shell" />;
}
