import { useEffect, useRef, useState } from "react";
import {
  changePassword,
  getAuthMe,
  getEngagementSummary,
  getFeatures,
  linkPlexAccount,
  patchAuthMe,
  pollPlexPinLogin,
  signOutEverywhere,
  startPlexPinLogin,
  uploadAuthAvatar,
} from "../../api/client";
import SettingsPageHeader from "../../components/settings/SettingsPageHeader";
import SettingsPanel from "../../components/settings/SettingsPanel";
import WeatherLocationPicker from "../../components/weather/WeatherLocationPicker";
import UserAvatar from "../../components/UserAvatar";
import { startPlexPinPoll } from "../../lib/plexPinPoll";
import { signOut } from "../../lib/signOut.js";
import {
  applyUiFontSize,
  applyUiTheme,
  loadPauseWhenBackgrounded,
  normalizeUiFontSize,
  normalizeUiTheme,
  persistPauseWhenBackgrounded,
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
  const [user, setUser] = useState<any | null>(null);
  const [preferredName, setPreferredName] = useState("");
  const [fontSize, setFontSize] = useState("medium");
  const [uiTheme, setUiTheme] = useState("system");
  const [pauseWhenBackgrounded, setPauseWhenBackgrounded] = useState(() =>
    loadPauseWhenBackgrounded(),
  );
  const [status, setStatus] = useState<any | null>(null);
  const [saving, setSaving] = useState(false);
  const [uploadingAvatar, setUploadingAvatar] = useState(false);
  const [avatarBust, setAvatarBust] = useState("");
  const [requestPath, setRequestPath] = useState("direct");
  const [seerrLinked, setSeerrLinked] = useState(false);
  const [linkBusy, setLinkBusy] = useState(false);
  const [linkWaiting, setLinkWaiting] = useState(false);
  const [linkAuthorized, setLinkAuthorized] = useState(false);
  const [linkPinId, setLinkPinId] = useState<any | null>(null);
  const [linkAuthUrl, setLinkAuthUrl] = useState("");
  const [linkPassword, setLinkPassword] = useState("");
  const linkPollRef = useRef<any>(null);
  const avatarInputRef = useRef<HTMLInputElement | null>(null);
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [passwordStatus, setPasswordStatus] = useState<any | null>(null);
  const [changingPassword, setChangingPassword] = useState(false);
  const [signOutEverywhereStatus, setSignOutEverywhereStatus] = useState<any | null>(null);
  const [signingOutEverywhere, setSigningOutEverywhere] = useState(false);
  const [defaultPage, setDefaultPage] = useState("auto");
  const [llmConfigured, setLlmConfigured] = useState(true);
  const [engagement, setEngagement] = useState<any>({ loading: true, data: null, error: "" });

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
        setDefaultPage(String(next?.default_page || "auto"));
      })
      .catch(() => setUser(null));
    getFeatures()
      .then((data) => {
        setRequestPath(data?.request_path || data?.features?.request_path || "direct");
        setLlmConfigured(Boolean(data?.features?.llm_configured));
      })
      .catch(() => {});
    getEngagementSummary()
      .then((data) => setEngagement({ loading: false, data, error: "" }))
      .catch((err) =>
        setEngagement({
          loading: false,
          data: null,
          error: (err as { message?: string }).message || "Could not load badges.",
        }),
      );
  }, []);

  // BD-2: /my-journey redirects here with #badges — land on the badges panel.
  useEffect(() => {
    if (typeof window === "undefined" || window.location.hash !== "#badges") return;
    const el = document.getElementById("badges");
    if (el && typeof el.scrollIntoView === "function") el.scrollIntoView();
  }, [engagement.loading]);

  useEffect(() => {
    return () => {
      if (typeof linkPollRef.current === "function") linkPollRef.current();
    };
  }, []);

  function stopLinkWait() {
    if (typeof linkPollRef.current === "function") {
      linkPollRef.current();
      linkPollRef.current = null;
    }
    setLinkWaiting(false);
    setLinkBusy(false);
  }

  function scheduleLinkPoll(pinId: any, deadline: any) {
    if (typeof linkPollRef.current === "function") {
      linkPollRef.current();
    }
    linkPollRef.current = startPlexPinPoll({
      deadline,
      peek: true,
      poll: () => pollPlexPinLogin(pinId, { peek: true }),
      onSuccess: () => {
        linkPollRef.current = null;
        setLinkAuthorized(true);
        setLinkWaiting(false);
        setLinkBusy(false);
      },
      onTimeout: () => {
        stopLinkWait();
        setStatus({ type: "error", message: "Plex sign-in timed out. Try again." });
      },
      onError: (error: any) => {
        stopLinkWait();
        setStatus({ type: "error", message: (error as { message?: string }).message || "Could not check Plex." });
      },
    });
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
    } catch (error: unknown) {
      setLinkBusy(false);
      setStatus({ type: "error", message: (error as { message?: string }).message || "Could not start Plex linking." });
    }
  }

  async function handleConfirmLinkPlex(event: any) {
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
      setStatus({
        type: "success",
        message: "Plex is linked. Watch history can now map to this account.",
      });
    } catch (error: unknown) {
      setStatus({ type: "error", message: (error as { message?: string }).message || "Could not link Plex." });
    } finally {
      setLinkBusy(false);
    }
  }

  async function handleSave(event: any) {
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
    } catch (error: unknown) {
      setStatus({ type: "error", message: (error as { message?: string }).message || "Could not save." });
    } finally {
      setSaving(false);
    }
  }

  async function handleSignOut() {
    await signOut();
  }

  async function handleDefaultPageChange(next: string) {
    const previous = defaultPage;
    setDefaultPage(next);
    try {
      const result = await patchAuthMe({ default_page: next });
      setDefaultPage(String(result.user?.default_page || next));
    } catch (error: unknown) {
      setDefaultPage(previous);
      setStatus({ type: "error", message: (error as { message?: string }).message || "Could not save default page." });
    }
  }

  async function handleChangePassword(event: any) {
    event.preventDefault();
    setPasswordStatus(null);
    if (newPassword.length < 8) {
      setPasswordStatus({ type: "error", message: "New password must be at least 8 characters." });
      return;
    }
    if (newPassword !== confirmPassword) {
      setPasswordStatus({ type: "error", message: "New password and confirmation do not match." });
      return;
    }
    setChangingPassword(true);
    try {
      await changePassword(currentPassword, newPassword);
      setCurrentPassword("");
      setNewPassword("");
      setConfirmPassword("");
      setPasswordStatus({
        type: "success",
        message: "Password changed. Every other signed-in device was signed out.",
      });
    } catch (error: unknown) {
      setPasswordStatus({ type: "error", message: (error as { message?: string }).message || "Could not change password." });
    } finally {
      setChangingPassword(false);
    }
  }

  async function handleSignOutEverywhere() {
    setSignOutEverywhereStatus(null);
    setSigningOutEverywhere(true);
    try {
      await signOutEverywhere();
      setSignOutEverywhereStatus({
        type: "success",
        message: "Every other signed-in device was signed out. This device stays signed in.",
      });
    } catch (error: unknown) {
      setSignOutEverywhereStatus({
        type: "error",
        message: (error as { message?: string }).message || "Could not sign out other devices.",
      });
    } finally {
      setSigningOutEverywhere(false);
    }
  }

  async function handleAvatarChange(event: any) {
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
    } catch (error: unknown) {
      setStatus({ type: "error", message: (error as { message?: string }).message || "Could not upload photo." });
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
                Youth mode · the owner can review curator notes saved since Youth mode started. Older
                memory stays private.
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
          title="Weather place"
          lead="Used by the Weather Channel. The household default applies until you save a place."
          testId="settings-weather-place"
        >
          <WeatherLocationPicker
            savedPlace={user.weather_place || ""}
            source={user.weather_place && user.weather_lat != null ? "profile" : "household"}
            householdPlace=""
            onSaved={(next) => {
              if (next) setUser((prev: any) => ({ ...(prev || {}), ...next }));
            }}
          />
        </SettingsPanel>

        <SettingsPanel
          title="Appearance"
          lead="Lights Up is gallery paper; Lights Down is the cinema chamber. Match system follows your OS preference."
          testId="ui-theme-fieldset"
        >
          <div
            className="settings-ui-theme-options"
            role="radiogroup"
            aria-label="Appearance theme"
          >
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
          title="Default page"
          lead={
            llmConfigured
              ? "Where Projectionist opens after you sign in."
              : "No language model is configured yet, so Auto opens Explore instead of Chat until one is connected."
          }
          testId="default-page-fieldset"
        >
          <div className="settings-default-page-options" role="radiogroup" aria-label="Default page">
            {[
              { value: "auto", label: "Auto", help: llmConfigured ? "Chat" : "Explore (no LLM yet)" },
              { value: "chat", label: "Chat" },
              { value: "explore", label: "Explore" },
            ].map((option) => (
              <label
                key={option.value}
                className={`settings-theme-option ${defaultPage === option.value ? "selected" : ""}`}
              >
                <input
                  type="radio"
                  name="default-page"
                  value={option.value}
                  checked={defaultPage === option.value}
                  data-testid={`default-page-${option.value}`}
                  onChange={() => handleDefaultPageChange(option.value)}
                />
                <span>
                  {option.label}
                  {option.help ? <span className="field-help"> · {option.help}</span> : null}
                </span>
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

        <SettingsPanel
          title="Playback"
          lead="Play keeps going when you switch Mac Spaces or hide the tab. Turn this on only if you want the reel to pause whenever Projectionist is in the background."
          testId="playback-prefs-fieldset"
        >
          <label className="settings-toggle-row">
            <input
              type="checkbox"
              checked={pauseWhenBackgrounded}
              data-testid="pause-when-backgrounded"
              onChange={(event) => {
                const next = event.target.checked;
                setPauseWhenBackgrounded(next);
                persistPauseWhenBackgrounded(next);
              }}
            />
            <span>Pause when backgrounded</span>
          </label>
          <span className="field-help">
            Stored in this browser only (`projectionist.pause_when_backgrounded`). Off by default.
          </span>
        </SettingsPanel>

        <div className="settings-actions">
          <button type="submit" data-testid="preferred-name-save" disabled={saving}>
            {saving ? "Saving…" : "Save profile"}
          </button>
        </div>
      </form>

      {status ? (
        <p
          className={`status ${status.type === "error" ? "status-error" : ""}`}
          data-testid="profile-status"
        >
          {status.message}
        </p>
      ) : null}

      <SettingsPanel
        id="badges"
        title="Badges &amp; achievements"
        lead="Milestones from chatting, rating titles, and finishing curated paths — what used to be My Journey."
        testId="settings-badges"
      >
        {engagement.loading ? <p className="status status-secondary">Loading badges…</p> : null}
        {engagement.error ? <p className="status status-error">{engagement.error}</p> : null}
        {!engagement.loading && engagement.data ? (
          <>
            <p className="status status-secondary" data-testid="badges-streak">
              Chat days in a row: {engagement.data.streak?.current_count || 0}
              {engagement.data.streak?.best_count ? ` · best ${engagement.data.streak.best_count}` : ""}
            </p>
            {(engagement.data.badges || []).length ? (
              <ul className="engagement-card-list" data-testid="badges-earned-list">
                {engagement.data.badges.map((badge: any) => (
                  <li key={badge.id} className="engagement-card">
                    <strong>{badge.name}</strong>
                    <p>{badge.description}</p>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="status status-secondary" data-testid="badges-empty">
                No badges yet — rate a title or keep a chat streak going to start.
              </p>
            )}
            {(engagement.data.challenges || []).length ? (
              <ul className="engagement-card-list" data-testid="badges-challenges-list">
                {engagement.data.challenges.map((challenge: any) => (
                  <li key={challenge.id} className="engagement-card">
                    <strong>{challenge.title}</strong>
                    <p>{challenge.description}</p>
                    <span className="status status-secondary">
                      {challenge.progress || 0} / {challenge.target_count}
                      {challenge.completed_at ? " · done" : ""}
                    </span>
                  </li>
                ))}
              </ul>
            ) : null}
          </>
        ) : null}
      </SettingsPanel>

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
              <button
                type="submit"
                className="primary"
                data-testid="link-plex-submit"
                disabled={linkBusy || !linkPassword}
              >
                {linkBusy ? "Linking…" : "Confirm and link Plex"}
              </button>
            </form>
          ) : null}
        </SettingsPanel>
      ) : (
        <SettingsPanel title="Plex" testId="settings-plex-linked">
          <p className="status status-secondary">
            Plex account linked. Watch history maps to this household member.
          </p>
        </SettingsPanel>
      )}

      {user.auth_method === "local" ? (
        <SettingsPanel
          title="Password"
          lead="Changing your password signs out every other device that is signed in as you."
          testId="settings-password"
        >
          <form className="settings-form" onSubmit={handleChangePassword}>
            <label>
              <span>Current password</span>
              <input
                type="password"
                data-testid="current-password-input"
                value={currentPassword}
                autoComplete="current-password"
                onChange={(event) => setCurrentPassword(event.target.value)}
                required
              />
            </label>
            <label>
              <span>New password</span>
              <input
                type="password"
                data-testid="new-password-input"
                value={newPassword}
                autoComplete="new-password"
                minLength={8}
                onChange={(event) => setNewPassword(event.target.value)}
                required
              />
            </label>
            <label>
              <span>Confirm new password</span>
              <input
                type="password"
                data-testid="confirm-password-input"
                value={confirmPassword}
                autoComplete="new-password"
                minLength={8}
                onChange={(event) => setConfirmPassword(event.target.value)}
                required
              />
            </label>
            <div className="settings-actions">
              <button type="submit" data-testid="change-password-submit" disabled={changingPassword}>
                {changingPassword ? "Changing…" : "Change password"}
              </button>
            </div>
          </form>
          {passwordStatus ? (
            <p
              className={`status ${passwordStatus.type === "error" ? "status-error" : ""}`}
              data-testid="password-status"
            >
              {passwordStatus.message}
            </p>
          ) : null}
        </SettingsPanel>
      ) : null}

      <SettingsPanel
        title="Sessions"
        lead="Sign out every other device signed in as you (phones, tablets, shared TVs). This device stays signed in."
        testId="settings-sessions"
      >
        <button
          type="button"
          className="ghost"
          data-testid="sign-out-everywhere"
          disabled={signingOutEverywhere}
          onClick={handleSignOutEverywhere}
        >
          {signingOutEverywhere ? "Signing out other devices…" : "Sign out everywhere else"}
        </button>
        {signOutEverywhereStatus ? (
          <p
            className={`status ${signOutEverywhereStatus.type === "error" ? "status-error" : ""}`}
            data-testid="sign-out-everywhere-status"
          >
            {signOutEverywhereStatus.message}
          </p>
        ) : null}
      </SettingsPanel>

      <div className="settings-actions">
        <button
          type="button"
          className="ghost"
          data-testid="settings-sign-out"
          onClick={handleSignOut}
        >
          Sign out
        </button>
      </div>
    </div>
  );
}
