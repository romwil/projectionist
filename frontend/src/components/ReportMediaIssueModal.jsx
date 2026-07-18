import { useState } from "react";
import { createMediaIssue } from "../api/client";

const ISSUE_CODES = [
  ["wrong_language", "Wrong language / subtitles"],
  ["bad_video", "Video is corrupted or unplayable"],
  ["bad_audio", "Audio is corrupted or unplayable"],
  ["wrong_title", "Wrong title or metadata"],
  ["mismatch", "This does not match the listing"],
  ["missing_subs", "Missing subtitles"],
  ["duplicate", "Duplicate copy"],
  ["other", "Something else"],
];

export default function ReportMediaIssueModal({ item, open, onClose, onReported }) {
  const [code, setCode] = useState("bad_video");
  const [note, setNote] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  if (!open) return null;

  async function submit(event) {
    event.preventDefault();
    setSaving(true);
    setError("");
    try {
      await createMediaIssue({
        code,
        note: note.trim() || undefined,
        rating_key: item?.rating_key || item?.plex_rating_key || undefined,
        tmdb_id: item?.tmdb_id || undefined,
        tvdb_id: item?.tvdb_id || undefined,
        media_type: item?.media_type || undefined,
        title: item?.title || undefined,
      });
      onReported?.();
      onClose?.();
    } catch (err) {
      setError(err.message || "Could not send the report.");
    } finally {
      setSaving(false);
    }
  }

  return <div className="media-issue-backdrop" role="presentation" onClick={onClose}>
    <form className="media-issue-modal" role="dialog" aria-modal="true" aria-label="Report a media issue" onSubmit={submit} onClick={(event) => event.stopPropagation()}>
      <h2>Report an issue</h2>
      <p>Reports go to the owner queue. They do not delete files or start a repair by themselves.</p>
      <label>Problem
        <select value={code} onChange={(event) => setCode(event.target.value)}>
          {ISSUE_CODES.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
        </select>
      </label>
      <label>Optional note
        <textarea value={note} maxLength={1000} onChange={(event) => setNote(event.target.value)} placeholder="What happened, and when?" />
      </label>
      {error ? <p className="error">{error}</p> : null}
      <div className="media-issue-actions">
        <button type="button" className="ghost" onClick={onClose} disabled={saving}>Cancel</button>
        <button type="submit" disabled={saving}>{saving ? "Sending…" : "Send report"}</button>
      </div>
    </form>
  </div>;
}
