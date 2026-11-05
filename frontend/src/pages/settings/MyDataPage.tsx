import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { deleteMyMemoryNote, eraseMyData, listMyMemoryNotes, listMyOwnerAccess } from "../../api/client";
import Button from "../../components/Button";
import SettingsPageHeader from "../../components/settings/SettingsPageHeader";
import SettingsPanel from "../../components/settings/SettingsPanel";
import {
  ERASE_CONFIRM_PHRASE,
  erasePhraseMatches,
  erasedSummary,
  exportMyDataUrl,
  noteKindLabel,
  ownerAccessLine,
  type MemoryNote,
  type OwnerAccessEntry,
} from "../../lib/myData";

function errorText(error: unknown, fallback: string) {
  return error instanceof Error && error.message ? error.message : fallback;
}

/** PRIV-023: what Projectionist keeps about the signed-in member, and their controls over it. */
export default function MyDataPage() {
  const [notes, setNotes] = useState<MemoryNote[] | null>(null);
  const [notesError, setNotesError] = useState("");
  const [deletingNote, setDeletingNote] = useState("");
  const [phrase, setPhrase] = useState("");
  const [erasing, setErasing] = useState(false);
  const [eraseStatus, setEraseStatus] = useState("");
  const [eraseError, setEraseError] = useState("");
  const [ownerAccess, setOwnerAccess] = useState<OwnerAccessEntry[] | null>(null);
  const [ownerAccessError, setOwnerAccessError] = useState("");

  function loadNotes() {
    return listMyMemoryNotes()
      .then((data) => {
        setNotesError("");
        setNotes(data?.notes || []);
      })
      .catch((error: unknown) => {
        setNotes([]);
        setNotesError(errorText(error, "Could not load your notes."));
      });
  }

  useEffect(() => {
    void loadNotes();
    listMyOwnerAccess()
      .then((data) => setOwnerAccess(data?.items || []))
      .catch((error: unknown) => {
        setOwnerAccess([]);
        setOwnerAccessError(errorText(error, "Could not load the owner-access log."));
      });
  }, []);

  async function removeNote(noteId: string) {
    setDeletingNote(noteId);
    setNotesError("");
    try {
      await deleteMyMemoryNote(noteId);
      setNotes((prev) => (prev || []).filter((note) => note.id !== noteId));
    } catch (error: unknown) {
      setNotesError(errorText(error, "Could not delete that note."));
    } finally {
      setDeletingNote("");
    }
  }

  async function eraseAll() {
    if (!erasePhraseMatches(phrase)) return;
    setErasing(true);
    setEraseError("");
    setEraseStatus("");
    try {
      const result = await eraseMyData(phrase);
      setEraseStatus(erasedSummary(Number(result?.total) || 0));
      setPhrase("");
      await loadNotes();
    } catch (error: unknown) {
      setEraseError(errorText(error, "Could not delete your data."));
    } finally {
      setErasing(false);
    }
  }

  return (
    <div className="settings-stack" data-testid="settings-my-data">
      <SettingsPageHeader title="My data" testId="settings-my-data-header">
        What Projectionist keeps about you, and what you can do about it. Everything here acts on your
        account only.
      </SettingsPageHeader>

      <SettingsPanel
        title="What the curator remembers"
        lead="Notes the curator keeps so it knows you. Deleting one removes it for good."
        testId="my-data-notes"
      >
        {notes === null ? <p className="status status-secondary">Loading notes…</p> : null}
        {notes && notes.length === 0 && !notesError ? (
          <p className="field-help" data-testid="my-data-notes-empty">
            The curator isn&apos;t keeping any notes about you.
          </p>
        ) : null}
        {notes && notes.length > 0 ? (
          <ul className="my-data-notes" aria-label="Memory notes">
            {notes.map((note) => (
              <li key={note.id} className="my-data-note" data-testid="my-data-note">
                <div>
                  <p className="eyebrow">{noteKindLabel(note.kind)}</p>
                  <p>{note.text}</p>
                </div>
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={() => removeNote(note.id)}
                  disabled={deletingNote === note.id}
                  aria-label={`Delete note: ${note.text || noteKindLabel(note.kind)}`}
                >
                  {deletingNote === note.id ? "Deleting…" : "Delete"}
                </Button>
              </li>
            ))}
          </ul>
        ) : null}
        {notesError ? (
          <p className="status status-error" role="alert">
            {notesError}
          </p>
        ) : null}
      </SettingsPanel>

      <SettingsPanel
        title="What the owner did"
        lead="Changes the household owner made to your account, and any time they opened the Youth memory review. It never shows them notes from before Youth mode."
        testId="my-data-owner-access"
      >
        {ownerAccess === null ? <p className="status status-secondary">Loading…</p> : null}
        {ownerAccess && ownerAccess.length === 0 && !ownerAccessError ? (
          <p className="field-help" data-testid="my-data-owner-access-empty">
            The owner hasn&apos;t changed anything on your account.
          </p>
        ) : null}
        {ownerAccess && ownerAccess.length > 0 ? (
          <ul className="my-data-owner-access" aria-label="Owner actions on your account">
            {ownerAccess.map((entry, index) => (
              <li key={`${entry.created_at}-${entry.event}-${index}`} data-testid="my-data-owner-access-row">
                {ownerAccessLine(entry)}
              </li>
            ))}
          </ul>
        ) : null}
        {ownerAccessError ? (
          <p className="status status-error" role="alert">
            {ownerAccessError}
          </p>
        ) : null}
      </SettingsPanel>

      <SettingsPanel
        title="Download my data"
        lead="Your profile, chats with every message, memory, watchlist, lists, ratings, inbox, Plex viewing, and the rest. Passwords and sign-in tokens are left out."
        testId="my-data-download"
      >
        <div className="settings-actions">
          <a className="btn btn-primary btn-md" href={exportMyDataUrl("json")} download data-testid="my-data-download-json">
            Download everything (JSON)
          </a>
          <a className="btn btn-secondary btn-md" href={exportMyDataUrl("markdown")} download data-testid="my-data-download-md">
            Download a readable copy
          </a>
        </div>
      </SettingsPanel>

      <SettingsPanel
        title="Delete my data"
        lead="Removes everything above except your account, so you can keep signing in and start fresh. This can't be undone."
        testId="my-data-erase"
      >
        <label className="settings-field" htmlFor="my-data-erase-phrase">
          <span id="my-data-erase-label">
            Type <kbd>{ERASE_CONFIRM_PHRASE}</kbd> to confirm
          </span>
          <input
            id="my-data-erase-phrase"
            type="text"
            autoComplete="off"
            spellCheck={false}
            value={phrase}
            disabled={erasing}
            aria-labelledby="my-data-erase-label"
            onChange={(event) => setPhrase(event.target.value)}
            data-testid="my-data-erase-phrase"
          />
        </label>
        <Button
          variant="danger"
          onClick={eraseAll}
          disabled={erasing || !erasePhraseMatches(phrase)}
          data-testid="my-data-erase-submit"
        >
          {erasing ? "Deleting…" : "Delete my data"}
        </Button>
        <p className="field-help">
          Daily backups made before today still hold your data until they roll off after seven days. If one is
          restored, Projectionist deletes your data from it again before the app starts.
        </p>
        <div aria-live="polite">
          {eraseStatus ? (
            <p className="status" data-testid="my-data-erase-status">
              {eraseStatus}
            </p>
          ) : null}
        </div>
        {eraseError ? (
          <p className="status status-error" role="alert">
            {eraseError}
          </p>
        ) : null}
      </SettingsPanel>

      <SettingsPanel title="Leave the household" testId="my-data-leave">
        <p className="field-help">
          To remove your account completely, ask the person who runs Projectionist. Removing it also deletes your
          profile and picture. <Link to="/privacy#getting-a-copy-or-leaving">What stays after removal</Link>
        </p>
      </SettingsPanel>
    </div>
  );
}
