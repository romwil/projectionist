import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  getAuthMe,
  getFeatures,
  linkPlexAccount,
  logout,
  patchAuthMe,
  pollPlexPinLogin,
  startPlexPinLogin,
  uploadAuthAvatar,
} from "../../api/client";
import SettingsPageHeader from "../../components/settings/SettingsPageHeader";
import SettingsPanel from "../../components/settings/SettingsPanel";
import UserAvatar from "../../components/UserAvatar";
import {
  applyUiFontSize,
  applyUiTheme,
  normalizeUiFontSize,
  normalizeUiTheme,
} from "../../lib/uiPrefs.js";

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
  const [uploadingAvatar, setUploadingAvatar] = useState(false);
  const [avatarBust, setAvatarBust] = useState("");
  const [requestPath, setRequestPath] = useState("direct");
  const [seerrLinked, setSeerrLinked] = useState(false);
  const [linkBusy, setLinkBusy] = useState(false);
  const [linkWaiting, setLinkWaiting] = useState(false);
  const [linkAuthorized, setLinkAuthorized] = useState(false);
  const [linkPinId, setLinkPinId] = useState(null);
  const [linkAuthUrl, setLinkAuthUrl] = useState("");
  const [linkPassword, setLinkPassword] = useState("");
  const linkPollRef = useRef(null);
  const avatarInputRef = useRef(null);

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

  useEffect(() => {
    return () => {
      if (linkPollRef.current) clearTimeout(linkPollRef.current);
    };
  }, []);

  function stopLinkWait() {
    if (linkPollRef.current) {
      clearTimeout(linkPollRef.current);
      linkPollRef.current = null;
    }
    setLinkWaiting(false);
    setLinkBusy(false);
  }

  function scheduleLinkPoll(pinId, deadline) {
    linkPollRef.current = setTimeout(async () => {
      try {
        if (Date.now() >= deadline) {
          stopLinkWait();
          setStatus({ type: "error", message: "Plex sign-in timed out. Try again." });
          return;
        }
        const result = await pollPlexPinLogin(pinId, { peek: true });
        if (result?.authorized) {
          setLinkAuthorized(true);
          setLinkWaiting(false);
          setLinkBusy(false);
          return;
        }
        scheduleLinkPoll(pinId, deadline);
      } catch (error) {
        stopLinkWait();
        setStatus({ type: "error", message: error.message || "Could not check Plex." });
      }
    }, 1000);
  }

  async function handleStartLinkPlex() {
    setLinkBusy(true);
    setStatus(null);
    setLinkAuthorized(false);
    setLinkPassword("");
    try {
      const pin = await startPlexPinLogin();
      setLinkPinId(pin.id);
      setLinkAuthUrl(pin.auth_url || "");
      setLinkWaiting(true);
      if (pin.auth_url) {
        window.open(pin.auth_url, "projectionist-plex-link", "width=600,height=700");
      }
      scheduleLinkPoll(pin.id, Date.now() + 15 * 60 * 1000);
    } catch (error) {
      setLinkBusy(false);
      setStatus({ type: "error", message: error.message || "Could not start Plex linking." });
    }
  }

  async function handleConfirmLinkPlex(event) {
    event.preventDefault();
    if (!linkPinId || !linkPassword) {
      setStatus({ type: "error", message: "Enter your password to finish linking Plex." });
      return;
    }
    setLinkBusy(true);
    setStatus(null);
    try {
      const result = await linkPlexAccount({ pinId: linkPinId, password: linkPassword });
      setUser(result.user);
      setLinkAuthorized(false);
      setLinkPinId(null);
      setLinkAuthUrl("");
      setLinkPassword("");
      setStatus({ type: "success", message: "Plex is linked. Watch history can now map to this account." });
    } catch (error) {
      setStatus({ type: "error", message: error.message || "Could not link Plex." });
    } finally {
      setLinkBusy(false);
    }
  }

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

  async function handleAvatarChange(event) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    setUploadingAvatar(true);
    setStatus(null);
    try {
      const result = await uploadAuthAvatar(file);
      setUser(result.user);
      setAvatarBust(String(Date.now()));
      setStatus({ type: "success", message: "Profile photo updated." });
    } catch (error) {
      setStatus({ type: "error", message: error.message || "Could not upload photo." });
    } finally {
      setUploadingAvatar(false);
    }
  }

  if (!user) {
    return (
      <div className="settings-stack" data-testid="settings-profile">
        <SettingsPageHeader title="Profile">Loading profile…</SettingsPageHeader>
        <p className="status status-secondary">Loading profile…</p>
      </div>
    );
  }

  return (
    <div className="settings-stack" data-testid="settings-profile">
      <SettingsPageHeader title="Profile" testId="settings-profile-header">
        How you appear to Projectionist. Preferred name is what the curator calls you in chat.
      </SettingsPageHeader>

      <SettingsPanel title="Identity" testId="settings-profile-identity">
        <div className="settings-identity">
          <UserAvatar
            user={user}
            className="settings-avatar"
            fallbackClassName="settings-avatar settings-avatar-fallback"
            cacheBust={avatarBust}
          />
          <div>
            <p className="settings-identity-name">{user.display_name}</p>
            {user.email ? <p className="settings-identity-meta">{user.email}</p> : null}
            <p className="settings-identity-meta">Role · {user.role}</p>
            {user.is_youth ? (
              <p className="settings-identity-meta" data-testid="youth-mode-badge">
                Youth mode · memory may be reviewed by the owner for moderation.
              </p>
            ) : null}
            <div className="settings-avatar-actions">
              <input
                ref={avatarInputRef}
                type="file"
                accept="image/jpeg,image/png,image/webp,image/gif"
                hidden
                data-testid="avatar-file-input"
                onChange={handleAvatarChange}
              />
              <button
                type="button"
                className="ghost"
                data-testid="avatar-upload-button"
                disabled={uploadingAvatar}
                onClick={() => avatarInputRef.current?.click()}
              >
                {uploadingAvatar ? "Uploading…" : "Upload photo"}
              </button>
              <span className="field-help">
                JPEG, PNG, WebP, or GIF · max 2MB. Overrides a broken Plex avatar.
              </span>
            </div>
          </div>
        </div>
      </SettingsPanel>

      <form className="settings-form" onSubmit={handleSave}>
        <SettingsPanel title="Chat name" testId="settings-profile-name">
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
        </SettingsPanel>

        <SettingsPanel
          title="Appearance"
          lead="Lights Up is gallery paper; Lights Down is the cinema chamber. Match system follows your OS preference."
          testId="ui-theme-fieldset"
        >
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
        </SettingsPanel>

        <SettingsPanel
          title="Text size"
          lead="Scales UI text across Projectionist. Default is medium."
          testId="font-size-fieldset"
        >
          <div className="settings-font-size-options" role="radiogroup" aria-label="Text size">
            {FONT_OPTIONS.map((option) => (
              <label
                key={option.value}
                className={`settings-font-option ${fontSize === option.value ? "selected" : ""}`}
              >
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
        </SettingsPanel>

        <div className="settings-actions">
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

      <SettingsPanel title="Requests" testId="settings-profile-requests">
        <p className="status status-secondary">
          Request path: <strong>{requestPath}</strong>
          {requestPath === "seerr" ? (
            <> · Seerr {seerrLinked ? "linked" : "not linked — re-sign in with Plex to refresh"}</>
          ) : null}
        </p>
      </SettingsPanel>

      {!user.plex_user_id ? (
        <SettingsPanel
          title="Link Plex"
          lead="Link Plex to count watches from the server. Confirm with your household password in the same step — the PIN poll never binds on its own."
          testId="settings-link-plex"
        >
          {!linkWaiting && !linkAuthorized ? (
            <button
              type="button"
              className="primary"
              data-testid="link-plex-start"
              disabled={linkBusy}
              onClick={handleStartLinkPlex}
            >
              {linkBusy ? "Starting…" : "Link Plex"}
            </button>
          ) : null}
          {linkWaiting ? (
            <p className="status status-secondary" data-testid="link-plex-waiting">
              Finish signing in with Plex
              {linkAuthUrl ? (
                <>
                  {" "}
                  <a href={linkAuthUrl} target="_blank" rel="noreferrer">
                    Open Plex
                  </a>
                </>
              ) : null}
              . This page waits until Plex authorizes — it does not attach yet.
              <button type="button" className="ghost" onClick={stopLinkWait}>
                Cancel
              </button>
            </p>
          ) : null}
          {linkAuthorized ? (
            <form onSubmit={handleConfirmLinkPlex} data-testid="link-plex-confirm">
              <label>
                <span>Confirm with your password</span>
                <input
                  type="password"
                  data-testid="link-plex-password"
                  value={linkPassword}
                  onChange={(event) => setLinkPassword(event.target.value)}
                  autoComplete="current-password"
                  required
                />
              </label>
              <button type="submit" className="primary" data-testid="link-plex-submit" disabled={linkBusy || !linkPassword}>
                {linkBusy ? "Linking…" : "Confirm and link Plex"}
              </button>
            </form>
          ) : null}
        </SettingsPanel>
      ) : (
        <SettingsPanel title="Plex" testId="settings-plex-linked">
          <p className="status status-secondary">Plex account linked. Watch history maps to this household member.</p>
        </SettingsPanel>
      )}

      <div className="settings-actions">
        <button type="button" className="ghost" data-testid="settings-sign-out" onClick={handleSignOut}>
          Sign out
        </button>
      </div>
    </div>
  );
}
