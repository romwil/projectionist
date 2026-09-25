import { useEffect, useMemo, useState } from "react";
import ReactMarkdown from "react-markdown";
import rehypeSanitize, { defaultSchema } from "rehype-sanitize";
import remarkGfm from "remark-gfm";
import {
  findFootnote,
  footnoteIdFromHref,
  footnoteSheetLabel,
  footnoteWalkKind,
  parseMarkdownFootnotes,
} from "../lib/chatFootnotes.js";
import { isAllowedMarkdownHref } from "../lib/markdownHref.js";
import { linkifyKnownTitles, titleItemFromHref } from "../lib/titleDigIn.js";
import TitleDetailLink from "./TitleDetailLink";
import "./MessageText.css";

const markdownSanitizeSchema = {
  ...defaultSchema,
  protocols: {
    ...defaultSchema.protocols,
    href: ["http", "https"],
  },
};

function MarkdownTitleLink({ href, children }) {
  const item = titleItemFromHref(href);
  if (item) {
    return (
      <TitleDetailLink item={item} className="message-title-link" data-testid="message-title-link">
        {children}
      </TitleDetailLink>
    );
  }
  if (!isAllowedMarkdownHref(href)) {
    return children;
  }
  if (/^https?:\/\//i.test(String(href || ""))) {
    return (
      <a href={href} target="_blank" rel="noreferrer">
        {children}
      </a>
    );
  }
  return <a href={href}>{children}</a>;
}

function isFootnoteRefLink(href, props) {
  if (props["data-footnote-backref"] != null) return false;
  if (props["data-footnote-ref"] != null) return true;
  return /(?:^|#)(?:user-content-)?fn(?:ref)?-/i.test(String(href || ""));
}

function childText(children) {
  if (Array.isArray(children)) return children.map(childText).join("");
  if (children?.props?.children != null) return childText(children.props.children);
  return String(children ?? "");
}

function buildMarkdownComponents({ onOpenFootnote }) {
  return {
    a: ({ href, children, ...props }) => {
      if (isFootnoteRefLink(href, props)) {
        const id = footnoteIdFromHref(href, childText(children));
        return (
          <button
            type="button"
            className="markdown-footnote-ref"
            data-testid="chat-footnote-ref"
            data-footnote-id={id}
            onClick={(event) => {
              event.preventDefault();
              onOpenFootnote(id);
            }}
          >
            {children}
          </button>
        );
      }
      return <MarkdownTitleLink href={href}>{children}</MarkdownTitleLink>;
    },
    table: ({ children }) => (
      <div className="markdown-table-wrap">
        <table>{children}</table>
      </div>
    ),
    // Theme-safe footnote chrome (remark-gfm emits these). Hide the raw dump;
    // [^1] refs open the sheet instead.
    section: ({ children, className, ...props }) => {
      const isFootnotes =
        String(className || "").includes("footnotes") ||
        props["data-footnotes"] != null;
      if (isFootnotes) {
        return (
          <section
            {...props}
            className="markdown-footnotes"
            data-testid="chat-footnotes"
            hidden
            aria-hidden="true"
          >
            {children}
          </section>
        );
      }
      return (
        <section className={className} {...props}>
          {children}
        </section>
      );
    },
    sup: ({ children, ...props }) => (
      <sup className="markdown-footnote-ref" {...props}>
        {children}
      </sup>
    ),
  };
}

export default function MessageText({
  content,
  markdown = false,
  className = "message-text",
  titleRefs = [],
  headingActionLabel = "",
  headingActions = null,
}) {
  const text = linkifyKnownTitles(content, titleRefs);
  const footnotes = useMemo(() => parseMarkdownFootnotes(text), [text]);
  const [openId, setOpenId] = useState("");
  const openNote = findFootnote(footnotes, openId);
  const hasMarkdownLinks = text.includes("](/title/");
  const markdownComponents = useMemo(
    () => buildMarkdownComponents({ onOpenFootnote: setOpenId }),
    [],
  );
  const components = headingActions && headingActionLabel
    ? {
        ...markdownComponents,
        ...Object.fromEntries(
          ["h1", "h2", "h3", "h4", "h5", "h6"].map((tag) => [
            tag,
            ({ children }) => {
              const Heading = tag;
              const matches = childText(children).trim() === headingActionLabel;
              return (
                <Heading className={matches ? "agent-media-heading" : undefined}>
                  <span>{children}</span>
                  {matches ? headingActions : null}
                </Heading>
              );
            },
          ]),
        ),
      }
    : markdownComponents;

  useEffect(() => {
    if (!openNote) return undefined;
    const onKey = (event) => {
      if (event.key === "Escape") setOpenId("");
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [openNote]);

  if (markdown || hasMarkdownLinks) {
    return (
      <div className={`${className} markdown-body`}>
        <ReactMarkdown
          remarkPlugins={[remarkGfm]}
          rehypePlugins={[[rehypeSanitize, markdownSanitizeSchema]]}
          components={components}
        >
          {text}
        </ReactMarkdown>
        {openNote ? (
          <div
            className="chat-footnote-sheet-scrim"
            onClick={() => setOpenId("")}
          >
            <aside
              className="chat-footnote-sheet"
              role="dialog"
              aria-modal="true"
              aria-label={footnoteSheetLabel(openNote)}
              data-testid="chat-footnote-sheet"
              data-walk-kind={footnoteWalkKind(openNote.id) || undefined}
              onClick={(event) => event.stopPropagation()}
            >
              <p className="chat-footnote-sheet-label">{footnoteSheetLabel(openNote)}</p>
              <p className="chat-footnote-sheet-body">{openNote.text}</p>
              <button
                type="button"
                className="chat-footnote-sheet-close"
                onClick={() => setOpenId("")}
              >
                Close
              </button>
            </aside>
          </div>
        ) : null}
      </div>
    );
  }

  return <p className={className}>{text}</p>;
}
