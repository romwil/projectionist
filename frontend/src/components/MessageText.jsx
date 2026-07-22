import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

const markdownComponents = {
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

export default function MessageText({ content, markdown = false, className = "message-text" }) {
  if (markdown) {
    return (
      <div className={`${className} markdown-body`}>
        <ReactMarkdown remarkPlugins={[remarkGfm]} components={markdownComponents}>
          {content}
        </ReactMarkdown>
      </div>
    );
  }

  return <p className={className}>{content}</p>;
}
