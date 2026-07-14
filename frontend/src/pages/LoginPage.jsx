import { useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import {
  formatApiError,
  getFeatures,
  loginWithPlex,
  pollPlexPinLogin,
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

  const plexEnabled = features?.auth?.plex_login_enabled !== false;

  return (
    <div className="login-page" data-testid="login-page">
      <div className="login-card">
        <p className="eyebrow">CuratorX</p>
        <h1>Sign in</h1>
        <p className="login-lede">
          Multi-user mode is enabled. Sign in with your Plex account to access your conversations and
          watchlist.
        </p>

        {error ? <InlineAlert type="error" message={error} /> : null}

        {plexEnabled ? (
          <div className="login-form">
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
        ) : (
          <InlineAlert type="error" message="Plex login is disabled in Configuration." />
        )}

        <p className="login-footer">
          <Link to="/privacy" data-testid="privacy-link">
            Privacy &amp; data use
          </Link>
        </p>
        <p className="login-footer">
          Need to change auth settings? <Link to="/config">Open Configuration</Link>
        </p>
      </div>
    </div>
  );
}
