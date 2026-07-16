import { useEffect, useState } from "react";
import { getAuthMe, getFeatures, logout, patchAuthMe } from "../../api/client";
import {
  applyUiFontSize,
  applyUiTheme,
  normalizeUiFontSize,
  normalizeUiTheme,
} from "../../lib/uiPrefs.js";
import { useNavigate } from "react-router-dom";

const FONT_OPTIONS = [
  { value: "small", label: "Small" },
  { value: "medium", label: "Medium" },
  { value: "large", label: "Large" },
];

const THEME_OPTIONS = [
  { value: "lights_up", label: "Lights Up" },
  { value: "lights_down", label: "Lights Down" },
  { value: "system", label: "Match system" },
];

export default function ProfilePage() {
  const navigate = useNavigate();
  const [user, setUser] = useState(null);
  const [preferredName, setPreferredName] = useState("");
  const [fontSize, setFontSize] = useState("medium");
  const [uiTheme, setUiTheme] = useState("system");
  const [status, setStatus] = useState(null);
  const [saving, setSaving] = useState(false);
  const [requestPath, setRequestPath] = useState("direct");
  const [seerrLinked, setSeerrLinked] = useState(false);

  useEffect(() => {
    getAuthMe()
      .then((payload) => {
        const next = payload?.user || null;
        setUser(next);
        setPreferredName(next?.preferred_name || "");
        const nextFont = normalizeUiFontSize(next?.ui_font_size);
        setFontSize(nextFont);
        applyUiFontSize(nextFont);
        const nextTheme = normalizeUiTheme(next?.ui_theme);
        setUiTheme(nextTheme);
        applyUiTheme(nextTheme);
        setSeerrLinked(Boolean(next?.seerr_user_id));
      })
      .catch(() => setUser(null));
    getFeatures()
      .then((data) => {
        setRequestPath(data?.request_path || data?.features?.request_path || "direct");
      })
      .catch(() => {});
  }, []);

  async function handleSave(event) {
    event.preventDefault();
    setSaving(true);
    setStatus(null);
    try {
      const result = await patchAuthMe({
        preferred_name: preferredName,
        ui_font_size: fontSize,
        ui_theme: uiTheme,
      });
      setUser(result.user);
      setPreferredName(result.user?.preferred_name || "");
      const nextFont = normalizeUiFontSize(result.user?.ui_font_size);
      setFontSize(nextFont);
      applyUiFontSize(nextFont);
      const nextTheme = normalizeUiTheme(result.user?.ui_theme);
      setUiTheme(nextTheme);
      applyUiTheme(nextTheme);
      setStatus({ type: "success", message: "Profile saved." });
    } catch (error) {
      setStatus({ type: "error", message: error.message || "Could not save." });
    } finally {
      setSaving(false);
    }
  }

  async function handleSignOut() {
    try {
      await logout();
    } catch {
      // continue to login
    }
    navigate("/login", { replace: true });
  }

  if (!user) {
    return (
      <section className="settings-section" data-testid="settings-profile">
        <h2>Profile</h2>
        <p className="status status-secondary">Loading profile…</p>
      </section>
    );
  }

  return (
    <section className="settings-section" data-testid="settings-profile">
      <header className="settings-section-header">
        <h2>Profile</h2>
        <p>How you appear to CuratorX. Preferred name is what the curator calls you in chat.</p>
      </header>

      <div className="settings-identity">
        {user.avatar_url ? (
          <img src={user.avatar_url} alt="" className="settings-avatar" />
        ) : (
          <span className="settings-avatar settings-avatar-fallback">
            {(user.display_name || "U").slice(0, 2).toUpperCase()}
          </span>
        )}
        <div>
          <p className="settings-identity-name">{user.display_name}</p>
          {user.email ? <p className="settings-identity-meta">{user.email}</p> : null}
          <p className="settings-identity-meta">Role · {user.role}</p>
        </div>
      </div>

      <form className="settings-form" onSubmit={handleSave}>
        <label>
          <span>Preferred name</span>
          <input
            type="text"
            data-testid="preferred-name-input"
            value={preferredName}
            maxLength={80}
            placeholder={user.display_name || "How should we address you?"}
            onChange={(event) => setPreferredName(event.target.value)}
          />
          <span className="field-help">
            Falls back to your Plex display name when empty. Separate from server admin identity.
          </span>
        </label>

        <fieldset className="settings-ui-theme" data-testid="ui-theme-fieldset">
          <legend>Appearance</legend>
          <p className="field-help">
            Lights Up is gallery paper; Lights Down is the cinema chamber. Match system follows your
            OS preference.
          </p>
          <div className="settings-ui-theme-options" role="radiogroup" aria-label="Appearance theme">
            {THEME_OPTIONS.map((option) => (
              <label
                key={option.value}
                className={`settings-theme-option ${uiTheme === option.value ? "selected" : ""}`}
              >
                <input
                  type="radio"
                  name="ui-theme"
                  value={option.value}
                  checked={uiTheme === option.value}
                  data-testid={`ui-theme-${option.value}`}
                  onChange={() => {
                    setUiTheme(option.value);
                    applyUiTheme(option.value);
                  }}
                />
                <span>{option.label}</span>
              </label>
            ))}
          </div>
        </fieldset>

        <fieldset className="settings-font-size" data-testid="font-size-fieldset">
          <legend>Text size</legend>
          <p className="field-help">Scales UI text across CuratorX. Default is medium.</p>
          <div className="settings-font-size-options" role="radiogroup" aria-label="Text size">
            {FONT_OPTIONS.map((option) => (
              <label key={option.value} className={`settings-font-option ${fontSize === option.value ? "selected" : ""}`}>
                <input
                  type="radio"
                  name="ui-font-size"
                  value={option.value}
                  checked={fontSize === option.value}
                  data-testid={`font-size-${option.value}`}
                  onChange={() => {
                    setFontSize(option.value);
                    applyUiFontSize(option.value);
                  }}
                />
                <span>{option.label}</span>
              </label>
            ))}
          </div>
        </fieldset>

        <div className="config-actions">
          <button type="submit" data-testid="preferred-name-save" disabled={saving}>
            {saving ? "Saving…" : "Save profile"}
          </button>
        </div>
      </form>

      {status ? (
        <p className={`status ${status.type === "error" ? "status-error" : ""}`} data-testid="profile-status">
          {status.message}
        </p>
      ) : null}

      <div className="settings-subsection">
        <h3>Requests</h3>
        <p className="status status-secondary">
          Request path: <strong>{requestPath}</strong>
          {requestPath === "seerr" ? (
            <> · Seerr {seerrLinked ? "linked" : "not linked — re-sign in with Plex to refresh"}</>
          ) : null}
        </p>
      </div>

      <div className="config-actions">
        <button type="button" className="ghost" data-testid="settings-sign-out" onClick={handleSignOut}>
          Sign out
        </button>
      </div>
    </section>
  );
}
