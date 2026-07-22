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
import { loginLede, plexAdvancedCopy, resolveAuthMethods } from "../lib/loginScreen";

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
    const advanced = plexAdvancedCopy({ open: true });
    const token = authToken.trim();
    if (!token) {
      setError(advanced.emptyError);
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
        setError("Sign-in provider did not return an authorization URL.");
        setLoading(false);
      }
    } catch (signInError) {
      setError(formatApiError(signInError));
      setLoading(false);
    }
  }

  const methods = resolveAuthMethods(features?.auth_methods);
  const plexEnabled = methods.includes("plex");
  const localEnabled = methods.includes("local");
  const oidcEnabled = methods.includes("oidc");
  const oidcProviderName = features?.auth?.oidc_provider_name || "SSO";
  const noMethods = features != null && methods.length === 0;
  const lede = loginLede(methods);
  const advanced = plexAdvancedCopy({ open: showTokenInput });

  const methodDivider = (
    <div className="login-divider" role="separator">
      <span>or</span>
    </div>
  );

  return (
    <div className="login-page" data-testid="login-page">
      <div className="login-card">
        <p className="eyebrow">CuratorX</p>
        <h1>Sign in</h1>
        <p className="login-lede">{lede}</p>

        {error ? <InlineAlert type="error" message={error} /> : null}

        {noMethods ? (
          <InlineAlert type="error" message="No sign-in methods are enabled. Ask the owner to check Configuration." />
        ) : null}

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
                  Finish signing in in the Plex window. This page updates when you are done.
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
              <div className="login-advanced" data-testid="plex-advanced">
                <button
                  type="button"
                  className="login-advanced-toggle"
                  data-testid="show-token-login"
                  aria-expanded={showTokenInput}
                  onClick={() => setShowTokenInput((open) => !open)}
                >
                  {advanced.toggleLabel}
                </button>
                {showTokenInput ? (
                  <form className="login-form" onSubmit={handleTokenSignIn}>
                    <label className="login-field">
                      <span>{advanced.tokenLabel}</span>
                      <input
                        type="password"
                        data-testid="plex-token-input"
                        value={authToken}
                        onChange={(event) => setAuthToken(event.target.value)}
                        placeholder={advanced.tokenPlaceholder}
                        autoComplete="off"
                        disabled={loading}
                      />
                    </label>
                    <p className="login-help">{advanced.tokenHelp}</p>
                    <button
                      type="submit"
                      className="login-secondary"
                      data-testid="submit-plex-login"
                      disabled={loading}
                    >
                      {loading ? "Signing in…" : advanced.submitLabel}
                    </button>
                  </form>
                ) : null}
              </div>
            ) : null}
          </div>
        ) : null}

        {oidcEnabled ? (
          <div className="login-form" data-testid="oidc-login-section">
            {plexEnabled ? methodDivider : null}
            <button
              type="button"
              className="login-primary login-oidc"
              data-testid="oidc-login-button"
              disabled={loading || waitingForPlex}
              onClick={handleOidcLogin}
            >
              {loading ? "Redirecting…" : `Sign in with ${oidcProviderName}`}
            </button>
          </div>
        ) : null}

        {localEnabled ? (
          <div className="login-form" data-testid="local-login-section">
            {plexEnabled || oidcEnabled ? methodDivider : null}
            <form onSubmit={handleLocalLogin}>
              <label className="login-field">
                <span>Username</span>
                <input
                  type="text"
                  data-testid="local-username"
                  value={localUsername}
                  onChange={(e) => setLocalUsername(e.target.value)}
                  placeholder="Username"
                  autoComplete="username"
                  disabled={loading || waitingForPlex}
                />
              </label>
              <label className="login-field">
                <span>Password</span>
                <input
                  type="password"
                  data-testid="local-password"
                  value={localPassword}
                  onChange={(e) => setLocalPassword(e.target.value)}
                  placeholder="Password"
                  autoComplete="current-password"
                  disabled={loading || waitingForPlex}
                />
              </label>
              <button
                type="submit"
                className="login-primary"
                data-testid="local-login-submit"
                disabled={loading || waitingForPlex}
              >
                {loading ? "Signing in…" : "Sign in"}
              </button>
            </form>
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
