import { useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import {
  formatApiError,
  getFeatures,
  loginWithLocal,
  loginWithPlex,
  pollPlexPinLogin,
  startOidcLogin,
  startPlexPinLogin,
} from "../api/client";
import InlineAlert from "../components/InlineAlert";

const PIN_POLL_MS = 1000;
const PIN_TIMEOUT_MS = 15 * 60 * 1000;

export default function LoginPage() {
  const navigate = useNavigate();
  const [features, setFeatures] = useState(null);
  const [authToken, setAuthToken] = useState("");
  const [showTokenInput, setShowTokenInput] = useState(false);
  const [loading, setLoading] = useState(false);
  const [waitingForPlex, setWaitingForPlex] = useState(false);
  const [authUrl, setAuthUrl] = useState("");
  const [error, setError] = useState("");
  const pollRef = useRef(null);
  const popupRef = useRef(null);

  const [localUsername, setLocalUsername] = useState("");
  const [localPassword, setLocalPassword] = useState("");

  useEffect(() => {
    getFeatures()
      .then((data) => {
        setFeatures(data);
        if (!data?.features?.multi_user_enabled) {
          navigate("/", { replace: true });
        }
      })
      .catch((fetchError) => setError(formatApiError(fetchError)));
  }, [navigate]);

  useEffect(() => {
    return () => {
      if (pollRef.current) {
        clearTimeout(pollRef.current);
      }
      if (popupRef.current && !popupRef.current.closed) {
        popupRef.current.close();
      }
    };
  }, []);

  function stopPinWait() {
    if (pollRef.current) {
      clearTimeout(pollRef.current);
      pollRef.current = null;
    }
    if (popupRef.current && !popupRef.current.closed) {
      popupRef.current.close();
    }
    popupRef.current = null;
    setWaitingForPlex(false);
    setAuthUrl("");
    setLoading(false);
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
          if (popupRef.current && !popupRef.current.closed) {
            popupRef.current.close();
          }
          popupRef.current = null;
          setWaitingForPlex(false);
          setLoading(false);
          navigate("/", { replace: true });
          return;
        }
        schedulePinPoll(pinId, deadline);
      } catch (pollError) {
        stopPinWait();
        setError(formatApiError(pollError));
      }
    }, PIN_POLL_MS);
  }

  async function handlePlexSignIn() {
    setLoading(true);
    setError("");
    setShowTokenInput(false);
    try {
      const pin = await startPlexPinLogin();
      setAuthUrl(pin.auth_url || "");
      setWaitingForPlex(true);
      const popup = window.open(pin.auth_url, "curatorx-plex-auth", "width=600,height=700");
      if (popup) {
        popup.focus();
        popupRef.current = popup;
      }
      const deadline = Date.now() + PIN_TIMEOUT_MS;
      schedulePinPoll(pin.id, deadline);
    } catch (signInError) {
      setWaitingForPlex(false);
      setLoading(false);
      setError(formatApiError(signInError));
    }
  }

  async function handleTokenSignIn(event) {
    event.preventDefault();
    const token = authToken.trim();
    if (!token) {
      setError("Paste a Plex auth token to continue.");
      return;
    }
    stopPinWait();
    setLoading(true);
    setError("");
    try {
      await loginWithPlex(token);
      navigate("/", { replace: true });
    } catch (signInError) {
      setError(formatApiError(signInError));
    } finally {
      setLoading(false);
    }
  }

  async function handleLocalLogin(event) {
    event.preventDefault();
    if (!localUsername.trim() || !localPassword) {
      setError("Enter your username and password.");
      return;
    }
    setLoading(true);
    setError("");
    try {
      await loginWithLocal(localUsername.trim(), localPassword);
      navigate("/", { replace: true });
    } catch (signInError) {
      setError(formatApiError(signInError));
    } finally {
      setLoading(false);
    }
  }

  async function handleOidcLogin() {
    setLoading(true);
    setError("");
    try {
      const data = await startOidcLogin();
      if (data?.authorize_url) {
        window.location.href = data.authorize_url;
      } else {
        setError("OIDC provider did not return an authorization URL.");
        setLoading(false);
      }
    } catch (signInError) {
      setError(formatApiError(signInError));
      setLoading(false);
    }
  }

  const authMethods = features?.auth_methods || [];
  const plexEnabled = authMethods.includes("plex");
  const localEnabled = authMethods.includes("local");
  const oidcEnabled = authMethods.includes("oidc");
  const oidcProviderName = features?.auth?.oidc_provider_name || "SSO";
  const noMethods = !plexEnabled && !localEnabled && !oidcEnabled;

  return (
    <div className="login-page" data-testid="login-page">
      <div className="login-card">
        <p className="eyebrow">CuratorX</p>
        <h1>Sign in</h1>
        <p className="login-lede">
          Multi-user mode is enabled. Sign in to access your conversations and watchlist.
        </p>

        {error ? <InlineAlert type="error" message={error} /> : null}

        {noMethods ? (
          <InlineAlert type="error" message="No sign-in methods are enabled in Configuration." />
        ) : null}

        {/* --- Local password login --- */}
        {localEnabled ? (
          <div className="login-form" data-testid="local-login-section">
            <form onSubmit={handleLocalLogin}>
              <label className="login-token-field">
                <span>Username</span>
                <input
                  type="text"
                  data-testid="local-username"
                  value={localUsername}
                  onChange={(e) => setLocalUsername(e.target.value)}
                  placeholder="Username"
                  autoComplete="username"
                  disabled={loading}
                />
              </label>
              <label className="login-token-field">
                <span>Password</span>
                <input
                  type="password"
                  data-testid="local-password"
                  value={localPassword}
                  onChange={(e) => setLocalPassword(e.target.value)}
                  placeholder="Password"
                  autoComplete="current-password"
                  disabled={loading}
                />
              </label>
              <button
                type="submit"
                className="login-primary"
                data-testid="local-login-submit"
                disabled={loading}
              >
                {loading ? "Signing in…" : "Sign in"}
              </button>
            </form>
          </div>
        ) : null}

        {/* --- Divider between methods --- */}
        {localEnabled && (plexEnabled || oidcEnabled) ? (
          <div className="login-divider">
            <span>or</span>
          </div>
        ) : null}

        {/* --- OIDC login --- */}
        {oidcEnabled ? (
          <div className="login-form" data-testid="oidc-login-section">
            <button
              type="button"
              className="login-primary login-oidc"
              data-testid="oidc-login-button"
              disabled={loading}
              onClick={handleOidcLogin}
            >
              {loading ? "Redirecting…" : `Sign in with ${oidcProviderName}`}
            </button>
          </div>
        ) : null}

        {/* --- Plex login --- */}
        {plexEnabled ? (
          <div className="login-form" data-testid="plex-login-section">
            {!waitingForPlex ? (
              <button
                type="button"
                className="login-primary"
                data-testid="sign-in-with-plex"
                disabled={loading}
                onClick={handlePlexSignIn}
              >
                {loading ? "Starting Plex…" : "Sign in with Plex"}
              </button>
            ) : (
              <div className="login-waiting" data-testid="plex-pin-waiting">
                <p className="login-help">
                  Complete sign-in in the Plex window. This page updates automatically when you are
                  done.
                </p>
                {authUrl ? (
                  <a
                    className="login-secondary-link"
                    href={authUrl}
                    target="_blank"
                    rel="noreferrer"
                    data-testid="open-plex-auth-link"
                  >
                    Open Plex sign-in
                  </a>
                ) : null}
                <button
                  type="button"
                  className="login-cancel"
                  data-testid="cancel-plex-login"
                  onClick={stopPinWait}
                >
                  Cancel
                </button>
              </div>
            )}

            {!waitingForPlex ? (
              <div className="login-advanced">
                {!showTokenInput ? (
                  <button
                    type="button"
                    className="login-advanced-toggle"
                    data-testid="show-token-login"
                    onClick={() => setShowTokenInput(true)}
                  >
                    Use a Plex auth token instead
                  </button>
                ) : (
                  <form className="login-form" onSubmit={handleTokenSignIn}>
                    <label className="login-token-field">
                      <span>Plex auth token (advanced)</span>
                      <input
                        type="password"
                        data-testid="plex-token-input"
                        value={authToken}
                        onChange={(event) => setAuthToken(event.target.value)}
                        placeholder="Paste X-Plex-Token value"
                        autoComplete="off"
                        disabled={loading}
                      />
                    </label>
                    <p className="login-help">
                      Prefer Sign in with Plex above. Plex no longer shows tokens on the account
                      settings page for most users. Only paste a token if you already have one from
                      another app or API session.
                    </p>
                    <button
                      type="submit"
                      className="login-primary"
                      data-testid="submit-plex-login"
                      disabled={loading}
                    >
                      {loading ? "Signing in…" : "Continue with token"}
                    </button>
                  </form>
                )}
              </div>
            ) : null}
          </div>
        ) : null}

        <p className="login-footer">
          <Link to="/help" data-testid="help-link">
            Help
          </Link>
          {" · "}
          <Link to="/privacy" data-testid="privacy-link">
            Privacy &amp; data use
          </Link>
          {" · "}
          <Link to="/about" data-testid="about-link">
            About
          </Link>
        </p>
      </div>
    </div>
  );
}
