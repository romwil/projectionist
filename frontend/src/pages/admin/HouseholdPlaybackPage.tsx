import { useEffect, useState } from "react";
import { useLocation } from "react-router-dom";
import {
  getFeatures,
  putPlayThroughProjectionist,
  putPublicBaseUrl,
} from "../../api/client";
import CopiesAhead from "../../components/settings/CopiesAhead";
import PlayabilityReport from "../../components/settings/PlayabilityReport";
import SettingsPageHeader from "../../components/settings/SettingsPageHeader";
import SettingsPanel from "../../components/settings/SettingsPanel";

/**
 * Owner-only household playback. Personal prefs stay on Settings → Profile.
 */
export default function HouseholdPlaybackPage() {
  const location = useLocation();
  const [playThrough, setPlayThrough] = useState(false);
  const [awayAddress, setAwayAddress] = useState("");
  const [awaySaving, setAwaySaving] = useState(false);
  const [status, setStatus] = useState<{ type: string; message: string } | null>(null);

  useEffect(() => {
    let live = true;
    getFeatures()
      .then((features) => {
        if (!live) return;
        setPlayThrough(Boolean(features?.features?.play_through_projectionist));
        setAwayAddress(String(features?.addresses?.away || ""));
      })
      .catch(() => {
        if (live) setPlayThrough(false);
      });
    return () => {
      live = false;
    };
  }, []);

  useEffect(() => {
    const id = String(location.hash || "").replace(/^#/, "");
    if (!id) return;
    const el = document.getElementById(id);
    if (el && typeof el.scrollIntoView === "function") el.scrollIntoView();
  }, [location.hash]);

  return (
    <div className="settings-stack" data-testid="household-playback">
      <SettingsPageHeader title="Playback" testId="household-playback-header">
        Household playback. These choices apply to everyone in the household.
      </SettingsPageHeader>
      {status ? (
        <p
          className={`status ${status.type === "error" ? "status-error" : ""}`}
          data-testid="household-playback-status"
        >
          {status.message}
        </p>
      ) : null}
      <SettingsPanel
        id="playback"
        title="Play through Projectionist"
        lead="When this is on, the next film or episode plays through Projectionist when the file can be remuxed. Captions stay on the usual path for now. Turning it off applies the next time someone presses play."
        testId="household-play-through"
      >
        <div id="play-through-projectionist">
          <label className="settings-toggle-row" htmlFor="play-through-projectionist-input">
            <input
              id="play-through-projectionist-input"
              type="checkbox"
              aria-label="Play through Projectionist (beta)"
              checked={playThrough}
              data-testid="play-through-projectionist"
              onChange={async (event) => {
                const next = event.target.checked;
                setPlayThrough(next);
                try {
                  await putPlayThroughProjectionist(next);
                } catch (error) {
                  setPlayThrough(!next);
                  setStatus({
                    type: "error",
                    message: (error as { message?: string })?.message || "Couldn’t save playback.",
                  });
                }
              }}
            />
            <span>Play through Projectionist (beta)</span>
          </label>
          <span className="field-help" data-testid="play-through-household-note">
            This affects everyone in the household.
          </span>
        </div>
      </SettingsPanel>
      <SettingsPanel
        id="away-address"
        title="Away address"
        lead="The address people use when they are not on the home network. Playback links stay relative, so the same film works at home and away. Leave this blank until you have one."
        testId="household-away"
      >
        <label htmlFor="away-address-input">
          <span>Away address</span>
          <input
            id="away-address-input"
            type="url"
            aria-label="Away address"
            data-testid="away-address"
            value={awayAddress}
            placeholder="https://your-household"
            autoComplete="off"
            spellCheck={false}
            onChange={(event) => setAwayAddress(event.target.value)}
          />
        </label>
        <button
          type="button"
          className="ghost"
          data-testid="away-address-save"
          disabled={awaySaving}
          onClick={async () => {
            setAwaySaving(true);
            try {
              const saved = await putPublicBaseUrl(awayAddress.trim());
              setAwayAddress(String(saved?.public_base_url || ""));
              setStatus({ type: "ok", message: "Saved the away address." });
            } catch (error) {
              setStatus({
                type: "error",
                message: (error as { message?: string })?.message || "Could not save the away address.",
              });
            } finally {
              setAwaySaving(false);
            }
          }}
        >
          {awaySaving ? "Saving…" : "Save away address"}
        </button>
      </SettingsPanel>
      <SettingsPanel id="playability" title="Playability" testId="household-playability">
        <PlayabilityReport />
      </SettingsPanel>
      <SettingsPanel id="copies" title="Copies made ahead" testId="household-copies">
        <CopiesAhead />
      </SettingsPanel>
    </div>
  );
}
