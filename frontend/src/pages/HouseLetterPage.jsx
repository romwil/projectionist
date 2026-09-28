import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  deliverHouseGift,
  enqueueHouseGift,
  getHouseLetter,
  getHouseSeasonalPreview,
  getHouseTrustDiary,
  listHouseGifts,
  listUsers,
  removeHouseGift,
  restoreHouseSeasonalVeto,
  searchHolidayLibrary,
  vetoHouseSeasonalTitle,
} from "../api/client";
import SettingsPageHeader from "../components/settings/SettingsPageHeader";
import SettingsPanel from "../components/settings/SettingsPanel";
import "./HouseLetterPage.css";

function itemId(item) {
  return item?.id ?? item?.library_item_id ?? null;
}

export default function HouseLetterPage() {
  const [letter, setLetter] = useState(null);
  const [rails, setRails] = useState(null);
  const [gifts, setGifts] = useState(null);
  const [diary, setDiary] = useState(null);
  const [members, setMembers] = useState([]);
  const [status, setStatus] = useState(null);
  const [loading, setLoading] = useState(true);
  const [giftForm, setGiftForm] = useState({
    user_id: "",
    library_item_id: "",
    titleLabel: "",
    why: "",
    deliverNow: false,
  });
  const [libraryQuery, setLibraryQuery] = useState("");
  const [libraryHits, setLibraryHits] = useState([]);
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [letterData, railData, giftData, diaryData, usersData] = await Promise.all([
        getHouseLetter(),
        getHouseSeasonalPreview(),
        listHouseGifts(),
        getHouseTrustDiary(),
        listUsers().catch(() => ({ users: [] })),
      ]);
      setLetter(letterData);
      setRails(railData);
      setGifts(giftData);
      setDiary(diaryData);
      const users = usersData.users || usersData.items || usersData || [];
      setMembers(Array.isArray(users) ? users.filter((user) => !user.disabled) : []);
      setStatus(null);
    } catch (error) {
      setStatus({ type: "error", message: error.message || "Could not load the house letter." });
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function handleVeto(scopeId, libraryItemId) {
    try {
      await vetoHouseSeasonalTitle({ scope_id: scopeId, library_item_id: libraryItemId });
      const data = await getHouseSeasonalPreview();
      setRails(data);
      setStatus({ type: "success", message: "That title will stay off the rail." });
    } catch (error) {
      setStatus({ type: "error", message: error.message || "Could not veto that title." });
    }
  }

  async function handleRestore(scopeId, libraryItemId) {
    try {
      await restoreHouseSeasonalVeto(scopeId, libraryItemId);
      const data = await getHouseSeasonalPreview();
      setRails(data);
      setStatus({ type: "success", message: "Veto lifted — it can return to the rail." });
    } catch (error) {
      setStatus({ type: "error", message: error.message || "Could not restore that title." });
    }
  }

  async function handleLibrarySearch(event) {
    event?.preventDefault?.();
    try {
      const data = await searchHolidayLibrary(libraryQuery.trim());
      setLibraryHits(data.items || []);
    } catch (error) {
      setStatus({ type: "error", message: error.message || "Library search failed." });
    }
  }

  async function handleEnqueueGift(event) {
    event.preventDefault();
    if (!giftForm.user_id || !giftForm.library_item_id) {
      setStatus({ type: "error", message: "Pick a member and a title first." });
      return;
    }
    if (giftForm.deliverNow) {
      const member = members.find((row) => row.id === giftForm.user_id);
      const name = member?.display_name || "this member";
      if (
        !window.confirm(
          `Deliver “${giftForm.titleLabel || "this title"}” to ${name} now? This sends one gift — not the household.`,
        )
      ) {
        return;
      }
    }
    setSaving(true);
    try {
      const queued = await enqueueHouseGift({
        user_id: giftForm.user_id,
        library_item_id: Number(giftForm.library_item_id),
        why: giftForm.why.trim(),
      });
      if (giftForm.deliverNow && queued.item?.id) {
        await deliverHouseGift(queued.item.id);
      }
      const data = await listHouseGifts();
      setGifts(data);
      setGiftForm({ user_id: giftForm.user_id, library_item_id: "", titleLabel: "", why: "", deliverNow: false });
      setLibraryHits([]);
      setStatus({
        type: "success",
        message: giftForm.deliverNow
          ? "Gift delivered to that member’s inbox."
          : "Gift queued. The weekly gift task will send it — or deliver it yourself.",
      });
    } catch (error) {
      setStatus({ type: "error", message: error.message || "Could not queue that gift." });
    } finally {
      setSaving(false);
    }
  }

  async function handleDeliverGift(gift) {
    const name = gift.member_name || "this member";
    if (!window.confirm(`Deliver “${gift.title}” to ${name} now? One gift, not a blast.`)) return;
    try {
      await deliverHouseGift(gift.id);
      setGifts(await listHouseGifts());
      setStatus({ type: "success", message: `Delivered to ${name}.` });
    } catch (error) {
      setStatus({ type: "error", message: error.message || "Could not deliver that gift." });
    }
  }

  async function handleRemoveGift(gift) {
    try {
      await removeHouseGift(gift.id);
      setGifts(await listHouseGifts());
    } catch (error) {
      setStatus({ type: "error", message: error.message || "Could not remove that gift." });
    }
  }

  if (loading) {
    return (
      <div className="settings-stack house-letter-page" data-testid="admin-house">
        <SettingsPageHeader title="House">Writing the letter…</SettingsPageHeader>
      </div>
    );
  }

  const paragraphs = letter?.paragraphs || [];
  const upcoming = rails?.rails || [];
  const pendingGifts = gifts?.pending || [];
  const diaryEntries = diary?.entries || [];

  return (
    <div className="settings-stack house-letter-page" data-testid="admin-house">
      <SettingsPageHeader title="House">
        A letter about the house — unwatched hours, dead weight, and disk — not a tile wall.
        Preview seasonal rails before they publish. Queue one gift at a time. The trust diary
        links rematch, Investigate, and job cards.
      </SettingsPageHeader>

      {status ? (
        <p
          className={`status ${status.type === "error" ? "status-error" : "status-success"}`}
          data-testid="house-status"
        >
          {status.message}
        </p>
      ) : null}

      <article className="house-letter" data-testid="house-letter">
        <p className="house-letter-salutation">{letter?.salutation || "Dear owner,"}</p>
        <div className="house-letter-body">
          {paragraphs.map((paragraph) => (
            <p key={paragraph.kind} data-testid={`house-letter-${paragraph.kind}`}>
              {paragraph.text}
            </p>
          ))}
        </div>
        <p className="house-letter-signoff">{letter?.signoff || "— your curator"}</p>
        <p className="house-letter-meta">
          Confirm before a fleet. Health still holds purge and undo.{" "}
          <Link to="/admin/health">Open Health</Link>
          {" · "}
          <Link to="/admin/holidays">Holiday calendar</Link>
        </p>
      </article>

      <SettingsPanel
        title="Seasonal preview"
        lead="Upcoming rails already exist. Veto a title here before the house publishes it."
        testId="house-seasonal"
      >
        {upcoming.length === 0 ? (
          <p className="settings-field-hint" data-testid="house-seasonal-empty">
            {rails?.empty_reason || "No seasonal window in the next few weeks."}
          </p>
        ) : (
          upcoming.map((rail) => {
            const vetoed = new Set(rail.vetoed_ids || []);
            return (
              <div key={rail.scope_id} className="house-rail-block" data-testid={`house-rail-${rail.scope_id}`}>
                <div className="house-rail-head">
                  <h4>{rail.name || rail.label}</h4>
                  <p className="house-rail-when">
                    {rail.active_now
                      ? "On the rail now"
                      : rail.grounding_date
                        ? `Grounding ${rail.grounding_date}`
                        : "Upcoming"}
                  </p>
                </div>
                {(rail.items || []).length === 0 ? (
                  <p className="settings-field-hint">{rail.note || "No titles matched yet."}</p>
                ) : (
                  (rail.items || []).map((item) => {
                    const id = itemId(item);
                    const isVetoed = id != null && vetoed.has(Number(id));
                    return (
                      <div key={`${rail.scope_id}-${id}`} className="house-title-row">
                        <p>
                          {item.title || item.name}
                          {item.year ? ` (${item.year})` : ""}
                          {isVetoed ? " — vetoed" : ""}
                        </p>
                        {id != null ? (
                          isVetoed ? (
                            <button
                              type="button"
                              className="ghost"
                              onClick={() => handleRestore(rail.scope_id, Number(id))}
                            >
                              Restore
                            </button>
                          ) : (
                            <button
                              type="button"
                              className="ghost"
                              onClick={() => handleVeto(rail.scope_id, Number(id))}
                              data-testid={`house-veto-${rail.scope_id}-${id}`}
                            >
                              Veto
                            </button>
                          )
                        ) : null}
                      </div>
                    );
                  })
                )}
              </div>
            );
          })
        )}
      </SettingsPanel>

      <SettingsPanel
        title="Gift queue"
        lead="One member, one title, a short why. Reuses the weekly newsletter / nudge cadence — never a household blast."
        testId="house-gifts"
      >
        <form className="house-gift-form" onSubmit={handleEnqueueGift} data-testid="house-gift-form">
          <label>
            Member
            <select
              value={giftForm.user_id}
              onChange={(event) => setGiftForm((prev) => ({ ...prev, user_id: event.target.value }))}
              data-testid="house-gift-member"
            >
              <option value="">Choose someone</option>
              {members.map((user) => (
                <option key={user.id} value={user.id}>
                  {user.display_name || user.id}
                </option>
              ))}
            </select>
          </label>
          <div className="house-gift-search">
            <label>
              Title from the house
              <input
                type="search"
                value={libraryQuery}
                onChange={(event) => setLibraryQuery(event.target.value)}
                placeholder="Search the library"
                data-testid="house-gift-search"
              />
            </label>
            <button type="button" className="ghost" onClick={handleLibrarySearch}>
              Search
            </button>
          </div>
          {giftForm.titleLabel ? (
            <p className="settings-field-hint">Selected: {giftForm.titleLabel}</p>
          ) : null}
          {libraryHits.map((hit) => (
            <div key={hit.id} className="house-title-row">
              <p>
                {hit.title}
                {hit.year ? ` (${hit.year})` : ""}
              </p>
              <button
                type="button"
                className="ghost"
                onClick={() =>
                  setGiftForm((prev) => ({
                    ...prev,
                    library_item_id: String(hit.id),
                    titleLabel: hit.year ? `${hit.title} (${hit.year})` : hit.title,
                  }))
                }
              >
                Choose
              </button>
            </div>
          ))}
          <label>
            Why (kept short)
            <textarea
              rows={2}
              value={giftForm.why}
              onChange={(event) => setGiftForm((prev) => ({ ...prev, why: event.target.value }))}
              placeholder="Because they asked for a quiet night, not a franchise."
              data-testid="house-gift-why"
            />
          </label>
          <label className="settings-toggle-row">
            <input
              type="checkbox"
              checked={giftForm.deliverNow}
              onChange={(event) => setGiftForm((prev) => ({ ...prev, deliverNow: event.target.checked }))}
              data-testid="house-gift-deliver-now"
            />
            Deliver now after I confirm — otherwise wait for the weekly gift task
          </label>
          <div className="settings-actions">
            <button type="submit" className="primary" disabled={saving} data-testid="house-gift-queue">
              {giftForm.deliverNow ? "Queue and deliver" : "Queue gift"}
            </button>
          </div>
        </form>

        {pendingGifts.length === 0 ? (
          <p className="settings-field-hint" data-testid="house-gifts-empty">
            No gifts waiting. Queue one when you have a why.
          </p>
        ) : (
          pendingGifts.map((gift) => (
            <div key={gift.id} className="house-title-row" data-testid={`house-gift-${gift.id}`}>
              <p>
                {gift.title}
                {gift.year ? ` (${gift.year})` : ""} — for {gift.member_name || "a member"}
                {gift.why ? `. ${gift.why}` : ""}
              </p>
              <div className="settings-actions">
                <button type="button" className="ghost" onClick={() => handleDeliverGift(gift)}>
                  Deliver
                </button>
                <button type="button" className="ghost" onClick={() => handleRemoveGift(gift)}>
                  Remove
                </button>
              </div>
            </div>
          ))
        )}
      </SettingsPanel>

      <SettingsPanel
        title="Trust diary"
        lead="Rematch, Investigate, and job cards in one place — so you can see what the house already decided."
        testId="house-diary"
      >
        {diaryEntries.length === 0 ? (
          <p className="settings-field-hint" data-testid="house-diary-empty">
            {diary?.empty_reason || "No rematch, Investigate, or job cards yet."}
          </p>
        ) : (
          <ol className="house-diary">
            {diaryEntries.map((entry, index) => (
              <li key={`${entry.kind}-${entry.related_id || index}`} data-testid={`house-diary-${entry.kind}`}>
                <Link to={entry.href || "/admin/libraries"}>{entry.title}</Link>
                <p className="house-diary-why">{entry.why}</p>
              </li>
            ))}
          </ol>
        )}
      </SettingsPanel>
    </div>
  );
}
