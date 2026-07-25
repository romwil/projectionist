import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import {
  formatApiError,
  getFeatures,
  loginWithPlex,
  pollPlexPinLogin,
  redeemInviteLocal,
  startOidcLogin,
  startPlexPinLogin,
  validateInvite,
} from "../api/client";
import InlineAlert from "../components/InlineAlert";
import { resolveAuthMethods } from "../lib/loginScreen";

const PIN_POLL_MS = 1000;
const PIN_TIMEOUT_MS = 15 * 60 * 1000;

/**
 * Public invite redeem page: /join?token=…
 */
export default function JoinPage() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const token = (searchParams.get("token") || "").trim();
  const pollRef = useRef(null);

  const [features, setFeatures] = useState(null);
  const [invite, setInvite] = useState(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [waitingForPlex, setWaitingForPlex] = useState(false);
  const [authUrl, setAuthUrl] = useState("");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");

  const reloadInvite = useCallback(() => {
    if (!token) {
      setError("This join link is missing a token.");
      setLoading(false);
      return;
    }
    setLoading(true);
    Promise.all([getFeatures(), validateInvite(token)])
      .then(([feat, data]) => {
        setFeatures(feat);
        setInvite(data?.invite || null);
        setError("");
      })
      .catch((err) => {
        setInvite(null);
        setError(formatApiError(err) || "This invite is not valid.");
      })
      .finally(() => setLoading(false));
  }, [token]);

  useEffect(() => {
    reloadInvite();
  }, [reloadInvite]);

  useEffect(() => {
    return () => {
      if (pollRef.current) clearTimeout(pollRef.current);
    };
  }, []);

  const methods = resolveAuthMethods(features?.auth_methods);
  const plexEnabled = methods.includes("plex") && (invite?.allowed_methods || []).includes("plex");
  const oidcEnabled = methods.includes("oidc") && (invite?.allowed_methods || []).includes("oidc");
  const localEnabled = methods.includes("local") && (invite?.allowed_methods || []).includes("local");

  function stopPinWait() {
    if (pollRef.current) {
      clearTimeout(pollRef.current);
      pollRef.current = null;
    }
    setWaitingForPlex(false);
    setAuthUrl("");
    setBusy(false);
  }

  function schedulePinPoll(pinId, deadline) {
    pollRef.current = setTimeout(async () => {
      try {
        if (Date.now() >= deadline) {
          stopPinWait();
          setError("Plex sign-in timed out. Try again.");
          return;
        }
        const result = await pollPlexPinLogin(pinId);
        if (result?.authenticated) {
          stopPinWait();
          navigate("/chat", { replace: true });
          return;
        }
        schedulePinPoll(pinId, deadline);
      } catch (err) {
        stopPinWait();
        setError(formatApiError(err) || "Plex sign-in failed.");
      }
    }, PIN_POLL_MS);
  }

  async function handlePlex() {
    setBusy(true);
    setError("");
    try {
      const pin = await startPlexPinLogin({ inviteToken: token });
      setWaitingForPlex(true);
      setAuthUrl(pin?.auth_url || "");
      if (pin?.auth_url) {
        window.open(pin.auth_url, "curatorx-plex-join", "noopener,noreferrer");
      }
      schedulePinPoll(pin.id, Date.now() + PIN_TIMEOUT_MS);
    } catch (err) {
      setBusy(false);
      setError(formatApiError(err) || "Could not start Plex sign-in.");
    }
  }

  async function handleOidc() {
    setBusy(true);
    setError("");
    try {
      const data = await startOidcLogin({ inviteToken: token });
      if (data?.authorize_url) {
        window.location.href = data.authorize_url;
        return;
      }
      setError("SSO did not return an authorize URL.");
      setBusy(false);
    } catch (err) {
      setBusy(false);
      setError(formatApiError(err) || "Could not start SSO.");
    }
  }

  async function handleLocal(event) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      await redeemInviteLocal({
        token,
        username: username.trim(),
        password,
      });
      navigate("/chat", { replace: true });
    } catch (err) {
      setError(formatApiError(err) || "Could not finish joining.");
      setBusy(false);
    }
  }

  async function handleTokenFallback(event) {
    event.preventDefault();
    const authToken = new FormData(event.target).get("auth_token");
    setBusy(true);
    setError("");
    try {
      await loginWithPlex(String(authToken || ""), { inviteToken: token });
      navigate("/chat", { replace: true });
    } catch (err) {
      setError(formatApiError(err) || "Could not finish joining.");
      setBusy(false);
    }
  }

  return (
    <div className="login-page" data-testid="join-page">
      <div className="login-card">
        <p className="eyebrow">Household invite</p>
        <h1>Join Projectionist</h1>
        {loading ? <p className="status status-secondary">Checking invite…</p> : null}
        {error ? <InlineAlert type="error" message={error} testId="join-error" /> : null}
        {!loading && invite ? (
          <>
            <p className="login-help" data-testid="join-invite-summary">
              You&apos;re joining as a <strong>{invite.role}</strong>
              {invite.is_youth ? " (Youth mode)" : ""}. This link works once.
            </p>
            {waitingForPlex ? (
              <p className="status status-secondary" data-testid="join-plex-waiting">
                Waiting for Plex…
                {authUrl ? (
                  <>
                    {" "}
                    <a href={authUrl} target="_blank" rel="noreferrer">
                      Open Plex again
                    </a>
                  </>
                ) : null}
              </p>
            ) : null}
            {plexEnabled ? (
              <button
                type="button"
                className="login-primary"
                data-testid="join-plex"
                disabled={busy || waitingForPlex}
                onClick={handlePlex}
              >
                Sign in with Plex
              </button>
            ) : null}
            {oidcEnabled ? (
              <button
                type="button"
                className="login-secondary"
                data-testid="join-oidc"
                disabled={busy || waitingForPlex}
                onClick={handleOidc}
              >
                Continue with SSO
              </button>
            ) : null}
            {localEnabled ? (
              <form className="login-form" onSubmit={handleLocal} data-testid="join-local-form">
                <label className="login-field">
                  <span>Choose a username</span>
                  <input
                    data-testid="join-username"
                    value={username}
                    onChange={(e) => setUsername(e.target.value)}
                    minLength={2}
                    required
                    disabled={busy}
                  />
                </label>
                <label className="login-field">
                  <span>Choose a password</span>
                  <input
                    type="password"
                    data-testid="join-password"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    minLength={8}
                    required
                    disabled={busy}
                  />
                </label>
                <button
                  type="submit"
                  className="login-primary"
                  data-testid="join-local-submit"
                  disabled={busy || username.trim().length < 2 || password.length < 8}
                >
                  {busy ? "Joining…" : "Create account & join"}
                </button>
              </form>
            ) : null}
            {plexEnabled ? (
              <details className="login-advanced">
                <summary>Advanced: Plex token</summary>
                <form onSubmit={handleTokenFallback}>
                  <input name="auth_token" data-testid="join-plex-token" placeholder="Plex auth token" />
                  <button type="submit" className="ghost" disabled={busy}>
                    Join with token
                  </button>
                </form>
              </details>
            ) : null}
          </>
        ) : null}
        <p className="login-help">
          Already a member? <Link to="/login">Sign in</Link>
        </p>
      </div>
    </div>
  );
}
