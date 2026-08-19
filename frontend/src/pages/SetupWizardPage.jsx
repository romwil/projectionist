import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  formatApiError,
  getFeatures,
  getSetupHandshake,
  commitSetup,
  testPlex,
  testTmdb,
} from "../api/client";
import GlassDoor from "../components/GlassDoor";
import InlineAlert from "../components/InlineAlert";
import {
  setupCommitHouseholdDomain,
  setupCommitInviteOnly,
  setupCommitTrustProxy,
  setupInviteOnlyDefault,
} from "../lib/setupWizard";

export default function SetupWizardPage() {
  const navigate = useNavigate();
  const [step, setStep] = useState(1);
  const [handshake, setHandshake] = useState(null);
  const [error, setError] = useState("");
  const [profile, setProfile] = useState("private");
  const [trustProxy, setTrustProxy] = useState(false);
  const [domain, setDomain] = useState("");
  const [inviteOnly, setInviteOnly] = useState(setupInviteOnlyDefault("private"));
  const [accessRequests, setAccessRequests] = useState(true);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [plexCheck, setPlexCheck] = useState(null);
  const [tmdbCheck, setTmdbCheck] = useState(null);
  const [busy, setBusy] = useState(false);
  const [recoveryKey, setRecoveryKey] = useState("");

  useEffect(() => {
    getFeatures()
      .then((feat) => {
        if (feat?.setup_state === "active") {
          navigate("/login", { replace: true });
          return;
        }
        return getSetupHandshake();
      })
      .then((data) => {
        if (!data) return;
        setHandshake(data);
        const pre = data.preselect_profile === "public" ? "public" : "private";
        setProfile(pre);
        setInviteOnly(setupInviteOnlyDefault(pre));
        if (pre === "public") {
          setAccessRequests(true);
          setTrustProxy(Boolean(data.trusted_proxy));
        }
      })
      .catch((err) => setError(formatApiError(err)));
  }, [navigate]);

  const halt = Boolean(handshake?.halt);
  const snapshot = handshake?.snapshot || {};

  async function runChecks() {
    setPlexCheck({ pending: true });
    setTmdbCheck({ pending: true });
    try {
      const plex = await testPlex({});
      setPlexCheck(plex);
    } catch (err) {
      setPlexCheck({ ok: false, message: formatApiError(err) });
    }
    try {
      const tmdb = await testTmdb({});
      setTmdbCheck(tmdb);
    } catch (err) {
      setTmdbCheck({ ok: false, message: formatApiError(err) });
    }
  }

  async function handleCommit(event) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const result = await commitSetup({
        profile,
        username: username.trim(),
        password,
        household_domain: setupCommitHouseholdDomain(profile, domain),
        trust_proxy: setupCommitTrustProxy(profile, trustProxy),
        allow_access_requests: accessRequests,
        invite_only: setupCommitInviteOnly(profile, inviteOnly),
      });
      setRecoveryKey(result.recovery_key || "");
    } catch (err) {
      setError(formatApiError(err) || "Could not finish setup.");
    } finally {
      setBusy(false);
    }
  }

  if (recoveryKey) {
    return (
      <GlassDoor
        testId="setup-wizard"
        eyebrow="Projectionist Setup"
        title="Household locked"
        lede="Save this recovery key. It is shown once."
      >
        <p className="login-help" data-testid="setup-recovery-key">
          {recoveryKey}
        </p>
        <p className="login-help">
          {profile === "public"
            ? "Public Household: invite-only join, multi-user on, registration off."
            : "Private Household: you can invite members later from Admin."}
        </p>
        <button type="button" className="login-primary" data-testid="setup-enter" onClick={() => navigate("/chat")}>
          Enter Projectionist
        </button>
      </GlassDoor>
    );
  }

  return (
    <GlassDoor
      testId="setup-wizard"
      halt={halt}
      eyebrow="Projectionist Setup"
      title={halt ? "Direct public exposure" : "Set up this household"}
      lede={handshake?.message || "Profiling how this instance is reached…"}
    >
      {error ? <InlineAlert type="error" message={error} /> : null}
      {halt ? (
        <p className="login-help" data-testid="setup-halt">
          Complete initial setup from your local network or a trusted tunnel — not from a raw public :8788 bind.
        </p>
      ) : (
        <>
          <p className="glass-door-steps" data-testid="setup-steps">
            <span aria-current={step === 1 ? "step" : undefined}>1 Environment</span>
            <span aria-current={step === 2 ? "step" : undefined}>2 Connections</span>
            <span aria-current={step === 3 ? "step" : undefined}>3 Owner</span>
          </p>

          {step === 1 ? (
            <div className="glass-door-cards">
              <button
                type="button"
                className={`glass-door-choice${profile === "private" ? " is-selected" : ""}`}
                aria-pressed={profile === "private"}
                data-testid="setup-profile-private"
                onClick={() => {
                  setProfile("private");
                  setInviteOnly(setupInviteOnlyDefault("private"));
                  setTrustProxy(false);
                  setDomain("");
                }}
              >
                <h2>Private Household</h2>
                <p>LAN, Tailscale, or a private VPN. Multi-user is optional. Invite-only stays off unless you opt in.</p>
              </button>
              <button
                type="button"
                className={`glass-door-choice${profile === "public" ? " is-selected" : ""}`}
                aria-pressed={profile === "public"}
                data-testid="setup-profile-public"
                onClick={() => {
                  setProfile("public");
                  setInviteOnly(setupInviteOnlyDefault("public"));
                  setAccessRequests(true);
                }}
              >
                <h2>Public Household</h2>
                <p>
                  Custom domain or Cloudflare Tunnel. Multi-user and invite-only are required. No anonymous owner.
                </p>
              </button>
              {profile === "public" ? (
                <>
                  <label className="login-field">
                    <span>Household domain</span>
                    <input
                      data-testid="setup-domain"
                      value={domain}
                      onChange={(e) => setDomain(e.target.value)}
                      placeholder="movies.example.com"
                    />
                  </label>
                  <label className="login-field">
                    <input
                      type="checkbox"
                      data-testid="setup-trust-proxy"
                      checked={trustProxy}
                      onChange={(e) => setTrustProxy(e.target.checked)}
                    />{" "}
                    This edge is my TLS proxy
                  </label>
                </>
              ) : (
                <label className="login-field">
                  <input
                    type="checkbox"
                    data-testid="setup-invite-only"
                    checked={inviteOnly}
                    onChange={(e) => setInviteOnly(e.target.checked)}
                  />{" "}
                  Require invite links for new members
                </label>
              )}
              <label className="login-field">
                <input
                  type="checkbox"
                  data-testid="setup-access-requests"
                  checked={accessRequests}
                  onChange={(e) => setAccessRequests(e.target.checked)}
                />{" "}
                Allow household members to request access
              </label>
              <details className="glass-door-advanced" data-testid="setup-advanced">
                <summary>Advanced network & topology</summary>
                <p className="login-help">
                  Bind {snapshot.bind_host}:{snapshot.bind_port} · peer class {handshake?.peer_class || "unknown"} ·
                  classification {handshake?.classification}
                </p>
                <p className="login-help">
                  Forwarded proto {snapshot.forwarded_proto_present ? "present" : "absent"}, forwarded-for{" "}
                  {snapshot.forwarded_for_present ? "present" : "absent"}, trusted proxy{" "}
                  {snapshot.trusted_proxy_mode ? "on" : "off"}.
                </p>
              </details>
              <button type="button" className="login-primary" data-testid="setup-step1-next" onClick={() => setStep(2)}>
                Continue
              </button>
            </div>
          ) : null}

          {step === 2 ? (
            <div className="login-form">
              <p className="login-help">Connection checks are optional. You can continue with warnings.</p>
              <button type="button" className="login-secondary" data-testid="setup-run-checks" onClick={runChecks}>
                Check Plex and TMDB
              </button>
              {plexCheck ? (
                <p className="login-help" data-testid="setup-plex-check">
                  Plex: {plexCheck.pending ? "checking…" : plexCheck.ok ? plexCheck.message || "ok" : plexCheck.message || "not configured"}
                </p>
              ) : null}
              {tmdbCheck ? (
                <p className="login-help" data-testid="setup-tmdb-check">
                  TMDB: {tmdbCheck.pending ? "checking…" : tmdbCheck.ok ? tmdbCheck.message || "ok" : tmdbCheck.message || "not configured"}
                </p>
              ) : null}
              {profile === "public" && (handshake?.trusted_proxy || trustProxy) ? (
                <p className="login-help" data-testid="setup-tls-verified">
                  TLS edge proxy {handshake?.trusted_proxy ? "verified" : "will be trusted after you confirm"}.
                </p>
              ) : null}
              <button type="button" className="login-secondary" onClick={() => setStep(1)}>
                Back
              </button>
              <button type="button" className="login-primary" data-testid="setup-step2-next" onClick={() => setStep(3)}>
                Continue
              </button>
            </div>
          ) : null}

          {step === 3 ? (
            <form className="login-form" onSubmit={handleCommit} data-testid="setup-commit-form">
              <p className="login-help">
                Profile: <strong>{profile === "public" ? "Public Household" : "Private Household"}</strong>
                {profile === "public" ? " · invite-only · multi-user" : inviteOnly ? " · invite-only" : ""}
              </p>
              <label className="login-field">
                <span>Owner username</span>
                <input
                  data-testid="setup-username"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  minLength={2}
                  required
                  autoComplete="username"
                />
              </label>
              <label className="login-field">
                <span>Owner password</span>
                <input
                  type="password"
                  data-testid="setup-password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  minLength={8}
                  required
                  autoComplete="new-password"
                />
              </label>
              <button type="button" className="login-secondary" onClick={() => setStep(2)}>
                Back
              </button>
              <button type="submit" className="login-primary" data-testid="setup-commit" disabled={busy}>
                {busy ? "Locking household…" : "Create owner and lock"}
              </button>
            </form>
          ) : null}
        </>
      )}
    </GlassDoor>
  );
}
