import InlineAlert from "../../components/InlineAlert";

/**
 * Admin Household section — multi-user login toggles + user management.
 * Extracted from ConfigPage (H1/M8 incremental carve after LiveChannelsSection).
 */
export default function HouseholdSection({
  settings,
  featureFlags,
  persistSettings,
  updateFeatureFlags,
  updateAuthSettings,
  updateYouthSettings,
  managedUsers,
  usersLoading,
  actionAlert,
  setActionFeedback,
  handleUserRoleChange,
  handleUserDisableToggle,
  handleYouthModeToggle,
  handleUserRemove,
  handleUserSyncSeerr,
}) {
  return (
          <section className="config-section" data-testid="multi-user-settings">
            <h2>Household login (optional)</h2>
            <p className="wizard-note">
              When enabled, people open Projectionist via <strong>Sign in with Plex</strong> (plex.tv PIN / link
              on the login page). The first account becomes owner; later accounts join via an invite link
              from <strong>Admin → Access</strong> (invite-only by default). This is separate from the Plex{" "}
              <em>server</em> token above used for library sync.
            </p>
            <label className="config-toggle" data-testid="multi-user-enabled-toggle">
              <input
                type="checkbox"
                checked={Boolean(settings?.features?.multi_user_enabled)}
                onChange={(event) => {
                  const enabled = event.target.checked;
                  const nextAuthMode = enabled ? "plex" : "disabled";
                  updateFeatureFlags({ multi_user_enabled: enabled });
                  updateAuthSettings({ mode: nextAuthMode, plex_login_enabled: true });
                  persistSettings({
                    features: { ...(settings.features || {}), multi_user_enabled: enabled },
                    auth: {
                      ...(settings.auth || {}),
                      mode: nextAuthMode,
                      plex_login_enabled: true,
                    },
                  })
                    .then(() =>
                      setActionFeedback(
                        "multi-user",
                        "success",
                        enabled
                          ? "Household login enabled. Members use Sign in with Plex (PIN) on the login page."
                          : "Household login disabled.",
                      ),
                    )
                    .catch((error) => setActionFeedback("multi-user", "error", error.message));
                }}
              />
              <span>Require Plex sign-in for the app</span>
            </label>
            {settings?.features?.multi_user_enabled ? (
              <>
                <label className="config-toggle" data-testid="agent-may-mutate-personal-data-toggle">
                  <input
                    type="checkbox"
                    checked={Boolean(settings?.features?.agent_may_mutate_personal_data)}
                    onChange={(event) => {
                      const enabled = event.target.checked;
                      updateFeatureFlags({ agent_may_mutate_personal_data: enabled });
                      persistSettings({
                        features: {
                          ...(settings.features || {}),
                          agent_may_mutate_personal_data: enabled,
                        },
                      });
                    }}
                  />
                  <span>Agent may mutate personal data</span>
                </label>
                <p className="wizard-note">
                  When multi-user is on, chat tools that pin watchlist items, edit lists, save reviews, or
                  write memory stay off unless you enable this. *arr / Seerr / collections still require a
                  confirm token either way.
                </p>
              </>
            ) : null}
            {settings?.features?.multi_user_enabled ? (
              <>
                <label className="config-toggle" data-testid="invite-only-toggle">
                  <input
                    type="checkbox"
                    checked={settings?.features?.invite_only !== false}
                    onChange={(event) => {
                      const enabled = event.target.checked;
                      updateFeatureFlags({ invite_only: enabled });
                      persistSettings({
                        features: { ...(settings.features || {}), invite_only: enabled },
                      })
                        .then(() =>
                          setActionFeedback(
                            "invite-only",
                            "success",
                            enabled
                              ? "Invite-only join is on — new Plex/SSO users need a /join link."
                              : "Invite-only is off — new sign-ins can auto-provision (unless open auto-provision is also considered).",
                          ),
                        )
                        .catch((error) => setActionFeedback("invite-only", "error", error.message));
                    }}
                  />
                  <span>Require invite to join (recommended)</span>
                </label>
                <label className="config-toggle" data-testid="open-auto-provision-toggle">
                  <input
                    type="checkbox"
                    checked={Boolean(settings?.features?.open_auto_provision)}
                    onChange={(event) => {
                      const enabled = event.target.checked;
                      updateFeatureFlags({ open_auto_provision: enabled });
                      persistSettings({
                        features: { ...(settings.features || {}), open_auto_provision: enabled },
                      })
                        .then(() =>
                          setActionFeedback(
                            "open-auto-provision",
                            "success",
                            enabled
                              ? "Open auto-provision is on — anyone who can reach sign-in becomes a member (pre-1.26 LAN behavior)."
                              : "Open auto-provision is off — invite-only applies when Require invite is on.",
                          ),
                        )
                        .catch((error) =>
                          setActionFeedback("open-auto-provision", "error", error.message),
                        );
                    }}
                  />
                  <span>Open auto-provision (LAN-open; opt-in)</span>
                </label>
                <p className="wizard-note field-help">
                  Default is invite-only. Create links under <strong>Admin → Access</strong>. Turn on{" "}
                  <em>Open auto-provision</em> only if you want any reachable Plex/SSO identity to join
                  without an invite.
                </p>
                <div className="service-fields">
                  <label>
                    <span>Sign-in method</span>
                    <select
                      data-testid="auth-mode-select"
                      value={settings?.auth?.mode || "plex"}
                      onChange={(event) => {
                        const mode = event.target.value;
                        updateAuthSettings({ mode });
                        persistSettings({
                          auth: { ...(settings.auth || {}), mode },
                        }).catch((error) => setActionFeedback("multi-user", "error", error.message));
                      }}
                    >
                      <option value="plex">Plex (recommended)</option>
                      <option value="disabled">Off</option>
                      <option value="oidc" disabled>
                        Other providers (coming soon)
                      </option>
                      <option value="local" disabled>
                        Local accounts (coming soon)
                      </option>
                    </select>
                  </label>
                  <label className="config-toggle" data-testid="plex-login-enabled-toggle">
                    <input
                      type="checkbox"
                      checked={settings?.auth?.plex_login_enabled !== false}
                      onChange={(event) => {
                        const enabled = event.target.checked;
                        updateAuthSettings({ plex_login_enabled: enabled });
                        persistSettings({
                          auth: { ...(settings.auth || {}), plex_login_enabled: enabled },
                        }).catch((error) => setActionFeedback("multi-user", "error", error.message));
                      }}
                    />
                    <span>Allow Sign in with Plex (PIN)</span>
                  </label>
                  <p className="wizard-note field-help">
                    Household members sign in with Plex on the login page. New people join with an invite
                    link from Admin → Access.
                  </p>
                </div>
                {featureFlags?.user?.role === "owner" || !featureFlags?.features?.multi_user_enabled ? (
                  <div className="user-management" data-testid="user-management">
                    <h3>Household users</h3>
                    {usersLoading ? <p className="wizard-note">Loading users…</p> : null}
                    {!usersLoading && managedUsers.length === 0 ? (
                      <p className="wizard-note" data-testid="users-empty-state">
                        Household members appear after Sign in with Plex
                      </p>
                    ) : null}
                    {managedUsers.length ? (
                      <div className="user-management-table-wrap">
                        <table className="user-management-table" data-testid="users-table">
                          <thead>
                            <tr>
                              <th scope="col">Name</th>
                              <th scope="col">Email</th>
                              <th scope="col">Role</th>
                              <th scope="col">Youth mode</th>
                              <th scope="col">Seerr</th>
                              <th scope="col">Status</th>
                              <th scope="col">Actions</th>
                            </tr>
                          </thead>
                          <tbody>
                            {managedUsers.map((entry) => {
                              const isSelf = entry.id === featureFlags?.user?.id;
                              const seerrLinked = Boolean(entry.seerr_linked ?? entry.seerr_user_id);
                              return (
                                <tr
                                  key={entry.id}
                                  className={entry.disabled ? "user-row-disabled" : undefined}
                                  data-testid={`user-row-${entry.id}`}
                                >
                                  <td>
                                    <strong>{entry.display_name || "—"}</strong>
                                  </td>
                                  <td>{entry.email || "—"}</td>
                                  <td>
                                    <select
                                      aria-label={`Role for ${entry.display_name || entry.id}`}
                                      value={entry.role}
                                      disabled={isSelf && entry.role === "owner"}
                                      onChange={(event) =>
                                        handleUserRoleChange(entry.id, event.target.value)
                                      }
                                    >
                                      <option value="owner">Owner</option>
                                      <option value="member">Member</option>
                                    </select>
                                  </td>
                                  <td>
                                    <button
                                      type="button"
                                      className="ghost"
                                      data-testid={`user-youth-mode-${entry.id}`}
                                      disabled={isSelf}
                                      onClick={() => handleYouthModeToggle(entry)}
                                    >
                                      {entry.is_youth ? "Youth mode on" : "Set Youth mode"}
                                    </button>
                                  </td>
                                  <td>
                                    {seerrLinked ? (
                                      <span className="user-status-pill linked">
                                        Linked{entry.seerr_user_id ? ` #${entry.seerr_user_id}` : ""}
                                      </span>
                                    ) : (
                                      <span className="user-status-pill">Not linked</span>
                                    )}
                                  </td>
                                  <td>
                                    <span
                                      className={`user-status-pill ${entry.disabled ? "disabled" : "active"}`}
                                    >
                                      {entry.disabled ? "Disabled" : "Active"}
                                    </span>
                                  </td>
                                  <td>
                                    <div className="user-management-actions">
                                      <button
                                        type="button"
                                        className="ghost"
                                        data-testid={`user-disable-${entry.id}`}
                                        disabled={isSelf}
                                        onClick={() => handleUserDisableToggle(entry)}
                                      >
                                        {entry.disabled ? "Enable" : "Disable"}
                                      </button>
                                      <button
                                        type="button"
                                        className="ghost"
                                        data-testid={`user-sync-seerr-${entry.id}`}
                                        onClick={() => handleUserSyncSeerr(entry)}
                                      >
                                        Sync Seerr
                                      </button>
                                      <button
                                        type="button"
                                        className="ghost danger"
                                        data-testid={`user-remove-${entry.id}`}
                                        disabled={isSelf}
                                        onClick={() => handleUserRemove(entry)}
                                      >
                                        Remove
                                      </button>
                                    </div>
                                  </td>
                                </tr>
                              );
                            })}
                          </tbody>
                        </table>
                      </div>
                    ) : null}
                    {actionAlert?.area === "users" || actionAlert?.area === "multi-user" ? (
                      <InlineAlert
                        type={actionAlert.type}
                        message={actionAlert.message}
                        testId="multi-user-alert"
                      />
                    ) : null}
                  </div>
                ) : (
                  <p className="wizard-note">Sign in as owner to manage household users.</p>
                )}
                <label className="config-field" data-testid="youth-max-rating-field">
                  <span>Youth max content rating</span>
                  <select
                    value={settings?.youth?.max_content_rating || "PG-13"}
                    onChange={(event) => {
                      const max_content_rating = event.target.value;
                      updateYouthSettings({ max_content_rating });
                      persistSettings({
                        youth: { ...(settings.youth || {}), max_content_rating },
                      })
                        .then(() =>
                          setActionFeedback(
                            "users",
                            "success",
                            `Youth max rating set to ${max_content_rating}. Unrated titles stay hidden.`,
                          ),
                        )
                        .catch((error) => setActionFeedback("users", "error", error.message));
                    }}
                    data-testid="youth-max-rating"
                  >
                    {["G", "PG", "PG-13", "R", "TV-Y", "TV-Y7", "TV-G", "TV-PG", "TV-14"].map((rating) => (
                      <option key={rating} value={rating}>
                        {rating}
                      </option>
                    ))}
                  </select>
                  <span className="wizard-note">
                    Youth-mode accounts never see empty ratings or anything above this max (fail-closed).
                  </span>
                </label>
              </>
            ) : null}
          </section>

  );
}
