import { useEffect, useState } from "react";
import { useLocation } from "react-router-dom";
import {
  getFeatures,
  getQualityCeiling,
  patchAuthMe,
  putPlayThroughProjectionist,
  putPublicBaseUrl,
  putQualityCeiling,
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
  const [justForMe, setJustForMe] = useState(false);
  const [qualityCeiling, setQualityCeiling] = useState("1080p");
  const [listRevision, setListRevision] = useState(0);
  const [awayAddress, setAwayAddress] = useState("");
  const [awaySaving, setAwaySaving] = useState(false);
  const [status, setStatus] = useState<{ type: string; message: string } | null>(null);

  useEffect(() => {
    let live = true;
    getFeatures()
      .then((features) => {
        if (!live) return;
        setPlayThrough(Boolean(features?.features?.play_through_projectionist));
        setJustForMe(
          Boolean(
            features?.features?.play_through_just_for_me ||
              features?.user?.play_through_just_for_me,
          ),
        );
        setAwayAddress(String(features?.addresses?.away || ""));
      })
      .catch(() => {
        if (live) setPlayThrough(false);
      });
    getQualityCeiling()
      .then((payload) => {
        if (!live) return;
        const ceiling = String((payload as { quality_ceiling?: string })?.quality_ceiling || "");
        if (ceiling) setQualityCeiling(ceiling);
      })
      .catch(() => {
        if (live) setQualityCeiling("1080p");
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
          <label className="settings-toggle-row" htmlFor="play-through-just-for-me-input">
            <input
              id="play-through-just-for-me-input"
              type="checkbox"
              aria-label="Play through Projectionist — just for me"
              checked={justForMe}
              data-testid="play-through-just-for-me"
              onChange={async (event) => {
                const next = event.target.checked;
                setJustForMe(next);
                try {
                  await patchAuthMe({ play_through_just_for_me: next });
                } catch (error) {
                  setJustForMe(!next);
                  setStatus({
                    type: "error",
                    message: (error as { message?: string })?.message || "Couldn’t save playback.",
                  });
                }
              }}
            />
            <span>Play through Projectionist — just for me</span>
          </label>
          <span className="field-help" data-testid="play-through-just-for-me-note">
            Only your plays use Projectionist. The household switch stays as it is.
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
                message:
                  (error as { message?: string })?.message || "Could not save the away address.",
              });
            } finally {
              setAwaySaving(false);
            }
          }}
        >
          {awaySaving ? "Saving…" : "Save away address"}
        </button>
      </SettingsPanel>
      <SettingsPanel
        id="quality-ceiling"
        title="Quality ceiling"
        lead="The tallest picture this household aims for. The default is 1080p. Titles above it are listed on the playability report. Only the owner can change this."
        testId="household-quality-ceiling"
      >
        <label htmlFor="quality-ceiling-input">
          <span>Quality ceiling</span>
          <select
            id="quality-ceiling-input"
            aria-label="Quality ceiling"
            data-testid="quality-ceiling"
            value={qualityCeiling}
            onChange={async (event) => {
              const next = event.target.value;
              const previous = qualityCeiling;
              setQualityCeiling(next);
              try {
                const saved = await putQualityCeiling(next);
                const ceiling = String(
                  (saved as { quality_ceiling?: string })?.quality_ceiling || next,
                );
                setQualityCeiling(ceiling);
                setListRevision((current) => current + 1);
                setStatus({ type: "ok", message: "Saved the quality ceiling." });
              } catch (error) {
                setQualityCeiling(previous);
                setStatus({
                  type: "error",
                  message:
                    (error as { message?: string })?.message ||
                    "Couldn’t save the quality ceiling.",
                });
              }
            }}
          >
            <option value="720p">720p</option>
            <option value="1080p">1080p</option>
            <option value="2160p">4K</option>
          </select>
        </label>
      </SettingsPanel>
      <SettingsPanel id="playability" title="Playability" testId="household-playability">
        <PlayabilityReport listRevision={listRevision} />
      </SettingsPanel>
      <SettingsPanel id="copies" title="Copies made ahead" testId="household-copies">
        <CopiesAhead />
      </SettingsPanel>
    </div>
  );
}
