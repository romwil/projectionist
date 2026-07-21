import { useEffect } from "react";
import { Link, useLocation } from "react-router-dom";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import helpMarkdown from "@docs/HELP.md?raw";
import BackLink from "../components/BackLink";
import { useAuthGate } from "../components/UserMenu";
import AppShell from "../layouts/AppShell";
import { ROUTES } from "../lib/backNav.js";
import { slugify, targetIdFromHash } from "../lib/helpAnchors.js";

const GITHUB_DOCS_BASE = "https://github.com/romwil/curatorx/tree/main/docs";

/** In-app routes that should use React Router navigation. */
const IN_APP_ROUTES = new Set([
  "/",
  "/help",
  "/privacy",
  "/about",
  "/settings",
  "/login",
  "/admin",
  "/admin/tasks",
  "/admin/dashboard",
  "/explore",
  "/explore/tags",
  "/explore/plot-lab",
  "/watchlist",
]);

function headingText(children) {
  if (typeof children === "string") return children;
  if (Array.isArray(children)) return children.map(headingText).join("");
  if (children?.props?.children) return headingText(children.props.children);
  return "";
}

/**
 * GitHub-style anchor id for a heading. Every h2/h3/h4 gets a stable slug so
 * any section is deep-linkable — no hand-maintained lookup table to drift.
 */
function headingId(children) {
  return slugify(headingText(children)) || undefined;
}

/**
 * Rewrite relative .md links from HELP.md so they work inside the SPA:
 *  - anchor-only (#foo) → kept as-is
 *  - absolute http(s) → kept, opened in new tab
 *  - in-app routes → React Router <Link>
 *  - *.md → GitHub docs URL
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

  const pathOnly = href.split("#")[0].replace(/\/$/, "") || href;
  if (IN_APP_ROUTES.has(href) || IN_APP_ROUTES.has(pathOnly)) {
    return <Link to={href}>{children}</Link>;
  }

  if (href.startsWith("wiki/")) {
    return (
      <a href={`${GITHUB_DOCS_BASE}/${href}`} target="_blank" rel="noreferrer">
        {children}
      </a>
    );
  }

  if (href.endsWith(".md") || href.includes(".md#")) {
    return (
      <a href={`${GITHUB_DOCS_BASE}/${href}`} target="_blank" rel="noreferrer">
        {children}
      </a>
    );
  }

  return (
    <a href={`${GITHUB_DOCS_BASE}/${href}`} target="_blank" rel="noreferrer">
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
  h3: ({ children, ...props }) => {
    const id = headingId(children);
    return (
      <h3 id={id} {...props}>
        {children}
      </h3>
    );
  },
  h4: ({ children, ...props }) => {
    const id = headingId(children);
    return (
      <h4 id={id} {...props}>
        {children}
      </h4>
    );
  },
  table: ({ children }) => (
    <div className="privacy-table-wrap">
      <table>{children}</table>
    </div>
  ),
  a: MarkdownLink,
};

const OWNER_SECTION_MARKER = "## For owners";

/** Drop owner/scheduler sections for members/guests; keep full doc for owners. */
function markdownForRole(source, { includeOwnerSections }) {
  const text = typeof source === "string" ? source.trim() : "";
  if (!text) return "";
  if (includeOwnerSections) return text;
  const idx = text.indexOf(OWNER_SECTION_MARKER);
  if (idx === -1) return text;
  const before = text.slice(0, idx).trimEnd();
  const relatedIdx = text.indexOf("## Related documentation", idx);
  const related = relatedIdx === -1 ? "" : text.slice(relatedIdx).trim();
  return [before, related].filter(Boolean).join("\n\n");
}

/**
 * In-app Help — content from docs/HELP.md (vite @docs alias).
 * Role-aware: owners see curation/scheduler sections; members/guests get browse/chat.
 */
export default function HelpPage() {
  const { isOwner, role, multiUserEnabled } = useAuthGate({ redirect: false });
  const showOwnerNav = isOwner || !multiUserEnabled;
  const markdown = markdownForRole(helpMarkdown, { includeOwnerSections: showOwnerNav });
  const { hash } = useLocation();

  // Scroll to the anchored section once react-markdown has painted the headings.
  // Runs after render (and on hash change) with a couple of frames + a fallback
  // timeout so it wins over any route-level scroll reset.
  useEffect(() => {
    const id = targetIdFromHash(hash);
    if (!id) return undefined;
    let raf1 = 0;
    let raf2 = 0;
    const scrollToTarget = () => {
      const el = typeof document !== "undefined" ? document.getElementById(id) : null;
      if (el) el.scrollIntoView({ block: "start" });
    };
    raf1 = requestAnimationFrame(() => {
      raf2 = requestAnimationFrame(scrollToTarget);
    });
    const timer = setTimeout(scrollToTarget, 250);
    return () => {
      cancelAnimationFrame(raf1);
      cancelAnimationFrame(raf2);
      clearTimeout(timer);
    };
  }, [hash, markdown]);

  const roleLabel = !multiUserEnabled
    ? "Single workspace"
    : role === "owner"
      ? "Owner"
      : role === "member"
        ? "Household member"
        : "Guest";

  return (
    <AppShell
      className="app-root explore-page help-page"
      testId="help-page"
      requireAuth={false}
      title="Help"
      eyebrow="Chat, Explore, Plot Lab, and idle curation"
      actions={<BackLink fallbackTo={ROUTES.chat} testId="help-back" label="Back to chat" />}
    >
      <main className="explore-main help-main">
        <section className="explore-section help-role-bar" aria-label="Help shortcuts">
          <p className="status status-secondary help-role-meta" data-testid="help-role-label">
            Viewing as {roleLabel}
            {showOwnerNav
              ? " — owner guidance included below."
              : " — browse and chat guidance below. Ask the server owner about sync and scheduled tasks."}
          </p>
          <nav className="help-jump-nav" aria-label="Help sections">
            <a href="#start-here">Start</a>
            <a href="#chat">Chat</a>
            <a href="#plot-lab">Plot Lab</a>
            <a href="#title-detail--plot-knowledge">Plot knowledge</a>
            <a href="#why-motif-walls-feel-sparse">Sparse walls</a>
            {showOwnerNav ? (
              <>
                <a href="#for-owners--curation--scheduler" data-testid="help-jump-owners">
                  Owners
                </a>
                <a href="#coverage-over-time" data-testid="help-jump-coverage">
                  Coverage
                </a>
                <Link to={ROUTES.adminTasks} data-testid="help-link-admin-tasks">
                  Scheduled Tasks
                </Link>
                <Link to={ROUTES.adminDashboard} data-testid="help-link-admin-dashboard">
                  Dashboard
                </Link>
              </>
            ) : null}
            <Link to={ROUTES.plotLab}>Plot Lab app</Link>
            <Link to={ROUTES.about}>About</Link>
            <Link to="/privacy">Privacy</Link>
            <a
              href={`${GITHUB_DOCS_BASE}/CURATOR_KNOWLEDGE.md`}
              target="_blank"
              rel="noreferrer"
              data-testid="help-link-knowledge"
            >
              Knowledge guide
            </a>
          </nav>
        </section>

        <article className="help-article privacy-prose" data-testid="help-content" data-source="docs">
          {markdown ? (
            <ReactMarkdown remarkPlugins={[remarkGfm]} components={markdownComponents}>
              {markdown}
            </ReactMarkdown>
          ) : (
            <p className="status status-secondary">Help content is unavailable.</p>
          )}
        </article>
      </main>
    </AppShell>
  );
}
