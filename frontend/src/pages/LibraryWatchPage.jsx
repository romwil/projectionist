import { useParams } from "react-router-dom";
import LibraryPlayer from "../components/theater/LibraryPlayer.jsx";

/** In-app library theater — Play CTA lands here. Pop-out uses the same player. */
export default function LibraryWatchPage({ popout = false }) {
  const { ratingKey } = useParams();
  return (
    <div className="watch-theater-shell" data-theater-mode="true" data-testid="watch-theater-shell">
      <LibraryPlayer key={ratingKey || ""} ratingKey={ratingKey} popout={popout} />
    </div>
  );
}
