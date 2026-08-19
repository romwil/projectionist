/**
 * Setup-wizard invite-only / trust-proxy posture.
 *
 * Public Household: invite-only is mandatory; TLS-edge trust-proxy is an
 * explicit operator choice (handshake preselect or checkbox).
 * Private Household: invite-only off unless opted in; never persist a leftover
 * public trust-proxy / household domain from handshake or a prior Public click.
 */

export function setupInviteOnlyDefault(profile) {
  return profile === "public";
}

export function setupCommitInviteOnly(profile, inviteOnly) {
  if (profile === "public") return true;
  return Boolean(inviteOnly);
}

export function setupCommitTrustProxy(profile, trustProxy) {
  if (profile === "public") return Boolean(trustProxy);
  return false;
}

export function setupCommitHouseholdDomain(profile, domain) {
  if (profile === "public") return String(domain || "").trim();
  return "";
}
