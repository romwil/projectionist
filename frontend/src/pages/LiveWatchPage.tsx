import LivePage from "./LivePage";

/** Dedicated pop-out TV window — watch-first, same proxy/OSD/CC as `/live`. */
export default function LiveWatchPage() {
  return (
    <div className="live-theater-shell" data-theater-mode="true" data-testid="live-theater-shell">
      <LivePage popout />
    </div>
  );
}
