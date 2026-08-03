import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { linkifyKnownTitles, titleItemFromHref } from "../lib/titleDigIn.js";
import TitleDetailLink from "./TitleDetailLink";

function MarkdownTitleLink({ href, children }) {
  const item = titleItemFromHref(href);
  if (item) {
    return (
      <TitleDetailLink item={item} className="message-title-link" data-testid="message-title-link">
        {children}
      </TitleDetailLink>
    );
  }
  if (/^https?:\/\//.test(String(href || ""))) {
    return (
      <a href={href} target="_blank" rel="noreferrer">
        {children}
      </a>
    );
  }
  return <a href={href}>{children}</a>;
}

const markdownComponents = {
  a: MarkdownTitleLink,
  table: ({ children }) => (
    <div className="markdown-table-wrap">
      <table>{children}</table>
    </div>
  ),
  // Theme-safe footnote chrome (remark-gfm emits these).
  section: ({ children, className, ...props }) => {
    const isFootnotes =
      String(className || "").includes("footnotes") ||
      props["data-footnotes"] != null;
    if (isFootnotes) {
      return (
        <section className="markdown-footnotes" data-testid="chat-footnotes" {...props}>
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

function childText(children) {
  if (Array.isArray(children)) return children.map(childText).join("");
  if (children?.props?.children != null) return childText(children.props.children);
  return String(children ?? "");
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
  const hasMarkdownLinks = text.includes("](/title/");
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

  if (markdown || hasMarkdownLinks) {
    return (
      <div className={`${className} markdown-body`}>
        <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>
          {text}
        </ReactMarkdown>
      </div>
    );
  }

  return <p className={className}>{text}</p>;
}
