import { Link } from "react-router-dom";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import privacyMarkdown from "@docs/PRIVACY.md?raw";
import BackLink from "../components/BackLink";
import AppShell from "../layouts/AppShell";
import { ROUTES } from "../lib/backNav.js";

const GITHUB_DOCS_BASE = "https://github.com/romwil/curatorx/tree/main/docs";

/** In-app routes that should use React Router navigation. */
const IN_APP_ROUTES = new Set(["/privacy", "/about", "/help", "/settings", "/login", "/admin"]);

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

/**
 * Rewrite relative .md links from PRIVACY.md so they work inside the SPA:
 *  - anchor-only (#foo) → kept as-is
 *  - absolute http(s) → kept, opened in new tab
 *  - in-app routes (/privacy, /about, …) → React Router <Link>
 *  - wiki/*.md → GitHub docs wiki URL
 *  - *.md → GitHub docs URL
 *  - anything else → GitHub docs URL (best-effort)
 */
function MarkdownLink({ href, children }) {
  if (!href) return <a>{children}</a>;

  if (href.startsWith("#")) return <a href={href}>{children}</a>;

  if (/^https?:\/\//.test(href)) {
    return (
      <a href={href} target="_blank" rel="noreferrer">
        {children}
      </a>
    );
  }

  if (IN_APP_ROUTES.has(href) || IN_APP_ROUTES.has(href.replace(/\/$/, ""))) {
    return <Link to={href}>{children}</Link>;
  }

  // Relative .md link — rewrite to the GitHub docs tree
  if (href.startsWith("wiki/")) {
    const githubUrl = `${GITHUB_DOCS_BASE}/${href}`;
    return (
      <a href={githubUrl} target="_blank" rel="noreferrer">
        {children}
      </a>
    );
  }

  if (href.endsWith(".md") || href.includes(".md#")) {
    const githubUrl = `${GITHUB_DOCS_BASE}/${href}`;
    return (
      <a href={githubUrl} target="_blank" rel="noreferrer">
        {children}
      </a>
    );
  }

  // Fallback: treat unknown relative links as docs paths on GitHub
  const githubUrl = `${GITHUB_DOCS_BASE}/${href}`;
  return (
    <a href={githubUrl} target="_blank" rel="noreferrer">
      {children}
    </a>
  );
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
  a: MarkdownLink,
};

/**
 * Public privacy disclosure — content from docs/PRIVACY.md (vite @docs alias).
 */
export default function PrivacyPage() {
  const markdown = typeof privacyMarkdown === "string" && privacyMarkdown.trim() ? privacyMarkdown : "";

  return (
    <AppShell
      className="app-root explore-page privacy-page"
      testId="privacy-page"
      requireAuth={false}
      title="Privacy"
      eyebrow="How CuratorX handles your data"
      actions={<BackLink fallbackTo={ROUTES.chat} testId="privacy-back" label="Back to chat" />}
    >
      <main className="explore-main privacy-main">
        <nav className="privacy-jump-nav help-jump-nav" aria-label="Privacy shortcuts">
          <a href="#household-members">Household</a>
          <a href="#server-owners">Owners</a>
          <a href="#mcp">MCP</a>
          <Link to="/help">Help</Link>
          <Link to="/about">About</Link>
          <Link to="/login">Login</Link>
        </nav>
        <article className="privacy-article privacy-prose" data-testid="privacy-content" data-source="docs">
          {markdown ? (
            <ReactMarkdown remarkPlugins={[remarkGfm]} components={markdownComponents}>
              {markdown}
            </ReactMarkdown>
          ) : (
            <p className="status status-secondary">Privacy disclosure is unavailable.</p>
          )}
        </article>
      </main>
    </AppShell>
  );
}
