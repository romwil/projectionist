# Interactive UI QA — authored checklist

Inventory for `full` and `delta` modes. **Agents execute these IDs only.**
When UI ships, add/edit IDs here in the same change.

Each ID:

| Field | Meaning |
|-------|---------|
| **roles** | Who must run this ID (`member`, `owner`, `youth`, `guest`, `guest-tour`, or `*`) |
| **tags** | Delta selection keys (`gating`, `nav`, `scroll`, `theme`, `journey`, `chat`, `explore`, `search`, `inbox`, `notifications`, `recommend`, `settings`, `admin`, `shell`, `login`, `tour`, `invite`, `access-request`, `persona`, `library`, `youth`, `save`, `export`, `lists`, `watchlist`) |
| **source** | Primary frontend file(s) |
| **steps** | Required interactions (page-load alone ≠ pass) |
| **pass** | Observable pass criteria |

Target: `http://10.10.1.202:8790`. Creds: `projectionist-qa-scripts/.env.qa`.

---

## Shared / login

### `login.local-form`

- **roles:** `*` (run once per signed-in role campaign before gated IDs)
- **tags:** `login`, `gating`
- **source:** `frontend/src/pages/LoginPage.jsx`, `frontend/src/lib/loginScreen.js`
- **steps:** Open `/login`. Confirm local Username + Password fields (`data-testid="local-username"`, `local-password`) are visible **before** submit. Sign in with the role’s `QA_*` creds.
- **pass:** Fields visible pre-submit; successful submit lands on chat (`/chat` or `/`); no silent blank form.

### `login.glass-door`

- **roles:** `*` (logged-out)
- **tags:** `login`, `gating`
- **source:** `frontend/src/pages/LoginPage.jsx`, `frontend/src/components/GlassDoor.jsx`
- **steps:** Open `/login` logged out. Confirm `data-testid="login-page"` glass-door chrome (wordmark / Sign in). Confirm **Sign in with Plex** (`sign-in-with-plex`) and/or local form. Confirm **Need an invite?** (`need-invite-toggle`) when access requests are on. Confirm no signup card and no raw Plex token paste.
- **pass:** Cinematic gate renders; Plex and/or password paths present; no register / token-paste / tour CTA.

### `login.honeypot-hidden`

- **roles:** `*` (logged-out)
- **tags:** `login`
- **source:** `frontend/src/pages/LoginPage.jsx`
- **steps:** On `/login`, expand **Need an invite?** (`need-invite-toggle`). Inspect `data-testid="access-request-honeypot"` (`name="organization_url"`).
- **pass:** Field exists in the DOM, is not visible (`display: none` / `.hp-field`), `aria-hidden="true"`, and is skipped in tab order (`tabIndex=-1`). Do not submit a filled honeypot against prod.

### `login.no-tour`

- **roles:** `*` (logged-out)
- **tags:** `login`, `tour`
- **source:** `frontend/src/pages/LoginPage.jsx`, `frontend/src/main.jsx`
- **steps:** On `/login`, confirm `login-take-tour` is absent. Navigate to `/tour`.
- **pass:** No Take a Tour CTA. `/tour` redirects to `/login`. FAIL if a public tour shell renders.

### `join.glass-door`

- **roles:** `*` (logged-out)
- **tags:** `login`, `gating`
- **source:** `frontend/src/pages/JoinPage.jsx`
- **steps:** Open `/join` without a token (do **not** redeem a live invite). Confirm `data-testid="join-page"` glass-door copy (“You’re invited” / Join this household).
- **pass:** Join gate renders with invite-specific copy; missing/invalid token does not create a user. Do not burn a real household invite.

### `setup.skip-when-active`

- **roles:** `owner` (QA sidecar already provisioned)
- **tags:** `login`, `gating`, `admin`
- **source:** `frontend/src/pages/SetupWizardPage.jsx`
- **steps:** Open `/setup` on QA. If `setup_state` is `active`, confirm redirect to `/login` or chat. Do **not** submit `setup-commit`.
- **pass:** Wizard does not re-open; no recovery-key screen; no new owner. If handshake `setup-steps` is visible, record N/A and stop — do not commit.

### `settings.link-plex`

- **roles:** `member`, `owner` (local-password user without `plex_user_id`)
- **tags:** `settings`, `login`
- **source:** `frontend/src/pages/settings/ProfilePage.jsx`
- **steps:** Open **Settings**. If `settings-link-plex` is present, confirm **Link Plex** (`link-plex-start`) and that waiting copy says poll does not attach. Do **not** complete a live Plex bind unless a disposable QA local user exists.
- **pass:** Panel present for unlinked local users **or** `settings-plex-linked` for already-linked accounts (note which). Password confirm (`link-plex-password`) is required before bind. N/A if the role is already Plex-native.

### `login.take-tour-link`

- **roles:** `guest-tour` (legacy; tour is removed)
- **tags:** `login`, `tour`
- **source:** `frontend/src/pages/LoginPage.jsx`
- **steps:** On `/login`, look for `data-testid="login-take-tour"`. Navigate to `/tour`.
- **pass:** Link absent; `/tour` redirects to `/login`. Same as `login.no-tour`.

### `login.access-request-submit`

- **roles:** `*` (logged-out)
- **tags:** `login`, `access-request`
- **source:** `frontend/src/pages/LoginPage.jsx`
- **steps:** On `/login`, expand **Need an invite?** (`need-invite-toggle`). Leave the honeypot empty. Fill `access-request-name` with a disposable QA marker (e.g. `QA UI request`). Optionally add a short `access-request-message`. Submit `access-request-submit`. Do **not** fill `access-request-honeypot`.
- **pass:** `access-request-status` shows success copy. Session stays logged out (still on `/login`). Does not mint a join token by itself.

### `invite.owner-mint`

- **roles:** `owner`
- **tags:** `invite`, `admin`, `login`, `gating`
- **source:** `frontend/src/pages/AccessRequestsPage.jsx`
- **steps:** Sign in as owner. Open **Admin → Access** (`/admin/access`, `access-requests-page`). On `access-create-invite`, leave role **Member**, leave Youth off, skip email. Submit `invite-create-submit`. Read `access-join-link-input` (copy via `access-join-link-copy` is optional). Confirm a pending row appears in `invite-list`.
- **pass:** Feedback reports invite created (not emailed unless Mail is configured). Join link contains `/join?token=` with a non-empty token. Pending list shows the new invite. Use this token only for `join.redeem-token-ui` on QA; do not share off-LAN.

### `join.redeem-token-ui`

- **roles:** `*` (logged-out)
- **tags:** `invite`, `login`, `gating`
- **source:** `frontend/src/pages/JoinPage.jsx`
- **steps:** After `invite.owner-mint`, sign out. Open the minted `/join?token=…` URL. Confirm `join-page` glass-door and `join-invite-summary` (household member, one-time). If local is allowed, click `join-local-toggle` and confirm `join-username` / `join-password` / `join-local-submit` appear. Do **not** submit `join-local-submit` and do **not** complete a live Plex bind (avoid extra QA users). Then open `/join?token=not-a-real-token` and confirm `join-error`.
- **pass:** Valid token shows invite chrome + method controls without creating a user. Invalid token shows `join-error` and no `join-local-form`. Revoke leftover pending invite via `invite.revoke`.

### `invite.revoke`

- **roles:** `owner`
- **tags:** `invite`, `admin`
- **source:** `frontend/src/pages/AccessRequestsPage.jsx`
- **steps:** After `join.redeem-token-ui`, sign in as owner on `/admin/access`. Click **Revoke** (`invite-revoke-*`) on the pending QA invite from `invite.owner-mint`.
- **pass:** Feedback reports revoked; the invite leaves the pending `invite-list` (or the row is gone after reload).

### `invite.access-queue`

- **roles:** `owner`
- **tags:** `invite`, `admin`, `access-request`
- **source:** `frontend/src/pages/AccessRequestsPage.jsx`
- **steps:** As owner on `/admin/access`, inspect **Access requests** (`access-request-list`). If `login.access-request-submit` ran this campaign, find that pending row. Approve is optional (creates a join invite — prefer **Deny** `access-deny-*` to clean up QA). If the queue is empty, `access-requests-empty` is PASS.
- **pass:** Queue renders without crash. Pending QA request visible when submitted this run, or honest empty copy. Do not leave an approved live invite hanging.

---

## Member

Nav peers for member (`primaryNavVisibleIds`): Search, Chat, Explore, Inbox, My Journey, Settings — **no Admin**.

Topbar and hamburger drawer share one model (`primaryNav.js`): whatever peers a role sees as topbar icons must also appear as labelled links in the drawer's **Navigate** block. A peer in one surface and missing from the other is a failure, not a cosmetic gap.

### `nav.peers-member`

- **roles:** `member`
- **tags:** `nav`, `gating`
- **source:** `frontend/src/lib/primaryNav.js`, `frontend/src/components/PrimaryTopbar.jsx`
- **steps:** After auth settles on `/explore` or `/chat`, inspect primary topbar icons.
- **pass:** Present: `topbar-search-link`, `topbar-chat-link`, `topbar-explore-link`, inbox, `topbar-my-journey-link`, `topbar-settings-link`. Absent: `topbar-admin-link`. Labels are Search / Chat / Explore (not Ask/Browse).

### `nav.no-admin`

- **roles:** `member`, `youth`
- **tags:** `gating`, `nav`
- **source:** `frontend/src/layouts/AppShell.jsx`, `frontend/src/components/PrimaryTopbar.jsx`, `frontend/src/components/UserMenu.jsx` (`useAuthGate`)
- **steps:** Hard-navigate to `/explore` as member/youth. Watch topbar **during load and after settle** (≥2s + network idle). Screenshot mid-load if flash suspected.
- **pass:** `topbar-admin-link` never appears (no Admin flash). Settled chrome matches role.

### `nav.admin-redirect`

- **roles:** `member`, `youth`, `guest`
- **tags:** `gating`, `admin`
- **source:** `frontend/src/layouts/AdminLayout.jsx`
- **steps:** Navigate to `/admin` (and `/admin/overview` if needed).
- **pass:** Redirected to `/settings` (or login if unauthenticated). Admin shell (`admin-layout`) does not remain usable.

### `nav.drawer-member`

- **roles:** `member`
- **tags:** `nav`
- **source:** `frontend/src/components/AppNav.jsx`, `frontend/src/lib/appNavItems.js`, `frontend/src/lib/primaryNav.js`
- **steps:** Open hamburger (`app-nav-toggle`). Scan drawer links under each heading.
- **pass:** Drawer opens with a **Navigate** heading (`app-nav-heading-navigate`) whose block carries **every primary peer this role sees in the topbar**, labelled: `app-nav-search`, `app-nav-chat`, `app-nav-explore`, `app-nav-inbox`, `app-nav-my-journey`, `app-nav-settings`. Then a **More** heading (`app-nav-heading-more`) with Plot Lab, Tags, Watchlist, Library, Help, Privacy, About. My Journey appears **once** (Navigate only). No `app-nav-admin` and no `app-nav-admin-*`. Close works.

### `chat.starter-or-send`

- **roles:** `member`, `owner`, `youth`, `guest`
- **tags:** `chat`
- **source:** `frontend/src/components/WelcomePanel.jsx`, `frontend/src/App.jsx`
- **steps:** On `/chat`, either click a welcome starter chip **or** type a short message in `composer-input` and send.
- **pass:** A user message appears in the transcript **or** a starter populates/sends. Not merely “page loaded”.

### `chat.mood-or-surprise`

- **roles:** `member`, `owner`, `youth`, `guest`
- **tags:** `chat`
- **source:** `frontend/src/App.jsx`, `frontend/src/lib/quickPick.js`, `frontend/src/hooks/useChatScroll.js`
- **steps:** On `/chat`, click a mood chip (`surprise-mood-*`) **or** `surprise-me-button`. Wait for the new assistant pick.
- **pass:** New pick/message appears; viewport scrolls so the new pick is in view (not stuck at top with pick off-screen).

### `chat.poster-scroll`

- **roles:** `member`, `owner`, `youth`, `guest`
- **tags:** `chat`, `scroll`
- **source:** `frontend/src/styles/02-nav-chrome.css`, `frontend/src/lib/chatLayout.js`, `frontend/src/lib/chatCardScroll.js`
- **steps:** Produce or open a completed recommendation/poster strip in chat. Attempt horizontal scroll on the strip; inspect for nested vertical scrollbar on the strip container.
- **pass:** Horizontal scroll works; strip does **not** show its own nested vertical scrollbar (page/transcript may scroll vertically).

### `explore.open-card`

- **roles:** `member`, `owner`, `youth`, `guest`
- **tags:** `explore`
- **source:** `frontend/src/pages/ExplorePage.jsx`
- **steps:** Open `/explore`. Open one rail card / poster action (title detail or overlay).
- **pass:** Card interaction opens detail, menu, or navigates; not a dead click. If library empty, record empty-state CTA visibility instead of FAIL only when owner CTA expected.

### `explore.chat-about-these`

- **roles:** `member`, `owner`, `youth`, `guest`
- **tags:** `explore`, `chat`
- **source:** `frontend/src/pages/ExplorePage.jsx` (`FeedRail` / `Chat about these`)
- **steps:** On a populated explore rail, click a `*-chat` “Chat about these” link when present.
- **pass:** Navigates into chat with rail context **or** link absent because rail empty (note N/A — not FAIL).

### `explore.hub-links`

- **roles:** `member`, `owner`, `youth`
- **tags:** `explore`, `nav`
- **source:** `frontend/src/pages/ExplorePage.jsx`
- **steps:** From `/explore`, click Browse Movies or Browse TV hub card.
- **pass:** Lands on library browse with expected media type; results or empty state render.

### `search.query`

- **roles:** `member`, `owner`, `youth`, `guest`
- **tags:** `search`
- **source:** `frontend/src/pages/ExplorePage.jsx`, `frontend/src/pages/SearchPage.jsx` → `LibraryBrowsePage.jsx`, `frontend/src/lib/browseLinks.js`, `frontend/src/lib/progressiveBrowseSearch.js`
- **steps:** Open `/search` via topbar Search (or Explore `explore-search-input` + submit). On Search, use the on-page bar (`library-browse-search-input`) with a known title fragment — progressive as-you-type is enough; submit optional.
- **pass:** URL becomes `/search?q=…` (or equivalent); `library-browse-title` / results / empty reflect that `q`. Emptying the input restores full browse (no `q`, “Browse library” / full grid).

### `search.progressive`

- **roles:** `member`, `owner`, `youth`, `guest`
- **tags:** `search`
- **source:** `frontend/src/pages/LibraryBrowsePage.jsx`, `frontend/src/lib/progressiveBrowseSearch.js`
- **steps:** On `/search` with a populated library, type a title fragment into `library-browse-search-input` without pressing Search/Enter. Wait briefly (~200ms debounce). Clear the input.
- **pass:** While typing, results update without requiring Enter (`q` in URL, grid/empty/heading follow). Clearing restores full browse. Filters/sort still apply with an active `q`.

### `inbox.empty-or-item`

- **roles:** `member`, `owner`, `youth`
- **tags:** `inbox`
- **source:** `frontend/src/pages/InboxPage.jsx`, `frontend/src/components/RecommendationsInbox.jsx`
- **steps:** Open `/inbox` via topbar. If empty, follow empty CTA to Chat or Explore. If items exist, open or dismiss one card.
- **pass:** Empty state (`inbox-empty`) with usable CTA **or** recommendation card actions work. No crash.

### `inbox.empty-state`

- **roles:** `member`, `owner`, `youth`
- **tags:** `inbox`
- **source:** `frontend/src/pages/InboxPage.jsx`
- **steps:** Open `/inbox` when there are no notifications (or after dismissing all). Inspect `inbox-empty`.
- **pass:** Empty copy visible with working links to Chat and Explore. If the inbox is populated and cannot be cleared without destroying QA data, note N/A and rely on `inbox.card-actions` instead — not FAIL.

### `inbox.badge`

- **roles:** `member`, `owner`, `youth`
- **tags:** `inbox`, `nav`
- **source:** `frontend/src/components/InboxBadgeButton.jsx`, `frontend/src/lib/recommendationInbox.js`
- **steps:** On any topbar page, inspect `topbar-inbox-button`. If `unread_count > 0`, confirm `topbar-inbox-badge` shows the count (or `99+`). Click the inbox control.
- **pass:** Inbox peer present; badge matches unread when >0 (absent when 0 is OK). Click lands on `/inbox` (`inbox-page`).

### `inbox.card-actions`

- **roles:** `member`, `owner`, `youth`
- **tags:** `inbox`
- **source:** `frontend/src/components/RecommendationsInbox.jsx`, `frontend/src/pages/InboxPage.jsx`
- **steps:** With at least one notification present (`recommendations-inbox`), identify card `data-kind` (recommendation / arrival / digest / access-request / nudge). Dismiss one card via `recommendation-dismiss-*` **or** open via primary CTA (`recommendation-open-*`, `recommendation-review-access-*`, `recommendation-open-live-*`, or digest pick `recommendation-pick-*`).
- **pass:** Card removes from stack (or navigates after open). No crash. If inbox empty, N/A (use `inbox.empty-state`). Multi-kind: when several kinds are present, note each `data-kind` observed; a single kind is still PASS.

### `inbox.card-layout`

- **roles:** `member`, `owner`, `youth`
- **tags:** `inbox`, `layout`
- **source:** `frontend/src/components/RecommendationsInbox.jsx`, `frontend/src/styles/08-dashboard-coverage-cards.css`
- **steps:** Open `/inbox` with at least one card. Prefer a mix that includes a **text-only** kind (digest without picks / access-request / live nudge → `recommendation-card--text-only`) and a poster kind (recommendation / arrival / enthusiast nudge). At desktop width, inspect card geometry. Digests should show `recommendation-blurb-*` + optional `recommendation-pick-strip-*`, **not** the full email body as the main surface (`recommendation-curator-note-*` disclosure is OK).
- **pass:** Every card spans the inbox reading column (not a ~64px strip). Lead/blurb wraps as normal lines — **not** character-by-character vertically. Huge empty vertical gaps from collapsed columns are FAIL. If inbox empty, N/A.

### `inbox.dismiss-all`

- **roles:** `member`, `owner`, `youth`
- **tags:** `inbox`
- **source:** `frontend/src/components/RecommendationsInbox.jsx`, `frontend/src/pages/InboxPage.jsx`, `frontend/src/lib/recommendationInbox.js`
- **steps:** With **two or more** cards, click `recommendations-dismiss-all`. Confirm stack clears. Reload `/inbox` (or leave and reopen via `topbar-inbox-button`).
- **pass:** Stack clears to empty state (or loading then empty). After reload, dismissed items stay gone (`inbox-empty` or fewer cards) — dismiss must stick because list uses unread-only (`INBOX_LIST_PARAMS.unread_only`). Button absent with <2 cards → N/A.

### `inbox.digest-picks`

- **roles:** `member`, `owner`, `youth`
- **tags:** `inbox`, `digest`
- **source:** `frontend/src/components/RecommendationsInbox.jsx`
- **steps:** When a `data-kind="digest"` card is present with `recommendation-pick-strip-*`, open one pick (`recommendation-pick-*-N`) **or** primary `recommendation-open-*` (“Open picks”). Optionally expand `recommendation-curator-note-*`.
- **pass:** Dig-in opens title detail (or overlay); full body stays behind disclosure by default. No pick strip + empty picks → short lead + Dismiss only is PASS. No digest card → N/A.

### `inbox.access-review-cta`

- **roles:** `owner`
- **tags:** `inbox`, `access`
- **source:** `frontend/src/components/RecommendationsInbox.jsx`
- **steps:** With an `access-request` card, click `recommendation-review-access-*`.
- **pass:** Navigates to `/admin/access`. Member role: CTA absent (Dismiss only) is PASS. No access-request card → N/A.

### `inbox.live-nudge-cta`

- **roles:** `member`, `owner`
- **tags:** `inbox`, `live`
- **source:** `frontend/src/components/RecommendationsInbox.jsx`
- **steps:** With a Live Channels ready nudge (`data-kind="nudge"` + Open Live), click `recommendation-open-live-*`.
- **pass:** Navigates to `/live`. No live nudge → N/A.

### `recommend.open-modal`

- **roles:** `member`, `owner`
- **tags:** `recommend`
- **source:** `frontend/src/components/RecommendModal.jsx`, `frontend/src/components/PosterActionMenu.jsx`, `frontend/src/pages/TitleDetailPage.jsx`
- **steps:** From Explore (or title detail), open poster ⋮ menu. Click **Recommend** (requires `multi_user_enabled`). Wait for `recommend-modal`.
- **pass:** Modal opens with title; either `recommend-peer-list` with household peers **or** `recommend-no-peers` empty copy. Close works (`recommend-modal-close`). If Recommend menu item absent because multi-user off, note N/A.

### `recommend.send-to-peer`

- **roles:** `member`, `owner`
- **tags:** `recommend`, `inbox`
- **source:** `frontend/src/components/RecommendModal.jsx`
- **steps:** Open recommend modal with peers available. Select one peer (`recommend-peer-*`), optionally fill `recommend-note`, submit `recommend-send`. Prefer sending **member → owner** or **owner → member** so the other role can verify inbox.
- **pass:** Modal closes (or success progress finishes); no persistent `recommend-error`. Optionally confirm recipient later via `inbox.card-actions` — record cross-role note. If no peers, N/A.

### `settings.notifications-prefs`

- **roles:** `member`, `owner`, `youth`
- **tags:** `notifications`, `settings`
- **source:** `frontend/src/pages/settings/NotificationsSettingsPage.jsx`
- **steps:** Open Settings → Notifications (`settings-nav-notifications` / `/settings/notifications`). Confirm Delivery panel: email input + inbox / email / newsletter / nudge toggles. Toggle one preference, click `notifications-save`, then restore original value and save again.
- **pass:** `settings-notifications` loads; all four toggles + email field present; save shows success (`notifications-status`) and prefs persist across reload. Do not leave QA accounts permanently opted into email/nudge unless already on.

### `settings.notifications-owner-self-send`

- **roles:** `owner`
- **tags:** `notifications`, `settings`
- **source:** `frontend/src/pages/settings/NotificationsSettingsPage.jsx`
- **steps:** As owner on Notifications, confirm “Send me this week’s newsletter” panel (`notifications-newsletter-self-send`). Do **not** confirm the send dialog unless newsletter is already opted in and the user asked to send — otherwise click cancel / skip actual send.
- **pass:** Owner-only panel visible with send control. Member must **not** see this panel (spot-check when running member). Actual send is optional; canceling confirm is PASS for UI presence.

### `admin.mail-notify-surface`

- **roles:** `owner`
- **tags:** `notifications`, `admin`
- **source:** `frontend/src/pages/MailSettingsPage.jsx`, `frontend/src/layouts/AdminLayout.jsx`
- **steps:** Open Admin → Mail (`admin-nav-mail` / `/admin/mail`). Inspect Outbound email (`mail-transport-panel`: enable toggle, provider, from fields when open). Confirm page copy points newsletter / Year in Review push to Ops → Newsletters (link to `/admin/newsletters`). Do **not** save destructive mail changes unless explicitly requested.
- **pass:** `admin-mail` loads; transport controls visible. Weekly newsletter scope / YIR generate controls are **not** on Mail (they live on Newsletters). Member navigating to `/admin/mail` still redirects away (covered by `nav.admin-redirect`).

### `admin.newsletters-surface`

- **roles:** `owner`
- **tags:** `notifications`, `admin`, `newsletter`, `yir`
- **source:** `frontend/src/pages/NewslettersPage.jsx`, `frontend/src/components/admin/WeeklyNewsletterPanel.jsx`, `frontend/src/components/admin/YearInReviewAdminPanel.jsx`, `frontend/src/lib/adminNav.js`
- **steps:** From Admin rail, open Ops → Newsletters (`admin-nav-newsletters` / `/admin/newsletters`). Confirm page chrome (`admin-newsletters`) and both panels: weekly newsletter (`newsletters-newsletter-scope` + `newsletters-newsletter-send`) and Year in Review (`newsletters-yir-panel`, `newsletters-yir-self-generate`, `newsletters-yir-notify-toggle`). Scroll the full page; confirm no sticky admin chrome pins content off-screen on a narrow viewport (~390px width) if available.
- **pass:** Both panels always visible (not gated behind mail-configured). Scope select + send control present; YIR notify toggle + generate button present. Do **not** confirm send/generate dialogs in this ID (presence only). Member hitting `/admin/newsletters` redirects (covered by `nav.admin-redirect`).

### `admin.newsletters-yir-generate-inbox`

- **roles:** `owner`
- **tags:** `notifications`, `admin`, `yir`, `inbox`
- **source:** `frontend/src/components/admin/YearInReviewAdminPanel.jsx`, `frontend/src/pages/InboxPage.jsx`, `projectionist/year_in_review/delivery.py`
- **steps:** On `/admin/newsletters`, leave `newsletters-yir-notify-toggle` on. Click `newsletters-yir-self-generate` and **confirm** the dialog. Wait for `newsletters-yir-status`. If status is success with `newsletters-yir-link`, follow the link (or open Inbox). If status reports not enough finishes / empty, record N/A for reel open but still open `/inbox` and note whether a YIR card appeared.
- **pass:** Generate completes without crash. On ready: status success, optional reel link only when ready, and Inbox shows a durable Year in Review item (or reel opens at `/year-in-review/{year}`). Empty-year is PASS with honest empty copy (not a silent failure). Canceling the confirm dialog without generating is not this ID — re-run with confirm.

### `settings.notifications-yir-opt-in`

- **roles:** `owner`, `member`
- **tags:** `notifications`, `settings`, `yir`
- **source:** `frontend/src/pages/settings/NotificationsSettingsPage.jsx`
- **steps:** Open Settings → Notifications. Locate Year in Review opt-in / self-generate controls when present. Confirm owner can see generate-self affordance; toggle opt-in once and save, then restore.
- **pass:** YIR preference controls render without crash; save persists. Do not leave the account permanently changed from its prior opt-in state.

### `journey.list-filter`

- **roles:** `member`, `owner`, `youth`
- **tags:** `journey`
- **source:** `frontend/src/pages/MyJourneyPage.jsx`
- **steps:** Open `/my-journey`. Ensure List view. Click a filter (e.g. `journey-filter-earned` or `in-progress`).
- **pass:** Filter becomes active; list updates (possibly empty matching message). Hero stats visible.

### `journey.tree-mode`

- **roles:** `member`, `owner`, `youth`
- **tags:** `journey`
- **source:** `frontend/src/pages/MyJourneyPage.jsx`
- **steps:** Click `journey-view-tree` (Achievements Tree).
- **pass:** `journey-tree` visible with pathway columns/nodes — not missing/blank chrome.

### `journey.tree-detail`

- **roles:** `member`, `owner`, `youth`
- **tags:** `journey`
- **source:** `frontend/src/pages/MyJourneyPage.jsx` (`JourneyDetailDrawer`)
- **steps:** In tree (or list), open a node. Inspect detail drawer.
- **pass:** Detail opens with name/description; close works. If Chat pathway control present, it may be exercised optionally.

### `journey.courses-section`

- **roles:** `member`, `owner`, `youth`
- **tags:** `journey`
- **source:** `frontend/src/pages/MyJourneyPage.jsx`
- **steps:** Scroll to Cinema courses (`journey-courses`).
- **pass:** Section renders with course cards **or** empty copy about published courses.

### `settings.role`

- **roles:** `member`
- **tags:** `settings`, `gating`
- **source:** `frontend/src/pages/settings/ProfilePage.jsx`
- **steps:** Open Settings → Profile. Read identity meta.
- **pass:** Shows `Role · member` (exact role string). No youth badge.

### `theme.toggle`

- **roles:** `member`, `owner`, `youth`, `guest`
- **tags:** `theme`
- **source:** `frontend/src/components/PrimaryTopbar.jsx`, `frontend/src/lib/uiPrefs.js`
- **steps:** Click `topbar-theme-toggle` until **Lights Up** and **Lights Down** have each been applied at least once (cycle: lights_up → lights_down → system). Confirm `html[data-theme]` / visible surfaces flip.
- **pass:** Both Lights Up and Lights Down observed; chrome/readable contrast OK; no broken hardcoded colors on primary surfaces.

### `shell.default-member`

- **roles:** `member`
- **tags:** `shell`
- **source:** `frontend/src/lib/memberShell.js`, `frontend/src/layouts/AppShell.jsx`
- **steps:** On a topbar page, inspect root `data-shell` / classes.
- **pass:** Not `youth-shell` / `guest-shell`; no “Youth mode” / “Guest tour” eyebrow on member pages.

---

## Owner

Owner peers: member set **plus** Admin (before My Journey).

### `nav.peers-owner`

- **roles:** `owner`
- **tags:** `nav`, `gating`, `admin`
- **source:** `frontend/src/lib/primaryNav.js`
- **steps:** Settle on `/explore` as owner. Inspect topbar.
- **pass:** `topbar-admin-link` present; Admin sits immediately before My Journey; other peers present.

### `nav.admin-open`

- **roles:** `owner`
- **tags:** `admin`, `gating`
- **source:** `frontend/src/layouts/AdminLayout.jsx`
- **steps:** Open `/admin` or Admin topbar link.
- **pass:** `admin-layout` loads; desktop admin rail sections visible (Overview, Connections, …) **or** on narrow viewports open hamburger (`app-nav-toggle`) and see Admin section links (`app-nav-admin-*`). No yellow `admin-drawer-toggle`. Not redirected to settings.

### `nav.drawer-owner`

- **roles:** `owner`
- **tags:** `nav`
- **source:** `frontend/src/lib/appNavItems.js`, `frontend/src/lib/primaryNav.js`
- **steps:** Outside `/admin`, open hamburger drawer. On `/admin/*`, open hamburger again.
- **pass:** Both times the drawer opens on a **Navigate** heading (`app-nav-heading-navigate`) carrying **every primary peer the owner sees in the topbar**, labelled: `app-nav-search`, `app-nav-chat`, `app-nav-explore`, `app-nav-inbox`, `app-nav-admin`, `app-nav-my-journey`, `app-nav-settings`. Off Admin: no Admin *section* dump (no `app-nav-admin-*`), then **More** with Plot Lab, Tags, Watchlist, Library, Help, Privacy, About. On Admin: an **Admin** heading (`app-nav-heading-admin`) with the section links (`app-nav-admin-*`) sits **between** Navigate and More — it adds to Navigate, never replaces it. My Journey appears once (Navigate only).

### `settings.role-owner`

- **roles:** `owner`
- **tags:** `settings`, `gating`
- **source:** `frontend/src/pages/settings/ProfilePage.jsx`
- **steps:** Settings → Profile.
- **pass:** `Role · owner`.

### `owner.chat-explore-inbox-journey-theme`

- **roles:** `owner`
- **tags:** `chat`, `explore`, `inbox`, `journey`, `theme`, `search`, `scroll`
- **source:** (reuse member IDs)
- **steps:** Execute the same interactions as: `chat.starter-or-send`, `chat.mood-or-surprise`, `chat.poster-scroll`, `explore.open-card`, `explore.chat-about-these`, `search.query`, `inbox.empty-or-item`, `journey.list-filter`, `journey.tree-mode`, `journey.tree-detail`, `theme.toggle`.
- **pass:** Each linked ID’s pass criteria. (In reports, may expand to those IDs individually — preferred for `full`.)

> For `full` owner campaigns, prefer running the shared IDs that list `owner` in **roles** rather than only this aggregate.

### `admin.tasks-detail-controls`

- **roles:** `owner`
- **tags:** `admin`
- **source:** `frontend/src/pages/ScheduledTasksPage.jsx`
- **steps:** Open Admin → Scheduled Tasks (`admin-nav-tasks` / `/admin/tasks`). Select a task so the monitor/detail pane is populated. Click `task-detail-run-now` (prefer a safe/fast task such as `health_metrics` if present). Confirm the same pane’s `task-detail-toggle-enabled` can Disable then Enable (restore enabled before leaving).
- **pass:** Detail Run now triggers a run (monitor shows Started / running / finished, or list status updates). Disable/Enable toggles the selected task’s enabled state and persists after Refresh / poll. List-row controls remain available; detail controls reuse the same actions.

### `admin.tasks-execution-log`

- **roles:** `owner`
- **tags:** `admin`, `scroll`, `theme`
- **source:** `frontend/src/pages/ScheduledTasksPage.jsx`
- **steps:** On `/admin/tasks`, locate `scheduled-tasks-execution-log` (collapsed by default). Click `execution-log-toggle` to expand. Inspect rows for task name, times, status, duration, and summary/error when present. Cycle theme (`topbar-theme-toggle`) through Lights Up and Lights Down while the pane is open. Confirm only the pane body scrolls when many rows exist — not a nested double vertical scrollbar on the page chrome.
- **pass:** Pane starts collapsed; expands to show unified newest-first history (`execution-log-body`). Theme-readable in Lights Up and Lights Down. No double vertical scrollbars (page may scroll; pane may scroll; both together should not fight).

### `admin.tasks-next-run-sort`

- **roles:** `owner`
- **tags:** `admin`
- **source:** `frontend/src/pages/ScheduledTasksPage.jsx`, `frontend/src/lib/scheduledTasks.js`
- **steps:** On `/admin/tasks`, read the All tasks table. Confirm a Next run column and Last run column. Note top rows are soonest-next / due / running; disabled tasks appear toward the bottom. After a Run now (or wait for poll), confirm ordering/next-run labels update without a full page reload.
- **pass:** Rows ordered by next fire time ascending (nearest upcoming / due first); disabled tasks last. Next-run and last-run values visible and legible; order remains dynamic after runs/polls.

### `admin.tasks-detail-layout`

- **roles:** `owner`
- **tags:** `admin`, `scroll`, `theme`
- **source:** `frontend/src/pages/ScheduledTasksPage.jsx`, `frontend/src/styles/10-explore-delight.css`
- **steps:** At a typical desktop viewport between 1280px and 1440px wide, open `/admin/tasks` and select a task with a multi-line description. Inspect the table, selected-task header/meta, description, and detail actions in both Lights Up and Lights Down. If the table overflows its list pane, scroll that pane horizontally to its Last run / Next run columns.
- **pass:** The detail pane has a usable width; its description reads as normal prose rather than wrapping one word per line. Status, Next/Last times, and action buttons are not jammed into a narrow strip. The table keeps legible Last run and Next run values without being clipped by or overlapping the detail pane; any horizontal overflow is contained inside the table pane. The layout remains usable throughout 1280–1440px desktop widths in both themes.

### `admin.logs-surface`

- **roles:** `owner`
- **tags:** `admin`, `logs`
- **source:** `frontend/src/pages/LogsPage.jsx`, `frontend/src/lib/adminNav.js`
- **steps:** Open Admin → Logs (`admin-nav-logs` / `/admin/logs`). Confirm `logs-page` and `logs-toolbar` render. Change `logs-level-filter` (e.g. INFO → WARNING) and apply a logger or text filter if fields are present (`logs-logger-apply` / `logs-q-apply`). Click `logs-refresh`. Toggle `logs-follow-toggle` once each way.
- **pass:** Page loads for owner (not redirected to Settings). Toolbar + scroller (`logs-scroller`) visible; level change and refresh re-query without a blank crash. Sensitive warning (`logs-sensitive-warning`) may appear — note if present. Empty state (`logs-empty`) or lines (`logs-line`) acceptable. Member/youth redirected away (covered by `nav.admin-redirect`).

### `admin.storage-purge-type-pagination`

- **roles:** `owner`
- **tags:** `admin`, `library`, `purge`
- **source:** `frontend/src/pages/DashboardPage.jsx` (Storage Intelligence / purge table)
- **steps:** Open Admin overview / dashboard with Storage Intelligence candidates. If `purge-empty`, note N/A (no candidates). Otherwise inspect the candidate table for a Type column (`purge-candidate-type` showing Movie or Show). When more than one page of candidates exists, use `purge-pagination` Previous/Next and confirm page label updates.
- **pass:** Type column visible and correct for at least one row when candidates exist. Pagination controls present when multi-page; page index changes on Next/Previous. Single-page lists still show pagination chrome or a clear single-page label without error.

### `admin.grooming-section-help`

- **roles:** `owner`
- **tags:** `admin`, `purge`, `help`
- **source:** `frontend/src/components/GroomingUndoPanel.jsx`, `frontend/src/components/SectionHelp.jsx`
- **steps:** On Admin overview, locate Purge candidates & index undo (`grooming-panel`). Open SectionHelp (`grooming-section-help`). Read that refresh is non-destructive and undo is index-only. Optionally click `grooming-rerun` and wait for notice or error (do not require disk deletes).
- **pass:** Help popover opens with refresh vs index-undo distinction. Panel remains usable; rerun (if clicked) completes without crashing the page.

### `admin.removal-summary-dialog`

- **roles:** `owner`
- **tags:** `admin`, `purge`, `library`
- **source:** `frontend/src/components/RemovalSummaryDialog.jsx`, `frontend/src/pages/DashboardPage.jsx`
- **steps:** After a successful full remove that returns a removal summary (or when QA seed already surfaces one), confirm `removal-summary-dialog` opens with totals (`removal-summary-totals`) and list (`removal-summary-list`). Open `removal-summary-help`. Close via `removal-summary-close` or `removal-summary-done`.
- **pass:** Dialog shows title/file/folder totals; help explains *arr path reporting. Close dismisses the dialog. If no remove was performed this session, mark N/A and do not invent a destructive delete solely for this ID — prefer pairing with an intentional QA purge campaign.

### `admin.taxonomy-surface`

- **roles:** `owner`
- **tags:** `admin`, `taxonomy`, `knowledge-ops`
- **source:** `frontend/src/pages/StagedAugmentationsPage.jsx`
- **steps:** Open Admin → Knowledge Ops (`/admin/taxonomy`). Confirm `admin-taxonomy` root, `knowledge-ops-summary`, `knowledge-ops-tabs`, and `knowledge-ops-funnel` render.
- **pass:** Page loads for owner (not redirected). Summary strip shows stat cards; funnel bars visible. Tabs switch without crash.

### `admin.knowledge-ops-facet-approve`

- **roles:** `owner`
- **tags:** `admin`, `taxonomy`, `knowledge-ops`
- **source:** `frontend/src/pages/StagedAugmentationsPage.jsx`, `projectionist/web/augmentation_routes.py`
- **steps:** On Taxonomy or All staged work tab with a pending facet row, open context panel (`knowledge-ops-context`). If QA has a pending facet candidate, fill concept id or TMDB name and click `taxonomy-approve-{id}`. Otherwise mark N/A when no pending facet rows.
- **pass:** Approve succeeds with `taxonomy-feedback` success message, or N/A when backlog empty. Reject (`taxonomy-reject-{id}`) clears row without overlay write when exercised.

### `admin.knowledge-ops-act-non-facet`

- **roles:** `owner`
- **tags:** `admin`, `knowledge-ops`
- **source:** `frontend/src/pages/StagedAugmentationsPage.jsx`, `projectionist/web/staged_augmentation_promote.py`
- **steps:** Switch to Demand or Coverage tab (or All staged work). Select a pending non-facet row if present. Confirm act button (`taxonomy-act-{id}`) shows label (Run enrichment / Run theme tagging). Click act or mark N/A if no pending demand/coverage rows.
- **pass:** Act button copy matches task kind; click completes with feedback or honest API error (e.g. missing TMDB key). Reject remains available.

### `admin.knowledge-ops-empty-states`

- **roles:** `owner`
- **tags:** `admin`, `knowledge-ops`
- **source:** `frontend/src/pages/StagedAugmentationsPage.jsx`
- **steps:** Open Activity tab — confirm trend panel and top events (`knowledge-ops-top-events` or empty message). Open Taxonomy tab top unresolved facets (`knowledge-ops-top-facets-empty` when none). Filter staged list to pending with no rows — `taxonomy-empty` message.
- **pass:** Empty states are honest (not errors). Activity tab renders sparkline area or “No signal trend yet.”

### `explore.surprising-neighbors-showcase`

- **roles:** `member`, `owner`
- **tags:** `explore`, `neighbors`
- **source:** `frontend/src/components/SurprisingNeighborsShowcase.jsx`, `frontend/src/pages/TitleDetailPage.jsx`
- **steps:** Open a title detail (or Plot Lab / neighbors surface) that shows surprising neighbors (`title-neighbors-surprising` or showcase `data-testid` such as `explore-neighbors-rail`). Confirm featured card + why copy (`*-featured`, `*-featured-why` or equivalent). If `*-show-more` is present, expand then collapse.
- **pass:** Showcase renders with intro and at least one featured neighbor when data exists; why signals/headline visible. Show more toggles extra cells when hidden count > 0. Empty/missing neighbors → N/A (not FAIL).

---

## Youth

Youth uses member peer set (no Admin). Topbar labels: Chat → **Ask**, Explore → **Browse**. Shell: youth.

### `nav.peers-youth`

- **roles:** `youth`
- **tags:** `nav`, `gating`, `shell`
- **source:** `frontend/src/lib/primaryNav.js`, `frontend/src/layouts/AppShell.jsx`
- **steps:** Settle on Explore/Ask surface. Read topbar `aria-label` / tooltips.
- **pass:** No Admin. Chat peer labeled **Ask**; Explore peer labeled **Browse**. Inbox / My Journey / Settings present. Root shows youth shell (`data-shell="youth"` / `youth-shell`). Eyebrow may show “Youth mode”.

### `nav.drawer-youth`

- **roles:** `youth`
- **tags:** `nav`, `shell`
- **source:** `frontend/src/lib/appNavItems.js`, `frontend/src/lib/primaryNav.js`
- **steps:** Open hamburger.
- **pass:** **Navigate** block carries every peer youth sees in the topbar — `app-nav-search`, `app-nav-chat` (labelled **Ask**), `app-nav-explore` (labelled **Browse**), `app-nav-inbox`, `app-nav-my-journey`, `app-nav-settings` — and no `app-nav-admin`. **More** stays reduced: My list (`app-nav-watchlist`) and Help only — not the adult Plot Lab / Tags / Library set. My Journey appears once (Navigate only).

### `settings.role-youth`

- **roles:** `youth`
- **tags:** `settings`, `gating`, `shell`
- **source:** `frontend/src/pages/settings/ProfilePage.jsx`
- **steps:** Settings → Profile.
- **pass:** Role line shows the account role; **Youth mode** badge (`youth-mode-badge`) visible.

### `youth.chat-explore-journey-theme`

- **roles:** `youth`
- **tags:** `chat`, `explore`, `journey`, `theme`, `inbox`, `search`, `scroll`, `gating`
- **source:** (reuse shared IDs)
- **steps:** Run `nav.no-admin`, `nav.admin-redirect`, plus shared chat/explore/search/inbox/journey/theme IDs that include `youth`.
- **pass:** Per those IDs; youth labels remain consistent after navigation.

> Prefer expanding shared IDs in `full` reports.

---

## Guest (signed-in role)

Guest peers only: Search, Chat (Ask), Explore (Browse). No Inbox / Admin / My Journey / Settings in primary topbar.

### `nav.peers-guest`

- **roles:** `guest`
- **tags:** `nav`, `gating`, `shell`
- **source:** `frontend/src/lib/primaryNav.js`, `frontend/src/lib/memberShell.js`
- **steps:** Sign in as `QA_GUEST_*`. Inspect topbar on `/explore` or `/chat`.
- **pass:** Only search / chat / explore peers. Labels Ask / Browse. Guest shell (`guest-shell`). No Inbox, Admin, My Journey, Settings icons.

### `nav.drawer-guest`

- **roles:** `guest`
- **tags:** `nav`, `tour`
- **source:** `frontend/src/lib/appNavItems.js`, `frontend/src/lib/primaryNav.js`
- **steps:** Open hamburger.
- **pass:** **Navigate** block carries only the peers a guest sees in the topbar — `app-nav-search`, `app-nav-chat` (**Ask**), `app-nav-explore` (**Browse**) — with no Inbox, My Journey, Settings, or Admin entry. **More** holds What’s great (`/tour`), Collections, Help, About.

### `nav.admin-redirect-guest`

- **roles:** `guest`
- **tags:** `gating`, `admin`
- **source:** `frontend/src/layouts/AdminLayout.jsx`
- **steps:** Navigate to `/admin`.
- **pass:** Redirect away from admin (settings or login); admin not usable.

### `guest.chat-explore-search-theme`

- **roles:** `guest`
- **tags:** `chat`, `explore`, `search`, `theme`, `scroll`
- **source:** (reuse shared IDs)
- **steps:** Run shared chat / explore / search / theme / poster-scroll IDs that include `guest`.
- **pass:** Per those IDs.

### `guest.no-journey-inbox`

- **roles:** `guest`
- **tags:** `gating`, `nav`
- **source:** `frontend/src/lib/primaryNav.js`
- **steps:** Attempt deep-link `/my-journey` and `/inbox`.
- **pass:** Either redirected/blocked or page does not expose member journey/inbox chrome as if authorized; document actual behavior. Must not show owner Admin.

---

## Guest tour (public `/tour`)

No account. Feature flag `guest_tour_enabled` / `CURATORX_GUEST_TOUR_ENABLED`.

### `tour.public-chrome`

- **roles:** `guest-tour`
- **tags:** `tour`, `shell`, `gating`
- **source:** `frontend/src/pages/GuestTourPage.jsx`, `frontend/src/layouts/AppShell.jsx`
- **steps:** Open `/tour` logged out. Inspect chrome.
- **pass:** Public chrome (no hamburger / no primary peer toolbar). Title / “Guest tour” eyebrow. Sign in action present. If flag off → redirect `/login` (note and stop tour IDs).

### `tour.grid-or-empty`

- **roles:** `guest-tour`
- **tags:** `tour`
- **source:** `frontend/src/pages/GuestTourPage.jsx`
- **steps:** Wait for load. Observe grid or empty.
- **pass:** `guest-tour-grid` with cards **or** `guest-tour-empty` copy. No uncaught error page.

### `tour.cta-browse-ask`

- **roles:** `guest-tour`
- **tags:** `tour`, `nav`
- **source:** `frontend/src/pages/GuestTourPage.jsx`
- **steps:** Click `guest-tour-browse` and/or `guest-tour-ask`.
- **pass:** Navigates toward Explore / Chat as linked. Auth gate may send to login — acceptable if intentional; note outcome.

### `tour.open-card`

- **roles:** `guest-tour`
- **tags:** `tour`
- **source:** `frontend/src/pages/GuestTourPage.jsx`
- **steps:** If cards exist, open one collection card.
- **pass:** Navigates to `/collections/{id}` (or documents auth redirect). Skip N/A if empty.

---

## Curator persona capability contracts

The curator "persona" is a **single household-level voice** the owner configures at
**Admin → Persona** (`frontend/src/components/PersonaSection.jsx`, backend
`projectionist/persona/presets.py`, `/api/persona/presets`, `/api/persona/preview`).
There are **exactly five built-in presets** with deterministic, code-defined UI copy:

| Preset id | Name | Tagline | Review dialogue band |
|-----------|------|---------|----------------------|
| `classic-curator` | Classic Curator | Warm film buff | warm |
| `blunt-archivist` | Blunt Archivist | Direct & data-driven | analytical |
| `enthusiastic-scout` | Enthusiastic Scout | Hype, but grounded | warm |
| `academic-critic` | Academic Critic | Analytical & reference-heavy | analytical |
| `night-owl-host` | Night Owl Host | Casual, tonight-focused | balanced |

Distinct, deterministic per-preset surfaces (do **not** assert LLM prose): welcome greeting,
welcome starters, composer placeholder, tagline, accent hue, typing phrases. Persona changes
**voice/UI copy only** — it never changes role capabilities, admin access, or the Youth gate.

### `persona.presets-grid`

- **roles:** `owner`
- **tags:** `persona`, `settings`, `admin`
- **source:** `frontend/src/components/PersonaSection.jsx`, `projectionist/persona/presets.py`
- **steps:** Open Admin → Persona (`persona-section`). Inspect `persona-preset-grid`.
- **pass:** Exactly five preset cards present with matching testids: `persona-preset-classic-curator`, `persona-preset-blunt-archivist`, `persona-preset-enthusiastic-scout`, `persona-preset-academic-critic`, `persona-preset-night-owl-host`. Each shows its authored name + tagline. No invented presets.

### `persona.select-persist`

- **roles:** `owner`
- **tags:** `persona`, `settings`, `admin`
- **source:** `frontend/src/components/PersonaSection.jsx`, `/api/persona`
- **steps:** Note the current active preset first (restore it at the end). Click a different preset card (e.g. `persona-preset-blunt-archivist`). If `persona-confirm-banner` appears (identity already written), confirm. Wait for save. Reload the page.
- **pass:** Selected card gains `preset-card-active`; `persona-assembled-preview` updates; after reload the same preset stays active (persisted). Restore the original preset before leaving.

### `persona.deterministic-welcome`

- **roles:** `owner`, `member`
- **tags:** `persona`, `chat`
- **source:** `projectionist/persona/presets.py` (`welcome_greeting`, `welcome_starters`), `frontend/src/components/WelcomePanel.jsx`, `/api/persona/preview`
- **steps:** With a known active preset, open `/chat` (fresh session/welcome panel). Read the welcome greeting, the starter chips, and the composer placeholder.
- **pass:** Copy matches the active preset's authored strings (e.g. `classic-curator` greets "…your film-buff curator. What should we queue tonight?" and offers "Suggest something unwatched from my library" / "…cozy Sunday double feature?"; `blunt-archivist` offers "Show my biggest unwatched gaps" / "What should I purge from my library?"). Preset-to-preset copy is observably different. Assert copy strings, not model-generated replies.

### `persona.preview-api-contract`

- **roles:** `owner`
- **tags:** `persona`, `settings`
- **source:** `/api/persona/preview`, `/api/persona/presets`, `projectionist/persona/presets.py:persona_ui_for`
- **steps:** (API-level, deterministic) GET `/api/persona/presets`; GET `/api/persona/preview?persona_preset_id=night-owl-host`.
- **pass:** presets list has 5 entries with `id`/`name`/`tagline`; preview returns `persona_ui` with `welcome_greeting`, `welcome_starters`, `composer_placeholders`, `accent_hue`, `preset_name`, `preset_tagline` for the requested preset (Night Owl Host: "What are we watching tonight?"). Use to assert per-persona structure when browser copy is ambiguous.

### `persona.no-capability-escalation`

- **roles:** `member`, `youth`
- **tags:** `persona`, `gating`
- **source:** `projectionist/persona/presets.py`, `frontend/src/lib/primaryNav.js`, `projectionist/web/auth.py`
- **steps:** Confirm the persona picker is **not** reachable by member/youth (Admin-gated). Navigate to `/admin/persona`.
- **pass:** Non-owner cannot open the persona editor (redirected per `nav.admin-redirect`). Persona/tone does not grant Admin peer, delete, or over-ceiling content — negative boundary. No `persona-preset-grid` for non-owners.

### `persona.youth-guardrail-boundary`

- **roles:** `youth`
- **tags:** `persona`, `chat`, `gating`
- **source:** `projectionist/youth/guardrails.py` (`YOUTH_CHAT_GUARDRAILS`), `frontend/src/lib/youthPersona.js` (`preferYouthFriendlyPersona`)
- **steps:** As youth, ask the curator for a mature/over-ceiling title (e.g. an R-rated film) in chat.
- **pass:** Response redirects to age-appropriate library picks and never surfaces an over-ceiling recommendation card (result cards still pass the rating gate — see `youth.filter.chat-cards`). Assert card/tool boundary + absence of blocked cards, not exact wording.

---

## Sharing, recommendations, inbox arrival (cross-role)

Builds on existing `recommend.*` / `inbox.*` IDs — these add recipient-side arrival, seen/badge,
and role/youth gates. Prefer member↔owner pairs so both ends verify.

### `recommend.recipient-arrival`

- **roles:** `member`, `owner`
- **tags:** `recommend`, `inbox`, `notifications`
- **source:** `projectionist/web/app.py:create_recommendations`, `frontend/src/components/RecommendationsInbox.jsx`
- **steps:** As sender (e.g. owner), send a recommendation to the other role via `recommend-send` (see `recommend.send-to-peer`). Sign in as the **recipient**; open `/inbox`.
- **pass:** A recommendation card appears whose lead reads **"{sender} recommended {title}"** — composed once, not double-wrapped (regression guard for the inbox-title-composition fix; title must not repeat). `recommendation-open-*`/`recommendation-dismiss-*` work.

### `inbox.seen-on-open`

- **roles:** `member`, `owner`, `youth`
- **tags:** `inbox`, `notifications`, `nav`
- **source:** `frontend/src/components/InboxBadgeButton.jsx`, `frontend/src/lib/recommendationInbox.js`
- **steps:** With `unread_count > 0`, note `topbar-inbox-badge`. Open `/inbox`, then open one card via `recommendation-open-*`. Return to a topbar page.
- **pass:** Opening marks the item seen; unread badge count decreases (or badge clears at zero). No stale count after navigation/reload.

### `recommend.role-gate`

- **roles:** `guest`, `youth`
- **tags:** `recommend`, `gating`
- **source:** `frontend/src/components/PosterActionMenu.jsx`, `projectionist/web/app.py:create_recommendations`
- **steps:** As guest (no inbox peer) and as youth, inspect poster ⋮ menu / title detail for a Recommend action.
- **pass:** Guest has no Inbox/Recommend surface (per `nav.peers-guest`). Recommend requires `multi_user_enabled`; where absent for the role, `recommend-title-button` / menu item is not offered. Document actual behavior; must not error.

### `recommend.youth-recipient-safe`

- **roles:** `owner`, `member`
- **tags:** `recommend`, `inbox`, `youth`, `gating`
- **source:** `projectionist/youth/apply.py`, `projectionist/web/app.py`, `frontend/src/components/RecommendationsInbox.jsx`
- **steps:** As owner/member, open the Recommend modal for an **over-ceiling** title (e.g. R-rated). If `qa-youth` appears in `recommend-peer-list`, send it, then sign in as youth and open `/inbox`.
- **pass:** The youth inbox/title surfaces must **not** render an openable over-ceiling title (fail-closed: the title detail deep link 404s for youth — `youth.filter.title-deeplink`). Record whether youth is even offered as a peer. Negative assertion: prohibited content never becomes viewable via a shared recommendation.

---

## Chat save / library / lists / watchlist workflows

Product semantics (actual labels):
- **Save to library** — an assistant chat reply → `ShareActionMenu` ("Save, share, print, or export") → **Save to library** → persists as a saved-library item at `/library/{id}` (`frontend/src/components/ShareActionMenu.jsx`, `/api/saved-library`).
- **Export / Print** — same menu: Export Markdown/JSON/text, Print/PDF (`/api/saved-library/{id}/export`).
- **Watchlist** — poster overlay / bulk **Pin to watchlist** (`frontend/src/components/PosterOverlayControls.jsx`, `library-browse-bulk-pin`).
- **Lists / collections** — Settings → Lists (`settings-lists`, `frontend/src/pages/settings/ListsSettingsPage.jsx`): create, add from watchlist, add manual, rename, remove, delete.

### `library.save-chat-reply`

- **roles:** `member`, `owner`
- **tags:** `chat`, `save`, `library`
- **source:** `frontend/src/components/ChatThread.jsx`, `frontend/src/components/ShareActionMenu.jsx`
- **steps:** Produce an assistant reply in `/chat`. Open its "Save, share, print, or export" menu. Click **Save to library**.
- **pass:** `share-action-flash` shows "Saved to your library." No error. (Item is now retrievable at `/library/{id}`.)

### `library.saved-persists`

- **roles:** `member`, `owner`
- **tags:** `save`, `library`
- **source:** `frontend/src/components/ShareActionMenu.jsx` (`libraryUrl`), `/api/saved-library`
- **steps:** After `library.save-chat-reply`, navigate away and back (or reload), then open the saved item URL `/library/{id}` (from the menu's Share/Open, or via the saved-library surface).
- **pass:** Saved item still renders after reload/navigation (persistence). No 404 for the owner's own saved item.

### `library.export-formats`

- **roles:** `member`, `owner`
- **tags:** `save`, `export`, `library`
- **source:** `frontend/src/components/ShareActionMenu.jsx`, `/api/saved-library/{id}/export`
- **steps:** From a saved reply's menu, trigger **Export Markdown** (and optionally JSON/text). Observe the export tab/flash. Do not assert file bytes.
- **pass:** `share-action-flash` shows "Export opened." and an export request to `/api/saved-library/{id}/export?format=markdown` is issued. No crash.

### `lists.create-add-remove`

- **roles:** `member`, `owner`
- **tags:** `lists`, `library`, `settings`
- **source:** `frontend/src/pages/settings/ListsSettingsPage.jsx`
- **steps:** Settings → Lists (`settings-lists`). Create a list via `lists-create-name` + `lists-create-submit`. Select it (`lists-select-*`). Add a manual item (`lists-add-manual-form`) **or** from watchlist (`lists-add-watchlist`). Remove the item (`lists-remove-*`). Optionally delete the QA list (`lists-delete`) to avoid clutter.
- **pass:** List appears in `lists-index`; detail (`lists-detail`) shows added item in `lists-items`; remove clears it; `lists-message` reflects status. Clean up QA-created lists.

### `watchlist.pin-persists`

- **roles:** `member`, `owner`, `youth`
- **tags:** `watchlist`, `library`
- **source:** `frontend/src/pages/LibraryBrowsePage.jsx` (`library-browse-bulk-pin`), `frontend/src/components/PosterOverlayControls.jsx`
- **steps:** On a populated `/search?q=` or browse page, select ≥1 poster (checkbox), click **Pin to watchlist** (`library-browse-bulk-pin`) — or use a poster hover pin. Reload.
- **pass:** Pin succeeds (status/flash, no error); pinned state survives reload. Youth: only ratings-allowed titles are pinnable (they never see over-ceiling posters to pin).

### `library.role-action-differences`

- **roles:** `owner`, `member`, `youth`
- **tags:** `library`, `gating`
- **source:** `frontend/src/pages/LibraryBrowsePage.jsx`, `frontend/src/components/TitleDetailContent.jsx`
- **steps:** On the same browse page and a title detail, compare available actions across roles.
- **pass:** Owner sees `library-browse-bulk-delete` / `title-detail-delete-button`; member does not (no delete). Youth sees reduced tooling (no adult library-management drawer; `nav.drawer-youth`). Watchlist/watched/review actions available per role. Document differences.

---

## Library + Explore (data-backed)

QA library is fully synced — assert real posters/results, not just empty states.

### `library.browse-posters`

- **roles:** `member`, `owner`, `youth`, `guest`
- **tags:** `library`, `explore`
- **source:** `frontend/src/pages/LibraryBrowsePage.jsx`
- **steps:** From Explore hub, open **Browse Movies** (`explore-hub-browse-movies`). Wait for `library-browse-results`.
- **pass:** `library-browse-results` renders poster cards (populated), `library-browse-summary` shows a title count, `library-browse-title` matches the media type. Not stuck loading; not empty (unless role/youth filter legitimately empties it).

### `library.sort`

- **roles:** `member`, `owner`
- **tags:** `library`
- **source:** `frontend/src/pages/LibraryBrowsePage.jsx`, `MediaBrowseControls`
- **steps:** In the browse toolbar (`library-browse-toolbar`), change the **sort** control (e.g. Title ↔ Year/Recently added). Observe result order.
- **pass:** Result order changes to match the chosen sort; summary/first cards update. No error.

### `library.filter-and-reset`

- **roles:** `member`, `owner`
- **tags:** `library`
- **source:** `frontend/src/pages/LibraryBrowsePage.jsx`, `MediaBrowseControls`
- **steps:** Apply a filter (genre/decade/unwatched, per `filterOptions`). Observe narrowed results and `library-browse-summary`. Then clear/reset filters.
- **pass:** Filter narrows results (count drops or empties with `library-browse-empty` copy); reset restores the fuller list. Deterministic count change.

### `library.pagination`

- **roles:** `member`, `owner`
- **tags:** `library`, `scroll`
- **source:** `frontend/src/pages/LibraryBrowsePage.jsx`
- **steps:** On a browse page with more than one page, click `library-browse-next`, then `library-browse-prev`.
- **pass:** `library-browse-summary` page number advances/retreats; results change; `library-browse-prev` disabled on page 1, `library-browse-next` disabled on last page. If a single page, note N/A.

### `explore.rails-horizontal`

- **roles:** `member`, `owner`, `youth`
- **tags:** `explore`, `scroll`
- **source:** `frontend/src/pages/ExplorePage.jsx` (`explore-card-rail`)
- **steps:** On `/explore`, find a populated rail (`explore-section-*`). Scroll it horizontally; inspect for a nested vertical scrollbar on the rail container.
- **pass:** Rail scrolls horizontally; no nested vertical scrollbar on the rail (page scrolls vertically). Matches `chat.poster-scroll` rule for rails.

### `library.search-to-detail`

- **roles:** `member`, `owner`, `youth`, `guest`
- **tags:** `search`, `library`, `explore`
- **source:** `frontend/src/pages/ExplorePage.jsx`, `LibraryBrowsePage.jsx`, `TitleDetailPage.jsx`
- **steps:** From Explore search (`explore-search-input` + submit) **or** on-page Search (`library-browse-search-input`, progressive or submit) enter a known title fragment. On the results, open a poster to `title-detail-page`.
- **pass:** Query lands on `/search?q=…` with matching `library-browse-title`/results; opening a card reaches `title-detail-page` with hero (`title-detail-hero`) for that title. Full search→detail flow completes.

### `explore.facets`

- **roles:** `member`, `owner`
- **tags:** `explore`
- **source:** `frontend/src/pages/ExplorePage.jsx` (`explore-facet-toolbar`, `explore-facet-wall`)
- **steps:** If a facet toolbar/wall is present on Explore, activate a facet.
- **pass:** Facet updates the wall/rails; no error. If facets absent for the role/data, note N/A.

---

## Youth fail-closed content filtering (extensive)

Policy (code source of truth): `projectionist/youth/rating_gate.py`, `projectionist/youth/apply.py`,
`projectionist/youth/guardrails.py`; applied in `projectionist/web/app.py` at library/browse/feed
endpoints (`_apply_youth_filters`, `_sanitize_library_payload`), title detail
(`title_allowed_for_user` → **HTTP 404**), and engagement aggregates
(`engagement_summary(..., youth_safe_only=True)`). QA ceiling: **PG-13**
(`settings.youth.max_content_rating`).

**Allowed at PG-13 ceiling** (rank ≤ 30): `G`, `TV-Y`, `TV-Y7`, `TV-G`, `PG`, `TV-PG`, `PG-13`.
**Blocked** (rank > 30): `TV-14`, `R`, `NC-17`, `TV-MA`, `X` — **and** unrated / missing / empty /
`NR` / `NA` / `Unrated` / unknown (fail-closed: no known rank ⇒ hidden).

All youth IDs below require signing in as `QA_YOUTH_*` (`is_youth=true`). Negative assertions are
mandatory: prohibited content must **never** appear — including transiently during load/hydration or
after direct URL navigation.

### `youth.filter.settings-ceiling`

- **roles:** `youth`, `owner`
- **tags:** `youth`, `settings`, `gating`
- **source:** `projectionist/web/app.py` (`/api/features` youth block), `seed-qa-roles.sh`
- **steps:** As youth, confirm Settings → Profile shows Youth mode (`youth-mode-badge`, per `settings.role-youth`). As owner, confirm Admin → Youth reflects the configured ceiling.
- **pass:** Youth gate active for the account; owner-configured ceiling = PG-13. Establishes the policy under test.

### `youth.filter.browse-movies`

- **roles:** `youth`
- **tags:** `youth`, `library`, `explore`
- **source:** `projectionist/web/app.py:_apply_youth_filters`, `LibraryBrowsePage.jsx`
- **steps:** As youth, open Browse Movies. Scan every visible poster's content-rating chip (`title-content-rating-chip`) across at least the first page; page through if feasible.
- **pass:** Every visible movie is rated ≤ PG-13 (`G`/`PG`/`PG-13`). No `R`/`NC-17`/`X`/unrated movie appears. Count should be lower than the owner/member view of the same browse.

### `youth.filter.browse-tv`

- **roles:** `youth`
- **tags:** `youth`, `library`, `explore`
- **source:** `projectionist/web/app.py:_apply_youth_filters`, `LibraryBrowsePage.jsx`
- **steps:** As youth, open Browse TV. Scan visible TV content-rating chips.
- **pass:** Only `TV-Y`/`TV-Y7`/`TV-G`/`TV-PG` (and film-scale ≤ PG-13). **`TV-14`, `TV-MA` and unrated shows are absent** (TV-14 rank 35 > 30 is blocked).

### `youth.filter.above-ceiling-absent`

- **roles:** `youth`
- **tags:** `youth`, `library`, `gating`
- **source:** `projectionist/youth/rating_gate.py`
- **steps:** Cross-check a specific R/TV-MA title that owner/member can see (note its title as owner first). As youth, browse/search for it.
- **pass:** The over-ceiling title never appears in youth browse/search/rails. Direct comparison against an adult role confirms it is filtered, not merely paginated away.

### `youth.filter.unrated-absent`

- **roles:** `youth`
- **tags:** `youth`, `library`, `gating`
- **source:** `projectionist/youth/rating_gate.py:content_rating_allowed` (None ⇒ False)
- **steps:** Identify an unrated/`NR`/missing-rating title visible to an adult role. As youth, browse/search for it.
- **pass:** Unrated/missing-rating titles are hidden for youth (fail-closed). No poster with a blank/absent rating chip appears.

### `youth.filter.title-deeplink`

- **roles:** `youth`
- **tags:** `youth`, `gating`
- **source:** `projectionist/web/app.py:title_detail` (`title_allowed_for_user` → 404)
- **steps:** Obtain an over-ceiling (or unrated) title's detail URL from an adult role (e.g. `/title/movie/{tmdb}`). As youth, navigate directly to that URL.
- **pass:** Youth gets a not-available/404 state (`title-detail-page` error), **not** the title hero. Prohibited content never renders — including no transient flash of the hero before the guard resolves.

### `youth.filter.search`

- **roles:** `youth`
- **tags:** `youth`, `search`
- **source:** `projectionist/web/app.py:_apply_youth_filters`, `SearchPage.jsx`
- **steps:** As youth, search a known adult title fragment (e.g. part of an R-rated film's name) via `explore-search-input`.
- **pass:** Results contain only ≤ PG-13 matches (or `library-browse-empty`); the over-ceiling match is absent even though it exists in the library.

### `youth.filter.explore-rails`

- **roles:** `youth`
- **tags:** `youth`, `explore`
- **source:** `projectionist/web/app.py:_sanitize_library_payload` (`filter_payload_for_youth`), `ExplorePage.jsx`
- **steps:** As youth, scan every Explore rail / For-you rail / hub card for ratings chips.
- **pass:** All rail cards are ≤ PG-13. No over-ceiling or unrated poster in any rail, including the personalized For-you rail.

### `youth.filter.chat-cards`

- **roles:** `youth`
- **tags:** `youth`, `chat`
- **source:** `projectionist/youth/guardrails.py`, agent tool result cards (`projectionist/agent`)
- **steps:** As youth, ask the curator for recommendations (broadly, then push toward mature genres like horror/R). Inspect the result poster cards.
- **pass:** Every recommendation card is ≤ PG-13; the curator declines/redirects mature asks. Assert card rating gate + absence of blocked cards (not exact prose).

### `youth.filter.person-facet`

- **roles:** `youth`
- **tags:** `youth`, `library`
- **source:** `projectionist/web/app.py` person/library-for-person payloads (`_apply_youth_filters`)
- **steps:** As youth, open a person/actor or tag/genre facet page that (for adults) includes over-ceiling titles.
- **pass:** Person/facet title lists show only ≤ PG-13 titles; over-ceiling credits are filtered. If no such surface reachable for youth, note N/A.

### `youth.filter.aggregates`

- **roles:** `youth`
- **tags:** `youth`, `journey`
- **source:** `projectionist/web/app.py` (`engagement_summary(..., youth_safe_only=True)`)
- **steps:** As youth, open any surface exposing engagement/coverage aggregates (Explore engagement hub / My Journey stats) if available.
- **pass:** Aggregates/exports are computed youth-safe (no over-ceiling titles feeding counts/examples). If the surface is not exposed to youth, note N/A.

### `youth.filter.watchlist-lists`

- **roles:** `youth`
- **tags:** `youth`, `watchlist`, `lists`
- **source:** `frontend/src/pages/settings/ListsSettingsPage.jsx`, watchlist surfaces
- **steps:** As youth, open My list (watchlist) and any lists surface reachable to youth.
- **pass:** Only ≤ PG-13 titles are pinnable/listable and shown. Youth cannot add an over-ceiling title (it is not selectable because it is not visible).

### `youth.filter.route-action-gates`

- **roles:** `youth`, `guest`
- **tags:** `youth`, `gating`, `nav`
- **source:** `frontend/src/lib/primaryNav.js`, `frontend/src/lib/appNavItems.js`, `AdminLayout.jsx`
- **steps:** As youth (and guest for comparison), attempt `/admin`, adult library-management routes, and delete/recommend actions.
- **pass:** Youth has no Admin peer/drawer, no delete tooling; `/admin` redirects (per `nav.admin-redirect`). Guest deep-links to `/my-journey`/`/inbox` are blocked (per `guest.no-journey-inbox`). Role route/action gates hold.

### `youth.filter.no-transient-leak`

- **roles:** `youth`
- **tags:** `youth`, `gating`, `scroll`
- **source:** `projectionist/youth/apply.py` (server-side filtering), `AppShell.jsx`
- **steps:** Hard-reload youth Explore, Browse, and a search result (network throttling helps). Watch during load/hydration and after direct URL navigation.
- **pass:** No over-ceiling/unrated poster appears even momentarily. Because filtering is server-side (payload never contains blocked items), hydration cannot leak them. Screenshot any transient leak as a blocker.

---

## Delta selection cheat sheet

| Tag | Typical surfaces |
|-----|------------------|
| `gating` | Admin flash, peer visibility, `/admin` redirect, role strings |
| `nav` | Topbar peers, hamburger drawer, hub links |
| `scroll` | Chat poster strip overflow |
| `theme` | Topbar theme cycle Lights Up / Down |
| `journey` | List filters, tree, detail, courses |
| `chat` | Starters, Surprise Me / mood, composer |
| `explore` | Rails, cards, Chat about these |
| `search` | Query submit → `/search?q=` |
| `inbox` | Empty CTA, badge, card dismiss/open, dismiss-all |
| `notifications` | Settings → Notifications prefs; owner self-send; Admin → Mail |
| `recommend` | Household Recommend modal open/send |
| `settings` | Profile role line; notification prefs |
| `admin` | Owner admin shell / Mail / Scheduled Tasks / Logs / Storage Intelligence / non-owner redirect |
| `logs` | Admin → Logs filters, follow, refresh |
| `purge` | Storage Intelligence candidates, grooming undo, removal summary |
| `neighbors` | Surprising neighbors showcase on title / explore |
| `help` | SectionHelp popovers on admin/library panels |
| `shell` | youth / guest / default shell classes |
| `login` | Local form fields |
| `tour` | Public guest tour (removed; `/tour` → `/login`) |
| `invite` | Owner mint / revoke join links; `/join?token=` redeem chrome |
| `access-request` | Login request-access form; owner Access queue |
| `persona` | Curator preset grid / select-persist / deterministic welcome / boundaries |
| `library` | Browse posters / sort / filter+reset / pagination / saved items / role actions |
| `youth` | Fail-closed rating gate: browse/TV/search/rails/detail/chat/aggregates/watchlist |
| `save` | Save chat reply to library; saved-item persistence |
| `export` | Export Markdown/JSON/text/PDF from saved library |
| `lists` | Settings → Lists create/add/remove/rename/delete |
| `watchlist` | Pin to watchlist; pin persistence |

---

## ID index (quick)

| ID | Roles |
|----|-------|
| `login.local-form` | * |
| `login.glass-door` | * (logged-out) |
| `login.honeypot-hidden` | * (logged-out) |
| `login.no-tour` | * (logged-out) |
| `join.glass-door` | * (logged-out) |
| `setup.skip-when-active` | owner |
| `settings.link-plex` | member, owner |
| `login.take-tour-link` | guest-tour (removed; same as login.no-tour) |
| `login.access-request-submit` | * (logged-out) |
| `invite.owner-mint` | owner |
| `join.redeem-token-ui` | * (logged-out) |
| `invite.revoke` | owner |
| `invite.access-queue` | owner |
| `nav.peers-member` | member |
| `nav.no-admin` | member, youth |
| `nav.admin-redirect` | member, youth, guest |
| `nav.drawer-member` | member |
| `chat.starter-or-send` | member, owner, youth, guest |
| `chat.mood-or-surprise` | member, owner, youth, guest |
| `chat.poster-scroll` | member, owner, youth, guest |
| `explore.open-card` | member, owner, youth, guest |
| `explore.chat-about-these` | member, owner, youth, guest |
| `explore.hub-links` | member, owner, youth |
| `search.query` | member, owner, youth, guest |
| `search.progressive` | member, owner, youth, guest |
| `inbox.empty-or-item` | member, owner, youth |
| `inbox.empty-state` | member, owner, youth |
| `inbox.badge` | member, owner, youth |
| `inbox.card-actions` | member, owner, youth |
| `inbox.card-layout` | member, owner, youth |
| `inbox.dismiss-all` | member, owner, youth |
| `inbox.digest-picks` | member, owner, youth |
| `inbox.access-review-cta` | owner |
| `inbox.live-nudge-cta` | member, owner |
| `recommend.open-modal` | member, owner |
| `recommend.send-to-peer` | member, owner |
| `settings.notifications-prefs` | member, owner, youth |
| `settings.notifications-owner-self-send` | owner |
| `admin.mail-notify-surface` | owner |
| `admin.newsletters-surface` | owner |
| `admin.newsletters-yir-generate-inbox` | owner |
| `settings.notifications-yir-opt-in` | owner, member |
| `admin.tasks-detail-controls` | owner |
| `admin.tasks-execution-log` | owner |
| `admin.tasks-next-run-sort` | owner |
| `admin.tasks-detail-layout` | owner |
| `admin.logs-surface` | owner |
| `admin.storage-purge-type-pagination` | owner |
| `admin.grooming-section-help` | owner |
| `admin.removal-summary-dialog` | owner |
| `admin.taxonomy-surface` | owner |
| `admin.knowledge-ops-facet-approve` | owner |
| `admin.knowledge-ops-act-non-facet` | owner |
| `admin.knowledge-ops-empty-states` | owner |
| `explore.surprising-neighbors-showcase` | member, owner |
| `journey.list-filter` | member, owner, youth |
| `journey.tree-mode` | member, owner, youth |
| `journey.tree-detail` | member, owner, youth |
| `journey.courses-section` | member, owner, youth |
| `settings.role` | member |
| `theme.toggle` | member, owner, youth, guest |
| `shell.default-member` | member |
| `nav.peers-owner` | owner |
| `nav.admin-open` | owner |
| `nav.drawer-owner` | owner |
| `settings.role-owner` | owner |
| `owner.chat-explore-inbox-journey-theme` | owner (aggregate; prefer expanded IDs) |
| `nav.peers-youth` | youth |
| `nav.drawer-youth` | youth |
| `settings.role-youth` | youth |
| `youth.chat-explore-journey-theme` | youth (aggregate) |
| `nav.peers-guest` | guest |
| `nav.drawer-guest` | guest |
| `nav.admin-redirect-guest` | guest |
| `guest.chat-explore-search-theme` | guest (aggregate) |
| `guest.no-journey-inbox` | guest |
| `tour.public-chrome` | guest-tour |
| `tour.grid-or-empty` | guest-tour |
| `tour.cta-browse-ask` | guest-tour |
| `tour.open-card` | guest-tour |
| `persona.presets-grid` | owner |
| `persona.select-persist` | owner |
| `persona.deterministic-welcome` | owner, member |
| `persona.preview-api-contract` | owner |
| `persona.no-capability-escalation` | member, youth |
| `persona.youth-guardrail-boundary` | youth |
| `recommend.recipient-arrival` | member, owner |
| `inbox.seen-on-open` | member, owner, youth |
| `recommend.role-gate` | guest, youth |
| `recommend.youth-recipient-safe` | owner, member |
| `library.save-chat-reply` | member, owner |
| `library.saved-persists` | member, owner |
| `library.export-formats` | member, owner |
| `lists.create-add-remove` | member, owner |
| `watchlist.pin-persists` | member, owner, youth |
| `library.role-action-differences` | owner, member, youth |
| `library.browse-posters` | member, owner, youth, guest |
| `library.sort` | member, owner |
| `library.filter-and-reset` | member, owner |
| `library.pagination` | member, owner |
| `explore.rails-horizontal` | member, owner, youth |
| `library.search-to-detail` | member, owner, youth, guest |
| `explore.facets` | member, owner |
| `youth.filter.settings-ceiling` | youth, owner |
| `youth.filter.browse-movies` | youth |
| `youth.filter.browse-tv` | youth |
| `youth.filter.above-ceiling-absent` | youth |
| `youth.filter.unrated-absent` | youth |
| `youth.filter.title-deeplink` | youth |
| `youth.filter.search` | youth |
| `youth.filter.explore-rails` | youth |
| `youth.filter.chat-cards` | youth |
| `youth.filter.person-facet` | youth |
| `youth.filter.aggregates` | youth |
| `youth.filter.watchlist-lists` | youth |
| `youth.filter.route-action-gates` | youth, guest |
| `youth.filter.no-transient-leak` | youth |
