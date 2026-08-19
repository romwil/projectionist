import { useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import {
  formatApiError,
  getFeatures,
  createAccessRequest,
  loginWithLocal,
  pollPlexPinLogin,
  startOidcLogin,
  startPlexPinLogin,
} from "../api/client";
import GlassDoor from "../components/GlassDoor";
import InlineAlert from "../components/InlineAlert";
import { loginLede, resolveAuthMethods } from "../lib/loginScreen";

const PIN_POLL_MS = 1000;
const PIN_TIMEOUT_MS = 15 * 60 * 1000;

export default function LoginPage() {
  const navigate = useNavigate();
  const [features, setFeatures] = useState(null);
  const [loading, setLoading] = useState(false);
  const [waitingForPlex, setWaitingForPlex] = useState(false);
  const [authUrl, setAuthUrl] = useState("");
  const [error, setError] = useState("");
  const pollRef = useRef(null);
  const popupRef = useRef(null);

  const [localUsername, setLocalUsername] = useState("");
  const [localPassword, setLocalPassword] = useState("");
  const [requestName, setRequestName] = useState("");
  const [requestEmail, setRequestEmail] = useState("");
  const [requestMessage, setRequestMessage] = useState("");
  const [organizationUrl, setOrganizationUrl] = useState("");
  const [requestStatus, setRequestStatus] = useState(null);
  const [requestBusy, setRequestBusy] = useState(false);
  const [showRequest, setShowRequest] = useState(false);

  useEffect(() => {
    getFeatures()
      .then((data) => {
        setFeatures(data);
        if (data?.setup_state === "setup") {
          navigate("/setup", { replace: true });
          return;
        }
        if (!data?.features?.multi_user_enabled) {
          navigate("/chat", { replace: true });
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
        if (result?.authenticated && result?.user) {
          if (popupRef.current && !popupRef.current.closed) {
            popupRef.current.close();
          }
          popupRef.current = null;
          setWaitingForPlex(false);
          setLoading(false);
          navigate("/chat", { replace: true });
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
    try {
      const pin = await startPlexPinLogin();
      setAuthUrl(pin.auth_url || "");
      setWaitingForPlex(true);
      const popup = window.open(pin.auth_url, "projectionist-plex-auth", "width=600,height=700");
      if (popup) {
        popup.focus();
        popupRef.current = popup;
      }
      schedulePinPoll(pin.id, Date.now() + PIN_TIMEOUT_MS);
    } catch (signInError) {
      setWaitingForPlex(false);
      setLoading(false);
      setError(formatApiError(signInError));
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
      navigate("/chat", { replace: true });
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
  const featuresLoading = features == null && !error;
  const plexEnabled = methods.includes("plex");
  const localEnabled = methods.includes("local") || featuresLoading;
  const oidcEnabled = methods.includes("oidc");
  const oidcProviderName = features?.auth?.oidc_provider_name || "SSO";
  const noMethods = features != null && methods.length === 0;
  const accessRequestsOn = features?.features?.access_requests_enabled !== false;
  const lede = featuresLoading ? "Loading sign-in options…" : loginLede(methods);
  const householdName = features?.household_domain || "Projectionist";

  const methodDivider = (
    <div className="login-divider" role="separator">
      <span>or</span>
    </div>
  );

  return (
    <GlassDoor
      testId="login-page"
      eyebrow={householdName}
      title="Sign in"
      lede={lede}
      footer={
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
      }
    >
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
              <p className="login-help">Finish signing in in the Plex window. This page updates when you are done.</p>
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
              <button type="button" className="login-cancel" data-testid="cancel-plex-login" onClick={stopPinWait}>
                Cancel
              </button>
            </div>
          )}
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
                disabled={loading || waitingForPlex || featuresLoading}
              />
            </label>
            <label className="login-field">
              <span>Password</span>
              <input
                type="password"
                data-testid="local-password"
                value={localPassword}
                onChange={(e) => setLocalPassword(e.target.value)}
                autoComplete="current-password"
                disabled={loading || waitingForPlex || featuresLoading}
              />
            </label>
            <button
              type="submit"
              className="login-primary"
              data-testid="local-login-submit"
              disabled={loading || waitingForPlex || featuresLoading}
            >
              {featuresLoading ? "Loading…" : loading ? "Signing in…" : "Sign in"}
            </button>
          </form>
        </div>
      ) : null}

      {accessRequestsOn ? (
        <div className="login-form login-request-access" data-testid="request-access-section">
          {plexEnabled || oidcEnabled || localEnabled ? methodDivider : null}
          {!showRequest ? (
            <button
              type="button"
              className="login-secondary"
              data-testid="need-invite-toggle"
              onClick={() => setShowRequest(true)}
            >
              Need an invite?
            </button>
          ) : (
            <>
              <h2 className="login-request-title">Request access</h2>
              <p className="login-help">Ask the household admin for a join link, or send a request below.</p>
              <form
                onSubmit={async (event) => {
                  event.preventDefault();
                  setRequestBusy(true);
                  setRequestStatus(null);
                  try {
                    await createAccessRequest({
                      display_name: requestName.trim(),
                      email: requestEmail.trim() || undefined,
                      message: requestMessage.trim() || undefined,
                      organization_url: organizationUrl,
                    });
                    setRequestStatus({
                      type: "success",
                      message: "Request sent. The owner will see it in their inbox.",
                    });
                    setRequestName("");
                    setRequestEmail("");
                    setRequestMessage("");
                  } catch (err) {
                    setRequestStatus({
                      type: "error",
                      message: formatApiError(err) || "Could not send request.",
                    });
                  } finally {
                    setRequestBusy(false);
                  }
                }}
              >
                <label className="hp-field" aria-hidden="true">
                  Organization URL
                  <input
                    type="text"
                    name="organization_url"
                    tabIndex={-1}
                    autoComplete="off"
                    value={organizationUrl}
                    onChange={(e) => setOrganizationUrl(e.target.value)}
                    data-testid="access-request-honeypot"
                  />
                </label>
                <label className="login-field">
                  <span>Your name</span>
                  <input
                    type="text"
                    data-testid="access-request-name"
                    value={requestName}
                    onChange={(e) => setRequestName(e.target.value)}
                    placeholder="Name"
                    required
                    minLength={2}
                    disabled={requestBusy}
                  />
                </label>
                <label className="login-field">
                  <span>Email (optional)</span>
                  <input
                    type="email"
                    data-testid="access-request-email"
                    value={requestEmail}
                    onChange={(e) => setRequestEmail(e.target.value)}
                    placeholder="you@example.com"
                    disabled={requestBusy}
                  />
                </label>
                <label className="login-field">
                  <span>Note (optional)</span>
                  <textarea
                    data-testid="access-request-message"
                    value={requestMessage}
                    onChange={(e) => setRequestMessage(e.target.value)}
                    placeholder="How do you know this household?"
                    rows={2}
                    disabled={requestBusy}
                  />
                </label>
                {requestStatus ? (
                  <p
                    className={`status ${requestStatus.type === "error" ? "status-error" : "status-success"}`}
                    data-testid="access-request-status"
                  >
                    {requestStatus.message}
                  </p>
                ) : null}
                <button
                  type="submit"
                  className="login-secondary"
                  data-testid="access-request-submit"
                  disabled={requestBusy || requestName.trim().length < 2}
                >
                  {requestBusy ? "Sending…" : "Send request"}
                </button>
              </form>
            </>
          )}
        </div>
      ) : null}
    </GlassDoor>
  );
}
