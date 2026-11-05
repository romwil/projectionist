/** /join copy (GRO-009): say how this invite signs in, and never mention Plex when Plex is off. */

export type JoinMethods = { plex: boolean; oidc: boolean; local: boolean };

export function joinMethods(installMethods: string[], inviteMethods: string[] | undefined): JoinMethods {
  const allowed = inviteMethods || [];
  const on = (id: string) => installMethods.includes(id) && allowed.includes(id);
  return { plex: on("plex"), oidc: on("oidc"), local: on("local") };
}

/** Only a username and password: open the form right away instead of a "fallback" toggle. */
export function isLocalOnlyJoin(methods: JoinMethods): boolean {
  return methods.local && !methods.plex && !methods.oidc;
}

export function joinLede({
  loading,
  hasInvite,
  methods,
}: {
  loading: boolean;
  hasInvite: boolean;
  methods: JoinMethods;
}): string {
  if (loading) return "Checking invite…";
  if (!hasInvite) return "This invite is not available.";
  if (methods.plex) {
    return methods.local
      ? "Sign in with Plex to join. Username and password is a fallback on the same link."
      : "Sign in with Plex to join.";
  }
  if (methods.oidc) {
    return methods.local
      ? "Continue with your household sign-in, or choose a username and password."
      : "Continue with your household sign-in to join.";
  }
  if (methods.local) return "Choose a username and password to join.";
  return "This invite has no sign-in method turned on. Ask the person who invited you.";
}
