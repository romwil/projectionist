import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

/**
 * Public privacy disclosure page.
 * Tries /privacy.md (static asset synced with docs/PRIVACY.md); falls back to a stub outline.
 */
const FALLBACK = `# Privacy & data use

CuratorX is self-hosted software. Your media credentials and household taste stay on the machine you run.

## For household members

- Sign in with Plex shares display name, optional email/avatar, and may link Seerr when the owner enables it.
- Chat history, ratings, and watchlist pins are yours when multi-user is on.
- The library catalog is shared household context.
- The owner's configured LLM provider receives prompts and tool results (title metadata — not Plex tokens).

## For server owners

- Fleet credentials live in Admin. Only owners should open Admin.
- MCP keys (when enabled) expose library intelligence according to privacy vs full mode — see Security docs when published.

## Voice

If you enable voice in Settings, your browser or OS may process speech. CuratorX stores transcripts as chat text, not raw audio files.

---

_Full disclosure text will mirror \`docs/PRIVACY.md\` when that document ships. Meanwhile use the links below._
`;

export default function PrivacyPage() {
  const [markdown, setMarkdown] = useState("");
  const [source, setSource] = useState("loading");

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const response = await fetch("/privacy.md", { credentials: "same-origin" });
        if (!response.ok) throw new Error("missing");
        const text = await response.text();
        if (cancelled) return;
        if (!text.trim() || text.trim().startsWith("<!")) {
          setMarkdown(FALLBACK);
          setSource("fallback");
          return;
        }
        setMarkdown(text);
        setSource("file");
      } catch {
        if (!cancelled) {
          setMarkdown(FALLBACK);
          setSource("fallback");
        }
      }
    }
    load();
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <div className="editorial-page privacy-page" data-testid="privacy-page" data-source={source}>
      <header className="editorial-header">
        <p className="eyebrow">Disclosure</p>
        <h1>Privacy &amp; data use</h1>
        <p className="editorial-lede">
          What CuratorX stores, what the chat model sees, and what never leaves your stack.
        </p>
      </header>

      <article className="editorial-prose" data-testid="privacy-content">
        {source === "loading" ? (
          <p className="status status-secondary">Loading…</p>
        ) : (
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{markdown}</ReactMarkdown>
        )}
      </article>

      <p className="editorial-back">
        <Link to="/login">Login</Link>
        {" · "}
        <Link to="/about">About</Link>
        {" · "}
        <Link to="/">Chat</Link>
      </p>
    </div>
  );
}
