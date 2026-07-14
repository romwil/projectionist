import { Link } from "react-router-dom";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import privacyMarkdown from "@docs/PRIVACY.md?raw";

/** Stable ids for in-page jump links / e2e (must match docs/PRIVACY.md anchors). */
const HEADING_ANCHORS = {
  "from the household member": "household-members",
  "from the server owner": "server-owners",
  "mcp (model context protocol)": "mcp",
  "exposure matrices": "exposure-matrices",
  "we do not": "we-do-not",
};

function headingText(children) {
  if (typeof children === "string") return children;
  if (Array.isArray(children)) return children.map(headingText).join("");
  if (children?.props?.children) return headingText(children.props.children);
  return "";
}

function headingId(children) {
  const text = headingText(children).trim().toLowerCase();
  for (const [prefix, id] of Object.entries(HEADING_ANCHORS)) {
    if (text.startsWith(prefix)) return id;
  }
  return undefined;
}

const markdownComponents = {
  h2: ({ children, ...props }) => {
    const id = headingId(children);
    return (
      <h2 id={id} {...props}>
        {children}
      </h2>
    );
  },
  table: ({ children }) => (
    <div className="privacy-table-wrap">
      <table>{children}</table>
    </div>
  ),
};

/**
 * Public privacy disclosure — content from docs/PRIVACY.md (vite @docs alias).
 */
export default function PrivacyPage() {
  const markdown = typeof privacyMarkdown === "string" && privacyMarkdown.trim() ? privacyMarkdown : "";

  return (
    <div className="privacy-page" data-testid="privacy-page" data-source="docs">
      <header className="privacy-topbar">
        <Link to="/" className="privacy-brand">
          CuratorX
        </Link>
        <nav className="privacy-topnav" aria-label="Privacy shortcuts">
          <a href="#household-members">Household</a>
          <a href="#server-owners">Owners</a>
          <a href="#mcp">MCP</a>
          <Link to="/about">About</Link>
          <Link to="/login">Login</Link>
        </nav>
      </header>

      <article className="privacy-article privacy-prose" data-testid="privacy-content">
        {markdown ? (
          <ReactMarkdown remarkPlugins={[remarkGfm]} components={markdownComponents}>
            {markdown}
          </ReactMarkdown>
        ) : (
          <p className="status status-secondary">Privacy disclosure is unavailable.</p>
        )}
      </article>

      <footer className="privacy-footer">
        <Link to="/about">About</Link>
        {" · "}
        <Link to="/settings">Settings</Link>
        {" · "}
        <Link to="/">Chat</Link>
      </footer>
    </div>
  );
}
