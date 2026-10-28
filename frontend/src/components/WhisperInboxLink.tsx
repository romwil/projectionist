import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { listWhispers } from "../api/client";
import { WHISPER_PATH, whisperHomeLabel } from "../lib/whisperInbox.js";

type WhisperListPayload = {
  member_name?: string;
  unread_count?: number;
};

type WhisperHomeState = {
  memberName: string;
  unreadCount: number;
};

/**
 * Chat-home opener for the named-member whisper inbox.
 * Self-contained so App.jsx only mounts it.
 */
export default function WhisperInboxLink() {
  const [state, setState] = useState<WhisperHomeState>({ memberName: "", unreadCount: 0 });

  useEffect(() => {
    let cancelled = false;
    listWhispers({ unread_only: true, limit: 5 })
      .then((data: WhisperListPayload) => {
        if (cancelled) return;
        setState({
          memberName: String(data?.member_name || "").trim(),
          unreadCount: Number(data?.unread_count) || 0,
        });
      })
      .catch(() => {
        if (!cancelled) setState({ memberName: "", unreadCount: 0 });
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const label = whisperHomeLabel(state);
  return (
    <div className="whisper-home-link-row" data-testid="whisper-home-link-row">
      <Link
        to={WHISPER_PATH}
        className="welcome-context-chip whisper-inbox-link"
        data-testid="whisper-inbox-link"
      >
        {label}
      </Link>
    </div>
  );
}
