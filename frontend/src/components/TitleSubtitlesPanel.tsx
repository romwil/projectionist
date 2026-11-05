import { useEffect, useState } from "react";
import { downloadLibraryItemSubtitles, getLibraryItemSubtitles } from "../api/client";
import { useConfirmModal } from "../hooks/useConfirmModal";
import { titleSubtitlePanelState } from "../lib/subtitleCues";

type SubtitleStream = {
  id?: string | number;
  label?: string;
  display_title?: string;
  language?: string;
};

type SubtitlePayload = {
  streams?: SubtitleStream[];
  has_preferred?: boolean;
  ok?: boolean;
  message?: string;
};

type SubtitlePanelState = {
  status: string;
  payload: SubtitlePayload | null;
  note: string;
};

type TitleSubtitlesPanelProps = {
  ratingKey?: string | number;
  canDownload?: boolean;
};

function errorMessage(error: unknown) {
  return error instanceof Error
    ? (error as { message?: string }).message
    : "message" in (error as object)
      ? String((error as { message: unknown }).message)
      : String(error);
}

/**
 * Dig-in / dual-watch subtitle surface — prefer Plex-attached tracks; soft-fail download.
 */
export default function TitleSubtitlesPanel({
  ratingKey,
  canDownload = true,
}: TitleSubtitlesPanelProps) {
  const { confirm, modal } = useConfirmModal();
  const key = String(ratingKey || "").trim();
  const [state, setState] = useState<SubtitlePanelState>({
    status: "idle",
    payload: null,
    note: "",
  });

  useEffect(() => {
    if (!key) {
      setState({ status: "idle", payload: null, note: "" });
      return undefined;
    }
    let cancelled = false;
    setState({ status: "loading", payload: null, note: "" });
    getLibraryItemSubtitles(key)
      .then((payload: SubtitlePayload) => {
        if (!cancelled) setState({ status: "ready", payload, note: "" });
      })
      .catch((error: unknown) => {
        if (!cancelled) {
          setState({
            status: "ready",
            payload: null,
            note: errorMessage(error) || "Couldn’t read subtitle tracks from Plex.",
          });
        }
      });
    return () => {
      cancelled = true;
    };
  }, [key]);

  if (!key) return null;

  const panel = titleSubtitlePanelState(state.payload);
  const showAsk = canDownload && state.status === "ready" && panel.showAsk;

  async function onAskPlex() {
    if (
      !(await confirm({
        title: "Download subtitles",
        body: "Ask Plex to search and download subtitles for this title?",
        confirmLabel: "Ask Plex",
      }))
    ) {
      return;
    }
    setState((prev) => ({ ...prev, status: "downloading", note: "" }));
    try {
      const result = (await downloadLibraryItemSubtitles(key)) as {
        ok?: boolean;
        message?: string;
      };
      const refreshed = result?.ok ? await getLibraryItemSubtitles(key) : state.payload;
      setState({
        status: "ready",
        payload: refreshed || state.payload,
        note: result?.message || "",
      });
    } catch (error: unknown) {
      setState((prev) => ({
        ...prev,
        status: "ready",
        note: errorMessage(error) || "Plex couldn’t download subtitles.",
      }));
    }
  }

  return (
    <section className="title-subtitles-panel" data-testid="title-subtitles-panel">
      <h3 className="title-subtitles-heading">Subtitles</h3>
      {state.status === "loading" ? <p className="wizard-note">Checking Plex…</p> : null}
      {panel.tracks.length ? (
        <ul className="title-subtitles-list" data-testid="title-subtitles-list">
          {panel.tracks.map((track) => (
            <li key={track.id} data-testid={track.onServer ? "title-subtitles-cached" : undefined}>
              {track.label}
            </li>
          ))}
        </ul>
      ) : state.status === "ready" ? (
        <p className="wizard-note" data-testid="title-subtitles-empty">
          {state.payload?.message || "No subtitle tracks attached in Plex yet."}
        </p>
      ) : null}
      {showAsk ? (
        <button
          type="button"
          className="ghost"
          data-testid="title-subtitles-ask-plex"
          disabled={state.status === "downloading"}
          onClick={onAskPlex}
        >
          {state.status === "downloading" ? "Asking Plex…" : "Ask Plex for subtitles"}
        </button>
      ) : null}
      {state.note ? (
        <p className="wizard-note" data-testid="title-subtitles-note">
          {state.note}
        </p>
      ) : null}
      {modal}
    </section>
  );
}
